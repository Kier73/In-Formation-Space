# BMO-008 — Exact depth-six transition and an extended all-depth hull sector

**Date:** 2026-11-14. **Status:** exact computational certificate, independent reconstruction tests, and a mathematical induction extending BMO-007.  
**Scope:** The fixed grammar `F → F[+F]F[-F]F`, initially upward with unit segments, depth six, and turning angles `0° < θ < 90°`. All classifications below refer to the **convex hull of endpoints**, not internal segment intersections or biological growth.

This is an independent continuation of [BMO-007](ALL-DEPTH-STABILIZATION.md) and its depth-two through depth-five exact certificates.

## Result: a genuine sixth transition

Let `c=cos(θ)`. Define `lambda` to be the unique real root in `(951/1000, 952/1000)` of

```text
q(c) = 5184c^5 - 1728c^4 - 5472c^3 + 1248c^2 + 1108c - 97.
```

Then the new turning angle is

```text
theta_6 = arccos(lambda) ≈ 17.9175302043 degrees.
```

The earlier five exact hull transitions all persist, at approximately 22.30947°, 29.46547°, 42.95738°, 60° and 75.52249°. Between those six angles the depth-six hull has **10 → 9 → 8 → 7 → 6 → 5 → 4** extreme vertices in increasing angle order.

At each transition the new point is collinear with an existing hull edge; the smaller count applies at the exact transition angle. No other outer-hull transitions exist between 0° and 90° at **depth six**, by the complete interval certificate below.

## How this was certified

There are `5^6 = 15,625` line segments and `15,626` indexed symbolic endpoints. Every endpoint is represented without trigonometric approximations by the polynomials `(sin θ · X(c), Y(c))`, where `X,Y` have integer coefficients derived from Chebyshev polynomials. Every oriented area equals `sin θ · P(c)` for an integer polynomial `P`. The sine is positive in the domain, so the sign of `P` determines hull orientation.

The fixed grammar constructs five affine images of the previous depth. For each previously **certified depth-five hull regime**, only the five transformed images of its convex-hull vertices need to be checked; the other endpoints lie inside those images. The tests independently confirm that five images of the full preceding endpoint set recover *all 15,626 depth-six endpoints*.

Ten closed cosine subintervals, in increasing order, suffice:

| Cosine subinterval | Depth-six vertices in interior | Inherited candidates | Exact containment checks |
| --- | ---: | ---: | ---: |
| (0,1/4) | 4 | 16 | 64 |
| (1/4,1/2) | 5 | 21 | 105 |
| (1/2,alpha) | 6 | 26 | 156 |
| (alpha,3/4) | 7 | 31 | 217 |
| (3/4,rho) | 7 | 31 | 217 |
| (rho,23/25) | 8 | 36 | 288 |
| (23/25,sigma) | 8 | 36 | 288 |
| (sigma,93/100) | 9 | 41 | 369 |
| (93/100,lambda) | 9 | 41 | 369 |
| (lambda,1) | 10 | 41 | 410 |
| **Total** | | | **2,483** |

Here `alpha`, `rho`, and `sigma` are the quadratic, cubic, and quartic transition cosines certified in BMO-004 through BMO-006. The rational subdivisions at `3/4`, `23/25`, and `93/100` are **not geometric transitions**; they avoid mixing algebraic extensions into a larger number field.

For each proposed hull polygon, the code verifies **every inherited candidate on the correct side of every hull edge** throughout the entire interval, plus **73 strict corner-orientation inequalities**. The exact Bernstein transformation

```text
(1+z)^d P((a+b*z)/(1+z)), z >= 0,
```

converts each interval inequality into checking nonnegative coefficients in the relevant exact number field. Nonnegative coefficients guarantee nonnegative values throughout the interval; a positive coefficient guarantees strict positivity inside it.

At all six algebraic transition values, an independent exact convex-hull routine checks the boundary vertex count: **4, 5, 6, 7, 8, 9** in increasing cosine order. Therefore the ten intervals and their shared boundaries classify the entire open angular domain without sampling.

**Proof economy:** The inherited method checks **2,483 containment inequalities** instead of `15,626 × 73 = 1,140,698` using all endpoints. That is **99.782% fewer inequalities**. It is not a measured execution-time improvement.

### Exact quintic arithmetic

The new root is represented by a class of degree-at-most-four rational polynomials in `lambda`, reduced modulo `q`. Its sign is determined from successively narrowed **rational isolating intervals**.

