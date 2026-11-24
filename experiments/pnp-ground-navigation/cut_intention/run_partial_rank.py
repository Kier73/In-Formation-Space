"""CIG-028B source-qualified campaign and separate irregular algebra control."""
import argparse,json,random
from math import lcm,prod
from run_disjunctive_time import fold
from run_output_time import fixture,circuit_source
from run_temporal_ground import timed,size
from inverse_time import spatial_groups
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_ground import Navigator
from verify_temporal_ground import Receiver
from temporal_algebra import compile_algebra,Language,Diagram,Budget
from verify_temporal_algebra import Admission
from temporal_rank import Rank,expand
from verify_temporal_rank import CheckedRank
from partial_rank import PartialRank
from verify_partial_rank import CheckedPartial

def trial(k):
    _,_,_,_,ts,g,p,f,initial,P,start,_,markers,desired=fixture(k)
    periods=[len(z) for z in spatial_groups(p)]
    parity=fold('xor',[a for a,b in markers]);alt=('or',fold('and',[a for a,b in markers]),fold('and',[b for a,b in markers]));impossible=('or',('and',*markers[0]),('and',*markers[-1]))
    n,s,q,fs=circuit_source(k,[parity,alt,impossible]);dec,ct=timed(synthesize_shared,n,s,q,fs);assert dec['status']=='COMPLETE' and all(x['status']=='SUFFICIENT' for x in dec['goals']);sec,st=timed(compile_section,n,s,q);rec,rt=timed(Receiver,n,s,q,fs,dec,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,dec)
    (d,r),cm=timed(compile_algebra,nav,initial);a,vm=timed(Admission,rec,r);lang=Language(d,r);assert r['cutoff']==0
    weights={1:1}
    for L in periods:
        new=weights.copy()
        for m,v in weights.items():z=lcm(m,L);new[z]=new.get(z,0)-2*v
        weights={m:v for m,v in new.items() if v}
    def oracle(t):return (t-sum(v*((t-1-desired%m)//m+1) for m,v in weights.items()))//2
    x,pt=timed(PartialRank,lang,0);c,vt=timed(CheckedPartial,a);full,ft=timed(Rank,lang,0);checked,fvt=timed(CheckedRank,a,full.packet());assert x.total==oracle(P)
    rng=random.Random(26026);queries=[];expected=[]
    for j in range(32):
        t=10**900*P+rng.randrange(P);estimate=t*x.total//P;h=estimate+([-1,1][j%2])*max(1,P//1000);queries.append((t,h));expected.append(oracle(t))
    results,ms=timed(lambda:[x.compare(t,h,budget=5000) for t,h in queries]);ok,vs=timed(lambda:all(c.verify(r,budget=5000) for r in results));assert ok
    for (t,h),z,e in zip(queries,results,expected):assert int(z['lower'])<=e<=int(z['upper']);assert z['status']=='UNKNOWN' or (int(z['upper'])<h)==(e<h)
    vals,fms=timed(lambda:[full.rank(t) for t,h in queries]);vv,fvs=timed(lambda:[checked.rank(t) for t,h in queries]);assert vals==vv==expected
    rows=[]
    for name,ordinal in [('early_phase',10**900*x.total+3),('late_phase',(10**900+1)*x.total-2),('arbitrary_phase',10**900+173)]:
        z,sm=timed(x.select,ordinal,budget=20000);ok,sv=timed(c.verify_select,0,ordinal,z,budget=20000) if z['status']=='FOUND' else (False,0)
        fz,fsm=timed(full.select,ordinal);assert checked.verify_select(ordinal,fz)
        if z['status']=='FOUND':
            assert ok and z['time']==fz['time'];t=int(z['time']);assert oracle(t)==ordinal-1 and oracle(t+1)==ordinal
        rows.append(dict(case=name,status=z['status'],probes=z['probes'],work=z['work'],select_ms=sm,verify_ms=sv,proof_bytes=size(z),full_ms=fsm,full_probes=fz['probes'],time=z['time']))
    tt=start+P//2;e=oracle(tt);bounds=[]
    for b in (0,100,1000,20000):
        z,bms=timed(x.compare,tt,budget=b);ok,bvs=timed(c.verify,z,budget=b);assert ok and int(z['lower'])<=e<=int(z['upper']);bounds.append(dict(budget=b,status=z['status'],width=str(int(z['upper'])-int(z['lower'])),work=z['work'],ms=bms,verify_ms=bvs,terms=z['terms'],scans=z['scans']))
    return dict(n=n,observed=k,period=str(P),total=str(x.total),nodes=len(d.nodes),signed_terms=len(full.terms),mass=str(x.mass[x.root]),partial_prepare_ms=pt,partial_verify_prepare_ms=vt,full_prepare_ms=ft,full_verify_prepare_ms=fvt,source_prepare_ms=ct+st+rt+cm+vm,decisions=dict(count=len(results),decisive=sum(r['status']!='UNKNOWN' for r in results),zero_work=sum(r['work']==0 for r in results),work=sum(r['work'] for r in results),ms=ms,verify_ms=vs,full_ms=fms,full_verify_ms=fvs,receipt_bytes=sum(size(r) for r in results)),ordinals=rows,bounds=bounds,suffix_tables=len(x.cache),suffix_terms=sum(map(len,x.cache.values())),suffix_compile_work=x.compiled_work)

def random_control():
    rng=random.Random(25025);d=Diagram([2,3,5,7,11,13]);P=prod(d.base);truth=[rng.getrandbits(1) for t in range(P)];root=d.atom(P,{t for t,v in enumerate(truth) if v});l=Language(d,dict(cutoff=0,outputs=[root],prefix=[]));x=PartialRank(l,0);N=sum(truth)
    try:expand(d,root,10000);refused=False
    except Budget:refused=True
    cases=[]
    for t in [7,P-7,P//2]:
        for b in [0,100,10000]:
            z,ms=timed(x.compare,t,budget=b);e=sum(truth[:t]);assert int(z['lower'])<=e<=int(z['upper']);cases.append(dict(t=t,budget=b,status=z['status'],width=int(z['upper'])-int(z['lower']),ms=ms,work=z['work']))
    z,ms=timed(x.select,10**900*N+3,budget=10000)
    if z['status']=='FOUND':assert int(z['time'])==10**900*P+[i for i,v in enumerate(truth) if v][2]
    return dict(period=P,nodes=len(d.nodes),signed_budget_refused=refused,near_edge_status=z['status'],near_edge_selection_ms=ms,near_edge_work=z['work'],cases=cases,note='Algebra-level exhaustive oracle, not a source-admission benchmark.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='CIG-028B-results.json');args=p.parse_args();out=dict(campaign=[],random_control=random_control());print('random',out['random_control'],flush=True)
    for k in args.sizes:
        row=trial(k);out['campaign'].append(row);open(args.output,'w').write(json.dumps(out,indent=2)+'\n');print(k,row['decisions'],[(x['case'],x['status'],x['work'],round(x['select_ms'],3)) for x in row['ordinals']],row['bounds'],flush=True)
