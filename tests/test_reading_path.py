"""Tests for tools/reading_path.py, the section-level "what do I need to read?" graph.

The property under test is **closure**: every hard dependency of every section
on a path is itself on the path. A path that is not closed sends a reader into
a gap, which is the failure the tool exists to prevent, so it is checked on a
graph built to break a naive implementation -- a chain, a diamond, a soft edge
that must not pull anything in, and a hard edge hiding behind a soft one.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import reading_path  # noqa: E402
from tools.reading_path import graph_from_labels  # noqa: E402


def label(file, uses_kinds, number="1.1.1", kind="theorem"):
    """A crossref_labels record: `uses` is the flat list, `uses_kinds` the split."""
    return {"file": file, "number": number, "type": kind,
            "uses": sorted(uses_kinds), "uses_kinds": {k: list(v) for k, v in uses_kinds.items()}}


# A small book, laid out so that reading order and citation direction agree.
#
#   ch01/01  def-a                     (no dependencies)
#   ch01/02  thm-b   proof cites def-a                  hard  01 <- 02
#   ch02/01  thm-c   proof cites thm-b                  hard  02 <- ch02/01
#            thm-c2  remark cites def-a                 soft
#   ch02/02  thm-d   statement cites thm-c              soft only
#   ch03/01  thm-e   proof cites thm-d, remark cites thm-f
#   ch03/02  thm-f   proof cites def-g
#   ch04/01  def-g                                      reachable only through thm-f
BOOK = {
    "def-a": label("ch01-start/01-first.html", {}, kind="definition"),
    "thm-b": label("ch01-start/02-second.html", {"def-a": ["proof"]}),
    "thm-c": label("ch02-middle/01-one.html", {"thm-b": ["proof"]}),
    "thm-c2": label("ch02-middle/01-one.html", {"def-a": ["remark"]}),
    "thm-d": label("ch02-middle/02-two.html", {"thm-c": ["theorem"]}),
    "thm-e": label("ch03-late/01-one.html", {"thm-d": ["proof"], "thm-f": ["remark"]}),
    "thm-f": label("ch03-late/02-two.html", {"def-g": ["proof"]}),
    "def-g": label("ch04-end/01-one.html", {}, kind="definition"),
}

# The same book with one exercise added to ch02/02, whose written solution leans on
# def-g over in ch04. A solution is the proof of its exercise, so that citation is
# hard for a reader who works the exercises and soft for one who does not, which is
# the whole distinction the two published variants of every path rest on.
EXERCISE_BOOK = dict(
    BOOK, **{"exr-h": label("ch02-middle/02-two.html", {"def-g": ["solution"]},
                            kind="exercise")})


class TestSectionKeys(unittest.TestCase):

    def test_section_id_from_a_file_name(self):
        self.assertEqual(reading_path.section_of("ch12-psd-and-svd/08-svd.html"),
                         "ch12-psd-and-svd/08")
        self.assertEqual(reading_path.section_of("ch05-poly/index.html"), "ch05-poly/index")
        self.assertIsNone(reading_path.section_of("results.html"))
        self.assertIsNone(reading_path.section_of(None))

    def test_a_lettered_chapter_sorts_after_its_own(self):
        """ch23a is an appendix to Chapter 23, not section 0 of Chapter 23."""
        graph = graph_from_labels({
            "a": label("ch23-applied/05-x.html", {}),
            "b": label("ch23a-notation/index.html", {}),
        })
        self.assertEqual(graph.order(["ch23a-notation/index", "ch23-applied/05"]),
                         ["ch23-applied/05", "ch23a-notation/index"])


class TestClosure(unittest.TestCase):

    def setUp(self):
        self.graph = graph_from_labels(BOOK)

    def test_hard_closure_follows_proofs_only(self):
        path = self.graph.closure(["ch02-middle/01"])
        self.assertEqual(path.sections,
                         ["ch01-start/01", "ch01-start/02", "ch02-middle/01"])

    def test_a_soft_citation_pulls_nothing_in(self):
        """thm-d cites thm-c in its statement, so ch02/02 needs nothing on hard edges."""
        self.assertEqual(self.graph.closure(["ch02-middle/02"]).sections, ["ch02-middle/02"])
        self.assertEqual(self.graph.closure(["ch02-middle/02"], hard_only=False).sections,
                         ["ch01-start/01", "ch01-start/02", "ch02-middle/01", "ch02-middle/02"])

    def test_soft_closure_is_a_superset(self):
        for target in ["ch01-start/02", "ch02-middle/01", "ch03-late/01"]:
            hard = set(self.graph.closure([target]).sections)
            full = set(self.graph.closure([target], hard_only=False).sections)
            self.assertTrue(hard <= full, target)

    def test_several_targets_are_merged(self):
        path = self.graph.closure(["ch02-middle/01", "ch03-late/02"])
        self.assertEqual(path.sections, ["ch01-start/01", "ch01-start/02", "ch02-middle/01",
                                         "ch03-late/02", "ch04-end/01"])
        self.assertEqual(path.targets, ["ch02-middle/01", "ch03-late/02"])

    def test_sections_come_back_in_reading_order(self):
        path = self.graph.closure(["ch03-late/01"], hard_only=False)
        self.assertEqual(path.sections, sorted(path.sections,
                                               key=lambda s: self.graph.key(s)))

    def test_an_unknown_target_names_near_misses(self):
        with self.assertRaises(KeyError) as caught:
            self.graph.closure(["ch02-middle/99"])
        self.assertIn("ch02-middle/01", caught.exception.args[0])

    def test_a_file_name_or_html_path_works_as_a_target(self):
        self.assertEqual(self.graph.resolve("ch02-middle/01-one.html"), "ch02-middle/01")


class TestClosedProperty(unittest.TestCase):
    """The property the whole exercise exists to enforce."""

    def setUp(self):
        self.graph = graph_from_labels(BOOK)

    def test_every_computed_path_is_closed(self):
        for target in sorted(self.graph.sections):
            for hard_only in (True, False):
                path = self.graph.closure([target], hard_only=hard_only)
                check = self.graph.is_closed(path)
                self.assertTrue(check, f"{target} (hard_only={hard_only}):\n{check.report()}")

    def test_a_hand_written_path_that_drops_a_prerequisite_is_caught(self):
        """This is the bug: a reader is sent to ch02/01 without ch01/01."""
        check = self.graph.is_closed(["ch01-start/02", "ch02-middle/01"])
        self.assertFalse(check)
        self.assertEqual([(src, dst) for src, dst, _ in check.violations],
                         [("ch01-start/02", "ch01-start/01")])
        self.assertIn("thm-b", check.report())

    def test_a_path_closed_on_hard_edges_can_be_open_on_soft_ones(self):
        path = self.graph.closure(["ch02-middle/02"])
        self.assertTrue(self.graph.is_closed(path))
        self.assertFalse(self.graph.is_closed(path.sections, hard_only=False))

    def test_dropping_any_one_section_breaks_closure(self):
        """A closure has no slack: every section in it is needed by something."""
        path = self.graph.closure(["ch03-late/02"])
        self.assertEqual(path.sections, ["ch03-late/02", "ch04-end/01"])
        for dropped in path.sections[1:]:
            shorter = [s for s in path.sections if s != dropped]
            self.assertFalse(self.graph.is_closed(shorter), dropped)

    def test_a_cycle_does_not_hang_the_closure(self):
        """Forward citations are barred elsewhere, but the walk must not depend on it."""
        graph = graph_from_labels({
            "thm-x": label("ch01-a/01-x.html", {"thm-y": ["proof"]}),
            "thm-y": label("ch02-b/01-y.html", {"thm-x": ["proof"]}),
        })
        path = graph.closure(["ch01-a/01"])
        self.assertEqual(path.sections, ["ch01-a/01", "ch02-b/01"])
        self.assertTrue(graph.is_closed(path))

    def test_a_citation_within_one_section_is_not_an_edge(self):
        graph = graph_from_labels({
            "def-p": label("ch01-a/01-x.html", {}),
            "thm-q": label("ch01-a/01-x.html", {"def-p": ["proof"]}),
        })
        self.assertEqual(graph.closure(["ch01-a/01"]).sections, ["ch01-a/01"])
        self.assertEqual(graph.citations, [])


class TestWeakestLinks(unittest.TestCase):

    def setUp(self):
        self.graph = graph_from_labels(BOOK)

    def test_a_section_held_by_one_proof_citation_is_reported(self):
        path = self.graph.closure(["ch02-middle/01"])
        weak = dict(self.graph.weakest_links(path))
        self.assertEqual(sorted(weak), ["ch01-start/01", "ch01-start/02"])
        self.assertEqual([c.citing for c in weak["ch01-start/01"]], ["thm-b"])
        self.assertEqual(weak["ch01-start/01"][0].site(), "thm-b (proof) -> def-a")

    def test_the_target_is_never_its_own_weakest_link(self):
        path = self.graph.closure(["ch02-middle/01"])
        self.assertNotIn("ch02-middle/01", dict(self.graph.weakest_links(path)))

    def test_soft_citations_are_not_counted_as_pulls(self):
        """thm-c2's remark cites def-a, but a remark never puts a section on the path."""
        path = self.graph.closure(["ch02-middle/01"])
        weak = dict(self.graph.weakest_links(path))
        self.assertEqual([c.citing for c in weak["ch01-start/01"]], ["thm-b"])

    def test_the_limit_is_respected(self):
        graph = graph_from_labels({
            "def-a": label("ch01-a/01-x.html", {}),
            "thm-1": label("ch02-b/01-y.html", {"def-a": ["proof"]}),
            "thm-2": label("ch02-b/01-y.html", {"def-a": ["proof"]}),
            "thm-3": label("ch02-b/01-y.html", {"def-a": ["proof"]}),
        })
        path = graph.closure(["ch02-b/01"])
        self.assertEqual(graph.weakest_links(path, limit=2), [])
        self.assertEqual([sid for sid, _ in graph.weakest_links(path, limit=3)], ["ch01-a/01"])

    def test_soft_context_lists_what_the_path_leaves_behind(self):
        path = self.graph.closure(["ch03-late/01"])
        self.assertIn("ch03-late/02", dict(self.graph.soft_context(path)))


