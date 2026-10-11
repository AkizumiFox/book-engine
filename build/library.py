"""
Build System Library Module
===========================
A library is several books published side by side on one origin, each in its own
sub-directory, with a generated landing page:

    ./build.py library site/books.json             # from any book, or the engine checkout
    ./build.py library site/books.json --out _site --with-pdf

The manifest (paths in it are relative to the manifest's directory):

    {
      "site-url": "https://example.github.io/library/",
      "out": "site",
      "landing": {"title": "Library", "intro": "...", "badge": "Work in progress",
                  "footer": "...",
                  "groups": [{"title": "Foundations", "intro": "...", "books": ["fd1", "fd2"]},
                             {"title": "Elsewhere", "links": [{"title": "The atlas",
                                                              "href": "atlas/atlas.html",
                                                              "blurb": "..."}]}]},
      "files": [{"from": "generated/atlas.html", "to": "atlas/atlas.html"}],
      "books": [{"prefix": "fd1", "title": "Logic and Proof", "short": "FD1",
                 "blurb": "...", "path": "../foundations/fd1", "subdir": "fd1",
                 "series": "Foundations", "overlay": {...},
                 "canonical": "https://fd1.example.org/"}]
    }

Two passes, so books may cite each other in both directions:

1. every book's label registry (`scan`, into its `<build-dir>/crossref_labels.json`);
2. every book's website, with a generated config overlay: `site-url` = the library's
   `site-url` + the book's sub-directory, `external-books` = every other book of the
   manifest under its prefix, `url` the relative path to its sub-directory (so links and
   hover previews stay on the same origin) and `labels` its pass-1 registry; and
   `canonical-url` = the book's `canonical` (its own production site, where its pages'
   canonical and og:url links then point; it gets no sitemap in the library), or none.

Each book is built in `_build/library` (the manifest's `build-dir`), never in the
author's `_build/html`, then its HTML copied to `<out>/<subdir>/`. The library root gets
`index.html` (the landing page), `404.html` (sends a reader to the book whose
sub-directory the missing path is in), `robots.txt`, `sitemap.xml` (an index of every
book's sitemap) and `.nojekyll`.
"""

import json
import posixpath
import re
import shutil
from html import escape
from pathlib import Path

from .book import Book, load_overlay, merge_patch
from .deploy import is_stale_chapter_dir, write_redirects
from .utils import print_header, print_step, print_success, print_error, print_info, print_warning

DEFAULT_BUILD_DIR = "_build/library"
SUBDIR = re.compile(r"^[A-Za-z0-9][\w.-]*(/[A-Za-z0-9][\w.-]*)*$")


class ManifestError(ValueError):
    pass


# =============================================================================
# Manifest
# =============================================================================

