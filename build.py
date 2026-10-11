#!/usr/bin/env python3
"""Shebang-executable entry point for the build system.

Run as: ./build.py html | pdf | book | all | serve | check | doctor | deploy | clean [file] [--book DIR]
   or:  python build.py html ...
   or:  python -m build html ...

Builds the book in this directory (the demo book) unless --book names another. A book
that uses the engine as a submodule has its own build.py: shim/build.py.
"""
from pathlib import Path

from build.cli import main

if __name__ == "__main__":
    raise SystemExit(main(default_book=Path(__file__).resolve().parent) or 0)
