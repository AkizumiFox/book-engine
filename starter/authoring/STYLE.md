# Writing standard for the book

This file is for anyone who writes a section: the author, or a drafting agent. Read all of it before you write. Also read `authoring/NOTATION.md` and, if the book keeps blueprints, the chapter's blueprint.

**Hard rules**
- **No copying.** Reference works consulted while writing are copyrighted. Use them to check which topics exist and whether a statement is true. Do not paraphrase their prose or copy their examples or exercises. Standard theorems are common property; the explanation, the examples and the exercises must be our own. Copyrighted reference material is never committed to this repository.
- **A result is either proved, or plainly marked as not proved here.** There is no third option. If a theorem is used without proof, say so in one sentence where it is stated, and say where a proof lives in general terms ("this is proved in any course on X"). Never let a gap pass as an argument.
- **No proof rests on an exercise.** Exercises may cite the text; the text may not cite an exercise for a step it needs. A later exercise may cite an earlier exercise.
- **No forward references in proofs.** A proof may cite only results that appear **earlier** in the book: an earlier section, or earlier in the same section. A forward pointer in the prose ("we will prove in Chapter 9 that ...") is fine. It must never be a step in an argument. `tools/check_forward_deps.py` enforces this.
- **Every claim is true.** Check every computation (with a computer algebra system, privately: the book text never mentions software, "sympy confirms" or how a result was verified; write a by-hand check the reader can follow instead), and state every hypothesis. If you are unsure, compute it or leave a `TODO(verify)` comment. Never guess.
- **Section titles carry no mathematics.** The `#` line becomes a navigation link, a page title and a PDF bookmark. Plain words only.

---

## 1. The reader

The reader is a motivated student working **alone**. They have no lecture to fill gaps and no one to ask. Care for them:

- **Say why before what.** Explain what problem a definition or theorem solves before stating it.
- **Recall before use.** When an earlier result is used, recall it in a clause, name it, and link it with `@label`.
- **Warn early.** Name a known trap *before* the reader can fall into it, with a concrete failing case.
- **Let the reader check themselves.** Put a Quick check with a folded answer in every section.
- **Show every move.** Where a move is not visible ("why this choice?"), give one clause of reason. The written proof stays minimal and forward; the Idea block carries the discovery.
- **Stay calm.** No hype and no "clearly" or "obviously" hiding a step. "Trivially" is allowed only for something that really is one line and is then written out.
- **One new notion at a time.** Use at most two new **major** notions per section. Minor definitions (notation, auxiliary terms) may exceed this when they are introduced just before their first use; a section carrying more than two major notions should be split.

## 2. Page skeleton

Each section is one Markdown file, `src/chNN-slug/MM-slug.md`, whose first line is `# Title`.

```markdown
# Title of the Section

Opening frame: 2-4 sentences. Where we are, what question is open, what this section
does. Plain prose, no heading.

## First subsection heading

...notion or theorem blocks...

## Exercises

### A. Check your understanding
### B. Practice
### C. Going deeper
```

