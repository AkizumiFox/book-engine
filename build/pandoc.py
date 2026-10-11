"""
Build System Pandoc Module
==========================
Builds Pandoc commands for a page and runs them.
"""

import hashlib
import json
import re
import subprocess
import threading
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode

from .book import Book, Page, ENGINE_ROOT
from .external import external_file
from .utils import print_error, print_warning, run_with_crash_retry

MARKDOWN_FORMAT = "markdown+tex_math_single_backslash"


# =============================================================================
# Metadata
# =============================================================================

def page_metadata(book: Book, page: Page, output_format: str, extra: Optional[dict] = None) -> dict:
    """Metadata passed to the filters and templates for one page."""
    metadata = {
        "chapter-num": page.chapter_number,
        "section-num": page.section,
        "is-preface": page.is_preface,
        "environment_settings": book.environment_settings,
        "section-number": page.number,
        "asset-prefix": page.asset_prefix if output_format == "html" else "./",
        "title": book.title,
        "title-text": page.title,
        "pagetitle": f"{page.number} {page.title}" if page.number else page.title,
        "tikz-cache-dir": str(book.tikz_cache_dir),
        "page-shard": page.shard,
        "page-path": page.html_path,
        "book-root": str(book.root),
        "engine-root": str(ENGINE_ROOT),
        "source-path": str(page.source.relative_to(book.root)),
    }
    if book.site_url:
        metadata["page-url"] = f"{book.site_url}{page.html_path}"
    if book.labels_file.exists():
        metadata["crossref-labels-file"] = str(book.labels_file)
    if book.config.get("external-books") and external_file(book).exists():
        metadata["external-books-file"] = str(external_file(book))

    if output_format == "html":
        prefix = page.asset_prefix
        if page.chapter:
            metadata["breadcrumb-chapter-title"] = page.chapter.title
            metadata["breadcrumb-chapter-url"] = f"{prefix}{page.chapter.slug}/index.html"
        else:
            metadata["breadcrumb-chapter-title"] = page.title
            metadata["breadcrumb-chapter-url"] = f"{prefix}index.html"
        metadata["breadcrumb-page-title"] = page.title
        metadata["breadcrumb-page-url"] = f"{prefix}{page.html_path}"
        metadata["pdf-url"] = f"{prefix}pdf/{Path(page.html_path).with_suffix('.pdf').as_posix()}"
        metadata["book-pdf-url"] = f"{prefix}book/book.pdf"
        # The licence the book's text carries, shown in the page footer. A book whose
        # config names none simply renders no notice.
        licence = book.config.get("license") or {}
        if licence.get("name"):
            metadata["license-name"] = licence["name"]
            if licence.get("url"):
                metadata["license-url"] = licence["url"]
        source = metadata["source-path"]
        if book.config.get("repo-url"):
            repo = book.config["repo-url"].rstrip("/")
            metadata["repo-url"] = repo
            # The page a reader should look at to check or fix the text: its own markdown
            metadata["source-url"] = f"{repo}/blob/{book.config.get('source-branch', 'main')}/{source}"
        if book.config.get("issues-url"):
            # A new issue prefilled with the section, its address and the file to edit
            label = f"{page.number} {page.title}" if page.number else page.title
            address = metadata.get("page-url") or page.html_path
            where = f"Page: {address}\nSource: {metadata.get('source-url') or source}"
            query = urlencode({
                "title": f"Typo or mistake in {label}",
                "body": f"{where}\n\nWhat is wrong (quote the sentence or formula):\n\n\nWhat it should say:\n",
            }, quote_via=quote)
            metadata["report-url"] = f"{book.config['issues-url']}?{query}"
        for direction in ("prev", "next"):
            neighbour = page.neighbours.get(direction)
            if neighbour:
                metadata[f"{direction}-page-url"] = f"{prefix}{neighbour.html_path}"
                metadata[f"{direction}-page-title"] = neighbour.title
                # For the aria-label attribute: rendered math markup would break the HTML there
                metadata[f"{direction}-page-label"] = plain_label(neighbour.title)
                metadata[f"{direction}-page-number"] = neighbour.number

    metadata.update(extra or {})
    return metadata


def plain_label(title: str) -> str:
    """A title as plain text for attributes: TeX math reduced to readable symbols."""
    from .extras import plain_title  # local import: extras imports this module
    return plain_title(title)


def write_metadata_file(book: Book, page: Page, output_format: str, metadata: dict) -> Path:
    key = hashlib.md5(f"{page.source}:{output_format}".encode()).hexdigest()
    meta_file = book.build_dir / "tmp" / "meta" / f"{key}.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    # Top-level numbers as strings, the form the filters and LaTeX template expect
    metadata = {k: str(v) if isinstance(v, int) and not isinstance(v, bool) else v for k, v in metadata.items()}
    meta_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return meta_file


# =============================================================================
# Environment declarations for LaTeX
# =============================================================================
# The environments come from the book's config (environment_settings) and the
# Lua filter turns them into \begin{theorem} ... in the LaTeX it writes. The
# same config has to reach the preamble, or the environments would have no
# definition and no colour. latex/theorem-envs.sty holds the style -- the
# book's framed theorem look -- and this writes the one-line declaration per
# environment that fills it in.

# Display names for the small environments, the same overrides
# filters/theorems.lua uses so the heads it writes and the heads the fallback
# definitions write read alike.
SMALL_ENV_NAMES = {"proofofclaim": "Proof of Claim", "check": "Quick check"}

