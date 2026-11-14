# BMO-005: Recursive proof of the depth-four canopy transitions

**Status:** Verified executable all-angle convex-hull certificate for the fixed grammar at four expansions.  
**Date:** 2026-11-14.  
**Lineage:** [BMO-001](README.md), [BMO-002](EXACT-LATTICE-60.md), [BMO-003](EXACT-ANGLE-REGIMES.md), [BMO-004](EXACT-DEPTH3-REGIMES.md).  
**Scope:** The convex hull of all endpoints drawn by `F -> F[+F]F[-F]F` after exactly **four** expansions, unit step, initial upward heading, `0° < θ < 90°`.

## Discovery

At depth four, the previous three hull transitions persist and a fourth appears at a smaller angle. With `c=cos(θ)`, define:

- `alpha = (2+sqrt(46))/12 ≈ 0.731860831927`;
- `rho` as the **unique root in (0.87,0.88)** of `144c³ - 48c² - 80c + 11 = 0`.

The angular transition values in increasing angle order are:

| Angle | Exact cosine | Number of hull vertices at the transition |
| --- | --- | ---: |
| arccos(rho) ≈ **29.465468°** | rho ≈ 0.870652318219 | 7 |
| arccos(alpha) ≈ **42.957378°** | (2+sqrt(46))/12 | 6 |
| 60° | 1/2 | 5 |
| arccos(1/4) ≈ **75.522488°** | 1/4 | 4 |

Between them the strict hull vertex counts, in increasing angle order, are **8 → 7 → 6 → 5 → 4**. No additional *outer convex-hull* transitions occur in the given domain. Internal segment intersections and line-density changes are not classified.

A depth-four grammar word has 625 `F` steps and 626 first-seen symbolic endpoints.

## An important numerical failure

An exploratory floating-point convex-hull sweep repeatedly claimed that endpoint 94 appeared and disappeared as an eighth vertex near `cos(θ)=0.73–0.87`. This was an artifact of rounding and a numerical orientation threshold.

The oriented-area polynomial of endpoint triple (0,94,470) is **identically zero**:

```text
cross(point0, point94, point470) = sin(theta) * 0
```

The three points are collinear for **every** angle in the domain, so vertex 94 must not be counted as an independent extreme. This counterexample is retained because it motivates the exact method rather than merely illustrating it.

## Recursive candidate reduction

BMO-003 and BMO-004 checked every endpoint against each proposed convex-hull edge. At depth four, that would take **23,162** exact half-plane inequalities across the chosen intervals.

A stronger method follows directly from the branching grammar. The depth-n drawing comprises five affine copies of the depth-(n−1) drawing:

```text
D_n(theta) = D_(n-1)
  union [a + R_(+theta) D_(n-1)]
  union [a + D_(n-1)]
  union [b + R_(-theta) D_(n-1)]
  union [b + D_(n-1)]

a = (0,-3^(n-1)), b = (0,-2*3^(n-1)).
```

Each copy represents actual branch **points** (including the translated origin), not five unrelated polygon approximations.

Convex hull commutes with a finite union followed by `conv`, and with affine transformations:

```text
conv(union_i A_i S) = conv(union_i A_i conv(S)).
```

Therefore, on a parameter interval where the previous depth's hull vertices are certified, it is sufficient to test **the five affine images of those hull vertices**. BMO-004 already certifies its depth-three hull at all angles. The new code reconstructs those images by shifting integer heading counts (for ±angle rotations) and adding 27 or 54 upward trunk steps. An independent test verifies that transforming **all** depth-three endpoints generates exactly the complete set of 626 depth-four endpoints.

Across the six proof subintervals, the number of **distinct transformed candidate points** is:

| Cosine interval | Previous hull corners | Distinct depth-4 candidates | New hull corners | Containment inequalities |
| --- | ---: | ---: | ---: | ---: |
| (0, 1/4) | 4 | 16 | 4 | 64 |
| (1/4, 1/2) | 5 | 21 | 5 | 105 |
| (1/2, alpha) | 6 | 26 | 6 | 156 |
| (alpha, 3/4) | 7 | 31 | 7 | 217 |
| (3/4, rho) | 7 | 31 | 7 | 217 |
| (rho, 1) | 7 | 31 | 8 | 248 |
| **Total** | | | | **1,007** |

