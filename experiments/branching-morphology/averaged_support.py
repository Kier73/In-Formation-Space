"""BMO-011: averaged heading-phasor exposed-edge bound at every depth.

The universal proof is in AVERAGED-SUPPORT-BRACKET.md. Floating-point
helpers are illustrative; all-depth validity follows from an exact
heading-distribution argument and finite integer gap.
"""

from __future__ import annotations

import json
import math

from angular_support_cone import nested_tip_headings, first_order_gap, cross_from_histograms
from all_depth_law import first_candidate_zero
from tip_exposure import tip_index
from depth6_phase import signatures as turtle_signatures


def improved_angle(depth: int) -> float:
    """All-depth guarantee for strict O--A_n supporting edge, radians."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError('depth must be a positive integer')
    return math.pi / (2*depth+1)


def normalized_tip_phasor(depth: int, theta: float) -> complex:
    """E(exp(-i H theta)) for the nested tip's signed heading H.

    Recurrence avoids enormous integer path lengths and float overflow:
    W_0=1, W_n=2/3+exp(i theta)*W_(n-1)/3.
    """
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError('depth must be a positive integer')
    if not math.isfinite(theta) or theta < 0:
        raise ValueError('theta must be finite and nonnegative')
    z = complex(math.cos(theta), math.sin(theta))
    w = 1.0 + 0j
    for _ in range(depth):
        w = (2 + z*w)/3
    return w


def quantitative_cross_lower_bound(depth: int, theta: float) -> float:
    """Universal lower bound on cross(O,A_n,p) at every other endpoint.

    cross >= (4*3**n/9) * sin(theta/2) * cos(n*theta) > 0,
    with 0 < theta <= pi/(2*n+1). Bounds are evaluated in float here;
    the proof uses exact inequalities.
    """
    limit = improved_angle(depth)
    if not math.isfinite(theta) or not 0 < theta <= limit:
        raise ValueError('theta outside guaranteed supporting interval')
    return (4 * (3**depth) / 9) * math.sin(theta/2) * math.cos(depth*theta)


def phase_enclosure(depth: int, theta: float) -> tuple[float, float]:
    """Measured argument and rigorous upper bound (radians) 0<=phi<theta/2."""
    limit = improved_angle(depth)
    if not math.isfinite(theta) or not 0 < theta <= limit:
        raise ValueError('theta outside guaranteed interval')
    w = normalized_tip_phasor(depth,theta)
    return math.atan2(w.imag, w.real), theta/2


def first_loss_bracket(depth: int) -> tuple[float, float]:
    """All-depth lower and upper bounds for first loss of strict support.

    Upper limit is the first zero of nested-tip collinearity polynomial
    (known exactly via the recurrence; numerical output here).
    n>=2 only because the depth-one polynomial has no such zero.
    """
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 2:
        raise ValueError('depth must be an integer >= 2')
    lo = improved_angle(depth)
    hi = first_candidate_zero(depth)
    assert lo < hi
    return lo, hi


def audit_depth(depth: int) -> dict:
    """Independent finite endpoint check; audited levels 1..6 only."""
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 6:
        raise ValueError('audit depth must be an integer from 1 to 6')
    signatures = turtle_signatures(depth)
    tip = nested_tip_headings(depth)
    index = tip_index(depth)
    assert signatures[index] == tip
    gap = 3**(depth-1)
    for theta in (improved_angle(depth)/2, improved_angle(depth)):
        phi, bound = phase_enclosure(depth, theta)
        assert 0 < phi < bound
        w = normalized_tip_phasor(depth, theta)
        assert w.real > 2/3 - 1e-14
        margin = quantitative_cross_lower_bound(depth, theta)
        for i, signature in enumerate(signatures):
            if i in (0, index):
                continue
            actual = cross_from_histograms(tip, signature, theta)
            assert first_order_gap(signature,depth) >= gap
            assert actual + 1e-8 * max(1,abs(actual)) >= margin, (depth,theta,i,actual,margin)
    lower = improved_angle(depth)
    previous = math.pi/(4*depth)
    return {
        'depth': depth,
        'endpoints':len(signatures),
        'nested_tip_index': index,
        'previous_guarantee_degrees': round(math.degrees(previous),8),
        'stronger_guarantee_degrees':round(math.degrees(lower),8),
        'factor':round(lower/previous,8),
        'first_loss_upper_bound_degrees': (round(math.degrees(first_candidate_zero(depth)),8) if depth>=2 else None),
        'min_integer_gap':gap,
        'proof_margin_at_upper_bound':quantitative_cross_lower_bound(depth,lower),
    }


def certificate(max_audit_depth: int = 6):
    if isinstance(max_audit_depth,bool) or not isinstance(max_audit_depth,int) or not 1<=max_audit_depth<=6:
        raise ValueError('max_audit_depth must be in 1..6')
    return {
        'experiment':'BMO-011',
        'theorem':'For n>=1, O--A_n strictly supports H_n at 0<theta<=pi/(2*n+1)',
        'exact_positive_margin':'cross(O,A_n,p)>=(4*3**n/9)*sin(theta/2)*cos(n*theta)',
        'tip_phasor':'W_0=1, W_n=(2+exp(i*theta)*W_(n-1))/3',
        'phase_bound':'0<arg(W_n)<theta/2 for 0<theta<=pi/(2*n+1)',
        'strict_support_loss_bracket':'pi/(2*n+1) <= tau_n <= theta_n, for n>=2',
        'asymptotic':'n*tau_n -> pi/2 (radians), from n*theta_n -> pi/2',
        'scope':'strict exposed O--A_n edge; not exact all-depth transition census',
        'finite_audits':[audit_depth(n) for n in range(1,max_audit_depth+1)],
    }


if __name__ == '__main__':
    print(json.dumps(certificate(),indent=2))
