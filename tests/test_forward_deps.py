"""Tests for tools/check_forward_deps.py, the gate against citing a later section.

The gate is kind-aware. A proof, a proof idea or a claim may not cite a result the
book proves later: the argument would not be finished where it stands. An example,
an exercise, a solution, a remark, a warning or a statement may -- that is a
signpost. A citation whose kind was never recorded is treated as load-bearing, because a gate
that cannot tell should stop rather than wave through.
"""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "check_forward_deps.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("check_forward_deps", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def label(file, number, kind="theorem", uses=(), uses_kinds=None):
    record = {"file": file, "number": number, "type": kind, "uses": list(uses)}
    if uses_kinds is not None:
        record["uses"] = sorted(uses_kinds)
        record["uses_kinds"] = {k: list(v) for k, v in uses_kinds.items()}
    return record


def run(labels):
    """Run the gate on a synthetic index; return (exit code, printed output)."""
    tool = load_tool()
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "crossref_labels.json"
        index.write_text(json.dumps({"crossref_labels": labels}))
        tool.INDEX = index
        out = io.StringIO()
        with redirect_stdout(out):
            code = tool.main()
    return code, out.getvalue()


class TestForwardDeps(unittest.TestCase):

    def test_backward_citation_passes(self):
        code, _ = run({
            "thm-early": label("ch01-a/02-x.html", "1.2.1"),
            "thm-late": label("ch03-b/01-y.html", "3.1.1", uses=["thm-early"]),
        })
        self.assertEqual(code, 0)

    def test_forward_citation_fails(self):
        code, out = run({
            "thm-early": label("ch01-a/02-x.html", "1.2.1", uses=["thm-late"]),
            "thm-late": label("ch03-b/01-y.html", "3.1.1"),
        })
        self.assertEqual(code, 1)
        self.assertIn("forward: thm-early", out)

    def test_dangling_citation_fails(self):
        code, out = run({
            "thm-a": label("ch01-a/01-x.html", "1.1.1", uses=["thm-missing"]),
        })
        self.assertEqual(code, 1)
        self.assertIn("dangling: thm-a", out)

    def test_gap_in_section_numbers_is_not_a_forward_citation(self):
        # Section 07 is not written yet, so the build numbers section 10's
        # results 16.9 while its file name still says 10. A result citing an
        # exercise in its own file must not be reported as forward. An earlier
        # version placed results by `number` and exercises by path, and failed.
        code, out = run({
            "cor-x": label("ch16-v/10-inertia.html", "16.9.2", uses=["exr-x-c1"]),
            "exr-x-c1": label("ch16-v/10-inertia.html", "", kind="exercise"),
        })
        self.assertEqual(code, 0, out)

    def test_forward_citation_across_a_gap_is_caught(self):
        # Section 06 citing section 09 across the missing 07 and 08: forward,
        # even though the positional numbers (16.6 and 16.7) sit side by side.
        code, out = run({
            "thm-six": label("ch16-v/06-a.html", "16.6.1", uses=["thm-nine"]),
            "thm-nine": label("ch16-v/09-b.html", "16.7.1"),
        })
        self.assertEqual(code, 1)
        self.assertIn("forward: thm-six", out)

    def test_same_section_is_unordered_not_an_error(self):
        # Labels sharing a section are not ordered by this tool, even when the
        # cited one has a larger third component.
        code, _ = run({
            "def-a": label("ch00-f/01-logic.html", "0.1.1", kind="definition"),
            "thm-a": label("ch00-f/01-logic.html", "0.1.1", uses=["def-b"]),
            "def-b": label("ch00-f/01-logic.html", "0.1.2", kind="definition"),
        })
        self.assertEqual(code, 0)

    def test_index_page_precedes_section_one(self):
        code, _ = run({
            "thm-intro": label("ch05-p/index.html", "5.0.1", uses=["thm-one"]),
            "thm-one": label("ch05-p/01-a.html", "5.1.1"),
        })
        self.assertEqual(code, 1)

    def test_lettered_chapter_directory_sorts_after_that_chapter(self):
        # `ch23a-notation` is an appendix to Chapter 23 and must keep its name:
        # `latex`/`theorems.lua` need it to read as chapter 23. Its index page
        # used to key as (23, 0) -- section zero -- so it sat *before* Chapter
        # 23's own sections, and a label put there would cite them "forward".
        tool = load_tool()
        self.assertGreater(
            tool.from_file("ch23a-notation/index.html"),
            tool.from_file("ch23-applied/12-last.html"),
        )
        code, out = run({
            "thm-notation": label("ch23a-notation/index.html", "23.0.1",
                                  uses=["thm-last"]),
            "thm-last": label("ch23-applied/12-last.html", "23.12.1"),
        })
        self.assertEqual(code, 0, out)

    def test_lettered_chapter_directory_still_cannot_cite_a_later_chapter(self):
        code, out = run({
            "thm-notation": label("ch23a-notation/index.html", "23.0.1",
                                  uses=["thm-later"]),
            "thm-later": label("ch24-x/01-a.html", "24.1.1"),
        })
        self.assertEqual(code, 1)
        self.assertIn("forward: thm-notation", out)



