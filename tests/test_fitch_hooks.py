"""The Fitch-derivation hooks are inert unless a book ships latex/fitch-book.sty.

A book that does (Foundations) writes `\\begin{nd} ... \\end{nd}` in a raw LaTeX block:
latex/preamble*.tex load the style if it exists, filters/tikz.lua compiles the
derivation to an SVG for the web like a TikZ picture (in math mode, alt "Derivation"),
and build/tikz.py crops it without standalone's `tikz` option. Here a five-line stand-in
for the style is enough to exercise all three. The book opts out of drawing derivations in
HTML ("fitch-html": false, tests/test_fitch_html.py), so the web build takes the SVG path.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FixtureBookCase  # noqa: E402

FITCH_STAND_IN = r"""\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{fitch-book}[2026/10/11 stand-in for the engine tests]
\newcommand{\have}[2]{#2\\}
\newcommand{\by}[2]{\quad\text{#1 #2}}
\newenvironment{nd}[1][]{\begin{array}{l}}{\end{array}}
"""

SECTION = r"""# Derivations

```{=latex}
\begin{center}
$\begin{nd}
  \have {i} {a < b}
  \have {k} {a < c} \by{Tr}{i}
\end{nd}$
\end{center}
```
"""


class TestFitchHooks(FixtureBookCase):
    build_commands = [("html",), ("pdf",)]

    @classmethod
    def prepare(cls, book_dir: Path):
        book_json = book_dir / "book.json"
        book_json.write_text(book_json.read_text().replace('{', '{\n    "fitch-html": false,', 1))
        (book_dir / "latex").mkdir(exist_ok=True)
        (book_dir / "latex" / "fitch-book.sty").write_text(FITCH_STAND_IN)
        refs = book_dir / "src" / "ch02-more" / "01-refs.md"
        refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))
        (book_dir / "src" / "ch02-more" / "04-derivations.md").write_text(SECTION)

    def test_derivation_is_an_svg_on_the_web(self):
        page = self.page("ch02-more/04-derivations.html")
        match = re.search(r'<img\s+src="\.\./tikz/([0-9a-f]+)\.svg"[^>]*alt="Derivation"', page)
        self.assertIsNotNone(match)
        self.assertTrue((self.html / "tikz" / f"{match.group(1)}.svg").exists())
        self.assertNotIn(r"\begin{nd}", page)

    def test_derivation_passes_through_to_the_pdf(self):
        tex = (self.book.build_dir / "tmp" / "pdf-single" / "ch02-more" / "04-derivations.tex").read_text()
        self.assertIn(r"\begin{nd}", tex)
        self.assertTrue((self.book.build_dir / "pdf" / "ch02-more" / "04-derivations.pdf").exists())
