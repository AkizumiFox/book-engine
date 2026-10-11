# Book engine

The Pandoc + Python engine the textbooks of this series are built with (linear algebra,
analysis, foundations, regression). One source — Pandoc Markdown in a book's `src/` —
becomes both a website and a set of PDFs, with numbered environments, cross-references
(also into other books), hover previews, a dependency graph and reading paths.

This repository is the engine only, plus `starter/`: the demo book a new book is copied
from, which is also how the engine is tested end to end. A book does not contain the
engine; it pins it as a git submodule in `engine/` and carries a ~20-line `build.py`.

| Task (in a book) | Command |
|---|---|
| Write with live preview | `./build.py serve` → http://127.0.0.1:8000 (rebuilds and reloads on save) |
| Build the HTML site | `./build.py html` |
| Build the book PDF | `./build.py book` (writes `_build/pdf/book.pdf`) |
| Everything | `./build.py all` |
| Validate references, numbering, and every check | `./build.py check` |
| Run the engine's tests / the book's tests | `python3 -m unittest discover -s engine/tests` / `-s tests` |
| List the signposts (allowed forward pointers) | `python3 engine/tools/check_forward_deps.py --signposts` |
| Work out what a reader needs | `python3 engine/tools/reading_path.py --list-profiles`, then `--profile <slug>` |
| Lint what the reader sees (HTML, LaTeX logs) | `python3 engine/tools/check_rendered.py` |
| Check the external tools are installed | `./build.py doctor` (also says which engine runs) |
| Publish | `./build.py deploy --push` (see `DEPLOY.md`) |

`BUILD.md` is the full command, syntax and config reference. This file is the orientation.

| Task (in this repository) | Command |
|---|---|
| Engine tests (fixture books) | `python3 -m unittest discover -s tests` |
| Build and check the demo book | `cd starter && ./build.py all && ./build.py check` |
| The demo book's own tests | `cd starter && python3 -m unittest discover -s tests` |

## Using the engine in a book

A book repository holds only what is its own:

```
build.py              the shim (copy of starter/build.py)
engine/               git submodule: this repository, pinned to a commit / tag
config/config.json    the book's settings
latex/macros.tex      the book's macros (plus any latex/*.sty override)
src/                  the book
authoring/            the writing standard and notation guide
tests/                the book's tests (copy starter/tests/ to start)
tools/                the book's own checkers, run by `check` through "checks"
.github/workflows/    starter/.github/workflows/build-and-check.yml
```

- **Add the engine:** `git submodule add https://github.com/AkizumiFox/book-engine.git engine`
  (https, so CI clones it without a key), then `git -C engine checkout v1.0.0-rc1` and
  commit the pointer. The pointer is the version the book builds with; each branch can
  pin its own.
- **A fresh clone or a new worktree** needs `git submodule update --init`; the shim
  says so when `engine/` is empty. CI needs `submodules: true` on `actions/checkout`.
- **Try an engine change on a book before pinning it:** `BOOK_ENGINE=~/coding/book-engine
  ./build.py all` builds the book with that working copy instead of `engine/`. When it is
  right, commit and tag the engine, then move the book's pointer
  (`git -C engine fetch && git -C engine checkout <tag>`, commit `engine`).
- **Override a template or style for one book:** put a file at the same relative path in
  the book (`templates/html/styles.css`, `latex/theorem-frame.sty`, ...); it takes
  precedence over the engine's copy, in HTML and in LaTeX.
- **Book-specific checks** are the book's own scripts in `tools/`, listed in the config:
  `"checks": [{"tool": "tools/check_structure.py", "requires": "authoring/STYLE.md"},
  "engine:check_macros"]`. Each defines `run(book, labels) -> (errors, warnings)`.
  `"checks-disable"` turns off an engine check while a book is being brought into line.
  See "Checks" in `BUILD.md`.
- **References into another book:** `@la:thm-spectral` with an `external-books` entry for
  `la` (see `BUILD.md`); hover previews work across books on one origin.