EARLY = "ch01-a/02-x.html"
LATE = "ch03-b/01-y.html"


def pointing(kind):
    """A one-result book in which the early label points forward from `kind`."""
    return {
        "thm-early": label(EARLY, "1.2.1", uses_kinds={"thm-late": [kind]}),
        "thm-late": label(LATE, "3.1.1"),
    }


class TestWhichKindsAreLoadBearing(unittest.TestCase):

    def test_a_proof_an_idea_and_a_claim_are_caught(self):
        for kind in ("proof", "idea", "claim", "proofofclaim"):
            tool = load_tool()
            violations = tool.find_violations(pointing(kind))
            self.assertEqual([(v[0], v[2], v[4]) for v in violations],
                             [("thm-early", "thm-late", (kind,))], kind)

    def test_a_signpost_is_not(self):
        """Prose pointing at what is coming is how the book is meant to be written."""
        for kind in ("example", "exercise", "solution", "remark", "warning",
                     "theorem", "proposition", "definition", "check"):
            tool = load_tool()
            self.assertEqual(tool.find_violations(pointing(kind)), [], kind)

    def test_an_unrecorded_kind_is_treated_as_load_bearing(self):
        tool = load_tool()
        book = {"thm-early": label(EARLY, "1.2.1", uses=["thm-late"]),
                "thm-late": label(LATE, "3.1.1")}
        self.assertEqual([v[0] for v in tool.find_violations(book)], ["thm-early"])

    def test_a_solution_is_load_bearing_for_optional_but_not_for_forward(self):
        """The two gates differ on purpose, and the difference is recorded in both."""
        tool = load_tool()
        self.assertNotIn("solution", tool.LOAD_BEARING)
        self.assertEqual(tool.find_violations(pointing("solution")), [])

    def test_a_backward_proof_citation_is_never_a_violation(self):
        tool = load_tool()
        book = {"thm-early": label(EARLY, "1.2.1"),
                "thm-late": label(LATE, "3.1.1", uses_kinds={"thm-early": ["proof"]})}
        self.assertEqual(tool.find_violations(book), [])

    def test_a_mixed_citation_is_caught_and_reports_only_the_guilty_kind(self):
        tool = load_tool()
        book = {"thm-early": label(EARLY, "1.2.1",
                                   uses_kinds={"thm-late": ["remark", "proof"]}),
                "thm-late": label(LATE, "3.1.1")}
        violations = tool.find_violations(book)
        self.assertEqual([v[4] for v in violations], [("proof",)])

    def test_the_report_names_the_citing_site(self):
        tool = load_tool()
        report = tool.report(tool.find_violations(pointing("idea")))
        self.assertIn("ch01-a/02-x", report)
        self.assertIn("thm-early cites thm-late in its idea", report)
        self.assertIn("is proved later", report)
        self.assertIn("ch03-b/01-y", report)


class TestCommandLine(unittest.TestCase):

    def test_a_signpost_does_not_fail_the_run(self):
        code, out = run(pointing("example"))
        self.assertEqual(code, 0, out)
        self.assertIn("No proof cites a later section", out)
        self.assertIn("1 forward pointers are signposts and stay", out)

    def test_a_proof_pointing_forward_does(self):
        code, out = run(pointing("proof"))
        self.assertEqual(code, 1)
        self.assertIn("forward: thm-early", out)
        self.assertIn("in its proof", out)
        self.assertIn("1 load-bearing forward", out)

    def test_signposts_can_be_listed(self):
        import sys as _sys
        argv = _sys.argv
        _sys.argv = ["check_forward_deps.py", "--signposts"]
        try:
            code, out = run(pointing("remark"))
        finally:
            _sys.argv = argv
        self.assertEqual(code, 0, out)
        self.assertIn("signpost: thm-early", out)


class TestAgainstTheRealBook(unittest.TestCase):
    """Skipped unless the book has been built. The gate, on the book itself."""

    def setUp(self):
        index = Path(__file__).resolve().parent.parent / "_build" / "crossref_labels.json"
        if not index.exists():
            self.skipTest("run ./build.py html first")
        self.tool = load_tool()
        self.labels = json.loads(index.read_text(encoding="utf-8"))["crossref_labels"]

    def test_no_proof_in_the_book_points_forward(self):
        violations = self.tool.find_violations(self.labels)
        self.assertEqual(violations, [], self.tool.report(violations))

    def test_the_signposts_are_all_soft(self):
        """Forward pointers are allowed as signposts (examples, remarks, exercises), never
        as steps of a proof. (The regression book also pinned their count; this book is too
        young to have a count worth pinning.)"""
        order = self.tool.place(self.labels)
        rows = self.tool.forward_citations(self.labels, order)
        self.assertTrue(all(not row[3] for row in rows))


if __name__ == "__main__":
    unittest.main()
