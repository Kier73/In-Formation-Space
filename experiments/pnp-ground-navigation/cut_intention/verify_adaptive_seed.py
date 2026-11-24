"""Independent semantic admission of adaptive seed relations and derived facts."""
from copy import deepcopy
from verify_rank_anchors import nat

class SeedReceiver:
    def __init__(self,v,members):
        self.v=v;members=tuple(members)
        if any(type(i) is not int for i in members):raise ValueError('members')
        self.members=tuple(sorted(set(members)));self.relations=[]
        if not self.members or len(self.members)>12 or any(type(i) is not int or i not in v.books for i in self.members):raise ValueError('unretained seed')
    def admit(self,z,max_work=500000):
        try:
            v=self.v;a=v.a;d=a.d
            if type(z) is not dict:return False
            kind=z['kind']
            if kind=='shift':
                if z['base'] not in self.members or not v.admit_shift(z):return False
                j=len(v.links)-1
            elif kind=='residual':
                if set(z)!={'kind','link','disagreement'}:return False
                r=z['link']
                if r['base'] not in self.members:return False
                # Check the supplied cost-related count before admitting the link.
                if nat(z['disagreement'])!=v.count(r['plus'])+v.count(r['minus']):return False
                if not v.admit_link(r):return False
                j=len(v.links)-1
            elif kind=='span':
                if set(z)!={'kind','target','den','constant','terms'} or type(max_work) is not int or max_work<1:return False
                t,den,c,terms=z['target'],z['den'],z['constant'],z['terms']
                if type(t) is not int or not 0<=t<len(a.roots) or type(den) is not int or not 1<=den<=16 or type(c) is not int or abs(c)>32 or type(terms) is not list or len(terms)>12:return False
                if any(type(row) is not list or len(row)!=2 or type(row[0]) is not int or row[0] not in self.members or row[0]==t or type(row[1]) is not int or not 0<abs(row[1])<=32 for row in terms):return False
                if [i for i,_ in terms]!=sorted(set(i for i,_ in terms)):return False
                used=0
                for p in range(a.D):
                    used+=len(terms)+1
                    if used>max_work or den*(a.prefix[t]>>p&1)!=c+sum(w*(a.prefix[i]>>p&1) for i,w in terms):return False
                # Traverse the synchronized product by DFS, but deduplicate
                # child tuples at each level. This is exact on the CRT cube.
                stack=[(a.roots[t],)+tuple(a.roots[i] for i,w in terms)];seen=set()
                while stack:
                    s=stack.pop()
                    if s in seen:continue
                    seen.add(s);used+=1;k=min(d.level(x) for x in s)
                    if k==len(d.base):
                        if den*s[0]!=c+sum(w*x for x,(_,w) in zip(s[1:],terms)):return False
                    else:
                        used+=len(s)*d.base[k]
                        if used>max_work:return False
                        stack.extend(set(tuple(d.arc(x,k,r) for x in s) for r in range(d.base[k])))
                    if used>max_work:return False
                j=None
            else:return False
            self.relations.append((deepcopy(z),j));return True
        except (ValueError,TypeError,IndexError,KeyError,OverflowError):return False
    def verify_span(self,j,p,r,*,commit=True):
        try:
            if type(j) is not int or not 0<=j<len(self.relations) or type(p) is not int or not 0<=p<=self.v.P:return False
            z,_=self.relations[j]
            if z['kind']!='span' or type(r) is not dict or set(r)!={'phase','lower','upper','status'} or nat(r['phase'])!=p:return False
            # Independent endpoint accumulation: negative coefficients swap extrema.
            a,b=self.v.bounds(z['target'],p);u=v=z['constant']*p
            for i,w in z['terms']:
                l,h=self.v.bounds(i,p)
                if w>0:u+=w*l;v+=w*h
                else:u+=w*h;v+=w*l
            den=z['den'];lo=max(a,(u+den-1)//den);hi=min(b,v//den)
            if lo>hi or (nat(r['lower']),nat(r['upper']),r['status'])!=(lo,hi,'EXACT' if lo==hi else 'UNKNOWN'):return False
            if commit and lo==hi:self.v.book(z['target'])._put(p,lo)
            return True
        except (ValueError,TypeError,IndexError,KeyError,OverflowError):return False
    def verify_descriptor(self,z):
        """Only authorize descriptions of facts already present in this Ground."""
        from hashlib import sha256
        from json import dumps
        try:
            a=self.v.a
            digests=[sha256(b'false').hexdigest(),sha256(b'true').hexdigest()]
            for j,kids in a.d.nodes:
                digests.append(sha256(dumps([j,[digests[v] for v in kids]],separators=(',',':')).encode()).hexdigest())
            body=dict(schema='ifs.cig032.seed.v1',base=list(a.d.base),cutoff=a.D,members=[dict(index=i,root=a.roots[i],semantic=digests[a.roots[i]],prefix=str(a.prefix[i]),anchors=[[str(p),str(r)] for p,r in sorted(self.v.book(i).anchors.items())]) for i in self.members])
            expected=dict(body,identity=sha256(dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest())
            return type(z) is dict and dumps(z,sort_keys=True,separators=(',',':'))==dumps(expected,sort_keys=True,separators=(',',':'))
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):return False

def restore_capsule(a,packet,*,max_terms=100000,max_facts=4096,max_work=4000000):
    """Cold independent admission into a fresh local memory. No trust in
    the capsule digest or ranks. Publish only after all facts are checked.
    The caller supplies the independently admitted original temporal Ground.
    """
    from verify_compositional_rank import MemoryReceiver
    from verify_temporal_rank import CheckedRank
    from verify_temporal_algebra import Admission
    try:
        if type(a) is not Admission or any(type(n) is not int or n<1 for n in (max_terms,max_facts,max_work)):return None
        if type(packet) is not dict:return None
        recipe=packet.get('schema')=='ifs.cig032.recipe.v1'
        if recipe:
            if set(packet)!={'schema','descriptor'}:return None
        elif set(packet)!={'schema','descriptor','proofs'} or packet['schema']!='ifs.cig032.capsule.v1':return None
        z=packet['descriptor'];ps=packet.get('proofs')
        if type(z) is not dict or set(z)!={'schema','base','cutoff','members','identity'} or z['schema']!='ifs.cig032.seed.v1' or z['base']!=list(a.d.base) or type(z['cutoff']) is not int or z['cutoff']!=a.D:return None
        rows=z['members']
        if type(rows) is not list or not 1<=len(rows)<=12:return None
        if not recipe and (type(ps) is not list or len(ps)!=len(rows)):return None
        if any(type(r) is not dict or set(r)!={'index','root','semantic','prefix','anchors'} or type(r['index']) is not int or not 0<=r['index']<len(a.roots) or type(r['anchors']) is not list for r in rows):return None
        ids=[r['index'] for r in rows]
        if ids!=sorted(set(ids)) or sum(len(r['anchors']) for r in rows)>max_facts:return None
        if recipe:ps=[[i,None] for i in ids]
        elif any(type(p) is not list or len(p)!=2 or type(p[0]) is not int or type(p[1]) is not dict or type(p[1].get('terms')) is not list for p in ps) or [p[0] for p in ps]!=ids or sum(len(p[1]['terms']) for p in ps)>max_terms:return None
        # Verify all facts inside an isolated, fresh receiver-owned memory.
        v=MemoryReceiver(a);terms=0
        for row,(_,proof) in zip(rows,ps):
            i=row['index'];b=v.book(i)
            if recipe:b.exact=CheckedRank.from_ground(a,i,max_work=max_work)
            else:
                if proof.get('index')!=i:return None
                b.exact=CheckedRank(a,proof,max_work=max_work)
            terms+=len(b.exact.terms)
            if terms>max_terms:return None
            last=-1
            for item in row['anchors']:
                if type(item) is not list or len(item)!=2:return None
                p,r=map(nat,item)
                if p<=last or not v.admit_fact(i,p,dict(index=i,phase=item[0],rank=item[1])):return None
                last=p
            b.close_rank()
        s=SeedReceiver(v,ids)
        if not s.verify_descriptor(z):return None
        return v,s
    except (ValueError,TypeError,IndexError,KeyError,OverflowError,AttributeError):return None
