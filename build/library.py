"""
Build System Library Module
===========================
A library is several books published side by side on one origin, each in its own
sub-directory, with a generated landing page:

    ./build.py library site/books.json             # from any book, or the engine checkout
    ./build.py library site/books.json --out _site --with-pdf

The manifest (paths in it are relative to the manifest's directory):

    {
      "site-url": "https://example.github.io/library/",
      "out": "site",
      "landing": {...},                     # the landing page: see build/landing.py
      "files": [{"from": "generated/atlas.html", "to": "atlas/atlas.html"}],
      "books": [{"prefix": "fd1", "title": "Logic and Proof", "short": "FD1",
                 "blurb": "...", "planned": 7, "path": "../foundations/fd1", "subdir": "fd1",
                 "series": "Foundations", "overlay": {...},
                 "canonical": "https://fd1.example.org/"}]
    }

Two passes, so books may cite each other in both directions:

1. every book's label registry (`scan`, into its `<build-dir>/crossref_labels.json`);
2. every book's website, with a generated config overlay: `site-url` = the library's
   `site-url` + the book's sub-directory, `external-books` = every other book of the
   manifest under its prefix, `url` the relative path to its sub-directory (so links and
   hover previews stay on the same origin) and `labels` its pass-1 registry; and
   `canonical-url` = the book's `canonical` (its own production site, where its pages'
   canonical and og:url links then point; it gets no sitemap in the library), or none.

Each book is built in `_build/library` (the manifest's `build-dir`), never in the
author's `_build/html`, then its HTML copied to `<out>/<subdir>/`. The library root gets
`index.html` (the landing page), `404.html` (sends a reader to the book whose
sub-directory the missing path is in), `robots.txt`, `sitemap.xml` (an index of every
book's sitemap) and `.nojekyll`.
"""

import json
import posixpath
import re
import shutil
from html import escape
from pathlib import Path

from .book import Book, ENGINE_ROOT, load_overlay, merge_patch
from .landing import groups as _groups, landing_page, not_found_page, render_landing_math  # noqa: F401
from .deploy import is_stale_chapter_dir, write_redirects
from .utils import print_header, print_step, print_success, print_error, print_info, print_warning

DEFAULT_BUILD_DIR = "_build/library"
SUBDIR = re.compile(r"^[A-Za-z0-9][\w.-]*(/[A-Za-z0-9][\w.-]*)*$")


class ManifestError(ValueError):
    pass


# =============================================================================
# Manifest
# =============================================================================

