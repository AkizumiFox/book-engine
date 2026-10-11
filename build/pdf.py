"""
Build System PDF Module
=======================
Per-section PDFs (skipped when unchanged) and the combined book PDF.
"""

import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from .book import Book, Page
from .external import external_file
from .html import FingerprintStore, page_fingerprint
from .manifest import scan_labels, load_scan
from .pandoc import (MARKDOWN_FORMAT, build_pandoc_command, environments_tex, page_metadata,
                     run_pandoc)
from .utils import print_step, print_file_action, print_success, print_error


def _pdflatex(book: Book, tex_file: Path, runs: int = 1) -> subprocess.CompletedProcess:
    env = {**os.environ, "TEXINPUTS": book.tex_inputs}
    result = None
    for _ in range(runs):
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file.name],
            cwd=str(tex_file.parent), env=env, capture_output=True, text=True, errors="replace",
        )
    return result


def _latex_error_lines(result: subprocess.CompletedProcess) -> list:
    """The `! ...` lines pdflatex printed. Non-empty means the PDF is damaged.

    pdflatex runs in nonstopmode, so it recovers from an error and still writes
    a PDF -- with the offending block dropped or mangled. A PDF existing is
    therefore not evidence of success; the absence of these lines is. (Twelve
    algorithm blocks shipped broken this way, the environment undefined in
    every build, while the build reported success.)
    """
    lines = result.stdout.splitlines()
    errors = []
    for i, line in enumerate(lines):
        if not line.startswith("!"):
            continue
        # A real TeX error is followed by its context, "l.<number> ..." (or "<*>" for a fatal
        # stop). A line that merely starts with "!" can also be a wrapped continuation of an
        # Overfull \hbox box dump, which is a warning, not an error.
        context = lines[i + 1:i + 14]
        if any(c.startswith("l.") and c[2:3].isdigit() for c in context) or \
                any(c.startswith("<*>") for c in context) or "Emergency stop" in line:
            errors.append(line)
    return errors


def _latex_errors(result: subprocess.CompletedProcess) -> str:
    errors = _latex_error_lines(result)
    return "; ".join(errors[:3]) or "\n".join(result.stdout.splitlines()[-20:])


# =============================================================================
# Section PDFs
# =============================================================================

def build_pdf(book: Book, specific_file: Optional[Path] = None) -> bool:
    """Build per-section PDFs (pandoc -> .tex, then pdflatex). Returns True on success."""
    print_step("Building PDF...")
    scan = scan_labels(book)
    _, labels = load_scan(book)

    tex_root = book.build_dir / "tmp" / "pdf-single"
    pages = book.pages
    if specific_file:
        page = book.page_for(specific_file)
        if not page:
            print_error(f"File not found in chapters: {specific_file}")
            return False
        pages = [page]

    engine = book.engine_fingerprint()
    store = FingerprintStore(book.cache_dir / "pdf-fingerprints.json")

    def build_one(page: Page) -> bool:
        relative_pdf = Path(page.html_path).with_suffix(".pdf")
        output_file = book.pdf_dir / relative_pdf
        tex_file = tex_root / relative_pdf.with_suffix(".tex")
        tex_file.parent.mkdir(parents=True, exist_ok=True)

        metadata = page_metadata(book, page, "pdf")
        cmd = build_pandoc_command(book, page, tex_file, "pdf", metadata)
        if not run_pandoc(cmd, cwd=book.root):
            return False
        result = _pdflatex(book, tex_file)
        # References to labels in the same file resolve on a second pass
        if "Rerun to get" in result.stdout or "undefined references" in result.stdout:
            result = _pdflatex(book, tex_file)
        out_pdf = tex_file.with_suffix(".pdf")
        if not out_pdf.exists():
            print_error(f"pdflatex failed for {page.source.name}: {_latex_errors(result)}")
            return False
        if _latex_error_lines(result):
            print_error(f"LaTeX errors in {page.source.name}: {_latex_errors(result)}")
            return False
        output_file.parent.mkdir(parents=True, exist_ok=True)
        out_pdf.replace(output_file)
        return True

    tasks = []
    for page in pages:
        metadata = page_metadata(book, page, "pdf")
        fingerprint = page_fingerprint(book, page, metadata, engine, scan, labels)
        output_file = book.pdf_dir / Path(page.html_path).with_suffix(".pdf")
        if not store.unchanged(page.html_path, fingerprint, output_file):
            tasks.append((page, fingerprint))

    failures = 0
    if tasks:
        with ThreadPoolExecutor(max_workers=min(4, len(tasks))) as executor:
            for (page, fingerprint), ok in zip(tasks, executor.map(lambda t: build_one(t[0]), tasks)):
                if ok:
                    store.record(page.html_path, fingerprint)
                    print_file_action("Built", page.source.name, Path(page.html_path).with_suffix(".pdf").name)
                else:
                    failures += 1
        store.save()
    skipped = len(pages) - len(tasks)
    summary = (f"{len(tasks) - failures}/{len(tasks)} built"
               + (f", {skipped} unchanged" if skipped else ""))
    if failures:
        print_error(f"PDF build FAILED: {failures} section(s) did not build cleanly ({summary})")
    else:
        print_success(f"PDF build complete: {summary}")

    _sync_pdfs_to_html(book)
    return failures == 0


