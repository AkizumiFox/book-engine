"""Anchors moved to another page keep working for links from outside the book.

When a section is split, its results move to a new page; cross-references inside the
book follow by themselves, but a deep link from elsewhere (page.html#thm-foo) would land
on the old page with no #thm-foo. Config "moved-ids" lists those anchors, the old page
forwards them, and check makes sure every entry still points from a gap to a real id.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build.check import check_moved_ids
from build.deploy import REDIRECT_PAGE
from build.pandoc import moved_ids
from test_build import FixtureBookCase, run_build  # noqa: E402

OLD, NEW = "ch13-psd-and-svd/06-block-positive-matrices.html", "ch13-psd-and-svd/07-determinant-inequalities.html"


class MovedIdsMetadata(unittest.TestCase):
    def test_entries_for_the_page_are_relative_to_it(self):
        config = {"moved-ids": {OLD: {"thm-b": NEW, "thm-a": NEW + "#thm-renamed"}}}
        self.assertEqual(moved_ids(config, OLD, "../"), [
            {"id": "thm-a", "target": "../" + NEW + "#thm-renamed"},
            {"id": "thm-b", "target": "../" + NEW + "#thm-b"},
        ])

    def test_other_pages_and_books_without_the_key_get_nothing(self):
        self.assertEqual(moved_ids({"moved-ids": {OLD: {"thm-a": NEW}}}, NEW, "../"), [])
        self.assertEqual(moved_ids({}, OLD, "../"), [])


class CheckMovedIds(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.html = Path(self._tmp.name)
        (self.html / "ch13-psd-and-svd").mkdir()
        (self.html / OLD).write_text('<p id="thm-stays">x</p>', encoding="utf-8")
        (self.html / NEW).write_text('<p id="thm-a">x</p><p id="thm-new">y</p>', encoding="utf-8")

    def problems(self, entries, page=OLD):
        return check_moved_ids({"moved-ids": {page: entries}}, self.html)

    def test_a_correct_entry_passes(self):
        self.assertEqual(self.problems({"thm-a": NEW, "thm-old": NEW + "#thm-new"}), [])

    def test_an_id_still_on_the_old_page(self):
        self.assertIn("still on", self.problems({"thm-stays": NEW})[0])

    def test_a_missing_target_page_or_id(self):
        self.assertIn("not found", self.problems({"thm-a": "ch13-psd-and-svd/99-gone.html"})[0])
        self.assertIn("has no #thm-zzz", self.problems({"thm-zzz": NEW})[0])

    def test_an_old_page_that_is_gone(self):
        self.assertIn("redirects", self.problems({"thm-a": NEW}, page="ch13-psd-and-svd/99-gone.html")[0])


class RedirectStubsKeepTheFragment(unittest.TestCase):
    def test_the_stub_appends_the_hash(self):
        page = REDIRECT_PAGE.format(target="../ch24a-notation/index.html")
        self.assertIn('location.replace("../ch24a-notation/index.html" + location.hash)', page)
        self.assertIn('http-equiv="refresh"', page)  # without scripts the page still moves


class MovedIdsInTheFixture(FixtureBookCase):
    """End to end: the old page forwards the moved id, and check accepts the entry."""

    @classmethod
    def prepare(cls, book_dir: Path):
        config = json.loads((book_dir / "book.json").read_text())
        config["moved-ids"] = {"ch01-basics/01-first.html": {"thm-old": "ch01-basics/02-second.html#thm-second"}}
        (book_dir / "book.json").write_text(json.dumps(config, indent=2))

    def test_the_old_page_carries_the_forwarding_script(self):
        page = self.page("ch01-basics/01-first.html")
        self.assertIn('"thm-old": "../ch01-basics/02-second.html#thm-second"', page)
        self.assertNotIn("var moved", self.page("ch01-basics/02-second.html"))

    def test_check_accepts_the_entry(self):
        result = run_build(self.book_dir, "check")
        self.assertNotIn("moved-ids", result.stdout)


if __name__ == "__main__":
    unittest.main()
