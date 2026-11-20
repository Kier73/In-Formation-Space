"""Deterministic witness report for theta/Cayley navigation (TCN-001)."""
import json
import numpy as np
from theta_cayley import admit, independent_test, _phase, plain_fourier_coherence, three_point_quantized


def run():
    p, a, b, c = 127, 17, 31, 7
    rng = np.random.default_rng(912)
    ids = rng.permutation(p)
    train, val, test = ids[:77], ids[77:102], ids[102:]
    truth = _phase(p, a, b, c, np.arange(p))
    observed = truth + 0.17*(rng.normal(size=p)+1j*rng.normal(size=p))
    ground = admit(p, train, observed[train], val, observed[val])
    goal = 19
    roots = ground.goal_coordinates(goal)
    far_index = 10**100 + 123456789
    far_value, products = ground.navigate_cayley(0, far_index, allow_unwitnessed=True)
    random_phases = np.exp(2j*np.pi*np.random.default_rng(233).random(p))
    random_ground = admit(p,train,random_phases[train],val,random_phases[val])
    shifted = truth.copy()
    shifted[test] = _phase(p,3,19,11,test)
    shifted_ground = admit(p,train,shifted[train],val,shifted[val])
    sample3 = _phase(p,a,b,c,[0,1,2])
    noisy3_rng=np.random.default_rng(2026)
    noisy3 = sample3 + .15*(noisy3_rng.normal(size=3)+1j*noisy3_rng.normal(size=3))
    return {
        'experiment': 'TCN-001',
        'family': 'one quadratic additive character over Z/pZ (not arbitrary dynamics)',
        'underlying_coefficients': [a,b,c],
        'observed': ground.receipt(),
        'independent_test': independent_test(ground,test,observed[test]),
        'ordinary_fft_coherence': plain_fourier_coherence(p,train,observed[train]),
        'cayley_generator_real_part': float(ground.cayley_generator().real),
        'cayley_generator_abs': abs(ground.cayley_generator()),
        'large_query': {'index_decimal_digits':len(str(far_index)),
                        'squaring_products': products,
                        'error_against_modular_direct_formula': abs(far_value-ground.predict(far_index,allow_unwitnessed=True)),
                        'status': 'MODEL-CONSISTENT only; not independently measured at distant index'},
        'goal_addressing': {'relative_phase_residue':goal, 'candidate_coordinates':roots,
                           'exact_verification_on_fitted_polynomial': all((ground.a*x*x+ground.b*x)%p==goal for x in roots)},
        'null_control': random_ground.receipt(),
        'hidden_test_regime_change': {'validation':shifted_ground.receipt(),
                                     'test':independent_test(shifted_ground,test,shifted[test])},
        'three_point_clean_coefficients': three_point_quantized(p,sample3),
        'three_point_noisy_coefficients': three_point_quantized(p,noisy3),
        'operation_accounting': {
            'discovery': 'p length-p FFTs per fit and per permutation null; O((R+1)*p^2 log p) floating arithmetic',
            'null_trials': ground.null_trials,
            'oracle_measurements_training': len(train),
            'oracle_measurements_validation': len(val),
            'oracle_measurements_test': len(test),
            'runtime': 'not benchmarked; no claimed speedup over polynomial interpolation on noiseless data',
            'navigation': 'exponent reduced modulo p; O(log p) scalar products for model power, plus coordinate phase reconstruction'
        },
    }


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
