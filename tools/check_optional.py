#!/usr/bin/env python3
"""Fail if any proof in the book rests on a result marked optional.

A result written `::: {#thm-foo .optional}` carries a promise, printed on the page
in both editions: *nothing later depends on this*. A reader who skips it loses an
illustration and nothing else, and `tools/reading_path.py` takes the promise at its
word -- an optional result's citations are never prerequisites, so it drags no
section onto anybody's reading path.

The promise is only true while nobody proves anything from it. One proof citing an
optional result and the claim on the page is a lie, the reading paths are short by
however many sections that proof needed, and a reader who skipped the result walks
into a gap. So it is checked here, the way `tools/check_forward_deps.py` checks that
no proof cites a later section: read `_build/crossref_labels.json`, find every hard
citation of an optional result, print the citing sites and exit 1.

*Hard* means the same thing it means to the reading paths, and then some: a proof, a
proof idea, a claim -- and a solution, which is the proof of its exercise. A reading
path may leave the exercises out; an optional result may not be what an exercise is
solved with, because the solution is printed in the book and would be unsupported for
the reader who skipped the result. Everything else -- a remark, a statement, a
warning, a "compare" in prose -- is fine, and is how an optional result is meant to be
referred to.

Run after `./build.py html`. Also run as part of `./build.py check`.

    python3 tools/check_optional.py
    python3 tools/check_optional.py --list      # what is marked optional, and why it costs nothing

Importable:

    from tools.check_optional import find_violations
    assert not find_violations(labels)
"""
import json
import sys
from pathlib import Path

INDEX = Path("_build/crossref_labels.json")

# The blocks whose citations are load-bearing. `proof`, `proofofclaim`, `claim` and
# `idea` are the reading path's hard kinds; `solution` is added because a printed
# solution is an argument the reader is handed, not one they may skip.
LOAD_BEARING = frozenset({"proof", "proofofclaim", "claim", "idea", "solution"})


def find_violations(labels: dict) -> list:
    """Every load-bearing citation of an optional result.

    Returns `(citing label, citing file, cited optional label, cited file, kinds)`
    tuples, sorted, one per (citing, cited) pair.
    """
    optional = {name for name, rec in labels.items() if rec.get("optional")}
    if not optional:
        return []
    violations = []
    for name, rec in sorted(labels.items()):
        kinds_by_label = rec.get("uses_kinds") or {}
        for cited in sorted(rec.get("uses") or ()):
            if cited not in optional or cited == name:
                continue
            kinds = sorted(kinds_by_label.get(cited) or ())
            guilty = [k for k in kinds if k in LOAD_BEARING]
            if guilty:
                violations.append((name, rec.get("file", ""), cited,
                                   labels[cited].get("file", ""), tuple(guilty)))
    return violations


def report(violations: list) -> str:
    lines = []
    for name, where, cited, cited_where, kinds in violations:
        lines.append(
            f"{where.replace('.html', '')}: {name} cites {cited} in its "
            f"{', '.join(kinds)}, but {cited} is marked optional "
            f"({cited_where.replace('.html', '')})")
    return "\n".join(lines)


def list_optional(labels: dict) -> int:
    optional = sorted((rec.get("file", ""), name, rec.get("number", ""),
                       rec.get("title", ""))
                      for name, rec in labels.items() if rec.get("optional"))
    for where, name, number, title in optional:
        soft = sum(1 for rec in labels.values() if name in (rec.get("uses") or ()))
        print(f"{where.replace('.html', '')}: {name} "
              f"{' '.join(filter(None, [number, f'({title})' if title else '']))} "
              f"-- referred to {soft} time{'' if soft == 1 else 's'}, none of them a proof")
    print(f"\n{len(optional)} results are marked optional.")
    return 0


def run(book, labels):
    """`./build.py check` plugin protocol (build/plugins.py): (errors, warnings)."""
    return report(find_violations(labels)).splitlines(), []


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    index = INDEX
    if "--index" in argv:
        index = Path(argv[argv.index("--index") + 1])
    if not index.exists():
        print(f"{index} not found; run ./build.py html first", file=sys.stderr)
        return 1
    labels = json.loads(index.read_text(encoding="utf-8"))["crossref_labels"]

    if "--list" in argv:
        return list_optional(labels)

    violations = find_violations(labels)
    if violations:
        print(report(violations))
        print(f"\n{len(violations)} proof(s) rest on a result marked optional. Either the "
              f"result is not optional -- drop the `.optional` class -- or the citing "
              f"argument must be rewritten so it does not need it.")
        return 1

    optional = sum(1 for rec in labels.values() if rec.get("optional"))
    print(f"No proof rests on an optional result: {optional} marked optional, "
          f"{len(labels)} labels checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
