"""CIG-014 heavy connected source and independent combinatorial transfer oracle.
The fixture supplies a regional layout, not the predicate identities to compiler.
"""
import argparse, json, random
from collections import Counter
from time import perf_counter_ns
from adaptive_ground import leaf, balanced, realize
from architecture_memory import Archive
from anticipatory_memory import Retained, leaves
from composed_ground import canonical
from nonlinear_sufficient import PredicateRetained


def timed(fn,*a,**kw):
    t=perf_counter_ns();r=fn(*a,**kw);return r,(perf_counter_ns()-t)/1e6


def fixture(m,seed=73):
    n=9*m+1; rng=random.Random(seed); labels=list(range(1,n+1));rng.shuffle(labels)
    edges=labels[:m+1]; private=labels[m+1:]; blocks=[]
    for i in range(m):
        l,r=edges[i:i+2];u=private[8*i:8*i+8];scope=sorted([l,r,*u])
        base=canonical([[-l,r,u[0]],[l,-r,u[4]]],n)
        predicates=[list(u[:4]),[-x for x in u[:4]],list(u[4:]),[-x for x in u[4:]]]
        blocks.append((scope,base,predicates))
    # Only the first four cases are declared to the anticipatory planner.
    # Queries 4--7 are held-out conjunctions/unions, including an empty clause.
    def case(j):
        rs=[];cs=[]
        for i,(s,b,p) in enumerate(blocks):
            extra=([p[j]] if 0<=j<4 else [p[0],p[1],p[2],p[3]] if j==4 else [p[0]+p[2]] if j==5 else [p[1]+p[3]] if j==6 else ([[]] if i==0 and j==7 else []))
            rows=canonical([*b,*extra],n);rs.append(leaf(s,rows));cs.extend(rows)
        rng.shuffle(cs)
        return cs,balanced(rs)
    return n,case(-1),[case(i) for i in range(8)]


def oracle(m,j):
    """Two-state transfer. Each group has four bits, one optionally pinned 1.
    Count from binomial-sized fibers, independent of source enumerator."""
    if j==7:return 0
    transfer=[]
    for l in (0,1):
        row=[]
        for r in (0,1):
            force=(int(l==1 and r==0),int(l==0 and r==1))
            def group(i):
                count=2**(4-force[i]);allow_zero=1-force[i]
                return count - (allow_zero if j in (2*i,4) else 0) - (1 if j in (2*i+1,4) else 0)
            count=group(0)*group(1)
            if j==5:count-=int(not any(force))
            if j==6:count-=1
            row.append(count)
        transfer.append(row)
    state=[1,1]
    for _ in range(m):state=[sum(state[l]*transfer[l][r] for l in (0,1)) for r in (0,1)]
    return sum(state)


class CoordinatePlan:
    def __init__(self,n,source,tree):
        self.n=n;self.covs=dict(leaves(source,n,tree))
    def selection(self):return {cov:cov[0] for cov in self.covs},{}


def campaign(m):
    n,(source,tree),qs=fixture(m);out=dict(n=n,regions=m,base_clauses=len(source),queries=len(qs))
    q,ms=timed(PredicateRetained,source,n,tree,qs[:4]);out['predicate_seed']=dict(ms=ms,bytes=q.bytes,**q.stats)
    c,ms=timed(Retained,CoordinatePlan(n,source,tree));out['coordinate_seed']=dict(ms=ms,bytes=c.bytes,**c.stats)
    answers=[oracle(m,j) for j in range(8)]
    for name,session in [('predicate',q.session),('coordinate',c.session),('cold',Archive)]:
        stats=Counter();elapsed=0; per=[]
        for j,(s,t) in enumerate(qs):
            result,ms=timed(realize,s,n,t,session());assert int(result['count'])==answers[j],(name,j)
            assert (result['witness'] is not None)==bool(answers[j]);elapsed+=ms;stats.update(result['metrics'])
            per.append(dict(query=j,ms=ms,metrics=result['metrics'],count_digits=len(result['count'])))
        out[name]=dict(ms=elapsed,metrics=dict(stats),per_query=per)
    out['count_digits']=[len(str(v)) for v in answers];out['count_sha256']=[__import__('hashlib').sha256(str(v).encode()).hexdigest() for v in answers]
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--regions',nargs='+',type=int,default=[8,32,128,256,512]);p.add_argument('--output',default='CIG-014-results.json');a=p.parse_args();results=[]
    for m in a.regions:
        row=campaign(m);results.append(row)
        with open(a.output,'w') as f:json.dump(results,f,indent=2);f.write('\n')
        print('completed',row['n'], 'bins',row['predicate_seed']['bins'],'coordinates',row['predicate_seed']['coordinate_cells'],'novel',row['predicate']['metrics'].get('novel_clause_covers',0),'ms',*[round(row[x]['ms'],2) for x in ['predicate','coordinate','cold']],flush=True)
