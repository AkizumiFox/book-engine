# Starter book

A complete small book on the book engine: the demo chapter uses every environment,
reference, display and component the engine offers. Copy this directory to start a book
(the engine's `README.md`, "Start a book", has the steps), and replace this file.

| Task | Command |
|---|---|
| Live preview | `./build.py serve` |
| Website / book PDF / everything | `./build.py html` / `./build.py book` / `./build.py all` |
| Validate | `./build.py check` |
| Tests | `python3 -m unittest discover -s engine/tests` (engine), `-s tests` (this book) |

- `build.py` finds the engine in `engine/` (a git submodule: `git submodule update --init`)
  or in `$BOOK_ENGINE`. Inside the engine repository it uses the repository itself.
- `config/config.json` -- the book's settings; `latex/macros.tex` -- its macros.
- `src/` -- the book; `authoring/` -- the writing standard and the notation guide.
- `tests/` -- the book's tests: its sources (displays, math spans, proof ownership) and,
  after `./build.py html`, the engine's gates and the reading paths on the built book.
  `tests/bookenv.py` finds the book and the engine.
- `tools/` (none yet) -- the book's own checkers, listed under `checks` in the config.
- `.github/workflows/build-and-check.yml` -- CI: builds, tests and checks on every push.
