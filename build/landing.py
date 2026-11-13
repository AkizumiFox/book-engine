"""
Build System Landing Module
===========================
The library's front page (index.html) and its root 404.html, generated from the library
manifest (build/library.py) and from what the build learned about each book.

The landing page is a product-style front page in the books' own look: Inter for the
interface and headings, Source Serif 4 for the blurbs (the fonts a book already serves,
so nothing is fetched from elsewhere), the same OKLCH colour tokens and light/dark themes
(the same saved "book-theme" choice).

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

PAGE_STYLE = """
%(tokens)s
:root {
  --font-body: 'Source Serif 4', 'Source Serif 4 Fallback', Georgia, serif;
  --font-ui: 'Inter', 'Inter Fallback', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  --page-width: 72rem;
  --gutter: max(1rem, env(safe-area-inset-left));
  --radius: 12px;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
  --shadow-color: 220 25%% 20%%;
  --shadow-xs: 0 1px 2px hsl(var(--shadow-color) / 0.06);
  --shadow-sm: 0 1px 2px hsl(var(--shadow-color) / 0.06), 0 2px 6px -2px hsl(var(--shadow-color) / 0.08);
  --shadow-md: 0 2px 4px -1px hsl(var(--shadow-color) / 0.06), 0 14px 32px -12px hsl(var(--shadow-color) / 0.2);
  --touch: 2.25rem;
}
@media (pointer: coarse) { :root { --touch: 2.75rem; } }
@media (min-width: 640px) { :root { --gutter: 2rem; } }
:root[data-theme="dark"] {
  color-scheme: dark;
  --shadow-color: 220 40%% 2%%;
  --shadow-xs: 0 1px 2px hsl(var(--shadow-color) / 0.4);
  --shadow-sm: 0 1px 2px hsl(var(--shadow-color) / 0.4), 0 2px 6px -2px hsl(var(--shadow-color) / 0.5);
  --shadow-md: 0 2px 4px -1px hsl(var(--shadow-color) / 0.4), 0 16px 36px -12px hsl(var(--shadow-color) / 0.7);
}

*, *::before, *::after { box-sizing: border-box; }
html { font-size: 16px; -webkit-text-size-adjust: 100%%; scroll-padding-top: 5rem; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: var(--font-ui); font-size: 1rem; line-height: 1.6;
  font-kerning: normal; font-variant-numeric: lining-nums proportional-nums; font-optical-sizing: auto;
  text-rendering: optimizeLegibility; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
}
a { color: var(--accent); text-decoration-thickness: from-font; text-underline-offset: 0.18em;
    text-decoration-color: color-mix(in srgb, var(--accent) 35%%, transparent); }
