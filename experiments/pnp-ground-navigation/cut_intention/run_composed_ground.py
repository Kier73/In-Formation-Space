"""CIG-008 matched connected heterogeneous source campaign."""
import json
import random
from time import perf_counter
from composed_ground import compile_ground, canonical
from verify_composed_ground import verify


def xor_clauses(variables, rhs=0):
    return [tuple(-v if p>>i&1 else v for i,v in enumerate(variables))
            for p in range(1<<len(variables)) if p.bit_count()%2!=rhs]


def chain(stages, bridge=4, seed=73, contradictory=False):
    """Connected AND/XOR source; accepted x sequences are nondecreasing.

    x_i,x_(i+1) -> y_i=AND; h=x_i XOR y_i; affine copies -> z_i;
    (not z_i OR x_(i+1)) rules out 10. Private bridge values are unique.
    A contradiction adds x_0=1 and x_last=0; both source constraints retained.
    """
    x=list(range(1,stages+2)); n=len(x); clauses=[]
    for i in range(stages):
        a,b=x[i:i+2]; y=n+1; h=n+2; n+=2
        clauses.extend([(-a,-b,y),(a,-y),(b,-y)])
        clauses.extend(xor_clauses((a,y,h)))
        for _ in range(bridge):
            nxt=n+1;n+=1;clauses.extend(xor_clauses((h,nxt)));h=nxt
        clauses.append((-h,b))
    if contradictory:clauses.extend([(x[0],),(-x[-1],)])
    rng=random.Random(seed); perm=list(range(1,n+1));rng.shuffle(perm)
    clauses=[tuple(perm[abs(l)-1] if l>0 else -perm[-l-1] for l in c) for c in clauses]
    rng.shuffle(clauses)
    return n,clauses


def campaign():
    records=[]
    for stages,contradiction in [(8,False),(32,False),(128,False),(256,False),(256,True)]:
        n,clauses=chain(stages,contradictory=contradiction)
        t=perf_counter();r=compile_ground(clauses,n);built=perf_counter()-t
        t=perf_counter();assert verify(clauses,n,r);checked=perf_counter()-t
        assert int(r['count'])==(0 if contradiction else stages+2)
        records.append(dict(stages=stages,n=n,clauses=len(clauses),contradiction=contradiction,
            count=r['count'],status=r['status'],affine_equations=len(r['equations']),
            interface=len(r['interface']),private_pivots=len(r['pivots']),free_hidden=r['free_hidden'],
            projected=len(r['projected']),factor_cells=r['cells'],peak_scope=r['peak_scope'],
            projection_row_visits=r['projection_row_visits'],certificate_bytes=len(json.dumps(r,separators=(',',':')).encode()),
            construction_ms=round(built*1000,3),verification_ms=round(checked*1000,3)))
    return records

def pigeonhole(p,h):
    clauses=[tuple(range(i*h+1,(i+1)*h+1)) for i in range(p)]
    clauses += [(-(i*h+j+1),-(k*h+j+1)) for j in range(h) for i in range(p) for k in range(i+1,p)]
    return p*h,clauses


def full_campaign():
    """Execute actual CIG-006 DPLL and CIG-007 Hall; no mock fallbacks."""
    from heavy_ground import dpll
    from composed_ground import decide_with_hall
    from verify_composed_ground import verify_decision
    records=campaign()
    for rec in records:
        n,c=chain(rec['stages'],contradictory=rec['contradiction'])
        r=dpll(c,n,intent='#SAT',max_nodes=1200,seconds=1.5)
        rec['direct_dpll']={k:r[k] for k in ('status','nodes','literal_checks','wall_ms') if k in r}
        if r['status']!='UNKNOWN':
            assert r['count']==rec['count']
            rec['direct_dpll']['count']=r['count']
    halls=[]
    for p,h in [(8,7),(32,31),(4,4)]:
        n,c=pigeonhole(p,h);c+=xor_clauses((1,n+1,n+2));n+=2
        t=perf_counter();r=decide_with_hall(c,n);a=perf_counter()-t
        t=perf_counter();assert verify_decision(c,n,r);b=perf_counter()-t
        halls.append(dict(n=n,clauses=len(c),pigeons=p,holes=h,status=r['status'],route=r['route'],construction_ms=round(a*1000,3),verification_ms=round(b*1000,3),certificate_bytes=len(json.dumps(r,separators=(',',':')).encode())))
    controls=[]
    for n in [50,75,100]:
        rng=random.Random(73)
        c=[tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),3)) for _ in range(round(4.26*n))]
        t=perf_counter();r=compile_ground(c,n)
        controls.append(dict(n=n,clauses=len(c),status=r['status'],ms=round((perf_counter()-t)*1000,3),reason=r.get('reason')))
    return {'connected':records,'hall_decision':halls,'random_controls':controls}


if __name__=='__main__':
    print(json.dumps(full_campaign(),indent=2))
