"""The second-reading fold: ::: {.second-reading title="..."} (filters/components.lua).

A display device: closed <details> on the website, the content inline between light rules
in the PDF. Environments inside it are numbered, labelled, cited and previewed exactly as
outside it, and the label scan (dependencies, search text) sees them as main-line blocks.
A fold inside a fold, and a heading inside a fold, are component errors (`check` fails).
"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FixtureBookCase, run_build  # noqa: E402
from test_fitch_html import prepare_book  # noqa: E402

ENGINE_ROOT = Path(__file__).resolve().parent.parent
FILTER = ENGINE_ROOT / "filters" / "components.lua"


def run_filter(text: str, to: str, scan: bool = False) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "page.md"
        source.write_text(text)
        args = ["pandoc", str(source), "-f", "markdown+tex_math_single_backslash", "-t", to,
                "--lua-filter", str(FILTER), "-M", "source-path=page.md"]
        if scan:
            args += ["-M", "scan_mode=true"]
        if to == "html":
            args.append("--mathjax")
        return subprocess.run(args, capture_output=True, text=True, check=True)


FOLD = """Before.

::: {.second-reading title="Why $P \\to P$ is *legal*"}
Inside the fold.
:::

::: {.second-reading}
Untitled fold.
:::

After.
"""

NESTED = """::: {.second-reading title="Outer"}
Outer text.

::: {.second-reading title="Inner"}
Inner text.
:::
:::
"""

HEADING = """::: {.second-reading}
## A heading
Text.
:::
"""


class TestSecondReadingFilter(unittest.TestCase):

    def test_html_is_a_closed_details_with_marker_and_title(self):
        html = run_filter(FOLD, "html").stdout
        self.assertEqual(html.count('<details class="second-reading">'), 2)
        self.assertNotIn(" open", html)                     # closed by default
        self.assertEqual(html.count("</div></details>"), 2)
        first = html[html.index("<details"):html.index("</details>")]
        self.assertIn('<span class="second-reading-marker" aria-hidden="true">', first)
        self.assertIn('<span class="second-reading-kicker">Second reading</span>', first)
        self.assertIn(r'\(P \to P\)', first)                 # math in the title stays math
        self.assertIn("<em>legal</em>", first)
        self.assertIn('<div class="second-reading-body">', first)
        self.assertIn("<p>Inside the fold.</p>", first)
        # Without a title the head is "Second reading" itself
        second = html[html.index("<details", html.index("</details>")):]
        self.assertIn('<span class="second-reading-title">Second reading</span>', second)
        self.assertNotIn("second-reading-kicker", second)
        # Text outside stays outside
        self.assertLess(html.index("Before."), html.index("<details"))
        self.assertGreater(html.index("After."), html.rindex("</details>"))

    def test_latex_prints_the_content_between_the_rules(self):
        tex = run_filter(FOLD, "latex").stdout
        self.assertIn(r"\begin{booksecondreading}{1}{Why \(P \to P\) is \emph{legal}}", tex)
        self.assertIn(r"\begin{booksecondreading}{0}{Second reading}", tex)
        self.assertEqual(tex.count(r"\end{booksecondreading}"), 2)
        self.assertNotIn("details", tex)
        inside = tex[tex.index(r"\begin{booksecondreading}{1}"):tex.index(r"\end{booksecondreading}")]
        self.assertIn("Inside the fold.", inside)

    def test_the_scan_sees_the_content_as_main_line(self):
        out = run_filter(FOLD, "json", scan=True).stdout
        doc = json.loads(out)
        kinds = [block["t"] for block in doc["blocks"]]
        self.assertNotIn("Div", kinds)                    # flattened
        self.assertIn("Inside the fold.", run_filter(FOLD, "plain", scan=True).stdout)

    def test_a_nested_fold_is_an_error(self):
        result = run_filter(NESTED, "json", scan=True)
        self.assertIn("COMPONENT_ERROR:", result.stdout)
        self.assertIn("inside another second-reading fold", result.stdout)
        html = run_filter(NESTED, "html")
        self.assertIn("inside another second-reading fold", result.stdout + html.stderr)
        # The text survives, in one fold
        self.assertEqual(html.stdout.count("<details"), 1)
        self.assertIn("Inner text.", html.stdout)
        self.assertNotIn("Inner</span>", html.stdout)

    def test_a_heading_in_a_fold_is_an_error(self):
        result = run_filter(HEADING, "json", scan=True)
        self.assertIn("heading inside a second-reading fold", result.stdout)

    def test_a_fold_alone_is_no_error(self):
        self.assertNotIn("COMPONENT_ERROR", run_filter(FOLD, "json", scan=True).stdout)


PAGE = r"""# Folds

