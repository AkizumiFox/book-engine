"""The TikZ diagram templates of latex/book-diagrams.sty.

Each picture in tests/fixtures/diagrams (the examples authoring guides copy) is compiled
the way the website compiles a figure (build/tikz.py's standalone template, which loads the
style), and a fixture book with all of them on one page is built to HTML (an SVG each) and
to a section PDF (latex/preamble.tex loads the style).
"""

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build.book import ENGINE_ROOT  # noqa: E402
from build.tikz import _compile_one  # noqa: E402
from test_build import FixtureBookCase  # noqa: E402

PICTURES = sorted((Path(__file__).resolve().parent / "fixtures" / "diagrams").glob("*.tex"))
HAVE_TEX = bool(shutil.which("pdflatex") and shutil.which("pdftocairo"))


@unittest.skipUnless(HAVE_TEX, "needs pdflatex and pdftocairo")
class TestStandalone(unittest.TestCase):

    def test_every_template_compiles_to_svg(self):
        self.assertEqual([p.stem for p in PICTURES],
                         ["arrow-diagram", "flowchart", "hasse", "square", "tree"])
        with tempfile.TemporaryDirectory() as tmp:
            macros = Path(tmp) / "macros.tex"
            macros.write_text("")
            for picture in PICTURES:
                source = Path(tmp) / picture.name
                shutil.copy(picture, source)
                _, error = _compile_one(source, macros, f".:{ENGINE_ROOT}//:")
                self.assertIsNone(error, picture.name)
                self.assertIn("<svg", source.with_suffix(".svg").read_text())


@unittest.skipUnless(HAVE_TEX, "needs pdflatex and pdftocairo")
class TestDiagramsInABook(FixtureBookCase):
    build_commands = [("html",), ("pdf",)]

    @classmethod
    def prepare(cls, book_dir: Path):
        refs = book_dir / "src" / "ch02-more" / "01-refs.md"
        refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))
        blocks = "\n\n".join("```{=latex}\n" + p.read_text() + "```" for p in PICTURES)
        (book_dir / "src" / "ch02-more" / "04-diagrams.md").write_text("# Diagrams\n\n" + blocks + "\n")

    def test_each_picture_is_an_svg(self):
        page = self.page("ch02-more/04-diagrams.html")
        self.assertEqual(page.count('class="tikz"'), len(PICTURES))
        svgs = re.findall(r'<img\s+src="\.\./tikz/([0-9a-f]+)\.svg"', page)
        self.assertEqual(len(set(svgs)), len(PICTURES))
        for name in svgs:
            self.assertTrue((self.html / "tikz" / f"{name}.svg").exists(), name)

    def test_section_pdf(self):
        pdfs = list(self.book.pdf_dir.rglob("04-diagrams.pdf"))
        self.assertEqual(len(pdfs), 1, self.results[("pdf",)].stdout[-2000:])


if __name__ == "__main__":
    unittest.main()
