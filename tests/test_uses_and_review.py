"""The Uses line (`::: {.uses}`, filters/components.lua) and the chapter review page
(`review.md` in a chapter directory, build/book.py).

A Uses line is the last paragraph of a proof listing the results it used: small type after
an italic "Uses:" on the web and in the PDF, and an ordinary part of the proof for the label
scan (dependencies, forward-reference gate). A review page follows the chapter's last
section in the reading order, the sidebar and the PDF, unnumbered, and renumbers nothing.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FixtureBookCase  # noqa: E402
from tools.check_forward_deps import REVIEW_SECTION, from_file  # noqa: E402

ENGINE_ROOT = Path(__file__).resolve().parent.parent
FILTER = ENGINE_ROOT / "filters" / "components.lua"


def run_filter(text: str, to: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "page.md"
        source.write_text(text)
        args = ["pandoc", str(source), "-f", "markdown+tex_math_single_backslash", "-t", to,
                "--lua-filter", str(FILTER), "-M", "source-path=page.md"]
        return subprocess.run(args, capture_output=True, text=True, check=True).stdout


USES = """::: {.proof}
Suppose not. Then a contradiction.

::: {.uses}
Transitivity; the definition of a thing.
:::
:::
"""

RELABELLED = """::: {.uses label="Sources:"}
Two facts.
:::
"""

SECTION_WITH_USES = """# Third Section

::: {#thm-third}
A third theorem.
:::

::: {.proof}
It follows.

::: {.uses}
@thm-main (every thing has codimension one); @lem-helper.
:::
:::
"""

REVIEW = """# Chapter Review

## Summary

The chapter proved @thm-main.

## Terms

- **thing**: a map into the reals of norm one (@def-thing).
"""


class TestUsesFilter(unittest.TestCase):

    def test_html_small_div_with_label(self):
        html = run_filter(USES, "html")
        self.assertIn('<div class="uses">', html)
        self.assertIn("<p><em>Uses:</em> Transitivity; the definition of a thing.</p>", html)
        self.assertLess(html.index("Suppose not"), html.index('class="uses"'))

    def test_latex_environment(self):
        tex = run_filter(USES, "latex")
        self.assertIn("\\begin{bookuses}", tex)
        self.assertIn("\\emph{Uses:} Transitivity", tex)
        self.assertLess(tex.index("\\begin{bookuses}"), tex.index("\\end{bookuses}"))

    def test_label_attribute(self):
        self.assertIn("<em>Sources:</em> Two facts.", run_filter(RELABELLED, "html"))

    def test_environment_is_defined(self):
        sty = (ENGINE_ROOT / "latex" / "theorem-envs.sty").read_text()
        self.assertIn("\\newenvironment{bookuses}", sty)


class TestForwardDepsPlacesReview(unittest.TestCase):

    def test_review_after_every_section(self):
        self.assertEqual(from_file("ch02-more/review.html"), (2, "", REVIEW_SECTION))
        self.assertGreater(from_file("ch02-more/review.html"), from_file("ch02-more/99-last.html"))
        self.assertLess(from_file("ch02-more/review.html"), from_file("ch03-next/index.html"))


class TestUsesAndReviewInABook(FixtureBookCase):
    build_commands = [("html",)] + ([("book",)] if shutil.which("pdflatex") else [])

    @classmethod
    def prepare(cls, book_dir: Path):
        chapter = book_dir / "src" / "ch01-basics"
        (chapter / "03-third.md").write_text(SECTION_WITH_USES)
        (chapter / "review.md").write_text(REVIEW)

    def test_citations_in_a_uses_line_belong_to_the_proof(self):
        record = self.labels()["thm-third"]
        self.assertEqual(sorted(record["uses"]), ["lem-helper", "thm-main"])
        self.assertEqual(record["uses_kinds"]["thm-main"], ["proof"])

    def test_uses_line_rendered(self):
        page = self.page("ch01-basics/03-third.html")
        self.assertIn('<div class="uses">', page)
        self.assertIn("<em>Uses:</em>", page)
        self.assertIn('href="../ch01-basics/01-first.html#thm-main"', page)

    def test_review_page_follows_the_last_section(self):
        pages = [p for p in self.book.pages if p.chapter and p.chapter.slug == "ch01-basics"]
        self.assertEqual([p.source.name for p in pages],
                         ["index.md", "01-first.md", "02-second.md", "03-third.md", "review.md"])
        review = pages[-1]
        self.assertTrue(review.review)
        self.assertEqual(review.number, "")
        self.assertEqual(review.html_path, "ch01-basics/review.html")
        self.assertIs(pages[-2].neighbours["next"], review)
        self.assertEqual(review.neighbours["next"].html_path, "ch02-more/index.html")
        self.assertEqual(pages[0].html_path, "ch01-basics/index.html")   # the index stays first

    def test_sections_keep_their_numbers(self):
        numbers = {k: v["number"] for k, v in self.labels().items()}
        self.assertEqual(numbers["thm-third"], "1.3.1")
        self.assertEqual(numbers["thm-second"], "1.2.1")

    def test_sidebar_lists_review_last_without_a_number(self):
        nav = json.loads((self.html / "navigation.json").read_text())
        chapter = nav["chapters"][0]
        self.assertEqual(chapter["path"], "ch01-basics/index.html")
        last = chapter["sections"][-1]
        self.assertEqual((last["title"], last["number"], last["path"]),
                         ("Chapter Review", "", "ch01-basics/review.html"))
        page = self.page("ch01-basics/review.html")
        self.assertIn("Chapter Review", page)
        self.assertIn('href="../ch01-basics/01-first.html#thm-main"', page)
        self.assertNotIn('class="header-section-number"', page)   # no 1.0.x heading numbers

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "needs pdflatex")
    def test_book_pdf(self):
        text = subprocess.run(["pdftotext", str(self.book.book_pdf), "-"],
                              capture_output=True, text=True, check=True).stdout
        self.assertIn("Uses:", text)
        review = text.index("Chapter Review")
        self.assertGreater(review, text.index("Third Section"))
        self.assertLess(review, text.index("More Topics", review))


if __name__ == "__main__":
    unittest.main()