_ENVIRONMENTS_LOCK = threading.Lock()


def _tex_name(text: str) -> str:
    """A LaTeX-safe name: colours and counters may only be letters."""
    return re.sub(r"[^a-z]", "", text.lower()) or "x"


def _env_key(name: str) -> str:
    """The environment name, as filters/theorems.lua derives it from the config."""
    return re.sub(r"\s+", "-", name.lower())


def environments_tex(book: Book) -> Path:
    r"""Write the \book...env declarations for the config's environments.

    Included right after latex/preamble.tex, where latex/theorem-envs.sty has
    just defined the commands it calls.
    """
    settings = book.environment_settings
    lines = [
        r"% Generated from the book's config (environment_settings) by build/pandoc.py.",
        r"% Do not edit: the style lives in latex/theorem-envs.sty, the data in the config.",
    ]

    big = settings.get("big_envs", []) or []
    groups = []
    for env in big:
        group = str(env.get("counter_group") or "").strip()
        if env.get("numbered", True) and group and group not in groups:
            groups.append(group)
    for group in groups:
        lines.append(rf"\bookenvcounter{{{_tex_name(group)}}}")

    def colour(name: str, value) -> str:
        colour_name = "env" + _tex_name(name)
        if value:
            rgb = str(value).lstrip("#").upper()
            lines.append(rf"\definecolor{{{colour_name}}}{{HTML}}{{{rgb}}}")
        return colour_name

    for env in big:
        name = str(env.get("name", ""))
        key, tint = _env_key(name), colour(name, env.get("color"))
        group = str(env.get("counter_group") or "").strip()
        if not env.get("numbered", True):
            lines.append(rf"\bookbigenvplain{{{key}}}{{{name}}}{{{tint}}}")
        elif group:
            lines.append(rf"\bookbigenv{{{key}}}{{{name}}}{{{_tex_name(group)}}}{{{tint}}}")
        else:
            lines.append(rf"\bookbigenvown{{{key}}}{{{name}}}{{{tint}}}")

    for env in settings.get("small_envs", []) or []:
        if isinstance(env, str):
            env = {"name": env}
        name = str(env.get("name", ""))
        key = _env_key(name)
        tint = colour(name, env.get("color"))
        head = SMALL_ENV_NAMES.get(key, name[:1].upper() + name[1:])
        lines.append(rf"\booksmallenv{{{key}}}{{{head}}}{{{tint}}}")

    path = book.build_dir / "tmp" / "environments.tex"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    # Pages are built in parallel and every one of them asks for this file.
    with _ENVIRONMENTS_LOCK:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
    return path


# =============================================================================
# Pandoc Command Building
# =============================================================================

def build_pandoc_command(book: Book, page: Page, output_file: Path, output_format: str, metadata: dict) -> list[str]:
    """Pandoc command converting one page to HTML or LaTeX (output_format "html" or "pdf")."""
    filters = book.filters_dir
    cmd = [
        "pandoc", str(page.source),
        "-o", str(output_file),
        "--standalone",
        "-f", MARKDOWN_FORMAT,
        "--lua-filter", str(filters / "format-visibility.lua"),
        "--lua-filter", str(filters / "components.lua"),
        "--lua-filter", str(filters / "tikz.lua"),
        "--lua-filter", str(filters / "enumerate.lua"),
        "--lua-filter", str(filters / "theorems.lua"),
        "--metadata-file", str(write_metadata_file(book, page, output_format, metadata)),
    ]

    if output_format == "html":
        from .manifest import render_navigation  # local import: manifest imports this module
        cmd += [
            "--template", str(book.html_template),
            "--lua-filter", str(filters / "numbering.lua"),
            "--mathjax",
            # A variable, not metadata: pandoc parses metadata as markdown and would mangle
            # the markup (verified — newlines come back as <br />). -V is inserted verbatim.
            "-V", f"navigation={render_navigation(book, page)}",
        ]
    elif output_format == "pdf":
        # # -> chapter (0.4), ## -> section (0.4.1), ### -> subsection (0.4.1.1)
        cmd += [
            "--template", str(book.latex_template),
            "--top-level-division", "chapter",
            "--resource-path", ":".join([str(page.source.parent), str(book.src_dir)]),
            "--include-in-header", str(book.engine_file("latex/preamble.tex")),
            # The config's environments, declared for the preamble that just
            # defined how they are framed.
            "--include-in-header", str(environments_tex(book)),
        ]
        if book.macros_file.exists():
            cmd += ["--include-in-header", str(book.macros_file)]
    return cmd


# =============================================================================
# Pandoc Execution
# =============================================================================

def run_pandoc(cmd: list[str], *, cwd: Optional[Path] = None, env: Optional[dict] = None) -> bool:
    """Run a pandoc command and return success. Logs errors and warnings."""
    try:
        result = run_with_crash_retry(cmd, cwd=cwd, env=env)
    except subprocess.CalledProcessError as e:
        print_error(f"Pandoc failed for {cmd[1]}")
        if e.stdout and e.stdout.strip():
            print(f"  stdout:\n{e.stdout.strip()}")
        if e.stderr and e.stderr.strip():
            print_error(f"  stderr:\n{e.stderr.strip()}")
        return False
    if result.stderr and result.stderr.strip():
        print_warning(f"Pandoc stderr for {Path(cmd[1]).name}:")
        for line in result.stderr.strip().splitlines():
            print(f"  {line}")
    return True
