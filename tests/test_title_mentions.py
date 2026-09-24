"""What counts as naming a result without citing it.

The advisory exists to catch "by the Basis Extension Theorem" with no link. Its first
run over the whole book produced 223 warnings, of which 4 were worth acting on; the
rules here are what separate those 4 from the rest, and each one is pinned because
losing it buries the signal again rather than breaking anything visibly.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build.manifest import add_title_mentions


def label(title, type_="theorem", uses=(), text="", file="ch01-x/01.html"):
    return {"title": title, "type": type_, "uses": list(uses), "text": text, "file": file}


class TitleMentions(unittest.TestCase):
    def test_a_named_result_used_without_a_link_is_reported(self):
        labels = {
            "thm-basis-extension": label("Basis Extension Theorem"),
            "thm-user": label("Something Else", text="By the Basis Extension Theorem, extend it."),
        }
        add_title_mentions(labels)
        self.assertEqual(labels["thm-user"]["mentions"], ["thm-basis-extension"])

    def test_citing_it_is_not_naming_it(self):
        labels = {
            "thm-basis-extension": label("Basis Extension Theorem"),
            "thm-user": label("Something Else", uses=["thm-basis-extension"],
                              text="By the Basis Extension Theorem, extend it."),
        }
        add_title_mentions(labels)
        self.assertEqual(labels["thm-user"]["mentions"], [])

    def test_a_longer_title_does_not_name_the_shorter_one_inside_it(self):
        """The block text begins with the owner's own title, so a result called "Basic
        Properties of Fields" was reported as naming one called "Basic Properties". This
        shape alone was 40 of the 223."""
        labels = {
            "prp-basic": label("Basic Properties", type_="proposition"),
            "prp-fields": label("Basic Properties of Fields", type_="proposition",
                                text="Basic Properties of Fields Let F be a field."),
        }
        add_title_mentions(labels)
        self.assertEqual(labels["prp-fields"]["mentions"], [])

    def test_citing_one_of_two_results_that_share_a_title_covers_both(self):
        """A book may carry two results under one title. Citing
        either gives the reader the statement. That collision was 82 of the 223."""
        labels = {
            "thm-complex-ti": label("Triangle Inequality"),
            "cor-ti": label("Triangle Inequality", type_="corollary"),
            "thm-user": label("Gershgorin", uses=["thm-complex-ti"],
                              text="using the triangle inequality"),
        }
        add_title_mentions(labels)
        self.assertEqual(labels["thm-user"]["mentions"], [])

    def test_a_citation_elsewhere_on_the_page_counts(self):
        """The book writes "this is @thm-x again" in the paragraph after a corollary,
        which sits inside no block and so was invisible to the scan."""
        labels = {
            "thm-row-rank": label("Row Rank Equals Column Rank", file="ch05-d/04.html"),
            "cor-user": label("Rank of a Dual Map", type_="corollary", file="ch05-d/04.html",
                              text="row rank equals column rank"),
        }
        add_title_mentions(labels, {"ch05-d/04.html": ["thm-row-rank"]})
        self.assertEqual(labels["cor-user"]["mentions"], [])

    def test_a_citation_on_a_different_page_does_not_count(self):
        labels = {
            "thm-row-rank": label("Row Rank Equals Column Rank", file="ch05-d/04.html"),
            "cor-user": label("Rank of a Dual Map", type_="corollary", file="ch09-e/02.html",
                              text="row rank equals column rank"),
        }
        add_title_mentions(labels, {"ch05-d/04.html": ["thm-row-rank"]})
        self.assertEqual(labels["cor-user"]["mentions"], ["thm-row-rank"])

    def test_an_exempt_title_is_never_a_mention(self):
        """Some results are named after ordinary language: "Permutation matrices" is a
        plural noun before it is the name of a lemma."""
        labels = {
            "lem-perm": label("Permutation matrices", type_="lemma"),
            "thm-user": label("Birkhoff", text="a convex combination of permutation matrices"),
        }
        add_title_mentions(labels, None, {"Permutation matrices"})
        self.assertEqual(labels["thm-user"]["mentions"], [])

    def test_definitions_and_one_word_titles_are_not_matched(self):
        labels = {
            "def-span": label("Span of a Set", type_="definition"),
            "thm-short": label("Rank"),
            "thm-user": label("User", text="the span of a set and the rank of it"),
        }
        add_title_mentions(labels)
        self.assertEqual(labels["thm-user"]["mentions"], [])



class TitlesAResult(unittest.TestCase):
    """Only a title that names a result is matched. The two books in this engine title
    theirs differently, and the check was written for one of them."""

    def test_names(self):
        from build.manifest import _titles_a_result
        for t in ("Basis Extension Theorem", "Invertible Matrix Theorem", "Schur's Lemma",
                  "Hölder's Inequality", "Triangle Inequality", "The Rank-Nullity Theorem",
                  "Sylvester's Law of Inertia", "Birkhoff-von Neumann"):
            self.assertTrue(_titles_a_result(t), t)

    def test_descriptions(self):
        from build.manifest import _titles_a_result
        for t in ("Permutation matrices", "Normal equations", "Conditional distribution",
                  "Random regressors", "The proportional odds model", "Prediction interval",
                  "Associativity of composition", "The matrix of a projection"):
            self.assertFalse(_titles_a_result(t), t)

    def test_a_description_never_becomes_a_mention(self):
        labels = {
            "thm-normal-eq": label("Normal equations"),
            "thm-user": label("Something", text="solving the normal equations gives"),
        }
        add_title_mentions(labels)
        self.assertEqual(labels["thm-user"]["mentions"], [])


if __name__ == "__main__":
    unittest.main()
