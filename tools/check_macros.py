#!/usr/bin/env python3
"""Fail on retired or undefined macros, in the manuscript and in the notation guide.

Two rules, one checker, applied to `src/` and to the files the book names as its
notation guide (`authoring/NOTATION.md`), so the guide cannot drift from the rule the
manuscript follows -- it was a second source of truth once, and drifted:

1. **Retired macros are errors.** The book's config lists them under
   `macro-check.retired` (with `retired-hint`, what to write instead). The notation
   guides are `macro-check.guides`; `macro-check.retired-only` names other authoring
   files (style guides whose code examples are build syntax, TikZ and the like, not
   formulas) that get this rule only. In the linear algebra book, for example, they are
   the single-letter bold vector macros `\\a` ... `\\z` and `\\0`: vectors are typed by
   what they are (`\\cvec{x}`, `\\elem{v}`), and a single bold letter says neither. The
   definitions stay in `latex/macros.tex` so old drafts still compile; using one is
   what fails.

2. **Every macro used must be defined.** Each control sequence and environment found
   in math is asked of MathJax, configured as `build/render_math.cjs` configures it for
   the book (same packages, same macro table from `latex/macros.tex`), so "defined"
   means what it means to the build. One name per formula, so one unknown name cannot
   hide another. Needs `node` and the MathJax copy the build downloads; without them
   this rule is skipped with a notice and rule 1 still runs.

3. **The zero matrix is not a zero vector.** When the config sets
   `macro-check.zero-matrix` (e.g. `\\O`, a bold O), the zero matrix must not be written
   as the zero vector `\\cvec{0}`. Two such spellings are caught: `\\cvec{0}`
   with a matrix-size subscript (`\\cvec{0}_{m \\times n}`), and `\\cvec{0}` on either
   side of a Loewner comparison (`\\succ`, `\\succeq`, `\\prec`, `\\preceq`, with or
   without `\\not`), since the Loewner order compares matrices. The \\( 1 \\times 1 \\)
   zero matrix is `\\O_1`, so `(0)` after `=`, `\\ne`, `\\oplus` or a Loewner sign is
   caught as well. Other zero matrices written `\\cvec{0}` or `(0)` are not detectable
   from the text and are left to review.

What is scanned. In `src/`: everything except fenced code blocks, inline code spans and
TikZ code, where `\\x`, `\\i`, `\\c` ... are mostly `\\foreach` variables -- inside a
`tikzpicture` only `$...$` labels count, and never a loop variable. A backslash pair
`\\\\` is a line break, not a macro. In the notation guide: everything, since every code
span, code block and formula there is an example of what to type; inline code is
checked as math when it contains a backslash.

Opt-in: `./build.py check` runs it only for a book whose config has a `macro-check`
object (even an empty one, for rule 2 alone). By hand:

    python3 tools/check_macros.py            # the book in the current directory
    python3 tools/check_macros.py --no-mathjax

Importable:

    from tools.check_macros import retired_uses
    assert not retired_uses(text, {"v"})
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
RENDERER = ENGINE_ROOT / "tools" / "check_macros.cjs"

# A backslash pair first (a line break), then a control word or a control symbol.
TOKEN = re.compile(r"\\\\|\\([A-Za-z]+|[^A-Za-z\s])")
TIKZ_BEGIN = re.compile(r"\\begin\{(tikzpicture|tikzcd)\}")
TIKZ_END = re.compile(r"\\end\{(tikzpicture|tikzcd)\}")
FOREACH = re.compile(r"\\foreach\s*((?:\\[A-Za-z]+\s*/?\s*)+)\s*in")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"(`+)(.+?)\1")
MATH = re.compile(r"\\\((.*?)\\\)|\\\[(.*?)\\\]", re.S)
DOLLARS = re.compile(r"\$([^$]*)\$")
ENVIRONMENT = re.compile(r"\\(?:begin|end)\s*\{([^}]*)\}")
# Text inside these is text to MathJax: a macro there is printed, never expanded.
CVEC_ZERO = r"\\cvec\s*\{\s*0\s*\}"
LOEWNER = r"\\(?:not\s*\\)?(?:succeq|succ|preceq|prec)(?![A-Za-z])"
ZERO_WITH_SIZE = re.compile(CVEC_ZERO + r"\s*_\s*\{[^{}]*\\times(?![A-Za-z])")
LOEWNER_ZERO = re.compile(LOEWNER + r"\s*" + CVEC_ZERO + "|" + CVEC_ZERO + r"\s*" + LOEWNER)
ONE_BY_ONE_ZERO = re.compile(r"(?:=|\\neq?(?![A-Za-z])|\\oplus(?![A-Za-z])|" + LOEWNER + r")\s*\(\s*0\s*\)")
TEXT_COMMANDS = re.compile(r"\\(?:text|textrm|textit|textbf|textsf|texttt|mbox|hbox)\s*\{")


def _blank(text: str, start: int, end: int) -> str:
    """Replace text[start:end] by spaces, keeping newlines so line numbers survive."""
    return text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]


def _strip_text_groups(text: str) -> str:
    """Blank the contents of \\text{...} and friends (nested braces respected)."""
    out = text
    for match in reversed(list(TEXT_COMMANDS.finditer(text))):
        depth, i = 0, match.end() - 1
        while i < len(out):
            if out[i] == "{" and out[i - 1] != "\\":
                depth += 1
            elif out[i] == "}" and out[i - 1] != "\\":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out = _blank(out, match.end(), i)
    return out


def manuscript_text(text: str) -> str:
    """The part of a manuscript file the checks see: code fences, inline code and TikZ
    code blanked out (TikZ `$...$` labels kept, minus `\\foreach` variables)."""
    lines = text.split("\n")
    out = []
    in_fence = in_tikz = False
    loop_vars: set[str] = set()
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        if in_fence:
            out.append("")
            continue
        starts_tikz = bool(TIKZ_BEGIN.search(line))
        if starts_tikz and not in_tikz:
            loop_vars = set()
        tikz_line = in_tikz or starts_tikz
        in_tikz = tikz_line and not TIKZ_END.search(line)
        if tikz_line:
            for match in FOREACH.finditer(line):
                loop_vars.update(re.findall(r"\\([A-Za-z]+)", match.group(1)))
            kept = []
            for match in DOLLARS.finditer(line):
                label = match.group(1)
                for var in loop_vars:
                    label = re.sub(r"\\" + var + r"(?![A-Za-z])", " " * (len(var) + 1), label)
                kept.append(label)
            out.append("  ".join(kept))
            continue
        out.append(INLINE_CODE.sub(lambda m: " " * len(m.group(0)), line))
    return "\n".join(out)


def retired_uses(text: str, retired: set[str]) -> list[tuple[int, str]]:
    """(line number, macro) for every use of a retired macro in already-filtered text."""
    found = []
    for match in TOKEN.finditer(text):
        name = match.group(1)
        if name and name in retired:
            found.append((text.count("\n", 0, match.start()) + 1, "\\" + name))
    return found


def zero_matrix_misuses(text: str, zero: str = r"\O") -> list[tuple[int, str]]:
    """(line number, message) for each `\\cvec{0}` that can only be a zero matrix: with
    a matrix-size subscript, or in a Loewner comparison; and each `(0)` that is a
    \\( 1 \\times 1 \\) zero matrix."""
    found = []
    for match in ONE_BY_ONE_ZERO.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        found.append((line, f"1 x 1 zero matrix written (0); write {zero}_1"))
    for pattern, why in ((ZERO_WITH_SIZE, "with a matrix size"),
                         (LOEWNER_ZERO, "in a Loewner comparison")):
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((line, f"zero matrix written \\cvec{{0}} {why}; write {zero}"))
    return sorted(found)


def math_segments(text: str, guide: bool) -> list[tuple[int, str]]:
    """(line number, TeX) for each formula. In a notation guide, inline code with a
    backslash counts as a formula, and fenced code blocks are read as Markdown."""
    segments = []
    if guide:
        for match in INLINE_CODE.finditer(text):
            code = match.group(2)
            if "\\" in code and not MATH.search(code):
                segments.append((text.count("\n", 0, match.start()) + 1, code))
        text = INLINE_CODE.sub(lambda m: m.group(2) if MATH.search(m.group(2)) else " " * len(m.group(0)), text)
    for match in MATH.finditer(text):
        body = match.group(1) if match.group(1) is not None else match.group(2)
        segments.append((text.count("\n", 0, match.start()) + 1, body))
    if not guide:
        # TikZ node labels survive manuscript_text as bare $...$ bodies on their line
        for match in DOLLARS.finditer(text):
            segments.append((text.count("\n", 0, match.start()) + 1, match.group(1)))
    return segments


def names_used(segments: list[tuple[int, str]]) -> tuple[dict, dict]:
    """{control sequence: first line} and {environment: first line} in the formulas."""
    names: dict[str, int] = {}
    environments: dict[str, int] = {}
    for line, tex in segments:
        tex = _strip_text_groups(tex)
        for match in ENVIRONMENT.finditer(tex):
            environments.setdefault(match.group(1).strip(), line)
        for match in TOKEN.finditer(tex):
            name = match.group(1)
            if name and name not in ("begin", "end"):
                names.setdefault(name, line)
    return names, environments


def ask_mathjax(names, environments, macros: dict, mathjax: Path) -> tuple[list, list]:
    job = {"mathjax": str(mathjax), "macros": macros,
           "names": sorted(names), "environments": sorted(environments)}
    result = subprocess.run(["node", str(RENDERER)], input=json.dumps(job),
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-2000:] or "node failed with no message")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    return data["undefined"], data["unknown_environments"]


def _mathjax_dir() -> Path | None:
    """The build's cached MathJax, if present (this check never downloads it)."""
    sys.path.insert(0, str(ENGINE_ROOT))
    from build.math import mathjax_dir  # noqa: E402
    target = mathjax_dir(None)
    return target if shutil.which("node") and (target / "startup.js").exists() else None


