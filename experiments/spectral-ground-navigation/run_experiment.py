"""Deterministic SGN-001 demonstration; prints a machine-readable evidence report."""
import json
import numpy as np
from navigator import ExactWeilGround, fit_spectral, test_report


def run():
    curve = ExactWeilGround.admit(5, 2, -8, {3: 2, 4: -28, 5: -198, 6: -8})
    residue, products = curve.navigate_mod(10**6, 2**61-1)
    result = {'experiment': 'SGN-001', 'curve': {
        'premise': 'genus-2 reciprocal Frobenius characteristic polynomial, assumed',
        'observed_trace': {'1': 2, '2': -8, '3': 2, '4': -28, '5': -198, '6': -8},
        'coefficients': list(curve.coefficients),
        'witness_sha256': curve.witness_digest,
        'n': 10**6, 'modulus': 2**61-1,
        'residue': residue, 'matrix_products': products}, 'series': {}}
    t = np.arange(1., 321.)
    x = .237
    chaos = []
    for _ in t:
        x = 4*x*(1-x)
        chaos.append(x)
    tlog = np.exp(np.linspace(0, 7, 320))
    signals = {
        'oscillator': (t, np.cos(.23*t)+.35*np.sin(.41*t)),
        'chirp': (t, np.sin(.035*t**1.5)),
        'log_amplitude': (tlog, np.sqrt(tlog)*(np.cos(2.3*np.log(tlog))+.35*np.sin(3.4*np.log(tlog)))),
        'dissipative': (t, np.exp(-.02*t)*np.sin(.24*t)),
        'chaotic_logistic': (t, np.asarray(chaos)),
        'noise': (t, np.random.default_rng(2026).normal(size=len(t))),
        'hidden_regime_change': (t, np.where(t<=265, np.sin(.23*t), np.sin(.39*t))),
    }
    for name, (time, values) in signals.items():
        model = fit_spectral(time, values)
        result['series'][name] = {'validation': model.receipt(),
                                  'untouched_test': test_report(model, time, values)}
    return result


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))