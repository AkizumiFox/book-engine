"""The engine's gates, on this book as built. Skipped until `./build.py html` has run.

`./build.py check` runs the same gates; these name the failing result in a test report
and also hold the reading paths the book publishes to their promise (closed paths).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bookenv  # noqa: E402

reading_path = bookenv.tool("reading_path")
check_optional = bookenv.tool("check_optional")
check_forward_deps = bookenv.tool("check_forward_deps")


class BuiltBookCase(unittest.TestCase):
    def setUp(self):
        self.labels = bookenv.built_labels()
        if self.labels is None:
            self.skipTest("run ./build.py html first")

    def graph(self, **kwargs):
        return reading_path.load_graph(bookenv.INDEX, bookenv.NAVIGATION, **kwargs)


class TestForwardDependencies(BuiltBookCase):

    def test_no_proof_in_the_book_points_forward(self):
        violations = check_forward_deps.find_violations(self.labels)
        self.assertEqual(violations, [], check_forward_deps.report(violations))

    def test_the_signposts_are_all_soft(self):
        """Forward pointers are allowed as signposts (examples, remarks, exercises), never
        as steps of a proof."""
        order = check_forward_deps.place(self.labels)
        rows = check_forward_deps.forward_citations(self.labels, order)
        self.assertTrue(all(not row[3] for row in rows))


class TestOptionalResults(BuiltBookCase):

    def test_no_proof_in_the_book_rests_on_an_optional_result(self):
        violations = check_optional.find_violations(self.labels)
        self.assertEqual(violations, [], check_optional.report(violations))

    def test_the_marked_results_are_marked_on_purpose(self):
        """Only a big environment may be optional: nobody skips a remark on purpose."""
        big = {"theorem", "lemma", "corollary", "proposition", "example", "definition", "axiom"}
        for name, rec in self.labels.items():
            if rec.get("optional"):
                self.assertIn(rec.get("type"), big, name)


class TestReadingPaths(BuiltBookCase):
    """The sections this book's reader profiles aim at, taken from its config, so that
    adding a profile puts it under this check and a stale target fails loudly."""

    def setUp(self):
        super().setUp()
        self.profiles = reading_path.load_profiles(bookenv.CONFIG)
        if not self.profiles:
            self.skipTest("no reader profiles in the config")

    def test_every_published_path_is_closed_in_both_variants(self):
        for kinds in (reading_path.HARD_KINDS, reading_path.EXERCISE_KINDS):
            graph = self.graph(hard_kinds=kinds)
            for profile in self.profiles:
                for hard_only in (True, False):
                    path = graph.closure(profile["targets"], hard_only=hard_only)
                    check = graph.is_closed(path)
                    self.assertTrue(check, f"{profile['slug']} (hard_only={hard_only}):\n{check.report()}")
                    for target in profile["targets"]:
                        self.assertIn(target, path.sections)

    def test_every_target_names_a_real_section(self):
        graph = self.graph()
        for profile in self.profiles:
            for target in profile["targets"]:
                self.assertEqual(graph.resolve(target), target)

    def test_every_citation_has_a_recorded_kind(self):
        self.assertEqual(self.graph().unknown_kinds, 0)

    def test_no_optional_result_carries_a_hard_edge(self):
        graph = self.graph()
        self.assertFalse([c.site() for c in graph.citations if c.from_optional and c.hard])


class TestConfig(unittest.TestCase):

    def test_the_books_own_profiles_are_well_formed(self):
        for profile in reading_path.load_profiles(bookenv.CONFIG):
            for key in ("slug", "name", "description", "targets"):
                self.assertTrue(profile.get(key), f"{profile.get('slug')}: {key}")
            self.assertRegex(profile["slug"], r"^[a-z0-9-]+$")

    def test_the_macro_file_parses(self):
        from build.book import Book
        from build.macros import mathjax_macros
        book = Book(bookenv.BOOK_ROOT)
        if not book.macros_file.exists():
            self.skipTest("no macro file")
        self.assertTrue(mathjax_macros(book.macros_file))

    def test_sources_and_notation_guide_pass_the_macro_check(self):
        from build.book import Book
        book = Book(bookenv.BOOK_ROOT)
        if "macro-check" not in book.config:
            self.skipTest("this book configures no macro check")
        errors, _ = bookenv.tool("check_macros").check_book(book)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