def check_files(root: Path, manuscript: list[Path], guides: list[Path], retired: set[str],
                macros: dict | None, mathjax: Path | None, hint: str = "",
                retired_only: list[Path] = (), zero_matrix: str = "") -> tuple[list[str], list[str]]:
    """(errors, notices) for the given files. `macros` None skips the definedness rule,
    and an empty `zero_matrix` (the macro to write instead) skips the zero-matrix rule."""
    errors, notices = [], []
    where_names: dict[str, tuple[str, int]] = {}
    where_envs: dict[str, tuple[str, int]] = {}
    files = [(p, False) for p in manuscript] + [(p, True) for p in guides]
    files += [(p, None) for p in retired_only]
    for path, guide in files:
        text = path.read_text(encoding="utf-8")
        seen = manuscript_text(text) if guide is False else text
        shown = path.relative_to(root) if path.is_relative_to(root) else path
        for line, macro in retired_uses(seen, retired):
            errors.append(f"{shown}:{line}: retired macro {macro}" + (f"; {hint}" if hint else ""))
        if guide is None:
            continue
        if zero_matrix:
            for line, message in zero_matrix_misuses(seen, zero_matrix):
                errors.append(f"{shown}:{line}: {message}")
        names, environments = names_used(math_segments(seen, guide))
        for name, line in names.items():
            where_names.setdefault(name, (str(shown), line))
        for env, line in environments.items():
            where_envs.setdefault(env, (str(shown), line))

    if macros is None or not (where_names or where_envs):
        return errors, notices
    if mathjax is None:
        notices.append("node or the cached MathJax not found: undefined-macro check skipped "
                       "(run ./build.py html once to download MathJax)")
        return errors, notices
    undefined, unknown = ask_mathjax(where_names, where_envs, macros, mathjax)
    for name in undefined:
        shown, line = where_names[name]
        errors.append(f"{shown}:{line}: undefined macro \\{name}")
    for env in unknown:
        shown, line = where_envs[env]
        errors.append(f"{shown}:{line}: unknown environment {env}")
    return errors, notices


