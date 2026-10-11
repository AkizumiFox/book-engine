"""
Build System Extra Pages
========================
Pages generated from the label registry rather than written by the author:

- results.html: every definition, theorem, example, ... grouped by chapter and section,
  with filters and hover previews.
- graph.html: the dependency graph of the chapters (templates/html/graph.js), built
  from the same hard/soft citation data as the reading paths, with a picker that
  shows the closure of any one section.
- paths.html and path-<slug>.html: the reader profiles declared in the config under
  `reading-paths`, each with the sections it needs, in reading order.

They use the book's HTML template, so they have the same sidebar, toolbar and theme.

Every generated path is checked before it is written: a path whose sections do not
carry all their own prerequisites sends a reader into a gap, so an unclosed path
fails the build rather than shipping.
"""

import importlib.util
import json
import re
from html import escape
from pathlib import Path

from .book import Book, Page, ENGINE_ROOT
from .manifest import load_scan, STATEMENT_TYPES
from .pandoc import build_pandoc_command, page_metadata, run_pandoc
from .utils import print_success, print_error, print_warning

RESULTS_PAGE = "results.html"
GRAPH_PAGE = "graph.html"
PATHS_PAGE = "paths.html"


def path_page(slug: str) -> str:
    return f"path-{slug}.html"


_reading_path_module = None


