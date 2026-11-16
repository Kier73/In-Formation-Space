"""BMO-010: an angle-dependent stochastic support cone at every depth.

The all-depth theorem is proved in ANGLE-DEPENDENT-SUPPORT-CONE.md.
This executable module audits its integer tail inequalities and provides
numerical checks, not a substitute for the universal induction argument.
Python standard library only.
"""
from __future__ import annotations

import json
import math
from fractions import Fraction

from depth6_phase import signatures as literal_endpoint_signatures
from tip_exposure import tip_index, tip_moments, small_angle_squared_bound


def nested_tip_headings(depth: int) -> tuple[tuple[int, int], ...]:
    """Exact distribution of signed integer turn headings at A_n.

    At headings -j, for 0<=j<n: multiplicity 2*3**(n-1-j).
    At heading -n: multiplicity 1. Total number of steps: 3**n.
    """
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError('depth must be a positive integer')
    counts = [(-depth, 1)]
    counts.extend((-j, 2 * 3 ** (depth - 1 - j)) for j in range(depth - 1, -1, -1))
    return tuple(counts)


def tail_counts(signature: tuple[tuple[int, int], ...], cutoff: int) -> int:
    """Number of path steps at a signed heading <= cutoff."""
    return sum(count for heading, count in signature if heading <= cutoff)


def normalized_left_tail_defects(signature: tuple[tuple[int, int], ...], depth: int) -> tuple[int, ...]:
    """Nonnegative integer slacks: T-3**j*N_{heading<=-j}, j=1..n."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError('depth must be a positive integer')
    total = sum(v for _, v in signature)
    if total < 0 or any(not isinstance(h, int) or not isinstance(k, int) or k < 0
                        for h, k in signature):
        raise ValueError('invalid heading multiplicities')
    return tuple(total - 3 ** j * tail_counts(signature, -j) for j in range(1, depth+1))


def first_order_gap(signature: tuple[tuple[int, int], ...], depth: int) -> int:
    """D_n(p)=(K_A*T - 3**n*K_p), integer oriented-area derivative."""
    s, ka = tip_moments(depth)
    total = sum(n for _, n in signature)
    k = -sum(heading * n for heading, n in signature)
    return ka * total - s * k


def guaranteed_angle(depth: int) -> float:
    """Lower-bound on actual exposed interval: 0<theta<=pi/(4n) radians."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError('depth must be a positive integer')
    return math.pi / (4 * depth)


def quantitative_cross_lower_bound(depth: int, theta: float) -> float:
    """For every other non-origin endpoint: cross(A_n,p)>=this > 0.

    The proof uses (i) stochastic dominance of signed heading histograms,
    (ii) increasing sine on the relevant difference domain and
    (iii) sharp first-order integer gap D_n(p)>=3**(n-1).
    """
    if not math.isfinite(theta) or theta <= 0 or theta > guaranteed_angle(depth):
        raise ValueError('theta must be in (0, pi/(4*depth)] radians')
    return (2 * 3 ** (depth-1) * math.sin(theta / 2)
            * math.cos((2 * depth - 0.5) * theta))


def cross_sine_coefficients(a, b):
    """Exact integer coefficients of the oriented sine-difference expansion.

    Write cross(a,b,theta) = sum_(d>0) c[d]*sin(d*theta).  For each
    positive heading difference d, c[d] is the *integer* count of
    (b-heading minus a-heading)==d minus its antisymmetric partner -d.

    Cancellation is performed in Z, before any floating-point sin call.
    Thus cross(a,a,theta) is identically zero, not merely close to zero,
    regardless of depth, angle, interpreter or summation order.
    """
    weights = {}
    for hist in (a, b):
        for heading, multiplicity in hist:
            if (type(heading) is not int or type(multiplicity) is not int
                    or multiplicity < 0):
                raise ValueError("heading histograms require nonnegative integer counts")
    for ka, na in a:
        for kb, nb in b:
            difference = kb - ka
            if difference:
                weights[difference] = weights.get(difference, 0) + na * nb
    return tuple(
        (d, weights.get(d, 0) - weights.get(-d, 0))
        for d in sorted({abs(offset) for offset in weights})
        if weights.get(d, 0) != weights.get(-d, 0)
    )


