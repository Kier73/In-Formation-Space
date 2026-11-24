"""Reproducible exact benchmark, separate fixture oracles and checked cold control."""
import argparse,json,random
from collections import Counter
from itertools import product
from time import perf_counter_ns
from proof_refinement import ProofLanguage
from composed_ground import compile_ground,canonical
from verify_composed_ground import verify,accepted
from heavy_ground import xor_encoding
from run_architecture_navigation import cycle,oracle


def affine(k):
    n=2*k;ids=list(range(1,n+1));rng=random.Random(1616);rng.shuffle(ids);x,e=ids[:k],ids[k:]
    source=[c for i in range(k-2) for c in xor_encoding(tuple(sorted(x[i:i+3])),0)];rng.shuffle(source)
    predicates=[(x[0],),(x[3],),(x[1],),(x[2],),(e[0],),tuple(sorted((x[0],x[1])))]
    def expected(p):
        h=Counter()
        for a,b,z in product((0,1),repeat=3):
            d={x[i]:(a,b,a^b)[i%3] for i in range(k)};d[e[0]]=z
            key=sum(int(any(d[abs(l)]==int(l>0) for l in row))*2**j for j,row in enumerate(p));h[key]+=1<<(k-1)
        return dict(h)
    return n,source,predicates,expected


def mixed(k):
    n,source,x=cycle(k,seed=1616);predicates=[(x[0],),(x[1],),(x[2],),(x[3],),tuple(sorted((x[0],x[2]))),(-x[2],)]
    def expected(p):
        h=Counter();used=sorted({x.index(abs(l)) for row in p for l in row})
        for bits in product((0,1),repeat=len(used)):
            pins=dict(zip(used,bits));z=oracle(k,pins)
            d={x[i]:b for i,b in pins.items()};key=sum(int(any(d[abs(l)]==int(l>0) for l in row))*2**j for j,row in enumerate(p))
            if z:h[key]+=z
        return dict(h)
    return n,source,predicates,expected


def cold(n,source,predicates,expected):
    # Two independently checked branch counts for each realized old fiber.
    # Deliberately uses the same CIG-008 exact engine, with no carried count.
    rows=canonical(source,n);stats=Counter();t=perf_counter_ns();p=[];keys=[0]
    def count(q):
        packet=compile_ground(q,n);assert packet['status']!='UNKNOWN';assert verify(q,n,packet)
        stats['calls']+=1;stats['cells']+=packet['cells'];stats['projection_row_visits']+=packet['projection_row_visits'];return int(packet['count'])
    assert count(rows)==sum(expected([]).values())
    for f in predicates:
        nxt={}
        for k in keys:
            base=list(rows)
            for j,g in enumerate(p):
                if (k//2**j)%2:base.append(g)
                else:base.extend((-l,) for l in g)
            for b,add in [(0,[(-l,) for l in f]),(1,[f])]:
                c=count(base+add)
                if c:nxt[k+b*2**len(p)]=c
        p.append(f);assert nxt==expected(p);keys=sorted(nxt)
    return dict(ms=(perf_counter_ns()-t)/1e6,**stats)


def campaign(kind,k,compare=True):
    n,source,predicates,expected=(affine if kind=='affine' else mixed)(k)
    start=perf_counter_ns();lang=ProofLanguage(n,source);seed_ms=(perf_counter_ns()-start)/1e6;rows=[];t=perf_counter_ns()
    for f in predicates:
        before=lang.stats.copy();step=perf_counter_ns();r=lang.extend(f,nodes=0 if kind=='affine' else 8)
        assert r['complete'];p,h=lang.snapshot();hist={key:c for key,(c,_) in h.items()};assert hist==expected(p)
        rows.append(dict(predicate=f,ms=(perf_counter_ns()-step)/1e6,fibers=len(h),status=dict(Counter(r['status'].values())),metrics=dict(lang.stats-before)))
    extension_ms=(perf_counter_ns()-t)/1e6
    # Repeated held-out union / conjunction queries over the admitted language.
    p,h=lang.snapshot();a,c=p[0],p[2];additions=[[list(a)],[list(c)],[list(a),list(c)],[list(sorted(set(a+c),key=abs))]]
    t=perf_counter_ns();attempts=lang.stats['count_attempts']
    for _ in range(8):
        for query in additions:
            r=lang.query(query);assert r['status']!='UNRESOLVED'
            q=tuple(tuple(row) for row in query);want=sum(c for s,c in expected(p+q).items() if s>>len(p)==(1<<len(q))-1)
            assert int(r['count'])==want
            if want:assert accepted(source+query,int(r['witness']))
    query_ms=(perf_counter_ns()-t)/1e6;assert lang.stats['count_attempts']==attempts
    out=dict(kind=kind,n=n,clauses=len(source),seed_ms=seed_ms,extension_ms=extension_ms,total_ms=seed_ms+extension_ms,query32_ms=query_ms,count_digits=len(str(sum(expected([]).values()))),steps=rows,metrics=dict(lang.stats),final_fibers=len(h))
    if compare:out['cold_two_sided']=cold(n,source,predicates,expected)
    return out


def controls():
    l=ProofLanguage(12,[]);a=l.extend([1,2,3],width=1,nodes=0);b=l.extend([1,2,3],width=1,nodes=8);c=l.extend([1,2,3],width=3,nodes=8)
    assert [a['status'][0],b['status'][0],c['status'][0]]==['UNRESOLVED','SPLIT_UNCOUNTED','REFINE']
    randoms=[]
    for n in (50,100,200,500):
        rng=random.Random(1616+n);src=[tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),3)) for _ in range(round(4.26*n))]
        t=perf_counter_ns();p=compile_ground(src,n,max_width=8,max_cells=100000)
        if p['status']!='UNKNOWN':assert verify(src,n,p,max_width=8,max_cells=100000)
        randoms.append(dict(n=n,clauses=len(src),status=p['status'],ms=(perf_counter_ns()-t)/1e6))
    return dict(retry=[a,b,c],retry_metrics=dict(l.stats),random_controls=randoms)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=['affine','mixed','both'],default='both');p.add_argument('--sizes',nargs='+',type=int,default=[32,128,256,512]);p.add_argument('--no-cold',action='store_true');p.add_argument('--output',default='CIG-016-results.json');a=p.parse_args();out={'campaign':[],'controls':controls()}
    for kind in ['affine','mixed'] if a.kind=='both' else [a.kind]:
        for k in a.sizes:
            r=campaign(kind,k,not a.no_cold);out['campaign'].append(r);open(a.output,'w').write(json.dumps(out,indent=2)+'\n');print(kind,r['n'],round(r['total_ms'],2),r.get('cold_two_sided'),flush=True)
