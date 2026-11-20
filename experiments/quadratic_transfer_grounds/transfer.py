"""TCN-002: exactly composable quadratic Fourier transfer *rays* over F_p.

T_a = D_a F with F_{y,x}=exp(2*pi*i*x*y/p)/sqrt(p) and
(D_a v)[y]=exp(2*pi*i*a*y*y/p)*v[y].  Only periodic quadratic
phase schedules and basis-vector initial states are handled.  This is a
classical finite-field Clifford/metaplectic (projective) calculation,
NOT generic optimization, quantum hardware, or a claim about the RH proof.

The symplectic representation omits global scalar phase.  Outputs are
rays: relative phase, support and probability are available, but absolute
complex amplitudes are not certified.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
import math
from typing import Mapping

import numpy as np


def _prime(p: int) -> bool:
    return (type(p) is int and p >= 3 and p % 2 == 1
            and all(p % d for d in range(3, math.isqrt(p) + 1, 2)))


def _mm(x, y, p):
    a, b, c, d = x[0][0], x[0][1], x[1][0], x[1][1]
    e, f, g, h = y[0][0], y[0][1], y[1][0], y[1][1]
    return (((a*e+b*g) % p, (a*f+b*h) % p),
            ((c*e+d*g) % p, (c*f+d*h) % p))


_I = ((1, 0), (0, 1))


def _mp(m, n: int, p: int):
    out, count = _I, 0
    while n:
        if n & 1:
            out = _mm(out, m, p)
            count += 1
        n >>= 1
        if n:
            m = _mm(m, m, p)
            count += 1
    return out, count


def _sqrt(n: int, p: int):
    """Tonelli-Shanks for odd prime p. Returns None for a nonresidue."""
    n %= p
    if n == 0:
        return 0
    if pow(n, (p-1)//2, p) != 1:
        return None
    if p % 4 == 3:
        return pow(n, (p+1)//4, p)
    q, s = p-1, 0
    while q % 2 == 0:
        q //= 2
        s += 1
    z = 2
    while pow(z, (p-1)//2, p) != p-1:
        z += 1
    c, x, t, m = pow(z,q,p), pow(n,(q+1)//2,p), pow(n,q,p), s
    while t != 1:
        i, tt = 0, t
        while tt != 1 and i < m:
            tt = tt*tt % p
            i += 1
        if i == m:
            raise ArithmeticError('Tonelli-Shanks invariant')
        power = pow(c, 1 << (m-i-1), p)
        x, t, c, m = x*power % p, t*power*power % p, power*power % p, i
    return x


def _inverse(m, p):
    """Inverse for a determinant-one 2x2 matrix over F_p."""
    a, b = m[0]
    c, d = m[1]
    return ((d % p, -b % p), (-c % p, a % p))


def _prime_factors(n):
    """Distinct prime factors of a small order bound; trial division cost exposed."""
    result = []
    candidate = 2
    while candidate * candidate <= n:
        if n % candidate == 0:
            result.append(candidate)
            while n % candidate == 0:
                n //= candidate
        candidate += 1 if candidate == 2 else 2
    if n > 1:
        result.append(n)
    return result


def _matrix_order(m, p):
    """Exact order in SL(2,F_p), via trace classification.

    Eigenvalues split (order | p-1), nonsplit (order | p+1), or are
    repeated unipotent / negative-unipotent (order | p or 2p).
    """
    trace = (m[0][0] + m[1][1]) % p
    delta = (trace*trace - 4) % p
    if delta == 0:
        bound = p if trace == (2 % p) else 2*p
    elif pow(delta, (p-1)//2, p) == 1:
        bound = p - 1
    else:
        bound = p + 1
    order = bound
    for prime_factor in _prime_factors(bound):
        while order % prime_factor == 0:
            reduced, _ = _mp(m, order//prime_factor, p)
            if reduced != _I:
                break
            order //= prime_factor
    power, _ = _mp(m, order, p)
    if power != _I:
        raise ArithmeticError('invalid order bound or symplectic matrix')
    return order


def _discrete_log_matrix(generator, target, order, p):
    """Baby-step giant-step in the cyclic subgroup <generator>.

    This is finite group search, O(sqrt(order)) group operations/memory,
    NOT a logarithmic inverse, and a target outside the subgroup yields None.
    """
    width = math.isqrt(order) + 1
    babies = {}
    current = _I
    for j in range(width):
        babies.setdefault(current, j)
        current = _mm(generator, current, p)
    negative_jump, _ = _mp(_inverse(generator,p), width, p)
    current = target
    for i in range(width + 1):
        j = babies.get(current)
        if j is not None and i*width + j < order:
            return i*width + j
        current = _mm(negative_jump, current, p)
    return None


@dataclass(frozen=True)
class Ray:
    """Normalized vector only up to a *common global complex phase*.

    ``kind=='delta'`` denotes a basis vector at site.  ``kind=='flat'``
    denotes exp(2*pi*i*(a*x*x+b*x)/p)/sqrt(p).  The latter's phase at
    x=0 is fixed to 1 by convention, not derived from the actual circuit.
    """
    p: int
    kind: str
    site: int | None = None
    a: int | None = None
    b: int | None = None

    def __post_init__(self):
        if not _prime(self.p):
            raise ValueError('ray requires odd prime p')
        if self.kind == 'delta':
            if type(self.site) is not int or self.a is not None or self.b is not None:
                raise ValueError('delta ray requires site and no phase coefficients')
            object.__setattr__(self, 'site', self.site % self.p)
        elif self.kind == 'flat':
            if self.site is not None or type(self.a) is not int or type(self.b) is not int:
                raise ValueError('flat ray requires two phase coefficients and no site')
            object.__setattr__(self, 'a', self.a % self.p)
            object.__setattr__(self, 'b', self.b % self.p)
        else:
            raise ValueError('unsupported ray kind')

    def probability(self, coordinate: int) -> Fraction:
        y = int(coordinate) % self.p
        if self.kind == 'delta':
            return Fraction(int(y == self.site), 1)
        return Fraction(1, self.p)

    def relative_phase_residue(self, x: int, y: int = 0) -> int | None:
        """Phase(x)/phase(y) as pth root; None where either amplitude is 0."""
        if self.kind == 'delta':
            return 0 if x % self.p == self.site and y % self.p == self.site else None
        x, y = x % self.p, y % self.p
        return (self.a*(x*x-y*y) + self.b*(x-y)) % self.p

    def relative_profile(self) -> np.ndarray:
        """Numerical canonical representative; requires O(p) output."""
        if self.kind == 'delta':
            v = np.zeros(self.p, dtype=complex)
            v[self.site] = 1
            return v
        x = np.arange(self.p, dtype=np.int64)
        exponent = (self.a*x*x + self.b*x) % self.p
        return np.exp(2j*np.pi*exponent/self.p) / np.sqrt(self.p)

    def goal_coordinates(self, h: int) -> tuple[int, ...]:
        """Coordinates whose relative phase from coordinate 0 is omega**h.

        A delta ray cannot define a phase relative to coordinate 0
        unless its support is at 0; use its exact support instead.
        """
        if type(h) is not int:
            raise ValueError('integer goal residue required')
        p, h = self.p, h % self.p
        if self.kind == 'delta':
            raise ValueError('delta has no nontrivial relative-phase goal; inspect support')
        a, b = self.a, self.b
        if a == 0:
            if b == 0:
                return tuple(range(p)) if h == 0 else ()
            return (h * pow(b, -1, p) % p,)
        disc = (b*b + 4*a*h) % p
        root = _sqrt(disc, p)
        if root is None:
            return ()
        inv = pow(2*a, -1, p)
        return tuple(sorted({((-b+root)*inv) % p, ((-b-root)*inv) % p}))

    def description(self):
        return {'kind': self.kind, 'p': self.p, 'site': self.site,
                'a': self.a, 'b': self.b, 'global_phase': 'unobserved'}


def ray_from_matrix(p: int, m, source: int):
    """Sends computational basis |source> through a projective symplectic map.

    Only a valid SL(2,F_p) matrix has this interpretation.  No global
    scalar phase is determined by a projective symplectic matrix.
    """
    if not _prime(p) or type(source) is not int:
        raise ValueError('prime field and integer source required')
    try:
        a, b = m[0]
        c, d = m[1]
    except (ValueError, TypeError, IndexError) as exc:
        raise ValueError('2x2 matrix required') from exc
    if any(type(z) is not int for z in (a,b,c,d)) or (a*d-b*c) % p != 1:
        raise ValueError('2x2 determinant-one integer matrix required')
    if b % p == 0:
        return Ray(p, 'delta', site=(a*source) % p)
    inv_b = pow(b, -1, p)
    return Ray(p, 'flat', a=(d*inv_b*pow(2,-1,p)) % p,
               b=(-source*inv_b) % p)


@dataclass(frozen=True)
class Ground:
    """A declared known quadratic transfer schedule, *not* fitted evidence."""
    p: int
    pattern: tuple[int, ...]

    def __post_init__(self):
        if not _prime(self.p):
            raise ValueError('p must be an odd prime')
        if not isinstance(self.pattern, tuple) or not self.pattern:
            raise ValueError('nonempty tuple of quadratic chirp coefficients required')
        if len(self.pattern) > 256 or any(type(a) is not int for a in self.pattern):
            raise ValueError('at most 256 integer chirp coefficients allowed')
        object.__setattr__(self, 'pattern', tuple(a % self.p for a in self.pattern))

    def _one(self, a):
        # J= [[0,-1],[1,0]] for the + Fourier convention;
        # D_a has shear [[1,0],[2a,1]] so D_a * J is below.
        return ((0, self.p-1), (1, (-2*a) % self.p))

    def advance_matrix(self, steps: int):
        """Exact symplectic map with O(L+log steps) 2x2 mod products."""
        if type(steps) is not int or steps < 0:
            raise ValueError('nonnegative Python int step count required')
        n, r = divmod(steps, len(self.pattern))
        count = 0
        if n:
            cycle = _I
            for a in self.pattern:
                cycle = _mm(self._one(a), cycle, self.p)
                count += 1
            power, powers = _mp(cycle, n, self.p)
            count += powers
        else:
            power = _I
        for a in self.pattern[:r]:
            power = _mm(self._one(a), power, self.p)
            count += 1
        if (power[0][0]*power[1][1]-power[0][1]*power[1][0]) % self.p != 1:
            raise ArithmeticError('lost symplectic determinant')
        return power, count

    def navigate(self, steps: int, source: int = 0):
        """Compute phase-space ray for (T_{{a_(n-1)}}...T_{{a0}})^n |source>.

        Exact finite-field state description, not an O(log n) production of a
        p-element vector and not an observation of the outside world.
        """
        if type(source) is not int:
            raise ValueError('source must be an integer basis coordinate')
        m, products = self.advance_matrix(steps)
        return ray_from_matrix(self.p, m, source), m, products


    def operator_period_bound(self):
        """Finite symplectic operator period L*ord(cycle) (may not be least)."""
        cycle = _I
        for a in self.pattern:
            cycle = _mm(self._one(a), cycle, self.p)
        order = _matrix_order(cycle, self.p)
        return len(self.pattern)*order

    def find_operator_coordinate(self, target):
        """Smallest nonnegative step whose symplectic map equals target.

        Enumerates schedule remainders and uses baby-step giant-step on the
        *cycle* operator. Cost O(L*sqrt(ord(C))+L), rather than O(log n).
        This is operator recurrence, NOT a discovery of when an arbitrary
        physical system or observable reaches an intended goal.
        """
        try:
            target = tuple(tuple(row) for row in target)
            if (len(target) != 2 or any(len(row) != 2 for row in target)
                    or any(type(z) is not int for row in target for z in row)):
                raise ValueError('2x2 integer matrix target required')
            target = tuple(tuple(z % self.p for z in row) for row in target)
        except (ValueError, TypeError) as exc:
            raise ValueError('2x2 integer matrix target required') from exc
        if ((target[0][0]*target[1][1]-target[0][1]*target[1][0]) % self.p) != 1:
            raise ValueError('target must have determinant one modulo p')
        cycle = _I
        for a in self.pattern:
            cycle = _mm(self._one(a), cycle, self.p)
        order = _matrix_order(cycle, self.p)
        prefix = _I
        minimum = None
        for r in range(len(self.pattern)):
            # target = prefix_r * cycle^q so cycle^q = prefix_r^-1 * target.
            target_power = _mm(_inverse(prefix, self.p), target, self.p)
            q = _discrete_log_matrix(cycle, target_power, order, self.p)
            if q is not None:
                coordinate = len(self.pattern)*q + r
                if minimum is None or coordinate < minimum:
                    minimum = coordinate
            prefix = _mm(self._one(self.pattern[r]), prefix, self.p)
        return minimum

    def receipt(self, steps: int, source: int = 0):
        ray, m, products = self.navigate(steps, source)
        record = {
            'schema': 'ifs.theta-symplectic-ray.v1',
            'field_modulus': self.p, 'pattern': list(self.pattern),
            'source': source % self.p, 'steps_decimal': str(steps),
            'matrix': [list(m[0]), list(m[1])],
            'matrix_products': products, 'ray': ray.description(),
            'semantics': 'conditional projective ray from declared quadratic schedule',
            'independent_measurement': False,
        }
        record['sha256'] = _digest(record)
        return record


def _digest(record: Mapping) -> str:
    return sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                            allow_nan=False).encode()).hexdigest()


def verify_receipt(record: Mapping):
    """Deterministic recomputation. Digest is *not* authentication/signature."""
    if not isinstance(record, Mapping) or set(record) != {
        'schema', 'field_modulus', 'pattern', 'source', 'steps_decimal',
        'matrix', 'matrix_products', 'ray', 'semantics',
        'independent_measurement', 'sha256'
    }:
        return False
    try:
        raw_steps = record['steps_decimal']
        if (type(raw_steps) is not str or not raw_steps.isascii()
                or not raw_steps.isdigit() or len(raw_steps) > 1000
                or (len(raw_steps) > 1 and raw_steps.startswith('0'))):
            return False
        ground = Ground(record['field_modulus'], tuple(record['pattern']))
        expected = ground.receipt(int(raw_steps), record['source'])
        return dict(record) == expected
    except (ValueError, TypeError, ArithmeticError, OverflowError, KeyError):
        return False


def direct_transfer(p: int, pattern: tuple[int, ...], steps: int, source: int):
    """Independent O(steps*p log(p)) direct complex-FFT reference."""
    if not _prime(p) or type(steps) is not int or steps < 0:
        raise ValueError('invalid direct reference')
    v = np.zeros(p, dtype=complex)
    v[source % p] = 1.0
    x = np.arange(p, dtype=np.int64)
    for n in range(steps):
        v = np.fft.ifft(v) * np.sqrt(p)  # positive sign, norm-preserving
        residues = (pattern[n % len(pattern)]*x*x) % p
        v *= np.exp(2j*np.pi*residues / p)
    return v


def fidelity(ray: Ray, actual) -> float:
    """Phase-insensitive fidelity, 1 iff vectors agree up to global phase."""
    v = np.asarray(actual, dtype=complex)
    if v.shape != (ray.p,) or not np.isfinite(v).all():
        raise ValueError('p finite complex amplitudes required')
    norm = float(np.linalg.norm(v))
    if norm < 1e-12:
        raise ValueError('zero observation')
    return float(min(1., abs(np.vdot(ray.relative_profile(), v/norm))**2))


def diagnose_quadratic_ray(actual, p: int, *, tolerance=1e-7):
    """Pure-state membership diagnostic from a complete complex vector.

    Certifies only algebraic shape of supplied samples at tolerance; it does
    not learn physical laws or establish future reliability. Requires all p
    observed complex entries, and allows an arbitrary common global phase.
    """
    if not _prime(p) or type(tolerance) not in (int,float) or tolerance <= 0:
        raise ValueError('invalid prime or tolerance')
    v = np.asarray(actual, dtype=complex)
    if v.shape != (p,) or not np.isfinite(v).all() or np.linalg.norm(v) < 1e-12:
        raise ValueError('full nonzero finite vector required')
    v = v / np.linalg.norm(v)
    weights = np.abs(v)
    peak = int(np.argmax(weights))
    delta = np.zeros(p, dtype=complex)
    delta[peak] = 1
    if 1-fidelity(Ray(p,'delta',site=peak), v) < tolerance:
        return {'admitted': True, 'kind': 'delta', 'site': peak, 'infidelity': 1-fidelity(Ray(p,'delta',site=peak),v)}
    if np.max(abs(weights - 1/math.sqrt(p))) > tolerance or abs(v[0]) < tolerance:
        return {'admitted': False, 'reason': 'nonflat amplitudes / unsupported ray'}
    r1, r2 = v[1]/v[0], v[2]/v[0]
    def nearest(z):
        coefficient = int(round((np.angle(z) % (2*np.pi)) * p / (2*np.pi))) % p
        if abs(z/abs(z)-np.exp(2j*np.pi*coefficient/p)) > tolerance:
            return None
        return coefficient
    y1, y2 = nearest(r1), nearest(r2)
    if y1 is None or y2 is None:
        return {'admitted': False, 'reason': 'non-pth-root relative phases'}
    a = ((y2-2*y1) * pow(2,-1,p)) % p
    b = (y1-a) % p
    candidate = Ray(p,'flat',a=a,b=b)
    infid = 1-fidelity(candidate,v)
    admitted = infid < tolerance and np.max(abs(v/v[0] - candidate.relative_profile()/candidate.relative_profile()[0])) < 2*tolerance
    return {'admitted': bool(admitted), 'kind': 'flat' if admitted else 'outside_quadratic_family',
            'a': a, 'b': b, 'infidelity': infid}


def quadratic_frame_audit(actual, p: int, *, energy_target=0.99):
    """Explore all quadratic dechirps, then Fourier coefficients.

    For each curvature a, functions omega^(a*x^2+b*x)/sqrt(p) over b
    form an orthonormal basis of C^p.  Report smallest number of such
    modes explaining energy_target of the *supplied* vector's norm.
    This is O(p^2 log p), not a small-cost general compressibility proof.
    No basis is predeclared, so search cost and selection bias matter.
    """
    if not _prime(p) or not 0 < energy_target <= 1:
        raise ValueError('odd prime and target in (0,1] required')
    vec = np.asarray(actual, dtype=complex)
    if vec.shape != (p,) or not np.isfinite(vec).all() or np.linalg.norm(vec)<1e-12:
        raise ValueError('nonzero finite p-vector required')
    vec = vec/np.linalg.norm(vec)
    x = np.arange(p, dtype=np.int64)
    xx = (x*x) % p
    best = None
    for a in range(p):
        demodulated = vec * np.exp(-2j*np.pi*((a*xx) % p)/p)
        coeffs = np.fft.fft(demodulated) / math.sqrt(p)
        energy = np.sort(abs(coeffs)**2)[::-1]
        # Numerical FFT energy may differ from one by a few epsilons.
        cumulative = np.cumsum(energy)
        count = min(p, int(np.searchsorted(cumulative,energy_target-1e-12)+1))
        b = int(np.argmax(abs(coeffs)))
        peak = float(abs(coeffs[b])**2)
        key = (count,-peak,a)
        if best is None or key < best[0]:
            best = (key,a,b,peak,count,float(cumulative[count-1]))
    _, a, b, peak, count, captured = best
    return {'best_curvature':a,'best_frequency':b,
            'best_single_mode_fidelity':peak,
            'modes_for_target':count,'energy_target':float(energy_target),
            'captured_energy':captured,'transform_candidates':p*p,
            'scope':'in-sample orthonormal frame energy; no future or physical guarantee'}
