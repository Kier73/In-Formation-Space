"""Measured PGI-004 use; target history is withheld from discovery."""
import json,time,random,argparse,math
from dataclasses import replace
from coordinate_language import CoordinateSkill,discover,discover_collapsing,compile_view,compose,Vocabulary
from verify_coordinate_language import verify_pullback,verify_composition
from test_coordinate_language import arbitrary,permutation,oracle
from test_family_language import train
from test_skill_language import random_view
from family_language import crt
from ground_network import select
from ground_network_verify import verify_selection

def ms():return time.perf_counter_ns()/1e6

def synthetic(family):
    results=[]
    for label,count,base in [('coupled',60,(3,5,7,11)),('large_parity',24,(3,5,7,11,13,17,19,23,29,31,37,41,43,47,53))]:
        rows=[]
        for i in range(count):
            a=arbitrary(10000+i,base,i%3) if label=='coupled' else random_view(20000+i,base,i%3)
            s=permutation(a,30000+i,i%2);b,_=compile_view(a,s);b=replace(b,source='hidden:'+str(i))
            t=ms();z,d=discover(a,b,max_work=2000000);elapsed=ms()-t
            assert z and verify_pullback(a,b,z)[0],(label,i,d)
            t=ms();old,profile=family.discover(a,b,max_work=100000,max_candidates=128);old_ms=ms()-t
            # Explicit full period for small cases, independently sampled CRT phases for huge cases.
            checks=range(a.period+a.cutoff) if label=='coupled' else [a.cutoff+random.Random(i*1000+j).randrange(a.period) for j in range(64)]
            assert all(b.bit(t)==oracle(a,z,t)==oracle(a,s,t) for t in checks)
            rows.append(dict(work=d['work'],branches=d['branches'],backtracks=d['backtracks'],ms=elapsed,affine_found=old is not None,affine_ms=old_ms,affine_work=profile['work']))
        results.append(dict(kind=label,period=str(math.prod(base)),count=count,found=count,affine_found=sum(r['affine_found'] for r in rows),work=sum(r['work'] for r in rows),branches=sum(r['branches'] for r in rows),backtracks=sum(r['backtracks'] for r in rows),ms=sum(r['ms'] for r in rows),affine_ms=sum(r['affine_ms'] for r in rows),affine_work=sum(r['affine_work'] for r in rows)))
    rows=[]
    for i in range(40):
        a=arbitrary(70000+i,(3,5,7),i%3);rng=random.Random(72000+i)
        skill=CoordinateSkill(a.base,tuple(tuple(rng.randrange(m) for _ in range(m)) for m in a.base),i%2)
        b,_=compile_view(a,skill);b=replace(b,source='unseen-collapse')
        t=ms();z,d=discover_collapsing(a,b,max_work=2000000);elapsed=ms()-t
        assert z and verify_pullback(a,b,z)[0] and all(b.bit(t)==oracle(a,z,t)==oracle(a,skill,t) for t in range(a.period+a.cutoff))
        v,_=discover(a,b,max_work=100000)
        rows.append(dict(work=d['work'],branches=d['branches'],backtracks=d['backtracks'],ms=elapsed,bijective_found=v is not None))
    results.append(dict(kind='many_to_one',period='105',count=len(rows),found=len(rows),bijective_found=sum(r['bijective_found'] for r in rows),work=sum(r['work'] for r in rows),branches=sum(r['branches'] for r in rows),backtracks=sum(r['backtracks'] for r in rows),ms=sum(r['ms'] for r in rows)))
    return results

