#!/usr/bin/env python3
"""Which sections must a reader actually read to reach a given section?

Reads `_build/crossref_labels.json`, which the HTML build writes. Every label
carries the `file` it lives in, a `uses` list of the labels it cites, and
`uses_kinds`, which says for each cited label *which environment* cited it: the
owning result's own type for a citation in its statement, or `proof`, `idea`,
`remark`, `solution`, `check`, ... for a citation in a block that follows it.

That distinction is the whole point of this tool:

* a **hard** edge is a citation from a proof, a proof idea or a claim. Remove
  the cited result and the citing theorem is no longer proved.
* a **soft** edge is a citation from a statement, a remark, a warning, an
  exercise, a solution or a check. Remove the cited result and a sentence needs
  rewording, or an exercise loses its point, but nothing is left unproved.

The one case that is genuinely both is the solution: a solution is the proof of
its exercise, and solutions make half of the book's citations. So the policy is
a parameter, `hard_kinds`, and the book publishes both answers side by side --
a reading path (`HARD_KINDS`) and a path for a reader who also works the
exercises (`EXERCISE_KINDS`) -- rather than choosing for the reader.

One more thing can make an edge soft: the result that made it. A result marked
`::: {#thm-foo .optional}` is one no reader is obliged to read -- an illustration,
or a bridge to another part of the book. Nothing requires it, so nothing it cites
can be required through it, and **every** citation it makes is soft, whatever
block it was written in. Its own section still shows as context on the soft view.
That is only honest while nothing proves anything from an optional result, which
`tools/check_optional.py` enforces and `./build.py check` fails on.

The graph is built **section by section**, not chapter by chapter (chapter-level
closures are roughly twice the size) and not from `scan.json`'s per-page `refs`,
which is what the dependency-graph page uses today: `refs` counts every citation
on a page, including the chapter introduction and the "What you need" prose,
which makes almost everything depend on almost everything.

A path is *closed* when every hard dependency of every section in it is itself
in the path. An unclosed path is a reader hitting a gap, and is the one bug this
tool exists to prevent; `is_closed` checks it and `--verify` reports it.

Command line
------------

    python3 tools/reading_path.py ch12-psd-and-svd/08
    python3 tools/reading_path.py ch11-spectral-theory/04 ch12-psd-and-svd/08 --soft
    python3 tools/reading_path.py ch18-nonnegative/05 --json
    python3 tools/reading_path.py ch22-algebras/08 --weakest 3
    python3 tools/reading_path.py --list-profiles
    python3 tools/reading_path.py --profile statistics --with-exercises

A target is written `<chapter directory>/<section number>`, the way the file
names it: `ch12-psd-and-svd/08`, or `ch12-psd-and-svd/index` for a chapter's
index page. A profile is a named set of targets kept in `config/config.json`,
which is also what the generated reading-path pages are built from. Run
`./build.py html` first.

Importable
----------

    from tools.reading_path import load_graph
    graph = load_graph()
    path = graph.closure(["ch12-psd-and-svd/08"])
    assert not graph.is_closed(path).violations
"""
import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
# The book's files, relative to the current directory: run the tool from the book's root
# (the engine may live elsewhere, e.g. in the book's engine/ submodule).
INDEX = Path("_build") / "crossref_labels.json"
NAVIGATION = Path("_build") / "html" / "navigation.json"
CONFIG_CANDIDATES = (Path("config") / "config.json", Path("book.json"))


def default_config() -> Path:
    """The book's config in the current directory: config/config.json, else book.json."""
    return next((p for p in CONFIG_CANDIDATES if p.exists()), CONFIG_CANDIDATES[0])


