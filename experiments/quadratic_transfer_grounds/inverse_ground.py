"""TCN-007 — intention-directed inverse navigation through a finite quadratic schedule.

An intervention G_g after U_n and a prior G_c is sought with
    G_g U_n G_c = G_target U_n
where all G are native cubic phase gates over F_p.  The identity holds if
U_n maps the native Weyl axis to (0,d) and g+c*d^3=target (mod p).

The inverse problem is solved on the *vector or projective-vector orbit* of
C^q(0,1), where C is the symplectic matrix of one schedule period.  This
uses baby-step/giant-step on an orbit, not enumeration over n, and preserves
TCN-003's exact global Clifford phase by replaying the chosen coordinate.

Mathematical reachability is conditional on the declared finite-field model.
No empirical observation, authenticated host, or physical prediction is made.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from cocycle import ExactSchedule, ExactOperator
from moving_frame import MovingFrameGround, _matvec, canonical_axis
from transfer import _I, _inverse, _mm, _mp, _matrix_order, _prime_factors

_AXIS = (0, 1)


def _normalize(v, p):
    return canonical_axis(v, p)[0]


def _validate_target_vector(v, p):
    if not isinstance(v, (tuple, list)) or len(v) != 2 or any(type(x) is not int for x in v):
        raise ValueError('target must be a 2-element integer Weyl vector')
    v = tuple(x % p for x in v)
    if v == (0, 0):
        raise ValueError('zero Weyl vector cannot be an axis target')
    return v


def _strict_nonnegative(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer')


def _first_at_or_after(start, period, minimum):
    return start if minimum <= start else start + ((minimum - start + period - 1) // period) * period


class _Exhausted(Exception):
    pass


@dataclass
class _Meter:
    max_probes: int
    probes: int = 0
    targets: int = 0

    def check(self):
        if self.probes >= self.max_probes:
            raise _Exhausted
        self.probes += 1


class _OrbitIndex:
    """Index <C> acting on e_z, with exact or scalar-quotiented equality.

    Divisor testing derives the actual orbit period from the order of C.
    A baby table is shared across all prefix-remainder/actuator candidates.
    """
    def __init__(self, cycle, p, projective, max_babies):
        self.cycle, self.p, self.projective = cycle, p, projective
        self.period = _matrix_order(cycle, p)
        for factor in _prime_factors(self.period):
            while self.period % factor == 0:
                mat, _ = _mp(cycle, self.period // factor, p)
                observed = _matvec(mat, _AXIS, p)
                if self._key(observed) != self._key(_AXIS):
                    break
                self.period //= factor
        self.width = min(self.period, math.isqrt(self.period) + 1)
        if self.width > max_babies:
            raise _Exhausted
        self.babies = {}
        v = _AXIS
        for j in range(self.width):
            self.babies.setdefault(self._key(v), j)
            v = _matvec(cycle, v, p)
        negative_jump, _ = _mp(_inverse(cycle, p), self.width, p)
        self.negative_jump = negative_jump
        self.orbit_kind = 'projective_axis' if projective else 'exact_weyl_vector'

    def _key(self, v):
        return _normalize(v, self.p) if self.projective else v

    def solve(self, target, meter):
        """Return smallest q in [0, period) with C^q e_z == target (up to scale)."""
        meter.targets += 1
        current = target
        for i in range((self.period - 1) // self.width + 2):
            meter.check()
            j = self.babies.get(self._key(current))
            q = i * self.width + j if j is not None else self.period
            if q < self.period:
                return q
            current = _matvec(self.negative_jump, current, self.p)
        return None


def _remainder_prefixes(schedule):
    """P_r= T_{r-1}...T_0, for 0<=r<len(pattern)."""
    prefix = _I
    for a in schedule.pattern:
        yield prefix
        prefix = _mm(ExactOperator.transfer(schedule.p, a).m, prefix, schedule.p)


def _bounds(min_step, max_step, max_babies, max_probes):
    _strict_nonnegative(min_step, 'min_step')
    if max_step is not None:
        _strict_nonnegative(max_step, 'max_step')
        if max_step < min_step:
            raise ValueError('max_step must be >= min_step')
    if type(max_babies) is not int or not 1 <= max_babies <= 10000:
        raise ValueError('max_babies must be in [1,10000]')
    if type(max_probes) is not int or not 1 <= max_probes <= 1000000:
        raise ValueError('max_probes must be in [1,1000000]')


def _out(status, *, reason, index=None, candidate=None, meter=None, schedule=None, products=0):
    return {
        'status': status, 'reason': reason,
        'coordinate_decimal': str(candidate['coordinate']) if candidate is not None else None,
        'period': candidate['period'] if candidate else (index.period * len(schedule.pattern) if index else None),
        'orbit_kind': index.orbit_kind if index else None,
        'orbit_width': index.width if index else None,
        'candidate_vectors_examined': candidate.get('vector_candidates') if candidate else None,
        'operator_matrix': [list(row) for row in candidate['operator'].m] if candidate else None,
        'global_quadrant_mod4': candidate['operator'].quadrant if candidate else None,
        'transported_weyl_vector': list(candidate['transport']) if candidate else None,
        'countergate_cubic': candidate.get('gate') if candidate else None,
        'target_cubic': candidate.get('target') if candidate else None,
        'giant_step_probes': meter.probes if meter else 0,
        'orbit_targets_queried': meter.targets if meter else 0,
        'operator_products_at_coordinate': products,
        'scope': 'exact identity for declared finite-field gates; no independent physical observation',
    }


def find_weyl_coordinate(schedule: ExactSchedule, desired_vector, *, projective=True,
                          min_step=0, max_step=None, max_babies=10000,
                          max_probes=100000):
    """Find first n>=min_step with M(n)e_z = desired vector, optionally up to scalar.

    A missing exact vector in the complete orbit is a proved model-relative
    nonreachability.  A search budget exhaustion is *not* nonreachability.
    """
    if not isinstance(schedule, ExactSchedule) or type(projective) is not bool:
        raise ValueError('exact schedule and boolean projective switch required')
    v = _validate_target_vector(desired_vector, schedule.p)
    _bounds(min_step, max_step, max_babies, max_probes)
    meter = _Meter(max_probes)
    try:
        idx = _OrbitIndex(schedule.cycle.m, schedule.p, projective, max_babies)
        best = None
        for r, prefix in enumerate(_remainder_prefixes(schedule)):
            origin = _matvec(_inverse(prefix, schedule.p), v, schedule.p)
            q = idx.solve(origin, meter)
            if q is None:
                continue
            n = _first_at_or_after(q * len(schedule.pattern) + r,
                                   idx.period * len(schedule.pattern), min_step)
            if best is None or n < best:
                best = n
        if best is None:
            return _out('unreachable', reason='desired axis is outside the complete declared orbit',
                        index=idx, meter=meter, schedule=schedule)
        if max_step is not None and best > max_step:
            return _out('outside_window', reason='orbit intersects target, but not in requested time window',
                        index=idx, meter=meter, schedule=schedule)
        op, products = schedule.navigate(best)
        transport = _matvec(op.m, _AXIS, schedule.p)
        if (projective and _normalize(transport, schedule.p) != _normalize(v, schedule.p)) or (
                not projective and transport != v):
            raise ArithmeticError('inverse orbit verification mismatch')
        candidate = {'coordinate': best, 'period': idx.period * len(schedule.pattern),
                     'operator': op, 'transport': transport}
        return _out('found', reason='exact finite-field Weyl orbit identity',
                    candidate=candidate, index=idx, meter=meter, schedule=schedule, products=products)
    except _Exhausted:
        return _out('refused_budget', reason='complete inverse orbit search exceeds explicit budget',
                    meter=meter, schedule=schedule)


def synthesize_native_cubic(schedule: ExactSchedule, incoming_cubic: int, target_cubic: int = 0,
                            *, allowed_controls=None, min_step=1, max_step=None,
                            max_babies=10000, max_probes=100000):
    """Solve G_g U_n G_c = G_t U_n with a *native* cubic control G_g.

    When controls=None, any finite-field strength g is allowed and the
    projective orbit suffices.  Otherwise exact vector orbit search respects
    the finite allowed-strength alphabet.  No control is claimed successful
    on an arbitrary physical process.
    """
    if not isinstance(schedule, ExactSchedule) or type(incoming_cubic) is not int or type(target_cubic) is not int:
        raise ValueError('schedule and integer cubic coefficients required')
    _bounds(min_step, max_step, max_babies, max_probes)
    p = schedule.p
    c, t = incoming_cubic % p, target_cubic % p
    if allowed_controls is not None:
        if (not isinstance(allowed_controls, (tuple, list)) or not allowed_controls
                or len(allowed_controls) > p or any(type(g) is not int for g in allowed_controls)):
            raise ValueError('nonempty bounded integer control alphabet required')
        allowed = tuple(sorted({g % p for g in allowed_controls}))
    else:
        allowed = None
    meter = _Meter(max_probes)
    # Identity prior gate: any coordinate works, with only g=t required.
    if c == 0:
        if allowed is not None and t not in allowed:
            return _out('unreachable', reason='no allowed native control realizes the requested target',
                        meter=meter, schedule=schedule)
        op, products = schedule.navigate(min_step)
        candidate = {'coordinate': min_step, 'period': 1, 'operator': op,
                     'transport': _matvec(op.m, _AXIS, p), 'gate': t, 'target': t,
                     'vector_candidates': 1}
        return _out('found', reason='trivial prior gate; target supplied directly',
                    candidate=candidate, meter=meter, schedule=schedule, products=products)
    try:
        projective = allowed is None
        idx = _OrbitIndex(schedule.cycle.m, p, projective, max_babies)
        if projective:
            wanted = [_AXIS]
        else:
            strengths = set(allowed)
            # Polynomial inversion is over field *amplitudes*, not time.
            wanted = [(0, d) for d in range(1, p) if (t - c * pow(d, 3, p)) % p in strengths]
        best = None
        checked = 0
        for r, prefix in enumerate(_remainder_prefixes(schedule)):
            inverse_prefix = _inverse(prefix, p)
            for v in wanted:
                checked += 1
                q = idx.solve(_matvec(inverse_prefix, v, p), meter)
                if q is None:
                    continue
                n = _first_at_or_after(len(schedule.pattern) * q + r,
                                       len(schedule.pattern) * idx.period, min_step)
                if best is None or n < best:
                    best = n
        if best is None:
            return _out('unreachable', reason='no permitted native cubic actuator lies in the exact orbit',
                        index=idx, meter=meter, schedule=schedule)
        if max_step is not None and best > max_step:
            return _out('outside_window', reason='actuator is reachable but not in the time window',
                        index=idx, meter=meter, schedule=schedule)
        op, products = schedule.navigate(best)
        transport = _matvec(op.m, _AXIS, p)
        if transport[0] != 0 or transport[1] == 0:
            raise ArithmeticError('computed countergate has non-native direction')
        gate = (t - c * pow(transport[1], 3, p)) % p
        if allowed is not None and gate not in allowed:
            raise ArithmeticError('computed countergate outside allowed alphabet')
        # Independent symbolic path through the TCN-006 phase-block compiler.
        compiled = (MovingFrameGround.start(p).after_cubic(c)
                    .after_schedule(schedule.pattern, best).after_cubic(gate))
        if compiled.core != op or len(compiled.blocks) != int(t != 0) or (
                t != 0 and (compiled.blocks[0].axis != _AXIS or compiled.blocks[0].cubic != t)):
            raise ArithmeticError('phase compiler disagrees with inverse construction')
        candidate = {'coordinate': best, 'period': idx.period * len(schedule.pattern),
                     'operator': op, 'transport': transport, 'gate': gate,
                     'target': t, 'vector_candidates': checked}
        return _out('found', reason='native cubic intervention realizes requested algebraic target',
                    candidate=candidate, index=idx, meter=meter, schedule=schedule, products=products)
    except _Exhausted:
        return _out('refused_budget', reason='complete inverse actuator search exceeds explicit budget',
                    meter=meter, schedule=schedule)


def make_receipt(spec):
    """Reconstructable unsigned receipt; decimal coordinates avoid JSON integer loss."""
    if not isinstance(spec, dict) or set(spec) != {
            'p', 'pattern', 'incoming_cubic', 'target_cubic', 'allowed_controls',
            'min_step_decimal', 'max_step_decimal', 'max_babies', 'max_probes'}:
        raise ValueError('complete canonical inverse-program specification required')
    if type(spec['min_step_decimal']) is not str or not spec['min_step_decimal'].isascii() or not spec['min_step_decimal'].isdigit() or len(spec['min_step_decimal']) > 350 or (len(spec['min_step_decimal']) > 1 and spec['min_step_decimal'][0] == '0'):
        raise ValueError('canonical bounded decimal min step required')
    latest = spec['max_step_decimal']
    if latest is not None and (type(latest) is not str or not latest.isascii() or not latest.isdigit() or len(latest) > 350 or (len(latest) > 1 and latest[0] == '0')):
        raise ValueError('canonical bounded decimal max step required')
    if type(spec['pattern']) is not list or not spec['pattern'] or len(spec['pattern']) > 256 or any(type(x) is not int for x in spec['pattern']):
        raise ValueError('canonical periodic chirp pattern required')
    schedule = ExactSchedule(spec['p'], tuple(spec['pattern']))
    if list(schedule.pattern) != spec['pattern']:
        raise ValueError('pattern must be canonical residues')
    controls = spec['allowed_controls']
    if controls is not None and (type(controls) is not list or sorted(set(controls)) != controls or any(type(x) is not int or not 0 <= x < schedule.p for x in controls)):
        raise ValueError('controls must be sorted unique canonical residues')
    if any(type(spec[k]) is not int for k in ('incoming_cubic','target_cubic')):
        raise ValueError('integer cubic coefficients required')
    if not 0 <= spec['incoming_cubic'] < schedule.p or not 0 <= spec['target_cubic'] < schedule.p:
        raise ValueError('cubic coefficients must be canonical residues')
    plan = synthesize_native_cubic(schedule, spec['incoming_cubic'], spec['target_cubic'],
             allowed_controls=controls, min_step=int(spec['min_step_decimal']),
             max_step=int(latest) if latest is not None else None,
             max_babies=spec['max_babies'], max_probes=spec['max_probes'])
    record = {'schema': 'ifs.inverse-native-cubic-ground.v1', 'spec': spec,
              'plan': plan, 'verification': 'deterministic recomputation of declared finite-field circuit',
              'authenticated_observation': False}
    record['sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return record


def verify_receipt(record):
    """Integrity and mathematical reconstruction, never external authentication."""
    if not isinstance(record, dict) or set(record) != {'schema','spec','plan','verification','authenticated_observation','sha256'} or record.get('schema') != 'ifs.inverse-native-cubic-ground.v1':
        return False
    try:
        return record == make_receipt(record['spec'])
    except (TypeError, ValueError, OverflowError, ArithmeticError, _Exhausted):
        return False
