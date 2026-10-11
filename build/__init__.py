"""
Build System Package
====================
Builds a Markdown textbook into a website and PDFs with Pandoc.

    from build import Book, build_html
    book = Book("path/to/book")
    build_html(book)
"""

__version__ = "1.0.0-rc1"

from .book import Book, Chapter, Page, ENGINE_ROOT
from .check import check, doctor
from .cli import main, build_all, clean
from .html import build_html
from .manifest import scan_labels
from .pdf import build_pdf, build_book

__all__ = [
    "__version__", "Book", "Chapter", "Page", "ENGINE_ROOT",
    "build_html", "build_pdf", "build_book", "build_all", "scan_labels",
    "check", "doctor", "clean", "main",
]
