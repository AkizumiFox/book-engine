"""
Build System Book Module
========================
A Book is one textbook: a root directory with a config file, Markdown sources and a
macro file. The engine (filters, templates, LaTeX styles) lives next to this package
and is shared by every book; a book may override any engine file by providing a file
at the same relative path.

Config lookup: <root>/book.json, then <root>/config/config.json.
All paths in the config are relative to the book root.

A config overlay (`Book(root, overlay=...)`, `./build.py --config-overlay FILE`) is a
JSON object merged over the config for one build without editing it -- a library build
sets `site-url` and `external-books` this way. The merge is a JSON Merge Patch (RFC 7396):
objects merge key by key, `null` removes a key, anything else replaces the value.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from .macros import plain_text

ENGINE_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_CANDIDATES = ("book.json", "config/config.json")


@dataclass
class Chapter:
    number: int
    slug: str          # directory name, e.g. "ch01-vector-spaces"
    directory: Path
    title: str
    part: str = ""     # set on the first chapter of a part: the part's heading


@dataclass
class Page:
    source: Path
    chapter: Chapter | None   # None for the preface
    section: int              # 0 for preface and chapter index pages
    title: str
    html_path: str            # relative to the HTML output root, e.g. "ch01-vector-spaces/03-span.html"
    neighbours: dict = field(default_factory=dict)  # "prev"/"next" -> Page
    back: bool = False        # a back-matter page (config "back-matter"), e.g. a glossary

    @property
    def is_preface(self) -> bool:
        return self.chapter is None and not self.back

    @property
    def unnumbered(self) -> bool:
        """The preface or a back-matter page: outside every chapter, nothing numbered."""
        return self.chapter is None

    @property
    def chapter_number(self) -> int:
        return self.chapter.number if self.chapter else 0

    @property
    def number(self) -> str:
        """Section number shown in titles and navigation ("1.3"), empty for index pages."""
        if self.section == 0:
            return ""
        return f"{self.chapter_number}.{self.section}"

    @property
    def depth(self) -> int:
        return self.html_path.count("/")

    @property
    def asset_prefix(self) -> str:
        return "../" * self.depth if self.depth else "./"

    @property
    def shard(self) -> str:
        """Name of the tooltip data shard for labels defined on this page."""
        return self.chapter.slug if self.chapter else "_root"


def extract_title(path: Path) -> str:
    """First level-1 Markdown heading (after optional YAML front matter), without attributes."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    in_front_matter = bool(lines) and lines[0].strip() == "---"
    for index, line in enumerate(lines):
        stripped = line.strip()
        if in_front_matter:
            if index > 0 and stripped in ("---", "..."):
                in_front_matter = False
            continue
        if stripped.startswith("# "):
            return re.sub(r"\s*\{[^}]*\}\s*$", "", stripped[2:]).strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def merge_patch(base, patch):
    """`base` with `patch` merged over it (JSON Merge Patch, RFC 7396); neither is changed.

    Objects merge recursively, a `null` in the patch removes the key, any other value
    (lists included) replaces it.
    """
    if not isinstance(patch, dict):
        return patch
    merged = dict(base) if isinstance(base, dict) else {}
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = merge_patch(merged.get(key), value)
    return merged


