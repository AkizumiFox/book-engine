"""
End-to-end tests: build tests/fixture-book with the engine and inspect the output.

Run from the project root:  python3 -m unittest discover -s tests
The book builds need pandoc, pdflatex and pdftocairo (see ./build.py doctor).
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixture-book"
sys.path.insert(0, str(ENGINE_ROOT))

from build.book import Book  # noqa: E402
from build.check import check_xref_links  # noqa: E402
from build.extras import _implied_edges  # noqa: E402
from tools import check_optional  # noqa: E402
from tools import reading_path  # noqa: E402


def run_build(book_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENGINE_ROOT / "build.py"), *args, "--book", str(book_dir)],
        capture_output=True, text=True,
    )


class TestTransitiveReduction(unittest.TestCase):
    """The chapter graph drops dependencies that a longer chain already implies."""

    def test_drops_the_shortcut(self):
        counts = {("a", "b"): 3, ("b", "c"): 4, ("a", "c"): 9}
        self.assertEqual(_implied_edges(counts), {("a", "c")})

    def test_keeps_a_dependency_no_path_implies(self):
        counts = {("a", "b"): 1, ("a", "c"): 1}
        self.assertEqual(_implied_edges(counts), set())

    def test_drops_a_shortcut_over_a_long_chain(self):
        counts = {("a", "b"): 1, ("b", "c"): 1, ("c", "d"): 1, ("a", "d"): 1, ("b", "d"): 1}
        self.assertEqual(_implied_edges(counts), {("a", "d"), ("b", "d")})

    def test_a_cycle_leaves_every_edge_drawn(self):
        counts = {("a", "b"): 1, ("b", "a"): 1, ("b", "c"): 1}
        self.assertEqual(_implied_edges(counts), set())


class FixtureBookCase(unittest.TestCase):
    """Copies the fixture book to a temporary directory and builds it once per class."""

    build_commands = [("html",)]

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="book-test-")
        cls.book_dir = Path(cls.tmp.name) / "book"
        shutil.copytree(FIXTURE, cls.book_dir)
        cls.prepare(cls.book_dir)
        cls.results = {}
        for command in cls.build_commands:
            result = run_build(cls.book_dir, *command)
            cls.results[command] = result
            if result.returncode != 0:
                raise AssertionError(f"build {command} failed:\n{result.stdout}\n{result.stderr}")
        cls.book = Book(cls.book_dir)
        cls.html = cls.book.html_dir

    @classmethod
    def prepare(cls, book_dir: Path):
        pass

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def page(self, path: str) -> str:
        return (self.html / path).read_text(encoding="utf-8")

    def labels(self) -> dict:
        return json.loads(self.book.labels_file.read_text())["crossref_labels"]


BROKEN_COMPONENTS = """# Broken Components

::: {.plot fn="sin(2x)"}
:::

