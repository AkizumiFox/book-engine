"""
Build System Landing Module
===========================
The library's front page (index.html) and its root 404.html, generated from the library
manifest (build/library.py) and from what the build learned about each book.

The landing page has the books' own look: STIX Two Text (the fonts a book already serves,
so nothing is fetched from elsewhere), the same colour tokens and light/dark themes (the
same saved "book-theme" choice), the same fluid text size and line length.

Manifest keys it reads (all optional except the books):

    "landing": {
      "title": "Math Atlas",
      "tagline": "One sentence: what the series is.",
      "usage": "How to use it (HTML).",
      "status": "A quiet work-in-progress note (HTML).",
      "groups": [{"series": "Foundations", "blurb": "One line (HTML)."},
                 {"title": "The atlas", "blurb": "...",
                  "links": [{"title": "...", "href": "...", "blurb": "...", "label": "Map"}]}],
      "diagram": {"title": "Reading order", "caption": "The text alternative (HTML).",
                  "nodes": [{"id": "F1", "book": "fd1", "name": "Logic", "at": [0, 0],
                             "at-narrow": [0, 0]},
                            {"id": "F4", "name": "Algebra", "planned": true, "at": [3, 0]}],
                  "edges": [["F1", "F2"], {"from": "F3", "to": "AN1", "kind": "optional"}]},
      "licence": "Licence line (HTML).",
      "sources": [{"title": "AkizumiFox/foundations", "href": "https://github.com/..."}],
      "footer": "Any further footer text (HTML)."
    },
    "books": [{"prefix": "fd1", "short": "F1", "blurb": "1-2 sentences (HTML, TeX math)",
               "planned": 5, "pdf": "https://.../book.pdf", ...}]

`intro` and `badge`, the older names of `tagline` and `status`, are still read.

Titles and blurbs may hold TeX math (\\( \\nN \\)). When the books' math was rendered at
build time, the landing page's math is rendered the same way (MathJax under Node, the
books' macro files) and styled by a book's mathjax.css; otherwise it is turned into plain
text (ℕ), as it always is in <title> and meta tags.
"""

import json
import re
import subprocess
import tempfile
from html import escape
from pathlib import Path

from .book import ENGINE_ROOT
from .macros import plain_text

# =============================================================================
# Styles
# =============================================================================

TOKENS_LIGHT = """
  color-scheme: light;
  --paper: #ffffff;
  --ink: #26282d;
  --ink-strong: #121418;
  --muted: #5f6570;
  --rule: #e1e4e8;
  --rule-strong: #c9ced5;
  --subtle: #f6f7f9;
  --accent: #1f5bb8;
  --accent-soft: #e8effa;
  --hover-wash: #eaf1fb;
  --hover-border: #9db8e3;
"""

TOKENS_DARK = """
  color-scheme: dark;
  --paper: #16181c;
  --ink: #d8dbe0;
  --ink-strong: #f1f2f4;
  --muted: #a1a7b1;
  --rule: #2b2f36;
  --rule-strong: #3a3f47;
  --subtle: #1d2025;
  --accent: #83adf0;
  --accent-soft: #1f2a3b;
  --hover-wash: #202b3c;
  --hover-border: #4d6a94;
"""

