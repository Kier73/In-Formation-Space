# BMO-011 — Averaged phase and an asymptotically tight exposure bracket

**Date:** 2026-11-14. **Status:** all-finite-depth mathematical theorem with independent finite audits.  
**Scope:** The outer convex hull of endpoints of `F -> F[+F]F[-F]F`, unit steps, initially upward, with angle `θ` in radians. No claims about internal line intersections, real plants, or an exact all-depth transition count.

This follows [BMO-010](ANGLE-DEPENDENT-SUPPORT-CONE.md), which proved strict origin-to-tip support for `0<θ≤π/(4n)`. BMO-011 changes the order of averaging and testing monotonicity.

## Theorem — a stronger all-depth supporting angle

Let `A_n` denote the nested left tip at endpoint index `(3·5^n+1)/4`, and `O` the origin. For **every finite depth `n≥1`**, the segment `O→A_n` is a strict supporting edge of the convex hull of **all** endpoints whenever

```text
0 < θ <= π/(2n+1).
```

For every endpoint `p` other than `O` or `A_n`,

```text
cross(O,A_n,p) >= (4·3^n/9) sin(θ/2) cos(nθ) > 0.
```

The sufficient interval improves on BMO-010 by the factor `4n/(2n+1)`, tending to **2**. The proof holds for every finite depth; it is not an extrapolation from the previous depth-two-through-six hull certificates.

## Lemma 1 — Nested-tip phasor has phase under half a step

Represent the path of each endpoint as a multiset of integer signed headings `k`, where a step at heading `kθ` contributes `(sin(kθ),−cos(kθ))`. Let `H` be a random heading chosen uniformly from the `3^n` steps of the nested tip, and put `J=−H`.

The exact tip-heading distribution from BMO-010 is

```text
Pr(J=j) = 2/3^(j+1), j=0,...,n−1;
Pr(J=n) = 1/3^n.
Pr(J>=j) = 3^(−j) for j=1,...,n.
E[J] = (1−3^(−n))/2 < 1/2.
```

Define the complex phasor

```text
W_n(θ) = E[exp(iJθ)] = R_n exp(i φ_n).
W_0=1;  W_n=(2+exp(iθ)W_(n−1))/3.
```

For `0<θ≤π/(2n+1)`, every `0≤jθ<π/2`. Consequently `Im(W_n)>0` and `Re(W_n)>2/3` (the zero-heading step probability is 2/3). In particular `R_n≥2/3` and `φ_n>0`.

**Phase lemma:** `φ_n<θ/2`. Use the elementary inequality `sin(mx)≤m sin x` for every positive integer `m` and `0<x<π`. Then

```text
Im(exp(−iθ/2)W_n)
 = E[sin((J−1/2)θ)]
 <= [2E[J]−1] sin(θ/2)
 = −3^(−n) sin(θ/2) < 0.
```

As `φ_n` is in the first quadrant, this proves

```text
0 < φ_n < θ/2.
```

Although individual path headings range down to `−n`, the entire nested-tip distribution averages to a phasor displaced by **less than half a turning step**.

## Lemma 2 — The *averaged* sine kernel remains increasing

For each integer heading `k`, define

```text
g_n(k) = E_H[sin((k−H)θ)]
       = Im(exp(ikθ)W_n)
       = R_n sin(kθ+φ_n).
```

Every endpoint at depth `n` has headings in `[−n,n]`. For adjacent integers `−n≤k≤n−1`,

```text
g_n(k+1)−g_n(k)
 = 2R_n sin(θ/2) cos((k+1/2)θ+φ_n).
```

Since `0<φ_n<θ/2`, the cosine argument has absolute value strictly less than `nθ`. Also `nθ≤nπ/(2n+1)<π/2`. Hence every increment is strictly positive, with the common lower bound

```text
g_n(k+1)−g_n(k) >= M_n(θ)
  := (4/3)sin(θ/2)cos(nθ) > 0.
```

This is the decisive improvement. BMO-010 required `sin((k−h)θ)` to be increasing for every *individual* tip heading `h`, losing roughly a factor of two in the permissible angle. Here only the **tip-averaged** kernel must increase.

## Lemma 3 — First-order stochastic order yields geometric support

Let `K` be a random signed heading drawn from the steps of any other non-origin endpoint `p` of length `T`. BMO-010 proves

