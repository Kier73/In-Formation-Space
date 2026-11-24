"""CIG-010: adaptive exact count trees with proof and value identities separated.
Reuse requires receiver-owned admission, not a sender-provided digest.
"""
from collections import Counter, defaultdict
from itertools import product
from time import perf_counter_ns
import json
from regional_memory import discover, bind, produce, identity, wire, index
from composed_ground import canonical
from verify_regional_memory import verify_message


def leaf(scope, clauses):
    return {'scope': sorted(scope), 'clauses': [list(c) for c in sorted(clauses,key=lambda c:(len(c),tuple(c)))]}


def balanced(nodes):
    if len(nodes)==1: return nodes[0]
    m=len(nodes)//2
    return [balanced(nodes[:m]),balanced(nodes[m:])]


def initial(source,n,width=8):
    p=discover(source,n,width); _,assigned,_=bind(source,n,p)
    return balanced([leaf(s,c) for s,c in zip(p['leaves'],assigned)])


def flatten(tree):
    if isinstance(tree,dict): yield tree
    else:
        for child in tree: yield from flatten(child)


def revise(tree,source,n,*,split=True,merge=False,width=8):
    """Preserve old subtrees. New crossing clauses get a new leaf at their LCA.
    Scope shrink/split is optional; all declared coordinates survive, including free ones.
    Full-source rebinding is charged. Heuristic, not optimal treewidth search.
    """
    if type(width) is not int or not 1<=width<=10: raise ValueError('width')
    rows=set(canonical(source,n)); old=set(); stats=Counter()
    def trim(t):
        if isinstance(t,list): return [trim(t[0]),trim(t[1])]
        s=t['scope']; c=[tuple(r) for r in t['clauses'] if tuple(r) in rows]; old.update(c)
        return leaf(s,c)
    root=trim(tree)
    # Empty bridge regions may vanish if every coordinate is still represented.
    totals=Counter(v for t in flatten(root) for v in t['scope'])
    def prune(t):
        if isinstance(t,dict):
            if not t['clauses'] and all(totals[v]>1 for v in t['scope']):
                totals.subtract(t['scope']);stats['removed_empty_regions']+=1;return None
            return t
        l,r=map(prune,t)
        if l is None:return r
        if r is None:return l
        return [l,r]
    root=prune(root)
    # Insert each new factor in the smallest old subtree whose scope covers it.
    # Batch by target path so multiple added clauses do not create a linear-depth spine.
    def locate(t,path,s):
        if isinstance(t,dict):
            return path,set(t['scope'])
        l,ls=locate(t[0],path+(0,),s); r,rs=locate(t[1],path+(1,),s)
        return (l if s<=ls else r if s<=rs else path),ls|rs
    additions=defaultdict(list)
    for c in sorted(rows-old,key=lambda c:(len(c),c)):
        s=set(map(abs,c))
        if len(s)>width: raise OverflowError('new clause exceeds local width')
        path,scope=locate(root,(),s)
        if not s<=scope: raise ValueError('new variable outside fixed domain')
        additions[path].append(c)
    def insert(t,path):
        extra=additions.get(path,[])
        if isinstance(t,dict):
            return leaf(t['scope'],[*map(tuple,t['clauses']),*extra])
        children=[insert(t[0],path+(0,)),insert(t[1],path+(1,))]
        if not extra:return children
        stats['inserted_bridge_regions']+=len(extra)
        bridges=[leaf(set(map(abs,c)),[c]) for c in extra]
        return [children,balanced(bridges)]
    root=insert(root,())
    def restructure(t):
        if isinstance(t,dict):
            if not split: return t
            # Components of local constraint graph, with free coordinates as singletons.
            groups=[{v} for v in t['scope']]
            for c in t['clauses']:
                s=set(map(abs,c)); hit=[g for g in groups if s&g]
                if hit: groups=[g for g in groups if g not in hit]+[set().union(*hit)]
            if len(groups)<=1:return t
            groups.sort(key=lambda g:min(g)); pieces=[]
            for i,g in enumerate(groups):
                cs=[c for c in t['clauses'] if (c and set(map(abs,c))<=g) or (not c and i==0)]
                pieces.append(leaf(g,cs))
            stats['split_regions']+=1
            return balanced(pieces)
        l,r=map(restructure,t)
        if merge and isinstance(l,dict) and isinstance(r,dict):
            s=set(l['scope'])|set(r['scope'])
            if len(s)<=width:
                stats['merged_regions']+=1
                return leaf(s,[*l['clauses'],*r['clauses']])
        return [l,r]
    return restructure(root),dict(stats)


def annotate(tree):
    totals=Counter(v for t in flatten(tree) for v in t['scope'])
    def walk(t):
        if isinstance(t,dict): f=Counter(t['scope']); children=None
        else:
            l,lf=walk(t[0]); r,rf=walk(t[1]); f=lf+rf; children=[l,r]
        b=sorted(v for v,k in f.items() if k<totals[v])
        if len(b)>12 or children and len(set(children[0]['boundary'])|set(children[1]['boundary']))>12:
            raise OverflowError('interface width budget')
        return dict(boundary=b,children=children,region=t if children is None else None),f
    return walk(tree)[0]


