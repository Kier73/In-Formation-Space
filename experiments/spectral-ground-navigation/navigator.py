"""SGN-001: witnessed algebraic and empirical navigation of observed series.

Only the algebraic lane has exact long-horizon semantics. Numerical spectral
models carry finite held-out witnesses and refuse unattended long jumps.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
from typing import Mapping

import numpy as np


def _matmul_mod(a, b, modulus):
    n = len(a)
    return [[sum(a[i][k] * b[k][j] for k in range(n)) % modulus
             for j in range(n)] for i in range(n)]


def _power_mod(base, exponent, modulus):
    if exponent < 0 or modulus < 2:
        raise ValueError('nonnegative exponent and modulus >= 2 required')
    n = len(base)
    result = [[int(i == j) for j in range(n)] for i in range(n)]
    multiplies = 0
    while exponent:
        if exponent & 1:
            result = _matmul_mod(result, base, modulus)
            multiplies += 1
        exponent >>= 1
        if exponent:
            base = _matmul_mod(base, base, modulus)
            multiplies += 1
    return result, multiplies


@dataclass(frozen=True)
class ExactWeilGround:
    """Conditional genus-2 Frobenius trace, not a free universal fit.

    Assumes integral characteristic polynomial T^4-e1*T^3+e2*T^2-q*e1*T+q^2.
    Observed power sums s1,s2 determine its coefficients; independent later
    witness traces are required before any navigational method is returned.
    """
    q: int
    coefficients: tuple[int, int, int, int]
    observed: tuple[tuple[int, int], ...]
    witness_digest: str

    @classmethod
    def admit(cls, q: int, s1: int, s2: int, witnesses: Mapping[int, int]):
        if not isinstance(q, int) or q < 2:
            raise ValueError('q must be an integer >= 2')
        e2 = Fraction(s1*s1 - s2, 2)
        if e2.denominator != 1:
            raise ValueError('nonintegral characteristic coefficient')
        coeffs = (int(s1), int(e2), int(q*s1), int(q*q))
        # The functional equation and root radii are declared assumptions;
        # numerical critical-circle checking is a diagnostic, not a proof.
        if not all(k in witnesses for k in (3, 4, 5, 6)):
            raise ValueError('independent witnesses for s3..s6 required')
        observed = tuple(sorted((int(k), int(v)) for k, v in witnesses.items()))
        digest = hashlib.sha256(json.dumps([q, s1, s2, observed],
                                         separators=(',', ':')).encode()).hexdigest()
        ground = cls(q, coeffs, observed, digest)
        for n, truth in observed:
            if n < 3 or n > 1000 or ground._trace(n) != truth:
                raise ValueError(f'Weil witness mismatch at n={n}')
            # Integer-only Weil bound: s_n^2 <= 16*q^n.
            if truth*truth > 16 * pow(q, n):
                raise ValueError(f'Weil magnitude mismatch at n={n}')
        return ground

    def _initial(self):
        a, b, c, d = self.coefficients
        s1 = a
        s2 = a*a - 2*b
        s3 = a*s2 - b*s1 + 3*c
        s4 = a*s3 - b*s2 + c*s1 - 4*d
        return (s1, s2, s3, s4)

    def _trace(self, n):
        if n < 1:
            raise ValueError('n must be positive')
        initial = self._initial()
        if n <= 4:
            return initial[n-1]
        a, b, c, d = self.coefficients
        s = list(initial)
        for _ in range(5, n+1):
            s.append(a*s[-1] - b*s[-2] + c*s[-3] - d*s[-4])
        return s[-1]

    def navigate_mod(self, n: int, modulus: int):
        """Return (s_n mod modulus, number of 4x4 modular products)."""
        if n < 1:
            raise ValueError('n must be positive')
        if modulus < 2:
            raise ValueError('modulus must be >= 2')
        initial = self._initial()
        if n <= 4:
            return initial[n-1] % modulus, 0
        a, b, c, d = self.coefficients
        companion = [[a, -b, c, -d], [1, 0, 0, 0],
                     [0, 1, 0, 0], [0, 0, 1, 0]]
        power, multiplies = _power_mod(companion, n-4, modulus)
        state = [initial[3], initial[2], initial[1], initial[0]]
        return sum(power[0][j]*state[j] for j in range(4)) % modulus, multiplies

    def point_count_mod(self, n: int, modulus: int):
        trace, operations = self.navigate_mod(n, modulus)
        return (pow(self.q, n, modulus) + 1 - trace) % modulus, operations


def _clock(times, name):
    if name == 'linear':
        return times
    if name == 'log':
        return np.log(times)
    if name == 'power-1.5':
        return times ** 1.5
    raise ValueError('unknown clock')


def _gauge(times, name):
    if name == 'none':
        return np.ones_like(times)
    if name == 'sqrt':
        return np.sqrt(times)
    if name == 'decay':
        return np.exp(-0.02 * times)
    raise ValueError('unknown gauge')


def cancellation_hint(values):
    """Histogram character and lag tests; neither diagnoses compressibility.

    Quantisation is deliberately explicit: ordered real-valued state is not
    inferred from a byte histogram. A shuffled series preserves `cancel`.
    """
    v = np.asarray(values, dtype=float)
    if len(v) < 20 or not np.isfinite(v).all():
        raise ValueError('need 20 finite samples')
    spread = float(np.ptp(v))
    x = np.zeros(len(v), dtype=np.uint8) if spread == 0 else np.floor(
        255 * (v-v.min()) / spread).astype(np.uint8)

    def character_score(a):
        hist = np.bincount(a.astype(int), minlength=256)
        return float(np.max(np.abs(np.fft.fft(hist)[1:])) / math.sqrt(len(a)))
    return {'cancel': character_score(x),
            'lag_cancel': max(character_score(((x[d:].astype(int)-x[:-d].astype(int)) % 256).astype(np.uint8))
                              for d in range(1, min(9, len(x)//3))),
            'quantisation': 'per-series min-max to 8 bit; diagnostic only'}


@dataclass
class SpectralGround:
    clock: str
    gauge: str
    rank: int
    circle: bool
    matrix: np.ndarray
    basis: np.ndarray
    last_state: np.ndarray
    u0: float
    step: float
    train_length: int
    validation_steps: int
    validation_count: int
    validation_rmse: float
    baseline_rmse: float
    relative_improvement: float
    condition: float
    preaudit: dict
    data_digest: str
    decision: str

    def predict_normalized(self, k, *, allow_unwitnessed=False):
        """k=1 advances the final training state one warped-clock step.

        A qualified empirical model is NOT a certificate for k beyond the
        witnessed interval. Explicit opt-in enables exploratory predictions.
        """
        if not isinstance(k, (int, np.integer)) or k < 1:
            raise ValueError('k must be an integer >= 1')
        if self.decision != 'qualified' and not allow_unwitnessed:
            raise ValueError('model refused admission')
        if k > self.validation_steps and not allow_unwitnessed:
            raise ValueError('outside held-out witness horizon')
        p = np.linalg.matrix_power(self.matrix, int(k))
        value = self.basis @ (p @ self.last_state)
        return float(np.real(value[-1]))

    def target_time(self, k):
        u = self.u0 + (self.train_length-1 + k)*self.step
        if self.clock == 'linear':
            return u
        if self.clock == 'log':
            return math.exp(u)
        if self.clock == 'power-1.5':
            return u**(2/3)
        raise AssertionError('invalid clock')

    def predict(self, k, *, allow_unwitnessed=False):
        return self.predict_normalized(k, allow_unwitnessed=allow_unwitnessed) * float(
            _gauge(np.array([self.target_time(k)]), self.gauge)[0])

    def receipt(self):
        return {'status': self.decision, 'clock': self.clock, 'gauge': self.gauge,
                'rank': self.rank, 'circle': self.circle,
                'validation_steps': self.validation_steps,
                'validation_count': self.validation_count,
                'validation_rmse': self.validation_rmse,
                'baseline_rmse': self.baseline_rmse,
                'relative_improvement': self.relative_improvement,
                'condition': self.condition, 'preaudit': self.preaudit,
                'data_sha256': self.data_digest,
                'scope': 'finite validation only, not a future guarantee'}


def _fit_delay(y, rank, delay, circle):
    # Each Hankel column is a consecutive oldest-to-newest delay state.
    h = np.lib.stride_tricks.sliding_window_view(y, delay).T.copy()
    x, nxt = h[:, :-1], h[:, 1:]
    u, sigma, vh = np.linalg.svd(x, full_matrices=False)
    if rank > min(len(sigma), np.count_nonzero(sigma > sigma[0]*1e-10)):
        raise ValueError('insufficient effective rank')
    basis, vr = u[:, :rank], vh[:rank, :].T
    mat = (basis.T @ nxt @ vr) / sigma[:rank][None, :]
    if circle:
        eigen, eigenvectors = np.linalg.eig(mat)
        if np.min(np.abs(eigen)) < 1e-8 or np.linalg.cond(eigenvectors) > 1e8:
            raise ValueError('circle projection ill-conditioned')
        mat = eigenvectors @ np.diag(eigen / np.abs(eigen)) @ np.linalg.inv(eigenvectors)
        if np.max(np.abs(mat.imag)) > 1e-7:
            raise ValueError('complex circle projection on real data')
        mat = mat.real
    return basis, mat, basis.T @ h[:, -1], float(sigma[0] / sigma[rank-1])


def fit_spectral(times, values, *, train_count=None, validation_count=None,
                 clocks=('linear', 'log', 'power-1.5'),
                 gauges=('none', 'sqrt', 'decay'), ranks=(2, 4, 6),
                 delay=24, improvement=0.15):
    """Select by a chronologically separate *validation* block, not test.

    Returns a fitted ground, including refused model (never 'no small M exists').
    A second untouched test block is the caller's responsibility.
    """
    t = np.asarray(times, dtype=float)
    v = np.asarray(values, dtype=float)
    if t.ndim != 1 or v.shape != t.shape or len(t) < 90:
        raise ValueError('need >=90 matched scalar observations')
    if np.any(np.diff(t) <= 0) or np.min(t) <= 0 or not np.isfinite(t).all() or not np.isfinite(v).all():
        raise ValueError('positive increasing times and finite values required')
    n = len(t)
    a = train_count if train_count is not None else n*3//5
    b = validation_count if validation_count is not None else n//5
    if a <= delay*2+10 or b < 12 or a+b >= n-8:
        raise ValueError('need separated training, validation and test blocks')
    digest = hashlib.sha256(t[:a+b].astype('<f8').tobytes()+v[:a+b].astype('<f8').tobytes()).hexdigest()
    audit = cancellation_hint(v[:a])
    best = None
    for clock in clocks:
        u_all = _clock(t, clock)
        du = (u_all[a-1]-u_all[0])/(a-1)
        if not np.isfinite(du) or du <= 0:
            continue
        # Require at least twelve independently future-indexed warped steps.
        steps = int((u_all[a+b-1]-u_all[a-1]) / du + 1e-8)
        if steps < 12:
            continue
        steps = min(steps, 120)
        targets = u_all[a-1]+np.arange(1, steps+1)*du
        if targets[-1] > u_all[a+b-1]+1e-8:
            continue
        u_train = u_all[0]+np.arange(a)*du
        for gauge in gauges:
            g = _gauge(t, gauge)
            if np.min(g) < 1e-100 or not np.isfinite(g).all():
                continue
            normalized = v/g
            train = np.interp(u_train, u_all[:a], normalized[:a])
            holdout = np.interp(targets, u_all[:a+b], v[:a+b])
            target_g = np.interp(targets, u_all[:a+b], g[:a+b])
            baseline = float(min(np.sqrt(np.mean((holdout-v[a-1])**2)),
                                 np.sqrt(np.mean((holdout-np.mean(v[:a]))**2))))
            for rank in ranks:
                for circle in (False, True):
                    try:
                        basis, mat, state, condition = _fit_delay(train, rank, delay, circle)
                        predictions = np.array([(basis @ (np.linalg.matrix_power(mat, k) @ state))[-1].real
                                                for k in range(1, steps+1)])
                        if not np.isfinite(predictions).all():
                            continue
                        err = float(np.sqrt(np.mean((predictions*target_g-holdout)**2)))
                    except (ValueError, OverflowError, np.linalg.LinAlgError, FloatingPointError):
                        continue
                    # Score dimensionless validation skill on original units.
                    skill = 1-err/max(baseline, 1e-12)
                    # Tie preference to simpler rank and unconstrained fit.
                    penalty = (0.005 * (clock != 'linear') + 0.005 * (gauge != 'none')
                               + 0.002*(rank-2) + 0.0001*circle)
                    key = (err/max(baseline, 1e-12) + penalty, rank, int(circle))
                    if best is None or key < best[0]:
                        best = (key, clock, gauge, rank, circle, mat, basis, state,
                                float(u_all[0]), float(du), steps, err, baseline, condition)
    if best is None:
        raise ValueError('no numerically valid candidate')
    (_, clock, gauge, rank, circle, mat, basis, state, u0, du,
     steps, err, baseline, condition) = best
    skill = 1-err/max(baseline, 1e-12)
    status = 'qualified' if skill >= improvement and baseline > 1e-9 else 'refused'
    return SpectralGround(clock, gauge, rank, circle, mat, basis, state, u0, du,
                          a, steps, b, err, baseline, skill, condition, audit, digest, status)


def test_report(ground: SpectralGround, times, values, *, max_steps=120):
    """Separate, retrospective assessment; never used to select the candidate.

    Invalidates earlier empirical qualification if evidence shifts. The test
    horizon is observational and does not certify a later, unobserved future.
    """
    t = np.asarray(times, dtype=float)
    v = np.asarray(values, dtype=float)
    if len(t) != len(v) or not np.isfinite(v).all():
        raise ValueError('test needs matched finite observations')
    first = ground.train_length + ground.validation_count
    if first >= len(t)-2:
        raise ValueError('no independent test observations')
    u = _clock(t, ground.clock)
    start = math.ceil((u[first]-u[ground.train_length-1]) / ground.step - 1e-8)
    stop = int((u[-1]-u[ground.train_length-1]) / ground.step + 1e-8)
    indices = range(max(1, start), min(stop, start+max_steps-1)+1)
    indices = tuple(indices)
    if not indices:
        raise ValueError('insufficient test coverage')
    target_u = u[ground.train_length-1]+np.asarray(indices)*ground.step
    truth = np.interp(target_u, u[first:], v[first:])
    predictions = np.asarray([ground.predict(k, allow_unwitnessed=True) for k in indices])
    rmse = float(np.sqrt(np.mean((predictions-truth)**2)))
    baseline = min(float(np.sqrt(np.mean((truth-v[ground.train_length-1])**2))),
                   float(np.sqrt(np.mean((truth-np.mean(v[:ground.train_length]))**2))))
    skill = 1-rmse/max(baseline, 1e-12)
    return {'status': ('corroborated' if ground.decision == 'qualified' and skill >= 0.15
                       else 'failed_out_of_sample'),
            'test_steps': len(indices), 'first_step': indices[0], 'last_step': indices[-1],
            'test_rmse': rmse, 'test_baseline_rmse': baseline,
            'test_relative_improvement': skill,
            'scope': 'retrospective finite test; model selection never saw these values'}