PAGE_STYLE = """
:root {%(light)s
  --font-body: 'STIX Two Text', 'STIX Two', 'Times New Roman', serif;
  /* the books' fluid text: 20px up to a 1440px window, 26px at 2560px; 18px on phones */
  --text-size: clamp(20px, calc(12.3px + 0.536vw), 26px);
  --measure: calc(var(--text-size) * 31.2);     /* the books' column: about 72 characters */
  --page-width: calc(var(--text-size) * 56);
  --gutter: 16px;
}
@media (max-width: 900px) { :root { --text-size: 18px; } }
@media (min-width: 600px) { :root { --gutter: 32px; } }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {%(dark)s} }
:root[data-theme="dark"] {%(dark)s}

*, *::before, *::after { box-sizing: border-box; }
html { font-size: 16px; -webkit-text-size-adjust: 100%%; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: var(--font-body); font-size: var(--text-size); line-height: 1.6;
  font-kerning: normal; font-variant-numeric: lining-nums proportional-nums;
  text-rendering: optimizeLegibility;
}
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 0.18em; }
a:hover { color: var(--ink-strong); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }
.skip-link { position: absolute; left: -9999px; top: 0; }
.skip-link:focus { left: var(--gutter); top: 8px; background: var(--paper); padding: 4px 8px; z-index: 2; }
.visually-hidden { position: absolute !important; width: 1px; height: 1px; overflow: hidden;
                   clip-path: inset(50%%); white-space: nowrap; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }

.page { max-width: calc(var(--page-width) + 2 * var(--gutter)); margin: 0 auto; padding: 0 var(--gutter); }

/* Header */
.masthead { position: relative; padding: clamp(2.2rem, 7vw, 4.5rem) 0 2.2rem; border-bottom: 1px solid var(--rule); }
.masthead h1 { margin: 0 0 0.35em; font-size: 2.3em; line-height: 1.1; font-weight: 600;
               letter-spacing: -0.01em; color: var(--ink-strong); padding-right: 2.5rem; }
.tagline { margin: 0 0 0.6em; max-width: var(--measure); font-size: 1.22em; line-height: 1.45; color: var(--ink-strong); }
.usage { margin: 0 0 0.9em; max-width: var(--measure); color: var(--ink); }
.status { margin: 0; max-width: var(--measure); font-size: 0.85em; color: var(--muted); font-style: italic; }
.theme-toggle { position: absolute; top: clamp(1.4rem, 5vw, 2.2rem); right: 0; display: inline-flex;
                align-items: center; justify-content: center; width: 2.25rem; height: 2.25rem; padding: 0;
                border: 1px solid var(--rule); border-radius: 8px; background: transparent;
                color: var(--muted); cursor: pointer; }
.theme-toggle:hover { color: var(--ink-strong); background: var(--subtle); }
.theme-toggle svg { width: 1.05rem; height: 1.05rem; }
.theme-toggle .moon { display: none; }
:root[data-theme="dark"] .theme-toggle .sun { display: none; }
:root[data-theme="dark"] .theme-toggle .moon { display: inline; }

/* Sections */
.band { padding: 2.2rem 0 2.4rem; border-bottom: 1px solid var(--rule); }
.band-head { max-width: var(--measure); margin-bottom: 1.1rem; }
.band h2 { margin: 0 0 0.2em; font-size: 1.4em; line-height: 1.25; font-weight: 600; color: var(--ink-strong); }
.band-head p { margin: 0; color: var(--muted); }

/* A run of one-card sections: side by side, their heads and cards on shared rows */
.band-row { display: grid; gap: 0 1rem; border-bottom: 1px solid var(--rule);
            grid-template-columns: repeat(auto-fit, minmax(min(100%%, calc(var(--text-size) * 15.5)), 1fr)); }
.band-row > .band { display: grid; grid-row: span 2; grid-template-rows: subgrid; row-gap: 0; border-bottom: 0; }
.band-row .band-head { margin-bottom: 1.1rem; }
.band-row .cards { grid-template-columns: 1fr; }
@media (max-width: 640px) { .band-row > .band + .band { border-top: 1px solid var(--rule); } }

/* Book cards */
.cards { list-style: none; margin: 0; padding: 0; display: grid; gap: 1rem;
         grid-template-columns: repeat(auto-fill, minmax(min(100%%, calc(var(--text-size) * 15.5)), 1fr)); }
.card { height: 100%%; display: flex; flex-direction: column; gap: 0.55em; padding: 1.05em 1.2em 1em;
        border: 1px solid var(--rule); border-radius: 8px; background: var(--paper);
        font-size: 0.86em; line-height: 1.55; transition: border-color 0.18s ease; }
.card:hover { border-color: var(--hover-border); }
.card-code { margin: 0; font-size: 0.82em; font-weight: 600; letter-spacing: 0.09em; color: var(--accent);
             font-variant-numeric: tabular-nums; }
.card h3 { margin: -0.2em 0 0; font-size: 1.32em; line-height: 1.25; font-weight: 600; color: var(--ink-strong); }
.card h3 a { color: inherit; text-decoration: none; }
.card h3 a:hover { text-decoration: underline; text-decoration-color: var(--hover-border); }
.card-blurb { margin: 0; }
.progress { margin: 0.15em 0 0; display: flex; flex-direction: column; align-items: flex-start; gap: 0.3em;
            font-size: 0.9em; color: var(--muted); }
.segments { display: inline-flex; gap: 3px; }
.segments i { display: block; width: 1.1em; height: 0.42em; border-radius: 2px;
              border: 1px solid var(--rule-strong); }
.segments i.done { background: var(--accent); border-color: var(--accent); }
.card-links { margin: auto 0 0; padding-top: 0.55em; display: flex; flex-wrap: wrap; gap: 0.3em 1.2em;
              border-top: 1px solid var(--rule); }
.card-links a { font-weight: 600; text-decoration: none; }
.card-links a:hover { text-decoration: underline; }
.nowrap { white-space: nowrap; }
.card-note { margin: 0; font-size: 0.9em; color: var(--muted); }

/* Reading order */
.order { margin: 0; padding: 1.2rem 1.2rem 1rem; background: var(--subtle); border: 1px solid var(--rule); border-radius: 8px; }
.order svg { display: block; width: 100%%; height: auto; margin: 0 auto 0.8rem; }
.order .narrow { display: none; }
@media (max-width: 640px) { .order .wide { display: none; } .order .narrow, .order .wide.narrow-too { display: block; } }
.order figcaption { max-width: var(--measure); color: var(--ink); font-size: 0.9em; }
.order figcaption p { margin: 0 0 0.4em; }
.node rect { fill: var(--paper); stroke: var(--rule-strong); stroke-width: 1.2; }
.node.book rect { stroke: var(--accent); }
.node.planned rect { stroke-dasharray: 5 4; fill: none; }
.node .code { font-size: 17px; font-weight: 600; fill: var(--ink-strong); }
.node.book .code { fill: var(--accent); }
.node .name { font-size: 12.5px; fill: var(--muted); }
.edge { stroke: var(--muted); stroke-width: 1.3; fill: none; }
.edge.optional { stroke-dasharray: 4 4; }
.arrowhead { fill: var(--muted); }

/* Footer */
.site-footer { padding: 1.8rem 0 3rem; font-size: 0.82em; color: var(--muted); }
.site-footer p { margin: 0 0 0.5em; max-width: var(--measure); }
.site-footer a { color: var(--muted); }
.site-footer a:hover { color: var(--ink-strong); }
.sources a { margin-right: 0.9em; white-space: nowrap; }

/* Math rendered at build time (mathjax.css styles the glyphs) */
mjx-container { letter-spacing: normal; word-spacing: normal; }

/* 404 */
.not-found { max-width: var(--measure); padding: 3rem 0; }
"""

