"""
Config "short-urls": chapters at ch<N>/, sections named by their title slug without the
file number, the source-named paths kept as the tools' reading-order key and as redirects.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FIXTURE  # noqa: E402
from build.book import Book  # noqa: E402
from build.deploy import write_redirects  # noqa: E402


class TestShortUrls(unittest.TestCase):

    def test_paths(self):
        plain = Book(FIXTURE)
        short = Book(FIXTURE, overlay={"short-urls": True})
        for a, b in zip(plain.pages, short.pages):
            self.assertEqual(b.src_path or a.html_path, a.html_path)
            if a.chapter:
                self.assertTrue(b.html_path.startswith(f"ch{a.chapter.number}/"))
                name = Path(b.html_path).name
                self.assertFalse(name[0].isdigit(), name)
            else:
                self.assertEqual(a.html_path, b.html_path)

    def test_default_unchanged(self):
        book = Book(FIXTURE)
        for page in book.pages:
            self.assertEqual(page.source_key, page.html_path)

    def test_redirect_stubs(self):
        short = Book(FIXTURE, overlay={"short-urls": True})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            count = write_redirects(short, out)
            moved = [p for p in short.pages if p.src_path and p.src_path != p.html_path]
            self.assertEqual(count, len(moved))
            stub = (out / moved[0].src_path).read_text(encoding="utf-8")
            self.assertIn(moved[0].html_path, stub)


if __name__ == "__main__":
    unittest.main()