def _load_forward_deps():
    """`from_file` places a file as (chapter, letter, section); don't reimplement it.

    It is the one place that knows a chapter directory may carry a letter
    (`ch23a-notation` sorts after every section of `ch23-applied`) and that an
    index page is section 0. Imported by path because `tools/` is not a package.
    """
    spec = importlib.util.spec_from_file_location(
        "check_forward_deps", TOOLS / "check_forward_deps.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


from_file = _load_forward_deps().from_file


# The environments whose citations leave a hole in a proof when the cited result
# goes away. `claim` and `proofofclaim` are here for completeness: in practice a
# claim sits inside the proof div, so its citations already arrive as "proof".
HARD_KINDS = frozenset({"proof", "proofofclaim", "claim", "idea"})

# The same, for a reader who also works the exercises. A solution *is* the proof of
# its exercise, and solutions make 5,778 of the book's 11,612 citations, so whether
# they count is the one question the reader has to answer for themselves. The two
# reading-path variants are the two answers; nothing here picks one.
EXERCISE_KINDS = HARD_KINDS | {"solution"}

# A citation whose kind is unknown (an index written before `uses_kinds` existed)
# is counted soft, and the count is reported rather than silently assumed.
UNKNOWN_KIND = "?"

SECTION = re.compile(r"^(ch\d+[a-z]*[^/]*)/(\d+|index)")


def section_of(path: str | None) -> str | None:
    """'ch12-psd-and-svd/08-singular-values.html' -> 'ch12-psd-and-svd/08'."""
    m = SECTION.match(path or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


@dataclass(frozen=True)
class Citation:
    """One citation, from the label that made it to the label it names."""
    src: str            # section id of the citing label
    dst: str            # section id of the cited label
    citing: str         # citing label
    cited: str          # cited label
    kinds: tuple        # the environments it was cited from, sorted
    hard: bool
    from_optional: bool = False   # the citing result is marked .optional, so never hard

    def site(self) -> str:
        optional = " [optional]" if self.from_optional else ""
        return f"{self.citing} ({'/'.join(self.kinds)}){optional} -> {self.cited}"


@dataclass
class Closure:
    """A reading path: the sections, in reading order, and how it was reached."""
    targets: list
    sections: list                       # section ids in reading order, targets included
    hard_only: bool
    reached_by: dict = field(default_factory=dict)   # section -> the citations that pulled it in

    def __len__(self):
        return len(self.sections)


@dataclass
class ClosureCheck:
    """The result of the closure property: empty `violations` means the path is closed."""
    violations: list                     # (section in path, missing dependency, [citations])

    def __bool__(self):
        return not self.violations

    def report(self) -> str:
        if not self.violations:
            return "closed"
        return "\n".join(
            f"  {src} needs {dst}, which is not in the path "
            f"({len(cites)} hard citation{'s' if len(cites) != 1 else ''}: "
            f"{', '.join(c.site() for c in cites[:3])})"
            for src, dst, cites in self.violations)


class SectionGraph:
    """Sections and the citations between them, split into hard and soft edges."""

    def __init__(self, citations, sections, titles=None, hard_kinds=HARD_KINDS,
                 optional=()):
        self.citations = list(citations)
        self.sections = dict(sections)               # section id -> sort key
        self.titles = dict(titles or {})
        self.hard_kinds = frozenset(hard_kinds)      # which policy built these edges
        self.optional = frozenset(optional)          # labels nothing is obliged to read
        self.unknown_kinds = sum(1 for c in self.citations if UNKNOWN_KIND in c.kinds)
        self.hard_out = defaultdict(list)
        self.soft_out = defaultdict(list)
        for c in self.citations:
            (self.hard_out if c.hard else self.soft_out)[c.src].append(c)

    # -- ordering ---------------------------------------------------------

    def key(self, sid):
        """Reading order. An unplaced section sorts last rather than raising."""
        return self.sections.get(sid) or (999, "", 999)

    def order(self, sids):
        return sorted(sids, key=lambda s: (self.key(s), s))

    def title(self, sid):
        return self.titles.get(sid, "")

    # -- closure ----------------------------------------------------------

    def out_edges(self, sid, hard_only=True):
        if hard_only:
            return self.hard_out.get(sid, [])
        return self.hard_out.get(sid, []) + self.soft_out.get(sid, [])

    def closure(self, targets, hard_only=True) -> Closure:
        """Every section reachable from `targets` by dependency edges, in reading order."""
        targets = [self.resolve(t) for t in targets]
        seen = set(targets)
        reached_by = defaultdict(list)
        queue = list(targets)
        while queue:
            sid = queue.pop()
            for c in self.out_edges(sid, hard_only):
                if c.dst == c.src:
                    continue
                reached_by[c.dst].append(c)
                if c.dst not in seen:
                    seen.add(c.dst)
                    queue.append(c.dst)
        return Closure(targets=targets, sections=self.order(seen), hard_only=hard_only,
                       reached_by={dst: self._sorted(cites)
                                   for dst, cites in reached_by.items()})

    def _sorted(self, cites):
        """A stable order for citations: by citing section, then by label."""
        return sorted(cites, key=lambda c: (self.key(c.src), c.src, c.citing, c.cited))

    def resolve(self, target):
        """Accept 'ch12-psd-and-svd/08', a file name, or an html path."""
        sid = section_of(target) or target
        if sid in self.sections:
            return sid
        # 'ch12-psd-and-svd/8' and 'ch12/08' are common slips; name the near misses.
        chapter, _, number = sid.partition("/")
        near = [s for s in self.sections if s.startswith(chapter.rstrip("/"))]
        if not near:
            near = [s for s in self.sections if s.split("/")[0].startswith(chapter.split("-")[0])]
        raise KeyError(f"no section {target!r}" +
                       (f"; did you mean one of {', '.join(sorted(near)[:6])}?" if near else ""))

    # -- the property that matters ---------------------------------------

    def is_closed(self, path, hard_only=True) -> ClosureCheck:
        """Is every dependency of every section in `path` also in `path`?"""
        inside = set(path.sections if isinstance(path, Closure) else path)
        hard_only = path.hard_only if isinstance(path, Closure) else hard_only
        missing = defaultdict(list)
        for sid in sorted(inside):
            for c in self.out_edges(sid, hard_only):
                if c.dst != c.src and c.dst not in inside:
                    missing[(sid, c.dst)].append(c)
        return ClosureCheck(violations=[(src, dst, cites)
                                        for (src, dst), cites in sorted(missing.items())])

    # -- review ------------------------------------------------------------

    def weakest_links(self, closure: Closure, limit=2):
        """Sections the path pulls in on only a citation or two, with the citing sites.

        These are the candidates for review: cut or reword that one citation and
        the section, and everything only it needed, leaves the path. Counted over
        hard citations from sections that are in the path, so the count is the
        work a reader would actually have to undo.
        """
        inside = set(closure.sections)
        targets = set(closure.targets)
        pulls = defaultdict(list)
        for sid in self.order(inside):
            for c in self.hard_out.get(sid, []):
                if c.dst != c.src and c.dst in inside and c.dst not in targets:
                    pulls[c.dst].append(c)
        weak = [(sid, self._sorted(cites)) for sid, cites in pulls.items() if len(cites) <= limit]
        return [(sid, cites) for sid, cites in
                sorted(weak, key=lambda item: (len(item[1]), self.key(item[0])))]

    def soft_context(self, closure: Closure):
        """Soft citations leaving the path: context a reader may want, not prerequisites."""
        inside = set(closure.sections)
        out = defaultdict(list)
        for sid in self.order(inside):
            for c in self.soft_out.get(sid, []):
                if c.dst != c.src and c.dst not in inside:
                    out[c.dst].append(c)
        return [(sid, self._sorted(out[sid])) for sid in self.order(out)]


# =============================================================================
# Loading
# =============================================================================

def graph_from_labels(labels: dict, titles=None, hard_kinds=HARD_KINDS) -> SectionGraph:
    """Build the section graph from a `crossref_labels` mapping.

    `hard_kinds` is the policy: which citing environments make an edge a
    prerequisite rather than context. Pass `EXERCISE_KINDS` for the reader who
    also works the exercises.
    """
    hard_kinds = frozenset(hard_kinds)
    # A result nothing is obliged to read cannot make anything else required: the
    # reader who skips it never follows its citations. So its edges are all soft.
    optional = {name for name, rec in labels.items() if rec.get("optional")}
    sections = {}
    where = {}
    for name, rec in labels.items():
        sid = section_of(rec.get("src") or rec.get("file"))
        if sid is None:
            continue
        where[name] = sid
        if sid not in sections:
            sections[sid] = from_file(rec.get("src") or rec.get("file"))

    citations = []
    for name, rec in sorted(labels.items()):
        src = where.get(name)
        if src is None:
            continue
        kinds_by_label = rec.get("uses_kinds") or {}
        for cited in rec.get("uses") or ():
            dst = where.get(cited)
            if dst is None or dst == src:
                continue
            kinds = tuple(kinds_by_label.get(cited) or (UNKNOWN_KIND,))
            from_optional = name in optional
            citations.append(Citation(src=src, dst=dst, citing=name, cited=cited,
                                      kinds=kinds,
                                      hard=(not from_optional
                                            and any(k in hard_kinds for k in kinds)),
                                      from_optional=from_optional))
    return SectionGraph(citations, sections, titles, hard_kinds, optional)


def load_titles(path=NAVIGATION) -> dict:
    """Section id -> section title, from the navigation manifest if it was built."""
    path = Path(path)
    if not path.exists():
        return {}
    nav = json.loads(path.read_text(encoding="utf-8"))
    titles = {}
    for chapter in nav.get("chapters", []):
        sid = section_of(chapter.get("src") or chapter.get("path"))
        if sid:
            titles[sid] = chapter.get("title", "")
        for section in chapter.get("sections", []):
            sid = section_of(section.get("src") or section.get("path"))
            if sid:
                number = section.get("number", "")
                titles[sid] = f"{number} {section.get('title', '')}".strip()
    return titles


def load_graph(index=INDEX, navigation=NAVIGATION, hard_kinds=HARD_KINDS) -> SectionGraph:
    index = Path(index)
    if not index.exists():
        raise FileNotFoundError(f"{index} not found; run ./build.py html first")
    labels = json.loads(index.read_text(encoding="utf-8"))["crossref_labels"]
    return graph_from_labels(labels, load_titles(navigation), hard_kinds)


def load_profiles(config=None) -> list:
    """The reader profiles, from `config/config.json`'s `reading-paths`.

    Each is `{"slug", "name", "description", "targets"}`. They live in the config
    so that the author can add one, or change where one aims, without touching
    code; the build reads the same list to generate the pages.
    """
    path = Path(config) if config is not None else default_config()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("reading-paths") or [])


# =============================================================================
# Command line
# =============================================================================

def _print_path(graph, closure, label):
    print(f"{label}: {len(closure)} sections")
    for sid in closure.sections:
        mark = "*" if sid in closure.targets else " "
        pulls = len(closure.reached_by.get(sid, ()))
        count = "" if sid in closure.targets else f"  [{pulls}]"
        print(f"  {mark} {sid:<34}{count:<7}{graph.title(sid)}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="The sections a reader needs in order to read the given ones.")
    parser.add_argument("targets", nargs="*", metavar="SECTION",
                        help="e.g. ch12-psd-and-svd/08")
    parser.add_argument("--profile", metavar="SLUG",
                        help="take the targets from a reader profile in config/config.json")
    parser.add_argument("--list-profiles", action="store_true",
                        help="print the reader profiles and their targets, then stop")
    parser.add_argument("--with-exercises", action="store_true",
                        help="count a solution as the proof of its exercise, so exercises "
                             "bring their prerequisites onto the path too")
    parser.add_argument("--soft", action="store_true",
                        help="also close over soft citations (statements, remarks, solutions)")
    parser.add_argument("--weakest", type=int, default=2, metavar="N",
                        help="report sections pulled in by at most N hard citations (default 2)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--verify", action="store_true",
                        help="only check that the path is closed; exit 1 if it is not")
    parser.add_argument("--index", default=INDEX, help="path to crossref_labels.json")
    parser.add_argument("--config", default=None,
                        help="path to the book's config (for --profile; default config/config.json or book.json)")
    args = parser.parse_args(argv)

    profiles = load_profiles(args.config)
    if args.list_profiles:
        for profile in profiles:
            print(f"{profile.get('slug', '?'):<20} {profile.get('name', '')}")
            print(f"  {'; '.join(profile.get('targets') or [])}")
        if not profiles:
            print("no reader profiles in the config", file=sys.stderr)
            return 1
        return 0

    targets = list(args.targets)
    if args.profile:
        chosen = next((p for p in profiles if p.get("slug") == args.profile), None)
        if chosen is None:
            print(f"no reader profile {args.profile!r}; try --list-profiles", file=sys.stderr)
            return 1
        targets += list(chosen.get("targets") or [])
    if not targets:
        parser.error("give at least one section, or --profile")

    kinds = EXERCISE_KINDS if args.with_exercises else HARD_KINDS
    try:
        graph = load_graph(args.index, hard_kinds=kinds)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    try:
        hard = graph.closure(targets, hard_only=True)
        full = graph.closure(targets, hard_only=False)
    except KeyError as exc:
        print(exc.args[0], file=sys.stderr)
        return 1

    check = graph.is_closed(hard)
    check_full = graph.is_closed(full)

    if args.verify:
        ok = bool(check) and bool(check_full)
        print("closed" if ok else "NOT CLOSED:\n" + check.report() + "\n" + check_full.report())
        return 0 if ok else 1

    weak = graph.weakest_links(hard, limit=args.weakest)

    if args.json:
        print(json.dumps({
            "targets": hard.targets,
            "hard": {"count": len(hard), "sections": hard.sections},
            "with_soft": {"count": len(full), "sections": full.sections},
            "soft_only": sorted(set(full.sections) - set(hard.sections)),
            "closed": bool(check),
            "weakest_links": [
                {"section": sid, "citations": len(cites),
                 "sites": [{"citing": c.citing, "in": c.src, "cited": c.cited,
                            "kinds": list(c.kinds)} for c in cites]}
                for sid, cites in weak],
        }, indent=2))
        return 0 if check else 1

    total = len(graph.sections)
    _print_path(graph, hard, "Prerequisites (" + ", ".join(sorted(graph.hard_kinds)) + ")")
    print(f"\n{len(hard)} of {total} sections on hard edges; "
          f"{len(full)} of {total} once soft citations count too "
          f"(+{len(full) - len(hard)}).")
    added = graph.order(set(full.sections) - set(hard.sections))
    if added:
        print("  added only by soft citations: " + ", ".join(added))
    if graph.unknown_kinds:
        print(f"  ({graph.unknown_kinds} citations had no recorded kind and were counted soft)")
    if graph.optional:
        print(f"  ({len(graph.optional)} results are marked optional; nothing may be proved "
              f"from one, so every citation they make is soft)")

    print(f"\nWeakest links (pulled in by at most {args.weakest} hard citation"
          f"{'s' if args.weakest != 1 else ''}):")
    if not weak:
        print("  none")
    for sid, cites in weak:
        print(f"  {sid} <- {len(cites)}  {graph.title(sid)}")
        for c in cites:
            print(f"      {c.src}: {c.site()}")

    print(f"\nClosure check: {check.report()}")
    return 0 if check else 1


if __name__ == "__main__":
    sys.exit(main())