::: {#thm-before}
Before the fold.
:::

The main line states the next result and folds its proof.

::: {#thm-folded-statement}
A statement on the main line.
:::

::: {.second-reading title="The proof, and a lemma it needs"}
::: {#lem-folded}
[Folded Lemma]

A lemma inside the fold, citing @thm-main.
:::

::: {.proof}
By @def-thing.
:::

The proof of @thm-folded-statement uses @lem-folded.

::: {.proof of="thm-folded-statement"}
Apply @lem-folded and @thm-before.
:::

A derivation in the fold:

```{=latex}
\begin{center}
$\begin{nd}
  \hypo {1} {P \wedge Q}
  \have {2} {Q} \ae{1}
\end{nd}$
\end{center}
```

Searchable folded word: zanzibarine.
:::

::: {#thm-after}
After the fold; see @lem-folded.
:::

## Exercises

::: {#exr-fold}
[Fold in a solution]

Show something.
:::

::: {.solution}
The short answer.

::: {.second-reading title="Edge cases"}
The degenerate case, citing @lem-folded.
:::
:::
"""


class TestSecondReadingBuild(FixtureBookCase):
    """A fixture book with a fold holding a labelled lemma, a proof and a derivation."""

    build_commands = [("all",)]

    @classmethod
    def prepare(cls, book_dir: Path):
        prepare_book(book_dir, {})        # ships fitch-book.sty, adds the exr environment
        (book_dir / "src" / "ch02-more" / "05-folds.md").write_text(PAGE)
        other = book_dir / "src" / "ch02-more" / "01-refs.md"
        other.write_text(other.read_text() + "\nA reference into a fold: @lem-folded.\n")

    def test_numbers_run_through_the_fold(self):
        labels = self.labels()
        numbers = [labels[k]["number"] for k in
                   ("thm-before", "thm-folded-statement", "lem-folded", "thm-after")]
        last = [int(n.rsplit(".", 1)[1]) for n in numbers]
        self.assertEqual(last, list(range(last[0], last[0] + 4)), numbers)
        self.assertEqual(labels["lem-folded"]["title"], "Folded Lemma")

    def test_dependencies_inside_the_fold_are_recorded(self):
        labels = self.labels()
        self.assertIn("def-thing", labels["lem-folded"]["uses"])                # its proof
        self.assertIn("thm-main", labels["lem-folded"]["uses"])                 # its statement
        self.assertEqual(sorted(labels["thm-folded-statement"]["uses"]), ["lem-folded", "thm-before"])
        self.assertIn("proof", labels["thm-folded-statement"]["uses_kinds"]["lem-folded"])

    def test_html_fold_holds_the_anchor_and_the_derivation(self):
        page = self.page("ch02-more/05-folds.html")
        self.assertEqual(page.count('<details class="second-reading">'), 2)
        fold = page[page.index('<details class="second-reading">'):page.index("</details>")]
        self.assertIn('id="lem-folded"', fold)
        self.assertIn('class="lemma env"', fold)
        self.assertIn('<div class="fitch" role="table"', fold)
        self.assertNotIn(r"\begin{nd}", page)
        self.assertNotIn("data-mjx-error", page)
        self.assertIn("<mjx-container", fold)          # math rendered inside the fold

    def test_fold_inside_a_solution(self):
        page = self.page("ch02-more/05-folds.html")
        solution = page[page.index('class="solution small-env"'):]
        self.assertIn('<details class="second-reading">', solution)
        self.assertIn('href="#lem-folded"', solution)

    def test_references_link_to_the_folded_label_and_preview_it(self):
        number = self.labels()["lem-folded"]["number"]
        refs = self.page("ch02-more/01-refs.html")
        self.assertIn('05-folds.html#lem-folded"', refs)
        self.assertIn(f"Lemma {number}", refs)
        preview = json.loads((self.html / "theorems" / "ch02-more" / "lem-folded.json").read_text())
        self.assertIn("citing", json.dumps(preview))

    def test_search_index_has_the_folded_text(self):
        index = json.loads((self.html / "search.json").read_text())
        self.assertTrue(any("zanzibarine" in entry["content"] for entry in index))

    def test_main_js_opens_folds_for_links(self):
        js = (self.html / "main.js").read_text()
        self.assertIn("function openFoldsAround", js)
        self.assertRegex(js, r"markTargetFromHash\(\) \{[^}]*openFoldsAround")

    def test_latex_prints_the_fold_inline(self):
        tex = (self.book.build_dir / "tmp" / "latex-book" / "book.tex").read_text()
        start = tex.index(r"\begin{booksecondreading}{1}{The proof, and a lemma it needs}")
        end = tex.index(r"\end{booksecondreading}", start)
        self.assertIn(r"\label{lem-folded}", tex[start:end])
        self.assertIn(r"\begin{nd}", tex[start:end])     # the PDF keeps fitch.sty
        self.assertIn(r"\begin{booksecondreading}{1}{Edge cases}", tex)

    def test_check_passes_and_pdf_numbers_match(self):
        result = run_build(self.book_dir, "check")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_rendered_output_is_clean(self):
        from tools import check_rendered
        errors, _ = check_rendered.find_violations(self.html, self.book.build_dir / "tmp", overfull=False)
        self.assertEqual(errors, [], check_rendered.report(errors))


class TestNestedFoldFailsCheck(FixtureBookCase):

    @classmethod
    def prepare(cls, book_dir: Path):
        refs = book_dir / "src" / "ch02-more" / "01-refs.md"
        refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))
        (book_dir / "src" / "ch02-more" / "05-nested.md").write_text("# Nested\n\n" + NESTED)

    def test_check_reports_the_nested_fold(self):
        result = run_build(self.book_dir, "check")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("inside another second-reading fold", result.stdout)


if __name__ == "__main__":
    unittest.main()
