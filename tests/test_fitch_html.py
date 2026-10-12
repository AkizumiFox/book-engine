"""Fitch derivations drawn in HTML (filters/fitch.lua) instead of compiled to SVG.

The filter is run on its own with pandoc over tests/fixtures/fitch/derivations.md (one
derivation per section; fitch-book.sty there is a copy of the Foundations book's, whose
rule macros the filter reads), then a fixture book is built twice: with the default (the
book ships fitch-book.sty, so derivations are HTML, inside exercises and solutions too, and
an unreadable one falls back to the SVG with a warning) and with "fitch-html": false.
"""

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_build import FixtureBookCase  # noqa: E402

ENGINE_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fitch"
FILTER = ENGINE_ROOT / "filters" / "fitch.lua"
STY = FIXTURES / "fitch-book.sty"


def run_filter(source: Path, to: str = "html", **metadata) -> subprocess.CompletedProcess:
    meta = {"fitch-html": True, "fitch-sty": str(STY), "fitch-rulename": True,
            "source-path": source.name, **metadata}
    args = ["pandoc", str(source), "-f", "markdown", "-t", to, "--lua-filter", str(FILTER)]
    for key, value in meta.items():
        args += ["-M", f"{key}={json.dumps(value) if isinstance(value, bool) else value}"]
    return subprocess.run(args, capture_output=True, text=True, check=True)


