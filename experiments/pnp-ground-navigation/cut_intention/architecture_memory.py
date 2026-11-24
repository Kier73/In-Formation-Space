"""CIG-012: receiver-admitted source-region identities across architecture changes.

A regional count depends on its exact owned clauses, variable domain and
exposed coordinates, not the binary derivation tree. Cache only admitted
functions. A marginal is never inverted. Reuse is local session evidence.
"""
from collections import Counter, defaultdict
from time import perf_counter_ns
import json
from adaptive_ground import annotate, realize, flatten, balanced, leaf
from composed_ground import canonical, extract
from regional_memory import identity, wire, produce
from verify_adaptive_ground import audit
from verify_architecture_memory import check_join_coverage, check_transfer
from verify_regional_memory import verify_message


def region(scope, clauses):
    return (tuple(sorted(set(scope))), tuple(sorted(set(map(tuple,clauses)), key=lambda c:(len(c),c))))


def combine(a,b):
    if set(a[1]) & set(b[1]): raise ValueError('overlapping clause ownership')
    return region(a[0]+b[0], a[1]+b[1])


def marginal(old,b,key):
    positions=[old['boundary'].index(v) for v in b]; counts=[0]*(1<<len(b))
    for x,v in enumerate(old['counts']):
        counts[sum(((x>>i)&1)<<j for j,i in enumerate(positions))]+=int(v)
    return dict(key=key,boundary=b,counts=list(map(str,counts)))


class Archive:
    """Compatible with adaptive_ground.realize; no external admission API.

    The audited traversal supplies exact leaf scopes and disjoint clauses.
    Internal coverage is derived from admitted children, not sender claims.
    Identity of a function excludes its derivation, but new proof keys still
    bind destination children. All stored messages are immutable JSON bytes.
    """
    def __init__(self):
        self._proofs={}; self._coverage={}; self._functions=defaultdict(dict)

    def obtain(self,desc,children,stats):
        key=identity(desc); b=tuple(desc['boundary'])
        if children is None:
            cov=region(desc['scope'],desc['clauses'])
        else:
            for c in children:
                if self._proofs.get(c['key'])!=wire(c): raise ValueError('unadmitted child')
            left,right=[self._coverage[c['key']] for c in children]
            if not check_join_coverage(left,right,children[0]['boundary'],children[1]['boundary'],b):
                raise ValueError('join lost shared coordinate or duplicated source clause')
            cov=combine(left,right)
            if desc['children']!=[identity(c) for c in children]: raise ValueError('child binding')
        if not set(b)<=set(cov[0]):raise ValueError('boundary outside region')
        # Direct proof identity still has precedence.
        if key in self._proofs:
            if self._coverage[key]!=cov:raise ValueError('coverage changed')
            stats['proof_reuse']+=1;return json.loads(self._proofs[key])
        variants=self._functions[cov]
        if b in variants:
            old=json.loads(variants[b]);msg=dict(old,key=key)
            if not check_transfer(self._coverage[old['key']],cov,old,msg):raise ValueError('transfer failed')
            stats['architecture_transfer']+=1
        else:
            supersets=[v for v in variants if set(b)<=set(v)]
            if supersets:
                old=json.loads(variants[min(supersets,key=lambda x:(len(x),x))]);msg=marginal(old,list(b),key)
                if not check_transfer(self._coverage[old['key']],cov,old,msg):raise ValueError('independent projection failed')
                stats['interface_projection']+=1;stats['projection_cells']+=len(old['counts'])
            else:
                msg,route,cells=produce(desc,children)
                if not verify_message(desc,children,msg):raise ValueError('independent source operation failed')
                stats[route]+=1;stats['producer_cells']+=cells;stats['new_full_checks']+=1
        self._proofs[key]=wire(msg);self._coverage[key]=cov;variants[b]=wire(msg)
        return json.loads(self._proofs[key])

    def estimate(self,source,n,tree,*,check_weight=0,message_weight=0):
        """Pure metadata preview. Counts each target node, even a cache hit.
        Estimates producer cells and full checks; projection verification and
        source/witness costs remain separate. No speculative archive mutation.
        """
        root=annotate(tree)
        if not audit(source,n,tree,root):raise ValueError('source layout')
        cost=Counter()
        def walk(node):
            b=tuple(node['boundary']);cs=node['children'];cost['nodes']+=1
            if cs is None:
                r=node['region'];cov=region(r['scope'],r['clauses'])
                _,residual=extract(canonical(r['clauses'],n));w=len(cov[0]) if residual else len(b)
            else:
                cov=combine(*(walk(c) for c in cs));w=len(set(cs[0]['boundary'])|set(cs[1]['boundary']))
            variants=self._functions.get(cov,{})
            if b in variants:cost['exact_hits']+=1
            else:
                ss=[v for v in variants if set(b)<=set(v)]
                if ss:cost['projection_cells']+=1<<min(map(len,ss));cost['projections']+=1
                else:cost['producer_cells']+=1<<w;cost['new_full_checks']+=1
            return cov
        walk(root)
        cost['objective']=cost['producer_cells']+cost['projection_cells']+check_weight*cost['new_full_checks']+message_weight*cost['nodes']
        return dict(cost)


def choose(source,n,catalog,archive,*,check_weight=0,message_weight=0):
    if any(type(w)is not int or w<0 for w in (check_weight,message_weight)):raise ValueError('cost contract')
    t=perf_counter_ns(); rows=[]; best=None
    for name,tree in catalog.items():
        try:s=archive.estimate(source,n,tree,check_weight=check_weight,message_weight=message_weight)
        except (OverflowError,RecursionError):continue
        rows.append(dict(name=name,**s));rank=(s['objective'],s['nodes'],name)
        if best is None or rank<best[0]:best=(rank,name,tree)
    if best is None:return dict(status='UNKNOWN',candidates=rows)
    return dict(status='SELECTED',selected=best[1],tree=best[2],candidates=rows,selection_ns=perf_counter_ns()-t)


def coarsen(tree,width=8):
    """Collapse qualified subtrees into leaf regions, preserving clause ownership."""
    if isinstance(tree,dict):return tree
    ls=list(flatten(tree));s=set(v for l in ls for v in l['scope'])
    if len(s)<=width:return leaf(s,[c for l in ls for c in l['clauses']])
    return [coarsen(c,width) for c in tree]