- The isolating interval `(951/1000,952/1000)` has opposite endpoint signs. An explicit positive derivative lower bound proves the root is unique there.
- `q` is irreducible over the rationals: its reduction modulo 7 has **no linear factor** and **no monic quadratic factor**. A reducible degree-five polynomial has a factor of degree ≤2; the source exhaustively checks all 7 linear candidates and all 49 monic quadratic candidates.
- Thus a nonzero reduced polynomial cannot vanish at `lambda`. Exact rational interval evaluation eventually decides its sign; the implementation raises an exception if its configured precision levels do not separate a sign.

The tip's exact collinearity equation is:

```text
cross(point_0, point_11719, point_11720) / sin(theta)
 = 3 q(c)
 = -291 + 3324c + 3744c² - 16416c³ - 5184c⁴ + 15552c⁵.
```

The point indexed 11719 lies inside the depth-six hull before `c=lambda`, becomes collinear at the root, and becomes a **strict extreme vertex** after it. This is not just a root of a candidate polynomial.

## An even stronger all-depth consequence

BMO-007 proved a scale-covariance lemma: if `H_(k+1)(θ)=3H_k(θ)` at an angle, that equality persists for every later depth. BMO-008's first **nine continuous subintervals** have hull vertices that are precisely the scaled old hull vertices. The certificate verifies **63 exact endpoint polynomial correspondences**; by continuity, these equalities also hold at interval endpoints.

Consequently:

```text
H_n(theta) = 3^(n-5) H_5(theta)  for every n>=6
              whenever 0 < cos(theta) <= lambda.

Equivalently, theta_6 <= theta < 90 degrees.
```

Thus **no additional outer-hull transition at a larger angle than theta_6 is possible at any future depth.** The previously established angles are preserved up to scale.

The new transition persists too. On `[lambda,1]`, the exact Bernstein coefficient sign pattern of `3q(c)` is

```text
[0, +, +, +, +, +].
```

For `lambda<c<1`, point 11719 lies strictly outside the old scaled depth-five hull edge from 0 to 11720. Every later grammar expansion embeds all old endpoints scaled by 3, so at every `n>=6` a scaled copy remains outside `3^(n-5)H_5`. On the other side `c<=lambda`, the hull is *exactly* `3^(n-5)H_5`. This establishes a lasting geometric change at `theta_6` independently of its future extreme-vertex count.

**What is not proven:** That every depth `n` has exactly `n` hull transitions. Future new transitions, if any, must occur in the smaller-angle sector `0<theta<theta_6`. The nested-tip recurrence from BMO-007 predicts candidates there, but exposure remains a separate proof obligation.

## Reproduction and independent checks

Python 3.11+ standard library only, from the root of the repository:

```bash
python experiments/branching-morphology/depth6_phase.py
python -m unittest discover -s experiments/branching-morphology -p 'test_*.py' -v
```

- [depth6_phase.py](depth6_phase.py) — exact quintic field, root isolation, inherited candidate construction, ten continuous-interval certificates, boundary hulls, and all-depth stabilization witnesses.
- [test_depth6_phase.py](test_depth6_phase.py) — **seven new tests**, including irreducibility and field arithmetic, five-copy reconstruction of all 15,626 endpoints, eight independently computed exact **full-vs-reduced** rational hulls, the exposed-tip witness, and coordinate-by-coordinate comparison with the original floating-point turtle at five angles.
- The existing GitHub Actions workflow runs the complete morphology test suite on Python 3.11 and Python 3.13 and retains the generated `depth6-certificate.json` proof record.

The local CPython 3.13.5 run passed **49/49 tests**. The interval inequalities are finite computational proof obligations checked by exact rational/algebraic arithmetic; the all-depth conclusion additionally uses the written affine-scaling induction. This is not a Lean/Coq kernel-check.

## The remaining research question

Depths two through six have exactly 2, 3, 4, 5, 6 distinct hull transitions, and all earlier transitions persist. The recurrence in [BMO-007](ALL-DEPTH-STABILIZATION.md) predicts the next candidate at depth seven near **14.9591°**. But merely finding that polynomial's zero is insufficient: another branch may preempt it, or new transitions may occur elsewhere.

The longer-term curiosity is therefore: **Can a structural support-line argument certify exposure of every nested-tip root at arbitrary depth without constructing a finite certificate at each depth?** This would convert a growing family of exact finite examples into a general theorem, or expose where the pattern fails.
