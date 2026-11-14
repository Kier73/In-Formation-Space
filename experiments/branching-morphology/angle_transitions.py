"""BMO-003: exact convex-hull regimes for the twice-expanded branching grammar.

The geometric coordinates of each endpoint are
    (sin(theta) * X(c), Y(c)), c = cos(theta),
with integer polynomials X, Y. The cross product of three endpoints is
    sin(theta) * P(c), where P is an integer polynomial.

Nonnegative rational Bernstein coefficients over each cosine interval
certify every candidate-hull half-plane inequality for ALL angles in
(0, 90) degrees, not just at sampled values. No third-party packages.
"""

from __future__ import annotations

import json
from fractions import Fraction
from math import comb

Poly = tuple[int, ...]  # ascending powers of c = cos(theta)
Signature = tuple[tuple[int, int], ...]  # (relative heading, step count)
Point = tuple[Poly, Poly]

RULE = "F[+F]F[-F]F"
DEPTH = 2
# Cyclic counterclockwise extreme endpoints. These are the indices returned by
# endpoint_signatures(). The indices identify exact symbolic endpoints, not
# floating-point coordinates. Regime boundaries are represented as cosines.
REGIMES = (
    ("narrow", Fraction(1, 2), Fraction(1), (19, 20, 25, 10, 7, 0)),
    ("intermediate", Fraction(1, 4), Fraction(1, 2), (19, 20, 25, 10, 0)),
    ("broad", Fraction(0), Fraction(1, 4), (20, 25, 10, 0)),
)


def trim(p: tuple[int, ...] | list[int]) -> Poly:
    q = list(p)
    while len(q) > 1 and q[-1] == 0:
        q.pop()
    return tuple(q) if q else (0,)


def add(a: Poly, b: Poly) -> Poly:
    return trim([(a[k] if k < len(a) else 0) +
                 (b[k] if k < len(b) else 0) for k in range(max(len(a), len(b)))])


def mul(a: Poly, b: Poly) -> Poly:
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return trim(out)


def scale(a: Poly, value: int) -> Poly:
    return trim([x * value for x in a])


def sub(a: Poly, b: Poly) -> Poly:
    return add(a, scale(b, -1))


def evaluate(p: Poly, x: Fraction) -> Fraction:
    ans = Fraction(0)
    for value in reversed(p):
        ans = ans * x + value
    return ans


def chebyshev_t(degree: int) -> Poly:
    if degree == 0:
        return (1,)
    prev, curr = (1,), (0, 1)
    for _ in range(1, degree):
        prev, curr = curr, sub(scale(mul((0, 1), curr), 2), prev)
    return curr


def chebyshev_u(degree: int) -> Poly:
    if degree == 0:
        return (1,)
    prev, curr = (1,), (0, 2)
    for _ in range(1, degree):
        prev, curr = curr, sub(scale(mul((0, 1), curr), 2), prev)
    return curr


def endpoint_signatures() -> tuple[Signature, ...]:
    """Enumerate unique algebraic endpoints in first-seen traversal order."""
    word = "F"
    for _ in range(DEPTH):
        word = "".join(RULE if char == "F" else char for char in word)
    heading = 0
    counts: dict[int, int] = {}
    stack: list[tuple[int, dict[int, int]]] = []
    endpoints: dict[Signature, None] = {(): None}
    for char in word:
        if char == "F":
            counts[heading] = counts.get(heading, 0) + 1
            signature = tuple(sorted(counts.items()))
            endpoints[signature] = None
        elif char == "+":
            heading += 1
        elif char == "-":
            heading -= 1
        elif char == "[":
            stack.append((heading, counts.copy()))
        elif char == "]":
            heading, counts = stack.pop()
        else:
            raise ValueError(f"unknown symbol {char!r}")
    assert not stack and heading == 0
    return tuple(endpoints)


def endpoint_polynomials(signature: Signature) -> Point:
    """Exact X,Y for (x,y)=(sin(theta)*X(c),Y(c))."""
    x, y = (0,), (0,)
    for k, multiplicity in signature:
        y = sub(y, scale(chebyshev_t(abs(k)), multiplicity))
        if k:
            x = add(x, scale(chebyshev_u(abs(k) - 1),
                             multiplicity * (1 if k > 0 else -1)))
    return x, y


def oriented_cross(a: Point, b: Point, p: Point) -> Poly:
    """Integer P(c) with Cartesian cross(a,b,p)=sin(theta)*P(c)."""
    return sub(mul(sub(b[0], a[0]), sub(p[1], a[1])),
               mul(sub(b[1], a[1]), sub(p[0], a[0])))


def bernstein_homogenized(p: Poly, lo: Fraction, hi: Fraction) -> tuple[Fraction, ...]:
    """Coefficients of (1+z)^d P((lo+hi*z)/(1+z)), z>=0.

    If they are all >= 0, P(c) >= 0 for every c in [lo,hi]. If a
    coefficient is positive, P(c) > 0 for every c in (lo,hi).
    """
    if lo > hi:
        raise ValueError("invalid interval")
    d = len(p) - 1
    out = [Fraction(0) for _ in range(d + 1)]
    for k, pk in enumerate(p):
        for j in range(k + 1):
            for l in range(d - k + 1):
                out[j + l] += (pk * comb(k, j) * lo ** (k - j) * hi ** j
                              * comb(d - k, l))
    return tuple(out)


