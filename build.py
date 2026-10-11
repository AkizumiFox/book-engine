#!/usr/bin/env python3
"""The engine's command line, run from the engine checkout.

    ./build.py html --book starter          # the demo book
    cd starter && ../build.py html          # the same: the book is the current directory

A book carries its own build.py (starter/build.py, ~20 lines) that finds this engine
in its engine/ submodule or $BOOK_ENGINE and builds that book; use that one in a book.
"""
from build.cli import main

if __name__ == "__main__":
    raise SystemExit(main() or 0)
