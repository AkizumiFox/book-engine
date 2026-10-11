"""
Build System Book Module
========================
A Book is one textbook: a root directory with a config file, Markdown sources and a
macro file. The engine (filters, templates, LaTeX styles) lives next to this package
and is shared by every book; a book may override any engine file by providing a file
at the same relative path.

Config lookup: <root>/book.json, then <root>/config/config.json.
All paths in the config are relative to the book root.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

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

    @property
    def is_preface(self) -> bool:
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


class Book:
    def __init__(self, root: Path | str = ENGINE_ROOT):
        self.root = Path(root).resolve()
        for candidate in CONFIG_CANDIDATES:
            if (self.root / candidate).exists():
                self.config_file = self.root / candidate
                break
        else:
            raise FileNotFoundError(f"No book config ({' or '.join(CONFIG_CANDIDATES)}) in {self.root}")
        self.config = json.loads(self.config_file.read_text(encoding="utf-8"))

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

    @property
    def author(self) -> str:
        return self.config.get("author", "")

    @property
    def src_dir(self) -> Path:
        return self.path(self.config.get("src", "src"))

    @property
    def build_dir(self) -> Path:
        return self.root / "_build"

    @property
    def cache_dir(self) -> Path:
        return self.build_dir / "cache"

    @property
    def html_dir(self) -> Path:
        return self.path(self.config.get("output", {}).get("html", "_build/html"))

    @property
    def pdf_dir(self) -> Path:
        return self.path(self.config.get("output", {}).get("pdf", "_build/pdf"))

    @property
    def book_pdf(self) -> Path:
        return self.path(self.config.get("output", {}).get("book", "_build/pdf/book.pdf"))

    @property
    def labels_file(self) -> Path:
        return self.build_dir / "crossref_labels.json"

    @property
    def scan_file(self) -> Path:
        return self.build_dir / "scan.json"

    @property
    def tikz_cache_dir(self) -> Path:
        return self.cache_dir / "tikz"

    @property
    def macros_file(self) -> Path:
        return self.path(self.config.get("macros", "latex/macros.tex"))

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
        """TEXINPUTS so LaTeX finds the book's files first, then the engine's styles."""
        roots = [self.root] if self.root == ENGINE_ROOT else [self.root, ENGINE_ROOT]
        return ".:" + ":".join(f"{r}//" for r in roots) + ":"

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
        """All pages in reading order: preface, then each chapter's index and sections."""
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
        for path in files:
            if path.is_file():
                digest.update(str(path).encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()