def load_overlay(value) -> dict:
    """An overlay given as a dict, or a path to a JSON file holding an object."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    path = Path(value)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise FileNotFoundError(f"Config overlay {path}: {error.strerror or error}") from error
    except ValueError as error:
        raise ValueError(f"Config overlay {path} is not valid JSON ({error})") from error
    if not isinstance(data, dict):
        raise ValueError(f"Config overlay {path} must hold a JSON object")
    return data


class Book:
    def __init__(self, root: Path | str, overlay: dict | str | Path | None = None):
        self.root = Path(root).resolve()
        for candidate in CONFIG_CANDIDATES:
            if (self.root / candidate).exists():
                self.config_file = self.root / candidate
                break
        else:
            raise FileNotFoundError(f"No book config ({' or '.join(CONFIG_CANDIDATES)}) in {self.root}")
        self.config = json.loads(self.config_file.read_text(encoding="utf-8"))
        # The overlay as given (a path stays a path, so a fresh Book can re-read it)
        self.overlay_source = overlay
        self.overlay = load_overlay(overlay)
        if self.overlay:
            self.config = merge_patch(self.config, self.overlay)

    # -- Paths ---------------------------------------------------------------

    def path(self, relative: str) -> Path:
        return self.root / relative

    def engine_file(self, relative: str) -> Path:
        """A file the book may override: the book's copy if present, else the engine's."""
        own = self.root / relative
        return own if own.exists() else ENGINE_ROOT / relative

    @property
    def title(self) -> str:
        return self.config.get("title", "Untitled")

    @cached_property
    def _plain_macros(self) -> dict:
        from .macros import mathjax_macros
        return mathjax_macros(self.macros_file)

    def plain(self, text: str) -> str:
        """TeX in a title as plain text (for <title>, og: tags, labels), read through the
        book's own macro file: "From \\(\\nN\\)" -> "From ℕ"."""
        return plain_text(text, self._plain_macros)

    @property
    def plain_title(self) -> str:
        return self.plain(self.title)

    @property
    def author(self) -> str:
        return self.config.get("author", "")

    @property
    def src_dir(self) -> Path:
        return self.path(self.config.get("src", "src"))

    @property
    def build_dir(self) -> Path:
        """Where everything a build writes goes (config `build-dir`, default `_build`). The
        library assembler builds each book in `_build/library`, so its overlaid build never
        touches the author's own `_build/html`."""
        return self.path(self.config.get("build-dir") or "_build")

    @property
    def cache_dir(self) -> Path:
        return self.build_dir / "cache"

    @property
    def html_dir(self) -> Path:
        configured = self.config.get("output", {}).get("html")
        return self.path(configured) if configured else self.build_dir / "html"

    @property
    def pdf_dir(self) -> Path:
        configured = self.config.get("output", {}).get("pdf")
        return self.path(configured) if configured else self.build_dir / "pdf"

    @property
    def book_pdf(self) -> Path:
        configured = self.config.get("output", {}).get("book")
        return self.path(configured) if configured else self.build_dir / "pdf" / "book.pdf"

    @property
    def labels_file(self) -> Path:
        return self.build_dir / "crossref_labels.json"

    @property
    def scan_file(self) -> Path:
        return self.build_dir / "scan.json"

    @property
    def tikz_cache_dir(self) -> Path:
        # Shared by every build directory: a figure's file name is the hash of its source,
        # so a library build reuses the figures the book's own build compiled
        return self.root / "_build" / "cache" / "tikz"

    @property
    def macros_file(self) -> Path:
        return self.path(self.config.get("macros", "latex/macros.tex"))

    @property
    def fitch_sty(self) -> "Path | None":
        """The book's latex/fitch-book.sty (or one next to its macros file), if it ships one."""
        for path in (self.path("latex/fitch-book.sty"), self.macros_file.parent / "fitch-book.sty"):
            if path.is_file():
                return path
        return None

    @property
    def fitch_purposes_inferred(self) -> bool:
        """Config "fitch-purposes": "infer": filters/fitch.lua prints each assumption's purpose
        ("asm, for ->I"), read off the rule that closes its box, in HTML and in the PDF."""
        return self.config.get("fitch-purposes") == "infer" and self.fitch_sty is not None

    @property
    def fitch_html(self) -> bool:
        """Whether the website draws `nd` derivations as HTML (filters/fitch.lua) rather than
        as SVGs: config "fitch-html", by default on when the book ships fitch-book.sty."""
        setting = self.config.get("fitch-html")
        if setting is None:
            return self.fitch_sty is not None
        return bool(setting)

    @property
    def filters_dir(self) -> Path:
        return ENGINE_ROOT / "filters"

    @property
    def html_template(self) -> Path:
        return self.engine_file(self.config.get("templates", {}).get("html", "templates/html/template.html"))

    @property
    def latex_template(self) -> Path:
        return self.engine_file(self.config.get("templates", {}).get("latex", "templates/latex/template.tex"))

    @property
    def html_styles(self) -> Path:
        return self.engine_file(self.config.get("styles", {}).get("html", "templates/html/styles.css"))

    @property
    def tex_inputs(self) -> str:
        """TEXINPUTS so LaTeX finds the book's files first, then the engine's styles.

        When the engine lives inside the book (a submodule in engine/), `book//` would
        also reach the engine's copies of the styles, in no defined order, and a book's
        override of one (latex/preamble.tex, say) could lose to the engine's. So the book
        root is searched flat, then each of its directories except the engine's, then the
        engine.
        """
        if self.root == ENGINE_ROOT:
            entries = [f"{self.root}//"]
        elif ENGINE_ROOT.is_relative_to(self.root):
            engine_top = self.root / ENGINE_ROOT.relative_to(self.root).parts[0]
            entries = [str(self.root)]
            entries += [f"{d}//" for d in sorted(self.root.iterdir())
                        if d.is_dir() and d != engine_top and not d.name.startswith(".")]
            entries.append(f"{ENGINE_ROOT}//")
        else:
            entries = [f"{self.root}//", f"{ENGINE_ROOT}//"]
        return ".:" + ":".join(entries) + ":"

    @property
    def site_url(self) -> str:
        """
        The address the website is published at, ending in "/", or "" if unknown.

        `site-url` in the config, for a book published under a sub-path of a shared
        origin (a library: https://books.example.com/analysis/); otherwise the root of
        `deploy-domain`. Canonical links, the sitemap and the PDF's links to runnable
        cells are built on it. Everything else in the site is relative, so the same
        output works at any path.
        """
        url = (self.config.get("site-url") or "").strip()
        if not url:
            domain = (self.config.get("deploy-domain") or "").strip()
            url = f"https://{domain}/" if domain else ""
        return url if not url or url.endswith("/") else url + "/"

    @property
    def canonical_url(self) -> str:
        """
        The address the pages' canonical and og:url links are built on, ending in "/".

        `canonical-url` in the config, for a copy of a book whose canonical home is
        elsewhere (a library carrying a book that also has its own site); otherwise
        site_url. Only those links change: the site, its 404 page and its links stay at
        site_url.
        """
        url = (self.config.get("canonical-url") or "").strip()
        if not url:
            return self.site_url
        return url if url.endswith("/") else url + "/"

    @property
    def canonical_elsewhere(self) -> bool:
        """True when the pages are canonical at another address than site_url: the
        site then publishes no sitemap of its own (see generate_site_files)."""
        return bool(self.canonical_url) and self.canonical_url != self.site_url

    @property
    def site_path(self) -> str:
        """The path part of site_url ("/" for a book at the root of its domain)."""
        match = re.match(r"^[a-z]+://[^/]+(/.*)?$", self.site_url)
        return (match.group(1) or "/") if match else "/"

    @property
    def environment_settings(self) -> dict:
        return self.config.get("environment_settings", {})

    # -- Structure -----------------------------------------------------------

    @cached_property
    def chapters(self) -> list[Chapter]:
        chapters = []
        for position, entry in enumerate(self.config.get("chapters", [])):
            if isinstance(entry, str):
                entry = {"dir": entry}
            directory = self.path(entry["dir"])
            match = re.match(r"ch(\d+)", directory.name)
            number = int(match.group(1)) if match else position
            title = entry.get("title")
            if not title:
                index = directory / "index.md"
                title = extract_title(index) if index.exists() else re.sub(
                    r"^ch\d+-", "", directory.name).replace("-", " ").title()
            chapters.append(Chapter(number=number, slug=directory.name, directory=directory, title=title,
                                    part=entry.get("part", "")))
        return chapters

    @cached_property
    def pages(self) -> list[Page]:
        """All pages in reading order: preface, then each chapter's index and sections, then
        the back matter (config "back-matter": a list of Markdown files, e.g.
        ["src/glossary.md"], each a page <stem>.html at the site root, unnumbered like the
        preface)."""
        pages = []
        preface = self.path(self.config.get("preface", str(self.src_dir.relative_to(self.root) / "index.md")))
        if preface.exists():
            pages.append(Page(source=preface, chapter=None, section=0,
                              title=extract_title(preface), html_path="index.html"))
        for chapter in self.chapters:
            if not chapter.directory.is_dir():
                continue
            sources = sorted(chapter.directory.glob("*.md"))
            index = [s for s in sources if s.name == "index.md"]
            sections = [s for s in sources if s.name != "index.md"]
            for source in index:
                pages.append(Page(source=source, chapter=chapter, section=0, title=extract_title(source),
                                  html_path=f"{chapter.slug}/index.html"))
            for number, source in enumerate(sections, start=1):
                pages.append(Page(source=source, chapter=chapter, section=number, title=extract_title(source),
                                  html_path=f"{chapter.slug}/{source.stem}.html"))
        for entry in self.config.get("back-matter", []) or []:
            source = self.path(entry)
            if source.is_file():
                pages.append(Page(source=source, chapter=None, section=0, title=extract_title(source),
                                  html_path=f"{source.stem}.html", back=True))
        for previous, following in zip(pages, pages[1:]):
            previous.neighbours["next"] = following
            following.neighbours["prev"] = previous
        return pages

    def page_for(self, source: Path) -> Page | None:
        source = Path(source).resolve()
        return next((p for p in self.pages if p.source.resolve() == source), None)

    def missing_chapter_dirs(self) -> list[str]:
        return [str(c.directory.relative_to(self.root)) for c in self.chapters if not c.directory.is_dir()]

    # -- Fingerprints ----------------------------------------------------------

    def engine_fingerprint(self) -> str:
        """Hash of every engine and book-level input that affects all pages."""
        digest = hashlib.sha1()
        files = sorted(self.filters_dir.glob("*.lua"))
        files += [self.html_template, self.latex_template, self.html_styles, self.config_file, self.macros_file]
        # rglob: any subdirectory of latex/ counts too
        files += sorted((ENGINE_ROOT / "latex").rglob("*"))
        if self.root != ENGINE_ROOT:   # the book's own LaTeX overrides (latex/preamble.tex, ...)
            files += sorted((self.root / "latex").rglob("*"))
        for path in files:
            if path.is_file():
                digest.update(str(path).encode())
                digest.update(path.read_bytes())
        if self.overlay:   # an overlay changes the config as much as an edit would
            digest.update(json.dumps(self.overlay, sort_keys=True).encode())
        return digest.hexdigest()
