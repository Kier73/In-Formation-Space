"""CIG-015: source-conditioned observation refinement and verified decoders.
Extend an admitted CIG-014 predicate seed. A semantic miss scans the bounded
source domain; a signed-union decoder needs only retained bins. Source scope
and clauses stay immutable. No lost-coordinate inversion.
"""
from collections import Counter, defaultdict
import json
from composed_ground import canonical
from regional_memory import identity, wire
from architecture_memory import Archive, region
from anticipatory_memory import leaves
from nonlinear_sufficient import make_seed, covers, plan, translate
from verify_nonlinear_sufficient import check_seed, check_translation
from verify_language_extension import check_extension


def equivalent_cover(d,clause,stats):
    """Implication paths in source binary clauses prove signed-literal equality."""
    graph={l:set() for u in d['scope'] for l in (u,-u)}
    for row in d['source']:
        if len(row)==2:
            a,b=row;graph[-a].add(b);graph[-b].add(a)
    reach={}
    for l in graph:
        seen={l};todo=[l]
        while todo:
            x=todo.pop();stats['implication_edge_visits']+=len(graph[x])
            for y in graph[x]-seen:seen.add(y);todo.append(y)
        reach[l]=seen
    representative={l:min(x for x in reach[l] if l in reach[x]) for l in graph}
    target={representative[l] for l in clause};parts=[];covered=set()
    for j,c in enumerate(d['predicates']):
        normalized={representative[l] for l in c}
        if normalized and normalized<=target:
            parts.append([0,j]);covered.update(normalized)
        if len(c)==1 and representative[-c[0]] in target-covered:
            parts.append([3,j]);covered.add(representative[-c[0]])
    for j,u in enumerate(d['visible']):
        for kind,l in ((1,u),(2,-u)):
            r=representative[l]
            if r in target-covered:parts.append([kind,j]);covered.add(r)
    return parts if covered==target else None


def extend(old, clause):
    d=old['descriptor'];s=d['scope'];v=d['visible'];p=d['predicates'];w=len(v)+len(p)
    if len(p)>=32 or clause in p or canonical([clause],d['n'])!=[tuple(clause)] or any(abs(l) not in s for l in clause):raise ValueError('extension contract')
    counts=Counter(); examples={}; stats=Counter(); parts=covers(d,clause);method='cover'
    if parts is None:
        stats['equivalence_attempts']+=1;parts=equivalent_cover(d,clause,stats);method='equivalent'
    if parts is not None:
        for k,z in old['bins']:
            bit=any(((k>>(len(v)+i))&1)^int(kind==3) if kind in (0,3) else ((k>>i)&1)^int(kind==2) for kind,i in parts)
            counts[k|(int(bit)<<w)]+=int(z)
        cert=dict(method=method,parts=parts);stats['symbolic_bins']+=len(old['bins']);stats['equivalence_extensions']+=int(method=='equivalent')
    else:
        pos={u:i for i,u in enumerate(s)}
        def mask(c):return sum(1<<pos[l] for l in c if l>0),sum(1<<pos[-l] for l in c if l<0)
        source=list(map(mask,d['source']));pred=list(map(mask,p));a,b=mask(clause)
        for x in range(1<<len(s)):
            if not all(x&m or ~x&n for m,n in source):continue
            k=sum(((x>>pos[u])&1)<<i for i,u in enumerate(v))
            k|=sum(int(bool(x&m or ~x&n))<<(len(v)+i) for i,(m,n) in enumerate(pred))
            bit=int(bool(x&a or ~x&b));counts[k|(bit<<w)]+=1;examples.setdefault((k,bit),x)
        cert=dict(method='semantic');stats['semantic_states']+=1<<len(s)
    splits=sorted(k for k,z in old['bins'] if counts[k] and counts[k|(1<<w)])
    cert.update(splits=splits,pairs=[[examples[k,0],examples[k,1]] for k in splits])
    nd=dict(d,predicates=p+[clause]);bins=[[k,str(z)] for k,z in sorted(counts.items()) if z]
    new=dict(descriptor=nd,key=identity(nd),bins=bins,bits=max(0,len(bins)-1).bit_length())
    stats['split_fibers']+=len(splits);stats['extensions']+=1
    stats['semantic_sufficient' if parts is None and not splits else 'refinements' if splits else 'symbolic_extensions']+=1
    return new,cert,stats


