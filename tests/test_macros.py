"""Unit tests for the LaTeX macro -> MathJax conversion (no external tools needed)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build.macros import parse_macros, mathjax_macros  # noqa: E402


class TestParseMacros(unittest.TestCase):

    def test_def_with_spaces_and_nested_braces(self):
        self.assertEqual(parse_macros(r"\def \nR {\ensuremath{\mathbbmss{R}}}"), {"nR": r"\mathbb{R}"})

    def test_newcommand_with_arguments(self):
        macros = parse_macros(r"\newcommand{\ip}[2]{\langle #1, #2 \rangle}")
        self.assertEqual(macros, {"ip": [r"\langle #1, #2 \rangle", 2]})

    def test_providecommand_does_not_override(self):
        macros = parse_macros("\\def\\tr{\\operatorname{tr}}\n\\providecommand{\\tr}{\\text{tr}}")
        self.assertEqual(macros["tr"], r"\operatorname{tr}")

    def test_declare_math_operator(self):
        macros = parse_macros(r"\DeclareMathOperator*{\argmax}{arg\,max}\DeclareMathOperator{\rank}{rank}")
        self.assertEqual(macros, {"argmax": r"\operatorname*{arg\,max}", "rank": r"\operatorname{rank}"})

    def test_comments_ignored(self):
        self.assertEqual(parse_macros("% \\def\\x{y}\n\\def\\z{w} % trailing"), {"z": "w"})

    def test_digit_names(self):
        self.assertEqual(parse_macros(r"\def \0 {\mathbf{0}}"), {"0": r"\mathbf{0}"})

    def test_web_defaults_and_overrides(self, tmp=None):
        macros = mathjax_macros(Path("/nonexistent/macros.tex"))
        self.assertIn("coloneqq", macros)
        self.assertEqual(macros["bm"], [r"\boldsymbol{#1}", 1])

if __name__ == "__main__":
    unittest.main()