def sections(html: str) -> dict:
    """The HTML of each fixture section, by its heading id."""
    parts = re.split(r'<h2 id="([^"]+)">.*?</h2>', html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def rows(html: str) -> list:
    """Each derivation row as a dict: num, bars (count), tops (count), levels (each box's
    flag, or ""), formula, assumption (underlined), just."""
    out = []
    for m in re.finditer(r'<div class="fitch-row[^"]*" role="row">(.*?)</span></span></div>', html):
        row = m.group(1)
        body = re.search(r'<span class="fitch-body" role="cell">(.*)</span><span class="fitch-just"', row).group(1)
        out.append({
            "num": re.search(r'<span class="fitch-num" role="cell">(.*?)</span>', row).group(1),
            "bars": len(re.findall(r'class="fitch-bar[ "]', body)),
            "tops": len(re.findall(r'fitch-bar-top', body)),
            "levels": re.findall(r'<span class="fitch-indent">(?:<span class="fitch-flag">(.*?)</span>)?</span>', body),
            "formula": re.search(r'<span class="fitch-formula[^"]*">(.*?)</span>$', body).group(1),
            "assumption": "fitch-assumption" in body,
            "just": row.rsplit('<span class="fitch-just" role="cell"><span>', 1)[1],
        })
    return out


@unittest.skipUnless(shutil.which("pandoc"), "needs pandoc")
class TestFitchFilter(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = run_filter(FIXTURES / "derivations.md")
        cls.html = cls.result.stdout
        cls.parts = sections(cls.html)

    def test_plain_lines(self):
        r = rows(self.parts["plain"])
        self.assertEqual([x["num"] for x in r], ["1", "2", "3"])
        self.assertEqual(r[0]["formula"], r"\(P \wedge Q\)")
        self.assertEqual(r[2]["formula"], r"\(a &lt; b\)")         # escaped for HTML
        self.assertEqual([x["bars"] for x in r], [1, 1, 1])          # the outer line
        self.assertEqual([x["tops"] for x in r], [1, 0, 0])          # starts below the top
        self.assertTrue(r[0]["assumption"])                          # the premise is underlined
        self.assertFalse(r[1]["assumption"])
        self.assertEqual(r[1]["just"], r"\(\rulename{{\wedge}E}\) 1")
        self.assertEqual(r[2]["just"], "")
        self.assertIn('class="fitch-display"', self.parts["plain"])  # centred: no fitch-left

    def test_nested_and_closing_boxes(self):
        r = rows(self.parts["nested"])
        self.assertEqual([x["bars"] for x in r], [1, 1, 2, 2, 3, 3, 2, 1])
        self.assertEqual([x["tops"] for x in r], [1, 0, 1, 0, 1, 0, 0, 0])
        # consecutive assumptions: only the last is underlined (fitch.sty)
        self.assertEqual([x["assumption"] for x in r],
                         [False, True, True, False, True, False, False, False])
        self.assertEqual(r[6]["just"], r"\(\rulename{{{\to}}I}\) 5–6")
        self.assertEqual(r[3]["just"], r"\(\rulename{{{\to}}E}\) 1, 3")

    def test_sibling_boxes_start_apart(self):
        r = rows(self.parts["siblings"])
        self.assertEqual([x["bars"] for x in r], [1, 2, 2, 2, 2, 1])
        self.assertEqual([x["tops"] for x in r], [1, 1, 0, 1, 0, 0])   # line 4 starts a new box
        self.assertEqual(r[5]["just"], r"\(\rulename{{\vee}E}\) 1, 2–3, 4–5")

    def test_flagged_boxes(self):
        r = rows(self.parts["flagged"])
        flags = [x["levels"] for x in r]
        self.assertEqual(flags[2], [r'\(x_0\)'])   # \open[x_0]: first row
        self.assertEqual(flags[3], [""])                                     # only there
        self.assertEqual(flags[7], [r'\(y_0\)'])   # \hypo{8}[y_0]{...}
        self.assertEqual(flags[9], [r'\(z_0\)'])   # \guard{z_0}
        self.assertTrue(r[2]["assumption"])
        self.assertEqual(r[6]["just"], r"\(\rulename{{\exists}E}\) 1, 3–6")
        self.assertEqual(r[9]["just"], r"\(\rulename{{=}I}\)")

    def test_by_text_and_refs(self):
        r = rows(self.parts["by"])
        self.assertEqual(r[2]["just"], "Tr 1, 2")
        self.assertEqual(r[3]["just"], r"arith, \(x \le y\) 3")
        self.assertEqual(r[4]["just"], "Flip 3")
        self.assertEqual(r[5]["just"], "5")

    def test_every_rule_macro_of_the_sty(self):
        sty = re.sub(r"%[^\n]*", "", STY.read_text())
        macros = re.findall(r"\\def\\([A-Za-z]+)\{\\by\{(.*?)\}\}", sty)
        self.assertEqual(len(macros), 27)
        r = rows(self.parts["rules"])
        self.assertEqual(len(r), len(macros))
        for (name, text), row in zip(macros, r):
            expected = r"\(\rulename{" + re.sub(r"\$(.*?)\$", r"{\1}", text) + r"}\) 1"
            self.assertEqual(row["just"], expected, name)

    def test_markers_are_comments(self):
        r = rows(self.parts["expect-invalid"])
        self.assertEqual(len(r), 2)
        self.assertNotIn("expect-invalid", self.parts["expect-invalid"].split("</h2>")[-1])
        self.assertNotIn("cites one line", self.parts["expect-invalid"])
        self.assertEqual(r[1]["just"], r"\(\rulename{{{\to}}E}\) 1")

    def test_schema_and_numbering_options(self):
        part = self.parts["schema"]
        self.assertEqual(part.count('<div class="fitch" role="table"'), 3)
        self.assertEqual(part.count('<div class="fitch-break">'), 1)    # \\[2ex]
        r = rows(part)
        # [schema]: labels printed; the flag on the box's first row; refs print labels
        self.assertEqual([x["num"] for x in r[:3]], [r"\(i\)", r"\(j\)", r"\(k\)"])
        self.assertEqual(r[0]["levels"], [r'\(x_0\)'])
        self.assertEqual(r[2]["just"], r"\(\rulename{{\forall}I}\) \(i\)–\(j\)")
        # \have[i][0], then i+1; \have[\ ][0] prints nothing; \have[][7] jumps to 7
        self.assertEqual([x["num"] for x in r[3:7]], [r"\(i\)", r"\(i+1\)", "", "7"])
        self.assertEqual(r[4]["just"], r"\(\rulename{R}\) \(i\)")
        self.assertEqual(r[6]["just"], "?")

    def test_unreadable_blocks_fall_back_with_a_warning(self):
        for section in ("fallback", "continuation"):
            self.assertNotIn("fitch", self.parts[section], section)
        warnings = [line for line in self.result.stderr.splitlines() if "fitch-html" in line]
        self.assertEqual(len(warnings), 2, self.result.stderr)
        self.assertIn("derivations.md", warnings[0])
        self.assertIn("unexpected `Prose", warnings[0])
        self.assertIn("havecont", warnings[1])

    def test_tikz_is_left_alone(self):
        self.assertNotIn("fitch", self.parts["tikz"])

    def test_off_unless_enabled(self):
        html = run_filter(FIXTURES / "derivations.md", **{"fitch-html": False}).stdout
        self.assertNotIn("fitch-row", html)

    def test_latex_output_is_untouched(self):
        tex = run_filter(FIXTURES / "derivations.md", to="latex").stdout
        self.assertEqual(tex.count(r"\begin{nd}"), 13)
        self.assertIn(r"\open[x_0]", tex)
        self.assertNotIn("fitch-row", tex)

    def test_stated_purpose_and_taut(self):
        r = rows(self.parts["purposes"])
        self.assertEqual(r[1]["just"], r'<span class="fitch-purpose">asm, for \(\rulename{{{\to}}I}\)</span>')
        self.assertTrue(r[1]["assumption"])
        self.assertEqual([r[4]["just"], r[5]["just"]], ["", ""])        # nothing inferred by default
        self.assertEqual(r[9]["just"], r"\(\rulename{TAUT}\)")           # \by{TAUT}: a rule name
        self.assertNotIn("fitch-purpose", self.parts["nested"])

    def test_inferred_purposes(self):
        parts = sections(run_filter(FIXTURES / "derivations.md", **{"fitch-purposes": "infer"}).stdout)
        purpose = r'<span class="fitch-purpose">asm, for \(\rulename{%s}\)</span>'
        r = rows(parts["purposes"])
        self.assertEqual(r[1]["just"], purpose % r"{{\to}}I")             # stated: kept
        self.assertEqual([r[4]["just"], r[5]["just"]], [purpose % "RAA"] * 2)   # both assumptions of the box
        self.assertEqual(r[0]["just"], "")                               # a premise has none
        r = rows(parts["nested"])
        self.assertEqual([r[2]["just"], r[4]["just"]], [purpose % r"{{\to}}I"] * 2)
        r = rows(parts["siblings"])
        self.assertEqual([r[1]["just"], r[3]["just"]], [purpose % r"{\vee}E"] * 2)
        r = rows(parts["flagged"])
        self.assertIn("fitch-purpose", "".join(x["just"] for x in r))

    def test_latex_purposes_only_when_inferred(self):
        tex = run_filter(FIXTURES / "derivations.md", to="latex").stdout
        self.assertEqual(tex.count(r"\purpose"), 1)                      # the stated one
        tex = run_filter(FIXTURES / "derivations.md", to="latex", **{"fitch-purposes": "infer"}).stdout
        self.assertIn(r"\hypo {5} {\neg Q} \purpose{\raa}", tex)
        self.assertIn(r"\hypo {6} {P} \purpose{\raa}", tex)
        self.assertIn(r"\hypo {3} {P} \purpose{\ii}", tex)
        self.assertIn(r"\hypo {2} {P} \purpose{\ii}", tex)                # not doubled
        self.assertNotIn(r"\purpose{\ii} \purpose", tex)
        self.assertNotIn(r"\hypo {1} {P \to Q} \purpose", tex)
        self.assertEqual(tex.count(r"\begin{nd}"), 13)

    def test_mathrm_without_a_rulename_macro(self):
        html = run_filter(FIXTURES / "derivations.md", **{"fitch-rulename": False}).stdout
        self.assertIn(r"\(\mathrm{{\wedge}E}\) 1", html)
        self.assertNotIn(r"\rulename", html)


SECTION = r"""# Derivations

```{=latex}
\begin{center}
% schema
$\begin{nd}
  \hypo {1} {P}
  \open[x_0]
  \hypo {2} {Q(x_0)}
  \have {3} {P \wedge Q(x_0)} \ai{1,2}
  \close
\end{nd}$
\end{center}
```

::: {#exr-derivation}
[Derive]

Fill in the justification.

```{=latex}
\begin{center}
$\begin{nd}
  \hypo {1} {P \wedge Q}
  \have {2} {Q} \by{(i)}{}
\end{nd}$
\end{center}
```
:::

::: {.solution}
```{=latex}
\begin{center}
$\begin{nd}
  \hypo {1} {P \wedge Q}
  \have {2} {Q} \ae{1}
\end{nd}$
\end{center}
```
:::

```{=latex}
\begin{center}
Not only a derivation: $\begin{nd}
  \have {1} {a < b}
\end{nd}$
\end{center}
```
"""


def prepare_book(book_dir: Path, config: dict):
    (book_dir / "latex").mkdir(exist_ok=True)
    shutil.copy(STY, book_dir / "latex" / "fitch-book.sty")
    macros = book_dir / "macros.tex"
    macros.write_text(macros.read_text() + "\n\\providecommand{\\rulename}[1]{\\mathrm{#1}}\n")
    book_json = book_dir / "book.json"
    data = json.loads(book_json.read_text())
    data.update(config)
    envs = data["environment_settings"]
    if not any(e.get("prefix") == "exr" for e in envs.get("big_envs", [])):
        envs["big_envs"].append({"prefix": "exr", "name": "Exercise", "numbered": True,
                                 "counter_group": "main", "color": "#2f62b5"})
    book_json.write_text(json.dumps(data, indent=2))
    refs = book_dir / "src" / "ch02-more" / "01-refs.md"
    refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))
    (book_dir / "src" / "ch02-more" / "04-derivations.md").write_text(SECTION)


