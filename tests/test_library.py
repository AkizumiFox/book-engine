"""
`./build.py library <manifest>`: several books in one site (build/library.py).

tests/fixtures/library-a (prefix `a`) and library-b (prefix `b`) cite each other; the
manifest tests/fixtures/library.json puts them at alpha/ and beta/ under one site-url.
Beta also has its own site (`"canonical"` in the manifest): its pages are canonical there.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build.library import (ManifestError, book_overlay, landing_page, load_manifest,  # noqa: E402
                           relative_url)

ENGINE_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SITE = "https://shelf.example.org/library/"
BETA_HOME = "https://beta.example.net/"


def run_library(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ENGINE_ROOT / "build.py"), "library", *args],
                          cwd=cwd, capture_output=True, text=True)


def external_links(html: str) -> list[dict]:
    """Every a.xref-external in a page, as its attributes."""
    links = []
    for tag in re.findall(r"<a\s[^>]*xref-external[^>]*>", html):
        links.append(dict(re.findall(r'([\w-]+)="([^"]*)"', tag)))
    return links


class TestManifest(unittest.TestCase):

    def write(self, directory: Path, data) -> Path:
        path = directory / "m.json"
        path.write_text(json.dumps(data))
        return path

    def test_normalized(self):
        manifest = load_manifest(FIXTURES / "library.json")
        self.assertEqual(manifest["site-url"], SITE)                   # trailing slash added
        self.assertEqual(manifest["out"], (FIXTURES / "site").resolve())
        self.assertEqual(manifest["build-dir"], "_build/library")
        a, b = manifest["books"]
        self.assertEqual((a["subdir"], b["subdir"]), ("alpha", "beta"))
        self.assertEqual(b["path"], (FIXTURES / "library-b").resolve())
        self.assertIsNone(a["canonical"])
        self.assertEqual(b["canonical"], BETA_HOME)                     # trailing slash added

    def test_rejected(self):
        book = {"prefix": "a", "path": "x"}
        cases = [
            ({"books": [book]}, "site-url"),
            ({"site-url": SITE, "books": []}, "books"),
            ({"site-url": SITE, "books": [book, dict(book, subdir="y")]}, "twice"),
            ({"site-url": SITE, "books": [book, {"prefix": "b", "path": "x", "subdir": "a"}]}, "twice"),
            ({"site-url": SITE, "books": [dict(book, subdir="../up")]}, "subdir"),
            ({"site-url": SITE, "books": [{"prefix": "1a", "path": "x"}]}, "prefix"),
            ({"site-url": SITE, "books": [{"prefix": "a"}]}, "path"),
            ({"site-url": SITE, "books": [dict(book, canonical="beta.example.net")]}, "canonical"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for data, message in cases:
                with self.assertRaises(ManifestError) as caught:
                    load_manifest(self.write(Path(tmp), data))
                self.assertIn(message, str(caught.exception))

    def test_relative_url(self):
        self.assertEqual(relative_url("fd1", "fd2"), "../fd2/")
        self.assertEqual(relative_url("foundations/fd1", "analysis/an1"), "../../analysis/an1/")

    def test_overlay(self):
        manifest = load_manifest(FIXTURES / "library.json")
        a, b = manifest["books"]
        b["title"] = "Beta Book"
        registries = {"a": Path("/r/a.json"), "b": Path("/r/b.json")}
        own = {"external-books": {"b": {"title": "Own Title", "url": "https://beta.example.org/",
                                        "labels": "x.json"},
                                  "zz": {"title": "Elsewhere", "url": "https://zz.example.org/"}}}
        overlay = book_overlay(manifest, a, own, registries)
        self.assertEqual(overlay["site-url"], SITE + "alpha/")
        self.assertIsNone(overlay["deploy-domain"])                    # null: removed
        self.assertIsNone(overlay["canonical-url"])                    # canonical in the library
        self.assertEqual(book_overlay(manifest, b, {}, registries)["canonical-url"], BETA_HOME)
        self.assertEqual(overlay["external-books"], {
            "b": {"url": "../beta/", "labels": "/r/b.json", "short": "B"},  # own title kept
        })
        self.assertEqual(book_overlay(manifest, b, {}, registries)["external-books"]["a"],
                         {"url": "../alpha/", "labels": "/r/a.json", "title": "Alpha Book", "short": "A"})


class TestLibraryBuild(unittest.TestCase):
    """The two fixture books built into one site through the command line."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="library-test-")
        root = Path(cls.tmp.name)
        shutil.copytree(FIXTURES, root / "fixtures")
        cls.root = root / "fixtures"
        cls.out = cls.root / "site"
        cls.out.mkdir()
        (cls.out / ".git").mkdir()                       # a clone of the site repo: kept
        (cls.out / "stale.html").write_text("old")       # anything else: replaced
        # Run from inside a book, the way `./build.py library` runs from any book
        cls.result = run_library(cls.root / "library-a", "../library.json")
        if cls.result.returncode != 0:
            raise AssertionError(f"library build failed:\n{cls.result.stdout}\n{cls.result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def read(self, path: str) -> str:
        return (self.out / path).read_text(encoding="utf-8")

    def assert_links_reach(self, page: str, other: str, labels: set):
        links = external_links(self.read(page))
        self.assertEqual({link["data-ref"] for link in links}, labels)
        page_url = SITE + page
        for link in links:
            # the base resolves to the other book's sub-directory, on the same origin
            self.assertEqual(urljoin(page_url, link["data-base"]), f"{SITE}{other}/", link)
            self.assertTrue(link["data-base"].startswith("../"), link)
            tooltip = self.out / other / "theorems" / link["data-shard"] / f"{link['data-ref']}.json"
            self.assertTrue(tooltip.is_file(), tooltip)
            target = urljoin(page_url, link["href"])
            self.assertTrue(target.startswith(f"{SITE}{other}/"), target)
            self.assertTrue((self.out / target[len(SITE):].split("#")[0]).is_file(), target)

    def test_alpha_cites_beta(self):
        self.assert_links_reach("alpha/index.html", "beta", {"def-beta-thing"})
        self.assert_links_reach("alpha/ch01-start/01-results.html", "beta", {"thm-beta"})
        root_page = external_links(self.read("alpha/index.html"))[0]
        self.assertEqual(root_page["data-base"], "../beta/")

    def test_beta_cites_alpha(self):
        self.assert_links_reach("beta/index.html", "alpha", {"thm-alpha"})
        self.assert_links_reach("beta/ch01-base/01-facts.html", "alpha", {"thm-alpha"})
        self.assertEqual(external_links(self.read("beta/index.html"))[0]["data-base"], "../alpha/")
        self.assertIn("Alpha Book, Theorem 1.1.1", self.read("beta/ch01-base/01-facts.html"))

    def test_book_settings_survive_the_overlay(self):
        # Alpha's config names book b itself: its title stays, its url and labels do not
        page = self.read("alpha/ch01-start/01-results.html")
        self.assertIn("Beta, as Alpha calls it, Theorem 1.1.1", page)
        self.assertNotIn("beta.example.org", page)

    def test_canonical_urls_from_the_library(self):
        page = self.read("alpha/ch01-start/01-results.html")
        self.assertIn(f'<link rel="canonical" href="{SITE}alpha/ch01-start/01-results.html">', page)
        self.assertIn(f'<meta property="og:url" content="{SITE}alpha/ch01-start/01-results.html">', page)
        self.assertNotIn("alpha.example.org", page)                 # deploy-domain cleared
        self.assertNotIn(BETA_HOME, page)
        self.assertIn(f"<loc>{SITE}alpha/index.html</loc>", self.read("alpha/sitemap.xml"))
        self.assertIn('href="/library/alpha/styles.css"', self.read("alpha/404.html"))

    def test_canonical_urls_of_a_book_with_its_own_site(self):
        for path in ("index.html", "ch01-base/01-facts.html"):
            page = self.read(f"beta/{path}")
            self.assertIn(f'<link rel="canonical" href="{BETA_HOME}{path}">', page)
            self.assertIn(f'<meta property="og:url" content="{BETA_HOME}{path}">', page)
            self.assertNotIn(f"{SITE}beta/", page)
        # everything else is the library build: relative links and assets, sibling books
        self.assertEqual(external_links(self.read("beta/index.html"))[0]["data-base"], "../alpha/")
        self.assertIn('href="../styles.css', self.read("beta/ch01-base/01-facts.html"))
        self.assertIn('href="/library/beta/styles.css"', self.read("beta/404.html"))
        self.assertFalse((self.out / "beta" / "sitemap.xml").exists())  # indexed at its home
        self.assertFalse((self.out / "beta" / "robots.txt").exists())

    def test_landing_page(self):
        landing = self.read("index.html")
        self.assertIn("<h1>Test Library</h1>", landing)
        self.assertIn('<a class="card" href="alpha/" data-book="a"><h3>Alpha Book', landing)
        self.assertIn('<a class="card" href="beta/" data-book="b"><h3>Beta Book', landing)  # title from its config
        self.assertIn("<h2>First Series</h2>", landing)
        self.assertIn("<h2>Second Series</h2>", landing)
        self.assertIn('href="notes/notes.html"', landing)
        self.assertIn("prefers-color-scheme: dark", landing)
        self.assertNotRegex(landing, r"https?://(?!shelf\.example\.org)")  # no external fonts or scripts
        self.assertTrue((self.out / "notes" / "notes.html").is_file())

    def test_site_files(self):
        self.assertEqual(self.read("robots.txt"), f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n")
        sitemap = self.read("sitemap.xml")
        self.assertIn("<sitemapindex", sitemap)
        self.assertIn(f"<loc>{SITE}alpha/sitemap.xml</loc>", sitemap)
        self.assertNotIn("beta", sitemap)                           # canonical elsewhere
        self.assertIn(f"<loc>{SITE}sitemap-landing.xml</loc>", sitemap)
        not_found = self.read("404.html")
        self.assertIn('"/library/"', not_found)
        self.assertIn('"subdir": "beta"', not_found)
        self.assertTrue((self.out / ".nojekyll").exists())

    def test_only_html_is_copied(self):
        self.assertTrue((self.out / ".git").is_dir())
        self.assertFalse((self.out / "stale.html").exists())
        for book in ("alpha", "beta"):
            self.assertTrue((self.out / book / "labels.json").is_file())
            for absent in ("crossref_labels.json", "scan.json", "cache", "tmp", "pdf", "book"):
                self.assertFalse((self.out / book / absent).exists(), f"{book}/{absent}")

    def test_books_own_build_untouched(self):
        for book in ("library-a", "library-b"):
            self.assertFalse((self.root / book / "_build" / "html").exists())
            self.assertTrue((self.root / book / "_build" / "library" / "library-overlay.json").is_file())

    def test_refuses_an_output_holding_the_books(self):
        result = run_library(self.root, "library.json", "--out", ".")
        self.assertEqual(result.returncode, 1)
        self.assertIn("would delete", result.stdout)
        self.assertTrue((self.root / "library.json").is_file())

    def test_landing_without_groups_lists_series_in_order(self):
        manifest = load_manifest(self.root / "library.json")
        manifest["landing"] = {"title": "T"}
        for entry in manifest["books"]:
            entry.setdefault("title", entry["prefix"])
        page = landing_page(manifest)
        self.assertLess(page.index("First Series"), page.index("Second Series"))


if __name__ == "__main__":
    unittest.main()