Section titles (the `#` line) contain no math, since they appear in navigation links and page titles. Use `##` for subsections (they appear in the page's table of contents) and `###` only inside Exercises or for a long worked computation. Aim for **2,500-5,000 words**. Split a longer section at a natural seam.

A chapter's `index.md` contains, in this order:
1. `# Chapter Title`.
2. A 1-2 paragraph story of the chapter: the question it answers and why the reader should care.
3. **What you need:** the earlier chapters or sections used, with links.
4. **Roadmap:** a bullet per section, with one sentence each.
5. **Named moves:** a short list of the proof techniques this chapter introduces, so the reader can transfer them.

## 3. Introducing a notion (the explain template)

For each new definition, in order:

1. **Situate** (1-2 sentences). Where does it sit? Objects then maps, an object then its subobjects, or a question left open.
2. **Hook.** Choose **one**:
   - a naive notion that fails, shown failing;
   - a recurring expression that deserves a name;
   - the standard example, generalised;
   - a goal theorem stated first ("we want to prove ...; we need a word for ...");
   - an everyday word.
3. **Slogan.** One sentence in plain words, written in *italics* as its own paragraph.
4. **Definition.**
   - Every quantifier, every ambient assumption, and what the notion is defined on.
   - **Bold** the term defined and the small words that carry weight: **not all zero**, **for every**, **strictly**, **a** vs **the**, **non-zero**.
5. **Paraphrase** clause by clause ("In words: the first condition says ...").
6. **Well-definedness**, if there is anything to check: independence of choices, existence, uniqueness.
7. **Examples**, 2-4 of them, simplest first.
   - Check each against the definition clause by clause.
   - Spread them across the families of objects the book works with.
   - Include one degenerate case (the empty one, the one-element one, the identity) and say why it matters.
8. **Non-example by minimal change.** Change one example slightly, say what still works, and name the exact clause that fails.
9. **Why this definition.** What breaks if a clause is dropped or a convention changed. Where the name comes from, if it helps.
10. **Warning** (`::: {.warning}`). The misconception, with a concrete failing case.
11. **Payoff.** The first small result, a link to an earlier concept, and one sentence on where this is going.

Not every notion needs every step at full size. A minor auxiliary definition may use steps 4, 7 and 8 only. **Major notions get all eleven.** A notion is major if later chapters cannot be read without it; keep the book's list of major notions in `authoring/NOTATION.md` or a blueprint so the judgement is made once.

## 4. Theorems and proofs

For each theorem:

1. **Lead-in sentence.** Say what the result does or what need it fills.
2. **The statement**, complete and self-contained, with all hypotheses. Give it a short `[Name]` title when it has a standard name or will be cited later.
3. **Idea** (`::: {.idea}`, 2-6 lines, plain prose).
   - The reasoning found backwards, a picture described in words (or TikZ), a small case, or a numbered plan.
   - This is where "why do we do this?" is answered.
   - Omit it for proofs of 3 lines or fewer.
4. **Proof** (`::: {.proof}`), in the typeset register:
   - **First sentence does mathematics:** "Let ...", "Suppose ...", "Since ...", "By @thm-x, ...". Never motivation (that went in the Idea).
   - **Chain the steps** with Therefore / Hence / Thus / In particular / Then.
   - **Every step names its reason**: a hypothesis, a definition, or a cited result (`@label`, not restated). Where a display hides a reason, add "where the second equality uses ...".
   - **Always justify:** each condition checked against a definition; why a choice is possible; that a quantity is non-zero before dividing; that two things commute before swapping them; that an object is invertible before cancelling.
   - **You may skip:** a symmetric half ("swapping the roles of \( U \) and \( W \) gives the reverse inclusion"), and a repeat of an argument just given.
   - **Labels:** `\( (\Rightarrow) \)`/`\( (\Leftarrow) \)`, `\( (\subseteq) \)`/`\( (\supseteq) \)`, *Case 1.*/*Case 2.*, and `::: {.claim}` with a nested `::: {.proofofclaim}` for a genuinely separate fact inside a long proof.
   - **Ending:** "This shows ..." / "This proves ..." / "as claimed".
   - **Length:** most proofs are 5-20 lines. For a long theorem, write a **Step roadmap** in the Idea, then `**Step 1.**` ... inside the proof, with Claims.
   - **One proof per theorem.** A second route gets at most one short "Alternatively," paragraph, and only when it teaches something.
5. **Aftermath** (1-2 sentences). What is this result for? What does it let us do now? Use a `::: {.remark}` only if it needs a separate block, e.g. "the converse fails: ...".

**Preferred proof routes.** Keep the book's own list here as it grows -- the moves that recur in *this* subject, written down once so a drafting agent reaches for them instead of improvising. The general ones:

- **Givens and goal first.** Unwind the definitions; the definition tells you what to fix arbitrarily.
- **Plug in a structure theorem.** If a big theorem applies, its conclusion is the first real line.
- **Find the job of each hypothesis.** An unused hypothesis is where the finish comes from.
- **Count instead of check**, whenever the book has an invariant that forces equality.
- **Contradiction for "cannot", "unique", "at most".** Negate carefully, quantifier by quantifier.
- **Induction:** say "induction on what", then find the smaller object inside.
- **Refute with one small witness** and name what fails.

When a brute-force route exists, it is fine to say in the Idea that it is legitimate but messy, then take the structural one.

### Optional results

Some results are worth stating and proving and yet nobody is obliged to read them: an illustration of a definition just given, a remark that deserves a proof, a bridge showing how this corner of the book meets another. Keep writing them. Mark them:

```markdown
::: {#thm-foo .optional}
[A Title]
```

`.optional` goes on the statement's div, beside its id. Both editions then print a marker on the title line -- *Optional: nothing later depends on this.* -- and the reader may skip the block, its Idea and its proof without wondering what they lost.

**What it buys.** The reading paths (`tools/reading_path.py`) treat an optional result's citations as context rather than prerequisites. Nothing requires the result, so nothing it cites can be required through it, and it puts no section on anybody's path. That is the point: a short result that cites a chapter the surrounding section otherwise never needs will drag that chapter onto every path that passes nearby. Marked optional, it drags nothing, and the label stays in the book.

**The invariant.** *Nothing anywhere may be proved from an optional result.* No proof, proof idea, claim or written solution may cite one -- in the whole book, not just later in the section. `tools/check_optional.py` checks it and `./build.py check` fails on it, naming the citing sites:

```
ch11-x/04: thm-later cites thm-aside in its proof,
but thm-aside is marked optional (ch10-y/06)
```

When that fires, one of two things is true: the result is genuinely used, so drop `.optional`; or the citing argument can be written without it, so write it that way. Never both mark a result optional and lean on it -- the marker is a promise printed on the page.

Prose, statements, remarks, warnings and quick checks may point at an optional result freely. That is how a connection is meant to be referred to.

**When to reach for it.** An illustration, or a connection between two parts of the book. Never use it on something a later proof needs, and never as a way to keep a result whose citations you would rather not justify. If in doubt, ask what breaks if the reader skips it: if the answer is anything but "a sentence elsewhere loses a pointer", it is not optional.

Run `python3 tools/check_optional.py --list` to see everything currently marked.

## 5. Examples, checks, warnings, remarks

- **Examples** `::: {#exm-slug}` with a `[Title]` first line. State the question inside the example. Put the worked answer in a following `::: {.solution}`; it starts folded on the web. Choose data so the computation is clean.
- **Quick check** `::: {.check}`: one short question. Its answer is a `::: {.solution}` placed **right after** the check block closes, never nested inside it. Put at least one per section, placed right after the idea it tests. Good checks:
  - a non-example failing only clause k;
  - "why must this be strict?";
  - "is this look-alike an example?";
  - a tiny computation.
- **Warning** `::: {.warning}`: one misconception, a concrete failing case, 1-4 sentences.
- **Remark** `::: {.remark}`: 1-3 sentences with one job (converse fails, other names or notations, in other words, outlook).
- **Pictures:** TikZ inside `\begin{center}\begin{tikzpicture}...\end{tikzpicture}\end{center}` in a raw LaTeX block. One idea per figure. Colour must never be the only carrier of meaning.
- **Interactive:** `::: {.plot fn= x= y= params=}` for functions with sliders, `{.python .run}` for small experiments, and `::: {.widget src=}` with a `::: {.print}` fallback. Use them sparingly and only where exploring helps.

## 6. Exercises

Each section ends with `## Exercises` and three groups.

**A. Check your understanding.** Exactly one exercise with 2-6 lettered parts: define, state, decide true/false with a reason, name the method. Readers should be able to answer before moving on.

**B. Practice.** 2-4 exercises "like the examples", each with a worked example type in the section:
- A "Determine which of the following ... Justify your answer." batch with one or two planted failures.
- A computation with clean data ending in "Hence ...".
- A routine proof applying one theorem once.

**C. Going deeper.** 1-4 exercises:
- a (a) Prove / (b) Deduce pair;
- a counterexample, construction, or change of one hypothesis;
- optionally one harder problem, made reachable with scaffolded parts and a hint.

**Format.** Every exercise is `::: {#exr-<section-slug>-a1}` (then `-b1`, `-b2`, `-c1`, ...) whose first line is a title `[A1]`, `[B2: Short name]`, etc. It is followed by a `::: {.solution}` written in the typeset register (complete, not a sketch).

**Parts** use a lettered list:

```markdown
::: {.enumerate options="label=(\alph*)"}
1. ...
2. ...
:::
```

**Wording:** "Prove that", "Determine whether ... Justify your answer.", "Give an example of ...", "Explain why ... is **not** ...", "Hence deduce ...".

**Hints** go at the end in italics: *Hint: consider ...*. A hint names a tool or an object, never a step.

**Calibration:**
- B uses one theorem once.
- C combines two ideas, generalises to \( n \), or changes a hypothesis.
- A harder C item uses three ingredients, one from an earlier chapter.
- A later exercise may cite an earlier one ("By @exr-something-b2 ..."). No proof in the main text may cite an exercise.

## 7. Prose

- **Voice.** "We" for the author and reader together; "you" sparingly, for direct advice. Median sentence 12-18 words. Paragraphs of 1-4 sentences. Vary rhythm; no walls of text.
- **Emphasis.** Bold is for defined terms and load-bearing small words, italics for slogans and light emphasis. No exclamation marks, and no "Note that" at the start of every other sentence.
- **Names.** Name results by content, with `@label`. Titles of named theorems match exactly so the dependency graph picks up mentions.
- **Promises.** Every forward promise ("we will see in @sec..." or "in Chapter 8") must be paid off. Keep a list of unpaid promises in `authoring/STATUS.md` as you write.
- **Spelling.** American spelling: "normalize", "color", "behavior", "center". Mathematical names keep their accents and en dashes (Cauchy-Schwarz with an en dash). Fix the hyphenation of any prefix the book uses often ("non-zero" or "nonzero") once, here, and then never argue about it again.
- **Math delimiters.** `\( ... \)` inline and `\[ ... \]` display, never `$` (except inside TikZ and inside `\tag{$\ast$}`). Numbered equations take `{#eq-slug}` **on the same line as the closing `\]`, with no space** (`\]{#eq-slug}`), and are cited with `@eq-slug`; on its own line, or after a blank line, the label is just text.
- **Relation symbols are typeset, never plain characters.** Write `\( \Rightarrow \)`, `\( \subseteq \)`, `\( \in \)`, `\( \le \)`, not the unicode characters -- including proof-direction tags `\( (\Rightarrow) \)` and chains such as `(a) \( \Rightarrow \) (b)`. A non-ASCII character inside a math span is dropped by pdflatex with no error, and `tests/test_display_math_source.py` fails the build over it. (An arrow used rhetorically in ordinary prose stays plain.)
- **Displays must fit the text column.** A formula wider than about 60 characters of ordinary math should be broken with `aligned`, `split` or `cases` inside `\[ ... \]`, aligned at `=` or at a natural operator, rather than left to overflow. See `authoring/measure-displays.md`.
- **Never leave a blank line inside a display.** Pandoc parses `\[ ... \]` only as one paragraph; a blank line ends it early and the display becomes literal text in the PDF. `tests/test_display_math_source.py` catches this too.
- **Macros** are in `latex/macros.tex`; use those listed in `NOTATION.md`. Define nothing ad hoc. If a new macro is needed, add it to `macros.tex` and `NOTATION.md`.

## 8. Authoring syntax reference

The live version of this reference is the demo section shipped with the template,
`src/ch00-demo/01-every-environment.md`: it uses every environment the config declares,
with a line above each saying what it is for. Read the source next to the built page.

```markdown
::: {#thm-slug}
[Name of the Theorem]

Let \( V \) be ...
:::

::: {.idea}
We want ...
:::

::: {.proof}
Let ...  This proves the theorem.
:::
```

- **Environment prefixes:** `thm`, `lem`, `cor`, `prp` (shared counter); `def`; `exm`; `exr`; `cnj`. Small blocks with no label: `.proof`, `.proofofclaim`, `.solution`, `.remark`, `.claim`, `.idea`, `.warning`, `.check`, `.algorithm`.
- **Labels** are lowercase-hyphenated and describe content (`thm-steinitz-exchange`, not `thm-3`). They are global across the book and must be unique.
- **References:** `@thm-slug` renders as "Theorem 3.12" with a hover preview; `@eq-slug` works for equations.
- **Labeled lists:** `::: {.enumerate options="label=(V\arabic*)"}` wraps an ordered list.
- **Web-only content:** `::: {.content-visible when-format="html"}`.
- **A proof under its own heading** must name its result: `::: {.proof of="thm-slug"}`. The dependency scanner credits a proof to the labeled result before it and resets at every heading, so a proof placed after a heading otherwise belongs to nothing. `tests/test_proof_ownership.py` fails the build over it.

## 9. Before handing a section back

- [ ] Every definition is preceded by its need. Major notions follow §3 in full.
- [ ] Every proof cites only earlier results, and every step names its reason. Nothing in the text rests on an exercise.
- [ ] Every result is proved, or plainly marked as not proved here.
- [ ] Every example's arithmetic is verified.
- [ ] There is at least one Quick check (its solution a sibling block after it), one warning and one non-example. The exercises have A, B and C groups, each exercise with a complete solution.
- [ ] Every B-type task has a worked example in the text.
- [ ] Notation matches `NOTATION.md`. No symbol is used before it is introduced, and none is reused with a new meaning.
- [ ] Labels are unique (grep `src/`), and every `@ref` target exists or is created in this chapter.
- [ ] The section title carries no mathematics.
- [ ] `./build.py html` on the section produces no new warnings.
- [ ] No copied text or examples from any reference.