## What the engine does

Each Markdown section goes through Pandoc twice — once to HTML, once to LaTeX — with the
same Lua filters both times, so the two editions cannot drift apart. The filters turn
fenced divs into numbered environments, resolve `@label` cross-references, number
equations, and compile TikZ pictures to SVG for the web (cached) while passing them
through untouched to the PDF. `latex/macros.tex` is parsed into a MathJax macro table, so
a macro defined once works in both formats. Math is rendered at build time under Node,
so pages arrive finished and load no math script.

On top of that the build generates a search index, a list of every result, a dependency
graph of which result uses which, hover previews for every reference, and a reading-path
page per reader profile (see "Reading paths" below).

Three gates keep the book honest, and all three must pass:

- **`./build.py all`** — a LaTeX error fails the build. `pdflatex` runs in nonstopmode and
  writes a PDF even after an error, so success is judged by the error lines in the log,
  not by the file existing. (Before this gate existed, 38 sections shipped damaged.)
- **`./build.py check`** — unresolved `@refs` (here and into other books), duplicate
  labels, cross-reference links pointing nowhere, any label whose number in the PDF
  differs from its number on the web, any proof that rests on a result marked
  `.optional`, any proof, proof idea or claim that cites a result proved later, and
  whatever the book adds through `checks`. It also warns, without failing, about
  spelling and about a named result mentioned in prose without a reference.
- **The tests** — the engine's own (`engine/tests`, which build the fixture books end to
  end) and the book's (`tests/`, from `starter/tests/`): no blank line inside a display,
  no non-ASCII character inside a math span, no proof that belongs to no result, and the
  gates and reading paths on the built book.

## Start a book

1. **Copy the starter.** `cp -r starter ~/coding/my-book && cd ~/coding/my-book && git init`,
   then add the engine: `git submodule add https://github.com/AkizumiFox/book-engine.git engine`
   and pin it (`git -C engine checkout v1.0.0-rc1`). `./build.py doctor` should name
   `engine/` as the engine.
2. **Set the config keys.** `config/config.json` lists them under `_TODO`:
   `title`, `author`, `repo-url`, `issues-url`, `deploy-repo`, `deploy-domain`,
   `deploy-push-url`. The deploy keys can stay empty until there is something to publish;
   `DEPLOY.md` explains them. Leave `environment_settings` alone unless the book really
   needs a different set of environments — it is the shared inheritance of the existing
   books, and changing a colour or a counter group later means rebuilding everything.
3. **Read the demo chapter, then delete it.** `src/ch00-demo/01-every-environment.md` is
   a working page that uses every environment, cross-reference, display, table, figure and
   exercise group the engine offers, each introduced by a line saying what it is for and
   what its markup is. Read the built page next to the source. When you no longer need it:
   `rm -rf src/ch00-demo` and remove its entry from `chapters`.
4. **Rewrite `src/index.md`**, the preface, which is the site's start page.
5. **Write sections** as `src/chNN-name/NN-title.md`. See the next section for how the
   numbers come out, and `authoring/STYLE.md` for how to write one.
6. **Raid `latex/macros-linear-algebra.tex.example`** for the macros this book needs and
   paste them into `latex/macros.tex`. Nothing loads the example file; it exists so the
   next book can take what it wants without inheriting 400 lines of someone else's
   notation. Record each macro you keep in `authoring/NOTATION.md`.
7. **Grow `spelling.txt`** as you write. It starts with a dozen general words on purpose.

## Where the numbers come from

Nothing is numbered by hand. Everything is derived from names on disk.

- **Chapter number:** the digits in the chapter directory name. `src/ch07-block-matrices/`
  is Chapter 7. A directory whose name does not start with `chNN` falls back to its
  position in the `chapters` list.
- **Chapter order:** the order of the `chapters` array in `config/config.json`, not
  alphabetical order. A chapter not listed there is not built.