::: {.widget src="widgets/missing.js"}
No print block.
:::
"""


class TestHtmlBuild(FixtureBookCase):

    @classmethod
    def prepare(cls, book_dir: Path):
        (book_dir / "src" / "ch02-more" / "03-broken.md").write_text(BROKEN_COMPONENTS)

    def test_numbering_shared_and_independent_counters(self):
        numbers = {k: v["number"] for k, v in self.labels().items()}
        self.assertEqual(numbers["def-thing"], "1.1.1")     # own counter
        self.assertEqual(numbers["thm-main"], "1.1.1")      # "main" counter
        self.assertEqual(numbers["lem-helper"], "1.1.2")    # shares "main" with theorems
        self.assertEqual(numbers["eq-sum"], "1.1.1")
        # A tagged display sharing its paragraph with prose must not swallow that prose:
        # the filter once returned only the equation, silently deleting the rest.
        self.assertEqual(numbers["eq-inline-tagged"], "1.1.2")
        page = self.page("ch01-basics/01-first.html")
        self.assertIn("Prose before the tagged display must survive", page)
        self.assertIn("and so must prose after it", page)
        self.assertEqual(numbers["thm-second"], "1.2.1")    # counters restart per section
        self.assertEqual(numbers["exm-titled"], "")         # unnumbered

    def test_cross_chapter_reference(self):
        page = self.page("ch02-more/01-refs.html")
        self.assertRegex(page, r'href="\.\./ch01-basics/01-first\.html#thm-main"')
        self.assertIn('data-shard="ch01-basics"', page)
        self.assertIn("Theorem 1.1.1", page)

    def test_unnumbered_reference_uses_title(self):
        self.assertIn("Example (Titled Example)", self.page("ch02-more/01-refs.html"))

    def test_all_reference_links_resolve(self):
        self.assertEqual(check_xref_links(self.html), [])

    def test_nested_environments(self):
        page = self.page("ch01-basics/01-first.html")
        proof = page.index('class="proof small-env"')
        claim = page.index('class="claim small-env"')
        self.assertLess(proof, claim)

    def test_tikz_figure(self):
        page = self.page("ch01-basics/01-first.html")
        match = re.search(r'src="\.\./tikz/([0-9a-f]{40})\.svg"', page)
        self.assertIsNotNone(match, "no TikZ image in page")
        self.assertTrue((self.html / "tikz" / f"{match.group(1)}.svg").exists())

    def test_labeled_list(self):
        page = self.page("ch01-basics/01-first.html")
        self.assertIn(">(A1)</span>", page)
        self.assertIn(">(A2)</span>", page)

    def test_chapter_titles_and_navigation(self):
        navigation = json.loads((self.html / "navigation.json").read_text())
        self.assertEqual([c["title"] for c in navigation["chapters"]], ["Basics", "More Topics"])
        self.assertEqual(navigation["home"], {"title": "Preface", "path": "index.html"})
        self.assertEqual(navigation["chapters"][0]["sections"][1]["number"], "1.2")
        self.assertEqual([c["part"] for c in navigation["chapters"]], ["", "Part Two"])
        self.assertNotIn("{.unnumbered}", self.page("ch02-more/index.html"))

    def test_teaching_blocks(self):
        page = (self.html / "ch02-more" / "01-refs.html").read_text()
        self.assertIn('class="warning small-env"', page)
        self.assertIn('class="check small-env"', page)
        self.assertIn("Quick check", page)

    def test_tooltip_shards(self):
        # One file per result, so a hover fetches kilobytes rather than a whole chapter
        entry = json.loads((self.html / "theorems" / "ch01-basics" / "thm-main.json").read_text())
        self.assertEqual(entry["title"], "Main Theorem")
        self.assertTrue((self.html / "theorems" / "ch02-more" / "exm-titled.json").exists())
        # A result that no longer exists must not be left behind for the tooltips to find
        self.assertFalse(list((self.html / "theorems").glob("*.json")))

    def test_macros_generated_from_book(self):
        macros = (self.html / "mathjax-macros.js").read_text()
        self.assertIn('"nR": "\\\\mathbb{R}"', macros)
        self.assertIn('"norm": [', macros)
        self.assertIn('"codim": "\\\\operatorname{codim}"', macros)

    def test_search_index(self):
        index = json.loads((self.html / "search.json").read_text())
        entry = next(e for e in index if e["url"] == "ch01-basics/02-second.html")
        self.assertEqual(entry["title"], "1.2 Second Section")
        self.assertIn("builds on", entry["content"])

    def test_search_index_has_results(self):
        index = json.loads((self.html / "search.json").read_text())
        result = next(e for e in index if e["url"] == "ch01-basics/01-first.html#thm-main")
        self.assertEqual(result["kind"], "result")
        self.assertEqual(result["title"], "Theorem 1.1.1 (Main Theorem)")
        self.assertEqual(result["page"], "1.1 First Section")
        page = next(e for e in index if e["url"] == "ch01-basics/02-second.html")
        self.assertEqual(page["title"], "1.2 Second Section")

    def test_page_metadata_and_site_files(self):
        page = self.page("ch01-basics/index.html")
        self.assertIn('<meta name="description" content="The first chapter.">', page)
        self.assertIn('rel="icon" href="../favicon.svg"', page)
        self.assertNotIn('rel="canonical"', page)            # no deploy-domain in the fixture
        self.assertTrue((self.html / "favicon.svg").exists())
        self.assertIn("Page not found", (self.html / "404.html").read_text())
        self.assertFalse((self.html / "sitemap.xml").exists())

    def test_tikz_svg_scaled_for_the_web(self):
        svg = next((self.html / "tikz").glob("*.svg")).read_text()
        width = float(re.search(r'<svg[^>]*\bwidth="([\d.]+)"', svg).group(1))
        view_width = float(re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+)', svg).group(1))
        self.assertAlmostEqual(width / view_width, 1.5, places=2)

    def test_results_page_and_graph(self):
        results = self.page("results.html")
        self.assertIn('data-ref="thm-main"', results)
        self.assertIn('href="ch01-basics/01-first.html#thm-main"', results)
        self.assertIn("Main Theorem", results)
        # The graph is chapter-level: nodes are chapters, edges count the citations made
        # *inside a result*. Chapter 2 §01's opening prose names three of Chapter 1's
        # results and that is deliberately not an edge -- counting prose is what made the
        # old graph nearly complete. The one edge comes from §02's proof of thm-area.
        graph = json.loads((self.html / "graph.json").read_text())
        self.assertEqual([n["id"] for n in graph["nodes"]], ["ch01-basics", "ch02-more"])
        self.assertTrue(any(e["source"] == "ch01-basics" and e["target"] == "ch02-more" and e["weight"] >= 1
                            for e in graph["edges"]), graph["edges"])
        # and the remark beside it is carried as a soft citation, not as a dependency
        self.assertTrue(any(e["soft"] >= 1 for e in graph["edges"]), graph["edges"])
        self.assertTrue(all(e["source"] != e["target"] for e in graph["edges"]))
        # Only the transitive reduction is drawn; the rest carry implied = true
        self.assertTrue(all("implied" in e for e in graph["edges"]), graph["edges"])
        self.assertIn('data-graph="graph.json"', self.page("graph.html"))
        self.assertIn("graph.js?v=", self.page("graph.html"))
        navigation = json.loads((self.html / "navigation.json").read_text())
        self.assertEqual([e["path"] for e in navigation["extras"]],
                         ["paths.html", "results.html", "graph.html"])

    def test_graph_data_carries_the_closures_the_picker_needs(self):
        """A reader picks a target; the graph looks its closure up rather than walking."""
        graph = json.loads((self.html / "graph.json").read_text())
        self.assertEqual(graph["total"], 4)
        self.assertEqual([p["slug"] for p in graph["profiles"]], ["example"])
        closure = graph["closures"]["ch01-basics/02"]
        self.assertEqual(closure["n"], 2)                   # 01 and 02 of Chapter 1
        self.assertEqual(closure["chapters"], {"0": 2})     # keyed by chapter position
        self.assertLessEqual(closure["n"], closure["nx"])   # exercises never shorten a path
        # Soft citations are carried alongside the hard ones rather than drawn
        self.assertTrue(all("soft" in e and "weight" in e for e in graph["edges"]))

    def test_reading_path_pages_are_generated_and_closed(self):
        index = self.page("paths.html")
        self.assertIn('href="path-example.html"', index)
        self.assertIn("An example reader", index)
        page = self.page("path-example.html")
        self.assertIn('href="ch01-basics/01-first.html"', page)
        self.assertIn('href="ch01-basics/02-second.html"', page)
        self.assertIn("2 of the book's 4 sections", index + page)
        # The path a reader is handed must contain its own prerequisites
        graph = reading_path.graph_from_labels(self.labels())
        closure = graph.closure(["ch01-basics/02"])
        self.assertTrue(graph.is_closed(closure), graph.is_closed(closure).report())

    def test_citation_kinds_recorded_beside_uses(self):
        """`uses` keeps its flat shape; `uses_kinds` says which block made each citation.

        thm-second cites thm-main in its statement, def-thing in its proof and
        lem-helper in a remark. Only the proof citation is a hard dependency:
        drop def-thing and thm-second is unproved, drop lem-helper and a
        sentence needs rewording.
        """
        record = self.labels()["thm-second"]
        self.assertEqual(sorted(record["uses"]), ["def-thing", "lem-helper", "thm-main"])
        self.assertEqual(record["uses_kinds"], {
            "thm-main": ["theorem"],        # the statement's own environment
            "def-thing": ["proof"],
            "lem-helper": ["remark"],
        })
        # every cited label is accounted for, in both directions
        for info in self.labels().values():
            self.assertEqual(set(info["uses_kinds"]), set(info["uses"]))

    def test_an_optional_result_says_so_and_is_recorded(self):
        """`::: {#thm-aside .optional}`: a marker on the page, a flag on the label."""
        page = self.page("ch02-more/01-refs.html")
        self.assertIn('class="theorem env optional"', page)
        # pandoc wraps the page's HTML, so match across the line breaks
        self.assertRegex(page, r'class="env-optional">Optional:\s+nothing\s+later\s+depends\s+on\s+'
                               r'this\.</span>')
        self.assertTrue(self.labels()["thm-aside"]["optional"])
        # and nothing else in the fixture carries the flag
        self.assertEqual([name for name, info in self.labels().items() if info.get("optional")],
                         ["thm-aside"])

    def test_an_optional_results_citations_are_not_prerequisites(self):
        """thm-aside's proof cites lem-helper in Chapter 1, and that pulls nothing in.

        Nothing requires thm-aside, so nothing can be required through it. The soft
        view still shows Chapter 1 as context, and the remark in §02 that points at
        thm-aside is the way an optional result is meant to be referred to.
        """
        graph = reading_path.graph_from_labels(self.labels())
        self.assertEqual(graph.optional, frozenset({"thm-aside"}))
        hard = graph.closure(["ch02-more/01"])
        self.assertEqual(hard.sections, ["ch02-more/01"])
        self.assertIn("ch01-basics/01", graph.closure(["ch02-more/01"], hard_only=False).sections)
        self.assertTrue(graph.is_closed(hard), graph.is_closed(hard).report())

    def test_check_fails_when_a_proof_leans_on_an_optional_result(self):
        labels = self.labels()
        labels["thm-area"]["uses"] = sorted(set(labels["thm-area"]["uses"]) | {"thm-aside"})
        labels["thm-area"]["uses_kinds"]["thm-aside"] = ["proof"]
        violations = check_optional.find_violations(labels)
        self.assertEqual([v[0] for v in violations], ["thm-area"])
        self.assertIn("marked optional", check_optional.report(violations))

    def test_reading_path_uses_the_built_index(self):
        """The section graph over the fixture: a proof edge is hard, a remark edge is not."""
        graph = reading_path.graph_from_labels(self.labels())
        hard = graph.closure(["ch01-basics/02"])
        self.assertEqual(hard.sections, ["ch01-basics/01", "ch01-basics/02"])
        self.assertTrue(graph.is_closed(hard))
        self.assertEqual(graph.unknown_kinds, 0)

    def test_title_mentions_become_dependencies(self):
        labels = self.labels()
        # 02-second.md references thm-main explicitly, so it is a use, not a mention
        self.assertIn("thm-main", labels["thm-second"]["uses"])
        self.assertNotIn("thm-main", labels["thm-second"]["mentions"])

    def test_figure_alt_text(self):
        page = self.page("ch01-basics/01-first.html")
        self.assertRegex(page, r'class="tikz"\s+alt="Diagram\. Labels: x"')

    def test_math_rendered_at_build_time(self):
        if not shutil.which("node"):
            self.skipTest("node not installed")
        page = self.page("ch01-basics/01-first.html")
        self.assertIn("<mjx-container", page)
        self.assertNotIn("tex-chtml-full.js", page)                  # no MathJax script
        self.assertIn('href="../mathjax.css?v=', page)
        self.assertNotIn('data-mjx-error', page)
        self.assertTrue((self.html / "mathjax.css").exists())
        self.assertTrue(any((self.html / "mathjax-fonts").glob("*.woff")))
        entry = (self.html / "theorems" / "ch01-basics" / "thm-main.json").read_text()
        self.assertIn("mjx-container", entry)                         # tooltip previews too

    def test_unchanged_rebuild_skips_pages(self):
        result = run_build(self.book_dir, "html")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("0/0 built", result.stdout)

    def test_check_reports_broken_reference(self):
        result = run_build(self.book_dir, "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unresolved reference @thm-missing in src/ch02-more/01-refs.md", result.stdout)

    def test_check_reports_broken_components(self):
        result = run_build(self.book_dir, "check")
        self.assertIn('plot fn="sin(2x)" in src/ch02-more/03-broken.md: missing \'*\' before \'x\'', result.stdout)
        self.assertIn("widget file not found: widgets/missing.js", result.stdout)
        self.assertIn("has no ::: {.print} content", result.stdout)

    # -- Interactive components ------------------------------------------------

    def test_code_cells(self):
        page = self.page("ch02-more/02-interactive.html")
        self.assertRegex(page, r'<div id="cell-matrix" class="code-cell"\s+data-lang="python"')
        self.assertEqual(page.count('class="code-cell-run"'), 2)
        self.assertIn('class="sourceCode python"', page)          # the plain listing is not a cell
        self.assertIn("<style>", page)                             # highlighting CSS is included

    def test_components_script_only_where_used(self):
        self.assertIn("components.js?v=", self.page("ch02-more/02-interactive.html"))
        self.assertNotIn("components.js", self.page("ch02-more/01-refs.html"))
        for name in ("cell.js", "pyodide-worker.js", "plot.js", "expression.js", "widget.js", "jsxgraph.js"):
            self.assertTrue((self.html / "components" / name).exists(), name)
        self.assertTrue((self.html / "widgets" / "linear-map.js").exists())

    def test_plot_and_widget_html(self):
        page = self.page("ch02-more/02-interactive.html")
        self.assertIn('data-fn="sin(a*x); a*cos(x)/2"', page)
        self.assertIn('data-params="a=1:0..3"', page)
        self.assertIn('class="plot-caption"', page)
        self.assertIn('data-src="../widgets/linear-map.js"', page)
        self.assertIn('class="widget-fallback"', page)


class TestFullBuild(FixtureBookCase):
    """Without the broken reference, the whole book builds and check passes, which
    includes comparing every label number in the PDFs with the website."""

    build_commands = [("all",)]

    @classmethod
    def prepare(cls, book_dir: Path):
        refs = book_dir / "src" / "ch02-more" / "01-refs.md"
        refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))

    def test_check_passes(self):
        result = run_build(self.book_dir, "check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Check passed", result.stdout)

    def test_pdfs_exist(self):
        self.assertTrue(self.book.book_pdf.exists())
        self.assertTrue((self.book.pdf_dir / "ch01-basics" / "01-first.pdf").exists())
        self.assertTrue((self.html / "book" / "book.pdf").exists())

    def test_pdf_components(self):
        tex = (self.book.build_dir / "tmp" / "pdf-single" / "ch02-more" / "02-interactive.tex").read_text()
        self.assertEqual(tex.count(r"\begin{lstlisting}[language=Python]"), 2)
        self.assertIn(r"\addplot[thick, blue] {sin(((1)*x))};", tex)       # parameter at its default
        self.assertIn(r"\addplot[thick, blue] {((x^3)-(3*x))};", tex)
        self.assertIn("parallelogram spanned by the columns", tex)          # widget print content
        self.assertNotIn("widget-mount", tex)

    def test_pdf_reference_text(self):
        tex = (self.book.build_dir / "tmp" / "latex-book" / "book.tex").read_text()
        self.assertIn(r"\hyperref[thm-main]{Theorem~\ref*{thm-main}}", tex)
        self.assertIn(r"\begin{enumerate}[label=(A\arabic*)]", tex)

    def test_pdf_accented_names_survive_the_shorthands(self):
        """\\H, \\o, \\r, \\v are both text accents and bold-vector shorthands: in prose they stay accents."""
        log = (self.book.build_dir / "tmp" / "latex-book" / "book.log").read_text(errors="replace")
        self.assertNotIn("allowed only in math mode", log)

    def test_pdf_optional_marker(self):
        """The printed edition makes the same promise as the web one, inside the box."""
        tex = (self.book.build_dir / "tmp" / "latex-book" / "book.tex").read_text()
        self.assertIn("\\begin{theorem}[{An Aside}]\\label{thm-aside}\n\n\\bookoptionalnote", tex)
        self.assertEqual(tex.count(r"\bookoptionalnote"), 1)
        section = (self.book.build_dir / "tmp" / "pdf-single" / "ch02-more" / "01-refs.tex").read_text()
        self.assertIn(r"\bookoptionalnote", section)


class TestForwardProofFailsCheck(FixtureBookCase):
    """A proof in Chapter 1 citing a Chapter 2 result fails `check`; a remark does not."""

    @classmethod
    def prepare(cls, book_dir: Path):
        refs = book_dir / "src" / "ch02-more" / "01-refs.md"
        refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))
        second = book_dir / "src" / "ch01-basics" / "02-second.md"
        second.write_text(second.read_text().replace(
            "Immediate from @def-thing.", "Immediate from @def-thing and @thm-area."
        ).replace("Compare @lem-helper.", "Compare @lem-helper and, later, @thm-aside."))

    def test_the_proof_is_reported_and_the_remark_is_not(self):
        result = run_build(self.book_dir, "check")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("thm-second cites thm-area in its proof", result.stdout)
        self.assertNotIn("thm-aside is proved later", result.stdout)


class TestSiteUrl(FixtureBookCase):
    """`site-url`: a book published under a sub-path of a shared origin (a library)."""

    @classmethod
    def prepare(cls, book_dir: Path):
        config = json.loads((book_dir / "book.json").read_text())
        config["site-url"] = "https://books.example.com/fixture"
        config["deploy-domain"] = "ignored.example.com"
        (book_dir / "book.json").write_text(json.dumps(config, indent=2))

    def test_site_url_and_path(self):
        self.assertEqual(self.book.site_url, "https://books.example.com/fixture/")
        self.assertEqual(self.book.site_path, "/fixture/")

    def test_canonical_links_use_the_sub_path(self):
        page = self.page("ch01-basics/01-first.html")
        self.assertIn('rel="canonical" href="https://books.example.com/fixture/ch01-basics/01-first.html"', page)
        self.assertIn('href="../styles.css', page)               # the page itself stays relative

    def test_sitemap_but_no_robots_under_a_sub_path(self):
        sitemap = (self.html / "sitemap.xml").read_text()
        self.assertIn("<loc>https://books.example.com/fixture/index.html</loc>", sitemap)
        self.assertNotIn("ignored.example.com", sitemap)
        self.assertFalse((self.html / "robots.txt").exists())

    def test_404_links_from_the_sub_path(self):
        page = (self.html / "404.html").read_text()
        self.assertIn('href="/fixture/styles.css"', page)
        self.assertIn('href="/fixture/index.html"', page)

    def test_deploy_domain_alone_is_the_root(self):
        book = Book(self.book_dir)
        book.config.pop("site-url")
        self.assertEqual(book.site_url, "https://ignored.example.com/")
        self.assertEqual(book.site_path, "/")


if __name__ == "__main__":
    unittest.main()