# The books' setting (main.js stores it as "book-theme"): one choice for the whole site
THEME_SCRIPT = """(function () {
    var theme = null;
    try { theme = localStorage.getItem('book-theme'); } catch (e) {}
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
})();"""

TOGGLE_SCRIPT = """(function () {
    var button = document.querySelector('.theme-toggle');
    if (!button) return;
    var root = document.documentElement;
    function current() {
        return root.dataset.theme
            || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    }
    function show() {
        var dark = current() === 'dark';
        button.setAttribute('aria-pressed', dark ? 'true' : 'false');
        button.title = dark ? 'Light mode' : 'Dark mode';
    }
    button.hidden = false;
    show();
    button.addEventListener('click', function () {
        var next = current() === 'dark' ? 'light' : 'dark';
        root.dataset.theme = next;
        try { localStorage.setItem('book-theme', next); } catch (e) {}
        show();
    });
})();"""

SUN = ('<svg class="sun" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor"><path d="M8 11a3 3 0 1 1 0-6 '
       '3 3 0 0 1 0 6m0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8M8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0m0 '
       '13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13m8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 '
       '.5.5M3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8m10.657-5.657a.5.5 0 0 1 0 .707l-1.414 '
       '1.415a.5.5 0 1 1-.707-.708l1.414-1.414a.5.5 0 0 1 .707 0m-9.193 9.193a.5.5 0 0 1 0 .707L3.05 13.657a.5.5 0 '
       '0 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0m9.193 2.121a.5.5 0 0 1-.707 0l-1.414-1.414a.5.5 0 0 1 '
       '.707-.707l1.414 1.414a.5.5 0 0 1 0 .707M4.464 4.465a.5.5 0 0 1-.707 0L2.343 3.05a.5.5 0 1 1 .707-.707l1.414 '
       '1.414a.5.5 0 0 1 0 .708"/></svg>')
MOON = ('<svg class="moon" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor"><path d="M6 .278a.77.77 0 0 1 '
        '.08.858 7.2 7.2 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277q.792-.001 1.533-.16a.79.79 0 0 1 .81.316.73.73 '
        '0 0 1-.031.893A8.35 8.35 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.75.75 0 0 1 6 '
        '.278"/></svg>')


