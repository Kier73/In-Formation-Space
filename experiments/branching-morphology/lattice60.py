"""Exact triangular-lattice certificate for the 60-degree branching grammar.

Coordinates (u, v) represent Cartesian (sqrt(3)/2*u, v/2).
No floating-point operations enter the hull computation or proof certificate.
"""

from __future__ import annotations

import json
from fractions import Fraction

# Up, up/right, down/right, down, down/left, up/left.
DIRECTIONS = ((0, -2), (1, -1), (1, 1), (0, 2), (-1, 1), (-1, -1))
Point = tuple[int, int]


def rotate60(point: Point, sign: int) -> Point:
    """Exact plus or minus 60-degree rotation in lattice coordinates."""
    u, v = point
    if (u - v) % 2 or sign not in (-1, 1):
        raise ValueError("invalid lattice point parity or rotation sign")
    if sign == 1:
        return (u - v) // 2, (3 * u + v) // 2
    return (u + v) // 2, (-3 * u + v) // 2


def convex_hull(points: list[Point] | tuple[Point, ...]) -> tuple[Point, ...]:
    """Monotone-chain convex hull in integer arithmetic, CCW from leftmost."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return tuple(pts)

    def cross(o: Point, a: Point, b: Point) -> int:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    upper: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return tuple(lower[:-1] + upper[:-1])


def trace_points(word: str) -> tuple[Point, ...]:
    """Independent lattice turtle for cross-checking the hull recurrence."""
    u = v = turn = 0
    points: list[Point] = [(0, 0)]
    stack: list[tuple[int, int, int]] = []
    for token in word:
        if token == "F":
            du, dv = DIRECTIONS[turn % 6]
            u, v = u + du, v + dv
            points.append((u, v))
        elif token == "+":
            turn += 1
        elif token == "-":
            turn -= 1
        elif token == "[":
            stack.append((u, v, turn))
        elif token == "]":
            if not stack:
                raise ValueError("unmatched closing bracket")
            u, v, turn = stack.pop()
        else:
            raise ValueError(f"invalid token {token!r}")
    if stack:
        raise ValueError("unmatched opening bracket")
    return tuple(points)


def step_candidates(previous: tuple[Point, ...], central_length: int) -> tuple[Point, ...]:
    """Vertices of the five affine images in the exact substitution step."""
    if central_length < 1:
        raise ValueError("central_length must be positive")
    a = (0, -2 * central_length)
    b = (0, -4 * central_length)
    points = list(previous)
    for offset, rotation in ((a, 1), (a, 0), (b, -1), (b, 0)):
        for point in previous:
            rotated = rotate60(point, rotation) if rotation else point
            points.append((offset[0] + rotated[0], offset[1] + rotated[1]))
    return tuple(points)


def hull_step(previous: tuple[Point, ...], central_length: int) -> tuple[Point, ...]:
    """Exact convex hull of five affine copies of the previous-stage hull.

    Convex hull commutes with affine transformation and finite union-hull,
    so interior endpoints are unnecessary for this recurrence.
    """
    return convex_hull(step_candidates(previous, central_length))


def inside_convex_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    """Containment by CCW integer half-plane inequalities, boundary included."""
    if len(polygon) < 3:
        raise ValueError("polygon needs at least three vertices")
    return all((b[0] - a[0]) * (point[1] - a[1]) -
               (b[1] - a[1]) * (point[0] - a[0]) >= 0
               for a, b in zip(polygon, polygon[1:] + polygon[:1]))


def hull_at_depth(depth: int) -> tuple[Point, ...]:
    if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 6:
        raise ValueError("depth must be an integer from 0 to 6")
    hull: tuple[Point, ...] = ((0, -2), (0, 0))
    for n in range(1, depth + 1):
        hull = hull_step(hull, 3 ** (n - 1))
    return hull


def area_fraction(hull: tuple[Point, ...]) -> Fraction | None:
    if not hull:
        return None
    width = max(p[0] for p in hull) - min(p[0] for p in hull)
    height = max(p[1] for p in hull) - min(p[1] for p in hull)
    if not width or not height:
        return None
    twice_area = abs(sum(u * qv - qu * v
                         for (u, v), (qu, qv) in zip(hull, hull[1:] + hull[:1])))
    return Fraction(twice_area, 2 * width * height)


def certificate() -> dict:
    """Check the finite exact identity sufficient for induction at all n >= 2."""
    h2, h3 = hull_at_depth(2), hull_at_depth(3)
    scaled_h2 = convex_hull(tuple((3 * u, 3 * v) for u, v in h2))
    candidates = step_candidates(h2, 9)
    assert len(candidates) == 25
    # Independent half-plane containment and vertex attainment certificate:
    # exactly these finite checks establish T_9(H_2) = 3 H_2.
    assert all(inside_convex_polygon(point, scaled_h2) for point in candidates)
    assert all(vertex in candidates for vertex in scaled_h2)
    assert h3 == scaled_h2
    assert area_fraction(h2) == Fraction(19, 36)
    return {
        "angle_degrees": 60,
        "integer_lattice": "x=sqrt(3)/2*u; y=v/2",
        "hull_at_2": [list(v) for v in h2],
        "hull_at_3": [list(v) for v in h3],
        "step_candidates_checked": len(candidates),
        "all_candidates_inside_scaled_hull": True,
        "all_scaled_hull_vertices_attained": True,
        "induction_step_base": "H_3 = 3 H_2 (integer half-planes and vertex attainment)",
        "derived_for_all_depths_n_ge_2": {
            "hull": "H_n = 3**(n-2) H_2",
            "area_fraction": "19/36",
            "aspect_width_over_height": "1/sqrt(3)",
        },
    }


if __name__ == "__main__":
    print(json.dumps(certificate(), indent=2))
