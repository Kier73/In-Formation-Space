"""Compare one vector recurrence with separate source-pinned scalar proofs.

Measures local Python costs in this process; excludes actual TLS, M1/M3,
model-download costs and host trust. No performance-based correctness shortcuts.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time

from temporal_ground import SparseTransfer, prepare, verify_preparation, navigate_verified
from conjugate_ground import ConjugatedGround, prepare_shared, verify_shared, navigate
from test_temporal_ground import make_sparse_fixture


def timed(fun):
    start=time.perf_counter_ns()
    result=fun()
    return result,time.perf_counter_ns()-start


def benchmark(*,n:int=448,fanout:int=8,depth:int=3,tick:int=2**56+73,comparison:bool=True)->dict:
    if not (16<=n<=1024 and 2<=fanout<=16 and 1<=depth<=6 and depth+1<=n):
        raise ValueError('benchmark shape outside declared bounds')
    ground=make_sparse_fixture(n,fanout,137)
    indices=[1]+[max(2,i*n//(depth+1)) for i in range(1,depth+1)]
    if len(set(indices))!=depth+1:
        raise AssertionError('benchmark coordinate collision')
    coordinates=tuple(f'V{i:04d}' for i in indices)
    op=SparseTransfer.from_ground(ground,coordinates[0],coordinates[0])
    model=ConjugatedGround(op,coordinates)
    certificate,prep_ns=timed(lambda:prepare_shared(model))
    _,verify_ns=timed(lambda:verify_shared(model,certificate))
    output,nav_ns=timed(lambda:navigate(model,certificate,tick,trusted_certificate=True))
    report={
        'schema':'ifs.rcg005.shared-vector-benchmark.v1',
        'source':'deterministic-synthetic-graph-not-OpenWorm-biological-simulation',
        'field':op.field, 'dimension':op.n, 'edges':op.sparse_edge_count,
        'depth':depth,'requested_readout_coordinates':list(coordinates),
        'nonlinear_readout_algebraic_degree_upper_bound':2**depth,
        'recurrence_degree':certificate['recurrence_degree'],
        'observed_tick':tick,'polynomial_multiplications':output['polynomial_products'],
        'shared_prepare_ns':prep_ns,'shared_verify_ns':verify_ns,
        'shared_navigation_ns':nav_ns,'output_mod_p':output['nonlinear_readout'],
        'common_vector_annihilator_verified':True,
        'python':platform.python_version(),
        'separate_scalar_comparison_included':comparison,
    }
    if comparison:
        timings=[]
        for target in coordinates:
            scalar=SparseTransfer.from_ground(ground,coordinates[0],target)
            scalar_cert,t1=timed(lambda:prepare(scalar))
            _,t2=timed(lambda:verify_preparation(scalar,scalar_cert))
            scalar_result,t3=timed(lambda:navigate_verified(scalar_cert,tick))
            if scalar_result['value_mod_p']!=output['latent_readouts'][target]:
                raise AssertionError('independent scalar proof disagrees with shared vector recurrence')
            timings.append({'target':target,'degree':scalar_cert['recurrence_degree'],
                            'prepare_ns':t1,'verify_ns':t2,'navigate_ns':t3,
                            'value_mod_p':scalar_result['value_mod_p']})
        report['independent_scalar_observers']=timings
        report['sum_independent_navigation_ns']=sum(t['navigate_ns'] for t in timings)
        report['measured_navigation_ratio_separate_over_shared']=round(
            report['sum_independent_navigation_ns']/nav_ns,3) if nav_ns else None
        report['independent_readout_agreement']=True
    return report


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--nodes',type=int,default=448)
    ap.add_argument('--fanout',type=int,default=8)
    ap.add_argument('--depth',type=int,default=3)
    ap.add_argument('--skip-scalar-comparison',action='store_true')
    ap.add_argument('--out',type=str)
    args=ap.parse_args()
    r=benchmark(n=args.nodes,fanout=args.fanout,depth=args.depth,
                comparison=not args.skip_scalar_comparison)
    txt=json.dumps(r,indent=2,sort_keys=True)+'\n'
    if args.out:
        from pathlib import Path
        f=Path(args.out);f.parent.mkdir(parents=True,exist_ok=True);f.write_text(txt)
    else:
        print(txt)

if __name__=='__main__':
    main()
