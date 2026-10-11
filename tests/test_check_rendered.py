"""Tests for tools/check_rendered.py: what the reader sees in the built HTML and PDF logs."""

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "check_rendered.py"
spec = importlib.util.spec_from_file_location("check_rendered", TOOL)
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)


def msgs(html):
    return [m for _, m in cr.lint_html(html)]


class HtmlTests(unittest.TestCase):
    def test_clean_page(self):
        page = ('<html><head><style>a::before{content:"\\\\"}</style>'
                '<script>var s = "\\\\alpha ??";</script></head><body>'
                '<p>Plain text with <span class="math inline">\\(x^2\\)</span> and '
                '<mjx-container data-tex="\\alpha"><mjx-math>x</mjx-math></mjx-container>.</p>'
                '<pre><code>print("a\\\\nb")</code></pre><img src="x.png"><br></body></html>')
        self.assertEqual(msgs(page), [])

    def test_raw_tex_and_qedhere(self):
        found = msgs("<p>We have \\alpha here and \\qedhere.</p>")
        self.assertTrue(any("raw TeX \\alpha" in m for m in found))
        self.assertIn("\\qedhere in the page", found)

    def test_stray_backslash(self):
        self.assertTrue(any(m.startswith("backslash in text") for m in msgs("<p>a \\ b</p>")))

    def test_unresolved_reference(self):
        self.assertTrue(any("??" in m for m in msgs("<p>See Theorem ??.</p>")))

    def test_mathjax_error(self):
        page = '<mjx-container><mjx-merror data-mjx-error="Undefined control sequence \\foo">x</mjx-merror></mjx-container>'
        self.assertEqual(msgs(page), ["MathJax error node: Undefined control sequence \\foo"])

    def test_visible_fences(self):
        found = msgs("<p>::: {.check}</p><pre><code>```python</code></pre>")
        self.assertTrue(any("visible ::: fence" in m for m in found))
        self.assertTrue(any("visible ``` fence" in m for m in found))

    def test_markup_quoted_in_inline_code_is_not_a_fence(self):
        self.assertEqual(msgs("<p>Write <code>::: {.proof}</code> to open a proof.</p>"), [])

    def test_code_with_escaped_bar(self):
        self.assertTrue(any("<code> contains \\|" in m for m in msgs("<p><code>a \\| b</code></p>")))
        self.assertEqual(msgs("<p><code>a \\n b</code></p>"), [])


class LogTests(unittest.TestCase):
    LOG = """This is pdfTeX
! Undefined control sequence.
<recently read> \\foo
l.42 some \\foo
Missing character: There is no ⊢ in font cmr10!
Overfull \\hbox (12.5pt too wide) in paragraph at lines 10--12
"""

    def test_scan_log(self):
        errors, warnings = cr.scan_log(self.LOG)
        self.assertEqual([m for _, m in errors],
                         ["Undefined control sequence: l.42 some \\foo",
                          "Missing character: There is no ⊢ in font cmr10!"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("12.5pt", warnings[0][1])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            html, logs = Path(tmp) / "html", Path(tmp) / "tmp"
            html.mkdir()
            logs.mkdir()
            (html / "a.html").write_text("<p>fine</p>")
            (logs / "book.log").write_text("Overfull \\hbox (1pt too wide) in paragraph\n")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cr.main(["--html", str(html), "--logs", str(logs)]), 0)
            (logs / "book.log").write_text(self.LOG)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cr.main(["--html", str(html), "--logs", str(logs)]), 1)


if __name__ == "__main__":
    unittest.main()