def _sync_pdfs_to_html(book: Book):
    """Copy per-section PDFs into the website so the PDF links work."""
    if not book.pdf_dir.exists():
        return
    destination = book.html_dir / "pdf"
    for source in book.pdf_dir.rglob("*.pdf"):
        if source.resolve() == book.book_pdf.resolve():
            continue
        target = destination / source.relative_to(book.pdf_dir)
        if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


# =============================================================================
# Book PDF
# =============================================================================

def build_book(book: Book) -> bool:
    """Build the combined book PDF. Returns True on success."""
    print_step("Building combined book PDF...")
    scan_labels(book)

    latex_tmp = book.build_dir / "tmp" / "latex-book"
    latex_tmp.mkdir(parents=True, exist_ok=True)
    tex_file = latex_tmp / "book.tex"

    pages = book.pages
    if not pages:
        print_error("No source files found")
        return False

    # One Markdown document with a boundary marker before each file; theorems.lua uses the
    # markers to set LaTeX's part/chapter counters.
    parts = []
    for page in pages:
        attrs = f'data-chapter="{page.chapter_number}" data-section="{page.section}"'
        if page.is_preface:
            attrs += ' data-preface="true"'
        if page.section == 0 and page.chapter and page.chapter.part:
            attrs += f' data-part-title="{page.chapter.part}"'
        if page.section >= 1:
            attrs += f' data-chapter-title="{page.chapter.title}"'
        marker = f"\n\n::: {{.file-boundary {attrs}}}\n:::\n\n"
        parts.append(marker + page.source.read_text(encoding="utf-8"))
    combined_path = latex_tmp / "_combined.md"
    combined_path.write_text("\n\n".join(parts), encoding="utf-8")

    book_meta = latex_tmp / "_book_meta.json"
    book_meta.write_text(json.dumps({
        "book-mode": True,
        "is-preface": True,
        "environment_settings": book.environment_settings,
        "crossref-labels-file": str(book.labels_file),
        "book-root": str(book.root),
        "engine-root": str(book.filters_dir.parent),
        "source-path": "book",
        **({"external-books-file": str(external_file(book))}
           if book.config.get("external-books") and external_file(book).exists() else {}),
    }), encoding="utf-8")

    filters = book.filters_dir
    cmd = [
        "pandoc", str(combined_path),
        "-f", MARKDOWN_FORMAT,
        "-o", str(tex_file),
        "--standalone",
        "--toc", "--toc-depth", "2",
        "--variable", "titlepage",
        "--top-level-division", "chapter",
        "--metadata-file", str(book_meta),
        "--metadata", f"title={book.title}",
        "--metadata", f"author={book.author or 'Anonymous'}",
        "--resource-path", ":".join([str(book.src_dir)] + [str(c.directory) for c in book.chapters]),
        "--template", str(book.latex_template),
        "--lua-filter", str(filters / "format-visibility.lua"),
        "--lua-filter", str(filters / "components.lua"),
        "--lua-filter", str(filters / "enumerate.lua"),
        "--lua-filter", str(filters / "theorems.lua"),
        "--include-in-header", str(book.engine_file("latex/preamble-book.tex")),
        # The config's environments, declared for the preamble that just
        # defined how they are framed.
        "--include-in-header", str(environments_tex(book)),
    ]
    if book.macros_file.exists():
        cmd += ["--include-in-header", str(book.macros_file)]

    if not run_pandoc(cmd, cwd=book.root):
        return False

    # Two runs so the table of contents and references resolve
    result = _pdflatex(book, tex_file, runs=2)
    out_pdf = tex_file.with_suffix(".pdf")
    if not out_pdf.exists():
        print_error(f"pdflatex did not produce the book PDF: {_latex_errors(result)}")
        return False
    if _latex_error_lines(result):
        print_error(f"LaTeX errors in the book PDF: {_latex_errors(result)}")
        return False
    book.book_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.replace(book.book_pdf)
    print_success(f"Book PDF created: {book.book_pdf}")

    book_in_html = book.html_dir / "book" / "book.pdf"
    book_in_html.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(book.book_pdf, book_in_html)
    return True