def actual(k,family):
    from run_output_time import fixture
    from run_cross_ground_seed import make
    from run_disjunctive_time import fold
    from run_seed_network import admitted
    from seed_network import SeedNetwork
    from temporal_ground import Navigator
    from inverse_time import spatial_groups
    t=ms();_,_,_,_,_,g,p,f,u,P,_,_,markers,desired=fixture(k)
    nav=Navigator(k,3,g,{'contract':'fixture','circuit':{'gates':[],'outputs':[]}})
    code=nav.jump(u,desired+2)
    third=[next(i for i in z if code>>(3*i)&1)*3 for z in spatial_groups(p)]
    expr=fold('or',[fold('and',x) for x in ([a for a,b in markers],[b for a,b in markers],third)])
    nav,rec=make(k,3,p,f,u,[expr]);lang,ad,receipt=admitted(nav,rec);network=SeedNetwork();key=network.register(rec,receipt,0);a=network.graph.views[key];source_ms=ms()-t
    assert a.cutoff==0 and a.total==3
    # Force a non-affine event projection on a prime radix >= 7, hiding maps from discovery.
    rng=random.Random(41000+k);maps=[list(rng.sample(range(m),m)) for m in a.base];j=next(i for i,m in enumerate(a.base) if m>=7 and all(m%d for d in range(2,math.isqrt(m)+1)));m=a.base[j]
    selected=[(desired+i)%m for i in range(3)];row=[None]*m
    for x,y in zip((0,1,3),selected):row[x]=y
    rest=iter(rng.sample([r for r in range(m) if r not in selected],m-3));maps[j]=[next(rest) if x is None else x for x in row]
    s=CoordinateSkill(a.base,tuple(tuple(row) for row in maps));b,_=compile_view(a,s);b=replace(b,source='unknown-target')
    t=ms();z,d=discover(a,b,max_work=2000000);discovery_ms=ms()-t;assert z and verify_pullback(a,b,z)[0],d
    t=ms();old,profile=family.discover(a,b,max_work=100000,max_candidates=128);old_ms=ms()-t;assert old is None
    # Prove no local affine preimage (including constants) has this projection.
    assert not any({r for r in range(m) if (alpha*r+beta)%m in selected}=={0,1,3} for alpha in range(m) for beta in range(m))
    # independent oracle: use hidden permutation, never inferred maps, to compute all 3 target phases.
    phases=sorted(crt((row.index((desired+i)%rad),rad) for row,rad in zip(s.maps,s.base)) for i in range(3))
    assert b.total==3 and len(set(phases))==3
    vocab=Vocabulary();assert vocab.observe(a,b,z);vocab=Vocabulary.restore(json.loads(json.dumps(vocab.packet())),{a.key:a,b.key:b});created,work=vocab.activate(a,z.key)
    t=ms();results=[]
    for i in range(8):
        ordinal=10**900+19*i;out=select(created,ordinal);assert out['status']=='FOUND';assert verify_selection(b,ordinal,out['time']);q,r=divmod(ordinal-1,3);tt=int(out['time']);assert tt==q*P+phases[r];results.append((tt,out['work']))
    selection_ms=ms()-t;t=ms()
    for tt,_ in results:
        x=crt((row[tt%rad],rad) for row,rad in zip(z.maps,z.base));r=nav.result(rec.initial,x);assert r['outputs'][0]==1 and rec.accept(x,r)
    terminal_ms=ms()-t
    # Increase the preimage of one event in a single prime coordinate. This
    # changes cardinality, so neither bijective discovery nor a local unit
    # affine map can explain it. A nonunit affine map on that prime would
    # erase all distinction there, also incompatible with the target.
    from itertools import product
    mm=[list(row) for row in s.maps];mm[j][2]=selected[0]
    collapse=CoordinateSkill(a.base,tuple(tuple(row) for row in mm));c,_=compile_view(a,collapse);c=replace(c,source='unknown-collapse')
    assert c.total==4 and discover(a,c,max_work=100000)[0] is None
    t=ms();cs,cd=discover_collapsing(a,c,max_work=2000000);collapse_ms=ms()-t
    assert cs and verify_pullback(a,c,cs)[0],cd
    cp=sorted({crt(zip(rr,a.base)) for i in range(3) for rr in product(*(tuple(x for x in range(rad) if row[x]==(desired+i)%rad) for rad,row in zip(a.base,collapse.maps)))})
    assert len(cp)==4
    t=ms();cw=0
    for i in range(8):
        ordinal=10**900+i*19;out=select(c,ordinal);assert out['status']=='FOUND' and verify_selection(c,ordinal,out['time']);q,r=divmod(ordinal-1,len(cp));tt=int(out['time']);assert tt==q*P+cp[r];cw+=out['work']
        x=crt((row[tt%rad],rad) for row,rad in zip(cs.maps,cs.base));r=nav.result(rec.initial,x);assert r['outputs'][0]==1 and rec.accept(x,r)
    collapse_realization_ms=ms()-t
    return dict(bits=k,period=str(P),radices=a.base,source_nodes=len(a.nodes),target_nodes=len(b.nodes),nonaffine_prime=m,source_ms=source_ms,discovery_ms=discovery_ms,discovery=d,old_found=old is not None,old_ms=old_ms,old=profile,skill_bytes=len(json.dumps(z.maps,separators=(',',':')).encode()),activation=work,ordinal_checks=len(results),selection_ms=selection_ms,selection_work=sum(x[1] for x in results),terminal_ms=terminal_ms,collapse=dict(discovery_ms=collapse_ms,discovery=cd,ordinal_checks=8,selection_work=cw,realization_and_terminal_ms=collapse_realization_ms,events=c.total))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='*',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='PGI-004-results.json');args=p.parse_args();family=train();out={'synthetic':synthetic(family),'actual':[]};print(json.dumps(out),flush=True)
    for k in args.sizes:
        row=actual(k,family);out['actual'].append(row);print(json.dumps(row),flush=True);open(args.output,'w').write(json.dumps(out,indent=2)+'\n')