class TestMissingKinds(unittest.TestCase):
    """An index written before uses_kinds existed must not be read as all-hard."""

    def test_a_citation_with_no_kind_is_soft_and_counted(self):
        graph = graph_from_labels({
            "def-a": {"file": "ch01-a/01-x.html", "number": "1.1.1", "type": "definition",
                      "uses": []},
            "thm-b": {"file": "ch02-b/01-y.html", "number": "2.1.1", "type": "theorem",
                      "uses": ["def-a"]},
        })
        self.assertEqual(graph.unknown_kinds, 1)
        self.assertEqual(graph.closure(["ch02-b/01"]).sections, ["ch02-b/01"])
        self.assertEqual(graph.closure(["ch02-b/01"], hard_only=False).sections,
                         ["ch01-a/01", "ch02-b/01"])


class TestCommandLine(unittest.TestCase):

    def run_cli(self, *argv):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "crossref_labels.json"
            index.write_text(json.dumps({"crossref_labels": BOOK}))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = reading_path.main([*argv, "--index", str(index)])
        return code, out.getvalue(), err.getvalue()

    def test_it_prints_a_path_and_its_counts(self):
        code, out, _ = self.run_cli("ch02-middle/01")
        self.assertEqual(code, 0)
        self.assertIn("ch01-start/01", out)
        self.assertIn("3 of 7 sections on hard edges", out)
        self.assertIn("Closure check: closed", out)

    def test_json_output_carries_both_closures(self):
        code, out, _ = self.run_cli("ch02-middle/02", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["hard"]["count"], 1)
        self.assertEqual(data["with_soft"]["count"], 4)
        self.assertEqual(data["soft_only"],
                         ["ch01-start/01", "ch01-start/02", "ch02-middle/01"])
        self.assertTrue(data["closed"])

    def test_verify_passes_on_a_computed_path(self):
        code, out, _ = self.run_cli("ch03-late/01", "--verify")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "closed")

    def test_an_unknown_section_fails_with_a_message(self):
        code, _, err = self.run_cli("ch99-nowhere/01")
        self.assertEqual(code, 1)
        self.assertIn("no section", err)

    def test_a_missing_index_fails_cleanly(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = reading_path.main(["ch01-start/01", "--index", "/nonexistent/labels.json"])
        self.assertEqual(code, 1)
        self.assertIn("run ./build.py html first", err.getvalue())


class TestExercisePolicy(unittest.TestCase):
    """`hard_kinds` is the policy knob, and the solution is the case that needs one."""

    def test_a_solution_is_soft_for_the_reader_who_skips_the_exercises(self):
        graph = graph_from_labels(EXERCISE_BOOK)
        self.assertNotIn("ch04-end/01", graph.closure(["ch02-middle/02"]).sections)

    def test_a_solution_is_hard_for_the_reader_who_works_them(self):
        graph = graph_from_labels(EXERCISE_BOOK, hard_kinds=reading_path.EXERCISE_KINDS)
        path = graph.closure(["ch02-middle/02"])
        self.assertEqual(path.sections, ["ch02-middle/02", "ch04-end/01"])
        self.assertTrue(graph.is_closed(path))

    def test_the_longer_variant_contains_the_shorter_one(self):
        reading = graph_from_labels(EXERCISE_BOOK)
        with_exercises = graph_from_labels(EXERCISE_BOOK,
                                           hard_kinds=reading_path.EXERCISE_KINDS)
        for target in sorted(reading.sections):
            short = set(reading.closure([target]).sections)
            long = set(with_exercises.closure([target]).sections)
            self.assertTrue(short <= long, target)

    def test_the_graph_remembers_which_policy_built_it(self):
        self.assertEqual(graph_from_labels(BOOK).hard_kinds, reading_path.HARD_KINDS)
        self.assertIn("solution", reading_path.EXERCISE_KINDS)
        self.assertTrue(reading_path.HARD_KINDS < reading_path.EXERCISE_KINDS)


class TestProfiles(unittest.TestCase):
    """The reader profiles live in the config so the author can edit them without code."""

    def test_profiles_are_read_from_a_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text(json.dumps({"reading-paths": [
                {"slug": "demo", "name": "Demo", "description": "d",
                 "targets": ["ch02-middle/01"]}]}))
            profiles = reading_path.load_profiles(config)
        self.assertEqual([p["slug"] for p in profiles], ["demo"])

    def test_a_missing_config_is_not_an_error(self):
        self.assertEqual(reading_path.load_profiles("/nonexistent/config.json"), [])

if __name__ == "__main__":
    unittest.main()
