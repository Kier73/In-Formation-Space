"""CIG-029A measured source-qualified ordinal reuse; independent marker oracle."""
import argparse,json,random
from math import lcm
from run_disjunctive_time import fold
from run_output_time import fixture,circuit_source
from run_temporal_ground import timed,size
from inverse_time import spatial_groups
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_ground import Navigator
from verify_temporal_ground import Receiver
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank
from partial_rank import PartialRank
from rank_anchors import Anchors
from verify_rank_anchors import CheckedAnchors


def trial(k, count=32):
    _,_,_,_,ts,g,p,f,initial,P,start,_,markers,desired=fixture(k)
    periods=[len(z) for z in spatial_groups(p)]
    parity=fold('xor',[a for a,b in markers])
    n,s,q,fs=circuit_source(k,[parity]);dec,ct=timed(synthesize_shared,n,s,q,fs)
    assert dec['status']=='COMPLETE' and all(x['status']=='SUFFICIENT' for x in dec['goals'])
    sec,st=timed(compile_section,n,s,q);rec,rt=timed(Receiver,n,s,q,fs,dec,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,dec)
    (d,r),cm=timed(compile_algebra,nav,initial);ad,vm=timed(Admission,rec,r);lang=Language(d,r);assert r['cutoff']==0
    # Independently derived marker parity inclusion-exclusion (not MDD).
    weights={1:1}
    for L in periods:
        new=weights.copy()
        for m,v in weights.items():z=lcm(m,L);new[z]=new.get(z,0)-2*v
        weights={m:v for m,v in new.items() if v}
    def oracle(t):return (t-sum(v*((t-1-desired%m)//m+1) for m,v in weights.items()))//2
    full,ft=timed(Rank,lang,0);checked,fvt=timed(CheckedRank,ad,full.packet());assert full.total==oracle(P)
    x,pt=timed(Anchors,lang,0);v,vt=timed(CheckedAnchors,ad,0)
    phase=P//3;seed,sp=timed(x.seed,phase,exact=full);ok,sv=timed(v.admit_seed,seed);assert ok;x.commit_seed(seed);assert int(seed['rank'])==oracle(phase)
    center=int(seed['rank']);rng=random.Random(2929);width=min(32,max(1,full.total//10));targets=[10**900*full.total+(rng.randrange(1000))*full.total+max(1,min(full.total,center+rng.randint(-width,width))) for _ in range(count)]
    baseline=[];local=[];base_ms=base_verify=local_ms=local_verify=0.;scans=0;max_steps=0
    # No seed: expose whether the exact interior point is reachable under the same small budget.
    cold=Anchors(lang,0);cv=CheckedAnchors(ad,0);cold_r,cms=timed(cold.select,targets[0],budget=128);assert cv.admit_select(targets[0],cold_r,budget=128)
    for j in targets:
        b,bms=timed(full.select,j);ok,bvs=timed(checked.verify_select,j,b);assert ok
        z,zms=timed(x.compact,j,budget=128);got,zvs=timed(v.admit_compact,j,z,budget=128);assert got is not None
        x.commit(z);assert got['status']=='FOUND' and got['time']==b['time'];t=int(got['time']);assert oracle(t)==j-1 and oracle(t+1)==j
        base_ms+=bms;base_verify+=bvs;local_ms+=zms;local_verify+=zvs;scans+=z['steps'];max_steps=max(max_steps,z['steps']);baseline.append(size(b));local.append(size(z))
    assert x.anchors==v.anchors
    # Additional rank queries near the seed in a different huge period.
    compare_exact=compare_decisive=0
    for j in range(32):
        t=(10**900+1001)*P+max(0,min(P-1,phase+rng.randrange(-128,129)));e=oracle(t)
        z=x.compare(t,e+(-1 if j%2 else 1));assert v.verify_compare(t,e+(-1 if j%2 else 1),z);assert int(z['lower'])<=e<=int(z['upper']);compare_exact+=z['status']=='EXACT';compare_decisive+=z['status']!='UNKNOWN'
    # A cold anchor-only ordinal can acquire progress without publishing a result.
    cold.commit(cold_r);assert cold.anchors==cv.anchors
    # Arbitrary distant queries remain honest under a bounded local scan.
    far_phase=P*5//6;far_rank=oracle(far_phase);far=10**900*full.total+max(1,far_rank)
    zz,far_ms=timed(x.select,far,budget=128);assert v.admit_select(far,zz,budget=128);x.commit(zz)
    return dict(n=n,observed=k,period=str(P),signed_terms=len(full.terms),source_prepare_ms=ct+st+rt+cm+vm,full_prepare_ms=ft,full_verify_prepare_ms=fvt,anchor_prepare_ms=pt,anchor_verify_prepare_ms=vt,seed_ms=sp,seed_verify_ms=sv,seed_receipt_bytes=size(seed),seed_phase=str(phase),seed_rank=str(center),queries=count,baseline_ms=base_ms,baseline_verify_ms=base_verify,anchor_ms=local_ms,anchor_verify_ms=local_verify,local_steps=scans,max_steps=max_steps,anchor_count=len(x.anchors),anchor_coordinate_bytes=size(x.anchors),baseline_receipt_bytes=sum(baseline),anchor_receipt_bytes=sum(local),cold_status=cold_r['status'],cold_ms=cms,cold_steps=cold_r['steps'],far_status=zz['status'],far_ms=far_ms,far_steps=zz['steps'],compare_exact=compare_exact,compare_decisive=compare_decisive)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='CIG-029A-results.json');a=p.parse_args();rows=[]
    for k in a.sizes:
        r=trial(k);rows.append(r);print(k,json.dumps(r),flush=True);open(a.output,'w').write(json.dumps(rows,indent=2)+'\n')
