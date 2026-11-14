# BMO-007: All-depth hull stabilization and nested-tip angle recurrence

**Date:** 2026-11-14. **Status:** Mathematical all-depth induction, anchored in executable exact-arithmetic interval certificates; an independent recurrence for future candidate collinearities.  
**Scope:** The planar convex hull of the grammar `F -> F[+F]F[-F]F`, unit segments, initial heading upward, turn angle `0° < θ < 90°`. This does not classify the internal line arrangement or growth in living plants.

This follows [BMO-003](EXACT-ANGLE-REGIMES.md), [BMO-004](EXACT-DEPTH3-REGIMES.md), [BMO-005](EXACT-DEPTH4-RECURSIVE.md) and [BMO-006](EXACT-DEPTH5-RECURSIVE.md). The intention is to explain **why** earlier transitions persist rather than simply count another finite depth.

## Theorem 1: Once an envelope scales, it keeps scaling

Write `E_n(θ)` for the endpoints after depth `n`, and `H_n(θ)=conv(E_n(θ))` for their convex hull.

For fixed `θ`, define the five-copy hull operator

```text
T_(s,θ)(K) = conv(
    K
    union ((0,-s) + R_(+θ) K)
    union ((0,-s) + K)
    union ((0,-2s) + R_(-θ) K)
    union ((0,-2s) + K)
).
```

The exact grammar gives

```text
H_(n+1) = T_(3^n,θ)(H_n).
T_(3s,θ)(3K) = 3 T_(s,θ)(K).
```

**Homothety absorption:** For any angle, if `H_(k+1)=3H_k`, then

```text
H_m = 3^(m-k) H_k   for every m >= k.
```

*Proof.* From the hypothesis,

```text
H_(k+2) = T_(3^(k+1),θ)(3H_k)
        = 3 T_(3^k,θ)(H_k)
        = 3H_(k+1).
```

Repeat the argument inductively. The proof concerns the **entire convex polygon**, not only its height, width or vertex count.

**Scaled endpoint embedding:** Replacing an old `F` draws five new `F` segments but displaces the turtle by exactly three units in the old heading. Its pre-existing endpoint after segment `i` is therefore found at new index `5i`, scaled by three. Thus, at every depth and every angle,

```text
3 E_n ⊆ E_(n+1) and 3 H_n ⊆ H_(n+1).
```

These are general substitution identities, not numerical observations.

## Theorem 2: A complete infinite-depth angular sector

Let `c=cos(θ)`. Define the previously proven algebraic constants:

- `alpha=(2+sqrt(46))/12`;
- `rho`: unique root of `144c³−48c²−80c+11` in `(0.87,0.88)`;
- `sigma`: unique root of `864c⁴−288c³−696c²+136c+65` in `(0.92,0.93)`.

The exact interval certificates from BMO-003 through BMO-006, plus **15 independent polynomial comparisons** between their corresponding hull corners, verify the following *one-step identities throughout continuous angle intervals*:

| Cosine region | Finite certified identity | Valid for every later depth |
| --- | --- | --- |
| `0<c<=alpha` | `H_3=3H_2` | `H_m=3^(m−2)H_2` for all `m≥3` |
| `0<c<=rho` | `H_4=3H_3` | `H_m=3^(m−3)H_3` for all `m≥4` |
| `0<c<=sigma` | `H_5=3H_4` | `H_m=3^(m−4)H_4` for all `m≥5` |

The certificate checks all **89** corresponding extreme-vertex polynomial identities across the 15 intervals. The premises are not samples: the previous certificates prove their vertex sets on the entire open parameter intervals, and continuity of finite convex hulls carries the homothety identity to their shared endpoints.

**Consequently, for every finite depth `m≥5` and every angle `arccos(sigma) ≤ θ < 90°`,**

```text
H_m(θ) = 3^(m−4) H_4(θ).

arccos(sigma) ≈ 22.309473247°.
```

No additional convex-hull changes can occur at a **larger angle** at any future depth. The earlier four phase changes (at `arccos(rho)`, `arccos(alpha)`, 60°, and `arccos(1/4)`) are reproduced at every future depth, with no change in their geometric hull types except uniform scaling.

### The newest transition also persists, without a vertex-count assumption

At depth five, the old scaled-depth-four hull has an edge from endpoint 0 to endpoint 2345. Endpoint 2344 is collinear with it at `c=sigma`. Its exact oriented-area polynomial is

```text
cross(point0, point2344, point2345) / sin(θ)
  = 195 +408c −2088c² −864c³ +2592c⁴.
```

The exact Bernstein coefficient signs over `[sigma,1]` are **[0,+,+,+,+]**. Therefore point 2344 lies **strictly outside** the old edge for `sigma<c<1`. The endpoint embedding keeps a scaled copy of this point at *every later depth*, forcing

```text
H_m = 3^(m−4)H_4           when 0<c<=sigma,
H_m strictly contains
       3^(m−4)H_4         when sigma<c<1, for every m>=5.
```

Because each fixed-depth hull is generated from finitely many analytic endpoint curves, this departure at `sigma` requires a change in its extreme-face/vertex description. Thus the **fifth** previously certified transition remains a genuine geometric transition at every later depth. We do **not** assert that it must add exactly one vertex after depth five.

It remains possible for additional changes to appear in the as-yet-unclassified sector `sigma<c<1` (angles *smaller* than about 22.31°).

## Theorem 3: A closed recurrence for the potential next tip

Number the drawn line segments at depth `n` from 1 to `5^n`, with the origin at endpoint index 0. Define

```text
a_n = (3*5^n+1)/4,
A_n = endpoint a_n,
B_n = endpoint a_n+1.
```

