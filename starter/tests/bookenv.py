"""Where the book and its engine are, for a book's own tests.

These tests read *a book* -- its sources, its config, its built `_build/` -- not the
engine's fixtures. They run from the book: `python3 -m unittest discover -s tests`.

- The book: $BOOK_ROOT, else the nearest directory above this file with
  config/config.json or book.json.
- The engine: $BOOK_ENGINE, else the book's engine/ submodule, else the nearest
  directory above this file with build/cli.py (the starter inside the engine repo).
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIGS = ("config/config.json", "book.json")


def _up(start: Path, test):
    for directory in (start, *start.parents):
        if test(directory):
            return directory
    return None


BOOK_ROOT = Path(os.environ["BOOK_ROOT"]).resolve() if os.environ.get("BOOK_ROOT") else \
    _up(HERE, lambda d: any((d / c).is_file() for c in CONFIGS))
if BOOK_ROOT is None:
    raise RuntimeError(f"no book config above {HERE}; set BOOK_ROOT")

if os.environ.get("BOOK_ENGINE"):
    ENGINE_ROOT = Path(os.environ["BOOK_ENGINE"]).expanduser().resolve()
elif (BOOK_ROOT / "engine" / "build" / "cli.py").is_file():
    ENGINE_ROOT = BOOK_ROOT / "engine"
else:
    ENGINE_ROOT = _up(HERE, lambda d: (d / "build" / "cli.py").is_file())
if ENGINE_ROOT is None:
    raise RuntimeError("no book engine found; run `git submodule update --init` or set BOOK_ENGINE")
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

SRC = BOOK_ROOT / "src"
INDEX = BOOK_ROOT / "_build" / "crossref_labels.json"
NAVIGATION = BOOK_ROOT / "_build" / "html" / "navigation.json"
CONFIG = next(BOOK_ROOT / c for c in CONFIGS if (BOOK_ROOT / c).is_file())


def tool(name: str):
    """An engine checker in tools/, imported by path."""
    spec = importlib.util.spec_from_file_location(name, ENGINE_ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def built_labels():
    """The built label index, or None before `./build.py html`."""
    if not INDEX.exists():
        return None
    return json.loads(INDEX.read_text(encoding="utf-8"))["crossref_labels"]
