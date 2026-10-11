# Build Commands

Use `./build.py <command>` from the book's root: the book's own `build.py` (a copy of
`starter/build.py`) finds the engine in `engine/` or `$BOOK_ENGINE` and builds that book.
From the engine checkout, `./build.py <command> --book DIR` (or `cd DIR && ../build.py`)
builds any book; the demo book is `starter/`.

## Everyday

| Goal | Command |
|------|---------|
| Live preview while writing | `./build.py serve` (`--port 8000`) |
| Build the website | `./build.py html` |
| Build one page | `./build.py html src/ch00-demo/01-every-environment.md` |
| Build per-section PDFs | `./build.py pdf` (or one file, as above) |
| Build the combined book PDF | `./build.py book` |
| Build everything | `./build.py all` |
| Remove `_build/` | `./build.py clean` |

`html` and `pdf` skip pages whose inputs are unchanged: the source file, the filters,
templates, config and macros, the page's previous/next pages, and the numbers and titles
of the labels it references. `clean` forces a full rebuild.

`serve` builds the site, serves `_build/html` on http://127.0.0.1:8000, and rebuilds when
anything in `src/`, `filters/`, `templates/html/`, the config or the macros changes. Open
pages reload by themselves. Pages built by `serve` contain the reload script; the next
`html` or `deploy` rebuilds them without it.

## Checks

| Goal | Command |
|------|---------|
| Verify required tools (pandoc, pdflatex, pdftocairo); show the engine in use | `./build.py doctor` |
| Validate references, links, web vs PDF numbering, and every check | `./build.py check` |
| Run the engine tests | `python3 -m unittest discover -s engine/tests` (in the engine repo: `-s tests`) |
| Run the book's tests | `python3 -m unittest discover -s tests` |
| Lint the built HTML and LaTeX logs | `python3 engine/tools/check_rendered.py` |

`check` fails on unresolved `@refs`, duplicate labels, cross-reference links in `_build/html`
that point nowhere, component problems, any label whose number in the PDFs differs from
the website, a proof, claim or written solution citing a result marked `.optional`
(`tools/check_optional.py`), and a proof, proof idea or claim citing a result proved in a
later section (`tools/check_forward_deps.py`; a forward pointer from an example, exercise,
remark, warning or statement is a signpost and allowed -- `--signposts` lists them). Run it
after `./build.py all`, since the numbering comparison reads the LaTeX `.aux` files.
`deploy` runs `all` and `check` first and stops if either fails.

`check` also warns (without failing) about:

- **Spelling** (needs `aspell`): words in the prose, not in formulas or code. Add correct
  terms to `spelling.txt` in the book directory, one per line.
- **Named results without a reference**: a proof that says "by the Basis Extension Theorem"
  instead of `@thm-basis-extension`. A reference gives readers a link and a preview and makes
  the dependency graph exact.

**Accepted unresolved references.** A reference into a section that is planned but not yet
written can be listed in `config/known-unresolved.json` (or the file the config key
`known-unresolved` names), with a reason:

```json
[{"why": "Chapter 9 not written yet",
  "references": [{"ref": "thm-spectral", "in": "src/ch04-maps/02-kernels.md"}]}]
```

`check` then fails only on new unresolved references, and warns about an entry that no
longer occurs (delete it, or it would excuse the same reference breaking again).

**Book-specific checks (plugins).** The config's `checks` list adds checkers to `check`:

```json
"checks": [
  {"tool": "tools/check_structure.py", "fatal": true, "requires": "authoring/STYLE.md"},
  {"tool": "tools/check_numbers.py", "fatal": false, "requires": "verify", "prefix": "numbers"},
  "engine:check_macros",
  {"tool": "engine:check_rendered", "options": {"overfull": false}}
],
"checks-disable": ["forward-deps"]
```