def cross_from_histograms(a, b, theta):
    """Oriented cross with exact integer antisymmetry before numeric evaluation.

    The trigonometric projection remains floating-point for nonzero terms;
    no approximate float is used as a mathematical proof of zero.
    """
    return math.fsum(
        coefficient * math.sin(difference * theta)
        for difference, coefficient in cross_sine_coefficients(a, b)
    )


def audit_depth(depth: int, *, numeric_probe: bool = True) -> dict:
    """Exact integer histogram audit of the literal depth-n grammar, n<=6."""
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 6:
        raise ValueError('audit depth must be an integer 1..6')
    signatures = literal_endpoint_signatures(depth)
    nested = nested_tip_headings(depth)
    index = tip_index(depth)
    assert signatures[index] == nested
    s = 3 ** depth
    assert sum(v for _, v in nested) == s
    assert all(tail_counts(nested, -j) * 3**j == s for j in range(1, depth + 1))

    minimal_gap: int | None = None
    zero_defect_indices = []
    for i, signature in enumerate(signatures):
        defects = normalized_left_tail_defects(signature, depth)
        assert all(slack >= 0 for slack in defects), (depth, i, defects)
        if i == 0:
            continue
        if all(slack == 0 for slack in defects):
            zero_defect_indices.append(i)
            assert i == index
        if i == index:
            continue
        gap = first_order_gap(signature, depth)
        assert gap >= s // 3, (depth, i, gap)
        minimal_gap = gap if minimal_gap is None else min(minimal_gap, gap)
    assert zero_defect_indices == [index]
    assert minimal_gap == s // 3

    if numeric_probe:
        for theta in (guaranteed_angle(depth)/2, guaranteed_angle(depth)):
            lower = quantitative_cross_lower_bound(depth, theta)
            for i, signature in enumerate(signatures):
                if i in (0, index):
                    continue
                cross = cross_from_histograms(nested, signature, theta)
                assert cross + 1e-9 * max(1, abs(cross)) >= lower, (depth, i, cross, lower)
    return {
        'depth': depth,
        'total_endpoints': len(signatures),
        'nested_tip_endpoint': index,
        'nested_tip_exact_steps': s,
        'tail_bounds': '3**j * N(heading<=-j) <= T for j=1..depth',
        'unique_all_tail_equality_endpoint': zero_defect_indices[0],
        'minimum_support_derivative_gap': minimal_gap,
        'all_depth_exposure_angle_degrees': 45 / depth,
        'previous_bound_angle_degrees': round(math.degrees(math.sqrt(float(small_angle_squared_bound(depth)))), 9),
        'ratio_of_new_to_old_angle_guarantee': round(guaranteed_angle(depth) / math.sqrt(float(small_angle_squared_bound(depth))), 4),
    }


def certificate(max_audit_depth: int = 6) -> dict:
    if isinstance(max_audit_depth, bool) or not isinstance(max_audit_depth, int) or not 1 <= max_audit_depth <= 6:
        raise ValueError('max_audit_depth must be 1..6')
    return {
        'experiment': 'BMO-010',
        'grammar': 'F[+F]F[-F]F',
        'theorem': 'For every depth n>=1, O to A_n is a strict supporting edge for 0<theta<=pi/(4*n)',
        'angle_units': 'radians',
        'tail_invariant': 'for every j>=1: 3**j*count(heading<=-j) <= path_step_count',
        'nested_tip_distribution': 'N(heading<=-j)/T=3**(-j) for 1<=j<=n',
        'support_bound': 'cross(O,A_n,p)>=2*3**(n-1)*sin(theta/2)*cos((2*n-1/2)*theta)>0',
        'proof_method': 'five exact histogram affine shifts, first-order stochastic dominance, monotone sine, integer support gap',
        'open_question': 'Exposure at full candidate angle theta_n, and all-depth hull transition census',
        'finite_audits': [audit_depth(n) for n in range(1, max_audit_depth+1)],
    }


if __name__ == '__main__':
    print(json.dumps(certificate(), indent=2))
