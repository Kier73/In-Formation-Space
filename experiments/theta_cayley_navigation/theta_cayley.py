"""TCN-001: partial-observation quadratic-phase discovery and conditional navigation.

A full scan of p^2 candidate (curvature, frequency) pairs is performed through
p padded FFTs. Discovery is NOT logarithmic or a generic optimizer. Once a
quadratic phase law is established as a *hypothesis*, its navigation can be.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

import numpy as np


def _prime(p: int) -> bool:
    if not isinstance(p, int) or p < 3 or p % 2 == 0:
        return False
    return all(p % d for d in range(3, math.isqrt(p) + 1, 2))


def _read(p: int, indices, values):
    x = np.asarray(indices)
    y = np.asarray(values, dtype=np.complex128)
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or not len(x):
        raise ValueError('matched nonempty 1D indices/values required')
    if not np.issubdtype(x.dtype, np.integer):
        raise ValueError('indices must be integers')
    if np.any(x < 0) or np.any(x >= p) or len(np.unique(x)) != len(x):
        raise ValueError('indices must be unique in [0,p)')
    if not np.isfinite(y).all() or np.any(np.abs(y) < 1e-12):
        raise ValueError('finite nonzero complex measurements required')
    return x.astype(np.int64), y / np.abs(y)


def _phase(p: int, a: int, b: int, c: int, x):
    """Return pth-root phases; reduce integer indices before float conversion."""
    # Reduce arbitrary-size Python integer coordinates BEFORE fixed-width conversion.
    v = np.asarray([int(i) % p for i in x], dtype=np.int64)
    residues = (a * (v*v % p) + b*v + c) % p
    return np.exp(2j*np.pi*residues/p)


def _peak_scan(p: int, x: np.ndarray, phasors: np.ndarray):
    """Max correlation with e_p(a*x*x+b*x) across the entire p^2 family.

    One complex FFT per curvature a; zeros for unobserved coordinates.
    FFT is a classical computation over the entire supplied observation set.
    """
    a = np.arange(p, dtype=np.int64)[:, None]
    xx = (x*x) % p
    chirp = np.exp(-2j*np.pi*((a*xx[None, :]) % p)/p)
    padded = np.zeros((p, p), dtype=np.complex128)
    padded[:, x] = chirp * phasors[None, :]
    fourier = np.fft.fft(padded, axis=1)
    ai, bi = np.unravel_index(np.abs(fourier).argmax(), fourier.shape)
    coefficient = fourier[ai, bi] / len(x)
    return int(ai), int(bi), float(abs(coefficient)), float(np.angle(coefficient))


def _phasor_rmse(pred, truth):
    return float(np.sqrt(np.mean(np.abs(pred - truth)**2)))


@dataclass(frozen=True)
class QuadraticGround:
    p: int
    a: int
    b: int
    c: int
    training_count: int
    training_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    training_coherence: float
    permutation_pvalue: float
    permutation_null_max: float
    validation_rmse: float
    baseline_rmse: float
    validation_skill: float
    decision: str
    observed_digest: str
    null_trials: int

    def predict(self, index: int, *, allow_unwitnessed=False):
        """Unit-modulus phase at any integer index; unobserved queries opt in."""
        if not isinstance(index, (int, np.integer)):
            raise ValueError('index must be an integer')
        if self.decision != 'qualified' and not allow_unwitnessed:
            raise ValueError('refused ground; explicit hypothesis opt-in required')
        if index % self.p not in self.validation_indices and not allow_unwitnessed:
            raise ValueError('unwitnessed coordinate; explicit hypothesis opt-in required')
        return complex(_phase(self.p, self.a, self.b, self.c, [index])[0])

    def cayley_generator(self):
        """Complex scalar skew-Hermitian generator S=(1-U)/(1+U)."""
        lam = complex(np.exp(2j*np.pi*self.b/self.p))
        return (1-lam)/(1+lam)

    def navigate_cayley(self, start: int, steps: int, *, allow_unwitnessed=False):
        """Dechirp, advance by the Cayley unitary, and re-chirp.

        The fitted quadratic is a *model*, not a claim about all future data.
        The periodic fitted model permits steps mod p; squaring count recorded.
        """
        if not isinstance(start, int) or not isinstance(steps, int) or steps < 0:
            raise ValueError('integer start and nonnegative steps required')
        destination = (start+steps) % self.p
        if self.decision != 'qualified' and not allow_unwitnessed:
            raise ValueError('refused ground')
        if destination not in self.validation_indices and not allow_unwitnessed:
            raise ValueError('unwitnessed coordinate')
        s = self.cayley_generator()
        unit = (1-s)/(1+s)
        remaining = steps % self.p
        power = complex(1)
        products = 0
        while remaining:
            if remaining & 1:
                power *= unit
                products += 1
            remaining >>= 1
            if remaining:
                unit *= unit
                products += 1
        z0 = complex(_phase(self.p, 0, self.b, self.c, [start])[0])
        xfinal = destination
        chirp = complex(_phase(self.p, self.a, 0, 0, [xfinal])[0])
        return chirp * power * z0, products

    def goal_coordinates(self, target_residue: int):
        """Solve a*x^2+b*x == target_residue (mod p), relative to fitted c.

        Deterministic algebraic roots of the FITTED model, not ground truth.
        Uses Tonelli-Shanks for odd prime fields.
        """
        if self.decision != 'qualified':
            raise ValueError('refused ground')
        if not isinstance(target_residue, int):
            raise ValueError('integer target residue required')
        p, a, b, h = self.p, self.a, self.b, target_residue % self.p
        if a == 0:
            if b == 0:
                return tuple(range(p)) if h == 0 else ()
            return (h * pow(b, -1, p) % p,)
        disc = (b*b + 4*a*h) % p
        root = _sqrt_mod(disc, p)
        if root is None:
            return ()
        inv = pow(2*a, -1, p)
        return tuple(sorted({((-b+root)*inv) % p, ((-b-root)*inv) % p}))

    def receipt(self):
        return {'decision': self.decision, 'p': self.p, 'quadratic': [self.a, self.b, self.c],
                'training_count': self.training_count,
                'validation_count': len(self.validation_indices),
                'training_coherence': self.training_coherence,
                'permutation_pvalue': self.permutation_pvalue,
                'permutation_null_max': self.permutation_null_max,
                'null_trials': self.null_trials, 'validation_rmse': self.validation_rmse,
                'baseline_rmse': self.baseline_rmse,
                'validation_skill': self.validation_skill, 'observed_sha256': self.observed_digest,
                'scope': 'finite partial observations, inferred model only; exact modular navigation is conditional'}


def _sqrt_mod(n, p):
    """Tonelli-Shanks modular square root; None if n is a nonresidue."""
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
    c = pow(z, q, p)
    x = pow(n, (q+1)//2, p)
    t = pow(n, q, p)
    m = s
    while t != 1:
        i, tt = 0, t
        while tt != 1 and i < m:
            tt = tt*tt % p
            i += 1
        if i >= m:
            raise ArithmeticError('Tonelli-Shanks invariant')
        b = pow(c, 1 << (m-i-1), p)
        x = x*b % p
        t = t*b*b % p
        c = b*b % p
        m = i
    return x


def admit(p, train_indices, train_values, validation_indices, validation_values,
          *, null_trials=39, seed=2031, coherence_floor=0.65,
          validation_ceiling=0.65, improvement_floor=0.3, significance=0.05):
    """Fit a single quadratic character, reject weak evidence (not impossible).

    Null permutation tests MAX over p^2 candidate lifts on every trial, so
    look-elsewhere is included for the scanned model family. The null assumes
    phase/index exchangeability, not guaranteed under every physical process.
    """
    if not _prime(p) or p > 1021:
        raise ValueError('odd prime p in [3,1021] required')
    if not isinstance(null_trials, int) or null_trials < 19:
        raise ValueError('at least 19 permutations required')
    x, y = _read(p, train_indices, train_values)
    vx, vy = _read(p, validation_indices, validation_values)
    if len(x) < max(16, p//3) or len(vx) < max(8, p//12):
        raise ValueError('insufficient partial observations')
    if set(x).intersection(set(vx)):
        raise ValueError('validation indices must not occur in training')
    a, b, peak, angle = _peak_scan(p, x, y)
    c = int(np.round(angle * p / (2*np.pi))) % p
    observed_digest = hashlib.sha256(
        x.astype('<i8').tobytes() + y.astype('<c16').tobytes()
        + vx.astype('<i8').tobytes() + vy.astype('<c16').tobytes()).hexdigest()
    rng = np.random.default_rng(seed)
    nulls = [_peak_scan(p, x, rng.permutation(y))[2] for _ in range(null_trials)]
    pvalue = (1 + sum(z >= peak-1e-12 for z in nulls)) / (null_trials+1)
    predicted = _phase(p, a, b, c, vx)
    err = _phasor_rmse(predicted, vy)
    const = np.exp(1j*np.angle(np.mean(y)))
    baseline = _phasor_rmse(np.full(len(vx), const), vy)
    skill = 1-err/max(baseline, 1e-12)
    decision = ('qualified' if peak >= coherence_floor and pvalue <= significance
                and err <= validation_ceiling and skill >= improvement_floor else 'refused')
    return QuadraticGround(p, a, b, c, len(x), tuple(int(i) for i in x),
                           tuple(int(i) for i in vx),
                           peak, pvalue, max(nulls), err, baseline, skill,
                           decision, observed_digest, null_trials)


def independent_test(ground, indices, values):
    """Untouched test: no candidate tuning, no refitting, no retroactive admission."""
    x, y = _read(ground.p, indices, values)
    if set(x).intersection(set(ground.validation_indices) | set(ground.training_indices)):
        raise ValueError('independent test overlaps training or validation')
    prediction = _phase(ground.p, ground.a, ground.b, ground.c, x)
    err = _phasor_rmse(prediction, y)
    return {'test_rmse': err, 'status': 'corroborated' if ground.decision == 'qualified'
            and err <= 0.65 else 'failed_out_of_sample',
            'scope': 'retrospective withheld observations; not a future guarantee'}


def plain_fourier_coherence(p, x, y):
    x, y = _read(p, x, y)
    padded = np.zeros(p, dtype=np.complex128)
    padded[x] = y
    return float(np.max(np.abs(np.fft.fft(padded)))/len(x))


def three_point_quantized(p: int, values_at_0_1_2):
    """Cheap algebraic baseline (3 queries), exact only for noiseless pth roots.

    Quantization before finite differences is *not* a robust estimator.
    The complete array of sampled x=0,1,2 phases must be independently given.
    """
    if not _prime(p):
        raise ValueError('odd prime required')
    v = np.asarray(values_at_0_1_2, dtype=np.complex128)
    if v.shape != (3,) or not np.isfinite(v).all() or np.any(np.abs(v) < 1e-12):
        raise ValueError('three nonzero finite phases at x=0,1,2 required')
    residues = np.rint(np.angle(v) * p / (2*np.pi)).astype(np.int64) % p
    c = int(residues[0])
    a = int((residues[2] - 2*residues[1] + residues[0])*pow(2,-1,p) % p)
    b = int((residues[1] - residues[0] - a) % p)
    return a,b,c