- `tool`: a path relative to the book (the book's own checker), or `engine:<name>` for
  one of the engine's `tools/<name>.py`. A plain string is short for `{"tool": ...}`.
- `fatal` (default `true`): its errors fail `check`; `false` reports them as warnings.
- `requires`: a file or directory in the book; the check is skipped when it is missing.
- `options`: passed to `run` as a third argument. `prefix`: put before each reported line.
- Protocol: the module defines `run(book, labels) -> (errors, warnings)` (or
  `run(book, labels, options)`), where `book` is `build.book.Book` (`book.root`,
  `book.src_dir`, `book.build_dir`, `book.config`, `book.pages`) and `labels` the label
  index. A module with only `find_violations(labels)` and `report(violations)` is run
  through those. A plugin's directory and its parent are on `sys.path` while it loads.
  A missing or crashing plugin is a `check` error.
- `checks-disable` turns off the engine's default checkers (`optional`, `forward-deps`)
  or a built-in rule (`xref-links`, `moved-ids`, `components`, `numbering`,
  `title-mentions`, `spelling`) -- a switch for bringing a book into line in steps, not a
  setting to leave on.

Engine checkers available as `engine:<name>`:

- `check_macros` -- retired and undefined macros in `src/` and the notation guides.
  Settings in the config's `macro-check`: `retired` (macro names), `retired-hint`,
  `guides` (e.g. `["authoring/NOTATION.md"]`), `retired-only` (files that get only the
  retired rule), `zero-matrix` (e.g. `"\\O"`: the zero matrix may not be written
  `\cvec{0}`). The definedness rule asks MathJax configured as the build configures it.
- `check_rendered` -- the built HTML (raw TeX or `\qedhere` in prose, `??`, MathJax errors,
  visible `:::` fences, `\|` in code) and the LaTeX logs (undefined control sequences,
  missing characters; overfull boxes as one warning).

## Writing

- Environments: `::: {#thm-name}` … `:::` (prefixes and counters in `environment_settings` in
  the config), small environments `::: {.proof}`. Environments nest. Each numbered
  environment has one `color`; the website derives the box's rule and background tint from
  it, for both light and dark mode.
- References: `@thm-name`, `@eq-name`. Numbered targets read "Theorem 1.2.3"; unnumbered
  ones (examples) read "Example (Title)".
- Equations: `\[ … \]{#eq-name}`.
- Labeled lists: `::: {.enumerate options="label=(VS\arabic*)"}` around a numbered list.
- Figures: TikZ or tikz-cd (e.g. exported from quiver) as raw LaTeX. The PDF uses it directly;
  the website gets an SVG compiled once and cached in `_build/cache/tikz/`.
- Macros: add them to `latex/macros.tex` (`\def`, `\newcommand`, `\providecommand`,
  `\DeclareMathOperator`). The website's MathJax macros are generated from this file.

## Math rendering

Formulas are rendered when the site is built (MathJax 3.2.2 under Node, `build/math.py`), so
pages show finished math immediately and load no math script. Tooltip previews and the list
of results are rendered too; search snippets load MathJax only when needed. MathJax is
downloaded once into `~/.cache/book-engine`. Without `node`, or without network access for
that download, the site falls back to rendering math in the browser; set
`"prerender-math": false` in the config to always do that. Unknown macros are reported as
build warnings.

## Generated pages

- `results.html`: every definition, theorem and example, grouped by chapter and section,
  with filters and previews.
- `graph.html`: dependency graph of the chapters. An arrow from one chapter to another
  means a *proof* in the second uses a result from the first, and its width counts those
  proofs. Citations made outside a proof -- a statement, a remark, an exercise, a written
  solution -- are carried as "soft" and shown on hover rather than drawn, as is any
  dependency a longer chain already implies. A picker computes the reading path of any one
  section and dims the chapters it never reaches.
- `paths.html` and one `path-<slug>.html` per reader profile: the sections a reader needs
  in order to reach the results that profile aims at, in reading order, with what can be
  skipped. Profiles are declared in the config under `reading-paths`; the closure is
  computed from the book's own proofs at build time. **A path that is not closed -- one
  whose sections do not carry all their own prerequisites -- fails the build.**
  `python3 tools/reading_path.py --help` is the same machinery on the command line.

## Reader features (no configuration)

Solutions start folded and proofs can be folded; visited sections get a check mark and the
start page offers "Continue reading"; ← and → go to the previous and next page; `/` opens
search; the toolbar folds the side panes and switches light/dark; on touch screens a tap on
a reference opens its preview. With `issues-url` set, each page links to a prefilled
"Report a typo" issue.

## Interactive components

Each component has a web form and a print form, so the PDF never has gaps. Pages without
components load no extra JavaScript. `./build.py check` reports bad plot expressions,
widgets without print content and missing widget files.

**Runnable Python cell**

````
```{.python .run #cell-eigen packages="numpy"}
import numpy as np
np.linalg.eigvals(np.array([[2, 1], [1, 3]]))
```
````

- Web: an editable cell with a Run button (Shift+Enter in the editor). Python runs in the
  reader's browser via Pyodide, downloaded on the first Run. Cells on a page share one
  namespace, and running a cell first runs earlier cells that have not run. Imports of
  bundled packages (numpy, scipy, sympy, pandas, matplotlib, networkx, statsmodels,
  scikit-learn, ...) load automatically; `packages` is only needed for packages that are
  not imported by name. matplotlib figures are shown as images. Stop ends a long run.
- PDF: a code listing, followed by a link to the cell online when `deploy-domain` is set.

**Function plot**

```
::: {.plot fn="sin(a*x); cos(x)" x="-6.28,6.28" y="-2,2" params="a=1:0..3"}
Optional caption.
:::
```

- `fn`: one or more expressions separated by `;`. Allowed: numbers, `x`, parameters, `pi`,
  `e`, `+ - * / ^`, parentheses, `sin cos tan asin acos atan sinh cosh tanh exp log sqrt abs`
  (`log` is natural, angles in radians). Multiplication must be written (`2*x`).
- `x`: range (default `-5,5`). `y`: range (default: chosen from the curves).
- `params`: `name=default:min..max`, comma-separated; each gets a slider.
- Web: JSXGraph. PDF: pgfplots with each parameter at its default.

**Widget** (custom JavaScript)

```
::: {.widget src="widgets/linear-map.js" matrix="2,1,0,1"}
::: {.print}
What the PDF shows instead (text, or a TikZ figure).
:::
:::
```

- `src` is a JavaScript module in the book's `widgets/` directory, or one of the engine's
  (`widgets/linear-map.js`: the image of the unit square under a 2×2 matrix whose column
  vectors can be dragged). Its default export is called as
  `mount(element, options, { loadJSXGraph, ensureId, COLORS })`, where `options` holds the
  div's other attributes. The print content is shown until the widget has mounted.
- PDF: only the `::: {.print}` content.

## Books and the engine

The engine (`build/`, `filters/`, `templates/`, `latex/*.sty`, `tools/`, `widgets/`) builds
any book directory. A book directory contains `book.json` (or `config/config.json`), its
Markdown sources and a macro file. Paths in the config are relative to the book directory,
and output goes to its own `_build/`. To change a template or style for one book, put a
file at the same relative path in the book directory (e.g. `templates/html/styles.css`,
`latex/theorem-frame.sty`); it takes precedence over the engine's copy. `starter/` is a
complete book; `tests/fixture-book/` a minimal one.

A book pins the engine as a git submodule in `engine/` and runs it through its own
`build.py` (copy `starter/build.py`): the engine is `$BOOK_ENGINE` if set (a working copy,
to try an engine change), else `engine/`. After a clone or in a new worktree, run
`git submodule update --init`.

Config keys: `title`, `author`, `chapters` (directory strings, or `{"dir": …, "title": …,
"part": …}`; the title defaults to the chapter's `index.md` heading), `src` (default `src`),
`preface` (default `src/index.md`), `macros`, `environment_settings`, `output`, `templates`,
`styles`, `repo-url` (optional source link in the sidebar), `source-branch` (default
`main`, for that link), `issues-url` (optional, e.g.
`https://github.com/USER/REPO/issues/new`, for the "Report it" link), `prerender-math`
(default true), `reading-paths`, `mention-exempt-titles`, `redirects`, `deploy-dir`,
`deploy-repo`, `deploy-domain`, `deploy-push-url`, and:

- `site-url` -- the address the site is published at when it is not the root of
  `deploy-domain`, e.g. `https://example.org/library/analysis/`. Canonical links, the
  sitemap and the PDF's links to runnable cells are built on it; under a sub-path the
  book writes no `robots.txt` and its `404.html` links from that path.
- `external-books` -- other books this one cites as `@prefix:label`:

  ```json
  "external-books": {
    "la": {"title": "Linear Algebra", "short": "LA",
           "url": "../linear-algebra/",
           "labels": "../linear-algebra/_build/crossref_labels.json"}
  }
  ```

  `labels` is that book's registry: its `_build/crossref_labels.json`, or the
  `labels.json` every build publishes at its site root, as a path or an http(s) URL
  (fetched once per build, cached). In text `@la:thm-x` reads "Linear Algebra, Theorem
  12.4"; bracketed `[@la:thm-x]` reads "[LA, Theorem 12.4]" (`format` / `short-format`
  change that). Links carry the other book's hover preview, fetched from its site (same
  origin, or a site that allows cross-origin reads). An unknown label fails `check`; an
  unreadable registry is a warning and the reference prints without a number. Citations of
  another book are not dependencies here: they never count as forward or in a reading path.
