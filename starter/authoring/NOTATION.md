# Book-wide notation

This list is fixed. A chapter that needs a new symbol adds it **here**, and a new macro in
`latex/macros.tex`, before using it. The left column is what to type.

It is a template. The conventions in "Standing conventions" are the ones the existing books
settled on and are worth keeping whatever the subject; the tables below are empty and are
filled in as the book grows. Fill a row the first time a symbol is used, not later.

## Standing conventions

These are book-independent. Keep them.

- **Bold for the concrete, italic for the abstract.** Matrices are bold uppercase
  (`\A`, `\B`), vectors bold lowercase (`\v`, `\x`), and the maps and spaces they represent
  stay plain italic (\( T \), \( V \)). Entries of a matrix stay plain: \( a_{ij} \).
  The zero vector is `\0`, bold, and the scalar zero is `0`.
- **Ordered things go in parentheses, unordered in braces.** An ordered basis is
  `\sB = (\v_1, \dots, \v_n)`; a set is `\{ \v_1, \dots, \v_n \}`. The distinction is load
  bearing the first time order matters, and a reader who has seen it kept everywhere trusts
  it.
- **The two-slot bracket rule.** `\coord{x}{B}` renders \( [x]_{B} \) and `\mtx{T}{B}{C}`
  renders \( [T]_{B}^{C} \): the object in brackets, the data it is taken relative to hanging
  off the brackets, **source below and target above**, always in that order. One notation for
  "X relative to Y", chosen once. Never write a second one for the same thing; the linear
  algebra book carried two for a year and every cross-reference had to be checked by hand
  when one was retired.
- **One symbol, one meaning, book-wide.** If a symbol must be reused with a different
  meaning in a later chapter, say so in its row here and state where the two uses could meet
  and why they do not.
- **Define it before you use it.** No symbol appears before the row that introduces it.
- **`\coloneqq` for "is defined to be"**, not `=` and not `:=` typed by hand.
- **Set-builder notation uses a colon**, `\{ x \in S : P(x) \}`, not a bar, so a bar is free
  to mean divisibility, restriction or absolute value.
- **Functions:** `f \colon X \to Y` and `x \mapsto f(x)`; composition is `g \circ f`.
- **Every symbol here has a macro** in `latex/macros.tex`, so the PDF and the website agree
  and a change of mind is one edit. Nothing ad hoc in a section file.

## Numbers, sets, logic

| Type | Renders / meaning |
|---|---|
| `\nN, \nZ, \nQ, \nR, \nC` | ℕ, ℤ, ℚ, ℝ, ℂ. **Say here whether ℕ contains 0.** |
| `\coloneqq` | "is defined to be" |
| `\{ x \in S : P(x) \}` | set-builder notation, with a colon |
| `S \setminus T`, `\card{S}` | difference, cardinality |
| `f \colon X \to Y`, `x \mapsto f(x)` | functions |
| `\id_X` | identity function |
| | |

## The book's objects

The main characters: what letter each kind of object gets, and what stays plain.

| Type | Meaning |
|---|---|
| | |
| | |
| | |

## Operators and named maps

| Type | Meaning |
|---|---|
| | |
| | |
| | |

## Relations

One row per relation symbol, saying what it relates and to what. A relation reused with a
second meaning is recorded here, with the reason the two uses never meet.

| Type | Meaning |
|---|---|
| | |
| | |

## Retired notation

Notation the book used and no longer uses. Keep the row: it stops a drafting agent
reintroducing it, and it explains an old label that cannot be renamed.

| Was | Now | Why |
|---|---|---|
| | | |

## Major notions

The notions that get the full eleven-step explain template (`authoring/STYLE.md` §3),
listed once so the judgement is not remade per section.

- 