def semantic(m):
    return {'boundary':m['boundary'],'counts':m['counts']}


class Memory:
    """Separate leaf proofs and exact join-operation results; memory is receiver-local.
    A projection may be derived from a verified finer leaf with identical local source.
    No reuse based merely on a producer's assertion of equality.
    """
    def __init__(self): self.__proofs={}; self.__values={}; self.__finer=defaultdict(list)
    def obtain(self,desc,children,stats):
        key=identity(desc); source_key=None
        if children is not None:
            for c in children:
                if self.__proofs.get(c['key'])!=wire(c): raise ValueError('unadmitted dependency')
        if key in self.__proofs:
            stats['proof_reuse']+=1
            return json.loads(self.__proofs[key])
        if children is None:
            source_key=identity([desc['scope'],desc['clauses']]); b=desc['boundary']
            for data in self.__finer[source_key]:
                old=json.loads(data)
                if set(b)<=set(old['boundary']):
                    counts=[0]*(1<<len(b)); positions=[old['boundary'].index(v) for v in b]
                    for x,v in enumerate(old['counts']):
                        counts[sum((x>>i&1)<<j for j,i in enumerate(positions))]+=int(v)
                    msg={'key':key,'boundary':b,'counts':list(map(str,counts))}
                    # Independent tuple projection checker, not the original leaf enumeration.
                    from verify_adaptive_ground import verify_projection
                    if not verify_projection(old,msg):raise ValueError('projection failed')
                    stats['projected_leaf']+=1; stats['projection_cells']+=len(old['counts']); break
            else:msg=None
        else:
            # A new derivation can reuse the old exact operation on admitted values.
            # Child proof identity is intentionally excluded from the *operation* key.
            op=wire([desc['boundary'],sorted([semantic(c) for c in children],key=wire)])
            if op in self.__values:
                msg={'key':key,'boundary':desc['boundary'],'counts':json.loads(self.__values[op])}
                stats['semantic_join_reuse']+=1
            else: msg=None
        if msg is None:
            msg,route,cells=produce(desc,children)
            if not verify_message(desc,children,msg):raise ValueError('independent message check failed')
            stats[route]+=1;stats['producer_cells']+=cells;stats['new_full_checks']+=1
        self.__proofs[key]=wire(msg)
        if children is None: self.__finer[source_key].append(wire(msg))
        else:self.__values[op]=wire(msg['counts'])
        return json.loads(self.__proofs[key])


def realize(source,n,tree,memory=None,*,witness=True):
    from verify_adaptive_ground import audit
    t=perf_counter_ns(); rows=canonical(source,n); root=annotate(tree)
    if not audit(source,n,tree,root): raise ValueError('source/region audit')
    audit_ns=perf_counter_ns()-t; stats=Counter(); memory=memory or Memory()
    records={}; results={}
    def walk(node):
        cs=None if node['children'] is None else [walk(c) for c in node['children']]
        d={'version':'ifs.cig010.adaptive.v1','boundary':node['boundary']}
        if cs is None:d.update(node['region'])
        else:d['children']=[identity(c) for c in cs]
        m=memory.obtain(d,cs,stats);records[m['key']]=m;results[id(node)]=m;return m
    t=perf_counter_ns(); m=walk(root); navigation_ns=perf_counter_ns()-t
    count=int(m['counts'][0]); a={}; t=perf_counter_ns()
    def descend(node):
        if node['children'] is None:
            r=node['region']; s=r['scope']; unknown=[v for v in s if v not in a]
            for bits in product((0,1),repeat=len(unknown)):
                a.update(zip(unknown,bits))
                if all(any(a[abs(l)]==int(l>0) for l in c) for c in r['clauses']):return
        else:
            l,r=node['children']; lc,rc=results[id(l)],results[id(r)]
            unknown=sorted((set(lc['boundary'])|set(rc['boundary']))-a.keys())
            for bits in product((0,1),repeat=len(unknown)):
                a.update(zip(unknown,bits))
                if int(lc['counts'][index(lc['boundary'],a)]) and int(rc['counts'][index(rc['boundary'],a)]):
                    descend(l);descend(r);return
        raise AssertionError('missing witness')
    if count and witness:
        descend(root)
        if set(a)!=set(range(1,n+1)) or not all(any(a[abs(l)]==int(l>0) for l in c) for c in rows):raise AssertionError('source witness')
    return {'source':identity([n,rows]),'plan':identity(tree),'root':m['key'],'count':str(count),'witness':''.join(str(a[v]) for v in sorted(a)) if a else None,'messages':records,'metrics':dict(stats),'audit_ns':audit_ns,'navigation_ns':navigation_ns,'witness_ns':perf_counter_ns()-t}
