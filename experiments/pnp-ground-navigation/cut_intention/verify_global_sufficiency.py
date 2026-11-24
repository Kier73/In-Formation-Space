"""Independent source verifier for CIG-017. No producer import."""
from itertools import product
from hashlib import sha256
import json
from verify_composed_ground import normal, accepted, verify as check_count


def contract(n,source,q,f):
    c=normal(source,n)
    if len(q)>1024:raise ValueError('observer budget')
    def pred(p):
        if not p or len(p)>63 or normal([p],n)!=[tuple(p)]:raise ValueError('canonical nonempty clause required')
        return tuple(p)
    q=tuple(pred(p) for p in q);f=pred(f)
    if len(set(q))!=len(q):raise ValueError('duplicate observations')
    return c,q,f


def value(p,x):return int(any((x//2**(abs(l)-1))%2==int(l>0) for l in p))

def maskvars(m,n):
    if type(m)is not int or not 0<m<1<<n:raise ValueError('invalid equation')
    v=[]
    while m:
        z=m&-m;v.append(z.bit_length());m-=z
    return v


def check_affine(n,source,q,f,d):
    eqs=d['equations'];rows=set(source)
    if len(d['terms'])!=len(f):return False
    for vs,b in eqs:
        if not 1<=len(vs)<=3 or any(type(v)is not int or not 1<=v<=n for v in vs) or vs!=sorted(set(vs)) or type(b)is not int or b not in (0,1):return False
        for assignment in product((0,1),repeat=len(vs)):
            if sum(assignment)%2!=b and tuple(v if bit==0 else -v for v,bit in zip(vs,assignment)) not in rows:return False
    for l,t in zip(f,d['terms']):
        js=t['inputs'];ids=t['proof'];constant=t['constant']
        if any(type(j)is not int or not 0<=j<len(q) or len(q[j])!=1 for j in js) or js!=sorted(set(js)):return False
        if any(type(i)is not int or not 0<=i<len(eqs) for i in ids) or ids!=sorted(set(ids)):return False
        if type(constant)is not int or constant not in (0,1):return False
        m=0;b=0
        for i in ids:
            vs,c=eqs[i];m^=sum(1<<(v-1) for v in vs);b^=c
        want=1<<(abs(l)-1);rhs=constant^int(l<0)
        for j in js:want^=1<<(abs(q[j][0])-1);rhs^=int(q[j][0]<0)
        if (m,b)!=(want,rhs):return False
    return True


def check_circuit(n,source,q,f,d):
    known={abs(c[0]) for c in q if len(c)==1};rows=set(source)
    for g in d['gates']:
        v=g['output'];ins=g['inputs'];table=g['table'];clauses=list(map(tuple,g['clauses']))
        if type(v)is not int or not 1<=v<=n or v in known or len(ins)>2 or len(ins)!=len(set(ins)) or any(type(i)is not int or i not in known for i in ins):return False
        if len(table)!=2**len(ins) or any(type(b)is not int or b not in (0,1) for b in table):return False
        if not clauses or any(c not in rows or not set(map(abs,c))<=set(ins)|{v} for c in clauses):return False
        for a in product((0,1),repeat=len(ins)):
            values=dict(zip(ins,a));idx=sum(b*2**i for i,b in enumerate(a));possible=[]
            for b in (0,1):
                values[v]=b
                if all(any(values[abs(l)]==int(l>0) for l in c) for c in clauses):possible.append(b)
            if possible!=[table[idx]]:return False
        known.add(v)
    return set(map(abs,f))<=known


def pair_source(n,source,q,f):
    # Reconstruct independently using explicit left/right output indices.
    k=len(q)+1;rows=[]
    for offset,base in ((0,2*n),(n,2*n+k)):
        def move(c):return tuple((abs(l)+offset) if l>0 else -(abs(l)+offset) for l in c)
        rows.extend(move(c) for c in source)
        for j,c in enumerate(q+(f,),1):
            p=base+j;shifted=move(c)
            rows.extend([(p,-l) for l in shifted]);rows.append((*shifted,-p))
    for j in range(1,k+1):
        l=2*n+j;r=l+k
        rows.extend([(l,-r),(-l,r)] if j<k else [(l,r),(-l,-r)])
    return 2*n+2*k,rows


def verify(n,source,q,f,r,*,width=12,cells=2_000_000,decoder_bits=6):
    try:
        source,q,f=contract(n,source,q,f)
        key=sha256(json.dumps([n,source,q,f],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if r['schema']!='ifs.cig017.global-sufficiency.v1' or r['contract']!=key:return False
        status=r['status'];route=r['route'];d=r['decoder']
        if status=='UNKNOWN':return False # not an admitted proof
        if route=='union':
            js=d['inputs']
            return status=='SUFFICIENT' and all(type(j)is int and 0<=j<len(q) for j in js) and js==sorted(set(js)) and set().union(*(set(q[j]) for j in js))==set(f)
        if route=='affine':return status=='SUFFICIENT' and check_affine(n,source,q,f,d)
        if route=='circuit':return status=='SUFFICIENT' and check_circuit(n,source,q,f,d)
        if route!='paired':return False
        if status=='INSUFFICIENT':
            if d is not None or len(r['witness'])!=2:return False
            xs=r['witness']
            if any(type(x)is not str or not x.isascii() or not x.isdecimal() or str(int(x))!=x for x in xs):return False
            a,b=map(int,xs)
            return all(0<=x<1<<n and accepted(source,x) for x in (a,b)) and all(value(p,a)==value(p,b) for p in q) and value(f,a)!=value(f,b)
        nn,rows=pair_source(n,source,q,f)
        if status!='SUFFICIENT' or r['proof']['status']!='UNSAT' or not check_count(rows,nn,r['proof'],max_width=width,max_cells=cells):return False
        if d is None:return True
        if len(q)>decoder_bits or len(q)>8 or len(d['proofs'])!=2**len(q):return False
        anf=d['anf']
        if any(type(m)is not int or not 0<=m<1<<len(q) for m in anf) or anf!=sorted(set(anf)):return False
        for idx,p in enumerate(d['proofs']):
            extra=[f]
            for j,c in enumerate(q):
                if idx//2**j%2:extra.append(c)
                else:extra.extend([(-l,) for l in c])
            if not check_count(source+extra,n,p,max_width=width,max_cells=cells):return False
            if sum((idx&m)==m for m in anf)%2!=int(p['status']=='SAT'):return False
        return True
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False


from verify_proof_refinement import Receiver, MAX_PREDICATES, predicate, signature


def decode_checked(q,f,r,code):
    d=r['decoder']
    if r['route']=='union':return int(any(code//2**j%2 for j in d['inputs']))
    if r['route']=='affine':
        return int(any((t['constant']+sum(code//2**j%2 for j in t['inputs']))%2 for t in d['terms']))
    if r['route']=='circuit':
        a={abs(c[0]):(code//2**j%2)^int(c[0]<0) for j,c in enumerate(q) if len(c)==1}
        for g in d['gates']:
            a[g['output']]=g['table'][sum(a[v]*2**i for i,v in enumerate(g['inputs']))]
        return int(any(a[abs(l)]==int(l>0) for l in f))
    return sum(code&m==m for m in d['anf'])%2


class GlobalReceiver(Receiver):
    """Extend only receiver-owned, already verified exact fibers."""
    def accept_global(self,f,r,*,width=12,cells=2_000_000,decoder_bits=6):
        q,old=self.snapshot();f=predicate(self.n,f)
        if f in q or len(q)>=MAX_PREDICATES:raise ValueError('extension contract')
        if not verify(self.n,self.source,q,f,r,width=width,cells=cells,decoder_bits=decoder_bits):raise ValueError('unverified global proof')
        if r['status']!='SUFFICIENT' or r['decoder'] is None:return False
        new={}
        for code,(count,witness) in old.items():
            b=decode_checked(q,f,r,code)
            if not accepted(self.source,witness) or signature(q,witness)!=code or value(f,witness)!=b:raise ValueError('representative mismatch')
            new[code|(b<<len(q))]=(count,witness)
        self._predicates=q+(f,);self._fibers=new
        self.stats['global_admissions']+=1
        return True
