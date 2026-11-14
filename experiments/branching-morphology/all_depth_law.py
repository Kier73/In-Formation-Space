"""BMO-007: unbounded-depth hull absorption and nested-tip witness recurrence.

The interval premises are the exact BMO-003..006 convex-hull certificates.
Exact polynomial identities turn their finite results into the base cases
of a universal (all later depths) geometric induction.

The numerical angle illustrations are NOT hull-classification certificates.
"""

from __future__ import annotations

import json
import math
from fractions import Fraction

import angle_transitions as d2
import depth3_phase as d3
import depth4_phase as d4
import depth5_phase as d5

INHERITANCE = (
    # (old depth, new depth, index-pairs into their certified regimes)
    (2, 3, ((2, 0), (1, 1), (0, 2))),
    (3, 4, ((0, 0), (1, 1), (2, 2), (3, 3), (3, 4))),
    (4, 5, ((0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (5, 6))),
)
PHASES = {2: d2.REGIMES, 3: d3.REGIMES, 4: d4.REGIMES, 5: d5.REGIMES}
SIGNATURES = {
    1: lambda: d3.endpoint_signatures(1),
    2: lambda: d2.endpoint_signatures(),
    3: lambda: d3.endpoint_signatures(3),
    4: lambda: d4.signatures(4),
    5: lambda: d5.signatures(5),
}


def multiply_poly(p, scalar):
    return tuple(scalar * a for a in p)


def signature_homothety(old, new):
    """Every old endpoint reappears as endpoint 5*i at 3x its position."""
    if len(new) != 5 * (len(old) - 1) + 1:
        raise AssertionError("unexpected number of new endpoints")
    for i, signature in enumerate(old):
        if new[5 * i] != tuple((k, 3 * count) for k, count in signature):
            raise AssertionError(("embedded endpoint mismatch", i))
    return len(old)


def chebyshev_u(n):
    """U_n(c), integer coefficients ascending in c; U_-1=0."""
    if n == -1:
        return (0,)
    if n < -1:
        raise ValueError("index must be >= -1")
    if n == 0:
        return (1,)
    prev, now = (1,), (0, 2)
    for _ in range(1, n):
        prev, now = now, d2.sub(d2.scale(d2.mul((0, 1), now), 2), prev)
    return now


def new_corner_polynomial(depth):
    """Exact cross(0,A_n,B_n)/sin(theta) for the nested consecutive tips.

    The first zero at depths n>5 is only a potential convex-hull transition,
    NOT an established exposed-vertex event.
    """
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 100:
        raise ValueError("depth must be an integer in [1,100]")
    polynomial = (3,)
    for m in range(1, depth):
        polynomial = d2.add(
            polynomial,
            d2.scale(d2.sub(chebyshev_u(m), chebyshev_u(m - 1)),
                     2 * 3 ** m),
        )
    return polynomial


def endpoint_pair(depth):
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError("positive integer depth required")
    a = (3 * 5 ** depth + 1) // 4
    return a, a + 1


def phase_identity_certificate(*, verify_prior=True):
    """Exact H_(n+1)=3 H_n over previously certified continuous intervals.

    All four earlier exact interval certificates can be re-executed before
    treating their vertex tables as the premises for this induction.
    """
    if verify_prior:
        d2.certify()
        d3.certificate()
        d4.certificate()
        d5.certificate()
    signatures = {k: fn() for k, fn in SIGNATURES.items()}
    embeddings = {
        f"{n-1}_to_{n}": signature_homothety(signatures[n - 1], signatures[n])
        for n in range(2, 6)
    }
    records = []
    total_vertices = 0
    for old_depth, new_depth, pairs in INHERITANCE:
        old_table, new_table = PHASES[old_depth], PHASES[new_depth]
        old_sigs, new_sigs = signatures[old_depth], signatures[new_depth]
        for prev_index, next_index in pairs:
            old_vertices = old_table[prev_index][3]
            new_vertices = new_table[next_index][3]
            scaled = tuple(5 * i for i in old_vertices)
            if not any(scaled[k:] + scaled[:k] == new_vertices
                       for k in range(len(scaled))):
                raise AssertionError((old_depth, new_depth, prev_index, next_index,
                                      "vertex identities disagree"))
            for index in old_vertices:
                old_point = d2.endpoint_polynomials(old_sigs[index])
                new_point = d2.endpoint_polynomials(new_sigs[5 * index])
                if new_point != tuple(multiply_poly(p, 3) for p in old_point):
                    raise AssertionError(("polynomial geometry mismatch", old_depth, index))
            total_vertices += len(old_vertices)
            records.append({
                "old_depth": old_depth, "new_depth": new_depth,
                "old_regime": old_table[prev_index][0],
                "new_regime": new_table[next_index][0],
                "vertices": len(old_vertices),
                "exact_vertex_polynomial_identities": len(old_vertices),
            })
    if len(records) != 15 or total_vertices != 89:
        raise AssertionError((len(records), total_vertices))
    # At sigma, point 2344 lies on the old scaled-H4 edge 0->2345.
    # For sigma<c<1 it is strictly OUTSIDE the edge:
    # cross(0,2345,2344)=-sin(theta)*P_5(c)<0.
    witness = d2.bernstein_homogenized(
        new_corner_polynomial(5), d5.SIGMA, Fraction(1)
    )
    if not (witness[0] == 0 and all(v > 0 for v in witness[1:])):
        raise AssertionError("newest transition exterior witness failed")
    return {
        "experiment": "BMO-007",
        "inherited_endpoint_checks": embeddings,
        "certified_scale_equalities": len(records),
        "vertex_polynomial_equalities": total_vertices,
        "sigma_outside_witness": {
            "critical_edge": "0 -> 2345 at depth five; 2344 is outside for sigma<c<1",
            "oriented_area_polynomial": list(new_corner_polynomial(5)),
            "bernstein_signs_on_sigma_to_one": [v.sign() for v in witness],
        },
        "regimes": records,
        "all_future_depths": {
            "n_at_least_3": "H_n=3**(n-2)*H_2 on 0<c<=alpha",
            "n_at_least_4": "H_n=3**(n-3)*H_3 on 0<c<=rho",
            "n_at_least_5": "H_n=3**(n-4)*H_4 on 0<c<=sigma",
            "n_at_least_5_outside": "H_n strictly contains 3**(n-4)*H_4 for sigma<c<1",
            "c": "cos(theta)",
            "alpha": "(2+sqrt(46))/12",
            "rho": "unique (87/100,88/100) root of 144c^3-48c^2-80c+11",
            "sigma": "unique (23/25,93/100) root of 864c^4-288c^3-696c^2+136c+65",
        },
        "proof_dependency": "Earlier exact interval certificates and affine scale-covariant recurrence",
        "scope": "Outer convex hull only. Candidate tip roots at depths >5 are not classified.",
    }


def normalized_witness(theta, depth):
    """Q_n(theta)=cos(theta/2)*P_n(cos(theta))/3**n, stable recursion."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError("positive integer depth required")
    q = math.cos(theta / 2)
    for n in range(2, depth + 1):
        q = (2 * math.cos((n - 0.5) * theta) + q) / 3
    return q


def first_candidate_zero(depth, steps=70):
    """First zero of Q_n; numerical illustration, not a hull proof."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 2:
        raise ValueError("depth >=2 required")
    lo = 0.0
    hi = min(math.pi / 2, math.pi / (depth - 0.5))
    assert normalized_witness(lo, depth) > 0 > normalized_witness(hi, depth)
    for _ in range(steps):
        mid = (lo + hi) / 2
        if normalized_witness(mid, depth) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def recurrence_report():
    rows = []
    for n in range(2, 13):
        theta = first_candidate_zero(n)
        rows.append({
            "depth": n,
            "candidate_angle_degrees": round(math.degrees(theta), 8),
            "n_times_angle_radians": round(n * theta, 8),
        })
    return {
        "formula": "P_n(c)=3+2 sum_{m=1}^{n-1} 3^m (U_m(c)-U_(m-1)(c))",
        "difference": "P_(n+1)-P_n=2*3^n*(U_n-U_(n-1))",
        "normalized": "Q_(n+1)(theta)=(2/3)cos((n+1/2)theta)+(1/3)Q_n(theta)",
        "first_root": "theta_n strictly decreases for all n>=2; n*theta_n -> pi/2",
        "classification": "At n<=5 these roots are exposed-hull transitions. For n>5 they are candidate collinearities only.",
        "illustrations": rows,
    }


if __name__ == "__main__":
    print(json.dumps({
        "homothety": phase_identity_certificate(),
        "candidate_recurrence": recurrence_report(),
    }, indent=2))
