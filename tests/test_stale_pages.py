"""A built page whose source is gone must not survive the next build.

Splitting a section renames every page after it, and the old ones stay in the output
directory unless something removes them. Nothing downstream can tell a stale page from a
live one: `check` follows a link into it and reports an anchor that does not exist in any
source, and `deploy` copies the whole chapter directory, publishes it at its old URL,
and then finds a real page sitting where the redirect should go and writes no redirect.
The linear-algebra book produced six at once when a section was split.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build.html import _prune_stale_pages


class _Page:
    def __init__(self, html_path):
        self.html_path = html_path


class _Chapter:
    def __init__(self, slug):
        self.slug = slug


class _Book:
    def __init__(self, html_dir, chapters, pages):
        self.html_dir = html_dir
        self.chapters = [_Chapter(c) for c in chapters]
        self.pages = [_Page(p) for p in pages]


class PruneStalePages(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.html = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, *paths):
        for p in paths:
            f = self.html / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x", encoding="utf-8")

    def test_a_page_whose_source_is_gone_is_removed(self):
        self.write("ch13-x/06-a.html", "ch13-x/07-old.html", "ch13-x/07-new.html")
        book = _Book(self.html, ["ch13-x"], ["ch13-x/06-a.html", "ch13-x/07-new.html"])
        self.assertEqual(_prune_stale_pages(book), 1)
        self.assertFalse((self.html / "ch13-x/07-old.html").exists())
        self.assertTrue((self.html / "ch13-x/07-new.html").exists())
        self.assertTrue((self.html / "ch13-x/06-a.html").exists())

    def test_a_clean_output_directory_loses_nothing(self):
        self.write("ch13-x/06-a.html", "ch13-x/index.html")
        book = _Book(self.html, ["ch13-x"], ["ch13-x/06-a.html", "ch13-x/index.html"])
        self.assertEqual(_prune_stale_pages(book), 0)

    def test_a_chapter_the_book_no_longer_has_is_left_alone(self):
        """Not this function's job: deploy.is_stale_chapter_dir declines to publish a
        whole renamed chapter, and deleting it here would make a rename irreversible
        without a rebuild."""
        self.write("ch13-x/06-a.html", "ch12-old/01-a.html")
        book = _Book(self.html, ["ch13-x"], ["ch13-x/06-a.html"])
        self.assertEqual(_prune_stale_pages(book), 0)
        self.assertTrue((self.html / "ch12-old/01-a.html").exists())

    def test_non_page_files_are_left_alone(self):
        self.write("ch13-x/06-a.html", "ch13-x/diagram.svg", "ch13-x/data.json")
        book = _Book(self.html, ["ch13-x"], ["ch13-x/06-a.html"])
        self.assertEqual(_prune_stale_pages(book), 0)
        self.assertTrue((self.html / "ch13-x/diagram.svg").exists())
        self.assertTrue((self.html / "ch13-x/data.json").exists())


if __name__ == "__main__":
    unittest.main()
