"""
Build System HTML Module
========================
Builds the website. Pages whose inputs have not changed since the last build are
skipped (see page_fingerprint).
"""

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from .book import Book, Page, ENGINE_ROOT
from .macros import mathjax_macros_js
from .manifest import (scan_labels, load_scan, generate_theorem_manifest, generate_navigation_manifest,
                       generate_search_index, generate_site_files, page_description)
from .pandoc import build_pandoc_command, page_metadata, run_pandoc
from .extras import extra_page_names, generate_extra_pages
from .external import lookup as lookup_external, publish_labels
from .math import MATHJAX_VERSION, ensure_mathjax, render_math
from .tikz import build_tikz_figures
from .utils import print_step, print_file_action, print_success, print_error

ASSET_EXTENSIONS = ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg")


# =============================================================================
# Assets
# =============================================================================

def copy_html_assets(book: Book) -> str:
    """Write styles, scripts and MathJax macros. Returns a version hash of these assets."""
    out = book.html_dir
    out.mkdir(parents=True, exist_ok=True)
    assets = {
        "styles.css": book.html_styles.read_bytes(),
        "main.js": book.engine_file("templates/html/main.js").read_bytes(),
        "components.js": book.engine_file("templates/html/components.js").read_bytes(),
        "graph.js": book.engine_file("templates/html/graph.js").read_bytes(),
        "favicon.svg": book.engine_file("templates/html/favicon.svg").read_bytes(),
        "mathjax-macros.js": mathjax_macros_js(book.macros_file).encode("utf-8"),
    }
    # Component modules, widgets (engine, then the book's), and fonts
    for directory, prefix, pattern in (
        (ENGINE_ROOT / "templates" / "html" / "components", "components", "*.js"),
        (ENGINE_ROOT / "widgets", "widgets", "*.js"),
        (book.root / "widgets", "widgets", "*.js"),
        (ENGINE_ROOT / "templates" / "html" / "fonts", "fonts", "*"),
    ):
        if directory.is_dir():
            for path in sorted(p for p in directory.glob(pattern) if p.is_file()):
                assets[f"{prefix}/{path.name}"] = path.read_bytes()
    digest = hashlib.sha1()
    for name, content in assets.items():
        digest.update(content)
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)
    return digest.hexdigest()[:10]


def copy_chapter_assets(book: Book):
    """Copy images from chapter directories to the output."""
    count = 0
    for chapter in book.chapters:
        if not chapter.directory.is_dir():
            continue
        destination = book.html_dir / chapter.slug
        destination.mkdir(parents=True, exist_ok=True)
        for pattern in ASSET_EXTENSIONS:
            for source in chapter.directory.glob(pattern):
                target = destination / source.name
                if not target.exists() or source.stat().st_mtime > target.stat().st_mtime:
                    shutil.copy2(source, target)
                    print_file_action("Copying asset", source.name, target.name)
                    count += 1
    if count:
        print_success(f"Copied {count} chapter assets")


# =============================================================================
# Incremental Builds
# =============================================================================

def page_fingerprint(book: Book, page: Page, metadata: dict, engine: str, scan: dict, labels: dict) -> str:
    """Hash of everything a page's output depends on."""
    refs = scan["files"].get(page.html_path, {}).get("refs", [])
    referenced = {
        ref: {k: labels[ref].get(k) for k in ("type_name", "number", "title_html", "file", "shard")}
        for ref in sorted(set(refs)) if ref in labels
    }
    digest = hashlib.sha1()
    digest.update(engine.encode())
    digest.update(page.source.read_bytes())
    digest.update(json.dumps(metadata, sort_keys=True).encode())
    digest.update(json.dumps(referenced, sort_keys=True).encode())
    digest.update(json.dumps(sorted(set(refs) - set(labels))).encode())  # unresolved refs
    # References into other books: what each resolves to there (None: no such label,
    # {}: that book's registry could not be read)
    external = {ref: lookup_external(book, ref) for ref in sorted(set(refs) - set(labels))}
    digest.update(json.dumps({k: v for k, v in external.items() if v is not None},
                             sort_keys=True).encode())
    return digest.hexdigest()