def _font_faces(base: str) -> str:
    """The books' STIX Two Text @font-face rules (from the engine stylesheet), with their
    URLs pointing at a book's copy of the fonts (`base`, e.g. "fd1/")."""
    css = (ENGINE_ROOT / "templates" / "html" / "styles.css").read_text(encoding="utf-8")
    faces = re.findall(r"@font-face\s*\{[^}]*font-family:\s*'STIX Two Text'[^}]*\}", css)
    return "\n".join(face.replace("url('fonts/", f"url('{base}fonts/") for face in faces)


def _page(title: str, body: str, head_extra: str = "", scripts: str = "", font_base: str | None = None) -> str:
    style = PAGE_STYLE % {"light": TOKENS_LIGHT, "dark": TOKENS_DARK}
    if font_base is not None:
        style = _font_faces(font_base) + "\n" + style
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{escape(title)}</title>
{head_extra}<script>{THEME_SCRIPT}</script>
<style>{style}</style>
</head>
<body>
{body}
{scripts}</body>
</html>
"""


# =============================================================================
# Groups and text
# =============================================================================

def groups(manifest: dict) -> list[dict]:
    """The landing page's sections: the manifest's `landing.groups`, else one per series
    in the order the books list them. Books no group names go last, by series."""
    by_prefix = {entry["prefix"]: entry for entry in manifest["books"]}
    declared = manifest["landing"].get("groups")
    if not declared:
        declared, index = [], {}
        for entry in manifest["books"]:
            series = entry.get("series") or ""
            if series not in index:
                index[series] = {"title": series, "books": []}
                declared.append(index[series])
            index[series]["books"].append(entry["prefix"])
    result, placed = [], set()
    for group in declared:
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


class Text:
    """Turns the manifest's strings into HTML. With `math`, TeX is kept for the renderer;
    without, it becomes plain text (\\nN -> ℕ) through the books' macros."""

    def __init__(self, macros: dict | None, math: bool):
        self.macros = macros or {}
        self.math = math

    def title(self, text: str) -> str:
        """A title (plain text in the manifest or config): escaped."""
        return escape(text if self.math else plain_text(text, self.macros), quote=False)

    def html(self, text: str) -> str:
        """A blurb or note (HTML in the manifest)."""
        return text if self.math else _plain_html(text, self.macros)


def _plain_html(text: str, macros: dict) -> str:
    """TeX math inside an HTML string as plain text, the markup left alone."""
    return re.sub(r"\\\((.+?)\\\)", lambda m: plain_text(m.group(0), macros), text)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def _site_name(url: str) -> str:
    return re.sub(r"^https?://", "", url).rstrip("/")


# =============================================================================
# Cards
# =============================================================================

def progress(entry: dict) -> str:
    """The progress line: chapters written (in the book's config) against chapters
    planned (the manifest's `planned`), and sections; a bar of one mark per chapter."""
    chapters, sections, planned = entry.get("chapter-count"), entry.get("section-count"), entry.get("planned")
    if chapters is None:
        return ""
    parts = []
    if isinstance(planned, int) and planned >= chapters:
        parts.append(f"{chapters} of {planned} chapters written")
    else:
        parts.append(f"{chapters} chapter{'s' if chapters != 1 else ''}")
    if sections:
        parts.append(f"{sections} section{'s' if sections != 1 else ''}")
    bar = ""
    if isinstance(planned, int) and 0 < planned <= 40 and planned >= chapters:
        marks = "".join('<i class="done"></i>' if i < chapters else "<i></i>" for i in range(planned))
        bar = f'<span class="segments" aria-hidden="true">{marks}</span>'
    return f'<p class="progress">{bar}<span>{" · ".join(parts)}</span></p>'


