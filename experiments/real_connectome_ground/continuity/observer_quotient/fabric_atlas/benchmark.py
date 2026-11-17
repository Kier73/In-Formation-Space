"""Reproducible bounded RCG-007 scale evidence; includes cold proof costs."""
from __future__ import annotations
import argparse,hashlib,json,statistics,time
from pathlib import Path
from connectome_ground import ConnectomeGround
from observer_quotient import ExpandedSyntheticGround,discover
from atlas import prepare_atlas,verify_atlas,execute_batch

FIXTURE='''Source,Target,Weight,Type
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

def run(raw:bytes,*,groups:int=16,copies:int=8192,count:int=64,fixture:bool=False)->dict:
    t=time.perf_counter()
    source=ConnectomeGround.from_csv(raw,require_original=not fixture)
    op=ExpandedSyntheticGround(source,groups=groups,copies=copies,seed=73)
    init_ms=(time.perf_counter()-t)*1000
    t=time.perf_counter();cert=discover(op);learn_ms=(time.perf_counter()-t)*1000
    t=time.perf_counter();atlas=prepare_atlas(op,cert);prep_ms=(time.perf_counter()-t)*1000
    t=time.perf_counter();trusted=verify_atlas(op,cert,atlas);proof_ms=(time.perf_counter()-t)*1000
    n=cert['class_count']; p=op.field; tick=2**56+73
    batch=[]
    for j in range(count):
        kind=[{'kind':'class','index':j%n},
              {'kind':'linear','weights':[int(v==j%n or v==(j+3)%n) for v in range(n)]},
              {'kind':'sum_squares','indices':[j%n,(j+3)%n,(j+7)%n]},
              {'kind':'shear_pair','left':j%n,'right':(j+1)%n,'gain':(j+11)%p or 1}][j%4]
        batch.append({'tick':tick,'sources':[[j*19%op.n,1],[j*37%op.n,7],[j*19%op.n,9]],'readout':kind})
    samples=[]
    for _ in range(5):
        t=time.perf_counter();answer=execute_batch(op,cert,atlas,batch,trusted=trusted)
        samples.append((time.perf_counter()-t)*1000)
    assert len(answer['values'])==count
    return {'schema':'ifs.rcg007.benchmark.v1','source_sha256':hashlib.sha256(raw).hexdigest(),
            'source_evidence':'explicit-compact-fixture' if fixture else 'pinned-original-OpenWorm',
            'microstates':op.n,'generated_edges':8*op.n,'observer_classes':n,
            'quotient_certificate_bytes':len(json.dumps(cert,separators=(',',':'),sort_keys=True).encode()),
            'atlas_certificate_bytes':len(json.dumps(atlas,separators=(',',':'),sort_keys=True).encode()),
            'query_count':count,'logical_tick':tick,'polynomial_products':answer['polynomial_products'],
            'cold_source_index_ms':round(init_ms,3),'learn_quotient_ms':round(learn_ms,3),
            'prepare_universal_annihilator_ms':round(prep_ms,3),
            'independent_proof_ms':round(proof_ms,3),
            'batch_query_ms_samples':[round(z,3) for z in samples],
            'batch_query_ms_median':round(statistics.median(samples),3),
            'values_digest':hashlib.sha256(json.dumps(answer['values']).encode()).hexdigest(),
            'intermediate_microstate_vectors':0,
            'scope':'synthetic finite-field work, not measured network or hardware-independent compute'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--fixture',action='store_true')
    parser.add_argument('--source',type=Path)
    parser.add_argument('--groups',type=int,default=16)
    parser.add_argument('--copies',type=int,default=8192)
    parser.add_argument('--count',type=int,default=64)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.fixture:
        raw=FIXTURE.encode()
    elif args.source is not None:
        raw=args.source.read_bytes()
    else:raise ValueError('pinned original source required or explicit --fixture')
    report=run(raw,groups=args.groups,copies=args.copies,count=args.count,fixture=args.fixture)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()