"""RCG-004 repeatable local scale benchmark; synthetic topology, NOT OpenWorm."""
from __future__ import annotations

import argparse
import json
import time

from test_temporal_ground import make_sparse_fixture
from temporal_ground import SparseTransfer,prepare,verify_preparation,navigate_verified


def measure(nodes:int=448,fanout:int=8,seed:int=137,tick:int=2**56+73)->dict:
    if nodes not in (448,768,1024) or fanout!=8:
        raise ValueError('only benchmarked synthetic scenarios are admitted')
    ground=make_sparse_fixture(nodes,fanout,seed)
    target={448:'V0222',768:'V0384',1024:'V0512'}[nodes]
    op=SparseTransfer.from_ground(ground,'V0001',target)
    t0=time.perf_counter_ns()
    certificate=prepare(op)
    t1=time.perf_counter_ns()
    verify_preparation(op,certificate)
    t2=time.perf_counter_ns()
    response=navigate_verified(certificate,tick)
    t3=time.perf_counter_ns()
    return {
        'schema':'ifs.rcg004.local-synthetic-temporal-benchmark.v1',
        'kind':'deterministic synthetic graph, NOT original OpenWorm',
        'nodes':nodes,'edges':op.sparse_edge_count,'field':op.field,
        'recurrence_degree':certificate['recurrence_degree'],
        'prepared_samples':certificate['preparation_terms'],
        'tick':tick,'value_mod_p':response['value_mod_p'],
        'polynomial_products':response['polynomial_products'],
        'preparation_ns':t1-t0,'source_certification_ns':t2-t1,
        'distant_query_ns':t3-t2,
        'scope':'local Python; excludes network, model training and original biological dynamics',
    }


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--nodes',type=int,choices=(448,768,1024),default=448)
    parser.add_argument('--tick',type=int,default=2**56+73)
    args=parser.parse_args()
    print(json.dumps(measure(args.nodes,tick=args.tick),indent=2,sort_keys=True))
