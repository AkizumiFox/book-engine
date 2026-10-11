#!/usr/bin/env python3
"""Lint what the reader actually sees: the built HTML and the PDF build logs.

The source can be right and the page still wrong -- a `\\|` that Pandoc put in a
`<code>` span, a `\\qedhere` that only LaTeX understands, a `:::` fence that lost
its div, a reference printed as `??`. None of these is visible in the Markdown,
so they are looked for in `_build/html` after `./build.py html`, and in the LaTeX
logs under `_build/tmp` after a PDF build.

HTML (visible text only: `<script>`, `<style>`, `<svg>`, `<math>` and rendered math
(`<mjx-container>`, `span.math`) are skipped; attribute values are never text):

* **raw TeX** -- a backslash command (`\\alpha`, `\\(`) or any stray backslash in
  prose outside math and code; `\\qedhere` is named on its own;
* **`??`** -- an unresolved reference;
* **MathJax errors** -- an `mjx-merror` node or a `data-mjx-error` attribute;
* **visible fences** -- `:::` or ```` ``` ```` in the text or in a `<pre>` block, which
  means a div or a code block was not closed or not recognized (inline `<code>` is
  exempt: a page that documents the markup shows `::: {.proof}` on purpose);
* **`<code>` containing `\\|`** -- a table-escape that leaked into code.

PDF logs (`_build/tmp/**/*.log`):

* errors: `Undefined control sequence`, `Missing character`;
* warnings: `Overfull \\hbox` / `\\vbox` (with how much too wide).

    python3 tools/check_rendered.py                      # _build/html and _build/tmp
    python3 tools/check_rendered.py --html _build/html --logs _build/tmp
    python3 tools/check_rendered.py --no-overfull        # hide Overfull warnings

Exits 1 on any HTML problem or log error (warnings never fail). Importable:

    from tools.check_rendered import lint_html, scan_log
"""
import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SKIP = {"script", "style", "svg", "math", "mjx-container", "textarea", "template", "noscript"}
CODE = {"code", "pre", "kbd", "samp"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr", "param"}
TEX = re.compile(r"\\([A-Za-z]+|[()\[\]])")


class _Linter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []           # (tag, skip, code)
        self.problems = []        # (line, message)
        self.code_buf = None

    def _skip(self):
        return any(s for _, s, _ in self.stack)

    def _code(self):
        return any(c for _, _, c in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "mjx-merror" or "data-mjx-error" in a:
            self.problems.append((self.getpos()[0], f"MathJax error node: {a.get('data-mjx-error', tag)}"))
        if tag in VOID:
            return
        classes = (a.get("class") or "").split()
        skip = tag in SKIP or (tag == "span" and "math" in classes)
        code = tag in CODE
        self.stack.append((tag, skip, code))
        if tag == "code" and self.code_buf is None:
            self.code_buf = [self.getpos()[0], ""]

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        if tag == "mjx-merror" or "data-mjx-error" in a:
            self.problems.append((self.getpos()[0], f"MathJax error node: {a.get('data-mjx-error', tag)}"))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                del self.stack[k:]
                break
        if tag == "code" and self.code_buf is not None and not any(t == "code" for t, _, _ in self.stack):
            line, text = self.code_buf
            if "\\|" in text:
                self.problems.append((line, f"<code> contains \\|: {text.strip()[:60]!r}"))
            self.code_buf = None

    def handle_data(self, data):
        if self._skip():
            return
        line = self.getpos()[0]
        if self.code_buf is not None:
            self.code_buf[1] += data
        inline_code = self._code() and not any(t == "pre" for t, _, _ in self.stack)
        for fence in (":::", "```"):
            if fence in data and not inline_code:
                self.problems.append((line, f"visible {fence} fence: {_snip(data, fence)}"))
        if self._code():
            return
        if "??" in data:
            self.problems.append((line, f"?? in text: {_snip(data, '??')}"))
        for m in TEX.finditer(data):
            name = m.group(0)
            if name == "\\qedhere":
                self.problems.append((line, "\\qedhere in the page"))
            else:
                self.problems.append((line, f"raw TeX {name} in text: {_snip(data, name)}"))
        stray = data.count("\\") - len(TEX.findall(data))
        if stray > 0:
            self.problems.append((line, f"backslash in text: {_snip(data, chr(92))}"))


def _snip(text: str, needle: str) -> str:
    i = text.find(needle)
    return repr(" ".join(text[max(0, i - 30):i + 30].split()))


def lint_html(text: str) -> list:
    """(line, message) problems in one HTML page."""
    p = _Linter()
    p.feed(text)
    p.close()
    return p.problems


LOG_ERRORS = (
    (re.compile(r"^! Undefined control sequence"), "Undefined control sequence"),
    (re.compile(r"^Missing character: (.*)"), "Missing character"),
)
OVERFULL = re.compile(r"^Overfull \\[hv]box \(([\d.]+)pt too (?:wide|high)\) (.*)")


def scan_log(text: str):
    """(errors, warnings) in one LaTeX log: lists of (log line, message)."""
    errors, warnings = [], []
    lines = text.split("\n")
    for n, line in enumerate(lines, 1):
        for pat, name in LOG_ERRORS:
            m = pat.match(line)
            if m:
                detail = ""
                if name.startswith("Undefined"):
                    nxt = next((x for x in lines[n:n + 4] if x.startswith("l.")), "")
                    detail = nxt.strip()
                else:
                    detail = m.group(1).strip()
                errors.append((n, f"{name}: {detail}"[:160]))
        m = OVERFULL.match(line)
        if m:
            warnings.append((n, f"Overfull box, {m.group(1)}pt too wide {m.group(2)}"[:160]))
    return errors, warnings


def find_violations(html_dir: Path, log_dir: Path | None, overfull: bool = True):
    """(errors, warnings): lists of (path, line, message)."""
    errors, warnings = [], []
    if html_dir and Path(html_dir).exists():
        for page in sorted(Path(html_dir).rglob("*.html")):
            for line, msg in lint_html(page.read_text(encoding="utf-8")):
                errors.append((page, line, msg))
    if log_dir and Path(log_dir).exists():
        for log in sorted(Path(log_dir).rglob("*.log")):
            e, w = scan_log(log.read_text(encoding="latin-1"))
            errors += [(log, n, m) for n, m in e]
            if overfull:
                warnings += [(log, n, m) for n, m in w]
    return errors, warnings


def report(items) -> str:
    return "\n".join(f"{p}:{n}: {m}" for p, n, m in items)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lint the built HTML (visible raw TeX, ??, MathJax "
                                             "errors, stray fences) and the PDF build logs.")
    ap.add_argument("--html", default="_build/html", help="built site (default: _build/html)")
    ap.add_argument("--logs", default="_build/tmp", help="LaTeX logs (default: _build/tmp)")
    ap.add_argument("--no-overfull", action="store_true", help="do not list Overfull boxes")
    args = ap.parse_args(argv)
    if not Path(args.html).exists():
        print(f"{args.html} not found; run ./build.py html first", file=sys.stderr)
        return 1
    errors, warnings = find_violations(Path(args.html), Path(args.logs), not args.no_overfull)
    if warnings:
        print("Warnings:")
        print(report(warnings))
        print()
    if errors:
        print("Errors:")
        print(report(errors))
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
