"""RCG-006 separated source/learning/proof/query cost report (not a network benchmark)."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import time
from connectome_ground import ConnectomeGround
from observer_quotient import ExpandedSyntheticGround,discover,verify,quotient_at

FIXTURE = '''Source,Target,Weight,Type
AWCL,ASER,1,chemical
AWCL,AWCR,11,chemical
AWCL,AIYL,22,chemical
AWCL,AIBL,12,chemical
ASER,AIYL,9,chemical
ASER,AIBR,32,chemical
ASIL,AIYL,3,chemical
ASIL,AWCL,3,chemical
AWCR,AIYL,12,chemical
AFDL,AIYL,25,chemical
'''


def run(*, source: ConnectomeGround, groups: int=16,
        copies: int=4096,seed: int=73,query_count:int=8) -> dict:
    if type(query_count) is not int or not 1<=query_count<=16:
        raise ValueError('query count outside bounded benchmark')
    t=time.perf_counter_ns();micro=ExpandedSyntheticGround(source,groups=groups,copies=copies,seed=seed)
    construction=time.perf_counter_ns()-t
    t=time.perf_counter_ns();certificate=discover(micro)
    discovery=time.perf_counter_ns()-t
    t=time.perf_counter_ns();audited=verify(micro,certificate,replay_observations=True)
    verification=time.perf_counter_ns()-t
    source_picks=sorted(set([0,1,micro.n//3,micro.n//2,micro.n-1]+[
        (i*7919+1237)%micro.n for i in range(query_count)]))[:query_count]
    results=[]
    for source_micro in source_picks:
        t=time.perf_counter_ns()
        receipt=quotient_at(micro,certificate,source_micro,2**56+73,depth=6,trusted=audited)
        elapsed=time.perf_counter_ns()-t
        results.append({"source_micro":source_micro,"source_class":receipt['source_observer_class'],
                        "value_mod_p":receipt['neural_result']['nonlinear_readout'],
                        "navigation_ns":elapsed,
                        "polynomial_products":receipt['neural_result']['polynomial_products']})
    cert_bytes=len(json.dumps(certificate,sort_keys=True,separators=(',',':'),
                              ensure_ascii=False).encode())
    return {
        "schema":"ifs.rcg006.benchmark.v1",
        "source_ground":source.fingerprint,"source_blob":source.source_blob,
        "source_is_original_openworm_release":source.source_id != 'local-fixture',
        "synthetic_expansion":micro.description,"observed_classes":certificate['class_count'],
        "training_horizon":certificate['training_horizon'],
        "retained_certificate_bytes":cert_bytes,
        "compressed_partition_base64_bytes":len(certificate['partition_deflate_b64']),
        "synthetic_directed_edge_records_defined":8*micro.n,
        "eager_micro_edge_table_stored":False,
        "timing_ns":{"construction":construction,"observation_discovery":discovery,
                     "independent_full_edge_and_observation_replay":verification},
        "queries":results,
        "comparison_scope":"exact mathematical intertwining for all finite-field initial vectors and all ticks; synthetic generated network",
        "non_claims":"no trained neural parameters, no pretrained AI performance, no native E-CPU/TLS network measurement, no unbounded physical-free computation",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path)
    p.add_argument('--fixture',action='store_true',help='only use the checked-in small source-row fixture')
    p.add_argument('--groups',type=int,default=16)
    p.add_argument('--copies',type=int,default=4096)
    p.add_argument('--seed',type=int,default=73)
    p.add_argument('--query-count',type=int,default=8)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.fixture==bool(a.source):
        p.error('choose exactly one: --fixture or --source ORIGINAL_CSV')
    ground=ConnectomeGround.from_csv(FIXTURE.encode(),require_original=False) if a.fixture else \
        ConnectomeGround.from_csv(a.source.read_bytes(),require_original=True)
    report=run(source=ground,groups=a.groups,copies=a.copies,seed=a.seed,query_count=a.query_count)
    encoded=json.dumps(report,sort_keys=True,indent=2)+'\n'
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(encoded)
    else:
        print(encoded)


if __name__=='__main__':
    main()
