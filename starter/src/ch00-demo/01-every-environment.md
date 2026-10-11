# Every Environment

This page is the template's reference for authoring. Every environment the config declares — the `big_envs` and `small_envs` of `environment_settings` — appears below at least once, numbered and unnumbered, together with a cross-reference, a plain display, an aligned display, a table, a TikZ figure, a checkpoint and a full A/B/C exercise set with folded solutions. Each block is preceded by one line saying what it is for and what its markup is.

The mathematics is deliberately trivial — even and odd integers — because the page is a demonstration of style and not of content. It is, however, correct: nothing below is hand-waved, and the one fact taken on trust says so in the place it is used.

## Definitions

**Definition** — `::: {#def-slug}` with a `[Title]` on its own first line. Numbered on the `definition` counter, so definitions count separately from theorems. This is the block every new notion goes in; the eleven steps around it are in `authoring/STYLE.md` §3.

::: {#def-even}
[Even and odd]

An integer \( n \) is **even** if \( n = 2k \) for some integer \( k \), and **odd** if \( n = 2k + 1 \) for some integer \( k \).
:::

In words: an even integer is exactly twice something, and an odd integer is one more than twice something. Both clauses quantify over integers \( k \), and in both the \( k \) is allowed to be negative or zero.

**Cross-reference** — `@def-even` renders as a link reading "Definition 0.1.1", with a hover preview on the website. A reference to an unnumbered result reads by title instead: @exm-small-evens below is cited as "Example (The smallest cases)". Every `@ref` must resolve, or `./build.py check` fails.

**Example** — `::: {#exm-slug}`, unnumbered, so it is cited by its title rather than by a number. State the question inside the example and put the worked answer in a `::: {.solution}` after it; the solution starts folded on the website and is printed in full in the PDF.

::: {#exm-small-evens}
[The smallest cases]

Which of \( 0 \), \( 1 \), \( -4 \) and \( 7 \) are even?
:::

::: {.solution}
\( 0 = 2 \cdot 0 \) and \( -4 = 2 \cdot (-2) \), so both are even. For \( 1 \) and \( 7 \) we have \( 1 = 2 \cdot 0 + 1 \) and \( 7 = 2 \cdot 3 + 1 \), so both are odd. Note that \( 0 \) is even: the definition asks for *some* integer \( k \), and \( k = 0 \) is one.
:::

**Quick check** — `::: {.check}`, one short question, with its answer in a `::: {.solution}` placed **after the check block closes**, as a sibling and never nested inside it. Put at least one in every section, right after the idea it tests.

::: {.check}
The definition of "even" asks for an integer \( k \) with \( n = 2k \). Where does it say that \( k \) is unique, and does it need to?
:::

::: {.solution}
It does not say so, and it does not need to. Being even is an existence statement; the definition is satisfied as soon as one such \( k \) is produced. (Uniqueness does hold, since \( 2k = 2k' \) forces \( k = k' \), but nothing below uses it.)
:::

**Warning** — `::: {.warning}`, one misconception and a concrete failing case, one to four sentences. Put it *before* the reader can fall into the trap.

::: {.warning}
"Even" is not the same as "positive and divisible by two". Both \( 0 \) and \( -4 \) are even, and neither is positive. A definition that quietly assumes \( n > 0 \) breaks the very first computation below, where \( k + l \) may be negative.
:::

**Labeled list** — `::: {.enumerate options="label=(P\arabic*)"}` wrapped around an ordinary numbered list. The label format is a LaTeX `enumitem` one, so `(P1)`, `(P2)`, ... come out in both formats and can be referred to in prose.

The two facts about parity that this section proves are:

::: {.enumerate options="label=(P\arabic*)"}
1. the sum of two even integers is even;
2. an integer has an even square exactly when it is itself even.
:::

## Results and proofs

**Lemma** — `::: {#lem-slug}`. Numbered on the `main` counter, which theorems, lemmas, corollaries and propositions all share, so the numbers in a section run 0.1.1, 0.1.2, 0.1.3 whatever the mix.

::: {#lem-even-multiple}
Let \( n \) be an even integer and let \( m \) be any integer. Then \( mn \) is even.
:::

**Proof** — `::: {.proof}`, immediately after the result it proves. The first sentence does mathematics, every step names its reason, and the block ends by saying what has been shown. A proof that sits under its own heading, away from its statement, must name its owner with `::: {.proof of="lem-slug"}`, or `tests/test_proof_ownership.py` fails the build.

::: {.proof}
Since \( n \) is even, @def-even gives an integer \( k \) with \( n = 2k \). Then \( mn = m(2k) = 2(mk) \), and \( mk \) is an integer. Hence \( mn \) meets the definition of even. This proves the lemma.
:::

**Theorem** — `::: {#thm-slug}` with a `[Name]` first line when the result will be cited later. A named result should be cited as `@thm-slug` and not by its name in prose; `./build.py check` warns about a title mentioned without a reference, because a reference gives the reader a link and a hover preview and makes the dependency graph exact.

::: {#thm-sum-of-evens}
[Sum of Evens]

If \( m \) and \( n \) are even integers, then \( m + n \) is even.
:::

**Idea** — `::: {.idea}`, two to six lines of plain prose, placed between the statement and the proof. It carries the discovery: why this route, what the picture is, what the plan is. Omit it for proofs of three lines or fewer; this one is here to show the markup.

::: {.idea}
Both hypotheses are existence statements, so the first move is to name the two integers they hand us. After that the whole proof is one factorization: pulling the \( 2 \) out of \( 2k + 2l \) is exactly what the definition of even asks to see.
:::

**Numbered equation** — `\[ ... \]{#eq-slug}`, with the label on the **same line as the closing `\]` and no space before it**. On its own line, or after a blank line, the label is just text on the page. Cite it with `@eq-slug`.

::: {.proof}
Suppose \( m \) and \( n \) are even. By @def-even there are integers \( k \) and \( l \) with \( m = 2k \) and \( n = 2l \). Then
\[
    m + n = 2k + 2l = 2(k + l)
\]{#eq-sum-of-evens}
and \( k + l \) is an integer, since the integers are closed under addition. So @eq-sum-of-evens exhibits \( m + n \) as twice an integer, which is what it means to be even. This proves the theorem.
:::

This is the payoff sentence a result should end on: @thm-sum-of-evens is the reason the even integers can be added among themselves without ever leaving them, which is the first thing one wants of a set of numbers.

**Corollary** — `::: {#cor-slug}`, sharing the `main` counter with theorems and lemmas.

::: {#cor-even-square}
If \( n \) is an even integer, then \( n^2 \) is even.
:::

::: {.proof}
Apply @lem-even-multiple with \( m = n \). This proves the corollary.
:::

**Aligned display** — a multi-line display uses `aligned` inside `\[ ... \]`, aligned at `=`. Anything wider than about sixty characters of ordinary mathematics should be broken this way rather than left to overflow the text column; `authoring/measure-displays.md` says how to find the ones that still do. Never leave a blank line inside a display: Pandoc ends the paragraph there and the display becomes literal text in the PDF.

Squaring an odd integer \( n = 2k + 1 \) gives

\[
\begin{aligned}
    n^2 &= (2k + 1)^2 \\
        &= 4k^2 + 4k + 1 \\
        &= 2(2k^2 + 2k) + 1,
\end{aligned}
\]

so the square of an odd integer is odd. That is the computation the next proof needs.

**Proposition** — `::: {#prp-slug}`, again on the `main` counter. Use it for a result that is worth numbering and citing but is not a headline.

::: {#prp-square-parity}
[Parity of a Square]

An integer \( n \) is even if and only if \( n^2 \) is even.
:::

::: {.idea}
One direction is @cor-even-square. The other is easier by contraposition: rather than getting from "\( n^2 \) even" to "\( n \) even", we show that an odd \( n \) has an odd square, and then rule out a number that is both.
:::

**Claim and proof of claim** — `::: {.claim}` followed by `::: {.proofofclaim}`, for a genuinely separate fact established inside a longer proof. Both are small blocks and carry no number; `proofofclaim` ends with its own tombstone so the reader can see where the digression closes and the main argument resumes.

**A result used but not proved here** must say so in the place it is used, in one sentence, in plain words. That is the standing rule: a result is either proved from earlier material, or marked plainly as not proved here. There is no third option, and the mark below is what one looks like.

::: {.proof}
\( (\Rightarrow) \) This is @cor-even-square.

\( (\Leftarrow) \) We prove the contrapositive: if \( n \) is odd then \( n^2 \) is not even.

Suppose \( n \) is odd, say \( n = 2k + 1 \) with \( k \) an integer. The aligned computation above gives \( n^2 = 2(2k^2 + 2k) + 1 \), so \( n^2 \) is odd.

::: {.claim}
No integer is both even and odd.
:::

::: {.proofofclaim}
Suppose \( a = 2k \) and \( a = 2l + 1 \) for integers \( k \) and \( l \). Subtracting the second from the first gives \( 2(k - l) = 1 \). Write \( j = k - l \), an integer. If \( j \le 0 \) then \( 2j \le 0 \), and if \( j \ge 1 \) then \( 2j \ge 2 \); neither is \( 1 \). The only possibility left is an integer \( j \) with \( 0 < j < 1 \), and there is none — a fact about the ordering of the integers that we take as known and do not prove here. So there is no such \( a \).
:::

Hence \( n^2 \), being odd, is not even. This proves the contrapositive, and with it the proposition.
:::

**Remark** — `::: {.remark}`, one to three sentences doing exactly one job: the converse fails, another name for the same thing, an outlook.

::: {.remark}
The same argument, with \( 2 \) replaced by any integer \( d \ge 2 \), shows that \( d \) divides \( n^2 \) whenever \( d \) divides \( n \). The converse of *that* is false for \( d = 4 \): take \( n = 2 \).
:::

**Conjecture** — `::: {#cnj-slug}`, unnumbered, for a statement the book states but does not settle. Like an example, it is cited by its title.

::: {#cnj-collatz}
[Collatz]

Start from any positive integer and repeat the step "if it is even, halve it; if it is odd, treble it and add one". Every starting value eventually reaches \( 1 \).
:::

**Algorithm** — `::: {.algorithm}`, a small block for a procedure written as steps rather than as a formula. It carries no number and no tombstone.

::: {.algorithm}
To decide the parity of an integer \( n \) written in decimal:

- read its last digit \( d \);
- if \( d \) is one of \( 0, 2, 4, 6, 8 \), report **even**;
- otherwise report **odd**.

This is correct because \( n \) and \( d \) differ by a multiple of \( 10 \), which is even, so by @thm-sum-of-evens they have the same parity.
:::

## Tables and figures

**Table** — an ordinary Pandoc pipe table. Mathematics inside a cell is written `\( ... \)` as everywhere else. Keep tables narrow: they are set at the text width in both formats.

| \( n \) | \( n \) even? | \( n^2 \) | \( n^2 \) even? |
|---|---|---|---|
| \( -2 \) | yes | \( 4 \) | yes |
| \( -1 \) | no | \( 1 \) | no |
| \( 0 \) | yes | \( 0 \) | yes |
| \( 1 \) | no | \( 1 \) | no |
| \( 2 \) | yes | \( 4 \) | yes |

Every row of the table agrees with @prp-square-parity, as it must.

**Figure** — raw LaTeX: a `tikzpicture` inside a `\begin{center}` block, with a blank line before and after. The PDF uses it directly; the website gets an SVG compiled once by `pdflatex` and cached in `_build/cache/tikz/`. One idea per figure, and color must never be the only thing carrying meaning — here the even integers are both filled and labeled.

\begin{center}
\begin{tikzpicture}[scale=1.0]
  \draw[->] (-3.6,0) -- (3.6,0) node[right] {$n$};
  \foreach \pos in {-3,-2,-1,0,1,2,3} {
    \draw (\pos,0.12) -- (\pos,-0.12);
    \node[below] at (\pos,-0.16) {$\pos$};
  }
  \foreach \pos in {-2,0,2} {
    \filldraw (\pos,0) circle (2.6pt);
    \node[above] at (\pos,0.18) {even};
  }
  \foreach \pos in {-3,-1,1,3} {
    \draw[fill=white] (\pos,0) circle (2.6pt);
  }
\end{tikzpicture}
\end{center}

The filled dots sit two apart, which is the picture behind @def-even: the even integers are the ones reached from \( 0 \) by steps of \( 2 \).

**Web-only content** — `::: {.content-visible when-format="html"}` hides a block from the PDF. Use it for something that only makes sense on a screen; the PDF must never end up with a hole where an explanation was.

::: {.content-visible when-format="html"}
On the website, hovering a reference such as @thm-sum-of-evens shows a preview of the result, the solutions above start folded, and `/` opens search. None of that exists in the PDF, so this paragraph is not printed.
:::

## Exercises

Every section ends with `## Exercises` and three groups under `###` headings. Each exercise is `::: {#exr-<section-slug>-a1}` — unnumbered, cited by its title — whose first line is a title such as `[A1]` or `[B2: Short name]`, followed by a `::: {.solution}` containing a complete answer, not a sketch. Solutions start folded on the website.

### A. Check your understanding

Exactly one exercise, with two to six lettered parts, that a reader should be able to answer before moving on. Parts use `::: {.enumerate options="label=(\alph*)"}`.

::: {#exr-every-environment-a1}
[A1]

::: {.enumerate options="label=(\alph*)"}
1. State the definition of an even integer.
2. Is \( 0 \) even? Justify your answer from the definition.
3. True or false, with a reason: the sum of two odd integers is odd.
:::
:::

::: {.solution}
(a) An integer \( n \) is even if \( n = 2k \) for some integer \( k \) (@def-even).

(b) Yes. Taking \( k = 0 \) gives \( 0 = 2 \cdot 0 \), which is exactly what the definition asks for.

(c) False. If \( m = 2k + 1 \) and \( n = 2l + 1 \) then \( m + n = 2(k + l + 1) \), which is even.
:::

### B. Practice

Two to four exercises like the worked examples, each using one result once.

::: {#exr-every-environment-b1}
[B1]

Determine which of \( -6 \), \( 9 \), \( 100 \) and \( 2k + 4 \) (for an integer \( k \)) are even. Justify your answer.
:::

::: {.solution}
\( -6 = 2 \cdot (-3) \) and \( 100 = 2 \cdot 50 \) are even. \( 9 = 2 \cdot 4 + 1 \) is odd. Finally \( 2k + 4 = 2(k + 2) \) with \( k + 2 \) an integer, so it is even for every \( k \); alternatively, \( 2k \) and \( 4 \) are both even and @thm-sum-of-evens applies.
:::

::: {#exr-every-environment-b2}
[B2: One application]

Let \( n \) be an integer with \( n^2 = 196 \). Show that \( n \) is even.
:::

::: {.solution}
\( 196 = 2 \cdot 98 \), so \( n^2 \) is even. By @prp-square-parity, \( n \) is even. (Indeed \( n = 14 \) or \( n = -14 \).)
:::

### C. Going deeper

One to four exercises that combine two ideas, generalize, or change a hypothesis. A hint, when there is one, goes last and in italics, and names a tool or an object but never a step.

::: {#exr-every-environment-c1}
[C1: Sums of three]

::: {.enumerate options="label=(\alph*)"}
1. Prove that the sum of three even integers is even.
2. Deduce that \( 2a + 2b + 2c \) is even for all integers \( a \), \( b \), \( c \).
:::

*Hint: @thm-sum-of-evens takes two arguments, not three.*
:::

::: {.solution}
(a) Let \( m \), \( n \), \( p \) be even. By @thm-sum-of-evens, \( m + n \) is even. Applying @thm-sum-of-evens again to \( m + n \) and \( p \) shows that \( (m + n) + p \) is even, and addition of integers is associative, so \( m + n + p \) is even.

(b) Each of \( 2a \), \( 2b \), \( 2c \) is even by @def-even, so part (a) applies.
:::

::: {#exr-every-environment-c2}
[C2: Changing the modulus]

Call an integer \( n \) a **triple** if \( n = 3k \) for some integer \( k \).

::: {.enumerate options="label=(\alph*)"}
1. Prove that the sum of two triples is a triple.
2. Determine whether the analogue of @prp-square-parity holds: is \( n \) a triple if and only if \( n^2 \) is one? Prove it or give a counterexample, and say which facts about the integers your argument needs that are not proved in this section.
:::

*Hint: the proof of @prp-square-parity leaned on the claim that no integer is both even and odd. Ask what the corresponding claim says for \( 3 \).*
:::

::: {.solution}
(a) If \( m = 3k \) and \( n = 3l \) then \( m + n = 3(k + l) \), and \( k + l \) is an integer, so the sum is a triple. The argument is word for word the one in @thm-sum-of-evens with \( 2 \) replaced by \( 3 \).

(b) The statement **holds**. Forwards, \( n = 3k \) gives \( n^2 = 3(3k^2) \). Backwards, an integer that is not a triple is \( 3k + 1 \) or \( 3k + 2 \), and

\[
\begin{aligned}
    (3k + 1)^2 &= 3(3k^2 + 2k) + 1, \\
    (3k + 2)^2 &= 3(3k^2 + 4k + 1) + 1,
\end{aligned}
\]

so in both cases \( n^2 \) is one more than a triple, and no integer is both a triple and one more than a triple (same case argument as in the claim above). What the hint points at is the input this needs: that every integer is exactly one of \( 3k \), \( 3k + 1 \), \( 3k + 2 \). That is the division algorithm for \( 3 \), a genuine assumption and not a triviality. The honest write-up names it and says it is not proved here — the same move the proof of @prp-square-parity makes for \( 2 \).
:::
