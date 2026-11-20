"""TCN-008: synthesize a Ground from an intended finite-field phase state.

The intent is a set of exact relative pth-root phase constraints on the output
of a *declared* basis preparation, positive Fourier/quadratic transfer, and
optionally higher-degree diagonal phase gates.  The compiler discovers the
minimal degree, chooses a declared capable host, and creates a reconstructable
mathematical witness. No outside host, state, or permission is authenticated.

For degree < p, polynomial uniqueness gives exact *family-relative* obstructions;
unknown unrequested output coordinates are never claimed to be observed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from cocycle import ExactOperator
from moving_frame import MovingFrameGround
from transfer import _prime

MAX_DEGREE = 5
SCHEMA = 'ifs.intention-ground-synthesis.v1'


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'),
                      allow_nan=False, ensure_ascii=False).encode('utf-8')


def _digest(data):
    return hashlib.sha256(_canonical(data)).hexdigest()


def _integer(value, name, lower=0):
    if type(value) is not int or value < lower:
        raise ValueError(f'{name} must be an integer >= {lower}')
    return value


@dataclass(frozen=True)
class Intent:
    """Desired relative phase residues, anchored to output index zero.

    A missing coordinate is not a physical observation, nor an additional
    constraint. The cost budget is in declared host cost units, not seconds.
    """
    p: int
    constraints: tuple[tuple[int, int], ...]
    max_cost: int

    def __post_init__(self):
        if not _prime(self.p) or not 7 <= self.p <= 1021:
            raise ValueError('supported odd prime must be in [7,1021]')
        _integer(self.max_cost, 'max_cost')
        if not isinstance(self.constraints, tuple) or not self.constraints:
            raise ValueError('nonempty tuple of phase constraints required')
        if any(not isinstance(pair, tuple) or len(pair) != 2 or
               any(type(z) is not int for z in pair) for pair in self.constraints):
            raise ValueError('phase constraints must contain pairs of exact integers')
        if any(not 0 <= x < self.p or not 0 <= r < self.p for x, r in self.constraints):
            raise ValueError('phase residues and coordinates must be canonical')
        if tuple(sorted(self.constraints)) != self.constraints or len({x for x, _ in self.constraints}) != len(self.constraints):
            raise ValueError('constraints must be sorted by distinct coordinate')
        if self.constraints[0] != (0, 0):
            raise ValueError('relative phase at coordinate zero must be 0')

    @property
    def complete(self):
        return len(self.constraints) == self.p

    def spec(self):
        return {'p': self.p, 'constraints': [list(pair) for pair in self.constraints],
                'max_cost': self.max_cost}


@dataclass(frozen=True)
class Host:
    """Declared capabilities, *not* an authenticated E-CPU runtime authority."""
    host_id: str
    max_degree: int
    allowed_sources: tuple[int, ...]
    transfer_cost: int = 1
    preparation_cost: int = 1
    higher_phase_cost: int = 5
    capacity: int = 1000

    def validate(self, p):
        if (not isinstance(self.host_id, str) or not self.host_id or
            len(self.host_id) > 64 or not self.host_id.isascii() or
            any(not (c.isalnum() or c in '-_.:') for c in self.host_id)):
            raise ValueError('invalid host identifier')
        if type(self.max_degree) is not int or not 2 <= self.max_degree <= MAX_DEGREE:
            raise ValueError('host supports degree 2..5')
        if (not isinstance(self.allowed_sources, tuple) or not self.allowed_sources or
            tuple(sorted(set(self.allowed_sources))) != self.allowed_sources or
            any(type(x) is not int or not 0 <= x < p for x in self.allowed_sources)):
            raise ValueError('sorted canonical available sources required')
        for name in ('transfer_cost', 'preparation_cost', 'higher_phase_cost', 'capacity'):
            _integer(getattr(self, name), name)

    def spec(self):
        return {'host_id': self.host_id, 'max_degree': self.max_degree,
                'allowed_sources': list(self.allowed_sources),
                'transfer_cost': self.transfer_cost,
                'preparation_cost': self.preparation_cost,
                'higher_phase_cost': self.higher_phase_cost, 'capacity': self.capacity}


def _polynomial(coefficients, x, p):
    """Horner evaluation in F_p, no floating phase or dense vector needed."""
    result = 0
    for c in reversed(coefficients):
        result = (result * (x % p) + c) % p
    return result


def _interpolate(points, degree, p):
    """Interpolate from first degree+1 distinct x via exact modular elimination."""
    if len(points) < degree + 1:
        return None
    rows = []
    for x, value in points[:degree + 1]:
        rows.append([(pow(x, i, p)) for i in range(degree + 1)] + [value])
    for col in range(degree + 1):
        pivot = next((r for r in range(col, degree + 1) if rows[r][col]), None)
        if pivot is None:
            raise ArithmeticError('distinct-field Vandermonde matrix lost invertibility')
        rows[col], rows[pivot] = rows[pivot], rows[col]
        inv = pow(rows[col][col], -1, p)
        rows[col] = [(v * inv) % p for v in rows[col]]
        for r in range(degree + 1):
            if r != col:
                factor = rows[r][col]
                rows[r] = [(a - factor * b) % p for a, b in zip(rows[r], rows[col])]
    coeffs = tuple(row[-1] for row in rows)
    if all(_polynomial(coeffs, x, p) == v for x, v in points):
        return coeffs
    return None


def _find_law(intent):
    """Try ascending degrees; report an exact mismatch witness if unsupported."""
    points, p = intent.constraints, intent.p
    for degree in range(min(MAX_DEGREE, len(points) - 1) + 1):
        coeffs = _interpolate(points, degree, p)
        if coeffs is not None:
            return tuple(coeffs), degree, None
    if len(points) <= MAX_DEGREE:
        # At most five points always admit some deg<=4 polynomial, so this
        # branch is defensive: no reachability result can be drawn.
        return None, None, {'kind': 'insufficient_specification'}
    # Uniqueness: the first six points fix degree<=5. Any later mismatch
    # rules out the entire supported family, not arbitrary higher degrees.
    partial = _solve_first(points[:MAX_DEGREE + 1], MAX_DEGREE, p)
    failing = next((x, v, _polynomial(partial, x, p)) for x, v in points
                   if _polynomial(partial, x, p) != v)
    return None, None, {'kind': 'degree_bound_witness',
                        'degree_cap': MAX_DEGREE, 'fixed_by': [list(pair) for pair in points[:6]],
                        'first_mismatch': list(failing)}


def _solve_first(points, degree, p):
    """Return exact interpolation polynomial even if later samples disagree."""
    rows = [[pow(x, k, p) for k in range(degree + 1)] + [y] for x, y in points[:degree + 1]]
    for col in range(degree + 1):
        pivot = next(i for i in range(col, degree + 1) if rows[i][col] != 0)
        rows[col], rows[pivot] = rows[pivot], rows[col]
        inv = pow(rows[col][col], -1, p)
        rows[col] = [v*inv % p for v in rows[col]]
        for i in range(degree + 1):
            if i != col:
                factor = rows[i][col]
                rows[i] = [(a-factor*b) % p for a,b in zip(rows[i], rows[col])]
    return tuple(row[-1] for row in rows)


@dataclass(frozen=True)
class SynthesizedGround:
    """An exact declared polynomial-phase state, not an observed system."""
    p: int
    coefficients: tuple[int, ...]
    source: int

    def __post_init__(self):
        if (not _prime(self.p) or not 7 <= self.p <= 1021 or
            not 1 <= len(self.coefficients) <= MAX_DEGREE+1 or
            self.coefficients[0] != 0 or
            any(type(v) is not int or not 0 <= v < self.p for v in self.coefficients) or
            type(self.source) is not int or self.source != (self.coefficients[1] if len(self.coefficients)>1 else 0)):
            raise ValueError('canonical polynomial-phase Ground required')

    @property
    def degree(self):
        return len(self.coefficients)-1

    @property
    def family(self):
        return 'quadratic' if self.degree <= 2 else 'cubic' if self.degree == 3 else 'higher_polynomial'

    def core(self):
        return ExactOperator.transfer(self.p, self.coefficients[2] if self.degree >= 2 else 0)

    def relative_residue(self, coordinate):
        if type(coordinate) is not int:
            raise ValueError('coordinate must be an exact integer')
        return _polynomial(self.coefficients, coordinate, self.p)

    def amplitude(self, coordinate):
        """Exact modular phase construction; complex float only at readout."""
        if type(coordinate) is not int:
            raise ValueError('coordinate must be an exact integer')
        y = coordinate % self.p
        q = self.core().basis_amplitude(self.source, y)
        high = sum(self.coefficients[k]*pow(y,k,self.p) for k in range(3,self.degree+1)) % self.p
        # No loss of integer phase at enormous coordinate values.
        return complex(q.complex_value() * np.exp(2j*np.pi*high/self.p))

    def full_vector(self):
        return np.array([self.amplitude(y) for y in range(self.p)])

    def dense_independent(self):
        """Independent reference: basis source -> positive FFT -> chirp -> phases."""
        p = self.p
        source = np.zeros(p, dtype=np.complex128)
        source[self.source] = 1.0
        vector = np.fft.ifft(source) * math.sqrt(p)
        for y in range(p):
            residue = (self.relative_residue(y) - self.source*y) % p
            vector[y] *= np.exp(2j*np.pi*residue/p)
        return vector

    def legacy_cubic(self):
        """TCN-006 bridge for degrees<=3 (its existing phase-block algebra)."""
        if self.degree > 3:
            raise ValueError('TCN-006 does not support higher polynomial gates')
        ground = MovingFrameGround.start(self.p,self.source).after_clifford(self.core())
        return ground.after_cubic(self.coefficients[3]) if self.degree == 3 else ground

    def spec(self):
        return {'p':self.p,'coefficients':list(self.coefficients),
                'source':self.source,'family':self.family}


def _minimality_witness(intent, degree):
    """Prove degree>=d by contradicting the unique degree<d interpolation.

    The first d distinct coordinates fix every polynomial of degree <=d-1.
    A later disagreement is a complete finite-field obstruction in that family.
    """
    if degree == 0:
        return None
    lower = _solve_first(intent.constraints[:degree], degree-1, intent.p)
    mismatch = next((x,v,_polynomial(lower,x,intent.p)) for x,v in intent.constraints
                    if _polynomial(lower,x,intent.p) != v)
    return {'excluded_degree_at_most':degree-1,
            'fixed_by':[list(pair) for pair in intent.constraints[:degree]],
            'first_mismatch':list(mismatch),
            'scope':'exact under polynomial-degree family only'}


def synthesize(intent: Intent, hosts: tuple[Host, ...]):
    if not isinstance(intent, Intent) or not isinstance(hosts, tuple) or not hosts:
        raise ValueError('intention and nonempty host tuple required')
    for h in hosts:
        if not isinstance(h,Host):
            raise ValueError('host must have typed capabilities')
        h.validate(intent.p)
    if len(set(h.host_id for h in hosts)) != len(hosts):
        raise ValueError('host identities must be unique')
    law, degree, obstruction = _find_law(intent)
    if law is None:
        return {'status':'unreachable_in_degree_5_family','reason':'full constraint set defeats every degree<=5 polynomial',
                'obstruction':obstruction,'ground':None,'selected_host':None,
                'estimated_cost':None,'candidate_host_count':0}
    minimality = _minimality_witness(intent, degree)
    # Normalize polynomial degree-0 source as zero; first coefficient is zero.
    if law[0] != 0:
        raise ArithmeticError('relative phase anchor was lost')
    source = law[1] if len(law)>1 else 0
    ground = SynthesizedGround(intent.p,law,source)
    candidates = []
    supported = 0
    for h in hosts:
        if ground.degree > h.max_degree or source not in h.allowed_sources:
            continue
        supported += 1
        phase_terms = sum(int(law[k]!=0) for k in range(3,len(law)))
        cost = h.transfer_cost + int(source!=0)*h.preparation_cost + phase_terms*h.higher_phase_cost
        if cost <= min(h.capacity,intent.max_cost):
            candidates.append((cost,h.host_id,h))
    if candidates:
        cost,_,host = min(candidates)
        # Fully exact check over the requested mathematical constraints.
        if not all(ground.relative_residue(x)==r for x,r in intent.constraints):
            raise ArithmeticError('synthesized law did not satisfy intention')
        return {'status':'realizable','reason':'declared host can execute the selected polynomial-phase family',
                'ground':ground.spec(),'selected_host':host.host_id,
                'estimated_cost':cost,'candidate_host_count':len(candidates),
                'constraint_count':len(intent.constraints),
                'complete_target':intent.complete,'minimality_witness':minimality,
                'semantic_scope':'all stated phase constraints only; symbolic declared hosts'}
    return {'status':'refused_budget' if supported else 'unreachable_with_declared_hosts',
            'reason':'supported host cost exceeds budget' if supported else 'no host supports phase degree and source preparation',
            'ground':ground.spec(), 'selected_host':None,'estimated_cost':None,
            'candidate_host_count':0,'constraint_count':len(intent.constraints),
            'complete_target':intent.complete,'minimality_witness':minimality,
            'semantic_scope':'declared finite polynomial-phase host family only'}


def make_receipt(intent: Intent, hosts: tuple[Host,...]):
    """Full deterministic reconstruction, SHA-256 is NOT authentication."""
    plan = synthesize(intent,hosts)
    record = {'schema':SCHEMA,'intention':intent.spec(),'hosts':[h.spec() for h in hosts],
              'result':plan,'authenticated_hosts':False,
              'external_realization_witnessed':False,
              'verification':'recompute finite-field construction and all stated constraints'}
    record['sha256'] = _digest(record)
    return record


def verify_receipt(record):
    if not isinstance(record,dict) or set(record) != {'schema','intention','hosts','result',
       'authenticated_hosts','external_realization_witnessed','verification','sha256'} or record.get('schema') != SCHEMA:
        return False
    try:
        i=record['intention']
        if type(i) is not dict or set(i) != {'p','constraints','max_cost'}:
            return False
        if type(i['constraints']) is not list or any(type(x) is not list for x in i['constraints']):
            return False
        intent=Intent(i['p'],tuple(tuple(pair) for pair in i['constraints']),i['max_cost'])
        if type(record['hosts']) is not list:
            return False
        hosts=[]
        for hs in record['hosts']:
            if type(hs) is not dict or set(hs) != {'host_id','max_degree','allowed_sources',
                'transfer_cost','preparation_cost','higher_phase_cost','capacity'} or type(hs['allowed_sources']) is not list:
                return False
            hosts.append(Host(hs['host_id'],hs['max_degree'],tuple(hs['allowed_sources']),
                hs['transfer_cost'],hs['preparation_cost'],hs['higher_phase_cost'],hs['capacity']))
        return record == make_receipt(intent,tuple(hosts))
    except (ValueError,TypeError,ArithmeticError,OverflowError,KeyError):
        return False


def make_intent(p:int, phases, max_cost=1000):
    """Convenient full-state relative phase intention; costs O(p) to read."""
    phases=tuple(phases)
    if len(phases) != p:
        raise ValueError('full-state intention must contain exactly p residues')
    return Intent(p,tuple(enumerate(phases)),max_cost)
