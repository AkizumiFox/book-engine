"""
Build System Check Plugins
==========================
The checks `./build.py check` runs beyond its built-in ones, named in the book's config:

    "checks": [
        {"tool": "tools/check_structure.py", "fatal": true, "requires": "authoring/STYLE.md"},
        {"tool": "tools/check_numbers.py", "fatal": false, "requires": "verify"},
        "engine:check_macros",
        {"tool": "engine:check_rendered", "options": {"overfull": false}}
    ],
    "checks-disable": ["forward-deps"]

`tool` is a path relative to the book (the book's own plugin) or `engine:<name>`, a
checker in the engine's `tools/`. A plain string is short for `{"tool": ...}`.
`fatal` (default true): its errors fail the check; false reports them as warnings.
`requires`: a file or directory relative to the book; the check is skipped without it.
`options`: passed as a third argument to `run` when given.
`prefix`: put in front of each line it reports (e.g. "fitch").

Protocol: the module defines

    def run(book, labels) -> tuple[list[str], list[str]]        # (errors, warnings)

(or `run(book, labels, options)`), where `book` is a build.book.Book and `labels` the
label index (`_build/crossref_labels.json`'s `crossref_labels`). A module without `run`
but with the label checkers' pair `find_violations(labels)` / `report(violations)` is
run through that pair.

Two engine checkers always run unless `checks-disable` names them: `optional`
(tools/check_optional.py) and `forward-deps` (tools/check_forward_deps.py).
`checks-disable` also takes the names of `check`'s built-in rules: `xref-links`,
`moved-ids`, `components`, `numbering`, `title-mentions`, `spelling`.
"""

import importlib.util
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
ENGINE_TOOLS = ENGINE_ROOT / "tools"

# name in checks-disable -> engine tool, run by default
DEFAULT_CHECKS = {
    "optional": "check_optional",
    "forward-deps": "check_forward_deps",
}
BUILT_IN_RULES = {"xref-links", "moved-ids", "components", "numbering", "title-mentions", "spelling"}


def disabled(book, name: str) -> bool:
    """Whether the config's `checks-disable` turns off a default check or built-in rule."""
    return name in set(book.config.get("checks-disable") or ())


def unknown_disables(book) -> list[str]:
    known = set(DEFAULT_CHECKS) | BUILT_IN_RULES
    return [name for name in book.config.get("checks-disable") or () if name not in known]


def resolve_tool(book, tool: str) -> Path:
    """`engine:<name>` -> the engine's tools/<name>.py; anything else is relative to the book."""
    if tool.startswith("engine:"):
        name = tool.split(":", 1)[1]
        return ENGINE_TOOLS / (name if name.endswith(".py") else f"{name}.py")
    return book.root / tool


def load_module(path: Path, name: str | None = None):
    """Import a checker by path (`tools/` is not a package). The checker's directory and,
    for a book's plugin, the book root are put on sys.path while it loads, so it can
    import its sibling modules either way it is used to."""
    name = name or f"book_check_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    added = [str(p) for p in (path.parent, path.parent.parent) if str(p) not in sys.path]
    sys.path[:0] = added
    try:
        spec.loader.exec_module(module)
    finally:
        for p in added:
            if p in sys.path:
                sys.path.remove(p)
    return module


def engine_tool(name: str):
    """An engine checker in tools/, by name (e.g. "check_optional")."""
    return load_module(ENGINE_TOOLS / f"{name}.py", name)


def entries(book) -> list[dict]:
    """The `checks` list, normalised: each entry a dict with `tool` and `fatal`."""
    result = []
    for entry in book.config.get("checks") or ():
        if isinstance(entry, str):
            entry = {"tool": entry}
        result.append(dict({"fatal": True}, **entry))
    return result


def _call(module, book, labels, options):
    if hasattr(module, "run"):
        if options is not None:
            return module.run(book, labels, options)
        return module.run(book, labels)
    if hasattr(module, "find_violations") and hasattr(module, "report"):
        return module.report(module.find_violations(labels)).splitlines(), []
    raise AttributeError("defines neither run(book, labels) nor find_violations/report")


def run_checks(book, labels: dict) -> tuple[list[str], list[str]]:
    """(errors, warnings) of the default engine checks and the config's `checks`."""
    errors, warnings = [], []
    for name in unknown_disables(book):
        warnings.append(f"checks-disable: unknown check '{name}' (known: "
                        f"{', '.join(sorted(set(DEFAULT_CHECKS) | BUILT_IN_RULES))})")

    plan = [{"tool": f"engine:{tool}", "fatal": True}
            for name, tool in DEFAULT_CHECKS.items() if not disabled(book, name)]
    configured = entries(book)
    named = {resolve_tool(book, e["tool"]).resolve() for e in plan}
    plan += [e for e in configured if resolve_tool(book, e.get("tool", "")).resolve() not in named]

    if "macro-check" in book.config and not any(
            resolve_tool(book, e.get("tool", "")).stem == "check_macros" for e in configured):
        warnings.append('config has "macro-check" but "checks" does not list "engine:check_macros"; '
                        'the macro check does not run')

    for entry in plan:
        tool = entry.get("tool") or ""
        path = resolve_tool(book, tool)
        requires = entry.get("requires")
        if requires and not (book.root / requires).exists():
            continue
        if not tool or not path.is_file():
            errors.append(f"checks: {tool or '(entry without a tool)'} not found ({path})")
            continue
        try:
            module = load_module(path, path.stem if tool.startswith("engine:") else None)
            found, notes = _call(module, book, labels, entry.get("options"))
        except Exception as error:  # a plugin that crashes fails the check, legibly
            errors.append(f"checks: {tool} failed: {type(error).__name__}: {error}")
            continue
        prefix = f"{entry['prefix']}: " if entry.get("prefix") else ""
        found = [prefix + line for line in found if line.strip()]
        notes = [prefix + line for line in notes if line.strip()]
        (errors if entry.get("fatal", True) else warnings).extend(found)
        warnings.extend(notes)
    return errors, warnings