a:hover { color: var(--accent-strong); text-decoration-color: currentColor; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.skip-link { position: fixed; left: var(--gutter); top: 0; z-index: 30; padding: 0.5rem 0.9rem; border-radius: 6px;
             background: var(--ink-strong); color: var(--paper); text-decoration: none; transform: translateY(-120%%); }
.skip-link:focus { top: 0.6rem; transform: none; }
.visually-hidden { position: absolute !important; width: 1px; height: 1px; overflow: hidden;
                   clip-path: inset(50%%); white-space: nowrap; }
.wrap, .page { max-width: calc(var(--page-width) + 2 * var(--gutter)); margin: 0 auto;
        padding-inline: max(var(--gutter), env(safe-area-inset-left)) max(var(--gutter), env(safe-area-inset-right)); }
.tnum { font-variant-numeric: tabular-nums; }

/* Header */
.top { position: sticky; top: 0; z-index: 20; padding-top: env(safe-area-inset-top);
       background: color-mix(in srgb, var(--paper) 82%%, transparent);
       -webkit-backdrop-filter: saturate(1.6) blur(14px); backdrop-filter: saturate(1.6) blur(14px);
       border-bottom: 1px solid transparent; transition: border-color 0.2s;
       view-transition-name: site-header; }
.top.scrolled { border-bottom-color: var(--rule); }
.top .wrap { display: flex; align-items: center; gap: 0.5rem; height: 3.5rem; }
.brand { display: inline-flex; align-items: center; gap: 0.5rem; min-height: var(--touch); margin-right: auto;
         color: var(--ink-strong); font-weight: 650; font-size: 0.9375rem; letter-spacing: -0.012em; text-decoration: none; }
.brand:hover { color: var(--ink-strong); }
.brand svg { width: 1.375rem; height: 1.375rem; fill: var(--ink-strong); stroke: var(--paper); stroke-width: 1.9;
             stroke-linecap: round; stroke-linejoin: round; }
.brand svg rect { stroke: none; }
.top-nav { display: flex; gap: 0.125rem; }
.top-nav a { display: inline-flex; align-items: center; min-height: var(--touch); padding: 0 0.7rem; border-radius: 6px;
             color: var(--muted); font-size: 0.875rem; font-weight: 500; text-decoration: none; }
.top-nav a:hover { background: var(--hover-wash); color: var(--ink-strong); }
@media (max-width: 640px) { .top-nav { display: none; } }
.theme-toggle { position: relative; display: inline-flex; align-items: center; justify-content: center;
                width: var(--touch); height: var(--touch); padding: 0; border: 0; border-radius: 6px;
                background: transparent; color: var(--muted); cursor: pointer;
                transition: background-color 0.12s, color 0.12s, transform 0.12s; }
.theme-toggle:hover { background: var(--hover-wash); color: var(--ink-strong); }
.theme-toggle:active { transform: scale(0.94); }
.theme-toggle svg { position: absolute; width: 1.125rem; height: 1.125rem;
                    transition: opacity 0.18s var(--ease-out), transform 0.26s var(--ease-out); }
.theme-toggle .moon { margin-left: 1px; }
.theme-toggle .sun, :root[data-theme="dark"] .theme-toggle .moon { opacity: 0; transform: rotate(-60deg) scale(0.5); }
:root[data-theme="dark"] .theme-toggle .sun { opacity: 1; transform: none; }

/* Hero */
.hero { padding: clamp(3rem, 9vw, 6.5rem) 0 clamp(2.5rem, 6vw, 4rem); }
.status { display: inline-flex; align-items: center; gap: 0.55rem; margin: 0 0 1.5rem; padding: 0.35rem 0.8rem 0.35rem 0.6rem;
          border: 1px solid var(--rule); border-radius: 999px; background: var(--subtle);
          color: var(--muted); font-size: 0.8125rem; line-height: 1.4; max-width: 100%%; }
.status::before { content: ""; flex: none; width: 0.5rem; height: 0.5rem; border-radius: 50%%; background: var(--note);
                  box-shadow: 0 0 0 3px color-mix(in srgb, var(--note) 22%%, transparent); }
.hero h1 { margin: 0 0 0.35em; color: var(--ink-strong); font-size: clamp(2.6rem, 7vw, 4.5rem); font-weight: 700;
           line-height: 1.02; letter-spacing: -0.04em; text-wrap: balance; }
.tagline { margin: 0 0 1.25rem; max-width: 34em; color: var(--ink); font-family: var(--font-body);
           font-size: clamp(1.2rem, 2.2vw, 1.5rem); line-height: 1.45; text-wrap: pretty; }
.usage { margin: 0 0 2rem; max-width: 40em; color: var(--muted); font-size: 0.9375rem; line-height: 1.6; text-wrap: pretty; }
.actions { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.btn { display: inline-flex; align-items: center; gap: 0.5rem; min-height: 2.75rem; padding: 0 1.1rem;
       border: 1px solid var(--rule-strong); border-radius: 8px; background: var(--paper); color: var(--ink-strong);
       font-size: 0.9375rem; font-weight: 600; text-decoration: none; box-shadow: var(--shadow-xs);
       transition: border-color 0.18s var(--ease-out), box-shadow 0.18s var(--ease-out), transform 0.12s var(--ease-out), background-color 0.18s; }
.btn:hover { color: var(--ink-strong); border-color: var(--hover-border); box-shadow: var(--shadow-sm); }
.btn:active { transform: scale(0.98); }
.btn.primary { border-color: transparent; background: var(--ink-strong); color: var(--paper); }
.btn.primary:hover { color: var(--paper); background: color-mix(in srgb, var(--ink-strong) 88%%, var(--accent)); }
.btn svg { width: 1rem; height: 1rem; transition: transform 0.18s var(--ease-out); }
.btn:hover svg { transform: translateX(3px); }
.btn .code { padding: 0.25em 0.4em; border-radius: 4px; background: color-mix(in srgb, var(--paper) 18%%, transparent);
             font-size: 0.75rem; letter-spacing: 0.02em; line-height: 1; text-box: trim-both cap alphabetic; }

.hero .wrap { display: grid; grid-template-columns: minmax(0, 1fr) minmax(16rem, 21rem); align-items: end; gap: 2rem 4rem; }
@media (max-width: 900px) { .hero .wrap { grid-template-columns: 1fr; } }
.hero-stats { padding: 1.25rem 1.25rem 1.1rem; border: 1px solid var(--rule); border-radius: 16px; background: var(--pane);
              box-shadow: var(--shadow-xs); }
.hero-stats dl { display: grid; gap: 0; margin: 0; }
.stat { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; padding: 0.7rem 0;
        border-bottom: 1px solid var(--rule); }
.stat:first-child { padding-top: 0; }
.stat dt { color: var(--muted); font-size: 0.8125rem; font-weight: 500; }
.stat dd { display: flex; align-items: baseline; gap: 0.5rem; margin: 0; }
.stat-num { color: var(--ink-strong); font-size: 1.75rem; font-weight: 650; letter-spacing: -0.03em; line-height: 1;
            font-variant-numeric: tabular-nums; }
.stat-note { color: var(--faint); font-size: 0.75rem; white-space: nowrap; font-variant-numeric: tabular-nums; }
.stat-bar { height: 6px; margin-top: 1rem; border-radius: 999px; background: var(--rule); overflow: hidden; }
.stat-bar span { display: block; height: 100%%; background: var(--accent); border-radius: inherit;
                 transform-origin: 0 50%%; transform: scaleX(var(--w)); }

/* Sections */
.band { padding: 3.5rem 0; border-top: 1px solid var(--rule); }
.band-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 0.5rem 2rem;
             margin-bottom: 1.75rem; }
.band h2 { margin: 0; color: var(--ink-strong); font-size: 1.625rem; font-weight: 650; letter-spacing: -0.022em; line-height: 1.2; }
.band-head p { margin: 0; max-width: 36rem; color: var(--muted); font-size: 0.9375rem; text-wrap: pretty; }
.eyebrow { display: block; margin-bottom: 0.4rem; color: var(--accent); font-size: 0.75rem; font-weight: 600;
           letter-spacing: 0.08em; text-transform: uppercase; font-feature-settings: "case"; }

/* Reading-order map */
.order { margin: 0; padding: clamp(1rem, 3vw, 2rem); border: 1px solid var(--rule); border-radius: 16px;
         background: radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--ink) 10%%, transparent) 1px, transparent 0) 0 0 / 18px 18px, var(--pane); }
