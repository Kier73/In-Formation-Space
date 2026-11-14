"""BMO-004: exact depth-three canopy convex-hull regime certificate.

Coordinates are (sin(theta) * X(c), Y(c)) with c=cos(theta) and
X,Y integer Chebyshev polynomials. The only nonrational boundary is
alpha = (2+sqrt(46))/12. Quadratic-field arithmetic and Bernstein
positivity prove half-plane inequalities on full intervals, without
floating-point root isolation or point-sampling as a proof.

Python standard library only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from math import comb

from angle_transitions import (endpoint_polynomials, oriented_cross,
                                bernstein_homogenized, evaluate)


@dataclass(frozen=True)
class Q46:
    """Exact a+b*sqrt(46), with rational a,b and sign comparisons."""

    a: Fraction = Fraction(0)
    b: Fraction = Fraction(0)

    def __post_init__(self):
        object.__setattr__(self, 'a', Fraction(self.a))
        object.__setattr__(self, 'b', Fraction(self.b))

    @staticmethod
    def coerce(value):
        return value if isinstance(value, Q46) else Q46(Fraction(value))

    def __add__(self, other):
        other = self.coerce(other)
        return Q46(self.a + other.a, self.b + other.b)

    __radd__ = __add__

    def __neg__(self):
        return Q46(-self.a, -self.b)

    def __sub__(self, other):
        return self + -self.coerce(other)

    def __rsub__(self, other):
        return self.coerce(other) - self

    def __mul__(self, other):
        other = self.coerce(other)
        return Q46(self.a * other.a + 46 * self.b * other.b,
                   self.a * other.b + self.b * other.a)

    __rmul__ = __mul__

    def __pow__(self, exponent):
        if not isinstance(exponent, int) or exponent < 0:
            raise ValueError('nonnegative integer exponent required')
        acc, x = Q46(1), self
        while exponent:
            if exponent & 1:
                acc = acc * x
            x = x * x
            exponent >>= 1
        return acc

    def sign(self):
        a, b = self.a, self.b
        if not b:
            return (a > 0) - (a < 0)
        if not a or (a > 0) == (b > 0):
            return 1 if b > 0 else -1
        comparison = a * a - 46 * b * b
        if comparison == 0:
            raise AssertionError('irrational sqrt(46) cannot cancel nonzero rationals')
        if a > 0:
            return 1 if comparison > 0 else -1
        return -1 if comparison > 0 else 1

    def __eq__(self, other):
        try:
            other = self.coerce(other)
        except (TypeError, ValueError):
            return NotImplemented
        return self.a == other.a and self.b == other.b

    def __lt__(self, other):
        return (self - other).sign() < 0

    def __le__(self, other):
        return (self - other).sign() <= 0

    def __gt__(self, other):
        return (self - other).sign() > 0

    def __ge__(self, other):
        return (self - other).sign() >= 0

    def __str__(self):
        return f'({self.a})+({self.b})*sqrt(46)'


ALPHA = Q46(Fraction(1, 6), Fraction(1, 12))  # cos(theta*)

# Listed in counterclockwise order. Excluding breakpoint endpoints, each
# is strictly convex and contains all 126 depth-three symbolic endpoints.
REGIMES = (
    ('broad', Q46(0), Q46(Fraction(1, 4)), (100, 125, 50, 0)),
    ('middle', Q46(Fraction(1, 4)), Q46(Fraction(1, 2)), (100, 125, 50, 0, 95)),
    ('narrow', Q46(Fraction(1, 2)), ALPHA, (95, 100, 125, 50, 35, 0)),
    ('very_narrow', ALPHA, Q46(1), (95, 100, 125, 50, 35, 0, 94)),
)


def endpoint_signatures(depth=3):
    """Reconstruct every step endpoint from relative-angle heading counts."""
    if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 3:
        raise ValueError('depth must be an integer from 0 to 3')
    word = 'F'
    for _ in range(depth):
        word = ''.join('F[+F]F[-F]F' if token == 'F' else token for token in word)
    heading = 0
    counts = {}
    stack = []
    signatures = {(): None}
    for token in word:
        if token == 'F':
            counts[heading] = counts.get(heading, 0) + 1
            signatures[tuple(sorted(counts.items()))] = None
        elif token == '+':
            heading += 1
        elif token == '-':
            heading -= 1
        elif token == '[':
            stack.append((heading, counts.copy()))
        elif token == ']':
            if not stack:
                raise ValueError('unmatched closing bracket')
            heading, counts = stack.pop()
        else:
            raise ValueError('bad grammar token')
    assert not stack and heading == 0
    return tuple(signatures)


def exact_hull_at(points, cosine):
    """Independent convex-hull algorithm, ordering algebraic Q46 points."""
    cosine = Q46.coerce(cosine)
    xy = {}
    for i, (xp, yp) in enumerate(points):
        coordinate = (evaluate(xp, cosine), evaluate(yp, cosine))
        if coordinate not in xy:
            xy[coordinate] = i
    ordered = sorted((point, i) for point, i in xy.items())

    def cross(a, b, p):
        ax, ay = a[0]
        bx, by = b[0]
        px, py = p[0]
        return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

    lower, upper = [], []
    for vertex in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], vertex) <= 0:
            lower.pop()
        lower.append(vertex)
    for vertex in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], vertex) <= 0:
            upper.pop()
        upper.append(vertex)
    return tuple(vertex[1] for vertex in lower[:-1] + upper[:-1])


def cert_interval(points, name, lo, hi, corners):
    """Positive exact Bernstein coefficients certify every polygon edge."""
    assert lo < hi
    for i in range(len(corners)):
        a, b, p = (points[corners[(i + j) % len(corners)]] for j in range(3))
        poly = oriented_cross(a, b, p)
        coeff = bernstein_homogenized(poly, lo, hi)
        if not all(v >= 0 for v in coeff) or not any(v > 0 for v in coeff):
            raise AssertionError(('not strictly convex', name, i, poly, coeff))
    for i, j in zip(corners, corners[1:] + corners[:1]):
        for point_id, point in enumerate(points):
            poly = oriented_cross(points[i], points[j], point)
            coeff = bernstein_homogenized(poly, lo, hi)
            if not all(v >= 0 for v in coeff):
                raise AssertionError(('nonpositive Bernstein coeff', name, i, j, point_id, poly, coeff))
    return len(corners) * len(points)


def certificate():
    signatures = endpoint_signatures(3)
    points = tuple(map(endpoint_polynomials, signatures))
    assert len(points) == 126
    results = []
    constraints = 0
    for name, lo, hi, corners in REGIMES:
        constraints += cert_interval(points, name, lo, hi, corners)
        midpoint = (lo + hi) * Fraction(1, 2)
        assert set(exact_hull_at(points, midpoint)) == set(corners)
        results.append({
            'regime': name,
            'cosine_low': str(lo),
            'cosine_high': str(hi),
            'extreme_endpoint_indices_ccw': list(corners),
            'vertex_count': len(corners),
        })
    witnesses = (
        ((0, 95, 100), (-27, 108), Q46(Fraction(1, 4))),
        ((50, 35, 0), (-27, 54), Q46(Fraction(1, 2))),
        ((0, 94, 95), (-21, -24, 72), ALPHA),
    )
    counts = (4, 5, 6)
    boundary_results = []
    for (indices, expected_poly, root), num in zip(witnesses, counts):
        poly = oriented_cross(*(points[i] for i in indices))
        assert poly == expected_poly and evaluate(poly, root) == 0
        hull = exact_hull_at(points, root)
        assert len(hull) == num, (indices, hull)
        boundary_results.append({
            'at_cosine': str(root),
            'collinearity_triple': list(indices),
            'cross_polynomial_ascending': list(poly),
            'hull_vertex_count': len(hull),
            'hull_vertices': list(hull),
        })
    assert constraints == 2772
    return {
        'experiment': 'BMO-004',
        'scope': 'Convex hull only; depth three; angle 0<theta<90 degrees',
        'symbolic_endpoint_count': len(points),
        'halfplane_certificates': constraints,
        'strict_corner_certificates': sum(len(r[3]) for r in REGIMES),
        'field': 'Q(sqrt(46))',
        'critical_cosine': 'alpha=(2+sqrt(46))/12',
        'regimes': results,
        'boundaries': boundary_results,
        'proof_method': 'Exact polynomial cross-products; nonnegative rational/quadratic Bernstein coefficients, strict convexity, exact boundary hulls',
    }


if __name__ == '__main__':
    print(json.dumps(certificate(), indent=2))
