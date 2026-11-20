"""TCN-006: exact moving-frame descriptions of declared cubic/harmonic gates.

Clifford conjugation transports finite-field Weyl generators by Sp(2,F_p).
Commuting diagonal gates can be retained as a single movable phase carrier;
noncommuting carriers are kept in their original operator order, never silently
collapsed. This is classical algebraic simulation, not arbitrary state synthesis.
"""
from __future__ import annotations

from dataclasses import dataclass
import cmath
import math

import numpy as np

from cocycle import ExactOperator, ExactSchedule
from transfer import _prime


def _matvec(m, v, p):
    return ((m[0][0] * v[0] + m[0][1] * v[1]) % p,
            (m[1][0] * v[0] + m[1][1] * v[1]) % p)


def symplectic(v, w, p):
    """W(v)W(w)=omega^(-symplectic(v,w)/2)*W(v+w)."""
    return (v[0] * w[1] - v[1] * w[0]) % p


def canonical_axis(v, p):
    """Return (primitive direction, nonzero scalar) such that v=scalar*axis."""
    q, k = v[0] % p, v[1] % p
    if (q, k) == (0, 0):
        raise ValueError('zero vector has no Weyl generator')
    scalar = q if q else k
    return ((q * pow(scalar, -1, p)) % p,
            (k * pow(scalar, -1, p)) % p), scalar


def _harmonics(values, p):
    """Collapse cos(k theta) and cos(-k theta) to same canonical mode."""
    d = {}
    for f, g in values:
        if type(f) is not int or not isinstance(g, (int, float)) or isinstance(g, bool) or not math.isfinite(g):
            raise ValueError('finite real harmonic strength and integer frequency required')
        k = f % p
        k = min(k, (-k) % p)
        if k == 0:
            raise ValueError('zero-frequency harmonic requires separate global-phase carrier')
        d[k] = d.get(k, 0.0) + float(g)
    return tuple(sorted((k, v) for k, v in d.items() if v != 0))


@dataclass(frozen=True)
class PhaseBlock:
    """exp[2pi i*c*x^3/p + i*sum gamma_k cos(2pi*k*x/p)] in W(axis) eigenframe.

    `axis` is projectively normalized, so cubic coefficients and harmonic
    frequencies have already incorporated the generator's scalar multiplier.
    """
    p: int
    axis: tuple[int, int]
    cubic: int = 0
    harmonics: tuple[tuple[int, float], ...] = ()

    def __post_init__(self):
        if not _prime(self.p):
            raise ValueError('odd prime field required')
        if type(self.cubic) is not int:
            raise ValueError('integer cubic strength required')
        axis, factor = canonical_axis(self.axis, self.p)
        object.__setattr__(self, 'axis', axis)
        object.__setattr__(self, 'cubic', (self.cubic * pow(factor, 3, self.p)) % self.p)
        object.__setattr__(self, 'harmonics', _harmonics(((f*factor, g) for f,g in self.harmonics), self.p))

    def transported(self, matrix):
        v = _matvec(matrix, self.axis, self.p)
        axis, factor = canonical_axis(v, self.p)
        return PhaseBlock(self.p, axis, self.cubic * pow(factor, 3, self.p),
                          tuple((freq * factor, gamma) for freq, gamma in self.harmonics))

    def combined(self, other):
        if not isinstance(other, PhaseBlock) or self.p != other.p or self.axis != other.axis:
            raise ValueError('only collinear phase generators combine')
        return PhaseBlock(self.p, self.axis, self.cubic + other.cubic,
                          self.harmonics + other.harmonics)

    @property
    def trivial(self):
        return self.cubic == 0 and not self.harmonics

    def phase(self, x):
        p = self.p
        x = np.asarray(x, dtype=np.int64) % p
        x2 = x*x % p
        cubic_residue = self.cubic * (x2*x % p) % p
        angle = 2*np.pi*cubic_residue/p
        for f, strength in self.harmonics:
            angle = angle + strength * np.cos(2*np.pi*(f*x%p)/p)
        return np.exp(1j*angle)

    def frame(self):
        """Clifford with second symplectic column `axis`: A Z A^-1=W(axis)."""
        q, k = self.axis
        if k:
            a, c = pow(k, -1, self.p), 0
        else:
            a, c = 0, (-pow(q, -1, self.p)) % self.p
        return ExactOperator(self.p, ((a, q), (c, k)))

    def record(self):
        return {'axis': list(self.axis), 'cubic_mod_p': self.cubic,
                'harmonics': [[f, gamma.hex()] for f, gamma in self.harmonics]}