class FingerprintStore:
    """Fingerprints of the last successful build of each output, persisted as JSON."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def unchanged(self, key: str, fingerprint: str, output: Path) -> bool:
        return output.exists() and self.data.get(key) == fingerprint

    def record(self, key: str, fingerprint: str):
        self.data[key] = fingerprint

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")


# =============================================================================
# HTML Building
# =============================================================================

def _prune_stale_pages(book: Book) -> int:
    """Delete built pages whose source is gone, inside chapters the book still has.

    A renamed or split section leaves its old .html behind, and nothing downstream can
    tell it from a live page. `check` then follows a link into it and reports a broken
    anchor that does not exist in the sources; worse, `deploy` copies the whole chapter
    directory, so the stale page is published at its old URL -- and because a real page
    then sits there, write_redirects steps aside and the redirect that should have stood
    there is never written. Splitting ch13 §06 produced six of these at once.

    `deploy.is_stale_chapter_dir` covers a whole chapter that was renamed away. This is
    the same failure one level down, inside a chapter that is still live.
    """
    removed = 0
    for chapter in book.chapters:
        directory = book.html_dir / chapter.slug
        if not directory.is_dir():
            continue
        live = {Path(page.html_path).name for page in book.pages
                if Path(page.html_path).parent.name == chapter.slug}
        for built in directory.glob("*.html"):
            if built.name not in live:
                built.unlink()
                removed += 1
    if removed:
        print_step(f"Removed {removed} built page(s) whose source is gone")
    return removed


def build_html(book: Book, specific_file: Optional[Path] = None, dev_reload: bool = False) -> bool:
    """Build the website (or one page). Returns True if every page built."""
    print_step("Building HTML...")
    scan = scan_labels(book)
    _, labels = load_scan(book)

    asset_version = copy_html_assets(book)
    copy_chapter_assets(book)

    pages = book.pages
    if specific_file:
        page = book.page_for(specific_file)
        if not page:
            print_error(f"File not found in chapters: {specific_file}")
            return False
        pages = [page]

    if not specific_file:
        _prune_stale_pages(book)

    book.tikz_cache_dir.mkdir(parents=True, exist_ok=True)
    engine = book.engine_fingerprint()
    store = FingerprintStore(book.cache_dir / "html-fingerprints.json")
    extra = {"asset-version": asset_version}
    if dev_reload:
        extra["dev-reload"] = True
    mathjax = ensure_mathjax(book)
    if mathjax:
        extra["math-prerendered"] = True
        extra["mathjax-version"] = MATHJAX_VERSION

    site_url = book.site_url
    tasks = []
    for page in pages:
        output_file = book.html_dir / page.html_path
        page_extra = dict(extra)
        description = page_description(scan["files"].get(page.html_path, {}).get("description", ""))
        if description:
            page_extra["description"] = description
        if site_url:
            page_extra["canonical-url"] = f"{site_url}{page.html_path}"
        metadata = page_metadata(book, page, "html", page_extra)
        fingerprint = page_fingerprint(book, page, metadata, engine, scan, labels)
        if store.unchanged(page.html_path, fingerprint, output_file):
            continue
        output_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = build_pandoc_command(book, page, output_file, "html", metadata)
        tasks.append((page, fingerprint, cmd))

    failures = 0
    built = []  # (page, fingerprint) of pages written this run
    if tasks:
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
            for (page, fingerprint, _), ok in zip(tasks, executor.map(lambda t: run_pandoc(t[2]), tasks)):
                if ok:
                    built.append((page, fingerprint))
                    print_file_action("Built", page.source.name, Path(page.html_path).name)
                else:
                    failures += 1
    skipped = len(pages) - len(tasks)
    print_success(f"HTML build complete: {len(tasks) - failures}/{len(tasks)} built"
                  + (f", {skipped} unchanged" if skipped else ""))

    build_tikz_figures(book)
    generate_theorem_manifest(book)
    publish_labels(book, labels)
    generate_navigation_manifest(book)
    generate_search_index(book)
    generate_site_files(book)
    extras_ok = generate_extra_pages(book, extra)
    if not extras_ok:
        failures += 1

    # Math: rendered into the pages written this run, the generated pages and tooltip data.
    # A page's fingerprint is recorded only once it is complete.
    if mathjax:
        targets = [book.html_dir / page.html_path for page, _ in built]
        if extras_ok:
            targets += [book.html_dir / name for name in extra_page_names(book)]
        # One file per result, under theorems/<chapter>/; the glob must recurse or the
        # tooltips ship raw TeX and the reader waits on MathJax at the first hover.
        shards = sorted((book.html_dir / "theorems").glob("*/*.json"))
        if not render_math(book, mathjax, targets, shards):
            failures += 1
            built = []
    for page, fingerprint in built:
        store.record(page.html_path, fingerprint)
    store.save()
    return failures == 0
