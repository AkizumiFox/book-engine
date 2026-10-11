"""
Build System Check Module
=========================
Validates the book: tool availability (doctor), cross-references, duplicate labels,
and that the PDF numbering matches the web numbering.
"""

import importlib.util
import json
import re
import shutil
import subprocess
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

from .book import Book
from .manifest import scan_labels, load_scan
from .utils import print_step, print_success, print_warning, print_error, print_info

MIN_PANDOC = (3, 1)

ENGINE_ROOT = Path(__file__).resolve().parent.parent


def _tool(name):
    """A checker in `tools/`, imported by path (`tools/` is not a package).

    The same trick `build/extras.py` uses for `reading_path`: the checkers are
    standalone scripts the author runs by hand, and the build reuses them rather
    than keeping a second copy of the rule. Each one offers the same two
    functions, `find_violations(labels)` and `report(violations)`.
    """
    spec = importlib.util.spec_from_file_location(
        name, ENGINE_ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# (command, version flag, needed for)
TOOLS = [
    ("pandoc", "--version", "all builds"),
    ("pdflatex", "--version", "PDF builds and TikZ figures"),
    ("pdftocairo", "-v", "TikZ figures on the web"),
    ("node", "--version", "rendering math at build time (optional: without it math renders in the browser)"),
    ("aspell", "--version", "the spelling check (optional)"),
]


# =============================================================================
# Doctor
# =============================================================================

def doctor() -> bool:
    """Check that the external tools the build needs are installed."""
    print_step("Checking tools...")
    ok = True
    for tool, flag, purpose in TOOLS:
        path = shutil.which(tool)
        if not path:
            print_error(f"{tool}: not found (needed for {purpose})")
            ok = False
            continue
        result = subprocess.run([tool, flag], capture_output=True, text=True)
        first_line = (result.stdout or result.stderr).strip().splitlines()[0:1]
        version = first_line[0] if first_line else "unknown version"
        if tool == "pandoc":
            match = re.search(r"(\d+)\.(\d+)", version)
            if not match or tuple(map(int, match.groups())) < MIN_PANDOC:
                print_error(f"pandoc: {version} (need {'.'.join(map(str, MIN_PANDOC))} or newer)")
                ok = False
                continue
        print_success(f"{tool}: {version}")
    return ok


# =============================================================================
# Check
# =============================================================================

def read_aux_labels(aux_file: Path) -> dict[str, str]:
    """Map label -> printed number from a LaTeX .aux file."""
    text = aux_file.read_text(encoding="latin-1")
    return {m.group(1): m.group(2) for m in re.finditer(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", text)}


def _compare_numbers(book: Book, labels: dict, aux_file: Path, only: set[str] | None = None) -> list[str]:
    problems = []
    aux = read_aux_labels(aux_file)
    for label_id, info in sorted(labels.items()):
        if only is not None and label_id not in only:
            continue
        web = info.get("number", "")
        if not web:
            continue  # unnumbered environments are referenced by name, not number
        pdf = aux.get(label_id)
        if pdf is None:
            problems.append(f"{label_id}: missing from {aux_file.relative_to(book.root)}")
        elif pdf != web:
            problems.append(f"{label_id}: web {web}, PDF {pdf} ({aux_file.relative_to(book.root)})")
    return problems


class _LinkCollector(HTMLParser):
    """Collects element ids and the hrefs of a.xref links in one page."""

    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.xrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "xref" in (attrs.get("class") or "").split() and attrs.get("href"):
            self.xrefs.append(attrs["href"])


def check_xref_links(html_dir: Path) -> list[str]:
    """Verify every a.xref link in the built HTML resolves to a page containing the anchor."""
    pages: dict[Path, _LinkCollector] = {}
    for page in sorted(html_dir.rglob("*.html")):
        collector = _LinkCollector()
        collector.feed(page.read_text(encoding="utf-8"))
        pages[page.resolve()] = collector

    problems = []
    for page, collector in pages.items():
        where = page.relative_to(html_dir.resolve())
        for href in collector.xrefs:
            path, _, anchor = href.partition("#")
            target = (page.parent / path).resolve() if path else page
            if target not in pages:
                problems.append(f"broken link {href} in {where}: page not found")
            elif anchor and anchor not in pages[target].ids:
                problems.append(f"broken link {href} in {where}: no #{anchor}")
    return problems


def spelling_problems(book: Book, scan: dict) -> dict[str, list[str]]:
    """
    Words aspell does not know, per source file (prose only: formulas, code and raw LaTeX
    are left out by the scan). Words listed in <book>/spelling.txt (one per line, # for
    comments) are accepted. Returns {} when aspell is not installed.
    """
    if not shutil.which("aspell"):
        return {}
    allowed = set()
    allow_file = book.root / "spelling.txt"
    if allow_file.exists():
        for line in allow_file.read_text(encoding="utf-8").splitlines():
            word = line.split("#", 1)[0].strip()
            if word:
                allowed.add(word.lower())

    problems = {}
    for entry in scan["files"].values():
        prose = entry.get("prose", "")
        if not prose:
            continue
        result = subprocess.run(["aspell", "list", "--lang=en_US", "--ignore-case", "--mode=none"],
                                input=prose, capture_output=True, text=True)
        base = lambda w: w.lower().removesuffix("’s").removesuffix("'s")  # possessives
        unknown = sorted({w for w in result.stdout.split() if base(w) not in allowed and len(w) > 2
                          and not any(c.isdigit() for c in w)})
        if unknown:
            problems[entry["source"]] = unknown
    return problems


def _newest_source_mtime(book: Book) -> float:
    return max((p.source.stat().st_mtime for p in book.pages), default=0)


def check(book: Book, quiet: bool = False) -> bool:
    """Validate labels and references; compare PDF numbering if PDFs have been built."""
    scan_labels(book)
    scan, labels = load_scan(book)

    errors = []
    warnings = []

    # Chapters listed in the config must exist
    for chapter_dir in book.missing_chapter_dirs():
        errors.append(f"chapter directory not found: {chapter_dir}")

    # Duplicate labels
    defined_in = defaultdict(list)
    for entry in scan["files"].values():
        for label_id in entry["labels"]:
            defined_in[label_id].append(entry["source"])
    for label_id, sources in sorted(defined_in.items()):
        if len(sources) > 1:
            errors.append(f"duplicate label {label_id}: {', '.join(sources)}")

    # Unresolved references (only ids shaped like labels, e.g. thm-foo)
    for entry in sorted(scan["files"].values(), key=lambda e: e["source"]):
        for ref in sorted(set(entry["refs"])):
            if ref not in labels and re.match(r"^[A-Za-z]+-", ref):
                errors.append(f"unresolved reference @{ref} in {entry['source']}")

    # Component problems found by filters/components.lua (bad plot expressions, widgets
    # without print content, ...)
    for entry in scan["files"].values():
        errors.extend(entry.get("errors", []))

    # Cross-reference links in the built site must point at an existing page and anchor
    if book.html_dir.exists():
        errors.extend(check_xref_links(book.html_dir))

    # A result marked `.optional` prints a promise -- nothing later depends on it -- and
    # the reading paths believe it, so no proof, claim or written solution may cite one.
    optional_checker = _tool("check_optional")
    errors.extend(optional_checker.report(optional_checker.find_violations(labels)).splitlines())

    # Nor may a proof, a proof idea or a claim cite a result the book proves later: the
    # argument would not be complete where it stands. Forward pointers from an example,
    # an exercise, a solution, a remark, a warning or a statement are signposts and are
    # left alone -- `tools/check_forward_deps.py` lists them with `--signposts`.
    forward_checker = _tool("check_forward_deps")
    errors.extend(forward_checker.report(forward_checker.find_violations(labels)).splitlines())

    # Web vs PDF numbering
    book_aux = book.build_dir / "tmp" / "latex-book" / "book.aux"
    newest_source = _newest_source_mtime(book)
    if book_aux.exists():
        if book_aux.stat().st_mtime < newest_source:
            warnings.append("book PDF is older than the sources; run `./build.py book` for an accurate numbering check")
        errors.extend(_compare_numbers(book, labels, book_aux))
    elif not quiet:
        print_info("No book build found; skipping book numbering check (run `./build.py book`)")

    # References LaTeX could not resolve print as "??" in a PDF
    for log in sorted((book.build_dir / "tmp").glob("**/*.log")):
        for match in re.finditer(r"Reference `([^']+)' on page \d+ undefined", log.read_text(encoding="latin-1")):
            errors.append(f"undefined reference {match.group(1)} in {log.relative_to(book.root).with_suffix('.pdf')}")

    section_aux_dir = book.build_dir / "tmp" / "pdf-single"
    for aux_file in sorted(section_aux_dir.rglob("*.aux")) if section_aux_dir.exists() else []:
        entry = scan["files"].get(f"{aux_file.parent.name}/{aux_file.stem}.html")
        if entry:
            errors.extend(_compare_numbers(book, labels, aux_file, only=set(entry["labels"])))

    # Named results mentioned without a reference: a reference gives readers a link and a
    # preview, and makes the dependency graph exact
    source_of = {path: entry["source"] for path, entry in scan["files"].items()}
    for label, info in sorted(labels.items()):
        for mentioned in info.get("mentions", []):
            title = labels[mentioned].get("title", mentioned)
            warnings.append(f"{source_of.get(info.get('file'), info.get('file'))}: {label} names "
                            f"\"{title}\" without a reference; consider @{mentioned}")

    # Spelling: warnings only, since new terms are often correct
    for source, words in sorted(spelling_problems(book, scan).items()):
        warnings.append(f"spelling in {source}: {', '.join(words)}")

    for warning in warnings:
        print_warning(warning)
    if errors:
        for error in errors:
            print_error(error)
        print_error(f"Check failed: {len(errors)} problem(s)")
        return False
    print_success(f"Check passed: {len(labels)} labels, "
                  f"{sum(len(e['refs']) for e in scan['files'].values())} references")
    return True
