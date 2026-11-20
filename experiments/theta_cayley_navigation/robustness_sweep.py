"""Finite-seed noise sweep: phase law, relative gauge, and admission diverge."""
import json
import numpy as np
from theta_cayley import _phase, admit, independent_test


def run():
    p=127
    results=[]
    for sigma in (0,0.17,0.45,0.8,1.5):
        row=[]
        for seed in range(30,38):
            rng=np.random.default_rng(seed)
            ids=rng.permutation(p)
            x,vx,tx=ids[:77],ids[77:102],ids[102:]
            y=_phase(p,17,31,7,np.arange(p))
            if sigma:
                y+=sigma*(rng.normal(size=p)+1j*rng.normal(size=p))
            g=admit(p,x,y[x],vx,y[vx],seed=731)
            report=independent_test(g,tx,y[tx])
            row.append({'qualified':g.decision=='qualified','a_b_correct':(g.a,g.b)==(17,31),
                        'c_correct':g.c==7, 'test_corroborated':report['status']=='corroborated',
                        'validation_rmse':g.validation_rmse})
        results.append({'noise_sigma':sigma,'seeds':list(range(30,38)),
                        'qualified':sum(t['qualified'] for t in row),
                        'curvature_frequency_correct':sum(t['a_b_correct'] for t in row),
                        'absolute_offset_correct':sum(t['c_correct'] for t in row),
                        'test_corroborated':sum(t['test_corroborated'] for t in row),
                        'median_validation_rmse':float(np.median([t['validation_rmse'] for t in row]))})
    return {'experiment':'TCN-001-noise-sweep','trials_per_sigma':8,
            'scope':'synthetic F_127 quadratic characters, these deterministic seeds only',
            'warning':'relative phase law can survive when absolute phase offset is misquantized',
            'results':results}


if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