```text
Pr(K<=−j) <= 3^(−j) = Pr(H<=−j)  for each integer j>=1.
```

At nonnegative thresholds, the tip's CDF is already one. Thus `H` is first-order stochastically to the left of `K`.

The discrete summation-by-parts identity for the increasing function `g_n`, together with its uniform increment `M_n`, gives

```text
E[g_n(K)]−E[g_n(H')] >= M_n(θ)·(E[K]−E[H']),
```

where `H'` is an independent tip-heading sample. Antisymmetry implies `E[g_n(H')]=E[sin((H'−H)θ)]=0`. For the unit-step turtle vectors, determinant expansion gives

```text
cross(O,A_n,p) = 3^n T E[g_n(K)].
```

Therefore

```text
cross(O,A_n,p) >= M_n(θ)·D_n(p),
D_n(p) := 3^n T(E[K]−E[H]).
```

The exact integer moment cone from [BMO-009](ALL-DEPTH-TIP-EXPOSURE.md) establishes the **sharp gap `D_n(p)≥3^(n−1)`** for all `p` other than `O` or `A_n`. Substitution proves

```text
cross(O,A_n,p)
 >= (4·3^n/9) sin(θ/2) cos(nθ) > 0.
```

Every other endpoint lies strictly on the same side of line `O→A_n`, proving the theorem.

## Corollary — asymptotic location of the *actual first loss*

For `n≥2`, define `τ_n` as the **first loss of strict origin-to-tip support**: the infimum of positive angles `θ∈(0,π/2)` at which another endpoint is no longer strictly to the left of the oriented line `O→A_n`. This is not a claim about the full hull's number of transitions.

The new theorem immediately gives

```text
τ_n >= π/(2n+1).
```

BMO-007 established an exact nested-tip collinearity polynomial `P_n(c)` and its first positive-angle root `θ_n`. The distinct nested endpoint `B_n` satisfies

```text
cross(O,A_n,B_n) = sin(θ_n)P_n(cos θ_n) = 0.
```

So strict support necessarily fails **by** `θ_n`, even if some other point might intervene earlier. Therefore

```text
π/(2n+1) <= τ_n <= θ_n,  for every n>=2.
```

Since BMO-007 proved `nθ_n→π/2`, and `nπ/(2n+1)→π/2`, the squeeze theorem now yields a statement about the **actual** geometry:

```text
lim_(n→∞) nτ_n = π/2.
```

Equivalently, the first loss of the nested tip's strict supporting edge occurs at an angle asymptotic to **90°/n**. It is *not* proved that `τ_n=θ_n` at every finite depth, or that depth `n` has exactly `n` global hull transitions.

## Illustrative angular brackets

| Depth | BMO-010 guarantee | New guarantee | Candidate root upper bound | Lower / upper |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 22.5° | 36.0000° | 75.5225° | 47.7% |
| 4 | 11.25° | 20.0000° | 29.4655° | 67.9% |
| 6 | 7.5° | 13.8462° | 17.9175° | 77.3% |
| 10 | 4.5° | 8.5714° | 9.9917° | 85.8% |
| 100 | 0.45° | 0.8955° | 0.9091° | 98.5% |
| 1000 | 0.045° | 0.089955° | 0.090090° | 99.85% |

Here the candidate root is the **upper bound on loss of strict support**, not a proven exact hull-transition angle at arbitrary depth. The bracket closes relatively regardless of what other branches do.

## Reproducibility

Python 3.11+ standard library only:

```bash
python experiments/branching-morphology/averaged_support.py
python -m unittest discover -s experiments/branching-morphology -p 'test_*.py' -v
```

- [averaged_support.py](averaged_support.py) implements the stable averaged-phasor recurrence, strengthened angular margin, first-loss bracket, and finite audits through depth six.
- [test_averaged_support.py](test_averaged_support.py) adds **10 independent tests** for direct histogram/phasor agreement, averaged sine monotonicity, the complete depth-six endpoint set and original drawing turtle, collinearity upper bound, asymptotic bracket and input checks.
- The local full morphology suite passed **78/78 tests**. The CI workflow runs Python 3.11 and 3.13 and retains the JSON finite audit.

The all-depth theorem and asymptotic conclusion follow from the mathematical derivation; the finite tests are consistency checks, not substitutes for that proof. This is not a Lean/Coq kernel-checked proof, and no relationship with Collatz dynamics is claimed.