.order svg { display: block; width: 100%%; height: auto; margin: 0 auto; overflow: visible; }
.order .narrow { display: none; }
@media (max-width: 640px) { .order .wide { display: none; } .order .narrow, .order .wide.narrow-too { display: block; } }
.node rect { fill: var(--paper); stroke: var(--rule-strong); stroke-width: 1;
             transition: stroke 0.18s var(--ease-out), fill 0.18s var(--ease-out); }
.node.book rect { stroke: var(--accent-line); }
.node.planned rect, .node.nobook rect { stroke-dasharray: 4 4; fill: color-mix(in srgb, var(--paper) 60%%, transparent); }
.node text { font-family: var(--font-ui); }
.node .code { font-size: 14px; font-weight: 700; fill: var(--ink-strong); letter-spacing: 0.01em; }
.node.book .code { fill: var(--accent); }
.node .name { font-size: 11.5px; font-weight: 500; fill: var(--muted); }
.node .mine { font-size: 10px; font-weight: 600; fill: var(--success); }
a.node { cursor: pointer; outline: none; }
a.node:hover rect, a.node:focus-visible rect, .node.lit rect { stroke: var(--accent); fill: var(--accent-soft); }
a.node:focus-visible rect { stroke-width: 2; }
.edge { stroke: var(--rule-strong); stroke-width: 1.5; fill: none; transition: stroke 0.18s var(--ease-out); }
.edge.optional { stroke-dasharray: 4 4; }
.edge.lit { stroke: var(--accent); }
.arrowhead { fill: var(--rule-strong); }
.order details { max-width: 46rem; margin: 1.25rem 0 0; color: var(--muted); font-size: 0.875rem; }
.order summary { display: inline-flex; align-items: center; gap: 0.4rem; min-height: var(--touch); cursor: pointer;
                 color: var(--ink); font-weight: 550; list-style: none; }
.order summary::-webkit-details-marker { display: none; }
.order summary::before { content: ""; width: 0.8rem; height: 0.8rem; background: currentColor;
  -webkit-mask: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'><path d='m9 6 6 6-6 6'/></svg>") center / contain no-repeat;
  mask: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'><path d='m9 6 6 6-6 6'/></svg>") center / contain no-repeat;
  transition: transform 0.22s var(--ease-out); }
.order details[open] summary::before { transform: rotate(90deg); }
.order details p { margin: 0.25rem 0 0; line-height: 1.65; text-wrap: pretty; }

/* Volume cards */
.series + .series, .series + .series-row, .series-row + .series { margin-top: 2.75rem; }
.series-row { display: grid; gap: 0 1rem; grid-template-columns: repeat(auto-fill, minmax(min(100%%, 19rem), 1fr)); }
.series-row > .series { display: grid; grid-row: span 2; grid-template-rows: subgrid; margin: 0; }
.series-row .series-head { flex-direction: column; gap: 0.25rem; }
.series-row .cards { grid-template-columns: 1fr; }
@media (max-width: 700px) { .series-row > .series + .series { margin-top: 2.75rem; } }
.series-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.25rem 1.25rem; margin-bottom: 1rem; }
.series-head h3 { margin: 0; color: var(--ink-strong); font-size: 1rem; font-weight: 650; letter-spacing: -0.01em; }
.series-head p { margin: 0; max-width: 44rem; color: var(--muted); font-size: 0.875rem; text-wrap: pretty; }
.cards { list-style: none; margin: 0; padding: 0; display: grid; gap: 1rem;
         grid-template-columns: repeat(auto-fill, minmax(min(100%%, 19rem), 1fr)); }
