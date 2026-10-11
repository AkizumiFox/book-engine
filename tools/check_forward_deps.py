#!/usr/bin/env python3
"""Fail if any proof in the book rests on a result proved in a later section.

Reads `_build/crossref_labels.json`, which the HTML build writes. Every label
carries the `file` it lives in, a `uses` list of the labels cited inside its
block and the blocks that follow it, and `uses_kinds`, which says for each cited
label *which environment* cited it.

That last field is what separates the two things a forward citation can be.

* A citation from a **proof**, a proof idea or a claim is load-bearing: the
  argument as written is not complete until the reader has gone forward and read
  something the book has not yet proved. That is a defect, and this tool fails
  on it.
* A citation from an example, an exercise, a solution, a remark, a warning or a
  statement is a **signpost**: "Chapter 43 does this properly". It costs the
  reader nothing and it is how a book is meant to point at what is coming.
  They are listed with `--signposts` rather than treated as errors.

A citation whose kind was not recorded -- an index written before `uses_kinds`
existed -- counts as load-bearing. The reading paths make the opposite choice
and count an unknown kind soft, because there the cost of a wrong guess is a
reader carrying a section they did not need; here it is a gap in a proof, so
this one guesses the other way.

Every label is placed by its file path -- chapter directory, then the section
number in the file name -- and by nothing else. **Do not mix in the `number`
field.** That field is positional: while a chapter has a gap (its section 07
not yet written, say), the build numbers section 10's results 16.9, while the
file name still says 10. An earlier version of this tool placed numbered
results by `number` and exercises by path; the two disagreed across the gap,
which reported false forward citations and could have hidden a real one.

The tool compares sections only. Labels in the same section are reported as
unordered, not as errors: the third component of `number` counts within a type
(`def-connectives` and `thm-contrapositive-equivalent` are both 0.1.1), so it
cannot order two labels, and ordering inside a section is the job of the
section's referee, who can see the text.

Run after `./build.py html`. Exits 1 if a proof cites a later section, or if any
citation names a label that does not exist.

    python3 tools/check_forward_deps.py
    python3 tools/check_forward_deps.py --signposts   # the allowed forward pointers
    python3 tools/check_forward_deps.py --exercises   # results citing an exercise
    python3 tools/check_forward_deps.py --external    # citations of other books

Citations of another book (`@la:thm-x`, config `external-books`) are not
dependencies inside this one: the scan keeps them apart, in `external_uses`, and
they are never forward, never dangling. `--external` lists them.

Also run as part of `./build.py check`, through `find_violations` and `report`,
the way `tools/check_optional.py` is.

Importable:

    from tools.check_forward_deps import find_violations
    assert not find_violations(labels)
"""
import json
import re
import sys
from pathlib import Path

INDEX = Path("_build/crossref_labels.json")


CHAPTER = re.compile(r"^ch(\d+)([a-z]*)[^/]*/(\d+|index)")


def from_file(path):
    """Exercises and examples carry no number, but their path names the section.

    'ch15-norms/04-spectral-radius.html' -> (15, '', 4); an index page -> (n, '', 0).

    A chapter directory may carry a letter after its number: `ch23a-notation` is
    an appendix to Chapter 23 that must not be renamed, because `latex` and
    `theorems.lua` rely on it reading as chapter 23 so that no part banner and no
    "Chapter 24" is emitted (see `authoring/STATUS.md`). That letter is the middle
    component of the key, so `ch23a-notation/index` -> (23, 'a', 0) sorts *after*
    every section of `ch23-applied`, which keys as (23, '', n). Reading the page as
    (23, 0) -- section zero of Chapter 23 -- would place it before Chapter 23's own
    sections and misreport any label put there.
    """
    m = CHAPTER.match(path or "")
    if not m:
        return None
    section = 0 if m.group(3) == "index" else int(m.group(3))
    return int(m.group(1)), m.group(2), section


RESULT_TYPES = {"theorem", "proposition", "corollary", "lemma", "axiom"}


# The blocks whose citations are load-bearing: remove the cited result and the
# citing argument is no longer complete. These are the reading path's hard kinds
# (`tools/reading_path.py`) minus `solution`, which `tools/check_optional.py`
# does count. A solution forward-pointing at a later chapter hands the reader a
# place to look, not a hole -- the exercise is optional work, and the reader who
# does it before the later chapter loses nothing they were promised.
LOAD_BEARING = frozenset({"proof", "proofofclaim", "claim", "idea"})

# A citation the scan could not attribute to an environment. Counted load-bearing:
# see the module docstring.
UNKNOWN_KIND = "?"


def place(labels):
    """label -> (chapter, letter, section), by file path and nothing else."""
    return {name: key for name, rec in labels.items()
            if (key := from_file(rec.get("file"))) is not None}


def forward_citations(labels, order):
    """Every citation crossing into a later section, load-bearing or not.

    Returns `(citing, cited, kinds, load_bearing)` tuples, sorted by citing label.
    `order` maps a label to its `from_file` key; labels missing from it are skipped,
    as are labels naming something that is not a label at all (`main` reports those
    separately, as dangling).
    """
    rows = []
    for name, rec in sorted(labels.items()):
        here = order.get(name)
        if here is None:
            continue
        kinds_by_label = rec.get("uses_kinds") or {}
        for cited in rec.get("uses") or ():
            there = order.get(cited)
            if there is None or there <= here:
                continue
            kinds = tuple(sorted(kinds_by_label.get(cited) or (UNKNOWN_KIND,)))
            rows.append((name, cited, kinds,
                         any(k in LOAD_BEARING or k == UNKNOWN_KIND for k in kinds)))
    return rows


