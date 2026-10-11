"""Tests for tools/check_optional.py, the promise an optional result makes.

A result marked `::: {#thm-foo .optional}` prints "nothing later depends on this"
in both editions, and `tools/reading_path.py` believes it: none of its citations
is a prerequisite, so it drags no section onto anybody's reading path. The promise
holds only while no proof anywhere leans on it, and that is what is tested here --
the violation must be found, named with its citing site, and must fail the build.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import check_optional  # noqa: E402
from tools import reading_path  # noqa: E402
from tools.reading_path import graph_from_labels  # noqa: E402


def label(file, uses_kinds, optional=False, kind="theorem"):
    record = {"file": file, "number": "1.1.1", "type": kind, "title": "",
              "uses": sorted(uses_kinds),
              "uses_kinds": {k: list(v) for k, v in uses_kinds.items()}}
    if optional:
        record["optional"] = True
    return record


# thm-aside is the illustration: proved from def-far over in Chapter 4, cited by a
# remark (fine) and by nothing that proves anything (the invariant).
BOOK = {
    "def-near": label("ch01-start/01-first.html", {}, kind="definition"),
    "def-far": label("ch04-other/01-far.html", {}, kind="definition"),
    "thm-aside": label("ch02-middle/01-one.html",
                       {"def-far": ["proof"], "def-near": ["theorem"]}, optional=True),
    "thm-real": label("ch02-middle/01-one.html", {"def-near": ["proof"]}),
    "rmk-owner": label("ch03-late/01-one.html", {"thm-aside": ["remark"]}),
}


class TestTheInvariant(unittest.TestCase):

    def test_a_clean_book_has_no_violations(self):
        self.assertEqual(check_optional.find_violations(BOOK), [])

    def test_a_proof_leaning_on_an_optional_result_is_caught(self):
        guilty = dict(BOOK, **{
            "thm-later": label("ch03-late/01-one.html", {"thm-aside": ["proof"]})})
        violations = check_optional.find_violations(guilty)
        self.assertEqual([(v[0], v[2], v[4]) for v in violations],
                         [("thm-later", "thm-aside", ("proof",))])

    def test_the_report_names_the_citing_site(self):
        guilty = dict(BOOK, **{
            "thm-later": label("ch03-late/01-one.html", {"thm-aside": ["idea", "proof"]})})
        report = check_optional.report(check_optional.find_violations(guilty))
        self.assertIn("ch03-late/01-one", report)
        self.assertIn("thm-later", report)
        self.assertIn("thm-aside", report)
        self.assertIn("idea, proof", report)
        self.assertIn("marked optional", report)

    def test_a_remark_or_a_statement_may_cite_an_optional_result(self):
        """That is what an optional result is for: a connection, pointed at in prose."""
        for kind in ("remark", "theorem", "warning", "check", "exercise"):
            book = dict(BOOK, **{"x": label("ch03-late/01-one.html", {"thm-aside": [kind]})})
            self.assertEqual(check_optional.find_violations(book), [], kind)

    def test_a_written_solution_counts_as_a_proof(self):
        """A solution is printed in the book, so its reader may not be sent to a gap."""
        book = dict(BOOK, **{"exr-x": label("ch03-late/01-one.html",
                                            {"thm-aside": ["solution"]}, kind="exercise")})
        self.assertEqual([v[0] for v in check_optional.find_violations(book)], ["exr-x"])
        self.assertIn("solution", reading_path.EXERCISE_KINDS)

    def test_a_claim_inside_a_proof_counts(self):
        book = dict(BOOK, **{"thm-x": label("ch03-late/01-one.html",
                                            {"thm-aside": ["claim"]})})
        self.assertEqual([v[0] for v in check_optional.find_violations(book)], ["thm-x"])

    def test_a_book_with_nothing_optional_is_never_a_violation(self):
        plain = {name: {k: v for k, v in rec.items() if k != "optional"}
                 for name, rec in BOOK.items()}
        self.assertEqual(check_optional.find_violations(plain), [])


class TestPathSemantics(unittest.TestCase):
    """The other half: what the marker buys, and that it buys it honestly."""

    def test_an_optional_results_proof_citation_is_not_a_prerequisite(self):
        graph = graph_from_labels(BOOK)
        self.assertEqual(graph.closure(["ch02-middle/01"]).sections,
                         ["ch01-start/01", "ch02-middle/01"])

    def test_without_the_marker_the_same_citation_pulls_a_chapter_in(self):
        required = dict(BOOK, **{
            "thm-aside": label("ch02-middle/01-one.html",
                               {"def-far": ["proof"], "def-near": ["theorem"]})})
        graph = graph_from_labels(required)
        self.assertIn("ch04-other/01", graph.closure(["ch02-middle/01"]).sections)

    def test_the_section_is_still_context_on_the_soft_view(self):
        """Soft edges are untouched: a reader who wants the connection can still find it."""
        graph = graph_from_labels(BOOK)
        self.assertIn("ch04-other/01",
                      graph.closure(["ch02-middle/01"], hard_only=False).sections)

    def test_the_path_is_still_closed(self):
        graph = graph_from_labels(BOOK)
        path = graph.closure(["ch02-middle/01"])
        self.assertTrue(graph.is_closed(path), graph.is_closed(path).report())

    def test_optional_holds_whatever_the_exercise_policy(self):
        """An optional result is optional for the reader who works the problems too."""
        book = dict(BOOK, **{
            "thm-aside": label("ch02-middle/01-one.html",
                               {"def-far": ["proof", "solution"]}, optional=True)})
        for kinds in (reading_path.HARD_KINDS, reading_path.EXERCISE_KINDS):
            graph = graph_from_labels(book, hard_kinds=kinds)
            self.assertNotIn("ch04-other/01", graph.closure(["ch02-middle/01"]).sections)

    def test_the_graph_names_what_is_optional(self):
        self.assertEqual(graph_from_labels(BOOK).optional, frozenset({"thm-aside"}))

    def test_a_citation_says_it_came_from_an_optional_result(self):
        graph = graph_from_labels(BOOK)
        sites = {c.site() for c in graph.citations if c.citing == "thm-aside"}
        self.assertTrue(all("[optional]" in site for site in sites), sites)


class TestCommandLine(unittest.TestCase):

    def run_cli(self, labels, *argv):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "crossref_labels.json"
            index.write_text(json.dumps({"crossref_labels": labels}))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = check_optional.main(["--index", str(index), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_a_clean_book_passes(self):
        code, out, _ = self.run_cli(BOOK)
        self.assertEqual(code, 0)
        self.assertIn("No proof rests on an optional result", out)
        self.assertIn("1 marked optional", out)

    def test_a_violation_fails_with_the_sites(self):
        guilty = dict(BOOK, **{
            "thm-later": label("ch03-late/01-one.html", {"thm-aside": ["proof"]})})
        code, out, _ = self.run_cli(guilty)
        self.assertEqual(code, 1)
        self.assertIn("thm-later cites thm-aside in its proof", out)
        self.assertIn("1 proof(s) rest on a result marked optional", out)

    def test_list_prints_what_is_marked(self):
        code, out, _ = self.run_cli(BOOK, "--list")
        self.assertEqual(code, 0)
        self.assertIn("thm-aside", out)
        self.assertIn("1 results are marked optional", out)

    def test_a_missing_index_fails_cleanly(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check_optional.main(["--index", "/nonexistent/labels.json"])
        self.assertEqual(code, 1)
        self.assertIn("run ./build.py html first", err.getvalue())


if __name__ == "__main__":
    unittest.main()