@dataclass(frozen=True)
class MovingFrameGround:
    """Product B_0 B_1 ... B_(r-1) C |source>, leftmost block first.

    Block phases are analytically exact for declared gates; only rendering
    complex values involves floating-point evaluation. `core` is TCN-003's
    exact Gauss-cocycle Clifford operator, global phase included.
    """
    p: int
    source: int
    core: ExactOperator
    blocks: tuple[PhaseBlock, ...] = ()
    clifford_products: int = 0
    declared_gates: int = 0

    def __post_init__(self):
        if not _prime(self.p) or type(self.source) is not int or not 0 <= self.source < self.p:
            raise ValueError('odd prime and normalized basis coordinate required')
        if not isinstance(self.core, ExactOperator) or self.core.p != self.p:
            raise ValueError('core field mismatch')
        if not isinstance(self.blocks, tuple) or any(not isinstance(b, PhaseBlock) or b.p != self.p or b.trivial for b in self.blocks):
            raise ValueError('nontrivial typed phase blocks required')
        if type(self.clifford_products) is not int or type(self.declared_gates) is not int or min(self.clifford_products, self.declared_gates) < 0:
            raise ValueError('nonnegative operation counters required')

    @classmethod
    def start(cls, p, source=0):
        return cls(p, source, ExactOperator.identity(p))

    def after_clifford(self, op, products=1):
        if not isinstance(op, ExactOperator) or op.p != self.p or type(products) is not int or products < 0:
            raise ValueError('matching Clifford and nonnegative product count required')
        blocks = tuple(b.transported(op.m) for b in self.blocks)
        return MovingFrameGround(self.p, self.source, op.compose(self.core), blocks,
                                 self.clifford_products + products + 1, self.declared_gates)

    def after_schedule(self, pattern, steps):
        op, products = ExactSchedule(self.p, tuple(pattern)).navigate(steps)
        return self.after_clifford(op, products)

    def _add_gate(self, new):
        if new.trivial:
            return MovingFrameGround(self.p, self.source, self.core, self.blocks,
                                     self.clifford_products, self.declared_gates + 1)
        if self.blocks and self.blocks[0].axis == new.axis:
            combined = self.blocks[0].combined(new)
            blocks = (() if combined.trivial else (combined,)) + self.blocks[1:]
        else:
            blocks = (new,) + self.blocks
        return MovingFrameGround(self.p, self.source, self.core, blocks,
                                 self.clifford_products, self.declared_gates + 1)

    def after_cubic(self, strength):
        if type(strength) is not int:
            raise ValueError('integer cubic coefficient required')
        return self._add_gate(PhaseBlock(self.p, (0, 1), strength))

    def after_harmonic(self, strength):
        if not isinstance(strength, (int, float)) or isinstance(strength, bool) or not math.isfinite(strength):
            raise ValueError('finite real harmonic coefficient required')
        return self._add_gate(PhaseBlock(self.p, (0, 1), 0, ((1, float(strength)),)))

    @property
    def all_commute(self):
        return all(symplectic(a.axis, b.axis, self.p) == 0
                   for i,a in enumerate(self.blocks) for b in self.blocks[i+1:])

    def estimated_work(self, queries=1):
        """Conservative scalar arithmetic proxy, not wall-clock nor storage bytes."""
        if type(queries) is not int or queries < 1 or queries > self.p:
            raise ValueError('query count in [1,p] required')
        if not self.blocks:
            return queries
        if len(self.blocks) == 1:
            block = self.blocks[0]
            if block.axis == (0, 1):
                return queries * (2 + len(block.harmonics))
            return queries * self.p * (4 + len(block.harmonics))
        # Noncommuting words may need full p-dimensional intermediate states.
        return self.p * self.p * (4 * len(self.blocks) + 1)

    def admission(self, coordinates, max_work):
        if type(max_work) is not int or max_work < 0:
            raise ValueError('nonnegative work budget required')
        coords = tuple(coordinates)
        if not coords or len(set(coords)) != len(coords) or any(type(i) is not int or not 0 <= i < self.p for i in coords):
            raise ValueError('unique normalized output coordinates required')
        cost = self.estimated_work(len(coords))
        return {'status': 'admitted' if cost <= max_work else 'refused_cost',
                'estimated_work': cost, 'budget': max_work, 'coordinates': list(coords),
                'phase_blocks': len(self.blocks), 'all_commute': self.all_commute,
                'scope': 'known symbolic circuit; not evidence of external behavior'}

    def amplitude(self, coordinate, *, max_work=100000):
        if type(coordinate) is not int or not 0 <= coordinate < self.p:
            raise ValueError('normalized integer target required')
        if self.admission((coordinate,), max_work)['status'] != 'admitted':
            raise ValueError('refused: requested output exceeds work budget')
        if not self.blocks:
            return self.core.basis_amplitude(self.source, coordinate).complex_value()
        if len(self.blocks) == 1:
            block = self.blocks[0]
            if block.axis == (0,1):
                return (complex(block.phase([coordinate])[0]) *
                        self.core.basis_amplitude(self.source, coordinate).complex_value())
            a = block.frame()
            inner = a.inverse().compose(self.core)
            terms = (a.basis_amplitude(x, coordinate).complex_value() *
                     complex(block.phase([x])[0]) *
                     inner.basis_amplitude(self.source, x).complex_value()
                     for x in range(self.p))
            return sum(terms)
        return complex(self._dense_via_blocks()[coordinate])

    def _dense_via_blocks(self):
        v = np.array([self.core.basis_amplitude(self.source, x).complex_value()
                      for x in range(self.p)])
        for block in reversed(self.blocks):
            frame = block.frame()
            v = frame.apply_full(block.phase(np.arange(self.p))*frame.inverse().apply_full(v))
        return v

    def record(self):
        return {'p': self.p, 'source': self.source,
                'core': self.core.signature(),
                'blocks': [block.record() for block in self.blocks],
                'clifford_products': self.clifford_products,
                'declared_gates': self.declared_gates, 'all_commute': self.all_commute}


