"""Connected held-out semantic and refinement campaign, independent 2-state oracle."""
from collections import Counter
from itertools import product
from time import perf_counter_ns
import argparse,json,random,hashlib
from adaptive_ground import leaf,balanced,realize
from architecture_memory import Archive
from nonlinear_sufficient import PredicateRetained
from language_extension import LanguageRetained
from composed_ground import canonical


def fixture(m):
    n=9*m+1;rng=random.Random(1515);labels=list(range(1,n+1));rng.shuffle(labels);edges=labels[:m+1];hidden=labels[m+1:];blocks=[]
    for i in range(m):
        l,r=edges[i:i+2];a,b,c,d,e,f,g,h=hidden[8*i:8*i+8];scope=sorted([l,r,a,b,c,d,e,f,g,h]);base=[[-a,b],[a,-b],[-c,d],[c,-d],[-l,r,a],[l,-r,c]]
        extra=[[[a]],[[b]],[[e]],[[b,e]],[[f]],[[b,e,f]],[[-b]],[[b],[-b]]]
        blocks.append((scope,base,extra))
    def case(j):
        rows=[];nodes=[]
        for scope,base,extras in blocks:
            cs=canonical(base+([] if j==-1 else extras[j]),n);rows.extend(cs);nodes.append(leaf(scope,cs))
        rng.shuffle(rows);return rows,balanced(nodes)
    return n,case(-1),[case(i) for i in range(8)]


def oracle(m,j):
    # Independently substitute equality, count six free private bits per edge.
    transfer=[]
    for l in (0,1):
        row=[]
        for r in (0,1):
            count=0
            for a,c,e,f,g,h in product((0,1),repeat=6):
                if (l and not r and not a) or (not l and r and not c):continue
                if [a,a,e,a or e,f,a or e or f,not a,False][j]:count+=1
            row.append(count)
        transfer.append(row)
    v=[1,1]
    for _ in range(m):v=[sum(v[l]*transfer[l][r] for l in (0,1)) for r in (0,1)]
    return sum(v)


def campaign(m,rounds):
    n,(base,tree),qs=fixture(m);res=dict(n=n,regions=m,clauses=len(base),rounds=rounds);answers=[oracle(m,j) for j in range(8)]
    for name,cls in [('extending',LanguageRetained),('static',PredicateRetained),('cold',None)]:
        start=perf_counter_ns();mem=cls(base,n,tree,qs[:1]) if cls else None;prep=(perf_counter_ns()-start)/1e6;stats=Counter();runs=[];elapsed=0
        for iteration in range(rounds):
            st=Counter();t=perf_counter_ns()
            for j,(source,layout) in enumerate(qs):
                result=realize(source,n,layout,mem.session() if mem else Archive());assert int(result['count'])==answers[j],(name,j);assert bool(result['witness'] is not None)==bool(answers[j]);st.update(result['metrics'])
            ms=(perf_counter_ns()-t)/1e6;elapsed+=ms;stats.update(st);runs.append(dict(ms=ms,metrics=dict(st)))
        res[name]=dict(preparation_ms=prep,query_ms=elapsed,total_ms=prep+elapsed,metrics=dict(stats),runs=runs)
        if name=='extending':res[name]['archive_bytes'],res[name]['bins']=mem.size();res[name]['seed']=dict(mem.stats)
        elif name=='static':res[name]['archive_bytes']=mem.bytes;res[name]['bins']=mem.stats['bins'];res[name]['seed']=dict(mem.stats)
    res['count_digits']=[len(str(x)) for x in answers];res['count_sha256']=[hashlib.sha256(str(x).encode()).hexdigest() for x in answers];return res

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--regions',type=int,nargs='+',default=[8,32,128,512]);p.add_argument('--rounds',type=int,default=2);p.add_argument('--output',default='CIG-015-results.json');a=p.parse_args();out=[]
    for m in a.regions:
        row=campaign(m,a.rounds);out.append(row);open(a.output,'w').write(json.dumps(out,indent=2)+'\n');print(row['n'],[(x,round(row[x]['total_ms'],2)) for x in ('extending','static','cold')],flush=True)
