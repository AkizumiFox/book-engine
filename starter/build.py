#!/usr/bin/env python3
"""Build this book: ./build.py html | pdf | book | all | serve | check | doctor | deploy | clean

The engine is the git submodule in engine/ (after a clone or a new worktree:
`git submodule update --init`), or the directory $BOOK_ENGINE names -- a working copy
of the engine, to try an engine change on this book before pinning it.
"""
import os
import sys
from pathlib import Path

BOOK = Path(__file__).resolve().parent
ENGINE = Path(os.environ.get("BOOK_ENGINE") or BOOK / "engine").expanduser().resolve()
if not (ENGINE / "build" / "cli.py").is_file() and (BOOK.parent / "starter") == BOOK:
    ENGINE = BOOK.parent                     # the starter book inside the engine repository
if not (ENGINE / "build" / "cli.py").is_file():
    sys.exit(f"No book engine in {ENGINE}.\nRun: git submodule update --init   (or set BOOK_ENGINE)")
sys.path.insert(0, str(ENGINE))
from build.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(default_book=BOOK) or 0)