def load_manifest(path: Path) -> dict:
    """The manifest, checked and normalized: absolute book paths, a subdir per book."""
    path = Path(path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ManifestError(f"cannot read {path}: {error.strerror or error}") from error
    except ValueError as error:
        raise ManifestError(f"{path} is not valid JSON ({error})") from error
    if not isinstance(data, dict):
        raise ManifestError(f"{path} must hold a JSON object")
    base = path.parent
    site_url = (data.get("site-url") or "").strip()
    if not re.match(r"^https?://[^/]+(/.*)?$", site_url):
        raise ManifestError('"site-url" must be an http(s) address, e.g. "https://example.org/library/"')
    if not site_url.endswith("/"):
        site_url += "/"
    books = data.get("books")
    if not isinstance(books, list) or not books:
        raise ManifestError('"books" must be a non-empty list')
    seen_prefixes, seen_subdirs, normalized = set(), set(), []
    for position, entry in enumerate(books, start=1):
        if not isinstance(entry, dict):
            raise ManifestError(f"books[{position}] must be an object")
        prefix = entry.get("prefix") or ""
        if not re.match(r"^[A-Za-z]\w*$", prefix):
            raise ManifestError(f"books[{position}]: \"prefix\" must be a word starting with a letter")
        subdir = (entry.get("subdir") or prefix).strip("/")
        if not SUBDIR.match(subdir) or ".." in subdir.split("/"):
            raise ManifestError(f"book {prefix}: \"subdir\" {subdir!r} must be a relative path like \"fd1\"")
        if prefix in seen_prefixes:
            raise ManifestError(f"book prefix {prefix!r} appears twice")
        if subdir in seen_subdirs:
            raise ManifestError(f"subdir {subdir!r} appears twice")
        if any(subdir.startswith(other + "/") or other.startswith(subdir + "/") for other in seen_subdirs):
            raise ManifestError(f"subdir {subdir!r} nests inside another book's")
        seen_prefixes.add(prefix)
        seen_subdirs.add(subdir)
        if not entry.get("path"):
            raise ManifestError(f"book {prefix}: \"path\" (the book's directory) is missing")
        canonical = (entry.get("canonical") or "").strip()
        if canonical:
            if not re.match(r"^https?://[^/]+(/.*)?$", canonical):
                raise ManifestError(f"book {prefix}: \"canonical\" must be an http(s) address, "
                                    "e.g. \"https://book.example.org/\"")
            if not canonical.endswith("/"):
                canonical += "/"
        overlay = entry.get("overlay")
        if isinstance(overlay, str):
            overlay = load_overlay(base / overlay)
        normalized.append(dict(entry, prefix=prefix, subdir=subdir, canonical=canonical or None,
                               path=(base / entry["path"]).resolve(), overlay=overlay or {}))
    files = []
    for item in data.get("files") or []:
        if not isinstance(item, dict) or not item.get("from") or not item.get("to"):
            raise ManifestError('"files" entries are {"from": path, "to": path in the site}')
        to = item["to"].strip("/")
        if ".." in to.split("/"):
            raise ManifestError(f"files: {to!r} leaves the site")
        files.append({"from": (base / item["from"]).resolve(), "to": to})
    out = data.get("out") or "site"
    return {
        "site-url": site_url,
        "out": (base / out).resolve(),
        "build-dir": data.get("build-dir") or DEFAULT_BUILD_DIR,
        "landing": data.get("landing") or {},
        "files": files,
        "books": normalized,
        "file": path,
    }


def relative_url(from_subdir: str, to_subdir: str) -> str:
    """The URL of one book's root seen from another's: "../fd2/" for siblings."""
    return posixpath.relpath(to_subdir, from_subdir) + "/"


def book_overlay(manifest: dict, entry: dict, own_config: dict, registries: dict) -> dict:
    """The config overlay one book is built with (see the module docstring).

    `registries` maps each prefix to its pass-1 label registry. The other books' `title`
    and `short` come from the manifest unless the book's own config already names them
    for that prefix; `url` and `labels` always come from the library.
    """
    own_external = own_config.get("external-books") or {}
    external = {}
    for other in manifest["books"]:
        if other["prefix"] == entry["prefix"]:
            continue
        spec = {"url": relative_url(entry["subdir"], other["subdir"]),
                "labels": str(registries[other["prefix"]])}
        mine = own_external.get(other["prefix"]) or {}
        if not mine.get("title"):
            spec["title"] = other.get("title") or other["prefix"]
        if not mine.get("short"):
            spec["short"] = other.get("short") or other["prefix"].upper()
        external[other["prefix"]] = spec
    overlay = {
        "site-url": manifest["site-url"] + entry["subdir"] + "/",
        "deploy-domain": None,     # the library's own address, not the book's own domain
        # canonical and og:url: the book's own site when the manifest names one
        # ("canonical"), else the library (a canonical-url of the book's config is dropped)
        "canonical-url": entry.get("canonical"),
        "build-dir": manifest["build-dir"],
        "output": None,            # every output inside build-dir
        "external-books": external,
    }
    return merge_patch(overlay, entry.get("overlay") or {})


# =============================================================================
# Building
# =============================================================================

def build_library(manifest_path, out=None, with_pdf: bool = False, extra_overlay=None) -> bool:
    """Build every book of the manifest and assemble the site. True on success."""
    from .html import build_html
    from .manifest import scan_labels
    from .pdf import build_pdf, build_book

    try:
        manifest = load_manifest(Path(manifest_path))
    except ManifestError as error:
        print_error(f"Library manifest: {error}")
        return False
    if out:
        manifest["out"] = Path(out).resolve()
    # `out` is emptied: it must not hold the manifest or a book
    for keep in [manifest["file"]] + [entry["path"] for entry in manifest["books"]]:
        if keep == manifest["out"] or keep.is_relative_to(manifest["out"]):
            print_error(f"Library manifest: the output directory {manifest['out']} would delete {keep}")
            return False
    extra = load_overlay(extra_overlay)

    def open_book(entry, overlay):
        return Book(entry["path"], overlay=merge_patch(overlay, extra))

    # Pass 1: every book's label registry, so pass 2 can resolve citations either way
    books = {}
    for entry in manifest["books"]:
        try:
            plain = Book(entry["path"])
        except FileNotFoundError as error:
            print_error(f"book {entry['prefix']}: {error}")
            return False
        books[entry["prefix"]] = plain
    registries = {}
    for entry in manifest["books"]:
        plain = books[entry["prefix"]]
        probe = open_book(entry, {"build-dir": manifest["build-dir"], "output": None})
        registries[entry["prefix"]] = probe.labels_file
        if not entry.get("title"):
            entry["title"] = plain.title
    print_info("Pass 1 scans each book once; a warning there that a later book's registry "
               "is not found is expected (pass 2 has them all)")
    for entry in manifest["books"]:
        print_header(f"Library pass 1: labels of {entry['prefix']} ({entry['path']})")
        book = open_book(entry, book_overlay(manifest, entry, books[entry["prefix"]].config, registries))
        scan_labels(book)

    # Pass 2: the websites, every registry now in place
    ok = True
    built = []
    for entry in manifest["books"]:
        print_header(f"Library pass 2: {entry['prefix']} -> {entry['subdir']}/")
        overlay = book_overlay(manifest, entry, books[entry["prefix"]].config, registries)
        book = open_book(entry, overlay)
        book.build_dir.mkdir(parents=True, exist_ok=True)
        (book.build_dir / "library-overlay.json").write_text(
            json.dumps(merge_patch(overlay, extra), indent=2, ensure_ascii=False), encoding="utf-8")
        book_ok = build_html(book)
        if with_pdf:
            book_ok = build_pdf(book) and book_ok
            book_ok = build_book(book) and book_ok
        if not book_ok:
            print_error(f"book {entry['prefix']} did not build cleanly")
            ok = False
        built.append((entry, book))
        # what the landing page says about the book
        entry["title-plain"] = book.plain_title
        entry["chapter-count"] = sum(1 for c in book.chapters if c.directory.is_dir())
        entry["section-count"] = sum(1 for p in book.pages if p.section > 0)

    assemble(manifest, built, with_pdf)
    if ok:
        print_success(f"Library assembled in {manifest['out']}")
    else:
        print_warning(f"Library assembled in {manifest['out']}, but some books had build errors")
    return ok


def _clear(directory: Path):
    """Empty `directory`, keeping a git clone's .git (and a CNAME the site owner set)."""
    directory.mkdir(parents=True, exist_ok=True)
    for item in directory.iterdir():
        if item.name in (".git", "CNAME"):
            continue
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def copy_book_html(book: Book, destination: Path, with_pdf: bool):
    """The book's HTML output, as `deploy` would publish it (no stale chapters, no scratch
    `_` files), without the PDFs unless asked for, plus its redirect stubs."""
    chapter_slugs = {c.slug for c in book.chapters}
    destination.mkdir(parents=True, exist_ok=True)
    for item in book.html_dir.iterdir():
        if item.is_dir() and is_stale_chapter_dir(item.name, chapter_slugs):
            continue
        if item.name.startswith("_"):
            continue
        if not with_pdf and item.is_dir() and item.name in ("pdf", "book"):
            continue
        if item.is_dir():
            shutil.copytree(item, destination / item.name)
        else:
            shutil.copy2(item, destination / item.name)
    write_redirects(book, destination)


def assemble(manifest: dict, built: list, with_pdf: bool):
    out = manifest["out"]
    print_step(f"Assembling {out}")
    _clear(out)
    for entry, book in built:
        if book.html_dir.is_dir():
            copy_book_html(book, out / entry["subdir"], with_pdf)
    for item in manifest["files"]:
        target = out / item["to"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if item["from"].is_dir():
            shutil.copytree(item["from"], target)
        elif item["from"].is_file():
            shutil.copy2(item["from"], target)
        else:
            print_warning(f"files: {item['from']} not found")
    site_url = manifest["site-url"]
    write_landing(manifest, built, with_pdf)
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site_url}sitemap.xml\n", encoding="utf-8")
    (out / "sitemap.xml").write_text(sitemap_index(manifest, out), encoding="utf-8")
    (out / "sitemap-landing.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{escape(site_url)}index.html</loc></url>\n</urlset>\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")   # theorems/_root/... must be served
    print_info(f"{len(built)} book(s), landing page, 404.html, robots.txt, sitemap.xml")


def sitemap_index(manifest: dict, out: Path) -> str:
    site_url = manifest["site-url"]
    locations = [f"{site_url}sitemap-landing.xml"]
    # a book canonical elsewhere is indexed there, not here (and has no sitemap.xml)
    locations += [f"{site_url}{entry['subdir']}/sitemap.xml" for entry in manifest["books"]
                  if not entry.get("canonical") and (out / entry["subdir"] / "sitemap.xml").exists()]
    entries = "\n".join(f"  <sitemap><loc>{escape(loc)}</loc></sitemap>" for loc in locations)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{entries}\n</sitemapindex>\n")


def write_landing(manifest: dict, built: list, with_pdf: bool):
    """index.html, 404.html and favicon.svg at the library root (build/landing.py)."""
    from .macros import mathjax_macros
    from .math import mathjax_dir
    out = manifest["out"]
    macros = {}
    for entry, book in built:     # every book's macros; the first book's win a clash
        for name, body in mathjax_macros(book.macros_file).items():
            macros.setdefault(name, body)
        if not entry.get("pdf-url"):
            pdf = entry.get("pdf") or (f"{entry['subdir']}/book/book.pdf"
                                       if (out / entry["subdir"] / "book" / "book.pdf").is_file() else None)
            entry["pdf-url"] = pdf
    manifest["macros"] = macros
    # The books' fonts and math stylesheet, from the first book that has them
    font_base = next((f"{e['subdir']}/" for e, _ in built if (out / e["subdir"] / "fonts").is_dir()), None)
    math_css = next((f"{e['subdir']}/mathjax.css" for e, _ in built if (out / e["subdir"] / "mathjax.css").is_file()),
                    None)
    mathjax = built and mathjax_dir(built[0][1])
    page = None
    if math_css and mathjax and (mathjax / "startup.js").exists():
        page = render_landing_math(landing_page(manifest, math=True, font_base=font_base, math_css=math_css),
                                   mathjax, macros)
        if page is None:
            print_warning("Landing page: math rendering failed; titles shown as plain text")
    if page is None:
        page = landing_page(manifest, font_base=font_base)
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "404.html").write_text(not_found_page(manifest, font_base=font_base), encoding="utf-8")
    favicon = ENGINE_ROOT / "templates" / "html" / "favicon.svg"
    if built:
        favicon = built[0][1].engine_file("templates/html/favicon.svg")
    shutil.copy2(favicon, out / "favicon.svg")