.cards > li { display: flex; }
.card { position: relative; display: flex; flex-direction: column; gap: 0.75rem; width: 100%%;
        padding: 1.25rem 1.25rem 1rem; border: 1px solid var(--rule); border-radius: var(--radius);
        background: var(--paper); box-shadow: var(--shadow-xs);
        transition: border-color 0.2s var(--ease-out), box-shadow 0.25s var(--ease-out), transform 0.25s var(--ease-out); }
.card:has(.card-link:hover), .card:has(.card-link:focus-visible) {
  border-color: var(--hover-border); box-shadow: var(--shadow-md); transform: translateY(-2px); }
.card-top { display: flex; align-items: center; gap: 0.5rem; }
.card-code { padding: 0.35em 0.5em; border-radius: 5px; background: var(--accent-soft); color: var(--accent);
             font-size: 0.75rem; font-weight: 700; letter-spacing: 0.02em; line-height: 1;
             font-variant-numeric: tabular-nums; text-box: trim-both cap alphabetic; }
.card-series { color: var(--faint); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.07em;
               text-transform: uppercase; font-feature-settings: "case"; }
.card-arrow { margin-left: auto; width: 1.1rem; height: 1.1rem; color: var(--faint);
              transition: transform 0.2s var(--ease-out), color 0.2s; }
.card:has(.card-link:hover) .card-arrow { color: var(--accent); transform: translate(2px, -2px); }
.card h3 { margin: 0; color: var(--ink-strong); font-size: 1.1875rem; font-weight: 650; line-height: 1.3;
           letter-spacing: -0.015em; text-wrap: balance; }
.card-link { color: inherit; text-decoration: none; }
.card-link::after { content: ""; position: absolute; inset: 0; border-radius: inherit; }   /* the whole card is the link */
.card-link:hover { color: inherit; }
.card-link:focus-visible { outline: none; }
.card:has(.card-link:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
.card-blurb { margin: 0; color: var(--muted); font-family: var(--font-body); font-size: 0.96875rem; line-height: 1.6;
              text-wrap: pretty; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 4; overflow: hidden; }
.card.expanded .card-blurb { -webkit-line-clamp: unset; }
.card-more { position: relative; z-index: 1; align-self: flex-start; margin-top: -0.4rem; padding: 0.25rem 0;
             border: 0; background: none; color: var(--accent); font: inherit; font-size: 0.8125rem; font-weight: 550; cursor: pointer; }
.card-more:hover { text-decoration: underline; }
.card-more[hidden] { display: none; }
.card-meta { margin-top: auto; display: grid; gap: 0.5rem; padding-top: 0.25rem; }
.meter-row { display: flex; align-items: center; gap: 0.75rem; color: var(--muted); font-size: 0.8125rem; }
.segments { display: flex; flex: 1; gap: 3px; min-width: 4rem; max-width: 9rem; }
.segments i { flex: 1; height: 0.375rem; border-radius: 2px; background: var(--rule); }
.segments i.done { background: var(--accent); }
.mine { min-height: 1.25rem; color: var(--faint); font-size: 0.75rem; }
.mine b { color: var(--success); font-weight: 600; }
.card-links { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 0.25rem 1rem;
              padding-top: 0.75rem; border-top: 1px solid var(--rule); font-size: 0.8125rem; }
.card-links a { display: inline-flex; align-items: center; min-height: 2rem; font-weight: 550; text-decoration: none; }
.card-links a:hover { text-decoration: underline; }
@media (pointer: coarse) { .card-links a { min-height: 2.75rem; } }
.card-note { margin: 0; color: var(--faint); font-size: 0.75rem; }
.nowrap { white-space: nowrap; }

/* Staggered arrival of the cards: each a little after the one before, transform and
   opacity only (no layout shift); off for reduced motion */
@media (prefers-reduced-motion: no-preference) {
  .cards > li { animation: rise 0.5s var(--ease-out) backwards; animation-delay: calc(var(--i, 0) * 45ms + 60ms); }
  .hero-text > *, .hero-stats { animation: rise 0.6s var(--ease-out) backwards; }
  .hero-text > :nth-child(2) { animation-delay: 40ms; }
  .hero-text > :nth-child(3) { animation-delay: 80ms; }
  .hero-text > :nth-child(4) { animation-delay: 120ms; }
  .hero-text > :nth-child(5) { animation-delay: 160ms; }
  .hero-stats { animation-delay: 200ms; }
}
@keyframes rise { from { opacity: 0; transform: translateY(8px); } }

/* Footer */
.site-footer { padding: 2.5rem 0 calc(3rem + env(safe-area-inset-bottom)); border-top: 1px solid var(--rule);
               color: var(--muted); font-size: 0.8125rem; line-height: 1.65; }
.site-footer p { margin: 0 0 0.6em; max-width: 46rem; text-wrap: pretty; }
.site-footer a { color: var(--muted); }
.site-footer a:hover { color: var(--ink-strong); }
.sources { display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; }
.sources a { white-space: nowrap; }

mjx-container { font-size: 100%% !important; letter-spacing: normal; word-spacing: normal; }
.tagline mjx-container, .card-blurb mjx-container { font-size: 107%% !important; }

@view-transition { navigation: auto; }
::view-transition-group(book-code) { animation-duration: 0.35s; animation-timing-function: var(--ease-out); }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 1ms !important; animation-duration: 1ms !important; }
  ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation: none !important; }
}