At depths 2–5 these are the consecutive pairs `(19,20)`, `(94,95)`, `(469,470)`, `(2344,2345)`. The index formula follows by induction from the five-symbol rewrite.

Let `v_(-j)=(-sin(jθ),-cos(jθ))` denote a unit step at relative heading `−jθ`. Reading this nested branch from the grammar gives, for `n≥2`,

```text
B_n = Σ_(j=0..n−2) 2*3^(n−1−j) v_(-j) + 3 v_(-(n−1))
A_n = B_n + v_(-n) − v_(-(n−1)).
```

For `n=1`, `B_1=3v_0` and the second equation still holds. Let `U_j(c)` be a Chebyshev polynomial of the second kind, with `U_(−1)=0`. Using the exact identity `sin((j+1)θ)=sin(θ)U_j(cosθ)`, determinant expansion yields

```text
P_n(c) := cross(0,A_n,B_n)/sin(θ)
        = 3 + 2 Σ_(j=1..n−1) 3^j (U_j(c) − U_(j−1)(c)).

P_(n+1) − P_n = 2*3^n (U_n − U_(n−1)).

P_(n+1) = (1+6c)P_n − (9+6c)P_(n−1) + 9P_(n−2)
            for n>=3.
```

The last is a third-order linear recurrence in the depth index. These are **exact polynomial identities for every depth**. The executable tests reconstruct `P_n` independently from the literal symbolic endpoint positions at depths 1 through 5; they reproduce the established linear, quadratic, cubic and quartic transition witnesses.

**Caution:** A root of `P_n` means three nested-tip endpoints are collinear. It does *not* automatically mean that endpoint is exposed on the global convex hull. That extra claim has been proven only for the relevant roots at depths 2–5.

## The candidate angles decrease and obey an asymptotic law

For angles in radians define

```text
Q_n(θ) = cos(θ/2) P_n(cosθ) / 3^n.

Q_1(θ) = cos(θ/2).
Q_(n+1)(θ) = (2/3) cos((n+1/2)θ) + (1/3) Q_n(θ).
```

This is a finite mixture of cosine terms with **positive geometric weights**. Its leading term has weight 2/3; all remaining weights sum to 1/3. For `n≥2` the mixture is strictly decreasing on `(0,π/(n−1/2))`: all its component arguments lie strictly between 0 and π there. The leading cosine reaches −1 at that interval's upper end, ensuring the whole mixture is ≤−1/3; it starts at +1.

Hence each `Q_n` has a unique **first positive zero** `θ_n` in this interval. The `n=2` root also lies below 90° by direct evaluation at π/2. Moreover:

- For `θ ≤ π/(2n−1)` every cosine term is nonnegative, so `θ_n > π/(2n−1)`.
- At `θ_n`, the recurrence gives `Q_(n+1)(θ_n)=(2/3)cos((n+1/2)θ_n)<0`. The cosine is negative because its argument lies in `(π/2,3π/2)` (the `n=2` upper estimate is handled directly).
- Since `Q_(n+1)(0)=1`, its first root must occur earlier: **`θ_(n+1)<θ_n` for all `n≥2`**.

For fixed `x`, the weighted cosine representation of `Q_n(x/n)` has a truncated geometric offset with weighted expected offset at most one. Applying the 1-Lipschitz cosine inequality gives a *rigorous uniform estimate*

```text
|Q_n(x/n) − cos(x)| <= x/n      for x>=0.
```

Therefore `Q_n(x/n)→cos(x)` uniformly on compact intervals, and its first root satisfies

```text
n*θ_n -> π/2.
```

Angles in this formula are in radians. In degrees, the candidate first root approaches **90°/n** asymptotically.

| Depth | Candidate angle, degrees | Status |
| ---: | ---: | --- |
| 2 | 75.52248781 | Certified outer-hull transition |
| 3 | 42.95737816 | Certified outer-hull transition |
| 4 | 29.46546822 | Certified outer-hull transition |
| 5 | 22.30947325 | Certified outer-hull transition |
| 6 | 17.91753020 | **Algebraic candidate, not yet a hull certificate** |
| 7 | 14.95911930 | **Algebraic candidate, not yet a hull certificate** |

Thus the candidate sequence has a true general recurrence, strict ordering, and an asymptotic law, even though an exact all-depth **number of hull transitions** remains unproved.

## Reproduce, verify, and continue

Python 3.11+ standard library only, from the repository root:

```bash
python experiments/branching-morphology/all_depth_law.py
python -m unittest discover -s experiments/branching-morphology -p 'test_*.py' -v
```

- [all_depth_law.py](all_depth_law.py) reruns all four prior exact certificates, checks **15** inherited interval hull identities, **89** exact vertex polynomial identities and every embedded endpoint up to depth five, proves the latest transition's exact outside witness, and emits the recurrence evidence.
- [test_all_depth_law.py](test_all_depth_law.py) tests the nested endpoint signature formula, exact determinant polynomials and recurrence, monotonic first-root illustrations, the uniform convergence bound, and rejection of invalid parameters.
- The GitHub Actions workflow regenerates and retains the complete JSON prerequisite certificate on Python 3.11 and 3.13.

**Verification distinction:** The program provides finite, exact-arithmetic premises. The induction and recurrence algebra above are the arguments for *all* depths. This is not a formally kernel-checked Lean/Coq proof, and tests alone would not justify universal claims. The work has no dependencies on E-CPU or other neighboring research programs.

The most interesting unanswered question is not simply “what happens at depth six?” It is: **When does a zero of this nested-tip recurrence remain a new exposed extreme point, and could another branch family overtake it?** That question is retained as an open research direction rather than resolved by extrapolation.
