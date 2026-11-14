# BMO-006: A fifth exact branching-canopy transition at depth five

**Status:** Reproducible exact-arithmetic convex-hull certificate (2026-11-14).  
**Research sequence:** [BMO-001](README.md) · [BMO-002](EXACT-LATTICE-60.md) · [BMO-003](EXACT-ANGLE-REGIMES.md) · [BMO-004](EXACT-DEPTH3-REGIMES.md) · [BMO-005](EXACT-DEPTH4-RECURSIVE.md)  
**Domain:** Five expansions of the *unchanged* grammar `F -> F[+F]F[-F]F`, unit line length, initial heading upward, and `0° < θ < 90°`. Only the **convex hull of drawn endpoints** is classified, not the internal crossing structure, line thickness or botany.

## Main finding

Depth five has exactly **five** distinct convex-hull transition angles in the open angle domain. In order of increasing θ:

| Angle | Exact cosine | Vertex count at equality |
| --- | --- | ---: |
| `arccos(sigma) ≈ 22.309473247°` | sigma, defined below | 8 |
| `arccos(rho) ≈ 29.465468°` | unique cubic root in (0.87,0.88) | 7 |
| `arccos(alpha) ≈ 42.957378°` | `(2+√46)/12` | 6 |
| 60° | 1/2 | 5 |
| `arccos(1/4) ≈ 75.522488°` | 1/4 | 4 |

Between transitions, the strict hull vertex counts are **9, 8, 7, 6, 5, 4**. Every previously certified transition from depths two, three and four persists in depth five, and one new angle appears.

The new angle is defined using the **unique root sigma in (23/25,93/100)** of

```text
Q(c) = 864c^4 - 288c^3 - 696c^2 + 136c + 65.
```

The corresponding exact collinearity equation for endpoints (0,2344,2345) is

```text
cross(point0, point2344, point2345)
  = sin(theta) * 3Q(cos(theta)).
```

The root is approximately `sigma = 0.925146966707`, giving `theta ≈ 22.309473247°`. This is an algebraic definition, not an angle fitted by repeated sampling.

## What changed computationally

Depth five draws **3,125 line segments**, with **3,126 first-seen symbolic endpoints**. BMO-005 established that each depth is exactly five affine copies of the previous one, and that convex hull commutes with affine transformations and union-hull.

For every angle interval where the depth-four hull is known, the code forms only the five transformed images of the **previous hull's extreme vertices**. These are enough to reconstruct the next hull, because every other point in each copy lies within that transformed hull.

On the eight proof subintervals (six distinct hull regimes; two rational subdivisions only to separate algebraic fields), there are 16–36 distinct recursive candidates. The exact certificate checks:

- **1,659** edge-to-candidate half-plane constraints;
- **54** strictly convex adjacent-corner orientation constraints;
- all **five algebraic transition points** with an independent exact convex-hull algorithm on a recursively sufficient candidate set.

A naive all-endpoint check of the same eight polygons would require **168,804** containment inequalities (`3,126 × 54`). The recursive method removes **99.02%** of those inequalities. This is **not** a claim of equivalent wall-clock speedup: algebraic operations, especially quartic sign decisions, are more expensive than numerical tests.

| Cosine interval | Recursive candidates | New hull vertices | Containment checks |
| --- | ---: | ---: | ---: |
| (0, 1/4) | 16 | 4 | 64 |
| (1/4, 1/2) | 21 | 5 | 105 |
| (1/2, alpha) | 26 | 6 | 156 |
| (alpha, 3/4) | 31 | 7 | 217 |
| (3/4, rho) | 31 | 7 | 217 |
| (rho, 23/25) | 36 | 8 | 288 |
| (23/25, sigma) | 36 | 8 | 288 |
| (sigma, 1) | 36 | 9 | 324 |
| **Total** | | | **1,659** |

