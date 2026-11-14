# BMO-004: Three exact canopy-hull transitions at depth three

**Status:** All-angle exact-arithmetic convex-hull classification, with reproducible certificate and independent turtle tests.  
**Date:** 2026-11-14.  
**Source lineage:** [BMO-001](README.md) → [BMO-002](EXACT-LATTICE-60.md) → [BMO-003](EXACT-ANGLE-REGIMES.md).  
**Domain:** The branching grammar `F -> F[+F]F[-F]F`, *three* expansions, unit step length, initially upward heading, and turning angles `0° < θ < 90°`.

## Question

Does increasing the branching depth introduce new *exactly identifiable* geometric transitions, or only more detail inside the same outer silhouette?

**Result:** A new outer-hull transition appears at

```text
theta* = arccos((2+sqrt(46))/12) ≈ 42.9573781627 degrees.
```

The hull has exactly three transitions over the complete angle domain. With `beta = arccos(1/4) ≈ 75.5224878141°`:

| Angular region | Strict convex-hull vertices |
| --- | ---: |
| 0° < θ < theta* | 7 |
| θ = theta* | 6 |
| theta* < θ < 60° | 6 |
| θ = 60° | 5 |
| 60° < θ < beta | 5 |
| θ = beta | 4 |
| beta < θ < 90° | 4 |

The earlier depth-two transitions at 60° and beta **persist** at depth three, while theta* is **new**. These are statements about the *convex hull of the endpoints* only, not all self-intersections or overlap changes of the drawn branches.

## Why the classification is exact

The drawing has `5^3 = 125` line segments and `126` first-seen symbolic endpoints. Each endpoint is a sum of steps at integer multiples of the input turn angle. Writing `c=cos(theta)`, its coordinates are exactly `(sin(theta)*X(c), Y(c))` for integer polynomials `X` and `Y`, built via Chebyshev polynomials (see BMO-003). For any three endpoints a, b, p:

```text
cross(a,b,p) = sin(theta) * P(c),
```

where `P` is an integer polynomial. Since `sin(theta)>0` for `0<theta<90°`, exact signs of `P` determine convexity and containment.

The third angle arises from the collinearity condition of symbolic endpoints 0, 94, 95:

```text
P(c) = -21 - 24c + 72c^2
     = 3(24c^2 - 8c - 7).

P(c)=0 in (0,1) precisely when
c = alpha = (2+sqrt(46))/12.
```

The other transitions have witnesses `-27+54c` at `c=1/2`, and `-27+108c` at `c=1/4`.

The four proposed polygons have 4, 5, 6 and 7 vertices in **increasing order of cosine** (decreasing angle). For *every* edge-to-endpoint triple, a polynomial inequality certifies that the endpoint is inside the candidate hull over the **entire corresponding cosine interval**.

The only irrational boundary is `alpha`. The certificate implements exact arithmetic in the quadratic field `Q(sqrt(46))` using rational coefficients and an exact sign comparison. It converts each polynomial `P(c)` over an interval `[a,b]` into the homogenized Bernstein polynomial

```text
Q(z) = (1+z)^d P((a+b*z)/(1+z)),    z >= 0.
```

For each proposed hull, all coefficients of `Q` are nonnegative for every endpoint-vs-edge constraint; and the three-consecutive-vertex orientation polynomials have at least one positive coefficient. These sufficient conditions prove containment and strict convexity throughout each open interval, without any floating-point interval search.

**Certificate totals:** `126 × (4+5+6+7) = 2,772` polygon half-plane constraints, plus `4+5+6+7 = 22` strict adjacent-corner tests. The implementation also independently builds rational/quadratic-field convex hulls *at the three exact breakpoints*, proving the smaller vertex counts at equality.

### What the proof actually establishes

Each candidate polygon is made from the drawing's endpoints. Strict convexity in the interior, plus inclusion of every endpoint in all its half-planes, means it is **the** exact convex hull. These inequalities cover the complete continuum of c from 0 to 1, with adjacent intervals sharing endpoints. The exact breakpoint hull calculations handle the degenerate collinear cases. Consequently, no other depth-three *convex-hull* transitions occur in the stated angular domain.

The certificate is a transparent computational proof relative to the integer-polynomial generator and its exact arithmetic implementation, **not** a machine-checked formal proof in Lean/Coq. The independent original drawing turtle is compared with the symbolic endpoint interpreter at five sample angles; this checks implementation consistency but is not the basis of the universal interval claim.

## Reproduction

Python 3.11+ standard library only, from the repository root:

```bash
python experiments/branching-morphology/depth3_phase.py
python -m unittest discover -s experiments/branching-morphology -p 'test_*.py' -v
```

The first command emits the exact interval definitions, hull endpoint indices, transition polynomials and certificate counts. The second runs **20 tests**, including five new BMO-004 tests and the existing fifteen tests. The repository's branching-morphology GitHub Actions workflow runs this complete suite on Python 3.11 and 3.13.

Files:
- [depth3_phase.py](depth3_phase.py): symbolic endpoint generator, quadratic-field operations, exact hull builder and complete continuous-interval certificate.
- [test_depth3_phase.py](test_depth3_phase.py): tests quadratic signs, field identities, independently reconstructs the convex hull at exact algebraic boundaries and additional interior points, and compares symbolic endpoints with the original floating-point turtle.
- [angle_transitions.py](angle_transitions.py): reused integer polynomial, Chebyshev and Bernstein primitives from BMO-003.

## Where this points next

Depth two has **two** hull transitions; depth three has **three**, including an algebraic irrational angle. It is too early to infer a growth law for the number or complexity of transitions with depth.

At depth four there are 625 line segments. An interesting next problem is designing an **output-sensitive algebraic hull continuation** algorithm: discover active hull candidates without checking all endpoint triples, then generate exact interval certificates only for the proposed regimes. Such a method could reveal whether the transition sequence has recursively persistent structure.

The same distinctions still matter: the convex hull excludes internal crossings, branch thickness, raster resolution and biological growth. An independent future analysis of the internal line network may have a richer transition space.
