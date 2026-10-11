"""
Build System Macros Module
==========================
Converts the book's LaTeX macro file into a MathJax macro table, so the website and
the PDF use the same definitions.

Supported definitions (one per line or several per line):
    \\def\\name{body}
    \\newcommand{\\name}[n]{body}      (also \\renewcommand, \\providecommand, starred forms)
    \\DeclareMathOperator{\\name}{text} (starred form gives \\operatorname*)
"""

import json
import re
from pathlib import Path

# LaTeX constructs MathJax does not provide, rewritten for the web
WEB_REWRITES = [
    (re.compile(r"\\mathbbmss\b"), r"\\mathbb"),
]

# Definitions LaTeX gets from packages (mathtools, bm) that MathJax needs spelled out.
# Applied before the macro file, so the book's own definitions win.
WEB_DEFAULTS: dict[str, str | list] = {
    "coloneqq": "\\mathrel{:=}",
    "eqqcolon": "\\mathrel{=:}",
}
# Applied after the macro file: \providecommand{\bm} is a no-op in LaTeX once the bm
# package is loaded, so the web should follow the package, not the fallback.
WEB_OVERRIDES: dict[str, str | list] = {
    "bm": ["\\boldsymbol{#1}", 1],
}

_NAME = r"\\([A-Za-z]+|[0-9])"


def _strip_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", text)


def _read_group(text: str, pos: int) -> tuple[str, int] | None:
    """Read a balanced {...} group starting at or after pos (skipping spaces)."""
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] != "{":
        return None
    depth = 0
    for i in range(pos, len(text)):
        char = text[i]
        if char == "\\":
            continue
        if char == "{" and (i == 0 or text[i - 1] != "\\"):
            depth += 1
        elif char == "}" and text[i - 1] != "\\":
            depth -= 1
            if depth == 0:
                return text[pos + 1:i], i + 1
    return None


def _strip_ensuremath(body: str) -> str:
    """\\ensuremath{X} -> X (MathJax is always in math mode)."""
    while True:
        index = body.find("\\ensuremath")
        if index < 0:
            return body
        group = _read_group(body, index + len("\\ensuremath"))
        if not group:
            return body
        inner, end = group
        body = body[:index] + inner + body[end:]


def parse_macros(text: str) -> dict[str, str | list]:
    """Parse macro definitions into MathJax form: name -> body or [body, nargs]."""
    text = _strip_comments(text)
    macros: dict[str, str | list] = {}
    pattern = re.compile(
        r"\\def\s*" + _NAME
        + r"|\\(?:new|renew|provide)command\*?\s*(?:\{\s*" + _NAME + r"\s*\}|" + _NAME + r")"
        + r"|\\DeclareMathOperator(\*?)\s*\{\s*" + _NAME + r"\s*\}"
    )
    pos = 0
    while True:
        match = pattern.search(text, pos)
        if not match:
            break
        pos = match.end()
        def_name, cmd_name_braced, cmd_name_bare, operator_star, operator_name = match.groups()

        if def_name:
            group = _read_group(text, pos)
            if not group:
                continue
            body, pos = group
            name, nargs = def_name, 0
        elif operator_name:
            group = _read_group(text, pos)
            if not group:
                continue
            body, pos = group
            name, nargs = operator_name, 0
            body = f"\\operatorname{'*' if operator_star else ''}{{{body}}}"
        else:
            name = cmd_name_braced or cmd_name_bare
            nargs = 0
            arg_match = re.match(r"\s*\[(\d)\]", text[pos:])
            if arg_match:
                nargs = int(arg_match.group(1))
                pos += arg_match.end()
            group = _read_group(text, pos)
            if not group:
                continue
            body, pos = group
            is_provide = "providecommand" in match.group(0)
            if is_provide and name in macros:
                continue

        body = _strip_ensuremath(body.strip())
        for regex, replacement in WEB_REWRITES:
            body = regex.sub(replacement, body)
        macros[name] = [body, nargs] if nargs else body
    return macros


def mathjax_macros(macros_file: Path) -> dict:
    """MathJax macro table for the book (engine defaults, the macro file, then overrides)."""
    macros = dict(WEB_DEFAULTS)
    if macros_file.exists():
        macros.update(parse_macros(macros_file.read_text(encoding="utf-8")))
    macros.update(WEB_OVERRIDES)
    return dict(sorted(macros.items()))


def mathjax_macros_js(macros_file: Path) -> str:
    """Script defining window.BOOK_MACROS, loaded before the MathJax configuration."""
    body = json.dumps(mathjax_macros(macros_file), ensure_ascii=False, indent=1)
    return f"// Generated from {macros_file.name} by build/macros.py\nwindow.BOOK_MACROS = {body};\n"