Neither `3/4` nor `23/25` is a geometric transition. They let each algebraic interval use one exact number field at a time, avoiding a larger compositum of quadratic, cubic and quartic fields.

## Exact certificate method

BMO-003 expresses each endpoint in integer polynomials of `c = cos(theta)`:

```text
p(theta) = (sin(theta) * X_p(c), Y_p(c)).
```

Its oriented areas factor as `sin(theta) * P(c)`. On `0° < theta < 90°` the sine factor is positive, so polynomial signs alone determine which points lie on each candidate hull's left half-plane.

As before, for each interval `[a,b]` a polynomial `P` is transformed to the homogenized Bernstein form

```text
(1+z)^d * P((a + b*z)/(1+z)), z >= 0.
```

The verifier checks every coefficient is nonnegative in the exact endpoint field. All coefficients nonnegative establish containment over the *entire* closed interval; a strictly positive coefficient for each adjacent-corner orientation polynomial establishes strict convexity in the interior. Thus there is no angle-grid assumption.

The new quartic boundary uses a dedicated exact algebraic-number class:

- Rational polynomials of degree ≤3 in sigma represent elements of `Q(sigma)`; powers are reduced modulo `Q(c)`.
- The original quartic is irreducible over `Q`: its reduction modulo 17 has no degree-one root and no monic degree-two factor. The implementation exhaustively checks all 17 and 289 possibilities respectively.
- The isolator begins at `[23/25,93/100]`. `Q` has opposite signs at the endpoints and its derivative has a strictly positive rational lower bound there, so that interval contains exactly one real root.
- Every nonzero reduced element has nonzero value at that root. Its sign is decided from increasingly narrow **rational enclosures**, using exact interval arithmetic. Failure to separate within the configured precision produces an explicit exception, never a guessed sign.

The verifier checks the complete set of candidate hull half-planes on all eight intervals, exactly reproduces each algebraic boundary hull, and proves the new transition's collinearity equation. It is a finite computational proof **relative to the program's exact arithmetic**, not a kernel-checked formal proof in Lean or Coq.

## Independent tests and commands

Python 3.11+ standard library only:

```bash
python experiments/branching-morphology/depth5_phase.py
python -m unittest discover -s experiments/branching-morphology -p 'test_*.py' -v
```

- [depth5_phase.py](depth5_phase.py) — exact quartic field, rational root isolator, inherited depth-four hull candidate construction, interval positivity certificate and JSON proof record.
- [test_depth5_phase.py](test_depth5_phase.py) — eight new tests. Checks every formal regime, irreducibility modulo 17, exact quartic arithmetic and root isolation, reconstruction of **all 3,126 symbolic endpoints** from five full previous-depth copies, exact full-vs-reduced hull equality at seven rational cosine values, exact collinearity at the new root, and coordinate-by-coordinate agreement with the independent line-drawing turtle across six angles.
- The existing branching-morphology GitHub Actions workflow runs **35 tests** (8 new, 27 previous) on Python 3.11 and 3.13 and writes the exact depth-five certificate as a downloadable JSON artifact.

Observed local suite: **35/35 passed on CPython 3.13.5**. CI and post-merge status are available via the linked pull request/workflow.

## Research interpretation and the next question

From depths two through five, the measured **exact** hull-transition counts are 2, 3, 4 and 5, with all earlier angles persisting. This is evidence for a possible structural law but **does not establish** that the number of transitions at arbitrary depth `n` equals `n`, nor that old transitions always persist. The recursive hull argument ensures candidates can be inherited, not that their extremality cannot change.

One potential next study is to derive a closed recurrence for the polynomial marking each *new* extreme point and to prove that the earlier angles remain transitions for every larger depth. It would be more valuable than merely repeating a numerical search at depth six. A competing path would test whether interior segment intersections break this otherwise orderly outer-hull behavior.

The research remains entirely separate from other repositories' agendas. It concerns the geometry of a deliberately simple formal branching system.
