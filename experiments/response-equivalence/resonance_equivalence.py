"""RE-001: exact observer-relative resonance and finite-horizon identification.

A bounded, reproducible teaching/research fixture. No claims of universal
semantic distance, physical measurement, or arbitrary system identification.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import combinations
import json


def f(v):
    return Q(v)


def as_text(v):
    return str(v)


@dataclass(frozen=True)
class Plant:
    A: tuple[tuple[Q, ...], ...]
    B: tuple[Q, ...]
    C: tuple[Q, ...]

    def __post_init__(self):
        n = len(self.B)
        if n == 0 or len(self.A) != n or len(self.C) != n:
            raise ValueError('nonempty square system required')
        if any(len(row) != n for row in self.A):
            raise ValueError('state matrix is not square')

    def markov(self, n: int) -> list[Q]:
        """h[k]=C A^k B, indexed from the first observable impulse response."""
        if n < 0:
            raise ValueError('negative sample count')
        v = list(self.B)
        result = []
        for _ in range(n):
            result.append(sum((c * x for c, x in zip(self.C, v)), Q(0)))
            v = [sum((a * x for a, x in zip(row, v)), Q(0)) for row in self.A]
        return result


def block_sum(first: Plant, second: Plant) -> Plant:
    n, m = len(first.B), len(second.B)
    a = tuple(
        tuple((first.A[i][j] if i < n and j < n else
               second.A[i-n][j-n] if i >= n and j >= n else Q(0))
              for j in range(n+m))
        for i in range(n+m)
    )
    return Plant(a, first.B+second.B, first.C+second.C)


def examples(delay: int = 6) -> dict[str, Plant]:
    """Two modal poles, an exact coordinate change, two kinds of impostor."""
    base = Plant(((Q(1,2), Q(0)), (Q(0), Q(1,4))),
                 (Q(1), Q(1)), (Q(1), Q(1)))
    # Change of coordinates z=T*x, T=((1,1),(0,1)); A'=TAT^-1.
    coordinate = Plant(((Q(1,2), Q(-1,4)), (Q(0), Q(1,4))),
                       (Q(2), Q(1)), (Q(1), Q(0)))
    # Additional evolving state has zero coupling to the declared readout.
    hidden = block_sum(base, Plant(((Q(7,8),),), (Q(1),), (Q(0),)))
    # Same state eigenvalues (modes), but a different output coupling/residue.
    changed_output = Plant(base.A, base.B, (Q(1), Q(-1)))
    # Delay line: first visible extra impulse coefficient occurs at k=delay.
    size = delay+1
    shift = tuple(tuple(Q(int(i == j+1)) for j in range(size)) for i in range(size))
    injection = (Q(1),) + (Q(0),)*delay
    readout = (Q(0),)*delay + (Q(1),)
    delayed = block_sum(base, Plant(shift, injection, readout))
    return dict(base=base, coordinate=coordinate, hidden=hidden,
                same_modes_changed_output=changed_output, delayed=delayed)


def rank_exact(matrix: list[list[Q]]) -> int:
    if not matrix:
        return 0
    a = [list(row) for row in matrix]
    width = len(a[0])
    if any(len(row) != width for row in a):
        raise ValueError('ragged matrix')
    p = 0
    for col in range(width):
        pivot = next((r for r in range(p, len(a)) if a[r][col]), None)
        if pivot is None:
            continue
        a[p], a[pivot] = a[pivot], a[p]
        pivot_value = a[p][col]
        a[p] = [v/pivot_value for v in a[p]]
        for r in range(len(a)):
            if r != p and a[r][col]:
                scale = a[r][col]
                a[r] = [a[r][j]-scale*a[p][j] for j in range(width)]
        p += 1
        if p == len(a):
            break
    return p


def hankel_rank(samples: list[Q], size: int) -> int:
    if size < 1 or len(samples) < 2*size-1:
        raise ValueError('insufficient impulse-response horizon')
    return rank_exact([[samples[i+j] for j in range(size)] for i in range(size)])


def recover_two_mode_recurrence(samples: list[Q]) -> tuple[Q, Q]:
    """Solve h[k+2]=a*h[k+1]+b*h[k] from four exact observations."""
    if len(samples) < 4:
        raise ValueError('four samples are required')
    y0, y1, y2, y3 = samples[:4]
    determinant = y1*y1-y0*y2
    if not determinant:
        raise ValueError('not independently observable through these samples')
    return (y2*y1-y0*y3)/determinant, (y1*y3-y2*y2)/determinant


def response(plant: Plant, drive: tuple[Q, ...], n: int) -> tuple[Q, ...]:
    """Zero-state output, causal convolution with the Markov parameters."""
    h = plant.markov(n)
    return tuple(sum((h[k]*drive[t-k] for k in range(t+1)
                      if t-k < len(drive)), Q(0)) for t in range(n))


def probes() -> dict[str, tuple[Q, ...]]:
    return {
        'impulse': (Q(1),),
        'delayed_impulse': (Q(0), Q(1)),
        'double': (Q(1), Q(1)),
        'alternating': (Q(1), Q(-1), Q(1), Q(-1)),
        'step_4': (Q(1),)*4,
    }


def squared_distance(left: tuple[Q, ...], right: tuple[Q, ...]) -> Q:
    if len(left) != len(right):
        raise ValueError('mismatched response horizon')
    return sum(((a-b)**2 for a,b in zip(left,right)), Q(0))


def rdm(plant: Plant, n: int, gain: Q = Q(1), offset: Q = Q(0)) -> dict[str, Q]:
    traces = {name: tuple(gain*y+offset for y in response(plant, signal, n))
              for name,signal in probes().items()}
    return {'|'.join((a,b)): squared_distance(traces[a],traces[b])
            for a,b in combinations(traces,2)}


def analyze() -> dict:
    systems = examples(delay=6)
    h = {name: p.markov(20) for name,p in systems.items()}
    base = h['base']
    assert h['coordinate'] == base
    assert h['hidden'] == base
    assert h['same_modes_changed_output'] != base
    assert h['delayed'][:6] == base[:6]
    assert h['delayed'][6]-base[6] == 1
    assert recover_two_mode_recurrence(base) == (Q(3,4), Q(-1,8))
    assert all(base[k+2] == Q(3,4)*base[k+1]-Q(1,8)*base[k]
               for k in range(18))
    assert hankel_rank(base, 3) == 2
    assert hankel_rank(h['hidden'], 3) == 2
    assert hankel_rank(h['delayed'], 9) == 9
    # A new authorized observation of the previously invisible third coordinate
    # would reveal the hidden mode, but that sensor is not in the original contract.
    extra_hidden = Plant(systems['hidden'].A, systems['hidden'].B,
                         (Q(0),Q(0),Q(1)))
    assert extra_hidden.markov(3) == [Q(1),Q(7,8),Q(49,64)]
    # Differences between probes are all scaled by sensor gain squared;
    # normalized relational geometry is unchanged, despite offset and units.
    uncalibrated = rdm(systems['base'], 10, gain=Q(3), offset=Q(2))
    reference_rdm = rdm(systems['base'], 10)
    assert all(uncalibrated[k] == 9*v for k,v in reference_rdm.items())
    assert all(rdm(systems['coordinate'],10)[k] == v
               for k,v in reference_rdm.items())

    return {
        'experiment': 'RE-001', 'arithmetic': 'exact rational',
        'scope': 'zero-state discrete-time LTI, single input/output, no noise',
        'base_markov_first_8': [as_text(x) for x in base[:8]],
        'observable_modal_recurrence': {'a': '3/4', 'b': '-1/8',
                                        'rule': 'h[k+2] = a*h[k+1] + b*h[k]'},
        'hankel_rank_base_3x3': hankel_rank(base, 3),
        'hankel_rank_extra_hidden_3x3': hankel_rank(h['hidden'], 3),
        'hankel_rank_delayed_9x9': hankel_rank(h['delayed'], 9),
        'compared_to_base': {
            name: {
                'state_dimension': len(system.B),
                'first_difference_index': next((i for i,(a,b) in enumerate(zip(base,h[name]))
                                                if a!=b), None),
                'first_6_coefficients_equal': h[name][:6] == base[:6],
                'first_20_coefficients_equal': h[name] == base,
            }
            for name,system in systems.items() if name != 'base'
        },
        'new_observer_hidden_markov_first_3': [as_text(x) for x in extra_hidden.markov(3)],
        'rdm_pairs': len(reference_rdm),
        'rdm_sensor_gain_squared_ratio': 9,
        'rdm_all_pairs_match_after_calibration': True,
        'interpretation': {
            'established': 'two visible modal poles and a 2-state minimal response law in this fixture',
            'not_established': 'unique internal state, absence of unobservable modes, or equivalence beyond finite tests without system assumptions',
            'delayed_counterexample': 'six identical coefficients are distinguishable at coefficient index six',
        },
    }


if __name__ == '__main__':
    print(json.dumps(analyze(), indent=2))