# =============================================================================
# TeX as plain text
# =============================================================================
# For places that cannot typeset math: <title>, og: tags, aria-labels, graph labels,
# the landing page's text. A book title such as "Number Systems: From \(\nN\) to \(\nR\)"
# becomes "Number Systems: From ℕ to ℝ", reading \nN through the book's own macro file.

_DOUBLE_STRUCK_SPECIAL = {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}
_SCRIPT_SPECIAL = {"B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ", "L": "ℒ", "M": "ℳ", "R": "ℛ"}
_FRAKTUR_SPECIAL = {"C": "ℭ", "H": "ℌ", "I": "ℑ", "R": "ℜ", "Z": "ℨ"}

PLAIN_SYMBOLS = {
    "sqrt": "√", "cdot": "·", "times": "×", "to": "→", "mapsto": "↦", "leq": "≤", "le": "≤",
    "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "in": "∈", "notin": "∉", "subseteq": "⊆",
    "subset": "⊂", "oplus": "⊕", "otimes": "⊗", "cap": "∩", "cup": "∪", "infty": "∞",
    "emptyset": "∅", "varnothing": "∅", "ldots": "…", "dots": "…", "cdots": "⋯",
    "forall": "∀", "exists": "∃", "neg": "¬", "land": "∧", "wedge": "∧", "lor": "∨", "vee": "∨",
    "implies": "⇒", "iff": "⇔", "Rightarrow": "⇒", "Leftrightarrow": "⇔", "circ": "∘",
    "pm": "±", "partial": "∂", "nabla": "∇", "sum": "∑", "prod": "∏", "int": "∫",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "quad": " ", "qquad": " ", ",": " ", ";": " ", " ": " ", "{": "{", "}": "}",
}


def _styled_letter(style: str, char: str) -> str:
    """One letter in a mathematical alphabet (\\mathbb{R} -> ℝ)."""
    if not ("A" <= char <= "Z" or "a" <= char <= "z"):
        return char
    upper = char <= "Z"
    offset = ord(char) - (ord("A") if upper else ord("a")) + (0 if upper else 26)
    if style == "mathbb":
        if char in _DOUBLE_STRUCK_SPECIAL:
            return _DOUBLE_STRUCK_SPECIAL[char]
        return chr(0x1D538 + offset)
    if style == "mathcal" or style == "mathscr":
        if char in _SCRIPT_SPECIAL:
            return _SCRIPT_SPECIAL[char]
        return chr(0x1D49C + offset) if upper else char
    if style == "mathfrak":
        if char in _FRAKTUR_SPECIAL:
            return _FRAKTUR_SPECIAL[char]
        return chr(0x1D504 + offset)
    return char


_STYLES = ("mathbb", "mathcal", "mathscr", "mathfrak")
_UNWRAP = ("mathrm", "mathbf", "mathit", "mathsf", "mathtt", "text", "textrm", "textbf", "textit",
           "operatorname", "boldsymbol", "bm", "ensuremath", "mbox", "emph")


def plain_text(text: str, macros: dict | None = None) -> str:
    """TeX inside a title as readable plain text.

    `macros` is a MathJax macro table (mathjax_macros): argument-free macros are expanded
    through it first, so \\nN reads as the book defines it. Without a table the series
    convention \\nX = blackboard X is assumed.
    """
    if "\\" not in text and "$" not in text:
        return text
    macros = macros or {}
    for _ in range(8):     # expand the book's argument-free macros (nested ones too)
        expanded = re.sub(r"\\([A-Za-z]+)(?![A-Za-z])",
                          lambda m: (" " + macros[m.group(1)] + " ") if isinstance(macros.get(m.group(1)), str)
                          else m.group(0), text)
        if expanded == text:
            break
        text = expanded
    if not macros:
        text = re.sub(r"\\n([A-Z])(?![A-Za-z])", r"\\mathbb{\1}", text)
    # math delimiters
    text = re.sub(r"\\[()\[\]]", " ", text).replace("$", " ")
    # \mathbb{R}, \mathbb R
    def styled(match):
        style, group, single = match.group(1), match.group(2), match.group(3)
        return "".join(_styled_letter(style, c) for c in (group if group is not None else single))
    text = re.sub(r"\\(" + "|".join(_STYLES) + r")\s*(?:\{([^{}]*)\}|([A-Za-z]))", styled, text)
    # \mathrm{x} -> x
    for _ in range(4):
        text = re.sub(r"\\(?:" + "|".join(_UNWRAP) + r")\*?\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\([A-Za-z]+|[,; {}])", lambda m: PLAIN_SYMBOLS.get(m.group(1), m.group(1)), text)
    text = text.replace("{", "").replace("}", "").replace("~", " ")
    text = " ".join(text.split())
    # no space before closing punctuation left by a removed delimiter: "ℝ ," -> "ℝ,"
    return re.sub(r" ([,.;:!?)\]])", r"\1", text)