- **Chapter title:** the `# ` heading of the chapter's `index.md`, unless the `chapters`
  entry gives an explicit `"title"`.
- **Section number:** the position of the file among its chapter's `*.md` files in
  **sorted filename order**, counting from 1 and ignoring `index.md`. So
  `src/ch07-block-matrices/03-schur.md` is section 7.3 — as long as no file sorts between
  them. This is why every filename starts with a two-digit number. To insert a section
  between 03 and 04, renumber; to keep old URLs alive, add a `redirects` entry.
- **Section title:** the file's `# ` heading. It becomes the navigation link, the page
  title, the PDF bookmark and the running head, so it carries no mathematics.
- **Result number:** *chapter.section.serial*, where the serial runs per counter group per
  section. Theorems, lemmas, corollaries and propositions share the `main` counter;
  definitions have their own; examples, exercises and conjectures are unnumbered and are
  cited by title.
- **Parts** are cosmetic: a `"part"` key on a chapter entry starts a new part banner there.

## Reading paths

The build knows which environment made every citation — a proof, a proof idea and a claim
are *hard*, a statement, a remark, an exercise or a written solution are *soft* — so it can
answer the question a reader actually asks: **if I want that theorem, what must I read
first?** Following the hard citations backwards from a section gives the smallest set of
sections whose proofs are all complete, and nothing else.

A **reader profile** is a name and a handful of target sections. Declare them in
`config/config.json` under `reading-paths`, which is the whole interface — no code:

```json
"reading-paths": [
  {
    "slug": "example",
    "name": "The worked section",
    "description": "One sentence naming what this reader is after, in their language.",
    "targets": ["ch00-demo/01"]
  }
]
```

- `slug` — lowercase letters, digits and hyphens. It names the page, `path-<slug>.html`.
- `targets` — sections written the way the files name them, `<chapter directory>/<section
  number>`: `ch07-block-matrices/03`, or `ch07-block-matrices/index` for a chapter's index
  page. **Choose the sections, not the chapters**; a chapter-level answer is roughly twice
  as long, and it is a section that a reader actually turns to.

Pick each target by reading what the section *contains*, not by its title: the target is
the result this reader came for. Two or three to half a dozen per profile is the usual
shape, and a profile whose path is nearly the whole book is telling you it is aimed too
broadly.

Each build then writes `paths.html`, listing every profile with its two lengths, and one
`path-<slug>.html` per profile giving the sections in reading order, what can be skipped,
and where the path hangs on a single proof. The two lengths are the same path counted two
ways: the reading path, and the path for a reader who also works the exercises, since a
written solution is the proof of its exercise. Nothing here picks one for the reader.

**Every generated path is checked before it is written, and an unclosed path fails the
build.** Closed means every result a proof on the path uses is proved by another section
on the path. That is the whole point: a path with a gap in it is worse than no path.

On the command line, without building the pages:

```
python3 engine/tools/reading_path.py --list-profiles
python3 engine/tools/reading_path.py --profile example
python3 engine/tools/reading_path.py ch00-demo/01 --with-exercises --weakest 2
python3 engine/tools/reading_path.py ch00-demo/01 --verify
```

`--weakest N` lists the sections the path pulls in on at most N hard citations, with the
citing sites. Those are the cheap prunes: reword or move one citation and the section, and
everything only it needed, leaves the path.

The demo profile above ships with the starter and aims at the one section the starter
has. It is an example of the *shape*, not of the content — replace it with this book's
readers before the second chapter exists, and delete it along with `src/ch00-demo/`.

## The standing rules

The books built on this engine follow these. They are worth keeping, because each one
was adopted after the alternative caused a mess.

- **A result is either proved from earlier material, or marked plainly as not proved
  here.** One sentence in the place it is used, in the reader's own language. There is no
  third option, and a gap that is not marked is a lie to a reader working alone.
- **No proof rests on an exercise.** The text may not lean on something the reader was
  asked to do. Exercises may cite the text, and a later exercise may cite an earlier one.
