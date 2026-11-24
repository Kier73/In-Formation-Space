"""Independent constructive surjectivity proof: C(section(u)) and q(section(u))=u.
No producer import. The proof is local totality plus complete clause coverage.
"""
from hashlib import sha256
from itertools import product
import json
from verify_global_sufficiency import contract


def verify_section(n,source,q,r):
    try:
        s,q,_=contract(n,source,q,(1,));rows=set(s);seen=set();used=set()
        if set(r)!={'schema','key','free','gates'} or r['schema']!='ifs.cig021.section.v1' or r['key']!=sha256(json.dumps([n,s,q],sort_keys=True,separators=(',',':')).encode()).hexdigest():return False
        for c in q:
            # Disjoint clause seeds: choose first literal equal to the code bit,
            # all other literals false. This realizes each clause independently.
            if not c or seen.intersection(map(abs,c)):return False
            seen.update(map(abs,c))
        if type(r['free'])is not list or any(type(v)is not int or not 1<=v<=n or v in seen for v in r['free']) or len(set(r['free']))!=len(r['free']):return False
        seen.update(r['free'])
        if type(r['gates'])is not list or len(r['gates'])>n:return False
        for g in r['gates']:
            if set(g)!={'output','inputs','table','clauses'}:return False
            v,inputs,table,cs=g['output'],g['inputs'],g['table'],g['clauses']
            if type(v)is not int or not 1<=v<=n or v in seen or type(inputs)is not list or not 1<=len(inputs)<=2 or any(type(i)is not int or i not in seen for i in inputs) or len(set(inputs))!=len(inputs):return False
            if type(table)is not list or len(table)!=2**len(inputs) or any(type(b)is not int or b not in (0,1) for b in table):return False
            if not cs or any(type(l)is not int for c in cs for l in c):return False
            local={tuple(c) for c in cs}
            if not local<=rows or any(abs(l) not in set(inputs)|{v} for c in local for l in c):return False
            for bits in product((0,1),repeat=len(inputs)):
                env=dict(zip(inputs,bits));ix=sum(b*2**i for i,b in enumerate(bits));env[v]=table[ix]
                if any(not any(env[abs(l)]==int(l>0) for l in c) for c in local):return False
            seen.add(v);used.update(local)
        return seen==set(range(1,n+1)) and used==rows
    except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError):return False
