# `latex/`

The LaTeX side of the engine: the preamble the PDFs are built from, and the four
style files it layers.

| file | what it holds |
|------|---------------|
| `preamble.tex` | the preamble for a per-section PDF |
| `preamble-book.tex` | the same, for the combined book PDF |
| `page-style.sty` | the page: base packages, geometry, the running-head frame, `\arraystretch` |
| `theorem-frame.sty` | the `bookframe` mdframed style, and the `mdthm` key that lets `\declaretheorem` use it |
| `latex-template.sty` | the book's macros, colours and helpers |
| `chapter-style.sty` | chapters, `\part` banners, running heads, the Contents |
| `theorem-envs.sty` | the environments `filters/theorems.lua` emits, framed and coloured from the config |
| `book-diagrams.sty` | TikZ styles for arrow and Hasse diagrams, trees, the square of opposition and flowcharts (also loaded by `build/tikz.py`'s template for the website) |
| `macros.tex` | the book's own macros, shared with the website (MathJax reads this file) |

Load order is fixed by `preamble.tex`: `page-style`, then `latex-template`, then
`chapter-style`, then `theorem-envs` (which pulls in `theorem-frame`). Later
files deliberately override earlier ones — see "Who owns what", below.

## `page-style.sty`

Everything in it is written against the public interface of the packages it
loads: `geometry`'s key-value margins, `fancyhdr`'s `\fancyhead`/`\fancyfoot`,
`parskip`, `array`'s `\arraystretch`. It does three things.

1. **Loads the packages every page needs**, once and in one place, so that no
   later `\usepackage` can raise an option clash: `inputenc`, `fontenc`,
   `lmodern`; `geometry`, `fancyhdr`, `footmisc`; `parskip`, `enumitem`,
   `xcolor`; `amsmath`, `amssymb`, `bm`; `caption`, `subcaption`; `array`,
   `booktabs`, `multirow`.
2. **Sets the page**: a uniform 2.5cm margin on all four sides. This is the one
   place the measure is decided — `preamble.tex` loads `geometry` with no
   options at all — and every line break in the book follows from the
   `\textwidth` it leaves.
3. **Puts the `fancy` page style in place** with the chapter mark on the right
   and the page number centred in the foot, and makes array rows 10% taller.

Three things are pointedly *not* in it:

- **`hyperref`**, which is loaded exactly once, by
  `templates/latex/template.tex`, after `latex/macros.tex` — it has to be,
  because it reclaims `\H`. Its options reach that load from `preamble.tex`
  through `\PassOptionsToPackage`.
- **`\headrulewidth`**, which `chapter-style.sty` owns along with the rest of
  the running heads.
- **the `parfill` option to `parskip`.** It sets
  `\parfillskip=30pt plus 1fil`: 30pt of glue at the end of every paragraph
  that can stretch but not shrink. That adds 30pt to the natural width of every
  single-line paragraph, turning lines that merely reached the margin into
  overfull boxes, and in at least one measured case removing the only feasible
  break so a formula ran into the margin. Measured over one book's 262 section
  PDFs: **290** overfull boxes without it, **357** with. Do not put it back.

`fontenc` is T1 and `lmodern` comes with it: T1 without a scalable T1 font falls
back to bitmapped Type 3 glyphs, and Latin Modern is the standard Type 1 answer,
metric-compatible with Computer Modern. T1 also moves the caron from slot 20
(where OT1 keeps it) to slot 7, which matters to any book that reaches a caron
through `\accent` — see the `\DeclareUnicodeCharacter` lines in
`latex-template.sty`.

## `theorem-frame.sty`

Two things, written from the `mdframed` and `thmtools` manuals.

1. **`\mdfdefinestyle{bookframe}`** — the box the environments wear: a 0.25em
   rule in `black!10`, `roundcorner=0.15em`, half an em of padding on every
   side, `skipabove`/`skipbelow` of `\topskip`, a title bar in the same grey as
   the rule, and `theoremseparator={.}` so a box reads "Theorem 1.2.3. Rank–
   nullity". Lengths are in em, so a box scales with the type around it.
   `theorem-envs.sty` derives `bookenv` from it with `nobreak=false` (a single
   proof can be longer than a page) and the book's split skips, then one style
   per environment with the colour from `config/config.json`.
2. **the `mdthm` key for `\declaretheorem`.** `thmtools` builds each environment
   by calling `\thmt@theoremdefiner`, which is `\newtheorem` unless a key in the
   `thmdef` family says otherwise; `mdframed`'s `\mdtheorem` has `\newtheorem`'s
   signature with a leading optional argument of `mdframed` keys, so the key
   hands that argument over whole. (`thmtools` adds its own `thmbox` key exactly
   this way.) This is *not* `thmtools`' own `mdframed` key: that one wraps an
   already-defined theorem in `\begin{mdframed}`, leaving the head inside the
   box as running text, where `\mdtheorem` gives the head to `mdframed` as a
   frametitle — which is what puts the name and the number in the tinted bar.

It also adds `\parskip` to the pre-skip of amsthm's three built-in theorem
styles, by appending to the `\th@<style>` macro amsthm stores each style in: a
theorem sitting between two paragraphs should stand off the text by at least the
distance two paragraphs stand off each other.

## Who owns what

The later file wins, deliberately, and each of these is the single place its
setting is decided:

| setting | owner |
|---------|-------|
| page size and margins | `page-style.sty` |
| `\headrulewidth`, the head fields, `\parskip`, `\parindent` | `chapter-style.sty` |
| `hyperref` | `templates/latex/template.tex`, with options from `preamble.tex` |
| `\qedsymbol` | `latex-template.sty`, **outside** its `skipenv` block — `theorem-envs.sty` calls `\qed` and sets no symbol, so a `\qedsymbol` hidden inside the block would silently give amsthm's hollow box at the end of every proof in the book |
| which environments exist, their names, counters and colours | `config/config.json`, via `_build/tmp/environments.tex` |

## History

`page-style.sty` and `theorem-frame.sty` replace `latex/sleek/`, which vendored
two files from a third party's LaTeX style. The upstream repository named in
that directory's README returned 404 and neither file carried a licence
statement, so the terms they were offered under could not be established, and
the repository's `LICENSE` had to carve the directory out of its own terms.
These two files are written from the documentation of the packages underneath —
`geometry`, `fancyhdr`, `parskip`, `mdframed`, `thmtools` — and are covered by
the repository's own licence like everything else in the tree. The rendered
output did not change: same page count, same numbering, same overfull-box count,
the same boxes on the page.
