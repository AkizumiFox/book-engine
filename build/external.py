"""
Build System External Books Module
==================================
References into other books built with this engine: `@la:thm-spectral-real` cites the
label `thm-spectral-real` of the book the config registers under the prefix `la`.

    "external-books": {
        "la": {
            "title": "Linear Algebra",
            "short": "LA",
            "url": "https://linear-algebra.example.com/",   # or "../linear-algebra/"
            "labels": "../linear-algebra/_build/crossref_labels.json"   # or a URL
        }
    }

`labels` is that book's label registry: its `_build/crossref_labels.json`, or the
`labels.json` every build publishes at the root of its website (`publish_labels`), given
as a path relative to this book's directory or as an http(s) URL. A URL is fetched once
per build process and kept in `_build/cache/external/`, so an offline build still has
the last copy.

Every scan writes `_build/external_labels.json`: per prefix, the display settings and the
few fields a reference needs of each label this book cites. filters/theorems.lua reads that file (the
metadata key `external-books-file`); `./build.py check` reads it through `lookup`.

A registry that cannot be read (the other book not built, no network) is a warning, not
an error: references to it print the book's title and the label, and link to the book's
start page. A label the registry does not have is an error, like an unresolved local one.
"""

import json
import re
import urllib.request
from pathlib import Path

from .book import Book
from .utils import print_warning

# What another book needs to know about a label to print and link a reference to it
PUBLISHED_FIELDS = ("type", "type_name", "number", "title", "title_html", "title_latex",
                    "file", "shard", "optional")

DEFAULT_FORMAT = "{title}, {ref}"          # @la:thm-x    -> Linear Algebra, Theorem 12.4
DEFAULT_SHORT_FORMAT = "[{short}, {ref}]"  # [@la:thm-x]  -> [LA, Theorem 12.4]

EXTERNAL_REF = re.compile(r"^([A-Za-z][\w]*):(.+)$")


def published_registry(labels: dict, title: str = "") -> dict:
    """A label registry stripped to what other books need (see PUBLISHED_FIELDS)."""
    return {
        "book": title,
        "crossref_labels": {
            label: {k: info[k] for k in PUBLISHED_FIELDS if k in info}
            for label, info in labels.items()
        },
    }


def publish_labels(book: Book, labels: dict):
    """Write <html>/labels.json, so another book can set its `labels` to our URL."""
    path = book.html_dir / "labels.json"
    text = json.dumps(published_registry(labels, book.title), separators=(",", ":"), ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def configured(book: Book) -> dict:
    """The config's `external-books`, or {}."""
    return book.config.get("external-books") or {}


def split_ref(book: Book, ref: str):
    """(prefix, label) for a reference into a configured external book, else None."""
    match = EXTERNAL_REF.match(ref)
    if match and match.group(1) in configured(book):
        return match.group(1), match.group(2)
    return None


def looks_external(ref: str) -> bool:
    """`prefix:type-name`: shaped like a reference into another book (configured or not)."""
    match = EXTERNAL_REF.match(ref)
    return bool(match and re.match(r"^[A-Za-z]+-", match.group(2)))


def _is_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value or ""))


def _fetch(book: Book, prefix: str, source: str) -> tuple[str | None, str]:
    """(text, problem) of a registry at a URL: fetched once per process, cached on disk."""
    cache = book.cache_dir / "external" / f"{prefix}.json"
    fetched = book.__dict__.setdefault("_external_fetched", set())
    if source not in fetched or not cache.exists():
        fetched.add(source)
        try:
            with urllib.request.urlopen(source, timeout=10) as response:
                text = response.read().decode("utf-8")
            json.loads(text)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")
            return text, ""
        except (OSError, ValueError) as error:
            if not cache.exists():
                return None, f"could not fetch {source} ({error})"
            print_warning(f"external book '{prefix}': could not fetch {source}; using the cached copy")
    return cache.read_text(encoding="utf-8"), ""


def _read_registry(book: Book, prefix: str, source: str) -> tuple[dict | None, str]:
    """(labels, problem). Labels are None when the registry cannot be read."""
    if _is_url(source):
        text, problem = _fetch(book, prefix, source)
        if text is None:
            return None, problem
    else:
        path = (book.root / source).resolve() if source else None
        if not path or not path.is_file():
            return None, f"{source or '(no labels path)'} not found (build that book first)"
        text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except ValueError as error:
        return None, f"{source} is not JSON ({error})"
    labels = data.get("crossref_labels", data) if isinstance(data, dict) else None
    if not isinstance(labels, dict):
        return None, f"{source} has no crossref_labels"
    return labels, ""


def resolve(book: Book, refresh: bool = False) -> dict:
    """
    Read every configured registry and write `_build/external_labels.json`. Returns
    {prefix: {"title", "short", "url", "format", "short-format", "available", "problem",
    "labels"}}. Memoized on the book; every scan passes refresh=True, so `serve` sees the
    other book rebuilt. A URL is fetched once per process all the same.
    """
    cached = getattr(book, "_external_books", None)
    if cached is not None and not refresh:
        return cached
    books = {}
    for prefix, spec in configured(book).items():
        spec = spec or {}
        url = (spec.get("url") or "").strip()
        if url and not url.endswith("/"):
            url += "/"
        labels, problem = _read_registry(book, prefix, (spec.get("labels") or "").strip())
        if problem:
            print_warning(f"external book '{prefix}': {problem}; references to it print without numbers")
        title = spec.get("title") or prefix
        books[prefix] = {
            "title": title,
            "short": spec.get("short") or title,
            "url": url,
            "format": spec.get("format") or DEFAULT_FORMAT,
            "short-format": spec.get("short-format") or DEFAULT_SHORT_FORMAT,
            "available": labels is not None,
            "problem": problem,
            "labels": published_registry(labels or {})["crossref_labels"],
        }
    book._external_books = books
    return books


def external_file(book: Book) -> Path:
    return book.build_dir / "external_labels.json"


def write_external_file(book: Book, refs) -> Path:
    """
    Write `_build/external_labels.json` for the filter: each configured book's settings
    and the labels of it this book cites (`refs`, every reference the scan found). Only
    the cited ones: every page's pandoc run reads this file, and a whole registry is
    megabytes.
    """
    wanted = {}
    for ref in refs:
        split = split_ref(book, ref)
        if split:
            wanted.setdefault(split[0], set()).add(split[1])
    data = {}
    for prefix, ext in resolve(book).items():
        data[prefix] = dict(ext, labels={label: ext["labels"][label]
                                         for label in sorted(wanted.get(prefix, ()))
                                         if label in ext["labels"]})
    path = external_file(book)
    text = json.dumps(data, sort_keys=True, ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return path


def lookup(book: Book, ref: str):
    """
    What a reference into another book resolves to, for fingerprints and the check:
    None if `ref` is not an external reference; otherwise (prefix, label, entry) where
    entry is the label's record, {} if the book's registry is unavailable, or None if the
    registry has no such label.
    """
    split = split_ref(book, ref)
    if not split:
        return None
    prefix, label = split
    ext = resolve(book)[prefix]
    if not ext["available"]:
        return prefix, label, {}
    return prefix, label, ext["labels"].get(label)
