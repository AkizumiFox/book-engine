# Drafting brief (shared by all section-drafting agents)

You are drafting sections of a comprehensive, reader-caring textbook (Pandoc Markdown -> static site + PDF). The repository root is the book; `./build.py` builds it.

## Read before writing
1. `authoring/STYLE.md` — the writing standard. Follow it exactly (explain template, Idea/Proof registers, Quick checks, warnings, A/B/C exercises with complete solutions, syntax).
2. `authoring/NOTATION.md` — fixed notation; `latex/macros.tex` for available macros.
3. `src/ch00-demo/01-every-environment.md` — the markup of every environment, with the source next to the built page. Delete this chapter once the book has real content.
4. The chapter blueprint, if the book keeps one — your sections' entries are the spec (content, labels to keep, labels to create, proof routes, examples, exercises) and the cross-section label use list.
5. The earlier chapters' label lists: `grep -rho "{#[a-z]*-[^} ]*" src/chNN-*/` for each earlier chapter, and read the specific earlier results you cite so your recall of them is accurate.
6. Old versions of your files (if any), to preserve labels.

## Rules
- Original prose only. Do not copy from any textbook. A reference work may be consulted only to check that a statement is true or that coverage is complete — never paraphrase its text, examples or exercises. Copyrighted material is never committed to this repository.
- Keep every display inside the text column: a formula wider than about 60 characters of ordinary math is broken with `aligned` or `cases` (a `\tag` goes after `\end{aligned}`, never inside). No blank line inside a `\[ ... \]`.
- Section length ~2,500–5,000 prose words (math spans count as one word); complete: opening frame, notions per the explain template, theorems with lead-in / Idea / Proof / aftermath, ≥1 `::: {.check}` followed (not nested) by a `::: {.solution}` block, ≥1 `::: {.warning}`, `## Exercises` with `### A. Check your understanding` / `### B. Practice` / `### C. Going deeper`, each exercise `::: {#exr-<section-slug>-a1}` titled `[A1]` followed by a complete `::: {.solution}`.
- Math: `\( \)` and `\[ \]` only. Relation symbols are typeset, never unicode characters: proof-direction tags are `\( (\Rightarrow) \)`, `\( (\Leftarrow) \)`, `\( (\subseteq) \)`, `\( (\supseteq) \)`, and a chain reads `(a) \( \Rightarrow \) (b)`. Pandoc fenced divs must be closed, with blank lines around them.
- Labels globally unique: grep `src/` before creating one. Keep every "keep label" exactly.
- `@label` refs only to earlier material (earlier chapters, earlier sections of this chapter, or earlier in your file). Forward pointers in prose say "in Chapter N" without an `@ref`. No proof may rest on an exercise, and every result is either proved or plainly marked as not proved here.
- Verify every non-trivial computation with a computer algebra system. Never mention it, or any software, in the book text itself (runnable `{.python .run}` cells are the only exception).
- American spelling. Add genuine new words to `spelling.txt` (append only).
- Do not delete or rename files other than those assigned; do not edit other sections, the config, or `authoring/STATUS.md` (report forward promises instead).

## When done
Run `./build.py html 2>&1 | grep -i "warn\|error" | head -30` and fix warnings originating in YOUR files (other agents may build concurrently; ignore issues from files that aren't yours). Reply with: files written, prose word counts, labels created, blueprint deviations and why, forward promises made (for `STATUS.md`), claims you were unsure about.

## Building while other agents work

Several drafting agents may run at once, and **the scratchpad directory is shared between all of them**. Never build in the shared source tree (concurrent builds corrupt `_build/cache`), and never build in a generically named scratch folder such as `scratchpad/repo/`: in one chapter two agents used the same one and one `rsync --delete`d the other's copy. Copy the repo into a directory named after your own sections, for example `scratchpad/ch17-s05-s07/repo/`, and build there.
