"""
`--config-overlay FILE`: config keys overridden for one build, the config file untouched
(build/book.py: merge_patch, load_overlay). The library assembler builds every book this way.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FIXTURE, FixtureBookCase, run_build  # noqa: E402
from build.book import Book, merge_patch  # noqa: E402

SITE = "https://shelf.example.org/library/fx/"


class TestMergePatch(unittest.TestCase):

    def test_objects_merge_recursively(self):
        base = {"external-books": {"la": {"title": "Linear Algebra", "url": "https://la.example/"}},
                "title": "T"}
        patch = {"external-books": {"la": {"url": "../la/"}, "an": {"title": "Analysis"}}}
        self.assertEqual(merge_patch(base, patch), {
            "title": "T",
            "external-books": {"la": {"title": "Linear Algebra", "url": "../la/"},
                               "an": {"title": "Analysis"}},
        })

    def test_null_removes_and_lists_replace(self):
        base = {"deploy-domain": "books.example", "chapters": ["a", "b"], "keep": 1}
        merged = merge_patch(base, {"deploy-domain": None, "chapters": ["c"], "absent": None})
        self.assertEqual(merged, {"chapters": ["c"], "keep": 1})

    def test_inputs_unchanged(self):
        base = {"a": {"b": 1}}
        patch = {"a": {"c": 2}}
        merge_patch(base, patch)
        self.assertEqual(base, {"a": {"b": 1}})
        self.assertEqual(patch, {"a": {"c": 2}})


class TestBookOverlay(unittest.TestCase):

    def test_dict_and_file_overlays(self):
        with tempfile.TemporaryDirectory() as tmp:
            overlay = Path(tmp) / "overlay.json"
            overlay.write_text(json.dumps({"site-url": SITE.rstrip("/"), "author": None}))
            for given in ({"site-url": SITE.rstrip("/"), "author": None}, overlay, str(overlay)):
                book = Book(FIXTURE, overlay=given)
                self.assertEqual(book.site_url, SITE)
                self.assertEqual(book.site_path, "/library/fx/")
                self.assertNotIn("author", book.config)
                self.assertEqual(book.title, "Fixture Book")       # untouched keys stay
            self.assertEqual(Book(FIXTURE).site_url, "")

    def test_overlay_changes_the_engine_fingerprint(self):
        plain = Book(FIXTURE).engine_fingerprint()
        self.assertEqual(Book(FIXTURE, overlay={}).engine_fingerprint(), plain)
        self.assertNotEqual(Book(FIXTURE, overlay={"site-url": SITE}).engine_fingerprint(), plain)

    def test_bad_overlays(self):
        with tempfile.TemporaryDirectory() as tmp:
            not_object = Path(tmp) / "list.json"
            not_object.write_text("[1, 2]")
            broken = Path(tmp) / "broken.json"
            broken.write_text("{")
            self.assertRaises(ValueError, Book, FIXTURE, overlay=not_object)
            self.assertRaises(ValueError, Book, FIXTURE, overlay=broken)
            self.assertRaises(FileNotFoundError, Book, FIXTURE, overlay=Path(tmp) / "missing.json")
            for path in (not_object, Path(tmp) / "missing.json"):
                result = run_build(FIXTURE, "scan", "--config-overlay", str(path))
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("Config overlay", result.stdout)


class TestOverlayBuild(FixtureBookCase):
    """Built with an overlay: canonical/og URLs, sitemap and 404 follow the overlay's site-url;
    a later build without it drops them again."""

    @classmethod
    def prepare(cls, book_dir: Path):
        overlay = book_dir.parent / "overlay.json"
        overlay.write_text(json.dumps({"site-url": SITE, "title": "Overlaid Title"}))
        cls.config_before = (book_dir / "book.json").read_text()
        cls.build_commands = [("html", "--config-overlay", str(overlay))]

    def test_config_file_untouched(self):
        self.assertEqual((self.book_dir / "book.json").read_text(), self.config_before)

    def test_canonical_and_og_from_overlay(self):
        page = self.page("ch01-basics/01-first.html")
        self.assertIn(f'<link rel="canonical" href="{SITE}ch01-basics/01-first.html">', page)
        self.assertIn(f'<meta property="og:url" content="{SITE}ch01-basics/01-first.html">', page)
        self.assertIn("Overlaid Title", page)

    def test_site_files_from_overlay(self):
        self.assertIn(f"<loc>{SITE}index.html</loc>", self.page("sitemap.xml"))
        self.assertFalse((self.html / "robots.txt").exists())      # a sub-path: the root has it
        self.assertIn('href="/library/fx/styles.css"', self.page("404.html"))

    def test_zz_rebuild_without_overlay(self):   # last: it rebuilds the shared output
        result = run_build(self.book_dir, "html")
        self.assertEqual(result.returncode, 0, result.stdout)
        page = self.page("ch01-basics/01-first.html")
        self.assertNotIn("canonical", page)
        self.assertNotIn("Overlaid Title", page)


if __name__ == "__main__":
    unittest.main()