def cubic_echo_strength(op: ExactOperator, previous_coefficient: int):
    """Countergate after `op` that cancels its transported cubic predecessor.

    Exists in the native cubic(Z) family exactly when the transported Z-axis
    stays vertical (matrix top-right b=0). No claim for nonvertical axes.
    """
    if not isinstance(op, ExactOperator) or type(previous_coefficient) is not int:
        raise ValueError('operator and integer coefficient required')
    p = op.p
    b, d = op.m[0][1], op.m[1][1]
    if b:
        raise ValueError('refused: noncommuting Weyl axis; native cubic countergate insufficient')
    return (-previous_coefficient * pow(d, 3, p)) % p


def dense_reference(p, source, events):
    """INDEPENDENT numerical oracle: direct FFT/quadratic chirp, no cocycle code.

    Event op dictionaries: {'kind':'transfer','a':int}, {'kind':'cubic','c':int},
    {'kind':'harmonic','strength':float}, or {'kind':'clifford','op':ExactOperator}.
    The last case uses the operator kernel, so use only for short standalone
    cross-checks of declared general Clifford matrices.
    """
    v = np.zeros(p, dtype=complex)
    v[source] = 1
    x = np.arange(p, dtype=np.int64)
    for event in events:
        kind = event['kind']
        if kind == 'transfer':
            a = event['a']
            v = np.exp(2j*np.pi*((a * x*x) % p)/p) * np.fft.ifft(v)*np.sqrt(p)
        elif kind == 'cubic':
            v = np.exp(2j*np.pi*((event['c'] * (x*x%p)*x) % p)/p) * v
        elif kind == 'harmonic':
            v = np.exp(1j*event['strength']*np.cos(2*np.pi*x/p)) * v
        elif kind == 'clifford':
            v = event['op'].apply_full(v)
        else:
            raise ValueError('unknown dense event kind')
    return v


def first_native_cubic_echo(schedule: ExactSchedule, coefficient: int, *, max_steps=1000):
    """Find earliest positive *sampled* schedule coordinate allowing cubic echo.

    Discovery iterates at most max_steps Clifford updates; it is NOT a
    logarithmic search. When found, subsequent navigation may be logarithmic.
    A refusal means not found in this finite budget, not impossible forever.
    """
    if not isinstance(schedule, ExactSchedule) or type(coefficient) is not int:
        raise ValueError('schedule and integer cubic coefficient required')
    if type(max_steps) is not int or not 1 <= max_steps <= 10000:
        raise ValueError('max_steps in [1,10000] required')
    state = ExactOperator.identity(schedule.p)
    for n in range(1, max_steps + 1):
        a = schedule.pattern[(n - 1) % len(schedule.pattern)]
        state = ExactOperator.transfer(schedule.p, a).compose(state)
        if state.m[0][1] == 0:
            return {'status': 'found', 'coordinate': n,
                    'countergate_cubic': cubic_echo_strength(state, coefficient),
                    'operator_signature': state.signature(),
                    'search_operations': n,
                    'scope': 'earliest within enumerated finite budget, not logarithmic discovery'}
    return {'status': 'not_found_within_budget', 'coordinate': None,
            'countergate_cubic': None, 'search_operations': max_steps,
            'scope': 'finite search, no impossibility claim'}
