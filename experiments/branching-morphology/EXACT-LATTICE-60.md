# BMO-002: An exact canopy silhouette at a 60° turn

**Status:** An exact integer-arithmetic recurrence and finite induction certificate for a *specific formal branching grammar*.  
**Date:** 2026-11-14  
**Prerequisite:** [BMO-001](README.md); no E-CPU or other research dependency.

## Question

BMO-001 found that the width/height and convex-hull fraction of one generated canopy appeared unchanged across expansion depths at 60°. Was this rounding coincidence or a theorem for that angle?

**Result:** For the rule `F → F[+F]F[-F]F` with a 60° turn and unit steps, every depth **n ≥ 2** has a convex hull exactly equal to a uniform scaling of the depth-2 hull by **3^(n−2)**. Consequently:

- Bounding-box width / height = **1 / √3**.
- Convex-hull area / bounding-box area = **19 / 36**.

These statements concern the geometric envelope, not the number of internal lines, their total length, density, or biological growth. Depths 0 and 1 are exceptions to the stated domain.

## Exact lattice

Represent a Cartesian point by integer coordinates `(u,v)` using

```text
x = sqrt(3)/2 * u
y = 1/2 * v
```

The six unit headings are

```text
(0,-2), (1,-1), (1,1), (0,2), (-1,1), (-1,-1).
```

The ±60° rotations preserve the integer lattice (all reachable points have `u−v` even):

```text
R+(u,v) = ((u−v)/2, ( 3u+v)/2)
R−(u,v) = ((u+v)/2, (−3u+v)/2)
```

Every F at depth n−1 advances the central stem by `s = 3^(n−1)` lattice-unit segments in the initial heading. For the convex hull `H_n` of every endpoint in the n-expansion drawing, define `a_s=(0,−2s)` and `b_s=(0,−4s)`. The expansion rule gives the *exact* recurrence

```text
T_s(P) = conv(
    P
    union (a_s + R+(P))
    union (a_s + P)
    union (b_s + R−(P))
    union (b_s + P)
)
H_n = T_(3^(n−1))(H_(n−1)).
```

Convex hull commutes with these affine images and with taking the hull of a finite union. Hence it is sufficient to transform the vertices of `H_(n−1)`, without tracing every interior endpoint.

## Finite identity and induction

Exact integer enumeration gives the five vertices of `H_2` in counterclockwise order:

```text
(-3,-15), (0,-18), (3,-9), (0,0), (-3,-13).
```

At n=3, `s=9`. The recurrence produces 25 candidate points from five copies of the five vertices of `H_2`. The certificate checks, using only integer cross products, that **all 25 candidates lie inside 3H_2**, and that **all five vertices of 3H_2 occur among them**. Therefore, exactly:

```text
H_3 = T_9(H_2) = 3 H_2.
```

The recurrence is scale-covariant:

```text
T_(3s)(3P) = 3 T_s(P).
```

Suppose `H_n = 3^(n−2) H_2`. Apply this identity repeatedly to the step from n to n+1, using the base equality above. It follows by induction that

```text
H_n = 3^(n−2) H_2   for all n ≥ 2.
```

This induction does **not** rely on inspecting higher finite depths; only the explicitly checkable finite identity, the exact recurrence and its scale covariance are needed. The source additionally cross-checks direct full-word turtle tracing against the hull recurrence at depths 0 through 6.

## Geometric consequences

In lattice coordinates, `H_2` has width 6 and height 18. Its exact doubled shoelace area is 114, so its area is 57. Uniform scaling does not change either ratio:

```text
Area / bounding box = 57 / (6*18) = 19/36.

Cartesian width / height
  = ((sqrt(3)/2)*6) / ((1/2)*18)
  = 1/sqrt(3).
```

The result is exact for the defined grammar and angle, including arbitrarily large theoretical expansion depths. The implementation itself caps explicit expansion/tracing at depth 6 to keep the finite tests economical. At depth 1, the hull/bounding-box fraction is **1/2**, not 19/36.

## Reproduce and scrutinize

From the repository root:

```bash
python experiments/branching-morphology/lattice60.py
python -m unittest discover -s experiments/branching-morphology -p 'test_*.py' -v
```

Files:
- [lattice60.py](lattice60.py) — two independent finite hull constructions, exact rotations, polygon half-plane checks, rational area fraction, and certificate output.
- [test_lattice60.py](test_lattice60.py) — independent full-word comparison, rotation tests, depth sweep and counterexample.

**Limit of the result:** The theorem is specific to the 60° angle, this branching rule, unit steps and its convex hull. It says nothing about whether two canvases look identical internally, overlap counts, rasterized ink coverage, or real plant morphogenesis. A similar near-constant ratio at other angles should be investigated separately, not extrapolated from this proof.
