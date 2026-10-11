"""A book that uses the engine as a submodule: `engine/` inside the book, and the
book's own ~20-line build.py (starter/build.py) that honours $BOOK_ENGINE.

The engine is copied (not symlinked) into the book, so the engine really lives inside
the book root, as a submodule does -- the case where LaTeX's search path must still
prefer the book's own overrides.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixture-book"
SHIM = ENGINE_ROOT / "starter" / "build.py"
ENGINE_DIRS = ("build", "filters", "templates", "latex", "tools", "widgets")
MARKER = "BOOK-OVERRIDE-OF-THEOREM-FRAME"


def run_shim(book_dir: Path, *args: str, engine: Path | None = None, cwd: Path | None = None):
    env = {k: v for k, v in os.environ.items() if k != "BOOK_ENGINE"}
    if engine is not None:
        env["BOOK_ENGINE"] = str(engine)
    return subprocess.run([sys.executable, str(book_dir / "build.py"), *args],
                          capture_output=True, text=True, env=env, cwd=cwd or "/")


def make_book(parent: Path, with_engine: bool) -> Path:
    book = parent / "book"
    shutil.copytree(FIXTURE, book)
    refs = book / "src" / "ch02-more" / "01-refs.md"
    refs.write_text(refs.read_text().replace("A broken reference: @thm-missing.\n", ""))
    shutil.copy2(SHIM, book / "build.py")
    # A book override of an engine style, found through TEXINPUTS
    (book / "latex").mkdir()
    frame = (ENGINE_ROOT / "latex" / "theorem-frame.sty").read_text()
    (book / "latex" / "theorem-frame.sty").write_text(f"\\typeout{{{MARKER}}}\n" + frame)
    if with_engine:
        for name in ENGINE_DIRS:
            shutil.copytree(ENGINE_ROOT / name, book / "engine" / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
    return book


class TestSubmoduleLayout(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="book-shim-")
        cls.book = make_book(Path(cls.tmp.name), with_engine=True)
        cls.html = run_shim(cls.book, "html")
        cls.pdf = run_shim(cls.book, "pdf")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_builds_from_any_directory(self):
        self.assertEqual(self.html.returncode, 0, self.html.stdout + self.html.stderr)
        self.assertTrue((self.book / "_build" / "html" / "ch01-basics" / "01-first.html").exists())
        self.assertFalse((self.book / "engine" / "_build").exists())

    def test_the_engine_in_the_book_is_the_one_used(self):
        result = run_shim(self.book, "doctor")
        self.assertIn(f"Engine: {self.book / 'engine'}", result.stdout)

    def test_the_books_latex_override_wins_over_the_engine_inside_it(self):
        self.assertEqual(self.pdf.returncode, 0, self.pdf.stdout + self.pdf.stderr)
        log = self.book / "_build" / "tmp" / "pdf-single" / "ch01-basics" / "01-first.log"
        self.assertIn(MARKER, log.read_text(errors="replace"))

    def test_check_passes(self):
        result = run_shim(self.book, "check")
        self.assertEqual(result.returncode, 0, result.stdout)


class TestBookEngineVariable(unittest.TestCase):

    def test_book_engine_points_at_a_working_copy(self):
        with tempfile.TemporaryDirectory(prefix="book-shim-") as tmp:
            book = make_book(Path(tmp), with_engine=False)
            result = run_shim(book, "doctor", engine=ENGINE_ROOT)
            self.assertIn(f"Engine: {ENGINE_ROOT}", result.stdout)
            result = run_shim(book, "scan", engine=ENGINE_ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((book / "_build" / "crossref_labels.json").exists())

    def test_an_empty_engine_directory_says_what_to_run(self):
        with tempfile.TemporaryDirectory(prefix="book-shim-") as tmp:
            book = make_book(Path(tmp), with_engine=False)
            (book / "engine").mkdir()       # a submodule that was never initialised
            result = run_shim(book, "html")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("git submodule update --init", result.stderr)


if __name__ == "__main__":
    unittest.main()
