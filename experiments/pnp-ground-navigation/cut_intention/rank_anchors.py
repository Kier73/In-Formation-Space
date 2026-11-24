"""CIG-029A: retained phase-rank anchors on an admitted periodic language.
Producer book is local; use CheckedAnchors to admit each proposed mutation.
"""
from math import prod
from temporal_rank import Rank
from partial_rank import PartialRank
from temporal_ground import contract_time

MAX_SCAN = 100_000

class Anchors:
    def __init__(self, lang, index):
        if type(index) is not int or not 0 <= index < len(lang.roots):
            raise ValueError('output index')
        self.lang=lang; self.i=index; self.D=lang.D; self.P=prod(lang.d.base)
        self.N=lang.count(index); self.prefix=lang.prefix[index]; self.before=self.prefix.bit_count()
        self._anchors={0:0,self.P:self.N}
    @property
    def anchors(self): return dict(self._anchors)
    def seed(self, phase, *, exact=None, partial=None, budget=20000):
        """Construct a seed from an exact rank or exact partial proof; no mutation."""
        if type(phase) is not int or not 0<=phase<=self.P or (exact is None)==(partial is None):
            raise ValueError('seed contract')
        t=self.D+phase
        if exact is not None:
            if not isinstance(exact,Rank) or exact.i!=self.i:raise ValueError('rank')
            proof=exact.packet(); r=exact.rank(t)-self.before; method='full'
        else:
            if not isinstance(partial,PartialRank) or partial.i!=self.i:raise ValueError('partial rank')
            proof=partial.compare(t,budget=budget)
            if proof['status']!='EXACT':return None
            r=int(proof['lower'])-self.before;method='partial'
        return dict(index=self.i,phase=str(phase),rank=str(r),method=method,proof=proof)
    def commit_seed(self, packet):
        """Call only after independent receiver accepts the seed."""
        self._anchors[int(packet['phase'])]=int(packet['rank'])
    def compare(self,t,k):
        """Exact decision from the tight monotone bounds of two retained anchors."""
        contract_time(t);contract_time(k)
        if t<=self.D:
            L=U=(self.prefix&((1<<t)-1)).bit_count();a=b=None
        else:
            q,p=divmod(t-self.D,self.P);offset=self.before+q*self.N
            a=max(x for x in self._anchors if x<=p);b=min(x for x in self._anchors if x>=p)
            l,r=self._anchors[a],self._anchors[b]
            L=offset+max(l,r-(b-p));U=offset+min(r,l+(p-a))
        status='EXACT' if L==U else 'BELOW' if U<k else 'AT_LEAST' if L>=k else 'UNKNOWN'
        return dict(index=self.i,time=str(t),threshold=str(k),left=None if a is None else str(a),right=None if b is None else str(b),lower=str(L),upper=str(U),status=status)
    def span(self, phase, *, budget=4096):
        """Walk toward a target phase, preserving exact progress if unfinished."""
        if type(phase) is not int or not 0<=phase<=self.P:raise ValueError('phase')
        if type(budget) is not int or not 0<=budget<=MAX_SCAN:raise ValueError('budget')
        a=min(self._anchors,key=lambda x:(abs(phase-x),x));r=self._anchors[a]
        b=min(a+budget,phase) if phase>=a else max(a-budget,phase)
        n=sum(self.lang.membership(self.i,self.D+t) for t in range(min(a,b),max(a,b)))
        z=r+n if b>=a else r-n
        return dict(index=self.i,anchor=str(a),end=str(b),rank=str(z),steps=abs(b-a),target=str(phase),status='EXACT' if b==phase else 'UNKNOWN')
    def select(self,k,*,budget=4096):
        contract_time(k)
        if k<1 or type(budget) is not int or not 0<=budget<=MAX_SCAN:raise ValueError('ordinal/budget')
        out=dict(index=self.i,ordinal=str(k),anchor=None,end=None,rank=None,steps=0,status='UNKNOWN',time=None)
        if k<=self.before:
            z=self.prefix
            for _ in range(k-1):z &= z-1
            return dict(out,status='FOUND',time=str((z&-z).bit_length()-1))
        if not self.N:return dict(out,status='UNREACHABLE')
        q,j=divmod(k-self.before-1,self.N);j+=1
        # Conservative admission of the entire selected period.
        if (self.D+(q+1)*self.P).bit_length()>4096:return out
        # Rank distance is a heuristic only. Tie-break toward expected phase.
        lo=max(a for a,r in self._anchors.items() if r<j)
        hi=min(a for a,r in self._anchors.items() if r>=j)
        a=min((lo,hi),key=lambda a:(j-self._anchors[a] if self._anchors[a]<j else self._anchors[a]-j+1,abs(a*self.N-j*self.P),a))
        r=self._anchors[a]
        b=a;target=None
        if r<j:
            while b<self.P and b-a<budget:
                r+=self.lang.membership(self.i,self.D+b);b+=1
                if r==j:target=b-1;break
        else:
            while b>0 and a-b<budget:
                b-=1;r-=self.lang.membership(self.i,self.D+b)
                if r==j-1:target=b;break
        return dict(out,anchor=str(a),end=str(b),rank=str(r),steps=abs(b-a),status='UNKNOWN' if target is None else 'FOUND',time=None if target is None else str(self.D+q*self.P+target))
    def compact(self,k,*,budget=4096):
        """Return only phase evidence; the caller already supplies ordinal k."""
        r=self.select(k,budget=budget)
        return {key:value for key,value in r.items() if key not in ('ordinal','time')}
    def commit(self, receipt):
        """Call only after receiver accepts the exact local interval."""
        if receipt['end'] is not None:self._anchors[int(receipt['end'])]=int(receipt['rank'])