class Language:
    """Receiver-owned admitted seed and append-only observation language."""
    def __init__(self,n,scope,source,visible,predicates=()):
        seed,work=make_seed(n,scope,source,visible,list(predicates))
        if not check_seed(n,scope,source,visible,list(predicates),seed):raise ValueError('seed failed')
        self._raw=wire(seed);self.stats=Counter(work);self.stats['seed_check_states']+=1<<len(scope)
    def snapshot(self):return json.loads(self._raw)
    def ensure(self,clause,stats):
        old=self.snapshot();d=old['descriptor']
        if clause in d['predicates']:return
        if len(d['predicates'])>=32:raise OverflowError('predicate budget')
        new,cert,work=extend(old,clause)
        if not check_extension(old,clause,cert,new):raise ValueError('extension failed')
        self._raw=wire(new);stats.update(work);stats['extension_check_states']+=work['semantic_states'];stats['extension_check_bins']+=work['symbolic_bins']


class LanguageRetained:
    def __init__(self,source,n,tree,forecasts=()):
        self.n=n;self.languages=defaultdict(list);self.stats=Counter()
        base=dict(leaves(source,n,tree));specs={cov:[set(b),set()] for cov,b in base.items()}
        by_scope=defaultdict(list)
        for cov in base:by_scope[cov[0]].append(cov)
        for src,t in forecasts:
            for target,b in leaves(src,n,t):
                choices=[c for c in by_scope[target[0]] if set(c[1])<=set(target[1])]
                if choices:
                    c=min(choices,key=lambda c:(-len(c[1]),c[1]));a,p=specs[c];a.update(b);p.update(set(target[1])-set(c[1]))
        for cov,(a,p) in specs.items():
            if len(p)>32:continue
            lang=Language(n,cov[0],cov[1],sorted(a),list(p));self.languages[cov[0]].append(lang);self.stats.update(lang.stats)
    def session(self):return LanguageArchive(self)
    def size(self):return sum(len(l._raw) for ls in self.languages.values() for l in ls),sum(len(l.snapshot()['bins']) for ls in self.languages.values() for l in ls)


class LanguageArchive(Archive):
    def __init__(self,retained):super().__init__();self.retained=retained
    def obtain(self,desc,children,stats):
        if children is not None or identity(desc) in self._proofs:return super().obtain(desc,children,stats)
        cov=region(desc['scope'],desc['clauses']);b=tuple(desc['boundary']);new=set(cov[1])
        for lang in self.retained.languages.get(cov[0],()):
            seed=lang.snapshot();d=seed['descriptor'];old=set(map(tuple,d['source']))
            if not old<=new or not set(b)<=set(d['visible']):continue
            added=sorted(new-old,key=lambda c:(len(c),c))
            missing=[list(c) for c in added if covers(d,c) is None]
            if len(d['predicates'])+len(missing)>32:continue
            for c in missing:lang.ensure(c,stats)
            seed=lang.snapshot();cover=plan(seed,desc)
            if cover is None:raise ValueError('extended language failed')
            msg=translate(seed,desc,cover)
            if not check_translation(self.retained.n,seed,desc,cover,msg):raise ValueError('translation failed')
            key=msg['key'];self._proofs[key]=wire(msg);self._coverage[key]=cov;self._functions[cov][b]=wire(msg)
            stats['language_hits']+=1;stats['query_bins']+=len(seed['bins']);return json.loads(self._proofs[key])
        return super().obtain(desc,children,stats)
