# Fitch derivations for tests/test_fitch_html.py

Each section holds one raw LaTeX block; the tests split the HTML at the headings.
fitch-book.sty here is a copy of the Foundations book's (its rule macros are read from it).

## plain {#plain}

```{=latex}
\begin{center}
$\begin{nd}
  \hypo {1} {P \wedge Q}
  \have {2} {P} \ae{1}
  \have {3} {a < b}
\end{nd}$
\end{center}
```

## nested {#nested}

```{=latex}
\begin{center}
$\begin{nd}
  \hypo {1} {P \to Q}
  \hypo {2} {Q \to R}
  \open
  \hypo {3} {P}
  \have {4} {Q}  \ie{1,3}
  \open
  \hypo {5} {S}
  \have {6} {R}  \ie{2,4}
  \close
  \have {7} {S \to R} \ii{5-6}
  \close
  \have {8} {P \to (S \to R)} \ii{3-7}
\end{nd}$
\end{center}
```

## siblings {#siblings}

```{=latex}
\begin{center}
$\begin{nd}
  \hypo {1} {P \vee Q}
  \open
  \hypo {2} {P}
  \have {3} {Q \vee P} \oi{2}
  \close
  \open
  \hypo {4} {Q}
  \have {5} {Q \vee P} \oi{4}
  \close
  \have {6} {Q \vee P} \oe{1,2-3,4-5}
\end{nd}$
\end{center}
```

## flagged {#flagged}

```{=latex}
\begin{center}
$\begin{nd}
  \hypo {1} {\exists x\, P(x)}
  \hypo {2} {\forall x\, (P(x) \to Q(x))}
  \open[x_0]
  \hypo {3} {P(x_0)}
  \have {4} {P(x_0) \to Q(x_0)} \Ae{2}
  \have {5} {Q(x_0)} \ie{4,3}
  \have {6} {\exists x\, Q(x)} \Ei{5}
  \close
  \have {7} {\exists x\, Q(x)} \Ee{1,3-6}
  \open
  \hypo {8} [y_0] {P(y_0)}
  \have {9} {P(y_0)} \r{8}
  \close
  \open
  \guard{z_0}
  \have {10} {z_0 = z_0} \eqi{}
  \close
\end{nd}$
\end{center}
```

## by {#by}

```{=latex}
\begin{center}
$\begin{nd}
  \hypo {1} {a < b}
  \hypo {2} {b < c}
  \have {3} {a < c} \by{Tr}{1,2}
  \have {4} {a < c + 1} \by{arith, $x \le y$}{3}
  \have {5} {c > a} \by{Flip\ 3}{}
  \have {6} {c > a} \by{}{5}
\end{nd}$
\end{center}
```

## rules {#rules}

```{=latex}
\begin{center}
$\begin{nd}
  \have {1} {A} \ai{1}
  \have {2} {A} \ae{1}
  \have {3} {A} \ii{1}
  \have {4} {A} \ie{1}
  \have {5} {A} \oi{1}
  \have {6} {A} \oe{1}
  \have {7} {A} \ni{1}
  \have {8} {A} \ne{1}
  \have {9} {A} \be{1}
  \have {10} {A} \raa{1}
  \have {11} {A} \bi{1}
  \have {12} {A} \bie{1}
  \have {13} {A} \Ai{1}
  \have {14} {A} \Ae{1}
  \have {15} {A} \Ei{1}
  \have {16} {A} \Ee{1}
  \have {17} {A} \eqi{1}
  \have {18} {A} \eqe{1}
  \have {19} {A} \r{1}
  \have {20} {A} \nni{1}
  \have {21} {A} \nne{1}
  \have {22} {A} \mt{1}
  \have {23} {A} \lem{1}
  \have {24} {A} \ds{1}
  \have {25} {A} \dm{1}
  \have {26} {A} \ctp{1}
\end{nd}$
\end{center}
```

## expect-invalid {#expect-invalid}

```{=latex}
\begin{center}
% expect-invalid: a deliberately flawed derivation
$\begin{nd}
  \hypo {1} {P \to Q}
  \have {2} {P} \ie{1} % cites one line only
\end{nd}$
\end{center}
```

## schema {#schema}

```{=latex}
% schema
\begin{center}
$\begin{nd}[schema]
  \open[x_0]
  \have {i} {\vdots}
  \have {j} {\varphi[x_0/x]}
  \close
  \have {k} {\forall x\, \varphi} \Ai{i-j}
\end{nd}$
\qquad
$\begin{nd}
  \have[i][0] {i} {\varphi}
  \have {i1} {\psi} \r{i}
  \have[\ ][0] {} {\vdots}
  \have[][7] {7} {\chi} \by{?}{}
\end{nd}$
\\[2ex]
$\begin{nd}
  \hypo {1} {x < y}
\end{nd}$
\end{center}
```

## fallback {#fallback}

```{=latex}
\begin{center}
Prose next to a derivation: $\begin{nd}
  \have {1} {P}
\end{nd}$
\end{center}
```

## continuation {#continuation}

```{=latex}
\begin{center}
$\begin{nd}
  \have {1} {P \wedge Q}
  \havecont {\wedge R}
\end{nd}$
\end{center}
```

## tikz {#tikz}

```{=latex}
\begin{tikzpicture}
  \draw (0,0) -- (1,1);
\end{tikzpicture}
```
