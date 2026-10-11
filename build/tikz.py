"""
Build System TikZ Module
========================
Compiles the TikZ pictures collected by filters/tikz.lua into SVG for the website.
Each picture is compiled once as a standalone document and cached by content hash.
"""

import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .book import Book
from .utils import print_step, print_success, print_error, print_warning

# Web text (20px) is about 1.5 times the PDF's 10pt text, so figures are enlarged to keep
# their size relative to the text (the viewBox is unchanged, so they stay sharp).
WEB_SCALE = 1.5
# Fitch derivations are text, not pictures: scaled so their formulas match the body text's
# size on the web (20px) rather than a figure's.
DERIVATION_SCALE = 2.0

STANDALONE_TEMPLATE = r"""\documentclass[tikz,border=2pt]{standalone}
\usepackage{amsmath,amssymb,amsthm,mathtools,bbm}
\usepackage{tikz-cd}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usetikzlibrary{arrows.meta,shapes.geometric,calc,positioning,patterns}
\IfFileExists{fitch-book.sty}{\usepackage{fitch-book}}{}
\input{%(macros)s}
\begin{document}
%(picture)s
\end{document}
"""


def _scale_svg(svg: Path, factor: float):
    """Multiply the root <svg> width and height attributes by `factor`."""
    text = svg.read_text(encoding="utf-8")
    head, rest = text.split("<svg", 1)
    tag, body = rest.split(">", 1)
    for attribute in ("width", "height"):
        tag = re.sub(rf'\b{attribute}="([\d.]+)(pt)?"',
                     lambda m: f'{attribute}="{float(m.group(1)) * factor:.3f}"', tag, count=1)
    svg.write_text(f"{head}<svg{tag}>{body}", encoding="utf-8")


def _compile_one(tex_source: Path, macros_file: Path, tex_inputs: str) -> tuple[Path, str | None]:
    """Compile one picture to SVG next to its source. Returns (source, error or None)."""
    svg = tex_source.with_suffix(".svg")
    with tempfile.TemporaryDirectory(prefix="tikz-") as tmp:
        tmp_dir = Path(tmp)
        doc = tmp_dir / "picture.tex"
        picture = tex_source.read_text(encoding="utf-8")
        template = STANDALONE_TEMPLATE
        if picture.lstrip().startswith("$\\begin{nd}"):
            # A Fitch derivation (filters/tikz.lua wraps it in $...$) is not a tikzpicture:
            # standalone's `tikz` option crops only tikzpictures and would leave it on a
            # full page. Without the option standalone crops to the content, as it should.
            template = template.replace("\\documentclass[tikz,border=2pt]{standalone}",
                                        "\\documentclass[border=2pt]{standalone}", 1)
        doc.write_text(template % {
            "macros": macros_file.as_posix(),
            "picture": picture,
        }, encoding="utf-8")
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", doc.name],
            cwd=tmp_dir, capture_output=True, text=True, errors="replace",
            env={**os.environ, "TEXINPUTS": tex_inputs},
        )
        pdf = tmp_dir / "picture.pdf"
        if result.returncode != 0 or not pdf.exists():
            errors = [line for line in result.stdout.splitlines() if line.startswith("!")]
            return tex_source, "; ".join(errors[:3]) or "pdflatex failed"
        result = subprocess.run(["pdftocairo", "-svg", str(pdf), str(svg)], capture_output=True, text=True)
        if result.returncode != 0:
            return tex_source, result.stderr.strip() or "pdftocairo failed"
        _scale_svg(svg, DERIVATION_SCALE if picture.lstrip().startswith("$\\begin{nd}") else WEB_SCALE)
    return tex_source, None


def build_tikz_figures(book: Book):
    """Compile pending TikZ sources and copy every SVG into the HTML output."""
    cache_dir = book.tikz_cache_dir
    if not cache_dir.exists():
        return
    sources = sorted(cache_dir.glob("*.tex"))
    if not sources:
        return

    macros_file = book.macros_file
    macros_mtime = macros_file.stat().st_mtime if macros_file.exists() else 0
    stamp = cache_dir / f"scale-{WEB_SCALE}-{DERIVATION_SCALE}"
    if not stamp.exists():  # figures compiled at another scale
        for old in cache_dir.glob("*.svg"):
            old.unlink()
        for old_stamp in cache_dir.glob("scale-*"):
            old_stamp.unlink()
        stamp.touch()
    pending = [
        src for src in sources
        if not src.with_suffix(".svg").exists() or src.with_suffix(".svg").stat().st_mtime < macros_mtime
    ]

    if pending:
        if not shutil.which("pdflatex") or not shutil.which("pdftocairo"):
            print_warning("pdflatex or pdftocairo not found; TikZ figures will be missing from the website")
        else:
            print_step(f"Compiling {len(pending)} TikZ figure(s)...")
            with ThreadPoolExecutor(max_workers=min(4, len(pending))) as executor:
                for src, error in executor.map(lambda s: _compile_one(s, macros_file, book.tex_inputs), pending):
                    if error:
                        print_error(f"TikZ figure {src.stem[:12]} failed: {error}")

    dest = book.html_dir / "tikz"
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for svg in cache_dir.glob("*.svg"):
        target = dest / svg.name
        if not target.exists() or target.stat().st_mtime < svg.stat().st_mtime:
            shutil.copy2(svg, target)
        count += 1
    print_success(f"TikZ figures: {count}")
