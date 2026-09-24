# Finding maths that overflows the text column

The harness lives in the repo at `tools/_measure.html`. Copy it into the built site and drive
it headless: it renders every formula of every section into a 39rem column (the book's text
width) and lists the ones that stick out, as
`percent<TAB>page<TAB>first characters of the formula`, widest first.

It has two modes over the same page list, the same font warm-up and the same column, so the
two sets of numbers are comparable by construction:

| URL | measures | clean run says |
|---|---|---|
| `_measure.html` | display formulas (`mjx-container[display="true"]`) | `none (N displays measured on M pages)` |
| `_measure.html?mode=inline` | inline formulas (every other `mjx-container`) | `none (N inline formulas measured on M pages)` |

A dirty run ends with the same tally in brackets after the rows, so a short list of rows can
still be told apart from a run that only measured a handful of pages. Record this book's own
clean tally here after the first clean run: a tally that drops silently is how a broken
measurement looks.

```bash
cd /home/akizumi/coding/book-template
./build.py html
cp tools/_measure.html _build/html/_measure.html
(python3 -m http.server 8774 --directory _build/html >/dev/null 2>&1 &)
S=<your scratchpad>
rm -rf $S/measure           # see the traps
timeout 900 google-chrome --headless=new --disable-gpu --no-sandbox --user-data-dir=$S/measure \
  --virtual-time-budget=1200000 --dump-dom "http://localhost:8774/_measure.html" 2>/dev/null \
  | python3 -c "
import sys, re, html
m = re.search(r'<pre id=\"out\">(.*?)</pre>', sys.stdin.read(), re.S)
print(html.unescape(m.group(1)).strip() if m else '(no output)')"
```

Add `?mode=inline` to the URL for the inline pass. It measures every inline formula in the book and
still finishes quickly; nothing else changes.

**Measure `mjx-math`, not `mjx-container`.** The container of a *display* is a block with
`max-width: 100%` and `overflow-x: auto`, so it always reports exactly the column width and a
naive measurement says every formula fits. The typeset mathematics inside it is what sticks
out and what the reader has to scroll. A harness that reports "none" for the whole book is
measuring the wrong box; sanity-check it against a formula you can see overflowing. An inline
container is an inline-block that shrinks to its contents, so it would measure correctly
either way -- but `mjx-math` is still the right box, and using the same box in both modes is
what makes the percentages mean the same thing.

A formula over 100% overflows at all; at 110% and above it is clearly scrolling and should be
broken with `aligned`, `split` or `cases` (a `\tag` goes after `\end{aligned}`, never inside).

To measure a phone-width column instead, change `#stage { width: 39rem }` to 20rem.

## Fixing an inline formula

**Making the formula a display fixes nothing by itself.** A display is typeset in the same
39rem column, so a 124% inline chain becomes a 124% display. The display is only the vehicle:
what fixes the width is *breaking* the chain across lines inside it, or shortening it. Never
shrink the font, and never reach for `\psmallmatrix` to buy width.

Two shapes did the whole of the first inline pass in the linear-algebra book, from which
this note is ported:

- **Break the chain into `\begin{aligned}`**, the multi-line idiom these books use; check with
  a grep which of `aligned`, `split` and `align` this one actually uses before adding a second. Watch what this costs: an `aligned` row is as wide as
  the left-hand side *plus* the widest right-hand side, because the left column is shared. If
  the left-hand side is itself half the column, the aligned display will still overflow.
- **Move the left-hand side into the prose.** When the chain opens with something long --
  "Check by expanding: \\( <long left side> \\) equals" -- the sentence can carry it and the
  display starts at the first `=`. Look for a section that already does this and follow it.

  The third option, used once, is to cut the span in two in the running text
  ("the determinant is \\( X \\), that is \\( Y = 12 \\)"), which suits a parenthetical that a
  display would interrupt.

Inside a numbered list item, indent the display by three spaces, like the displays that
already sit inside `::: {.enumerate}` items; the rest of the item then has to be indented too.
`tests/test_display_math_source.py` is the gate for the shapes that silently break a display.

## Traps

- **Chrome caches the pages.** Re-running with the same `--user-data-dir` after editing can re-report the *old* widths, so an "after" number is a lie. Delete the profile directory before every run.
- **A row at exactly 100% is not an overflow.** An equation carrying a `\tag` gets `width="full"` from MathJax, which stretches `mjx-math` to precisely the column. Those rows are measurement artifacts. (This one is a display-mode trap only: inline maths never carries a `\tag`.)
- **A site that was never prerendered measures as clean.** MathJax runs at build time; if the pages you serve have not been through it there is no `mjx-container` to find, and an older harness reported "none". The harness now refuses that: a clean run prints `none (N … measured on M pages)`, and finding nothing at all is an error. If you see the error, run a full `./build.py html` first.
- **The incremental build races.** `_build/cache/html-fingerprints.json` can record stale HTML as freshly built when two builds run at once, and later builds then skip that page. Before trusting a measurement, delete that file and `_build/html` and rebuild; a serial `./build.py html` afterwards is the only state worth measuring.

Ported from the linear-algebra repo, where `tools/_measure.html` and this note were written.
The counts above are that book's; this one's are whatever its first clean run reports.
