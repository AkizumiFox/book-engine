"""
Build System CLI Module
=======================
Command-line interface and main entry point.
"""

import argparse
import shutil
import sys
from pathlib import Path

from .book import Book, ENGINE_ROOT
from .check import check, doctor
from .deploy import deploy
from .html import build_html
from .manifest import scan_labels, generate_theorem_manifest
from .pdf import build_pdf, build_book
from .utils import print_header, print_info, print_error


def build_all(book: Book) -> bool:
    """HTML, section PDFs and the book PDF. Returns True if everything built."""
    ok = build_html(book)
    ok = build_pdf(book) and ok
    ok = build_book(book) and ok
    return ok


def clean(book: Book):
    """Remove the build directory."""
    if not book.build_dir.exists():
        print_info("Nothing to clean")
        return
    try:
        shutil.rmtree(book.build_dir)
        print_info(f"Removed: {book.build_dir}")
    except OSError as e:
        print_error(f"Failed to remove {book.build_dir}: {e}")
        print_error("Close any open PDFs or files from _build/ and try again.")


def _book_root(value: str) -> Path:
    """Accept a book directory, or its book.json / config/config.json."""
    path = Path(value).resolve()
    if path.is_file():
        return path.parent.parent if path.parent.name == "config" else path.parent
    return path


def main(default_book=None, argv=None):
    """The command line. `default_book` is the book built when --book is not given: a
    book's build.py shim passes its own directory. Without either, the current directory."""
    # Line-buffered output, so progress shows up promptly when piped or logged
    sys.stdout.reconfigure(line_buffering=True)
    print_header("Pandoc Book Build System")

    parser = argparse.ArgumentParser(
        description="Pandoc Book Build System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    ./build.py html                Build the website (unchanged pages are skipped)
    ./build.py html src/ch01/01.md Build one page
    ./build.py pdf                 Build per-section PDFs
    ./build.py book                Build the combined book PDF
    ./build.py all                 Build everything
    ./build.py serve               Build, serve on localhost and rebuild on changes
    ./build.py check               Validate references, links and web/PDF numbering
    ./build.py doctor              Check that required tools are installed
    ./build.py deploy --push       Build, check, copy to site/ and push
    ./build.py clean               Remove _build
    ./build.py html --book ../other-book   Build a different book with this engine
        """,
    )
    parser.add_argument("command", choices=["html", "pdf", "book", "all", "serve", "check", "doctor",
                                            "scan", "manifest", "deploy", "clean"])
    parser.add_argument("file", nargs="?", help="html/pdf: build only this source file")
    parser.add_argument("--book", default=None,
                        help="book directory (containing book.json or config/config.json); "
                             "default: the book whose build.py ran this, else the current directory")
    parser.add_argument("--no-build", action="store_true", help="deploy: copy existing output without building")
    parser.add_argument("--push", action="store_true", help="deploy: commit and push from the deploy directory")
    parser.add_argument("--port", type=int, default=8000, help="serve: port (default 8000)")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        from . import __version__
        print_info(f"Engine: {ENGINE_ROOT} (book-engine {__version__})")
        sys.exit(0 if doctor() else 1)

    book_dir = args.book or default_book or Path.cwd()
    try:
        book = Book(_book_root(str(book_dir)))
    except FileNotFoundError as e:
        print_error(str(e))
        print_info("Run from a book's directory (its own build.py), or pass --book DIR "
                   "(the engine's demo book: --book starter)")
        sys.exit(2)

    specific_file = Path(args.file).resolve() if args.file else None
    ok = True
    if args.command == "clean":
        clean(book)
    elif args.command == "scan":
        scan_labels(book)
    elif args.command == "manifest":
        scan_labels(book)
        generate_theorem_manifest(book)
    elif args.command == "html":
        ok = build_html(book, specific_file)
    elif args.command == "pdf":
        ok = build_pdf(book, specific_file)
    elif args.command == "book":
        ok = build_book(book)
    elif args.command == "all":
        ok = build_all(book)
    elif args.command == "check":
        ok = check(book)
    elif args.command == "deploy":
        ok = deploy(book, run_build=not args.no_build, push=args.push)
    elif args.command == "serve":
        from .serve import serve
        serve(book, port=args.port)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