class TestFitchHtmlBuild(FixtureBookCase):
    """The default for a book that ships fitch-book.sty: derivations are HTML."""

    @classmethod
    def prepare(cls, book_dir: Path):
        prepare_book(book_dir, {})

    def test_derivations_are_html(self):
        page = self.page("ch02-more/04-derivations.html")
        self.assertEqual(page.count('<div class="fitch" role="table"'), 3)
        self.assertNotIn(r"\begin{nd}", page)
        self.assertNotIn("data-mjx-error", page)

    def test_inside_an_exercise_and_its_solution(self):
        page = self.page("ch02-more/04-derivations.html")
        exercise = page.index('id="exr-derivation"')
        solution = page.index("solution", exercise)
        self.assertIn('class="fitch"', page[exercise:solution])
        self.assertIn('class="fitch"', page[solution:])

    def test_an_unreadable_block_stays_an_svg_with_a_warning(self):
        page = self.page("ch02-more/04-derivations.html")
        self.assertEqual(len(re.findall(r'<img\s+src="\.\./tikz/[0-9a-f]+\.svg"[^>]*alt="Derivation"', page)), 1)
        output = self.results[("html",)].stdout
        self.assertRegex(output, r"fitch-html: a derivation in src/ch02-more/04-derivations\.md stays an SVG")

    def test_styles_ship(self):
        css = (self.html / "styles.css").read_text()
        self.assertIn(".fitch-bar", css)
        self.assertRegex(css, r"\.fitch-bar \{[^}]*border-left: var\(--fitch-rule\) solid var\(--ink\)")


class TestFitchHtmlOff(FixtureBookCase):
    """"fitch-html": false keeps every derivation on the SVG path."""

    @classmethod
    def prepare(cls, book_dir: Path):
        prepare_book(book_dir, {"fitch-html": False})

    def test_derivations_are_svgs(self):
        page = self.page("ch02-more/04-derivations.html")
        self.assertNotIn('class="fitch"', page)
        self.assertEqual(len(re.findall(r'alt="Derivation"', page)), 4)
        self.assertNotIn("fitch-html", self.results[("html",)].stdout)


if __name__ == "__main__":
    unittest.main()
