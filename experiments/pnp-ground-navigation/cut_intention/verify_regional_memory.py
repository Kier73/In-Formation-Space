"""Independent local verifier: finite assignment truth oracle and relational join.

Children are receiver-admitted messages, not arbitrary producer inputs. The
public replay path in regional_memory creates a fresh receiver for untrusted
packets; each node is independently checked before its parent is admitted.
"""
from hashlib import sha256
from itertools import product
import json


def _hash(x):
    return sha256(json.dumps(x,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('ascii')).hexdigest()


def verify_message(desc,children,msg):
    try:
        if set(msg)!={'key','boundary','counts'} or msg['key']!=_hash(desc) or msg['boundary']!=desc['boundary']:
            return False
        b=tuple(desc['boundary']); raw=msg['counts']
        if len(b)>12 or len(raw)!=2**len(b) or any(type(x) is not str or not x.isascii() or not x.isdecimal() or str(int(x))!=x for x in raw): return False
        expected={z:0 for z in product((0,1),repeat=len(b))}
        if children is None:
            s=desc['scope']
            if len(s)>10 or not set(b)<=set(s): return False
            for values in product((0,1),repeat=len(s)):
                a=dict(zip(s,values))
                if all(any((a[abs(l)]==1) == (l>0) for l in row) for row in desc['clauses']):
                    expected[tuple(a[v] for v in b)]+=1
        else:
            if len(children)!=2 or desc['children']!=[_hash(c) for c in children]:return False
            l,r=children; ls,rs=l['boundary'],r['boundary']
            if len(set(ls)|set(rs))>12 or not set(b)<=set(ls)|set(rs): return False
            common=sorted(set(ls)&set(rs)); groups={}
            for i,z in enumerate(product((0,1),repeat=len(rs))):
                # Producer packed table is little endian; tuple product is not.
                idx=sum(v*2**j for j,v in enumerate(z)); weight=int(r['counts'][idx])
                if weight:
                    a=dict(zip(rs,z)); groups.setdefault(tuple(a[v] for v in common),[]).append((a,weight))
            for z in product((0,1),repeat=len(ls)):
                idx=sum(v*2**j for j,v in enumerate(z)); weight=int(l['counts'][idx])
                if not weight:continue
                a=dict(zip(ls,z))
                for q,w in groups.get(tuple(a[v] for v in common),[]):
                    joined=a|q; expected[tuple(joined[v] for v in b)]+=weight*w
        return all(int(raw[sum(v*2**j for j,v in enumerate(z))])==value for z,value in expected.items())
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False


def audit_layout(source,n,plan,assigned,root):
    """Separate source partition and separator audit, before any cache access.

    Check each canonical source clause is assigned exactly once and every leaf
    owns its variables. The top-down external boundary recurrence independently
    checks the producer's bottom-up occurrence-count computation.
    """
    from verify_composed_ground import normal
    try:
        rows=normal(source,n); leaves=plan['leaves']; seen=[]; scopes={}
        if plan['n']!=n or len(assigned)!=len(leaves): return False
        for s,cs in zip(leaves,assigned):
            if len(s)>10 or s!=sorted(set(s)) or any(type(v)is not int or not 1<=v<=n for v in s): return False
            scope=set(s)
            for c in cs:
                if not set(map(abs,c))<=scope:return False
                seen.append(tuple(c))
        if sorted(seen,key=lambda c:(len(c),c))!=rows:return False
        def union(node,a,b):
            if tuple(node['span'])!=(a,b):raise ValueError('span')
            if b-a==1:
                if node['children'] is not None:raise ValueError('leaf')
                s=set(leaves[a])
            else:
                l,r=node['children']; m=(a+b)//2; s=union(l,a,m)|union(r,m,b)
            scopes[(a,b)]=s; return s
        if union(root,0,len(leaves))!=set(range(1,n+1)):return False
        def boundaries(node,outside):
            s=scopes[tuple(node['span'])]; b=set(node['boundary'])
            if list(node['boundary'])!=sorted(s&outside) or len(b)>12:return False
            if node['children'] is None:return True
            l,r=node['children']; ls,rs=[scopes[tuple(c['span'])] for c in (l,r)]
            lb=set(l['boundary']); rb=set(r['boundary'])
            return len(lb|rb)<=12 and boundaries(l,b|rs) and boundaries(r,b|ls)
        return boundaries(root,set())
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False