def reading_path():
    """`tools/reading_path.py`, the section-level dependency graph, imported by path.

    It is a standalone script (the author runs it on the command line) and `tools/`
    is not a package, so the build loads it the same way the script itself loads
    `check_forward_deps`. Loaded once: it costs a file read and a compile.
    """
    global _reading_path_module
    if _reading_path_module is None:
        spec = importlib.util.spec_from_file_location(
            "reading_path", ENGINE_ROOT / "tools" / "reading_path.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _reading_path_module = module
    return _reading_path_module

# Filter groups on the results page: (group, label, environment types)
RESULT_GROUPS = [
    ("statements", "Theorems and lemmas", STATEMENT_TYPES | {"conjecture"}),
    ("definitions", "Definitions", {"definition"}),
    ("examples", "Examples", {"example"}),
    ("exercises", "Exercises", {"exercise"}),
]


BLACKBOARD = {"R": "ℝ", "Q": "ℚ", "C": "ℂ", "Z": "ℤ", "N": "ℕ", "F": "𝔽"}
SYMBOLS = {"sqrt": "√", "cdot": "·", "times": "×", "to": "→", "leq": "≤", "geq": "≥", "neq": "≠",
           "in": "∈", "subseteq": "⊆", "oplus": "⊕", "cap": "∩", "cup": "∪", "infty": "∞"}


def plain_title(title: str) -> str:
    """A title for places that cannot typeset math (graph labels): TeX to readable text."""
    title = re.sub(r"\\n([A-Z])\b", lambda m: BLACKBOARD.get(m.group(1), m.group(1)), title)
    title = re.sub(r"\\[()\[\]]", "", title)
    title = re.sub(r"\\([A-Za-z]+)", lambda m: SYMBOLS.get(m.group(1), m.group(1)), title)
    title = title.replace("{", "").replace("}", "")
    return " ".join(title.split())


def _group_of(env_type: str) -> str:
    return next((group for group, _, types in RESULT_GROUPS if env_type in types), "other")


def _env_colors(book: Book) -> dict[str, str]:
    colors = {}
    for env in book.environment_settings.get("big_envs", []):
        key = env["name"].lower().replace(" ", "-")
        if env.get("color"):
            colors[key] = env["color"]
    return colors


def _results_by_page(book: Book, labels: dict) -> dict[str, list[tuple[str, dict]]]:
    """Labeled environments (not equations) per page, in reading order."""
    scan, _ = load_scan(book)
    grouped = {}
    for page in book.pages:
        entry = scan["files"].get(page.html_path)
        if not entry:
            continue
        # scan.json lists labels sorted by id; order them as they appear in the page text
        items = [(label, labels[label]) for label in entry["labels"]
                 if label in labels and labels[label].get("type") != "equation"]
        text = page.source.read_text(encoding="utf-8")
        items.sort(key=lambda item: text.find("#" + item[0]))
        if items:
            grouped[page.html_path] = items
    return grouped


def _results_body(book: Book, labels: dict) -> str:
    grouped = _results_by_page(book, labels)
    counts = {group: 0 for group, _, _ in RESULT_GROUPS}
    for items in grouped.values():
        for _, info in items:
            group = _group_of(info.get("type", ""))
            if group in counts:
                counts[group] += 1

    parts = ['<div class="results-filters" role="group" aria-label="Filter results">']
    for group, label, _ in RESULT_GROUPS:
        if counts[group]:
            parts.append(
                f'<label class="results-filter"><input type="checkbox" value="{group}" checked> '
                f'{escape(label)} <span class="results-count">{counts[group]}</span></label>')
    parts.append('<input type="search" class="results-search" placeholder="Filter by name or number" '
                 'aria-label="Filter results by name or number">')
    parts.append('</div>')

    for chapter in book.chapters:
        chapter_pages = [p for p in book.pages if p.chapter is chapter and p.html_path in grouped]
        if not chapter_pages:
            continue
        parts.append(f'<section class="results-chapter">')
        parts.append(f'<h2 id="chapter-{escape(chapter.slug)}">{escape(chapter.title)}</h2>')
        for page in chapter_pages:
            heading = f"{page.number} {page.title}" if page.number else page.title
            parts.append(f'<div class="results-section">')
            parts.append(f'<h3><a href="{escape(page.html_path)}">{escape(heading)}</a></h3>')
            parts.append('<ul class="results-list">')
            for label, info in grouped[page.html_path]:
                name = " ".join(filter(None, [info.get("type_name"), info.get("number")]))
                title = info.get("title_html") or ""
                search_text = f"{name} {info.get('title', '')}".lower()
                parts.append(
                    f'<li class="result" data-group="{_group_of(info.get("type", ""))}" '
                    f'data-search="{escape(search_text)}" style="--env-color: {_env_colors(book).get(info.get("type"), "var(--muted)")}">'
                    f'<a class="xref result-name" href="{escape(info["file"])}#{escape(label)}" '
                    f'data-ref="{escape(label)}" data-shard="{escape(info.get("shard", ""))}">{escape(name)}</a>'
                    + (f' <span class="result-title">{title}</span>' if title else "")
                    + '</li>')
            parts.append('</ul></div>')
        parts.append('</section>')
    parts.append('<p class="results-empty" hidden>No results match the filter.</p>')
    return "\n".join(parts)


# =============================================================================
# Reading paths
# =============================================================================

class BookGraph:
    """The book's section graph, twice: once for reading, once with the exercises.

    `tools/reading_path.py` decides what a prerequisite is. A citation made by a
    proof, a proof idea or a claim is hard: remove the cited result and the citing
    one is no longer proved. A citation made by a statement, a remark or a warning
    is soft. The one case that is both is the solution -- a solution is the proof of
    its exercise, and solutions make half of the book's citations -- so the reader
    gets both answers: `reading` counts proofs only, `with_exercises` counts
    solutions too, and every page prints the difference.
    """

    def __init__(self, book: Book, labels: dict):
        self.rp = reading_path()
        self.pages: dict[str, Page] = {}
        titles = {}
        for page in book.pages:
            sid = self.rp.section_of(page.html_path)
            if sid:
                self.pages[sid] = page
                titles[sid] = f"{page.number} {page.title}".strip()
        self.reading = self.rp.graph_from_labels(labels, titles, self.rp.HARD_KINDS)
        self.with_exercises = self.rp.graph_from_labels(labels, titles, self.rp.EXERCISE_KINDS)
        self.chapters = {chapter.slug: chapter for chapter in book.chapters}
        self.position = {slug: index for index, slug in enumerate(self.chapters)}
        self.sizes = {slug: 0 for slug in self.chapters}
        for sid in self.reading.sections:
            slug = sid.split("/")[0]
            if slug in self.sizes:
                self.sizes[slug] += 1

    @property
    def total(self) -> int:
        return len(self.reading.sections)

    def chapter_of(self, sid: str):
        return self.chapters.get(sid.split("/")[0])

    def url(self, sid: str) -> str:
        page = self.pages.get(sid)
        return page.html_path if page else ""

    def number(self, sid: str) -> str:
        page = self.pages.get(sid)
        return page.number if page else ""

    def title(self, sid: str) -> str:
        page = self.pages.get(sid)
        return page.title if page else sid

    def label(self, sid: str) -> str:
        return " ".join(filter(None, [self.number(sid), self.title(sid)]))

    def by_chapter(self, sids) -> dict[str, int]:
        """How many of these sections each chapter holds, keyed by the chapter's position.

        The position rather than the slug: graph.json carries 236 of these and the slugs
        would triple the file for no reader.
        """
        counts: dict[str, int] = {}
        for sid in sids:
            key = str(self.position.get(sid.split("/")[0], -1))
            counts[key] = counts.get(key, 0) + 1
        return counts


class ReadingPath:
    """One profile's two closures, with the checks that say they are usable."""

    def __init__(self, graph: BookGraph, profile: dict):
        self.graph = graph
        self.slug = profile.get("slug", "")
        self.name = profile.get("name", self.slug)
        self.description = profile.get("description", "")
        self.targets = list(profile.get("targets") or [])
        self.reading = graph.reading.closure(self.targets)
        self.with_exercises = graph.with_exercises.closure(self.targets)
        self.extra = set(self.with_exercises.sections) - set(self.reading.sections)
        self.weakest = dict(graph.reading.weakest_links(self.reading, limit=2))

    @property
    def page(self) -> str:
        return path_page(self.slug)

    def check(self) -> list[str]:
        """Why this path is not usable, if it is not. Empty means it is."""
        problems = []
        for name, graph, closure in (("reading path", self.graph.reading, self.reading),
                                     ("with-exercises path", self.graph.with_exercises,
                                      self.with_exercises)):
            closed = graph.is_closed(closure)
            if not closed:
                problems.append(f"{self.slug}: the {name} is not closed\n{closed.report()}")
        return problems


def _profiles(book: Book) -> list[dict]:
    return list(book.config.get("reading-paths") or [])


def _reading_paths(book: Book, graph: BookGraph) -> list[ReadingPath]:
    paths = []
    for profile in _profiles(book):
        try:
            paths.append(ReadingPath(graph, profile))
        except KeyError as exc:
            print_error(f"Reading path {profile.get('slug', '?')}: {exc.args[0]}")
    return paths


def _count_phrase(count: int, total: int) -> str:
    return f"{count} of the book's {total} sections"


def _paths_body(book: Book, graph: BookGraph, paths: list[ReadingPath]) -> str:
    parts = [
        '<p class="paths-lede">Every result in this book is proved from results that came '
        'earlier, and the build records which. Following those records backwards from a '
        'theorem gives the sections a reader actually needs in order to reach it, and nothing '
        'else. The paths below are computed that way, from the proofs themselves, each time '
        'the book is built.</p>',
        '<p>A path is aimed at a handful of sections, listed on its own page. It contains '
        'every section those proofs rest on, and it is <strong>closed</strong>: nothing on it '
        'cites anything off it in a proof. Read it in order and no step is missing.</p>',
        '<p>Each path comes in two lengths. The <strong>reading</strong> column counts what '
        'the proofs need. The <strong>with exercises</strong> column also counts what the '
        'written solutions need, since a solution is the proof of its exercise; it is the '
        'longer figure, and the difference is the price of working the problems rather than '
        'reading past them.</p>',
        '<table class="paths-table">',
        '<thead><tr><th scope="col">Reading path</th>'
        '<th scope="col" class="paths-number">Reading</th>'
        '<th scope="col" class="paths-number">With exercises</th></tr></thead><tbody>',
    ]
    for path in paths:
        added = len(path.with_exercises) - len(path.reading)
        parts.append(
            f'<tr><td><a class="paths-name" href="{escape(path.page)}">{escape(path.name)}</a>'
            f'<span class="paths-description">{escape(path.description)}</span></td>'
            f'<td class="paths-number">{len(path.reading)}</td>'
            f'<td class="paths-number">{len(path.with_exercises)}'
            f'<span class="paths-delta">+{added}</span></td></tr>')
    parts.append('</tbody></table>')
    parts.append(
        f'<p class="paths-foot">Out of {graph.total} sections that carry a result. '
        'None of these lists is a syllabus: it is the smallest set that leaves no proof '
        'unfinished. To aim at something else, see the '
        f'<a href="{escape(GRAPH_PAGE)}">dependency graph</a>, which will compute the same '
        'closure for any single section.</p>')
    return "\n".join(parts)


def _path_body(book: Book, graph: BookGraph, path: ReadingPath) -> str:
    total = graph.total
    added = len(path.with_exercises) - len(path.reading)
    targets = set(path.reading.targets)
    shown = graph.reading.order(set(path.reading.sections) | path.extra)

    parts = [f'<p class="paths-lede">{escape(path.description)}</p>']
    parts.append('<p class="path-targets">It aims at ' + ", ".join(
        f'<a href="{escape(graph.url(sid))}">{escape(graph.label(sid))}</a>'
        for sid in graph.reading.order(targets)) + '.</p>')
    parts.append(
        '<div class="path-counts">'
        f'<p><strong class="path-figure">{len(path.reading)}</strong> sections to read, '
        f'of {total}. That is everything the proofs of those sections rest on, and nothing '
        'else.</p>'
        f'<p><strong class="path-figure">{len(path.with_exercises)}</strong> if you also work '
        f'the exercises, since a written solution is the proof of its exercise: '
        f'<strong>{added} more</strong> section{"" if added == 1 else "s"}.</p>'
        '</div>')

    parts.append('<h2 id="what-to-read">What to read</h2>')
    parts.append(
        '<p class="path-key">In reading order. <strong>Bold</strong> marks a section the path '
        'is aimed at; <span class="path-extra-mark">+</span> marks one that only the exercises '
        'need. The note beside a section says when the whole path hangs on a single proof '
        'citing it.</p>')
    for chapter in book.chapters:
        here = [sid for sid in shown if sid.split("/")[0] == chapter.slug]
        if not here:
            continue
        size = graph.sizes.get(chapter.slug, 0)
        parts.append('<section class="path-chapter">')
        parts.append(
            f'<h3 id="path-{escape(chapter.slug)}">{escape(chapter.title)}'
            f'<span class="path-chapter-count">{len(here)} of {size}</span></h3>')
        parts.append('<ul class="path-list">')
        for sid in here:
            classes = ["path-section"]
            if sid in targets:
                classes.append("is-target")
            if sid in path.extra:
                classes.append("is-extra")
            note = ""
            cites = path.weakest.get(sid)
            if cites and sid not in targets and sid not in path.extra:
                sites = "; ".join(f"{c.citing} ({'/'.join(c.kinds)}) cites {c.cited}"
                                  for c in cites)
                word = "proof" if len(cites) == 1 else "proofs"
                note = (f'<span class="path-weak" title="{escape(sites, quote=True)}">'
                        f'{len(cites)} {word}</span>')
            mark = ('<span class="path-extra-mark" '
                    'title="needed only if you work the exercises">+</span>'
                    if sid in path.extra else "")
            parts.append(
                f'<li class="{" ".join(classes)}">{mark}'
                f'<a href="{escape(graph.url(sid))}">'
                f'<span class="path-number">{escape(graph.number(sid))}</span> '
                f'{escape(graph.title(sid))}</a>{note}</li>')
        parts.append('</ul></section>')

    # A chapter with no result of its own (the notation appendix) is not something a
    # reader can be told to skip, so it is left out of both counts.
    skipped = [chapter for chapter in book.chapters
               if graph.sizes.get(chapter.slug)
               and not any(sid.split("/")[0] == chapter.slug for sid in shown)]
    parts.append('<h2 id="what-to-skip">What you can skip</h2>')
    off = total - len(path.reading)
    parts.append(
        f'<p>{_count_phrase(off, total)} are not on this path, and skipping them costs you '
        'no proof you need.</p>')
    if skipped:
        parts.append('<p>Not needed at all: ' + ", ".join(
            f'<a href="{escape(_chapter_url(book, chapter))}">{escape(chapter.title)}</a>'
            for chapter in skipped) + '.</p>')
    context = graph.reading.soft_context(path.reading)
    context = [(sid, cites) for sid, cites in context if sid not in path.extra]
    if context:
        listed = context[:10]
        names = ", ".join(f'<a href="{escape(graph.url(sid))}">{escape(graph.label(sid))}</a>'
                          for sid, _ in listed)
        more = f", and {len(context) - len(listed)} more" if len(context) > len(listed) else ""
        parts.append(
            f'<p class="path-context">Cited in passing by sections on the path &#8212; in a '
            f'statement, a remark or an example, never in a proof &#8212; so they are context and '
            f'not prerequisites: {names}{more}.</p>')
    parts.append(
        '<p class="paths-foot">Computed from the book\'s proofs when the book was built, and '
        'checked: every result a proof on this path uses is proved by another section on this '
        f'path. The other paths are listed on the <a href="{escape(PATHS_PAGE)}">reading '
        f'paths</a> page.</p>')
    return "\n".join(parts)


def _chapter_url(book: Book, chapter) -> str:
    page = next((p for p in book.pages if p.chapter is chapter and p.section == 0), None)
    if page is None:
        page = next((p for p in book.pages if p.chapter is chapter), None)
    return page.html_path if page else ""

def _graph_data(book: Book, graph: BookGraph, labels: dict,
                paths: list[ReadingPath]) -> dict:
    """Chapter-level dependencies, from the same citations the reading paths are built on.

    This page used to count `scan.json`'s per-page `refs`, which is every cross-reference
    on a page -- including the chapter introduction, whose "What you need" list exists in
    order to cite the rest of the book. That made almost every pair of chapters adjacent
    and the graph unreadably dense. Here an edge is a citation made by a labelled result,
    and its weight counts only the **hard** ones: a proof, a proof idea or a claim, the
    citations that cannot be dropped without leaving something unproved. Soft citations --
    a statement, a remark, an exercise, a solution -- are carried alongside and shown on
    hover, and a pair of chapters joined by nothing else is not part of the skeleton.

    The closures are what the reader picks from: for every section, how many sections of
    each chapter its reading path needs, and how many more the exercises add.
    """
    chapter_of = {p.html_path: p.chapter for p in book.pages if p.chapter}
    index_of = {c.slug: _chapter_url(book, c) for c in book.chapters}
    results: dict[str, int] = {c.slug: 0 for c in book.chapters}
    for label, info in labels.items():
        chapter = chapter_of.get(info.get("file"))
        if chapter is not None and info.get("type") != "equation":
            results[chapter.slug] = results.get(chapter.slug, 0) + 1

    order_of = {c.slug: position for position, c in enumerate(book.chapters)}
    counts: dict[tuple[str, str], list[int]] = {}
    for citation in graph.reading.citations:
        citing, cited = graph.chapter_of(citation.src), graph.chapter_of(citation.dst)
        if citing is None or cited is None or citing.slug == cited.slug:
            continue  # citations inside one chapter are not drawn
        if order_of[cited.slug] > order_of[citing.slug]:
            # A citation pointing *forward* -- "Chapter 43 does this properly" -- is a
            # signpost to the reader, not a dependency of the earlier chapter. Drawn, it
            # becomes an arrow from the later chapter into the earlier one, which in this
            # graph reads "the earlier chapter's results use the later one's": false, and
            # the opposite of what the sentence says. No proof, proof idea or claim may
            # point forward (`./build.py check` fails through `tools/check_forward_deps.py`),
            # so only soft edges are dropped and the hard skeleton does not move. The
            # reading paths are built from `graph.reading`, not from this.
            continue
        entry = counts.setdefault((cited.slug, citing.slug), [0, 0])
        entry[0 if citation.hard else 1] += 1

    nodes = [{
        "id": chapter.slug,
        "name": f"Chapter {chapter.number}",
        "title": chapter.title,
        "url": index_of.get(chapter.slug, ""),
        "results": results.get(chapter.slug, 0),
        "sections": graph.sizes.get(chapter.slug, 0),
        "chapterNumber": chapter.number,
        "part": chapter.part,
    } for chapter in book.chapters]
    hard_edges = {key: pair[0] for key, pair in counts.items() if pair[0]}
    implied = _implied_edges(hard_edges)
    edges = [{"source": source, "target": target, "weight": hard, "soft": soft,
              "implied": hard == 0 or (source, target) in implied,
              "softOnly": hard == 0}
             for (source, target), (hard, soft) in sorted(counts.items())]
    return {"nodes": nodes, "edges": edges, "total": graph.total,
            "profiles": [_closure_data(graph, path.name, path.reading.sections,
                                       path.with_exercises.sections,
                                       url=path.page, slug=path.slug)
                         for path in paths],
            "closures": {sid: _closure_data(
                graph, graph.label(sid),
                graph.reading.closure([sid]).sections,
                graph.with_exercises.closure([sid]).sections,
                url=graph.url(sid), chapter=sid.split("/")[0])
                for sid in graph.reading.order(graph.reading.sections)}}


def _closure_data(graph: BookGraph, name: str, reading, with_exercises, **extra) -> dict:
    """One closure, small enough to ship 236 of them: per-chapter counts, not section lists."""
    reading = list(reading)
    added = set(with_exercises) - set(reading)
    return {"name": name, "n": len(reading), "nx": len(reading) + len(added),
            "chapters": graph.by_chapter(reading), "extra": graph.by_chapter(added), **extra}


def _implied_edges(counts: dict[tuple[str, str], int]) -> set[tuple[str, str]]:
    """The edges a transitive reduction drops: those a longer path already implies.

    An edge u -> v is implied when u has another direct successor w that reaches v, so
    drawing u -> v tells the reader nothing that u -> w -> ... -> v does not. On a directed
    acyclic graph the reduction is unique, so there is nothing to choose. A cycle would make
    it ambiguous; chapters may not cite each other in a circle, and if they ever do we draw
    every edge rather than pick a spanning shape at random.
    """
    successors: dict[str, set[str]] = {}
    for source, target in counts:
        successors.setdefault(source, set()).add(target)
        successors.setdefault(target, set())
    reach: dict[str, set[str]] = {}
    visiting: set[str] = set()
    cyclic = False

    def reachable(node: str) -> set[str]:
        nonlocal cyclic
        if node in reach:
            return reach[node]
        if node in visiting:
            cyclic = True
            return set()
        visiting.add(node)
        seen: set[str] = set()
        for nxt in successors[node]:
            seen.add(nxt)
            seen |= reachable(nxt)
        visiting.discard(node)
        reach[node] = seen
        return seen

    for node in successors:
        reachable(node)
    if cyclic:
        print_warning("chapters cite each other in a circle; drawing every dependency")
        return set()
    return {(source, target) for source, target in counts
            if any(other != target and target in reach[other] for other in successors[source])}


GRAPH_BODY = """<p class="graph-intro">
Each box is a chapter. An arrow from one chapter to another means a proof in the second
uses a result from the first; the thicker the arrow, the more proofs. Only citations made
inside a result count, so the chapter introductions, whose job is to cite the rest of the
book, do not crowd the picture. A dependency that a longer chain already implies is not
drawn, and neither is one made only in passing &#8212; a remark, an example, an exercise &#8212; nor
one that points forward in the book, which is a signpost and not something the earlier
chapter rests on. So what you see is the skeleton. Hover over a chapter to bring both back, as dashed arrows
and as counts beside the graph; click to open it.
</p>
<p class="graph-intro">
The graph is the overview. What a reader acts on is one section: choose it below and the
chapters it needs light up, with the number of sections needed from each. For the paths
this book declares, worked out section by section, see the <a href="paths.html">reading
paths</a>; for the results themselves, the <a href="results.html">list of results</a>.
</p>
<div class="graph-controls">
  <label>Show what you need for
    <select id="graph-target" disabled>
      <option value="">the whole book (overview)</option>
    </select>
  </label>
  <label class="graph-toggle"><input type="checkbox" id="graph-exercises"> count the exercises</label>
</div>
<div class="graph-frame">
  <div id="dependency-graph" class="dependency-graph" data-graph="graph.json" role="img"
       aria-label="Dependency graph of the book's chapters"></div>
  <aside class="graph-preview" hidden></aside>
</div>
<p class="graph-closure" hidden></p>
<noscript><p>The graph needs JavaScript. The <a href="paths.html">reading paths</a> and the
<a href="results.html">list of results</a> work without it.</p></noscript>
"""


def _render_page(book: Book, html_path: str, title: str, body_html: str, extra: dict) -> bool:
    source = book.build_dir / "tmp" / "generated" / Path(html_path).with_suffix(".md")
    source.parent.mkdir(parents=True, exist_ok=True)
    # A raw HTML block, so Pandoc passes the markup through unchanged
    # (the title gets its own id, which would otherwise collide with ids in the body)
    source.write_text(f"# {title} {{#page-title}}\n\n```{{=html}}\n{body_html}\n```\n", encoding="utf-8")
    page = Page(source=source, chapter=None, section=0, title=title, html_path=html_path)
    metadata = page_metadata(book, page, "html", extra)
    metadata["breadcrumb-chapter-title"] = book.title
    output = book.html_dir / html_path
    return run_pandoc(build_pandoc_command(book, page, output, "html", metadata))


def generate_extra_pages(book: Book, extra: dict) -> bool:
    """Write results.html, graph.html, graph.json and the reading-path pages.

    `extra` is shared page metadata. A reading path that is not closed is a reader
    sent into a gap, so it fails the build instead of being published.
    """
    _, labels = load_scan(book)
    ok = _render_page(book, RESULTS_PAGE, "List of results", _results_body(book, labels), extra)

    graph = BookGraph(book, labels)
    paths = _reading_paths(book, graph)
    if len(paths) != len(_profiles(book)):
        ok = False
    problems = [problem for path in paths for problem in path.check()]
    for problem in problems:
        print_error(problem)
    if problems:
        return False
    for path in paths:
        ok = _render_page(book, path.page, path.name, _path_body(book, graph, path), extra) and ok
    ok = _render_page(book, PATHS_PAGE, "Reading paths",
                      _paths_body(book, graph, paths), extra) and ok

    (book.html_dir / "graph.json").write_text(
        json.dumps(_graph_data(book, graph, labels, paths), separators=(",", ":")),
        encoding="utf-8")
    ok = _render_page(book, GRAPH_PAGE, "Dependency graph", GRAPH_BODY,
                      dict(extra, **{"page-scripts": ["graph.js"], "wide-page": True})) and ok
    if ok:
        print_success(f"Generated pages: list of results, dependency graph, "
                      f"{len(paths)} reading paths (all closed)")
    else:
        print_error("Could not generate the list of results, the dependency graph "
                    "or the reading paths")
    return ok


def extra_page_names(book: Book) -> list[str]:
    """Every page this module generates, for the sitemap and the math renderer."""
    return ([RESULTS_PAGE, GRAPH_PAGE, PATHS_PAGE]
            + [path_page(profile["slug"]) for profile in _profiles(book) if profile.get("slug")])