def find_violations(labels) -> list:
    """Every load-bearing forward citation, for `./build.py check`.

    Returns `(citing label, citing file, cited label, cited file, kinds)` tuples,
    the same shape `tools/check_optional.py` returns, so the two gates read alike.
    """
    order = place(labels)
    return [(name, labels[name].get("file", ""), cited,
             labels[cited].get("file", ""),
             tuple(k for k in kinds if k in LOAD_BEARING or k == UNKNOWN_KIND))
            for name, cited, kinds, load_bearing in forward_citations(labels, order)
            if load_bearing]


def report(violations: list) -> str:
    lines = []
    for name, where, cited, cited_where, kinds in violations:
        lines.append(
            f"{where.replace('.html', '')}: {name} cites {cited} in its "
            f"{', '.join(kinds)}, but {cited} is proved later "
            f"({cited_where.replace('.html', '')})")
    return "\n".join(lines)


def list_results_citing_exercises(labels):
    """Print every result that cites an exercise. Advisory, not a gate.

    A theorem must not *rest* on an exercise -- that rule has been broken and
    repaired seven times in this book. But a result may legitimately cite one
    for attribution ("this is exercise C1, proved here in general"), and only
    reading the passage tells the two apart. So this lists candidates for a
    human to triage; it never fails the run.
    """
    rows = []
    for name, rec in sorted(labels.items()):
        if rec.get("type") not in RESULT_TYPES:
            continue
        for cited in rec.get("uses", []):
            if cited.startswith("exr-"):
                rows.append((rec.get("file", "").replace(".html", ""), name, cited))
    for path, name, cited in rows:
        print(f"{path}: {name} -> {cited}")
    print(f"\n{len(rows)} results cite an exercise. Each needs reading: a citation for "
          f"attribution is fine, a proof that depends on the exercise is not.")
    return 0


# `prefix:label`: a citation of another book. The scan files these under
# `external_uses`; an index written before it did carries them in `uses`.
EXTERNAL = re.compile(r"^[A-Za-z]\w*:")


def external_citations(labels):
    """(citing label, citing file, cited external reference) for every citation of another book."""
    rows = []
    for name, rec in sorted(labels.items()):
        cited = set(rec.get("external_uses") or ()) | {
            ref for ref in rec.get("uses") or () if EXTERNAL.match(ref)}
        for ref in sorted(cited):
            rows.append((name, rec.get("file", ""), ref))
    return rows


def list_external_citations(labels):
    """Print every citation of another book, grouped by book prefix. Advisory."""
    rows = external_citations(labels)
    for name, where, ref in rows:
        print(f"{where.replace('.html', '')}: {name} -> {ref}")
    books = sorted({ref.split(":", 1)[0] for _, _, ref in rows})
    print(f"\n{len(rows)} citations of other books ({', '.join(books) or 'none'}). They are "
          f"not dependencies inside this book and are never counted as forward.")
    return 0


def main():
    if not INDEX.exists():
        print(f"{INDEX} not found; run ./build.py html first", file=sys.stderr)
        return 1

    labels = json.loads(INDEX.read_text())["crossref_labels"]

    if "--exercises" in sys.argv:
        return list_results_citing_exercises(labels)
    if "--external" in sys.argv:
        return list_external_citations(labels)

    order = place(labels)
    unplaced = [name for name in labels if name not in order]

    dangling = [(name, cited)
                for name, rec in sorted(labels.items())
                for cited in rec.get("uses") or ()
                if cited not in labels and not EXTERNAL.match(cited)]
    same_section = sum(1 for name, rec in labels.items() if name in order
                       for cited in rec.get("uses") or ()
                       if order.get(cited) == order[name] and cited != name)

    rows = forward_citations(labels, order)
    fatal = [row for row in rows if row[3]]
    signposts = [row for row in rows if not row[3]]

    for name, cited, kinds, _ in fatal:
        print(f"forward: {name} ({labels[name].get('number', '')}) cites "
              f"{cited} ({labels[cited].get('number', '')}) in its {'/'.join(kinds)}")
    for name, cited in dangling:
        print(f"dangling: {name} cites {cited}, which is not a label")

    if "--signposts" in sys.argv:
        for name, cited, kinds, _ in signposts:
            print(f"signpost: {name} ({labels[name].get('file', '')}) points at "
                  f"{cited} ({labels[cited].get('file', '')}) from its {'/'.join(kinds)}")

    checked = len(order)
    if fatal or dangling:
        print(f"\n{len(fatal)} load-bearing forward, {len(dangling)} dangling, "
              f"over {checked} labels. A proof, proof idea or claim may not cite a "
              f"result the book has not reached.")
        return 1

    kinds_seen = sorted({kind for _, _, kinds, _ in signposts for kind in kinds})
    skipped = f", {len(unplaced)} could not be placed" if unplaced else ""
    print(
        f"No proof cites a later section: {checked} labels checked{skipped}; "
        f"{same_section} citations within a section were not ordered.\n"
        f"{len(signposts)} forward pointers are signposts and stay "
        f"({', '.join(kinds_seen)}); run with --signposts to list them."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