The artificial split at `c=3/4` introduces **no geometric transition**. It separates the quadratic-algebraic and cubic-algebraic interval endpoints, avoiding the need for a compositum field `Q(sqrt(46),rho)` in one positivity test.

The reduction is **95.65% fewer inequalities** than the full-endpoint certificate. It is a reduction in the number of exact geometric checks, not a measured CPU-time speedup; the cubic-field sign operations cost more per check.

## The exact certificate

Every point has coordinates `(sin(theta)*X(c),Y(c))` with integer-polynomial `X,Y`. Each oriented cross product is `sin(theta)*P(c)` for some integer polynomial `P`. Since `sin(theta)>0`, signs of `P` determine half-plane containment and strict hull convexity.

For an interval `[a,b]`, the checker computes the exact homogenized Bernstein polynomial

```text
Q(z) = (1+z)^degree(P) * P((a+b*z)/(1+z))  for z >= 0.
```

When all coefficients are nonnegative, `P(c) >= 0` throughout `[a,b]`. At least one strictly positive coefficient proves the corner orientation is strictly positive on the open interval. The executable certificate verifies **1,007 containment** and **37 corner-orientation** inequalities, using rational, quadratic, or cubic-algebraic coefficients.

The cubic endpoint is represented by polynomials of degree at most two in `rho`, reduced modulo `144rho³ -48rho² -80rho +11`. Signs are determined by exact rational enclosing intervals of the uniquely isolated root; no floating-point approximations are used. The cubic is irreducible over the rationals (it is irreducible modulo 5: its reduction has no root), so a nonzero reduced degree-≤2 polynomial cannot vanish at `rho`. A finite rational interval eventually determines its sign. If the implementation cannot resolve a sign within its precision escalation, it raises an exception rather than claiming success.

Four exact collinearity witnesses fix the boundary angles:

```text
c = 1/4:   -243 + 972c = 0
c = 1/2:    243 - 486c = 0
c = alpha: -189 - 216c + 648c² = 0
c = rho:     33 - 240c - 144c² + 432c³ = 0.
```

At each breakpoint, the complete **626-endpoint hull** is independently reconstructed in its relevant exact algebraic field, obtaining 4, 5, 6 and 7 vertices respectively (listed in increasing cosine order).

These checks plus the depth-three premise certify **every** angle in the open interval, rather than a finite parameter sweep. The argument is a checkable computational proof relative to the included exact arithmetic and the earlier depth-three certificate; it has not been separately formalized in a proof assistant.

## Reproduce and inspect

Run from the repository root with Python 3.11 or 3.13, no third-party packages:

```bash
python experiments/branching-morphology/depth4_phase.py
python -m unittest discover -s experiments/branching-morphology -p 'test_*.py' -v
```

The first command prints a JSON proof summary. The 27-test local suite verifies the cubic root arithmetic and isolator, the irreducibility check modulo 5, the five-copy decomposition, full exact hulls at independently chosen rational cosines and every algebraic breakpoint, the persistent collinearity counterexample, and 626-by-626 indexed symbolic coordinate agreement with the original floating-point turtle at five angles. The recursive certificate is also evaluated by the test suite. GitHub Actions runs tests on two Python versions and retains the depth-four summary as an artifact.

## Next question, still independently motivated

The observed progression—two transitions at depth two, three at depth three, four at depth four—is suggestive **but not a proved general law**. The proof construction does suggest an approach to depth five: recursively carry *only active hull candidates* between regimes, discover potential new collinearities from candidate triples, isolate their algebraic roots, and prove the resulting intervals by exact sign certificates. That is a coherent research question without committing to an expected number of transitions.

The global hull also forgets many internal intersections. A separate and potentially richer exploration would classify internal line arrangements—but it must not be conflated with the proven outer-envelope results.
