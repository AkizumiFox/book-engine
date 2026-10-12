"""Back matter: config "back-matter" lists Markdown files (a glossary) that follow the last
chapter as unnumbered pages at the site root, linked from the sidebar, after the last
section in the reading order, and at the end of the book PDF under their own banner."""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FixtureBookCase  # noqa: E402

GLOSSARY = """# Glossary

Each term once, with the place it is defined.

- **Thing**: what @def-thing defines.
- **Main theorem**: @thm-main.
"""


class TestBackMatter(FixtureBookCase):
    build_commands = [("html",)] + ([("book",)] if shutil.which("pdflatex") else [])

    @classmethod
    def prepare(cls, book_dir: Path):
        config = json.loads((book_dir / "book.json").read_text())
        config["back-matter"] = ["src/glossary.md", "src/missing.md"]
        (book_dir / "book.json").write_text(json.dumps(config, indent=2))
        (book_dir / "src" / "glossary.md").write_text(GLOSSARY)
        refs = book_dir / "src" / "ch02-more" / "01-refs.md"
        refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))

    def test_page_and_its_place(self):
        pages = self.book.pages
        self.assertEqual(pages[-1].html_path, "glossary.html")      # a missing file is skipped
        self.assertTrue(pages[-1].back)
        self.assertFalse(pages[-1].is_preface)
        self.assertTrue(pages[0].is_preface)
        self.assertIs(pages[-2].neighbours["next"], pages[-1])
        page = self.page("glossary.html")
        self.assertIn("Glossary", page)
        self.assertIn('href="./ch01-basics/01-first.html#def-thing"', page)   # references resolve

    def test_sidebar_link(self):
        nav = json.loads((self.html / "navigation.json").read_text())
        self.assertIn({"title": "Glossary", "path": "glossary.html", "icon": "bi-journal-text"}, nav["extras"])
        self.assertIn('href="../glossary.html"', self.page("ch02-more/01-refs.html"))

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "needs pdflatex")
    def test_end_of_the_book_pdf(self):
        text = subprocess.run(["pdftotext", str(self.book.book_pdf), "-"],
                              capture_output=True, text=True, check=True).stdout
        self.assertIn("Glossary", text)
        self.assertGreater(text.rindex("Each term once"), text.index("More Topics"))


if __name__ == "__main__":
    unittest.main()
