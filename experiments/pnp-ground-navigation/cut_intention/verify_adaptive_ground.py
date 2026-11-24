"""Independent source partition, top-down boundary and projection audit."""
from itertools import product
from verify_composed_ground import normal


def audit(source,n,tree,root):
    try:
        rows=normal(source,n); seen=[]; scopes={}; nodes=0
        def scope(t,r,depth):
            nonlocal nodes
            nodes+=1
            if nodes>32767 or depth>128:raise ValueError('tree budget')
            if type(t) is dict:
                if set(t)!={'scope','clauses'} or r['region']!=t or r['children'] is not None:raise ValueError('leaf')
                s=t['scope']
                if len(s)>10 or any(type(v)is not int or not 1<=v<=n for v in s) or s!=sorted(set(s)):raise ValueError('scope')
                for c in t['clauses']:
                    if any(type(l)is not int or abs(l) not in s for l in c):raise ValueError('literal')
                    seen.append(tuple(c))
                result=set(s)
            elif type(t)is list and len(t)==2 and len(r['children'])==2 and r['region'] is None:
                result=scope(t[0],r['children'][0],depth+1)|scope(t[1],r['children'][1],depth+1)
            else:raise ValueError('tree')
            scopes[id(r)]=result;return result
        if scope(tree,root,0)!=set(range(1,n+1)) or sorted(seen,key=lambda c:(len(c),c))!=rows:return False
        def check(r,outside):
            b=sorted(scopes[id(r)]&outside)
            if r['boundary']!=b or len(b)>12:return False
            if r['children'] is None:return True
            l,h=r['children']
            return len(set(l['boundary'])|set(h['boundary']))<=12 and check(l,set(b)|scopes[id(h)]) and check(h,set(b)|scopes[id(l)])
        return check(root,set())
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,RecursionError):return False


def verify_projection(old,new):
    try:
        fine=old['boundary']; coarse=new['boundary']
        if not set(coarse)<=set(fine) or len(old['counts'])!=2**len(fine) or len(new['counts'])!=2**len(coarse):return False
        sums={z:0 for z in product((0,1),repeat=len(coarse))}
        for z in product((0,1),repeat=len(fine)):
            a=dict(zip(fine,z));sums[tuple(a[v] for v in coarse)]+=int(old['counts'][sum(v*2**i for i,v in enumerate(z))])
        return all(new['counts'][sum(v*2**i for i,v in enumerate(z))]==str(c) for z,c in sums.items())
    except (ValueError,TypeError,KeyError,IndexError):return False
