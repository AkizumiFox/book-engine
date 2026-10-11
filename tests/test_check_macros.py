"""Tests for tools/check_macros.py, the macro lint `./build.py check` runs.

The notation guide was once a second source of truth and drifted from the rule the
manuscript follows: it kept showing the retired single-letter bold vector macros after
the book had moved to typing vectors (`\\cvec{x}` in F^n, `\\elem{v}` in an abstract
space). The lint holds the guide and the sources to one rule: a retired macro is an
error in either, and every macro the guide shows must be one the build defines.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import check_macros  # noqa: E402
from tools.check_macros import (  # noqa: E402
    check_files, manuscript_text, math_segments, names_used, retired_uses,
    zero_matrix_misuses)

RETIRED = set("abcdefghijklmnopqrstuvwxyz0")


class TestRetiredUses(unittest.TestCase):

    def test_single_letter_and_zero_are_found(self):
        found = retired_uses(r"\( \v + \0 \) and \( \x_1 \)", RETIRED)
        self.assertEqual([m for _, m in found], [r"\v", r"\0", r"\x"])

    def test_longer_names_and_typed_vectors_are_not(self):
        text = r"\( \vec f, \varphi, \cvec{v}, \elem{0}, \e_{S} \)"
        self.assertEqual([m for _, m in retired_uses(text, RETIRED)], [r"\e"])
        self.assertEqual(retired_uses(r"\( \vec f + \cvec{x} \)", RETIRED), [])

    def test_a_backslash_pair_is_a_line_break(self):
        # `\\0` and `\\x` in a matrix are a line break followed by an entry
        text = r"\begin{pmatrix}1&0\\0&1\\x&y\end{pmatrix}"
        self.assertEqual(retired_uses(text, RETIRED), [])

    def test_line_numbers(self):
        self.assertEqual(retired_uses("one\ntwo \\( \\u \\)", RETIRED), [(2, r"\u")])


class TestZeroMatrixMisuses(unittest.TestCase):

    def test_a_sized_zero_vector_is_a_zero_matrix(self):
        found = zero_matrix_misuses(r"\( \cvec{0}_{m \times n} \) and \( \cvec{0} _ {2\times 3} \)")
        self.assertEqual(len(found), 2)
        self.assertIn("with a matrix size; write \\O", found[0][1])

    def test_loewner_comparisons_with_the_zero_vector(self):
        text = "\n".join([r"\( \A \succeq \cvec{0} \), \( \A \succ \cvec{0} \)",
                          r"\( \B \not\succeq \cvec{0} \), \( \cvec{0} \preceq \X \prec \I \)",
                          r"\( \X \preceq\cvec{ 0 } \)"])
        self.assertEqual([line for line, _ in zero_matrix_misuses(text)], [1, 1, 2, 2, 3])

    def test_a_one_by_one_zero_matrix_in_parentheses(self):
        text = "\n".join([r"\( \B = (0) \), \( \I_2 \oplus ( 0 ) \)",
                          r"\( \A \ne (0) \), \( (0) \preceq \A \succeq (0) \)"])
        found = zero_matrix_misuses(text)
        self.assertEqual([line for line, _ in found], [1, 1, 2, 2])
        self.assertIn("write \\O_1", found[0][1])
        self.assertEqual(zero_matrix_misuses(r"\( p(0) = q(0) \), \( \A^{(0)} = \A \), \( \B = (1) \)"), [])

    def test_zero_vectors_and_the_bold_o_pass(self):
        text = (r"\( \A\cvec{x} = \cvec{0} \), \( \cvec{x} \ge \cvec{0} \), "
                r"\( \cvec{0}_n \), \( \A \succeq \O \), \( \O_{m \times n} \), "
                r"\( \cvec{0} \succcurlyeq \)")
        self.assertEqual(zero_matrix_misuses(text), [])

    def test_check_files_applies_it_only_when_configured(self):
        tmp = Path(tempfile.mkdtemp())
        section = tmp / "section.md"
        section.write_text("x\n\\( \\A \\succ \\cvec{0} \\), `\\cvec{0}_{m \\times n}` in code", encoding="utf-8")
        errors, _ = check_files(tmp, [section], [], RETIRED, None, None)
        self.assertEqual(errors, [])
        errors, _ = check_files(tmp, [section], [], RETIRED, None, None, zero_matrix=r"\O")
        self.assertEqual(errors, [r"section.md:2: zero matrix written \cvec{0} in a Loewner comparison; write \O"])


class TestManuscriptText(unittest.TestCase):

    def test_tikz_loop_variables_and_code_are_not_math(self):
        source = "\n".join([
            r"\begin{tikzpicture}",
            r"  \foreach \i/\k in {1/2} \node at (\i,0) {$m_\i + \x$};",
            r"  \draw (\c,0) -- (1,1);",
            r"\end{tikzpicture}",
            "```python",
            r"print('\n')",
            "```",
            r"Inline `\v` is code; \( \y \) is math.",
        ])
        found = [m for _, m in retired_uses(manuscript_text(source), RETIRED)]
        # \i is a loop variable, \c is TikZ code, \n is Python, `\v` is inline code;
        # \x sits in a node label and \y in a formula
        self.assertEqual(found, [r"\x", r"\y"])

    def test_line_numbers_survive_filtering(self):
        source = "```\n\\v\n```\n\\( \\w \\)"
        self.assertEqual(retired_uses(manuscript_text(source), RETIRED), [(4, r"\w")])


class TestNamesUsed(unittest.TestCase):

    def test_inline_code_in_a_guide_is_math(self):
        segments = math_segments(r"| `\cvec{x}`, `\frob{v}` | see \( \norm{\elem{v}} \) |", guide=True)
        names, _ = names_used(segments)
        self.assertEqual(set(names), {"cvec", "frob", "norm", "elem"})

    def test_text_groups_are_text(self):
        names, envs = names_used([(1, r"\text{see \emph{this}} \begin{pmatrix}a\end{pmatrix}")])
        self.assertEqual(set(names), {"text"})
        self.assertEqual(set(envs), {"pmatrix"})


class TestCheckFiles(unittest.TestCase):

    def files(self, **contents):
        tmp = Path(tempfile.mkdtemp())
        paths = {}
        for name, text in contents.items():
            path = tmp / f"{name}.md"
            path.write_text(text, encoding="utf-8")
            paths[name] = path
        return tmp, paths

    def test_retired_macro_fails_in_sources_and_in_the_guide(self):
        tmp, p = self.files(section=r"Let \( \v \in V \).", guide=r"| `\x + U` | coset |")
        errors, _ = check_files(tmp, [p["section"]], [p["guide"]], RETIRED, None, None,
                                hint="type the vector")
        self.assertEqual(len(errors), 2)
        self.assertIn(r"section.md:1: retired macro \v; type the vector", errors[0])
        self.assertIn(r"guide.md:1: retired macro \x", errors[1])

    def test_retired_only_files_are_not_asked_about_definitions(self):
        tmp, p = self.files(style=r"Write `\begin{tikzpicture}` and `\x`.")
        errors, notices = check_files(tmp, [], [], RETIRED, {}, Path("/nonexistent"),
                                      retired_only=[p["style"]])
        self.assertEqual([e.split(": ", 1)[1] for e in errors], [r"retired macro \x"])

    def test_typed_vectors_pass(self):
        tmp, p = self.files(guide=r"| `\cvec{x} \ge \cvec{0}`, `\elem{v} + U` | ok |")
        errors, _ = check_files(tmp, [], [p["guide"]], RETIRED, None, None)
        self.assertEqual(errors, [])

    def test_undefined_macro_in_the_guide_fails(self):
        mathjax = check_macros._mathjax_dir()
        if mathjax is None:
            self.skipTest("node or the cached MathJax is not available")
        from build.macros import mathjax_macros
        macros = mathjax_macros(ROOT / "tests" / "fixture-book" / "macros.tex")
        tmp, p = self.files(guide="| `\\norm{x}`, `\\frobnicate{v}` | \\( \\begin{nomatrix}1\\end{nomatrix} \\) |")
        errors, notices = check_files(tmp, [], [p["guide"]], RETIRED, macros, mathjax)
        self.assertEqual(notices, [])
        self.assertEqual(sorted(e.split(": ", 1)[1] for e in errors),
                         [r"undefined macro \frobnicate", "unknown environment nomatrix"])

    def test_without_mathjax_the_definition_rule_is_skipped_with_a_notice(self):
        tmp, p = self.files(guide=r"| `\frobnicate` |")
        errors, notices = check_files(tmp, [], [p["guide"]], RETIRED, {}, None)
        self.assertEqual(errors, [])
        self.assertEqual(len(notices), 1)


class TestThisBook(unittest.TestCase):

    def test_sources_and_notation_guide_pass(self):
        from build.book import Book
        book = Book(ROOT)
        if "macro-check" not in book.config:
            self.skipTest("this book configures no macro check")
        errors, _ = check_macros.check_book(book)
        self.assertEqual(errors, [])


sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import FixtureBookCase, run_build  # noqa: E402


class TestOptInFromTheConfig(FixtureBookCase):
    """`check` runs the macro check only when `checks` lists engine:check_macros; the
    settings come from `macro-check`."""

    @classmethod
    def prepare(cls, book_dir: Path):
        config = json.loads((book_dir / "book.json").read_text())
        config["macro-check"] = {"retired": ["nR"], "retired-hint": "write \\mathbb{R}"}
        config["checks"] = ["engine:check_macros"]
        (book_dir / "book.json").write_text(json.dumps(config, indent=2))

    def test_a_retired_macro_fails_check(self):
        result = run_build(self.book_dir, "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/ch01-basics/01-first.md:8: retired macro \\nR; write \\mathbb{R}", result.stdout)

    def test_settings_without_the_checks_entry_warn_and_do_not_run(self):
        config_file = self.book_dir / "book.json"
        original = config_file.read_text()
        config = json.loads(original)
        del config["checks"]
        config_file.write_text(json.dumps(config, indent=2))
        try:
            result = run_build(self.book_dir, "check")
            self.assertNotIn("retired macro", result.stdout)
            self.assertIn('"checks" does not list "engine:check_macros"', result.stdout)
        finally:
            config_file.write_text(original)


if __name__ == "__main__":
    unittest.main()