- **No forward references.** A proof cites only what appears earlier in the book. A
  forward pointer from an example, an exercise, a remark or a statement ("we will prove
  this in Chapter 9") is a signpost and is fine, as long as it is never a step in an
  argument. `./build.py check` fails if a proof, proof idea or claim cites a later
  section; `python3 engine/tools/check_forward_deps.py --signposts` lists the signposts.
- **A result marked `.optional` may be cited, but never proved from.** Writing
  `::: {#thm-foo .optional}` prints "Optional: nothing later depends on this" in both
  editions and takes the result off every reading path. A remark, a statement or an
  exercise may point at it; a proof, a proof idea, a claim or a written solution may not,
  and `./build.py check` fails if one does.
- **Section titles carry no mathematics.** They become links, bookmarks and running heads.
- **One notation per idea, fixed in `authoring/NOTATION.md` before first use.** A second
  notation for the same thing costs a whole-book pass to retire.
- **Every macro lives in `latex/macros.tex`**, so the PDF and the website agree. Nothing
  ad hoc in a section file.

`authoring/STYLE.md` is the full writing standard; `authoring/DRAFTING.md` is the brief
handed to a drafting agent.

## The two traps

Both of these have cost real time in this project. They are not obvious and they do not
announce themselves.

**1. The display-width harness needs a fresh Chrome profile.**

`authoring/measure-displays.md` drives headless Chrome over the built site to find
formulas that overflow the text column. Chrome caches the pages in its user-data
directory, so re-running with the same `--user-data-dir` after an edit happily re-reports
the *old* widths. An "after" measurement taken that way is a lie, and it will tell you a
formula you just fixed is still broken — or, worse, that a formula you just broke is
fine. `rm -rf "$S/measure"` before every run. Two related traps are in the same file: a
row at exactly 100% is a `\tag` artifact and not an overflow, and a site whose math was
never prerendered measures as perfectly clean because there is nothing to measure.

**2. `\qedsymbol`-style definitions must sit outside the `skipenv` block.**

`latex/latex-template.sty` takes a `skipenv` option, and `latex/preamble.tex` passes it:
it means "define no theorem styles, boxes or environments here", because
`latex/theorem-envs.sty` owns all of those and builds them from the config. The block
between `\if@skipenv\else` and `\fi` is skipped entirely under that option.

Anything the environments *use* but do not *define* must therefore live outside the block.
`\qedsymbol` is the example: `latex/theorem-envs.sty` ends every proof with `\qed` but
sets no symbol, so moving `\renewcommand{\qedsymbol}{$\blacksquare$}` inside the block
would not raise an error — it would silently give amsthm's hollow box at the end of every
proof in the book, which is the kind of thing nobody notices until the PDF is printed. The
comment at that line in `latex-template.sty` says so. Heed it for anything similar: a
shared colour, a length, a helper macro an environment body calls.

## Layout

- `build/` — the Python build (`cli.py` is the command line; `plugins.py` the `checks`
  hook; `external.py` references into other books).
- `filters/` — the Lua filters both formats go through.
- `templates/` — the HTML page, its script, styles and fonts, and the LaTeX template.
- `latex/` — the preamble and the style files the PDFs are built from (no book macros:
  those are the book's `latex/macros.tex`). `latex/README.md` says what is in them and
  who owns what.
- `tools/` — checkers usable by hand and from `check` (`check_optional`,
  `check_forward_deps`, `check_macros`, `check_rendered`), the reading-path tool and the
  display-width harness (`_measure.html`).
- `widgets/` — JavaScript modules available to `::: {.widget}`.
- `tests/` — the engine's tests and the fixture books they build (`fixture-book`,
  `fixture-companion` for references between books).
- `starter/` — the demo book: what a new book copies (shim, config, macros, `src/`,
  `authoring/`, `tests/`, CI workflow). The engine's CI builds and checks it.
- `DEPLOY.md` — publishing a book's site.
- `_build/`, `site/` and `docs/` are build output and are gitignored.
