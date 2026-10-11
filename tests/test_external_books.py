"""
References into another book: `@cb:thm-borrowed` in tests/fixture-book resolves against the
label registry of tests/fixture-companion (config "external-books", build/external.py).

The companion is built first, into a sibling directory, and publishes its registry as
_build/html/labels.json; the fixture book's config points `labels` at that file.
"""

import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FixtureBookCase, run_build  # noqa: E402
from build.check import check_xref_links  # noqa: E402
from tools import check_forward_deps  # noqa: E402

COMPANION = Path(__file__).resolve().parent / "fixture-companion"

CITING = """
In-text: @cb:thm-borrowed. Bracketed: [@cb:exm-lent]. Local, unchanged: @thm-main.

::: {#thm-leans-on-companion}
[Leaning]

A result whose proof cites the other book.
:::

::: {.proof}
By @cb:thm-borrowed and @lem-helper.
:::
"""


def configure(book_dir: Path, url: str, labels: str = "../companion/_build/html/labels.json",
              extra_text: str = ""):
    """Register the companion as `cb` and add a section citing it."""
    config_file = book_dir / "book.json"
    config = json.loads(config_file.read_text())
    config["external-books"] = {
        "cb": {"title": "Companion Book", "short": "CB", "url": url, "labels": labels},
    }
    config_file.write_text(json.dumps(config, indent=2))
    refs = book_dir / "src" / "ch02-more" / "01-refs.md"
    refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))
    (book_dir / "src" / "ch02-more" / "04-external.md").write_text(
        "# External\n" + CITING + extra_text)


def build_companion(book_dir: Path):
    companion = book_dir.parent / "companion"
    shutil.copytree(COMPANION, companion)
    result = run_build(companion, "html")
    if result.returncode != 0:
        raise AssertionError(f"companion build failed:\n{result.stdout}\n{result.stderr}")


class TestExternalAbsoluteUrl(FixtureBookCase):
    """The other book deployed at its own domain: absolute links, \\href in the PDF."""

    build_commands = [("html",), ("pdf",), ("book",)]

    @classmethod
    def prepare(cls, book_dir: Path):
        build_companion(book_dir)
        configure(book_dir, "https://companion.example.org")   # no trailing slash on purpose

    def test_companion_publishes_its_registry(self):
        published = json.loads((self.book_dir.parent / "companion" / "_build" / "html" / "labels.json").read_text())
        self.assertEqual(published["book"], "Companion Book")
        entry = published["crossref_labels"]["thm-borrowed"]
        self.assertEqual(entry["number"], "1.1.1")
        self.assertEqual(entry["file"], "ch01-tools/01-results.html")
        self.assertNotIn("html_content", entry)     # previews come from the book's own shards

    def test_html_in_text_reference(self):
        page = self.page("ch02-more/04-external.html")
        self.assertRegex(
            page, r'<a\s+href="https://companion\.example\.org/ch01-tools/01-results\.html#thm-borrowed"'
                  r'\s+class="xref xref-external"\s+data-ref="thm-borrowed"\s+data-shard="ch01-tools"'
                  r'\s+data-base="https://companion\.example\.org/"\s+data-book="Companion Book">'
                  r'Companion Book, Theorem 1\.1\.1</a>')

    def test_html_bracketed_reference_is_short(self):
        self.assertIn(">[CB, Example (Lent Example)]</a>", self.page("ch02-more/04-external.html"))

    def test_local_references_unaffected(self):
        page = self.page("ch02-more/04-external.html")
        self.assertRegex(page, r'href="\.\./ch01-basics/01-first\.html#thm-main"\s+class="xref"')
        self.assertIn(">Theorem 1.1.1</a>", page)
        self.assertEqual(check_xref_links(self.html), [])   # external links are not followed

    def test_latex_section_pdf(self):
        tex = (self.book.build_dir / "tmp" / "pdf-single" / "ch02-more" / "04-external.tex").read_text()
        self.assertIn(r"\href{https://companion.example.org/ch01-tools/01-results.html\#thm-borrowed}"
                      r"{Companion Book, Theorem~1.1.1}", tex)
        self.assertIn(r"[CB, Example (Lent Example)]}", tex)

    def test_latex_book_pdf(self):
        tex = (self.book.build_dir / "tmp" / "latex-book" / "book.tex").read_text()
        self.assertIn("{Companion Book, Theorem~1.1.1}", tex)
        self.assertIn(r"\hyperref[thm-main]{Theorem~\ref*{thm-main}}", tex)

    def test_external_citations_are_not_dependencies(self):
        labels = self.labels()
        record = labels["thm-leans-on-companion"]
        self.assertEqual(record["uses"], ["lem-helper"])
        self.assertEqual(record["external_uses"], ["cb:thm-borrowed"])
        self.assertEqual(check_forward_deps.find_violations(labels), [])
        self.assertEqual(check_forward_deps.external_citations(labels),
                         [("thm-leans-on-companion", "ch02-more/04-external.html", "cb:thm-borrowed")])

    def test_check_passes(self):
        result = run_build(self.book_dir, "check")
        self.assertEqual(result.returncode, 0, result.stdout)


class TestExternalRelativeUrl(FixtureBookCase):
    """Books side by side on one origin (a library): links relative to the page."""

    build_commands = [("html",), ("pdf",)]

    @classmethod
    def prepare(cls, book_dir: Path):
        build_companion(book_dir)
        configure(book_dir, "../companion/", labels="../companion/_build/crossref_labels.json")

    def test_html_link_is_relative_to_the_page(self):
        page = self.page("ch02-more/04-external.html")
        self.assertIn('href="../../companion/ch01-tools/01-results.html#thm-borrowed"', page)
        self.assertIn('data-base="../../companion/"', page)

    def test_pdf_prints_text_without_a_link(self):
        tex = (self.book.build_dir / "tmp" / "pdf-single" / "ch02-more" / "04-external.tex").read_text()
        self.assertIn("Companion Book, Theorem~1.1.1", tex)
        self.assertNotIn(r"\href{../", tex)


class TestExternalUnknownLabel(FixtureBookCase):
    """A label the other book does not have: a build warning, and check fails."""

    @classmethod
    def prepare(cls, book_dir: Path):
        build_companion(book_dir)
        configure(book_dir, "https://companion.example.org/",
                  extra_text="\nMissing: @cb:thm-nowhere. Unknown book: @zz:thm-other.\n")

    def test_build_warns(self):
        output = self.results[("html",)].stdout
        self.assertIn("unresolved reference @cb:thm-nowhere", output)
        self.assertIn("unresolved reference @zz:thm-other", output)

    def test_check_fails(self):
        result = run_build(self.book_dir, "check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unresolved reference @cb:thm-nowhere", result.stdout)
        self.assertIn("Companion Book has no label thm-nowhere", result.stdout)
        self.assertIn("no external book 'zz'", result.stdout)


class TestExternalRegistryMissing(FixtureBookCase):
    """The other book not built: references print without numbers, and check only warns."""

    @classmethod
    def prepare(cls, book_dir: Path):
        configure(book_dir, "https://companion.example.org/")   # companion never built

    def test_reference_falls_back_to_the_book(self):
        page = self.page("ch02-more/04-external.html")
        self.assertRegex(page, r'<a\s+href="https://companion\.example\.org/"\s+class="xref xref-external">'
                               r'Companion Book, thm-borrowed</a>')

    def test_check_warns_but_passes(self):
        result = run_build(self.book_dir, "check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("external book 'cb'", result.stdout)


if __name__ == "__main__":
    unittest.main()