def convex_hull_at_cos(points: tuple[Point, ...], c: Fraction) -> tuple[int, ...]:
    """Independent rational hull, since x=positive_factor*X(c)."""
    coords = sorted({(evaluate(x, c), evaluate(y, c), i)
                     for i, (x, y) in enumerate(points)})
    # Keep the earliest identity when algebraically distinct endpoints coincide.
    unique: dict[tuple[Fraction, Fraction], int] = {}
    for x, y, i in coords:
        unique[(x, y)] = min(i, unique.get((x, y), i))
    vertices = [(xy, index) for xy, index in sorted(unique.items())]

    def cross(a: tuple, b: tuple, p: tuple) -> Fraction:
        (ax, ay), (bx, by), (px, py) = a[0], b[0], p[0]
        return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

    lower: list[tuple] = []
    for v in vertices:
        while len(lower) > 1 and cross(lower[-2], lower[-1], v) <= 0:
            lower.pop()
        lower.append(v)
    upper: list[tuple] = []
    for v in reversed(vertices):
        while len(upper) > 1 and cross(upper[-2], upper[-1], v) <= 0:
            upper.pop()
        upper.append(v)
    return tuple(v[1] for v in lower[:-1] + upper[:-1])


def certify() -> dict:
    """Check all constraints, vertex extremality, and exact transitions.

    This computation is an explicit machine-checkable finite certificate.
    Polynomial positivity follows algebraically from nonnegative Bernstein
    coefficients; no sampling or approximate root finder is used.
    """
    signatures = endpoint_signatures()
    points = tuple(map(endpoint_polynomials, signatures))
    assert len(signatures) == 26
    checked = 0
    strict_corners = 0
    results = []
    for name, lo, hi, corners in REGIMES:
        assert len(corners) == len(set(corners))
        assert set(corners).issubset(range(len(points)))
        # Candidate polygon must be genuinely convex at every interior value.
        for i in range(len(corners)):
            a, b, p = (points[corners[(i + offset) % len(corners)]]
                       for offset in range(3))
            cross_poly = oriented_cross(a, b, p)
            coeff = bernstein_homogenized(cross_poly, lo, hi)
            assert any(v > 0 for v in coeff), (name, "corner collinear", i)
            assert all(v >= 0 for v in coeff), (name, "corner negative", i)
            strict_corners += 1
        # Every endpoint lies on the left side of every CCW boundary edge.
        # On a convex polygon, these half-plane conditions imply containment.
        for i, j in zip(corners, corners[1:] + corners[:1]):
            for p in points:
                poly = oriented_cross(points[i], points[j], p)
                coeff = bernstein_homogenized(poly, lo, hi)
                assert all(v >= 0 for v in coeff), (name, i, j, poly, coeff)
                checked += 1
        mid = (lo + hi) / 2
        assert set(convex_hull_at_cos(points, mid)) == set(corners)
        results.append({
            "name": name,
            "cosine_interval_inclusive": [str(lo), str(hi)],
            "open_interval_vertex_count": len(corners),
            "extreme_endpoint_indices_ccw": list(corners),
            "symbolic_extreme_endpoints": [list(map(list, signatures[i])) for i in corners],
        })

    # At 60 degrees, endpoint 7 becomes collinear on edge 10 -> 0.
    first = oriented_cross(points[10], points[7], points[0])
    # At arccos(1/4), endpoint 19 becomes collinear on edge 0 -> 20.
    second = oriented_cross(points[0], points[19], points[20])
    assert first == (-3, 6) and second == (-3, 12)
    assert evaluate(first, Fraction(1, 2)) == 0
    assert evaluate(second, Fraction(1, 4)) == 0
    assert set(convex_hull_at_cos(points, Fraction(1, 2))) == set(REGIMES[1][3])
    assert set(convex_hull_at_cos(points, Fraction(1, 4))) == set(REGIMES[2][3])
    return {
        "experiment": "BMO-003",
        "expansions": 2,
        "angle_domain_degrees": "0 < theta < 90",
        "indeterminate_cosine": "c = cos(theta)",
        "endpoint_count": len(points),
        "regimes": results,
        "transitions": [
            {"angle": "60 degrees", "cosine": "1/2", "vanishing_cross_poly": list(first),
             "vertex_lost": 7, "vertex_count_at_transition": 5},
            {"angle": "acos(1/4) radians", "cosine": "1/4",
             "vanishing_cross_poly": list(second), "vertex_lost": 19,
             "vertex_count_at_transition": 4},
        ],
        "half_plane_constraints_certified": checked,
        "strict_corner_checks": strict_corners,
        "method": "All rational Bernstein coefficients nonnegative over each cosine interval",
        "scope": "Convex-hull vertices only; no assertion about internal intersections or higher depths",
    }


if __name__ == "__main__":
    print(json.dumps(certify(), indent=2))