def load_manifest(path: Path) -> dict:
    """The manifest, checked and normalized: absolute book paths, a subdir per book."""
    path = Path(path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ManifestError(f"cannot read {path}: {error.strerror or error}") from error
    except ValueError as error:
        raise ManifestError(f"{path} is not valid JSON ({error})") from error
    if not isinstance(data, dict):
        raise ManifestError(f"{path} must hold a JSON object")
    base = path.parent
    site_url = (data.get("site-url") or "").strip()
    if not re.match(r"^https?://[^/]+(/.*)?$", site_url):
        raise ManifestError('"site-url" must be an http(s) address, e.g. "https://example.org/library/"')
    if not site_url.endswith("/"):
        site_url += "/"
    books = data.get("books")
    if not isinstance(books, list) or not books:
        raise ManifestError('"books" must be a non-empty list')
    seen_prefixes, seen_subdirs, normalized = set(), set(), []
    for position, entry in enumerate(books, start=1):
        if not isinstance(entry, dict):
            raise ManifestError(f"books[{position}] must be an object")
        prefix = entry.get("prefix") or ""
        if not re.match(r"^[A-Za-z]\w*$", prefix):
            raise ManifestError(f"books[{position}]: \"prefix\" must be a word starting with a letter")
        subdir = (entry.get("subdir") or prefix).strip("/")
        if not SUBDIR.match(subdir) or ".." in subdir.split("/"):
            raise ManifestError(f"book {prefix}: \"subdir\" {subdir!r} must be a relative path like \"fd1\"")
        if prefix in seen_prefixes:
            raise ManifestError(f"book prefix {prefix!r} appears twice")
        if subdir in seen_subdirs:
            raise ManifestError(f"subdir {subdir!r} appears twice")
        if any(subdir.startswith(other + "/") or other.startswith(subdir + "/") for other in seen_subdirs):
            raise ManifestError(f"subdir {subdir!r} nests inside another book's")
        seen_prefixes.add(prefix)
        seen_subdirs.add(subdir)
        if not entry.get("path"):
            raise ManifestError(f"book {prefix}: \"path\" (the book's directory) is missing")
        canonical = (entry.get("canonical") or "").strip()
        if canonical:
            if not re.match(r"^https?://[^/]+(/.*)?$", canonical):
                raise ManifestError(f"book {prefix}: \"canonical\" must be an http(s) address, "
                                    "e.g. \"https://book.example.org/\"")
            if not canonical.endswith("/"):
                canonical += "/"
        overlay = entry.get("overlay")
        if isinstance(overlay, str):
            overlay = load_overlay(base / overlay)
        normalized.append(dict(entry, prefix=prefix, subdir=subdir, canonical=canonical or None,
                               path=(base / entry["path"]).resolve(), overlay=overlay or {}))
    files = []
    for item in data.get("files") or []:
        if not isinstance(item, dict) or not item.get("from") or not item.get("to"):
            raise ManifestError('"files" entries are {"from": path, "to": path in the site}')
        to = item["to"].strip("/")
        if ".." in to.split("/"):
            raise ManifestError(f"files: {to!r} leaves the site")
        files.append({"from": (base / item["from"]).resolve(), "to": to})
    out = data.get("out") or "site"
    return {
        "site-url": site_url,
        "out": (base / out).resolve(),
        "build-dir": data.get("build-dir") or DEFAULT_BUILD_DIR,
        "landing": data.get("landing") or {},
        "files": files,
        "books": normalized,
        "file": path,
    }


def relative_url(from_subdir: str, to_subdir: str) -> str:
    """The URL of one book's root seen from another's: "../fd2/" for siblings."""
    return posixpath.relpath(to_subdir, from_subdir) + "/"


def book_overlay(manifest: dict, entry: dict, own_config: dict, registries: dict) -> dict:
    """The config overlay one book is built with (see the module docstring).

    `registries` maps each prefix to its pass-1 label registry. The other books' `title`
    and `short` come from the manifest unless the book's own config already names them
    for that prefix; `url` and `labels` always come from the library.
    """
    own_external = own_config.get("external-books") or {}
    external = {}
    for other in manifest["books"]:
        if other["prefix"] == entry["prefix"]:
            continue
        spec = {"url": relative_url(entry["subdir"], other["subdir"]),
                "labels": str(registries[other["prefix"]])}
        mine = own_external.get(other["prefix"]) or {}
        if not mine.get("title"):
            spec["title"] = other.get("title") or other["prefix"]
        if not mine.get("short"):
            spec["short"] = other.get("short") or other["prefix"].upper()
        external[other["prefix"]] = spec
    overlay = {
        "site-url": manifest["site-url"] + entry["subdir"] + "/",
        "deploy-domain": None,     # the library's own address, not the book's own domain
        # canonical and og:url: the book's own site when the manifest names one
        # ("canonical"), else the library (a canonical-url of the book's config is dropped)
        "canonical-url": entry.get("canonical"),
        "build-dir": manifest["build-dir"],
        "output": None,            # every output inside build-dir
        "external-books": external,
    }
    return merge_patch(overlay, entry.get("overlay") or {})


# =============================================================================
# Building
# =============================================================================

def build_library(manifest_path, out=None, with_pdf: bool = False, extra_overlay=None) -> bool:
    """Build every book of the manifest and assemble the site. True on success."""
    from .html import build_html
    from .manifest import scan_labels
    from .pdf import build_pdf, build_book

    try:
        manifest = load_manifest(Path(manifest_path))
    except ManifestError as error:
        print_error(f"Library manifest: {error}")
        return False
    if out:
        manifest["out"] = Path(out).resolve()
    # `out` is emptied: it must not hold the manifest or a book
    for keep in [manifest["file"]] + [entry["path"] for entry in manifest["books"]]:
        if keep == manifest["out"] or keep.is_relative_to(manifest["out"]):
            print_error(f"Library manifest: the output directory {manifest['out']} would delete {keep}")
            return False
    extra = load_overlay(extra_overlay)

    def open_book(entry, overlay):
        return Book(entry["path"], overlay=merge_patch(overlay, extra))

    # Pass 1: every book's label registry, so pass 2 can resolve citations either way
    books = {}
    for entry in manifest["books"]:
        try:
            plain = Book(entry["path"])
        except FileNotFoundError as error:
            print_error(f"book {entry['prefix']}: {error}")
            return False
        books[entry["prefix"]] = plain
    registries = {}
    for entry in manifest["books"]:
        plain = books[entry["prefix"]]
        probe = open_book(entry, {"build-dir": manifest["build-dir"], "output": None})
        registries[entry["prefix"]] = probe.labels_file
        if not entry.get("title"):
            entry["title"] = plain.title
    print_info("Pass 1 scans each book once; a warning there that a later book's registry "
               "is not found is expected (pass 2 has them all)")
    for entry in manifest["books"]:
        print_header(f"Library pass 1: labels of {entry['prefix']} ({entry['path']})")
        book = open_book(entry, book_overlay(manifest, entry, books[entry["prefix"]].config, registries))
        scan_labels(book)

    # Pass 2: the websites, every registry now in place
    ok = True
    built = []
    for entry in manifest["books"]:
        print_header(f"Library pass 2: {entry['prefix']} -> {entry['subdir']}/")
        overlay = book_overlay(manifest, entry, books[entry["prefix"]].config, registries)
        book = open_book(entry, overlay)
        book.build_dir.mkdir(parents=True, exist_ok=True)
        (book.build_dir / "library-overlay.json").write_text(
            json.dumps(merge_patch(overlay, extra), indent=2, ensure_ascii=False), encoding="utf-8")
        book_ok = build_html(book)
        if with_pdf:
            book_ok = build_pdf(book) and book_ok
            book_ok = build_book(book) and book_ok
        if not book_ok:
            print_error(f"book {entry['prefix']} did not build cleanly")
            ok = False
        built.append((entry, book))

    assemble(manifest, built, with_pdf)
    if ok:
        print_success(f"Library assembled in {manifest['out']}")
    else:
        print_warning(f"Library assembled in {manifest['out']}, but some books had build errors")
    return ok


def _clear(directory: Path):
    """Empty `directory`, keeping a git clone's .git (and a CNAME the site owner set)."""
    directory.mkdir(parents=True, exist_ok=True)
    for item in directory.iterdir():
        if item.name in (".git", "CNAME"):
            continue
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def copy_book_html(book: Book, destination: Path, with_pdf: bool):
    """The book's HTML output, as `deploy` would publish it (no stale chapters, no scratch
    `_` files), without the PDFs unless asked for, plus its redirect stubs."""
    chapter_slugs = {c.slug for c in book.chapters}
    destination.mkdir(parents=True, exist_ok=True)
    for item in book.html_dir.iterdir():
        if item.is_dir() and is_stale_chapter_dir(item.name, chapter_slugs):
            continue
        if item.name.startswith("_"):
            continue
        if not with_pdf and item.is_dir() and item.name in ("pdf", "book"):
            continue
        if item.is_dir():
            shutil.copytree(item, destination / item.name)
        else:
            shutil.copy2(item, destination / item.name)
    write_redirects(book, destination)


def assemble(manifest: dict, built: list, with_pdf: bool):
    out = manifest["out"]
    print_step(f"Assembling {out}")
    _clear(out)
    for entry, book in built:
        if book.html_dir.is_dir():
            copy_book_html(book, out / entry["subdir"], with_pdf)
    for item in manifest["files"]:
        target = out / item["to"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if item["from"].is_dir():
            shutil.copytree(item["from"], target)
        elif item["from"].is_file():
            shutil.copy2(item["from"], target)
        else:
            print_warning(f"files: {item['from']} not found")
    site_url = manifest["site-url"]
    (out / "index.html").write_text(landing_page(manifest), encoding="utf-8")
    (out / "404.html").write_text(not_found_page(manifest), encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site_url}sitemap.xml\n", encoding="utf-8")
    (out / "sitemap.xml").write_text(sitemap_index(manifest, out), encoding="utf-8")
    (out / "sitemap-landing.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{escape(site_url)}index.html</loc></url>\n</urlset>\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")   # theorems/_root/... must be served
    print_info(f"{len(built)} book(s), landing page, 404.html, robots.txt, sitemap.xml")


def sitemap_index(manifest: dict, out: Path) -> str:
    site_url = manifest["site-url"]
    locations = [f"{site_url}sitemap-landing.xml"]
    # a book canonical elsewhere is indexed there, not here (and has no sitemap.xml)
    locations += [f"{site_url}{entry['subdir']}/sitemap.xml" for entry in manifest["books"]
                  if not entry.get("canonical") and (out / entry["subdir"] / "sitemap.xml").exists()]
    entries = "\n".join(f"  <sitemap><loc>{escape(loc)}</loc></sitemap>" for loc in locations)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{entries}\n</sitemapindex>\n")


# =============================================================================
# Landing and 404 pages
# =============================================================================

PAGE_STYLE = """
:root { color-scheme: light; --bg: #fbfaf7; --fg: #1f1d1a; --muted: #6b665e; --card: #ffffff;
        --line: #e4e0d8; --accent: #2f5d8a; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark; --bg: #16171a; --fg: #e8e6e1; --muted: #9a958c;
        --card: #1f2125; --line: #33363c; --accent: #8ab4e0; }
}
:root[data-theme="dark"] { color-scheme: dark; --bg: #16171a; --fg: #e8e6e1; --muted: #9a958c;
        --card: #1f2125; --line: #33363c; --accent: #8ab4e0; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 17px/1.55 Georgia, "STIX Two Text", "Times New Roman", serif; }
main { max-width: 760px; margin: 0 auto; padding: 48px 16px 64px; }
h1 { font-weight: 600; margin: 0 0 6px; }
a { color: var(--accent); }
.lede { color: var(--muted); margin: 0 0 32px; }
.badge { display: inline-block; font: 600 12px/1 system-ui, sans-serif; letter-spacing: .04em; text-transform: uppercase;
         color: var(--accent); border: 1px solid var(--accent); border-radius: 4px; padding: 4px 6px; margin-bottom: 18px; }
.series { margin: 0 0 28px; }
.series h2 { font-size: 15px; font: 600 13px/1.2 system-ui, sans-serif; letter-spacing: .06em; text-transform: uppercase;
             color: var(--muted); margin: 0 0 10px; }
.series > p { color: var(--muted); margin: -4px 0 12px; font-size: 15px; }
a.card { display: block; background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 16px 20px;
         margin: 0 0 12px; color: inherit; text-decoration: none; }
a.card:hover, a.card:focus-visible { border-color: var(--accent); }
a.card h3 { margin: 0 0 4px; font-size: 20px; color: var(--accent); font-weight: 600; }
a.card .short { font: 600 12px/1 system-ui, sans-serif; color: var(--muted); margin-left: 6px; vertical-align: 2px; }
a.card p { margin: 0; color: var(--muted); font-size: 15px; }
footer { margin-top: 36px; color: var(--muted); font-size: 14px; }
.theme-toggle { position: absolute; top: 14px; right: 16px; background: none; border: 1px solid var(--line); color: var(--muted);
                border-radius: 6px; padding: 4px 8px; font: 13px system-ui, sans-serif; cursor: pointer; }
.theme-toggle:hover { color: var(--fg); border-color: var(--accent); }
"""

# The books' own setting (main.js stores it as "book-theme"): one choice for the whole site
THEME_SCRIPT = """(function () {
    var theme = null;
    try { theme = localStorage.getItem('book-theme'); } catch (e) {}
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
})();"""

TOGGLE_SCRIPT = """(function () {
    var button = document.querySelector('.theme-toggle');
    if (!button) return;
    button.hidden = false;
    button.addEventListener('click', function () {
        var root = document.documentElement;
        var current = root.dataset.theme
            || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        var next = current === 'dark' ? 'light' : 'dark';
        root.dataset.theme = next;
        try { localStorage.setItem('book-theme', next); } catch (e) {}
    });
})();"""


def _page(title: str, body: str, head_extra: str = "", scripts: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
{head_extra}<script>{THEME_SCRIPT}</script>
<style>{PAGE_STYLE}</style>
</head>
<body>
{body}
{scripts}</body>
</html>
"""


def _groups(manifest: dict) -> list[dict]:
    """The landing page's sections: the manifest's `landing.groups`, else one per series
    in the order the books list them. Books no group names go last, by series."""
    by_prefix = {entry["prefix"]: entry for entry in manifest["books"]}
    groups = manifest["landing"].get("groups")
    if not groups:
        groups, index = [], {}
        for entry in manifest["books"]:
            series = entry.get("series") or ""
            if series not in index:
                index[series] = {"title": series, "books": []}
                groups.append(index[series])
            index[series]["books"].append(entry["prefix"])
    result, placed = [], set()
    for group in groups:
        names = group.get("books")
        if names is None and group.get("series"):
            names = [e["prefix"] for e in manifest["books"] if e.get("series") == group["series"]]
        entries = [by_prefix[name] for name in names or [] if name in by_prefix]
        placed.update(e["prefix"] for e in entries)
        result.append(dict(group, title=group.get("title") or group.get("series") or "", entries=entries))
    for entry in manifest["books"]:      # the rest, by series
        if entry["prefix"] in placed:
            continue
        series = entry.get("series") or ""
        group = next((g for g in result if g.get("rest") and g["title"] == series), None)
        if group is None:
            group = {"title": series, "entries": [], "rest": True}
            result.append(group)
        group["entries"].append(entry)
    return result


def landing_page(manifest: dict) -> str:
    """index.html at the library root. Titles are text; `intro`, `blurb` and `footer` may
    hold HTML (the manifest is the site owner's own file)."""
    landing = manifest["landing"]
    title = landing.get("title") or "Library"
    parts = ['<main>', '<button class="theme-toggle" type="button" hidden aria-label="Switch light or dark theme">Theme</button>']
    if landing.get("badge"):
        parts.append(f'<span class="badge">{escape(landing["badge"])}</span>')
    parts.append(f"<h1>{escape(title)}</h1>")
    if landing.get("intro"):
        parts.append(f'<p class="lede">{landing["intro"]}</p>')
    for group in _groups(manifest):
        if not group["entries"] and not group.get("links"):
            continue
        parts.append('<section class="series">')
        if group["title"]:
            parts.append(f"<h2>{escape(group['title'])}</h2>")
        if group.get("intro"):
            parts.append(f"<p>{group['intro']}</p>")
        for entry in group["entries"]:
            short = entry.get("short") or entry["prefix"].upper()
            blurb = f"<p>{entry['blurb']}</p>" if entry.get("blurb") else ""
            parts.append(f'<a class="card" href="{escape(entry["subdir"])}/" data-book="{escape(entry["prefix"])}">'
                         f'<h3>{escape(entry["title"])}<span class="short">{escape(short)}</span></h3>{blurb}</a>')
        for link in group.get("links") or []:
            blurb = f"<p>{link['blurb']}</p>" if link.get("blurb") else ""
            parts.append(f'<a class="card" href="{escape(link.get("href", ""))}">'
                         f'<h3>{escape(link.get("title", ""))}</h3>{blurb}</a>')
        parts.append("</section>")
    if landing.get("footer"):
        parts.append(f"<footer>{landing['footer']}</footer>")
    parts.append("</main>")
    description = re.sub(r"<[^>]+>", "", landing.get("intro") or "")
    head = (f'<link rel="canonical" href="{escape(manifest["site-url"])}">\n'
            + (f'<meta name="description" content="{escape(description)}">\n' if description else ""))
    return _page(title, "\n".join(parts), head, f"<script>{TOGGLE_SCRIPT}</script>\n")


def not_found_page(manifest: dict) -> str:
    """The root 404.html. GitHub Pages serves only the root one for a project site, so it
    works out from the address which book the reader was in and offers that book."""
    site_path = re.match(r"^[a-z]+://[^/]+(/.*)?$", manifest["site-url"]).group(1) or "/"
    title = manifest["landing"].get("title") or "Library"
    books = [{"subdir": e["subdir"], "title": e["title"]} for e in manifest["books"]]
    body = f"""<main>
<p><a href="{escape(site_path)}">{escape(title)}</a></p>
<h1>Page not found</h1>
<p>This page does not exist, or it moved when a book was reorganized.</p>
<p id="book-hint" hidden></p>
<p><a href="{escape(site_path)}">Go to the library's front page</a>.</p>
</main>"""
    script = """<script>
(function () {
    var root = %s, books = %s;
    var path = location.pathname;
    if (path.indexOf(root) !== 0) return;
    var rest = path.slice(root.length);
    for (var i = 0; i < books.length; i++) {
        var subdir = books[i].subdir + '/';
        if (rest === books[i].subdir || rest.indexOf(subdir) === 0) {
            var hint = document.getElementById('book-hint');
            var link = document.createElement('a');
            link.href = root + subdir;
            link.textContent = books[i].title;
            hint.append('Go to the start of ', link, ', or use the search in its sidebar.');
            hint.hidden = false;
            return;
        }
    }
})();
</script>
""" % (json.dumps(site_path), json.dumps(books, ensure_ascii=False).replace("</", "<\\/"))
    return _page(f"Page not found – {title}", body, '<meta name="robots" content="noindex">\n', script)