def check_book(book, use_mathjax: bool = True) -> tuple[list[str], list[str]]:
    """Run both rules on a build.book.Book: its chapter sources and its notation guides."""
    from build.macros import mathjax_macros
    settings = book.config.get("macro-check", {})
    retired = set(settings.get("retired", []))
    guides = [book.path(p) for p in settings.get("guides", []) if book.path(p).exists()]
    retired_only = [book.path(p) for p in settings.get("retired-only", []) if book.path(p).exists()]
    manuscript = sorted(page.source for page in book.pages)
    macros = mathjax_macros(book.macros_file) if use_mathjax else None
    return check_files(book.root, manuscript, guides, retired, macros,
                       _mathjax_dir() if use_mathjax else None, settings.get("retired-hint", ""),
                       retired_only, settings.get("zero-matrix", ""))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    sys.path.insert(0, str(ENGINE_ROOT))
    from build.book import Book
    root = Path(argv[argv.index("--book") + 1]) if "--book" in argv else Path.cwd()
    errors, notices = check_book(Book(root), use_mathjax="--no-mathjax" not in argv)
    for notice in notices:
        print(notice, file=sys.stderr)
    if errors:
        print("\n".join(errors))
        print(f"\n{len(errors)} macro problem(s).")
        return 1
    print("Macros: no retired or undefined macro, and no zero matrix written as a vector, "
          "in the manuscript or the notation guide.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
