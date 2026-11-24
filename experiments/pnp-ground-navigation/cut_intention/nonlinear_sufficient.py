"""CIG-014: exact source-model predicate fibers, retained in receiver memory.

Bounded leaf domains; predicates discovered from forecast source additions.
No assumption that a marginal determines an arbitrary unobserved predicate.
"""
from collections import Counter, defaultdict
from time import perf_counter_ns
import json
from adaptive_ground import realize
from architecture_memory import Archive, region
from anticipatory_memory import leaves, cold
from composed_ground import canonical
from regional_memory import identity, wire
from verify_nonlinear_sufficient import check_seed, check_translation

MAX_PREDICATES = 32


def make_seed(n, scope, source, visible, predicates):
    scope = list(scope); visible = list(visible)
    if len(scope)>10 or scope!=sorted(set(scope)) or any(type(v)is not int or not 1<=v<=n for v in scope):
        raise ValueError('scope')
    if visible!=sorted(set(visible)) or not set(visible)<=set(scope): raise ValueError('visible')
    c=canonical(source,n); p=canonical(predicates,n)
    if len(p)>MAX_PREDICATES or any(abs(l) not in scope for row in c+p for l in row): raise ValueError('predicate budget/scope')
    pos={v:i for i,v in enumerate(scope)}
    def masks(rows):
        return [(sum(1<<pos[l] for l in row if l>0),sum(1<<pos[-l] for l in row if l<0)) for row in rows]
    clauses, tests=masks(c),masks(p)
    histogram=Counter(); models=0
    for x in range(1<<len(scope)):
        if not all(x&a or (~x)&b for a,b in clauses): continue
        models+=1
        k=sum(((x>>pos[v])&1)<<j for j,v in enumerate(visible))
        k|=sum(int(bool(x&a or (~x)&b))<<(len(visible)+j) for j,(a,b) in enumerate(tests))
        histogram[k]+=1
    d=dict(schema='ifs.cig014.predicate-fiber.v1',n=n,scope=scope,source=[list(r) for r in c],visible=visible,predicates=[list(r) for r in p])
    return dict(descriptor=d,key=identity(d),bins=[[k,str(v)] for k,v in sorted(histogram.items())],bits=(max(0,len(histogram)-1)).bit_length()),dict(seed_states=1<<len(scope),predicate_evaluations=models*len(p),source_models=models)


def covers(d, clause):
    """Exact union of signed literal sets; not a learned implication."""
    target=set(clause); parts=[]; covered=set()
    for j,c in enumerate(d['predicates']):
        if c and set(c)<=target:
            parts.append([0,j]); covered.update(c)
    for l in clause:
        if abs(l) in d['visible'] and l not in covered:
            parts.append([1 if l>0 else 2,d['visible'].index(abs(l))]);covered.add(l)
    return parts if covered==target else None


def plan(seed,desc):
    d=seed['descriptor']
    if d['scope']!=desc['scope'] or not set(desc['boundary'])<=set(d['visible']):return None
    orig=set(map(tuple,d['source']));new=set(map(tuple,desc['clauses']))
    if not orig<=new:return None
    out=[]
    for c in sorted(new-orig,key=lambda c:(len(c),c)):
        parts=covers(d,c)
        if parts is None:return None
        out.append([list(c),parts])
    return out


def translate(seed,desc,cover):
    d=seed['descriptor'];width=len(d['visible']);out=[0]*(1<<len(desc['boundary']))
    def truth(k,p):
        kind,i=p
        return ((k>>(width+i))&1) if kind==0 else (((k>>i)&1) ^ int(kind==2))
    for k,v in seed['bins']:
        if all(any(truth(k,p) for p in parts) for _,parts in cover):
            dest=sum(((k>>d['visible'].index(u))&1)<<j for j,u in enumerate(desc['boundary']))
            out[dest]+=int(v)
    return dict(key=identity(desc),boundary=desc['boundary'],counts=list(map(str,out)))


class PredicateRetained:
    """Audits all supplied layouts, derives predicates from actual CNF additions.

    Retains one independently checked finite quotient per matched base scope.
    No query-derived tables accumulate across sessions. Local receiver trust only.
    """
    def __init__(self, source,n,tree,forecasts):
        self.n=n; self._seeds={}; self.stats=Counter(); self.bytes=0
        base=dict(leaves(source,n,tree)); by_scope=defaultdict(list)
        for cov,b in base.items():by_scope[cov[0]].append(cov)
        specs={cov:[set(b),set()] for cov,b in base.items()}
        for src,t in forecasts:
            for target,b in leaves(src,n,t):
                candidates=[c for c in by_scope[target[0]] if set(c[1])<=set(target[1])]
                if not candidates:continue
                cov=min(candidates,key=lambda c:(-len(c[1]),c[1]));a,p=specs[cov]
                a.update(b);p.update(set(target[1])-set(cov[1]))
        for cov,(a,p) in specs.items():
            if len(p)>MAX_PREDICATES:continue
            seed,work=make_seed(n,cov[0],cov[1],sorted(a),list(p))
            if not check_seed(n,cov[0],cov[1],sorted(a),list(p),seed):raise ValueError('seed check failed')
            raw=wire(seed);self._seeds.setdefault(cov[0],[]).append(raw)
            self.stats.update(work);self.stats['seed_checks']+=1;self.stats['bins']+=len(seed['bins'])
            self.stats['coordinate_cells']+=1<<len(set(a)|{abs(l) for c in p for l in c})
            self.bytes+=len(raw)
    def session(self):return PredicateArchive(self)


class PredicateArchive(Archive):
    def __init__(self,retained):
        super().__init__()
        if type(retained)is not PredicateRetained:raise ValueError('receiver owned memory required')
        self.retained=retained
    def obtain(self,desc,children,stats):
        if children is not None or identity(desc) in self._proofs:return super().obtain(desc,children,stats)
        target=region(desc['scope'],desc['clauses']);b=tuple(desc['boundary']);best=None
        for raw in self.retained._seeds.get(target[0],()):
            seed=json.loads(raw);cover=plan(seed,desc)
            if cover is not None and len(seed['bins'])<=cold(target,b):
                choice=(len(seed['bins']),seed['key'])
                if best is None or choice<best[0]:best=(choice,seed,cover)
        if best is None:return super().obtain(desc,children,stats)
        _,seed,cover=best;msg=translate(seed,desc,cover)
        if not check_translation(self.retained.n,seed,desc,cover,msg):raise ValueError('translation check failed')
        key=msg['key'];self._proofs[key]=wire(msg);self._coverage[key]=target;self._functions[target][b]=wire(msg)
        stats['predicate_reuse']+=1;stats['predicate_bins']+=len(seed['bins']);stats['predicate_check_bins']+=len(seed['bins'])
        stats['novel_clause_covers']+=sum(c not in seed['descriptor']['predicates'] for c,_ in cover)
        return json.loads(self._proofs[key])