/* 404 */
.not-found { max-width: 40rem; padding: 4rem 0; }
.not-found h1 { font-size: 2.25rem; letter-spacing: -0.03em; }
"""

# The books' setting (main.js stores it as "book-theme"): one choice for the whole site
THEME_SCRIPT = """(function () {
    var theme = null, root = document.documentElement;
    try { theme = localStorage.getItem('book-theme'); } catch (e) {}
    root.dataset.theme = theme === 'light' || theme === 'dark' ? theme
        : (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
})();"""

TOGGLE_SCRIPT = """(function () {
    var root = document.documentElement;
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    var button = document.querySelector('.theme-toggle');
    function show() {
        var dark = root.dataset.theme === 'dark';
        button.setAttribute('aria-pressed', dark ? 'true' : 'false');
        button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
    }
    if (button) {
        button.hidden = false;
        show();
        button.addEventListener('click', function () {
            var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
            root.dataset.theme = next;          // optimistic: the page changes first
            show();
            try { localStorage.setItem('book-theme', next); } catch (e) {}
        });
    }
    // The header gains its rule once the page scrolls under it
    var top = document.querySelector('.top');
    var onScroll = function () { top && top.classList.toggle('scrolled', window.scrollY > 4); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    // Your progress, from what each book stored in this browser (sections marked done)
    document.querySelectorAll('[data-book-key]').forEach(function (el) {
        var done = [];
        try { done = JSON.parse(localStorage.getItem('atlas:done:' + el.dataset.bookKey)) || []; } catch (e) {}
        var total = +el.dataset.sections || 0;
        if (done.length) {
            el.innerHTML = '<b>' + done.length + '</b> of ' + total + ' sections done';
            var node = document.querySelector('.node[data-book="' + el.dataset.prefix + '"] .mine');
            if (node) node.textContent = Math.round(100 * done.length / Math.max(total, 1)) + '% done';
        }
    });
    // Blurbs longer than four lines fold, with a button to read the rest
    document.querySelectorAll('.card').forEach(function (card) {
        var blurb = card.querySelector('.card-blurb'), more = card.querySelector('.card-more');
        if (!blurb || !more) return;
        if (blurb.scrollHeight > blurb.clientHeight + 2) {
            more.hidden = false;
            more.addEventListener('click', function () {
                var open = card.classList.toggle('expanded');
                more.setAttribute('aria-expanded', open ? 'true' : 'false');
                more.textContent = open ? 'Less' : 'More';
            });
        }
    });
    // Map: hovering a volume lights it and the arrows into and out of it
    document.querySelectorAll('.order svg').forEach(function (svg) {
        svg.querySelectorAll('.node[data-id]').forEach(function (node) {
            var id = node.dataset.id;
            function light(on) {
                svg.querySelectorAll('.edge[data-from="' + id + '"], .edge[data-to="' + id + '"]').forEach(function (e) {
                    e.classList.toggle('lit', on);
                });
            }
            node.addEventListener('pointerenter', function () { light(true); });
            node.addEventListener('pointerleave', function () { light(false); });
            node.addEventListener('focus', function () { light(true); });
            node.addEventListener('blur', function () { light(false); });
        });
    });
    // Shared element: the clicked card's code chip becomes the book page's header chip
    var clicked = null;
    document.addEventListener('click', function (event) {
        clicked = event.target.closest && event.target.closest('.card, a.node');
    });
    window.addEventListener('pageswap', function (event) {
        if (!event.viewTransition || reduce.matches || !clicked) return;
        var chip = clicked.querySelector('.card-code');
        if (chip) chip.style.viewTransitionName = 'book-code';
    });
})();"""

SUN = ('<svg class="sun" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" '
       'stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 '
       '1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/></svg>')
MOON = ('<svg class="moon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linejoin="round"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>')
MARK = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="2.5" width="19" height="19" rx="5.5"/>'
        '<path d="M7 16.5 12 7l5 9.5M8.8 13.2h6.4"/></svg>')
ARROW = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>')
ARROW_UP = ('<svg class="card-arrow" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M8 7h9v9"/></svg>')


def _styles_css() -> str:
    return (ENGINE_ROOT / "templates" / "html" / "styles.css").read_text(encoding="utf-8")


def _tokens() -> str:
    """The books' colour tokens (OKLCH with sRGB fallbacks), from the engine stylesheet."""
    match = re.search(r"/\* tokens:start.*?\*/(.*?)/\* tokens:end \*/", _styles_css(), re.S)
    return match.group(1).replace("%", "%%") if match else ""


def _font_faces(base: str) -> str:
    """The books' @font-face rules (Source Serif 4, Inter and their metric-matched
    fallbacks), with their URLs pointing at a book's copy of the fonts (`base`)."""
    faces = re.findall(r"@font-face\s*\{[^}]*font-family:\s*'(?:Source Serif 4|Inter)(?: Fallback)?'[^}]*\}", _styles_css())
    return "\n".join(face.replace("url('fonts/", f"url('{base}fonts/") for face in faces)


def _page(title: str, body: str, head_extra: str = "", scripts: str = "", font_base: str | None = None) -> str:
    style = PAGE_STYLE % {"tokens": _tokens()}
    if font_base is not None:
        style = _font_faces(font_base) + "\n" + style
    preload = ""
    if font_base is not None:
        preload = (f'<link rel="preload" href="{escape(font_base)}fonts/inter-var-latin-opsz-normal.woff2" as="font" '
                   f'type="font/woff2" crossorigin>\n')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>{escape(title)}</title>
{preload}{head_extra}<script>{THEME_SCRIPT}</script>
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
    """Chapters written (the book's config) against chapters planned (the manifest's
    `planned`): a bar of one segment per chapter and the counts in tabular figures."""
    chapters, sections, planned = entry.get("chapter-count"), entry.get("section-count"), entry.get("planned")
    if chapters is None:
        return ""
    parts = []
    if isinstance(planned, int) and planned >= chapters:
        parts.append(f"{chapters}/{planned} chapters")
    else:
        parts.append(f"{chapters} chapter{'s' if chapters != 1 else ''}")
    if sections:
        parts.append(f"{sections} sections")
    bar = ""
    if isinstance(planned, int) and 0 < planned <= 40 and planned >= chapters:
        marks = "".join('<i class="done"></i>' if i < chapters else "<i></i>" for i in range(planned))
        bar = f'<span class="segments" aria-hidden="true">{marks}</span>'
    return f'<div class="meter-row">{bar}<span class="tnum">{" · ".join(parts)}</span></div>'


def book_card(entry: dict, text: Text) -> str:
    prefix = escape(entry["prefix"])
    short = escape(entry.get("short") or entry["prefix"].upper())
    href = escape(entry["subdir"]) + "/"
    title_id = f"title-{prefix}"
    plain = escape(entry.get("title-plain") or plain_text(entry["title"]))
    lines = [f'<article class="card" id="book-{prefix}" aria-labelledby="{title_id}" data-book="{prefix}">',
             f'<div class="card-top"><span class="card-code">{short}</span>'
             f'<span class="card-series">{escape(entry.get("series") or "")}</span>{ARROW_UP}</div>',
             f'<h3 id="{title_id}"><a class="card-link" href="{href}">{text.title(entry["title"])}</a></h3>']
    if entry.get("blurb"):
        lines.append(f'<p class="card-blurb">{text.html(entry["blurb"])}</p>')
        lines.append('<button type="button" class="card-more" aria-expanded="false" hidden>More</button>')
    meta = progress(entry)
    if entry.get("section-count"):
        # filled in from this browser's record of sections marked done (one line, reserved)
        meta += (f'<div class="mine" data-book-key="{plain}" data-prefix="{prefix}" '
                 f'data-sections="{entry["section-count"]}">Not started in this browser</div>')
    if meta:
        lines.append(f'<div class="card-meta">{meta}</div>')
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
    lines = [f'<article class="card" aria-labelledby="{title_id}">',
             f'<div class="card-top"><span class="card-code">{escape(link.get("label") or "Link")}</span>{ARROW_UP}</div>',
             f'<h3 id="{title_id}"><a class="card-link" href="{href}">{text.title(link.get("title", ""))}</a></h3>']
    if link.get("blurb"):
        lines.append(f'<p class="card-blurb">{text.html(link["blurb"])}</p>')
    lines.append(f'<p class="card-links"><a href="{href}">{escape(link.get("action") or "Open")}</a></p>')
    lines.append("</article>")
    return "\n".join(lines)


# =============================================================================
# Reading-order diagram
# =============================================================================

NODE_W, NODE_H = 124, 58


def _diagram_svg(diagram: dict, manifest: dict, key: str, css_class: str, caption_id: str) -> str:
    """One layout of the map (`key` is "at" or "at-narrow") as inline SVG. A volume that
    is in the library is a link to it; arrows run between the cards' edges."""
    nodes = [n for n in diagram.get("nodes") or [] if isinstance(n.get(key) or n.get("at"), list)]
    if not nodes:
        return ""
    gap_x, gap_y, pad = (48, 40, 8) if key == "at" else (22, 34, 8)
    by_prefix = {e["prefix"]: e for e in manifest["books"]}
    place = {}
    for node in nodes:
        col, row = (node.get(key) or node["at"])[:2]
        place[node["id"]] = (pad + col * (NODE_W + gap_x) + NODE_W / 2, pad + row * (NODE_H + gap_y) + NODE_H / 2)
    width = max(x for x, _ in place.values()) + NODE_W / 2 + pad
    height = max(y for _, y in place.values()) + NODE_H / 2 + pad
    marker = f"arrow-{css_class}"
    parts = [f'<svg class="{css_class}" viewBox="0 0 {width:g} {height:g}" style="max-width:{width * 1.2:g}px" '
             f'role="group" aria-labelledby="{caption_id}" xmlns="http://www.w3.org/2000/svg">',
             f'<defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
             f'orient="auto-start-reverse"><path class="arrowhead" d="M0,1 L9,5 L0,9 z"/></marker></defs>']
    for edge in diagram.get("edges") or []:
        if isinstance(edge, list):
            edge = {"from": edge[0], "to": edge[1]}
        if edge["from"] not in place or edge["to"] not in place:
            continue
        (x1, y1), (x2, y2) = place[edge["from"]], place[edge["to"]]
        dx, dy = x2 - x1, y2 - y1

        def clip():    # where the line between the centres leaves a card, plus a little air
            tx = (NODE_W / 2 + 4) / abs(dx) if dx else float("inf")
            ty = (NODE_H / 2 + 4) / abs(dy) if dy else float("inf")
            return min(tx, ty)
        t = clip()
        a = (x1 + dx * t, y1 + dy * t)
        b = (x1 + dx * (1 - t), y1 + dy * (1 - t))
        kind = " optional" if edge.get("kind") == "optional" else ""
        parts.append(f'<line class="edge{kind}" data-from="{escape(edge["from"])}" data-to="{escape(edge["to"])}" '
                     f'x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" marker-end="url(#{marker})"/>')
    for node in nodes:
        x, y = place[node["id"]]
        entry = by_prefix.get(node.get("book") or "")
        kind = "planned" if node.get("planned") else ("book" if entry else "nobook")
        name = node.get("name") or ""
        if node.get("planned"):
            name = f"{name} (planned)" if name else "planned"
        label = node.get("code") or (entry.get("short") if entry else None) or node["id"]
        shape = (f'<rect x="{x - NODE_W / 2:g}" y="{y - NODE_H / 2:g}" width="{NODE_W}" height="{NODE_H}" rx="9"/>'
                 f'<text class="code" x="{x - NODE_W / 2 + 12:g}" y="{y - 4:g}">{escape(label)}</text>'
                 f'<text class="name" x="{x - NODE_W / 2 + 12:g}" y="{y + 14:g}">{escape(name)}</text>'
                 f'<text class="mine" x="{x + NODE_W / 2 - 10:g}" y="{y - 4:g}" text-anchor="end"></text>')
        if entry:
            title = escape(entry.get("title-plain") or plain_text(entry.get("title") or name))
            parts.append(f'<a class="node {kind}" data-id="{escape(node["id"])}" data-book="{escape(entry["prefix"])}" '
                         f'href="{escape(entry["subdir"])}/" aria-label="{escape(label)}: {title}">{shape}</a>')
        else:
            parts.append(f'<g class="node {kind}" data-id="{escape(node["id"])}">{shape}</g>')
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
    return (f'<section class="band" id="reading-order" aria-labelledby="reading-order-title">\n<div class="wrap">'
            f'<div class="band-head"><div><span class="eyebrow">Map</span><h2 id="reading-order-title">{escape(title)}</h2></div>'
            + (f"<p>{text.html(diagram['intro'])}</p>" if diagram.get("intro") else "")
            + f'</div>\n<figure class="order">{wide}{narrow}'
            f'<details><summary>How the volumes connect</summary><p id="{caption_id}">{text.html(caption)}</p></details>'
            f'</figure>\n</div></section>')


# =============================================================================
# The page
# =============================================================================

def hero_stats(manifest: dict) -> str:
    """The library in four numbers (tabular figures, so they line up as they change)."""
    books = manifest["books"]
    written = sum(e.get("chapter-count") or 0 for e in books)
    planned = sum(max(e.get("planned") or 0, e.get("chapter-count") or 0) for e in books)
    sections = sum(e.get("section-count") or 0 for e in books)
    series = len({e.get("series") or "" for e in books})
    stats = [("Volumes", f"{len(books)}", f"in {series} series"),
             ("Chapters written", f"{written}", f"of {planned} planned" if planned > written else ""),
             ("Sections", f"{sections}", "each with exercises")]
    rows = "".join(f'<div class="stat"><dt>{escape(k)}</dt><dd><span class="stat-num">{escape(v)}</span>'
                   f'{f"<span class=stat-note>{escape(n)}</span>" if n else ""}</dd></div>' for k, v, n in stats)
    bar = ""
    if planned:
        bar = (f'<div class="stat-bar" role="img" aria-label="{written} of {planned} chapters written">'
               f'<span style="--w:{written / planned:.3f}"></span></div>')
    return f'<aside class="hero-stats" aria-label="The library in numbers"><dl>{rows}</dl>{bar}</aside>'


def landing_page(manifest: dict, math: bool = False, font_base: str | None = None,
                 math_css: str | None = None) -> str:
    """index.html at the library root: a product-style front page. Titles are text;
    `tagline`, `usage`, `status`, blurbs, `licence` and `footer` may hold HTML. With
    `math`, TeX is left in for render_landing_math; without, it is plain text."""
    landing = manifest["landing"]
    text = Text(manifest.get("macros"), math)
    title = landing.get("title") or "Library"
    tagline = landing.get("tagline") or landing.get("intro") or ""
    status = landing.get("status") or landing.get("badge") or ""
    toggle = (f'<button class="theme-toggle" type="button" hidden aria-pressed="false" '
              f'aria-label="Switch to dark mode">{MOON}{SUN}</button>')
    source = (landing.get("sources") or [{}])[0].get("href")
    nav = ['<a href="#reading-order">Reading order</a>', '<a href="#volumes">Volumes</a>']
    if source:
        nav.append(f'<a href="{escape(source)}">Source</a>')
    parts = ['<a class="skip-link" href="#volumes">Skip to the volumes</a>',
             f'<header class="top"><div class="wrap"><a class="brand" href="./">{MARK}<span>{escape(title)}</span></a>'
             f'<nav class="top-nav" aria-label="Page">{"".join(nav)}</nav>{toggle}</div></header>',
             '<main>', '<section class="hero"><div class="wrap"><div class="hero-text">']
    hero = []
    if status:
        hero.append(f'<p class="status">{text.html(status)}</p>')
    hero.append(f"<h1>{escape(title)}</h1>")
    if tagline:
        hero.append(f'<p class="tagline">{text.html(tagline)}</p>')
    if landing.get("usage"):
        hero.append(f'<p class="usage">{text.html(landing["usage"])}</p>')
    first = next((e for e in manifest["books"] if e.get("section-count")), manifest["books"][0])
    first_title = escape(first.get("title-plain") or plain_text(first.get("title", "")))
    hero.append('<div class="actions">'
                f'<a class="btn primary" href="{escape(first["subdir"])}/"><span class="code">'
                f'{escape(first.get("short") or first["prefix"].upper())}</span>Start with {first_title}{ARROW}</a>'
                '<a class="btn" href="#reading-order">See the reading order</a></div>')
    parts.extend(hero)
    parts.append('</div>')
    parts.append(hero_stats(manifest))
    parts.append('</div></section>')
    parts.append(diagram_section(manifest, text))
    parts.append('<section class="band" id="volumes" aria-labelledby="volumes-title"><div class="wrap">'
                 '<div class="band-head"><div><span class="eyebrow">Library</span>'
                 '<h2 id="volumes-title">Volumes</h2></div>'
                 '<p>Each volume is a book of its own, with its own contents, search and exercises.</p></div>')
    index = 0
    run = []      # a run of one-card series sits side by side, so a lone card does not
                  # leave a row two-thirds empty

    def flush():
        if len(run) > 1:
            parts.append('<div class="series-row">' + "".join(run) + "</div>")
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
        items = []
        for card in cards:
            items.append(f'<li style="--i:{index}">{card}</li>')
            index += 1
        section = (f'<section class="series" aria-labelledby="{heading_id}">'
                   f'<div class="series-head"><h3 id="{heading_id}">{escape(group["title"] or "Books")}</h3>'
                   + (f"<p>{text.html(blurb)}</p>" if blurb else "") + "</div>"
                   + '<ul class="cards">' + "".join(items) + "</ul></section>")
        if len(items) == 1:
            run.append(section)
        else:
            flush()
            parts.append(section)
    flush()
    parts.append('</div></section>')
    parts.append("</main>")
    footer = []
    if landing.get("licence"):
        footer.append(f"<p>{landing['licence']}</p>")
    if landing.get("sources"):
        links = " ".join(f'<a href="{escape(s.get("href", ""))}">{escape(s.get("title", ""))}</a>'
                         for s in landing["sources"])
        footer.append(f'<p class="sources"><span>{escape(landing.get("sources-label") or "Source")}:</span> {links}</p>')
    if landing.get("footer"):
        footer.append(f"<p>{landing['footer']}</p>")
    if footer:
        parts.append('<footer class="site-footer"><div class="wrap">' + "\n".join(footer) + "</div></footer>")
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