def book_card(entry: dict, text: Text) -> str:
    prefix = escape(entry["prefix"])
    short = escape(entry.get("short") or entry["prefix"].upper())
    href = escape(entry["subdir"]) + "/"
    title_id = f"title-{prefix}"
    lines = [f'<article class="card" id="book-{prefix}" aria-labelledby="{title_id}" data-book="{prefix}">',
             f'<p class="card-code">{short}</p>',
             f'<h3 id="{title_id}"><a href="{href}">{text.title(entry["title"])}</a></h3>']
    if entry.get("blurb"):
        lines.append(f'<p class="card-blurb">{text.html(entry["blurb"])}</p>')
    lines.append(progress(entry))
    plain = escape(entry.get("title-plain") or plain_text(entry["title"]))
    links = [f'<a href="{href}" aria-label="Read {plain}">Read</a>']
    if entry.get("pdf-url"):
        links.append(f'<a href="{escape(entry["pdf-url"])}" aria-label="{plain} as a PDF">PDF</a>')
    if entry.get("canonical"):
        links.append(f'<a href="{escape(entry["canonical"])}" aria-label="{plain} on its own site">Own site</a>')
    lines.append(f'<p class="card-links">{" ".join(links)}</p>')
    if entry.get("canonical"):
        lines.append(f'<p class="card-note">Mirrored here from its own site, '
                     f'<span class="nowrap">{escape(_site_name(entry["canonical"]))}</span>, which holds the canonical copy.</p>')
    lines.append("</article>")
    return "\n".join(line for line in lines if line)


def link_card(link: dict, text: Text) -> str:
    href = escape(link.get("href", ""))
    title_id = f"title-{_slug(link.get('title', ''))}"
    lines = [f'<article class="card" aria-labelledby="{title_id}">']
    if link.get("label"):
        lines.append(f'<p class="card-code">{escape(link["label"])}</p>')
    lines.append(f'<h3 id="{title_id}"><a href="{href}">{text.title(link.get("title", ""))}</a></h3>')
    if link.get("blurb"):
        lines.append(f'<p class="card-blurb">{text.html(link["blurb"])}</p>')
    lines.append(f'<p class="card-links"><a href="{href}">{escape(link.get("action") or "Open")}</a></p>')
    lines.append("</article>")
    return "\n".join(lines)


# =============================================================================
# Reading-order diagram
# =============================================================================

NODE_W, NODE_H = 112, 52


