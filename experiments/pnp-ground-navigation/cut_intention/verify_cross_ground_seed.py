"""Independent bridge qualification: no discovery/producer imports."""
from copy import deepcopy
from verify_temporal_ground import Receiver,digest
from verify_temporal_algebra import Checked,Admission
from verify_rank_anchors import CheckedAnchors
from verify_compositional_rank import MemoryReceiver


def verify_bridge(old,new,z,*,max_work=4_000_000):
    try:
        if type(max_work)is not int or max_work<1 or type(old)is not Receiver or type(new)is not Receiver or not old.total_image or not new.total_image:return False
        if type(z)is not dict or set(z)!={'schema','old','new','old_initial','new_initial','old_output','new_output','align','maps','nodes','old_refs','new_refs'} or z['schema']!='ifs.cig033.bridge.v1' or (z['old'],z['new'],z['old_initial'],z['new_initial'])!=(old.key,new.key,str(old.initial),str(new.initial)):return False
        a,h=z['align'],z['maps'];m=old.k//old.w;n=new.k//new.w
        if type(a)is not list or len(a)!=m or any(type(j)is not int or not 0<=j<n for j in a) or len(set(a))!=m or type(h)is not list or len(h)!=m:return False
        for i,row in enumerate(h):
            if type(row)is not list or len(row)!=new.a or any(type(x)is not int or not 0<=x<old.a for x in row) or set(row)!=set(range(old.a)):return False
            if row[(new.initial//new.a**a[i])%new.a]!=(old.initial//old.a**i)%old.a:return False
        # Uniform commuting square on the entire observation cube.
        for j,i in enumerate(old.g['pred']):
            nj=a[j]
            if new.g['pred'][nj]!=a[i]:return False
            for x in range(new.a):
                if h[j][new.g['tables'][nj][x]]!=old.g['tables'][j][h[i][x]]:return False
        d=Checked([new.a]*n,z['nodes'],max_work)
        def check(rec,idx,rows,project):
            if type(idx)is not int or not 0<=idx<len(rec.circuit['outputs']) or type(rows)is not list:return None
            if any(type(r)is not list or len(r)!=2 or type(r[0])is not int or type(r[1])is not int for r in rows):return None
            refs=dict(rows)
            if len(refs)!=len(rows) or refs.get(1)!=1 or refs.get(-1)!=0:return None
            k=rec.k;c=rec.circuit;root=c['outputs'][idx];live={abs(root)}
            for i in range(k+1+len(c['gates']),k+1,-1):
                if i in live:live.update(map(abs,c['gates'][i-k-2][1:]))
            if {i for i in refs if i>0}!=live|{1} or any(i==0 or abs(i) not in live|{1} for i in refs):return None
            for i,v in refs.items():d.root(v)
            for i in sorted(live):
                if i==1:continue
                r=refs[i]
                if i<=k+1:
                    j,b=divmod(i-2,rec.w)
                    vals=[(x//2**b)%2 for x in (h[j] if project else range(new.a))]
                    level=a[j] if project else j
                    if len(set(vals))==1:
                        if r!=vals[0]:return None
                    elif d.level(r)!=level or tuple(vals)!=d.nodes[r-2][1]:return None
                else:
                    op,x,y=c['gates'][i-k-2];d.relation(op,refs[x],refs[y],r)
            for i,v in refs.items():
                if i<-1:d.relation('not',refs[-i],0,v)
            return refs[root]
        x=check(old,z['old_output'],z['old_refs'],True);y=check(new,z['new_output'],z['new_refs'],False)
        return x is not None and y is not None and x==y
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError):return False


class BridgeAdmission:
    """Receiver-local transfer of existing rank evidence, bound to two anchors.
    Old Admission is re-derived from its receipt and compared with the live book.
    Does not trust a digest as evidence, or create a new target rank compiler.
    """
    def __init__(self,old,new,old_algebra,old_memory,proof,*,max_work=4_000_000):
        if not verify_bridge(old,new,proof,max_work=max_work):raise ValueError('bridge')
        if type(old_memory)is not MemoryReceiver:raise ValueError('memory')
        original=Admission(old,old_algebra,max_work=max_work);a=old_memory.a;i=proof['old_output']
        # Require the same admitted original output and its entire node prefix.
        if a.D!=original.D or a.d.base!=original.d.base or a.roots[i]!=original.roots[i] or a.prefix[i]!=original.prefix[i] or a.d.nodes[:len(original.d.nodes)]!=original.d.nodes:raise ValueError('old Ground binding')
        self.book=old_memory.book(i);self.proof=deepcopy(proof);self.key=digest(proof);self.new=new
    def accept(self,ordinal,z,*,budget=128):
        try:
            if type(z)is not dict or set(z)!={'bridge','output','ordinal','rank'} or z['bridge']!=self.key or type(z['output'])is not int or z['output']!=self.proof['new_output'] or z['ordinal']!=str(ordinal):return None
            # Compact receipt already reconstructs absolute time from admitted old anchors.
            return self.book.admit_compact(ordinal,z['rank'],budget=budget)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):return None
