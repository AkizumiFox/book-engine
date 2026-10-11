"""
Build System Math Module
========================
Renders TeX to HTML at build time with MathJax running under Node (build/render_math.cjs),
so pages show finished formulas immediately and load no math JavaScript.

MathJax is downloaded once (the npm package tarball) into a cache shared by all books
($XDG_CACHE_HOME/book-engine, else ~/.cache/book-engine). Without Node or without the
download, the site falls back to rendering math in the browser.
"""

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from .book import Book, ENGINE_ROOT
from .macros import mathjax_macros
from .utils import print_step, print_success, print_warning, print_error

MATHJAX_VERSION = "3.2.2"
MATHJAX_URL = f"https://registry.npmjs.org/mathjax/-/mathjax-{MATHJAX_VERSION}.tgz"
RENDERER = ENGINE_ROOT / "build" / "render_math.cjs"


def mathjax_dir(book: Book) -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache_home / "book-engine" / f"mathjax-{MATHJAX_VERSION}" / "es5"


def ensure_mathjax(book: Book) -> Path | None:
    """MathJax's es5 directory, downloading it on first use. None if unavailable."""
    if book.config.get("prerender-math") is False:
        return None
    if not shutil.which("node"):
        print_warning("node not found; math will be rendered in the browser")
        return None
    target = mathjax_dir(book)
    if (target / "startup.js").exists():
        return target
    print_step(f"Downloading MathJax {MATHJAX_VERSION}...")
    try:
        data = urllib.request.urlopen(MATHJAX_URL, timeout=60).read()
        destination = target.parent
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.name.startswith("package/es5/"):
                    continue
                member.name = member.name[len("package/"):]
                archive.extract(member, destination, filter="data")
    except Exception as e:  # network or archive problems: fall back to the browser
        print_warning(f"Could not download MathJax ({e}); math will be rendered in the browser")
        return None
    return target if (target / "startup.js").exists() else None


def copy_math_fonts(book: Book, source: Path):
    """MathJax's CommonHTML fonts, served next to mathjax.css."""
    fonts = source / "output" / "chtml" / "fonts" / "woff-v2"
    destination = book.html_dir / "mathjax-fonts"
    destination.mkdir(parents=True, exist_ok=True)
    for font in fonts.glob("*.woff"):
        target = destination / font.name
        if not target.exists():
            shutil.copy2(font, target)


# One node process rendering every page at once grows until it is killed, and the kill
# arrives with an empty stderr, so the build reports "Math rendering failed" with nothing
# to go on. Rendering in batches keeps each process small and makes the failure legible.
BATCH = 40


def render_math(book: Book, source: Path, pages: list[Path], shards: list[Path]) -> bool:
    """Render the math in the given HTML pages and tooltip shards, in place."""
    if not pages and not shards:
        return True
    macros = mathjax_macros(book.macros_file)
    css = book.html_dir / "mathjax.css"
    # The stylesheet is the same whichever document produces it (it carries the font faces,
    # not the glyphs of one page), so the first batch writes it and the rest discard theirs.
    scratch_css = book.build_dir / "tmp" / "mathjax-batch.css"
    scratch_css.parent.mkdir(parents=True, exist_ok=True)

    batches = [pages[i:i + BATCH] for i in range(0, len(pages), BATCH)] or [[]]
    batches[-1] = batches[-1]  # shards ride along with the final batch
    rendered_pages = rendered_shards = 0

    for index, batch in enumerate(batches):
        job = {
            "mathjax": str(source),
            "macros": macros,
            "pages": [str(p) for p in batch],
            "shards": [str(s) for s in shards] if index == len(batches) - 1 else [],
            "css": str(css if index == 0 else scratch_css),
        }
        result = subprocess.run(["node", str(RENDERER)], input=json.dumps(job),
                                capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip()[-2000:] or (
                f"node exited with code {result.returncode} and no message, most likely out of "
                f"memory on a batch of {len(batch)} pages")
            print_error(f"Math rendering failed: {detail}")
            return False
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        for error in summary["errors"]:
            print_warning(f"Math error in {error}")
        rendered_pages += summary["pages"]
        rendered_shards += summary["shards"]

    copy_math_fonts(book, source)
    tag_short_bold_greek(list(pages) + list(shards))
    print_success(f"Math rendered: {rendered_pages} pages, {rendered_shards} tooltip files")
    return True


# Bold upright Greek has no glyph in MathJax's TeX fonts, so MathJax emits it as <mjx-utext>
# drawn from a web font the stylesheet supplies. It cannot measure those glyphs when it
# prerenders and pads every one for a tall letter, so accents float above the short ones.
# Mark the short (x-height) letters so the stylesheet can pad and place accents for each kind.
SHORT_BOLD_GREEK = set(
    "\U0001D6C2\U0001D6C4\U0001D6C6\U0001D6C8\U0001D6CA\U0001D6CB\U0001D6CD\U0001D6CE"
    "\U0001D6D0\U0001D6D1\U0001D6D2\U0001D6D3\U0001D6D4\U0001D6D5\U0001D6D6\U0001D6D7"
    "\U0001D6D8\U0001D6DA\U0001D6DC\U0001D6DE\U0001D6E0\U0001D6E1"
)  # alpha gamma epsilon eta iota kappa mu nu omicron pi rho final-sigma sigma tau upsilon phi
   # chi omega and the variant epsilon, kappa, rho, pi: glyph heights about 0.48 em
_UTEXT_BOLD = re.compile(r'<mjx-utext([^>]*) variant="bold">([^<]*)</mjx-utext>')


def tag_short_bold_greek(files: list[Path]):
    def mark(match):
        attrs, text = match.group(1), match.group(2)
        if text and all(ch in SHORT_BOLD_GREEK for ch in text) and "data-short" not in attrs:
            return f'<mjx-utext{attrs} variant="bold" data-short="">{text}</mjx-utext>'
        return match.group(0)
    for path in files:
        path = Path(path)
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        if 'variant="bold"' not in html:
            continue
        tagged = _UTEXT_BOLD.sub(mark, html)
        if tagged != html:
            path.write_text(tagged, encoding="utf-8")
