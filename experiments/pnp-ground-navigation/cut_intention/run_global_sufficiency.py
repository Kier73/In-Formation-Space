"""CIG-017 benchmark; structured fixtures, finite exact oracles, separate costs."""
import argparse,json,random,sys
from time import perf_counter_ns
from collections import Counter
from global_sufficiency import synthesize,evaluate,GlobalLanguage
from verify_global_sufficiency import verify
from verify_composed_ground import accepted
from heavy_ground import xor_encoding
from proof_refinement import ProofLanguage
from run_architecture_navigation import cycle,oracle


def timed(fn,*a,**kw):
    t=perf_counter_ns();out=fn(*a,**kw);return out,(perf_counter_ns()-t)/1e6


def chain(n,kind):
    rng=random.Random(1717+n);ids=list(range(1,n+1));rng.shuffle(ids)
    k=max(2,n//8);a=ids[:k];z=ids[k:];rows=[];gates=[]
    prev=a[0]
    for i,out in enumerate(z):
        other=a[1+i%(k-1)];and_gate=kind=='mixed' and i%3==0
        if and_gate:rows.extend([(-prev,-other,out),(prev,-out),(other,-out)])
        else:rows.extend(xor_encoding(tuple(sorted((prev,other,out))),0))
        gates.append((prev,other,out,and_gate));prev=out
    rng.shuffle(rows);q=[(v if i%5 else -v,) for i,v in enumerate(a)];f=tuple(sorted((z[-1],-z[-2],z[-3]),key=abs))
    return rows,q,f,gates,a


def symbolic(n,kind):
    rows,q,f,gates,a=chain(n,kind);r,cm=timed(synthesize,n,rows,q,f);ok,vm=timed(verify,n,rows,q,f,r);assert ok and r['status']=='SUFFICIENT'
    assert r['route']==('affine' if kind=='affine' else 'circuit')
    rng=random.Random(2717);t=perf_counter_ns()
    for _ in range(24):
        values={v:rng.randrange(2) for v in a}
        for i,j,o,g in gates:values[o]=(values[i]&values[j]) if g else values[i]^values[j]
        x=sum(b<<(v-1) for v,b in values.items());assert accepted(rows,x)
        code=sum(int(values[abs(c[0])]==int(c[0]>0))<<j for j,c in enumerate(q))
        expected=int(any(values[abs(l)]==int(l>0) for l in f));assert evaluate(q,f,r,code)==expected
    oracle_ms=(perf_counter_ns()-t)/1e6
    return dict(kind=kind,n=n,clauses=len(rows),q=len(q),route=r['route'],compile_ms=cm,verify_ms=vm,oracle24_ms=oracle_ms,receipt_bytes=len(json.dumps(r,separators=(',',':')).encode()),proof_equations=len(r['decoder'].get('equations',[])),gates=len(r['decoder'].get('gates',[])),row_xors=r['decoder'].get('row_xors'),decoder_terms=sum(len(t['inputs']) for t in r['decoder'].get('terms',[])))


def receiver_case(n):
    _,rows,x=cycle(n//2,seed=1717);q=[(x[i],) for i in (0,4,8,12)];f=tuple(sorted((x[1],x[5],-x[9]),key=abs))
    def seeded(cls):
        g=cls(n,rows)
        for p in q:assert g.extend(p)['complete']
        return g
    a,seed_ms=timed(seeded,GlobalLanguage);b,seed2=timed(seeded,ProofLanguage);assert a.snapshot()==b.snapshot()
    old=a.stats.copy();(r,ok),gm=timed(a.global_extend,f);assert ok
    before=b.stats.copy();step,pm=timed(b.extend,f);assert step['complete']
    pa,ha=a.snapshot();pb,hb=b.snapshot();assert pa==pb
    expected=Counter()
    for k in range(16):
        pins={i:(k>>j)&1 for j,i in enumerate((0,4,8,12))};c=oracle(n//2,pins)
        if c:expected[k|((int(bool((k&1) or (k&2) or not(k&4))))<<4)]+=c
    assert {k:c for k,(c,w) in ha.items()}=={k:c for k,(c,w) in hb.items()}==dict(expected)
    return dict(n=n,source_clauses=len(rows),fibers=len(ha),seed_ms=seed_ms,control_seed_ms=seed2,global_extension_ms=gm,per_fiber_extension_ms=pm,global_work=dict(a.stats-old),per_fiber_work=dict(b.stats-before),route=r['route'])


def pair_cases():
    out=[]
    for n in (32,128,256,512):
        # A ring with source-implied nonlinear readout. Observe three ORs of
        # pairs; the target is their union. Neither symbolic singleton route
        # applies; deliberately exercise actual paired-CNF proof.
        _,rows,x=cycle(n//2,seed=1717);q=[tuple(sorted((x[i],x[i+2]))) for i in (0,4,8)];f=tuple(sorted({l for c in q for l in c}));r,cm=timed(synthesize,n,rows,q,f,mode='paired',decoder_bits=0)
        ok,vm=timed(verify,n,rows,q,f,r,decoder_bits=0);assert r['status']=='UNKNOWN' or (ok and r['status']=='SUFFICIENT');out.append(dict(n=n,case='nonlinear-union',status=r['status'],compile_ms=cm,verify_ms=vm,decoder=False,paired_cells=r.get('proof',{}).get('cells'),paired_projection_visits=r.get('proof',{}).get('projection_row_visits')))
    # Source-dependent nonlinear alias union: every selected odd coordinate
    # equals its even neighbour by the pinned XOR equations. This is not a
    # literal-union identity of the raw observation clauses.
    for n in (64,256,512):
        _,rows,x=cycle(n//2,seed=1717);q=[tuple(sorted((x[i],x[i+2]))) for i in (0,4,8)];f=tuple(sorted(x[i] for i in (1,3,5,7,9,11)));limit=3 if n==64 else 0
        r,cm=timed(synthesize,n,rows,q,f,mode='paired',decoder_bits=limit);ok,vm=timed(verify,n,rows,q,f,r,decoder_bits=limit)
        assert r['status']=='UNKNOWN' or (ok and r['status']=='SUFFICIENT')
        if n==64:assert r['decoder']['anf']==[1,2,3,4,5,6,7]
        out.append(dict(n=n,case='source-dependent-alias-union',status=r['status'],compile_ms=cm,verify_ms=vm,decoder=r.get('decoder') is not None,decoder_obligations=len(r['decoder']['proofs']) if r.get('decoder') else 0,paired_cells=r.get('proof',{}).get('cells'),paired_projection_visits=r.get('proof',{}).get('projection_row_visits')))
    # Actual ANF formation and counterexample with independent finite oracle.
    q=[(1,2),(-3,4)];f=(1,2,-3,4);r,cm=timed(synthesize,4,[],q,f,mode='paired');ok,vm=timed(verify,4,[],q,f,r);assert ok and r['decoder']['anf']==[1,2,3]
    out.append(dict(n=4,case='decoder-ANF',status=r['status'],compile_ms=cm,verify_ms=vm,anf=r['decoder']['anf'],decoder_obligations=len(r['decoder']['proofs'])))
    r=synthesize(4,[],q,(1,),mode='paired');assert r['status']=='INSUFFICIENT' and verify(4,[],q,(1,),r);out.append(dict(n=4,case='counterexample',status=r['status'],witness=r['witness']))
    return out


def controls():
    out=[]
    for n in (50,100,200,500):
        rng=random.Random(n+1717);rows=[tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),3)) for _ in range(round(4.26*n))];q=[(1,),(2,)];f=(3,)
        r,cm=timed(synthesize,n,rows,q,f,width=8,cells=100000,decoder_bits=0);assert r['status']=='UNKNOWN' or verify(n,rows,q,f,r,width=8,cells=100000,decoder_bits=0)
        out.append(dict(n=n,status=r['status'],route=r['route'],compile_ms=cm))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='CIG-017-results.json');p.add_argument('--sizes',type=int,nargs='+',default=[128,512,2048,8192]);p.add_argument('--receiver-sizes',type=int,nargs='+',default=[64,256,512,1024]);a=p.parse_args();out=dict(python=sys.version,symbolic=[],receiver=[],paired=[],controls=[])
    def save():open(a.output,'w').write(json.dumps(out,indent=2)+'\n')
    for k in ('affine','mixed'):
        for n in a.sizes:
            row=symbolic(n,k);out['symbolic'].append(row);save();print(row,flush=True)
    for n in a.receiver_sizes:
        row=receiver_case(n);out['receiver'].append(row);save();print(row,flush=True)
    out['paired']=pair_cases();save();print(out['paired'],flush=True)
    out['controls']=controls();save();print(out['controls'],flush=True)
