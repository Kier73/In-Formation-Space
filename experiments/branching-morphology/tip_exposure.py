"""BMO-009: all-depth small-angle supporting-edge theorem.

An endpoint is represented by integer moments (T,K), where T counts
unit steps and K is the negative sum of integer turn headings. The
universal claim is justified by the induction and Taylor argument in
ALL-DEPTH-TIP-EXPOSURE.md; finite checks only audit those premises.
"""

from __future__ import annotations

import json
import math
from fractions import Fraction

RULE = 'F[+F]F[-F]F'


def tip_index(depth: int) -> int:
    """First-seen turtle endpoint index of the recursively nested tip."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError('depth must be a positive integer')
    return (3 * 5**depth + 1) // 4


def tip_moments(depth: int) -> tuple[int, int]:
    """(T,K) of A_n: (3^n, (3^n-1)/2)."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError('depth must be a positive integer')
    s = 3**depth
    return s, (s - 1) // 2


def cone_slack(moment: tuple[int, int]) -> int:
    """S=T-1-2K; S>=0 for every non-origin endpoint."""
    t, k = moment
    return t - 1 - 2 * k


def affine_moment(moment: tuple[int, int], trunk: int, copy: int) -> tuple[int, int]:
    """Five true affine copies: original, right, straight, left, straight."""
    if isinstance(trunk, bool) or not isinstance(trunk, int) or trunk < 1:
        raise ValueError('trunk must be a positive integer')
    if isinstance(copy, bool) or copy not in range(5):
        raise ValueError('copy must be 0, 1, 2, 3, or 4')
    t, k = moment
    if not isinstance(t, int) or not isinstance(k, int) or t < 0 or t > trunk:
        raise ValueError('invalid moment for trunk length')
    if copy == 0:
        return t, k
    if copy == 1:
        return trunk + t, k - t
    if copy == 2:
        return trunk + t, k
    if copy == 3:
        return 2 * trunk + t, k + t
    return 2 * trunk + t, k


def moment_frontier(depth: int) -> frozenset[tuple[int, int]]:
    """Exact finite moment projection, for independent auditing only."""
    if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 20:
        raise ValueError('verification depth must be integer 0..20')
    moments = {(0, 0), (1, 0)}
    for level in range(depth):
        trunk = 3**level
        moments = {affine_moment(moment, trunk, i) for moment in moments for i in range(5)}
    return frozenset(moments)


def literal_turtle_moments(depth: int) -> tuple[tuple[int, int], ...]:
    """Independent literal grammar parser with full endpoint indexing."""
    if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 7:
        raise ValueError('literal depth must be integer 0..7')
    word = 'F'
    for _ in range(depth):
        word = ''.join(RULE if c == 'F' else c for c in word)
    heading, t, k = 0, 0, 0
    stack: list[tuple[int, int, int]] = []
    points = [(0, 0)]
    for token in word:
        if token == 'F':
            t += 1
            k -= heading
            points.append((t, k))
        elif token == '+':
            heading += 1
        elif token == '-':
            heading -= 1
        elif token == '[':
            stack.append((heading, t, k))
        elif token == ']':
            heading, t, k = stack.pop()
        else:
            raise ValueError('bad grammar instruction')
    assert not stack and heading == 0 and len(points) == 5**depth + 1
    return tuple(points)


def small_angle_squared_bound(depth: int) -> Fraction:
    """Sufficient theta^2 bound (radians) for strict supporting edge O--A_n.

    For 0<theta^2<=bound: cross(O,A_n,p) >= 3^n*theta/16 > 0
    for every endpoint p other than O and A_n.
    """
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError('depth must be a positive integer')
    return Fraction(1, 4 * depth**3 * 3**depth)


def support_gap(moment: tuple[int, int], depth: int) -> int:
    """First angular derivative of cross(O,A_n,p) at theta=0."""
    t, k = moment
    s, ka = tip_moments(depth)
    return ka * t - s * k


def verify_finite_moment_invariant(depth: int) -> dict:
    """Audit actual finite endpoints and the sharp first-order support gap."""
    points = moment_frontier(depth)
    s, ka = tip_moments(depth)
    assert len(points) > 2
    assert (0, 0) in points and (s, ka) in points
    assert all(0 <= t <= s and
               (t == 0 and k == 0 or t > 0 and cone_slack((t, k)) >= 0)
               for t, k in points)
    zero_slack = sorted((t, k) for t, k in points if t > 0 and cone_slack((t, k)) == 0)
    assert zero_slack == [(3**j, (3**j - 1)//2) for j in range(depth+1)]
    others = points - {(0, 0), (s, ka)}
    gap = min(support_gap(p, depth) for p in others)
    assert gap == s//3
    return {
        'depth': depth,
        'total_segments': 5**depth,
        'distinct_integer_moment_pairs': len(points),
        'unique_full_depth_tip_index': tip_index(depth),
        'tip_T_K': [s, ka],
        'zero_slack_path_lengths': [3**j for j in range(depth+1)],
        'min_first_order_support_gap': gap,
        'certified_theta_squared_max': str(small_angle_squared_bound(depth)),
        'certified_theta_degrees_max_approx': round(
            math.degrees(math.sqrt(float(small_angle_squared_bound(depth)))), 9),
    }


def certificate(max_audit_depth: int = 8) -> dict:
    """Finite tests accompanying, but not substituting for, the induction."""
    if (isinstance(max_audit_depth, bool) or not isinstance(max_audit_depth, int)
            or not 1 <= max_audit_depth <= 20):
        raise ValueError('max_audit_depth must be integer 1..20')
    checks = [verify_finite_moment_invariant(n) for n in range(1, max_audit_depth+1)]
    return {
        'experiment': 'BMO-009',
        'scope': 'Every finite depth n>=1; strict small-angle hull edge O--A_n',
        'rule': RULE,
        'moment_definition': 'T=path unit-step count; K=minus sum of integer headings',
        'invariant': 'Every non-origin endpoint has 0<T<=3^n and S=T-1-2K>=0',
        'slack_zero_cases': 'Only T=3^j, K=(3^j-1)/2 for j=0..n',
        'determinant_derivative': 'D_n(p)=((3^n-1)/2)*T-3^n*K>=3^(n-1) for p not O or A_n',
        'finite_angle_interval': '0<theta^2<=1/(4*n^3*3^n), theta in radians',
        'strict_support_bound': 'cross(O,A_n,p)>=3^n*theta/16>0 for all other endpoints',
        'proof_method': 'five affine slack cases, uniqueness induction, integer gap, uniform Taylor bounds',
        'interpretation': 'Exposure near zero, not certification up to theta_n candidate root',
        'finite_audits': checks,
    }


if __name__ == '__main__':
    print(json.dumps(certificate(), indent=2))