def _diagram_svg(diagram: dict, manifest: dict, key: str, css_class: str, caption_id: str) -> str:
    """One layout of the diagram (`key` is "at" or "at-narrow") as inline SVG."""
    nodes = [n for n in diagram.get("nodes") or [] if isinstance(n.get(key) or n.get("at"), list)]
    if not nodes:
        return ""
    gap_x, gap_y, pad = (44, 34, 6) if key == "at" else (22, 30, 6)
    by_prefix = {e["prefix"]: e for e in manifest["books"]}
    place = {}
    for node in nodes:
        col, row = (node.get(key) or node["at"])[:2]
        place[node["id"]] = (pad + col * (NODE_W + gap_x) + NODE_W / 2, pad + row * (NODE_H + gap_y) + NODE_H / 2)
    width = max(x for x, _ in place.values()) + NODE_W / 2 + pad
    height = max(y for _, y in place.values()) + NODE_H / 2 + pad
    marker = f"arrow-{css_class}"
    parts = [f'<svg class="{css_class}" viewBox="0 0 {width:g} {height:g}" style="max-width:{width * 1.15:g}px" '
             f'role="img" aria-labelledby="{caption_id}" xmlns="http://www.w3.org/2000/svg">',
             f'<defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
             f'orient="auto-start-reverse"><path class="arrowhead" d="M0,0 L10,5 L0,10 z"/></marker></defs>']
    for edge in diagram.get("edges") or []:
        if isinstance(edge, list):
            edge = {"from": edge[0], "to": edge[1]}
        if edge["from"] not in place or edge["to"] not in place:
            continue
        (x1, y1), (x2, y2) = place[edge["from"]], place[edge["to"]]
        dx, dy = x2 - x1, y2 - y1

        def clip(sign):    # where the line between the centres leaves a box, plus a little air
            tx = (NODE_W / 2 + 3) / abs(dx) if dx else float("inf")
            ty = (NODE_H / 2 + 3) / abs(dy) if dy else float("inf")
            return min(tx, ty) * sign
        t1, t2 = clip(1), 1 - clip(1)
        a = (x1 + dx * t1, y1 + dy * t1)
        b = (x1 + dx * t2, y1 + dy * t2)
        kind = " optional" if edge.get("kind") == "optional" else ""
        parts.append(f'<line class="edge{kind}" x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                     f'marker-end="url(#{marker})"/>')
    for node in nodes:
        x, y = place[node["id"]]
        entry = by_prefix.get(node.get("book") or "")
        kind = "planned" if node.get("planned") else ("book" if entry else "")
        name = node.get("name") or ""
        if node.get("planned"):
            name = f"{name} (planned)" if name else "planned"
        label = node.get("code") or (entry.get("short") if entry else None) or node["id"]
        parts.append(f'<g class="node {kind}"><rect x="{x - NODE_W / 2:g}" y="{y - NODE_H / 2:g}" '
                     f'width="{NODE_W}" height="{NODE_H}" rx="7"/>'
                     f'<text class="code" x="{x:g}" y="{y - 2:g}" text-anchor="middle">{escape(label)}</text>'
                     f'<text class="name" x="{x:g}" y="{y + 15:g}" text-anchor="middle">{escape(name)}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def diagram_section(manifest: dict, text: Text) -> str:
    diagram = manifest["landing"].get("diagram")
    if not diagram or not diagram.get("nodes"):
        return ""
    caption_id = "reading-order-caption"
    wide = _diagram_svg(diagram, manifest, "at", "wide", caption_id)
    has_narrow = any(n.get("at-narrow") for n in diagram["nodes"])
    narrow = _diagram_svg(diagram, manifest, "at-narrow", "narrow", caption_id) if has_narrow else ""
    if not narrow:
        wide = wide.replace('class="wide"', 'class="wide narrow-too"')
    caption = diagram.get("caption") or ""
    title = diagram.get("title") or "Reading order"
    return (f'<section class="band" aria-labelledby="reading-order">\n'
            f'<div class="band-head"><h2 id="reading-order">{escape(title)}</h2>'
            + (f"<p>{text.html(diagram['intro'])}</p>" if diagram.get("intro") else "")
            + f'</div>\n<figure class="order">{wide}{narrow}'
            f'<figcaption id="{caption_id}"><p>{text.html(caption)}</p></figcaption></figure>\n</section>')


# =============================================================================
# The page
# =============================================================================

def landing_page(manifest: dict, math: bool = False, font_base: str | None = None,
                 math_css: str | None = None) -> str:
    """index.html at the library root. Titles are text; `tagline`, `usage`, `status`,
    blurbs, `licence` and `footer` may hold HTML (the manifest is the site owner's own
    file). With `math`, TeX is left in for render_landing_math; without, it is plain text."""
    landing = manifest["landing"]
    text = Text(manifest.get("macros"), math)
    title = landing.get("title") or "Library"
    tagline = landing.get("tagline") or landing.get("intro") or ""
    status = landing.get("status") or landing.get("badge") or ""
    toggle = (f'<button class="theme-toggle" type="button" hidden aria-pressed="false" '
              f'aria-label="Dark mode">{SUN}{MOON}</button>')
    parts = ['<a class="skip-link" href="#books">Skip to the books</a>',
             '<div class="page">',
             '<header class="masthead">', toggle, f"<h1>{escape(title)}</h1>"]
    if tagline:
        parts.append(f'<p class="tagline">{text.html(tagline)}</p>')
    if landing.get("usage"):
        parts.append(f'<p class="usage">{text.html(landing["usage"])}</p>')
    if status:
        parts.append(f'<p class="status">{text.html(status)}</p>')
    parts.append("</header>")
    parts.append('<main id="books">')
    parts.append(diagram_section(manifest, text))
    # Sections with a single card sit side by side on a wide screen (a run of them shares
    # one row), so a lone card does not leave two thirds of the page empty
    run = []

    def flush():
        if len(run) > 1:
            parts.append('<div class="band-row">' + "\n".join(run) + "</div>")
        else:
            parts.extend(run)
        run.clear()

    for group in groups(manifest):
        if not group["entries"] and not group.get("links"):
            continue
        heading_id = f"series-{_slug(group['title'] or 'books')}"
        blurb = group.get("blurb") or group.get("intro")
        cards = [book_card(entry, text) for entry in group["entries"]]
        cards += [link_card(link, text) for link in group.get("links") or []]
        section = (f'<section class="band" aria-labelledby="{heading_id}">'
                   f'<div class="band-head"><h2 id="{heading_id}">{escape(group["title"] or "Books")}</h2>'
                   + (f"<p>{text.html(blurb)}</p>" if blurb else "") + "</div>"
                   + '<ul class="cards">' + "".join(f"<li>{card}</li>" for card in cards) + "</ul></section>")
        if len(cards) == 1:
            run.append(section)
        else:
            flush()
            parts.append(section)
    flush()
    parts.append("</main>")
    footer = []
    if landing.get("licence"):
        footer.append(f"<p>{landing['licence']}</p>")
    if landing.get("sources"):
        links = " ".join(f'<a href="{escape(s.get("href", ""))}">{escape(s.get("title", ""))}</a>'
                         for s in landing["sources"])
        label = escape(landing.get("sources-label") or "Source")
        footer.append(f'<p class="sources">{label}: {links}</p>')
    if landing.get("footer"):
        footer.append(f"<p>{landing['footer']}</p>")
    if footer:
        parts.append('<footer class="site-footer">' + "\n".join(footer) + "</footer>")
    parts.append("</div>")
    description = re.sub(r"<[^>]+>", "", plain_text(tagline, manifest.get("macros")))
    head = (f'<link rel="canonical" href="{escape(manifest["site-url"])}">\n'
            + (f'<meta name="description" content="{escape(description)}">\n' if description else "")
            + f'<meta property="og:title" content="{escape(title)}">\n'
            + f'<meta property="og:type" content="website">\n'
            + f'<meta property="og:url" content="{escape(manifest["site-url"])}">\n'
            + '<link rel="icon" href="favicon.svg" type="image/svg+xml">\n'
            + (f'<link rel="stylesheet" href="{escape(math_css)}">\n' if math and math_css else ""))
    return _page(title, "\n".join(p for p in parts if p), head, f"<script>{TOGGLE_SCRIPT}</script>\n", font_base)


def render_landing_math(page: str, mathjax: Path, macros: dict) -> str | None:
    """The page with its TeX rendered by MathJax under Node (build/render_math.cjs), the way
    the books' pages are. Only the <body>'s math is sent, so the rest of the page (the SVG
    above all) is not re-serialized. None if rendering failed."""
    head, sep, body = page.partition("<body>")
    if not sep or not re.search(r"\\\(|\\\[", body):
        return page
    with tempfile.TemporaryDirectory(prefix="landing-math-") as tmp:
        snippets = re.findall(r"<(h3|p)\b([^>]*)>((?:(?!</\1>).)*?\\\(.*?)</\1>", body, re.S)
        if not snippets:
            return page
        doc = "".join(f'<div data-snippet="{i}">{inner}</div>\n' for i, (_, _, inner) in enumerate(snippets))
        source = Path(tmp) / "landing.html"
        source.write_text(f"<!DOCTYPE html><html><head></head><body>{doc}</body></html>", encoding="utf-8")
        job = {"mathjax": str(mathjax), "macros": macros, "pages": [str(source)], "shards": [],
               "css": str(Path(tmp) / "mathjax.css")}
        result = subprocess.run(["node", str(ENGINE_ROOT / "build" / "render_math.cjs")],
                                input=json.dumps(job), capture_output=True, text=True)
        if result.returncode != 0:
            return None
        rendered = source.read_text(encoding="utf-8")
    pieces = dict(re.findall(r'<div data-snippet="(\d+)">(.*?)</div>\s*(?=<div data-snippet=|</body>)', rendered, re.S))
    if len(pieces) != len(snippets) or "data-mjx-error" in rendered:
        return None
    for i, (tag, attrs, inner) in enumerate(snippets):
        body = body.replace(f"<{tag}{attrs}>{inner}</{tag}>", f"<{tag}{attrs}>{pieces[str(i)]}</{tag}>", 1)
    return head + sep + body


# =============================================================================
# 404
# =============================================================================

def not_found_page(manifest: dict, font_base: str | None = None) -> str:
    """The root 404.html. GitHub Pages serves only the root one for a project site, so it
    works out from the address which book the reader was in and offers that book."""
    site_path = re.match(r"^[a-z]+://[^/]+(/.*)?$", manifest["site-url"]).group(1) or "/"
    title = manifest["landing"].get("title") or "Library"
    books = [{"subdir": e["subdir"], "title": e.get("title-plain") or plain_text(e["title"])}
             for e in manifest["books"]]
    body = f"""<div class="page"><main class="not-found">
<p><a href="{escape(site_path)}">{escape(title)}</a></p>
<h1>Page not found</h1>
<p>This page does not exist, or it moved when a book was reorganized.</p>
<p id="book-hint" hidden></p>
<p><a href="{escape(site_path)}">Go to the library's front page</a>.</p>
</main></div>"""
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
    base = None if font_base is None else site_path + font_base
    return _page(f"Page not found – {title}", body, '<meta name="robots" content="noindex">\n', script, base)
