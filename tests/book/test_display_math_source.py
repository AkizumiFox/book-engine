"""Lint the book's sources for two shapes that silently break a display.

Pandoc only parses \\[ ... \\] as display math when the block is one paragraph.
Two things end the paragraph early, and then the display is emitted as literal
text: stray "[" and "]" on the web page, and LaTeX errors in the PDF. MathJax
still renders the loose \\begin{aligned} it finds, so the web page looks
almost right, which is how 21 + 20 displays across Chapters 0-16 went unnoticed.

1. A blank line inside the display.
2. A line inside the display that begins like a list item ("+ ", "- ", "1. ",
   "(a) " ...). Inside a paragraph that is itself a list item, such as a
   solution beginning "(a)", Markdown starts a nested list there.

A third shape breaks only the PDF, and breaks it silently: a character outside
ASCII inside a math span. pdflatex drops an unmapped one with no error at all,
so the PDF gate passes and the sentence loses a symbol. Chapter 19 wrote the
degree sign as a raw glyph, and the printed book read "the angle is less than
13". Unicode in ordinary prose is fine; the preamble maps what the book uses.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bookenv import SRC  # noqa: E402
LIST_MARKER = re.compile(r'^\s{0,3}([-+*]|\d+[.)]|\(\w{1,4}\)|[a-zA-Z][.)]|#\.)\s')
# (?<!\\) so a LaTeX line break with spacing, \\\\[3ex], is not read as the start of a display
MATH_SPAN = re.compile(r'(?<!\\)\\\((.*?)\\\)|(?<!\\)\\\[(.*?)\\\]', re.S)


def display_lines():
    """Yield (path, line number, line) for every line strictly inside a \\[ ... \\] display."""
    for md in sorted(SRC.rglob("*.md")):
        inside = False
        for number, line in enumerate(md.read_text().split("\n"), 1):
            stripped = line.strip()
            if not inside and stripped.startswith("\\[") and not stripped.endswith("\\]"):
                inside = True
            elif inside and stripped.startswith("\\]"):
                inside = False
            elif inside:
                yield md, number, line


class TestDisplayMathSource(unittest.TestCase):

    def test_no_blank_line_inside_a_display(self):
        bad = [f"{p.relative_to(SRC)}:{n}" for p, n, l in display_lines() if not l.strip()]
        self.assertEqual(bad, [], "blank line inside \\[ ... \\] ends the display early")

    def test_no_non_ascii_inside_math(self):
        bad = []
        for md in sorted(SRC.rglob("*.md")):
            text = md.read_text()
            for match in MATH_SPAN.finditer(text):
                span = match.group(0)
                stray = sorted({c for c in span if ord(c) > 127})
                if stray:
                    line = text.count("\n", 0, match.start()) + 1
                    bad.append(f"{md.relative_to(SRC)}:{line}: {' '.join(stray)}")
        self.assertEqual(bad, [], "pdflatex drops an unmapped character in math with no error; "
                                  "write it as a command, e.g. ^\\circ for the degree sign")

    def test_no_display_line_that_looks_like_a_list_item(self):
        bad = [f"{p.relative_to(SRC)}:{n}: {l.strip()[:40]}"
               for p, n, l in display_lines() if LIST_MARKER.match(l)]
        self.assertEqual(bad, [], "join these onto the previous line; a newline in math is only a space")


if __name__ == "__main__":
    unittest.main()
