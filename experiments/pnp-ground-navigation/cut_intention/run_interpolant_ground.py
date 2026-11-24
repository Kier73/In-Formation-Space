"""Reproduce CIG-018: shuffled OR-observation chains, separate proof and decoder costs."""
import argparse,json,random,sys
from time import perf_counter_ns
from test_interpolant_ground import chain
from interpolant_ground import synthesize,evaluate
from verify_interpolant_ground import verify,decode
from global_sufficiency import synthesize as previous,evaluate as prev_eval
from verify_global_sufficiency import verify as prev_verify


def timed(fn,*a,**kw):
    t=perf_counter_ns();v=fn(*a,**kw);return v,(perf_counter_ns()-t)/1e6

def expected(code,k,mixed):
    v=code&1
    for j in range(1,k):
        b=(code>>j)&1;v=(v&b) if mixed and j%2 else (v^b)
    return v

def trial(k,mixed,ordering='scope'):
    n,s,q,f=chain(k,mixed);r,ct=timed(synthesize,n,s,q,f,ordering=ordering);ok,vt=timed(verify,n,s,q,f,r,ordering=ordering)
    row=dict(n=n,clauses=len(s),observed=k,family='mixed' if mixed else 'parity',ordering=ordering,status=r['status'],compile_ms=ct,verify_ms=vt,pairs=r['pairs'],eliminated=r['eliminated'])
    if r['status']=='SUFFICIENT':
        assert ok;d=r['decoder'];rng=random.Random(1800+k);codes=list(range(1<<k)) if k<=8 else [0,(1<<k)-1]+[rng.getrandbits(k) for _ in range(64)]
        t=perf_counter_ns()
        for code in codes:assert evaluate(d,code,k)==decode(d,code,k)==expected(code,k,mixed)
        row.update(oracle_codes=len(codes),oracle_ms=(perf_counter_ns()-t)/1e6,proof_steps=len(r['steps']),generated_steps=r['generated_steps'],circuit_gates=len(d['gates']),receipt_bytes=len(json.dumps(r,separators=(',',':')).encode()),decoder_bytes=len(json.dumps(d,separators=(',',':')).encode()))
    else:assert not ok and r['status']=='UNKNOWN';row['reason']=r['reason']
    return row

def compare(k):
    n,s,q,f=chain(k);kw=dict(width=10,cells=300000,decoder_bits=6)
    r,t=timed(previous,n,s,q,f,**kw);ok,v=timed(prev_verify,n,s,q,f,r,**kw)
    if r['status']!='UNKNOWN':assert ok and r['status']=='SUFFICIENT'
    if r.get('decoder') is not None:
        for code in range(1<<k):assert prev_eval(q,f,r,code)==expected(code,k,True)
    a=trial(k,True)
    return dict(n=n,observed=k,old_status=r['status'],old_route=r['route'],old_decoder=r.get('decoder') is not None,old_decoder_obligations=len((r.get('decoder') or {}).get('proofs',[])),old_compile_ms=t,old_verify_ms=v,new_compile_ms=a['compile_ms'],new_verify_ms=a['verify_ms'],new_proof_steps=a['proof_steps'],new_decoder_gates=a['circuit_gates'])

def controls():
    out=[]
    for n in (50,100,200,500):
        rng=random.Random(1818+n);s=[tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),3)) for _ in range(round(4.26*n))];q=[(1,2),(3,4)];f=(5,)
        r,t=timed(synthesize,n,s,q,f,max_pairs=20000,max_steps=10000,max_width=16)
        assert r['status']=='UNKNOWN' or verify(n,s,q,f,r,max_pairs=20000,max_steps=10000,max_width=16)
        out.append(dict(n=n,status=r['status'],pairs=r['pairs'],compile_ms=t,reason=r.get('reason')))
    for k in (32,128,1024):
        n,s,q,f=chain(k);s=[c for c in s if abs(f[0]) not in map(abs,c)]
        r,t=timed(synthesize,n,s,q,f);assert r['status']=='INSUFFICIENT' and verify(n,s,q,f,r)
        out.append(dict(n=n,case='removed output constraint',status=r['status'],pairs=r['pairs'],compile_ms=t))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='CIG-018-results.json');p.add_argument('--sizes',type=int,nargs='+',default=[8,32,128,512,1024]);a=p.parse_args()
    d=dict(python=sys.version,structured=[],ordering_control=[],comparison=[],controls=[])
    def save():open(a.output,'w').write(json.dumps(d,indent=2)+'\n')
    for mixed in (True,False):
        for k in a.sizes:
            d['structured'].append(trial(k,mixed));save();print(d['structured'][-1],flush=True)
    for k in (32,128,1024):
        d['ordering_control'].append(trial(k,False,'pairs'));save();print(d['ordering_control'][-1],flush=True)
    for k in (4,8,32,128):
        d['comparison'].append(compare(k));save();print(d['comparison'][-1],flush=True)
    d['controls']=controls();save();print(d['controls'],flush=True)