- `moved-ids` -- anchors that moved to another page keep their deep links:
  `{"ch13-x/06-old.html": {"thm-a": "ch13-x/07-new.html", "thm-b": "ch13-x/07-new.html#thm-c"}}`.
  The old page forwards `#thm-a` while it no longer has that id; `check` fails on an entry
  that leaves from an id still there or points nowhere. (A page that is gone entirely:
  `redirects`, whose stubs keep the fragment too.)
- `known-unresolved`, `checks`, `checks-disable`, `macro-check` -- see "Checks".

**Config overlay.** `./build.py html --config-overlay preview.json` (any command) builds
with config keys overridden from a JSON file, without editing the book's config. The
overlay is merged as a JSON Merge Patch: objects merge key by key (so
`{"external-books": {"la": {"url": "../la/"}}}` changes only that book's `url`), `null`
removes a key (`{"deploy-domain": null}`), and any other value, lists included, replaces
the config's. The overlay counts as part of the config for the "unchanged page" check, so
a build with a different overlay (or none) rebuilds the affected pages. `serve` re-reads
the overlay file when it changes.

Fitch-style derivations: a book that ships `latex/fitch-book.sty` (defining the `nd`
environment) gets it loaded in every preamble, and `\begin{nd}` in a raw LaTeX block is
compiled to an SVG for the web like a TikZ picture. Without that file nothing changes.

## Automatic deploys

`starter/.github/workflows/build-and-check.yml` builds, tests and checks a book on every
push (checking out the `engine/` submodule); it does not publish -- deploys run from the
author's machine (`DEPLOY.md`). The engine's own `.github/workflows/engine.yml` runs the
engine tests and builds and checks `starter/`.

## Other

| Goal | Command |
|------|---------|
| Scan labels only | `./build.py scan` |
| Regenerate tooltip data only | `./build.py manifest` |
