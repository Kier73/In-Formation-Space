"""Independent local admission of phase-rank anchors and ordinal receipts."""
from math import prod
from verify_temporal_algebra import Admission
from verify_temporal_rank import CheckedRank
from verify_partial_rank import CheckedPartial


def nat(s):
    if type(s) is not str or len(s)>1234 or not s.isascii() or not s.isdecimal():raise ValueError('integer')
    n=int(s)
    if str(n)!=s or n.bit_length()>4096:raise ValueError('integer')
    return n

class CheckedAnchors:
    def __init__(self,a,i):
        if type(a) is not Admission or type(i) is not int or not 0<=i<len(a.roots):raise ValueError('source admission')
        self.a=a;self.i=i;self.d=a.d;self.root=a.roots[i];self.D=a.D;self.prefix=a.prefix[i]
        self.P=prod(self.d.base);self.N=a.count(i);self.before=self.prefix.bit_count();self._anchors={0:0,self.P:self.N}
        self.partial=CheckedPartial(a)
    @property
    def anchors(self):return dict(self._anchors)
    def _bit(self,t):
        return self.d.value(self.root,self.D+t)
    def _put(self,p,r):
        if not 0<=p<=self.P or not 0<=r<=self.N or (p in self._anchors and self._anchors[p]!=r):raise ValueError('anchor')
        self._anchors[p]=r
    def admit_seed(self,z,*,budget=20000):
        try:
            if type(z) is not dict or set(z)!={'index','phase','rank','method','proof'} or type(z['index']) is not int or z['index']!=self.i:return False
            p,r=nat(z['phase']),nat(z['rank']);t=self.D+p;proof=z['proof']
            if p>self.P or r>self.N:return False
            if z['method']=='full':
                if proof['index']!=self.i:return False
                expected=CheckedRank(self.a,proof).rank(t)-self.before
            elif z['method']=='partial':
                if proof['index']!=self.i or proof['time']!=str(t) or proof['status']!='EXACT' or not self.partial.verify(proof,budget=budget):return False
                expected=nat(proof['lower'])-self.before
            else:return False
            if r!=expected:return False
            self._put(p,r);return True
        except (TypeError,ValueError,KeyError,IndexError,OverflowError):return False
    def _local(self,z,budget):
        if type(budget) is not int or not 0<=budget<=100000 or type(z['steps']) is not int:raise ValueError('budget')
        a,b,r=map(nat,(z['anchor'],z['end'],z['rank']))
        if a not in self._anchors or b>self.P or abs(b-a)!=z['steps'] or z['steps']>budget:raise ValueError('span')
        # Independently count interval on receiver's admitted diagram.
        n=0
        for t in range(min(a,b),max(a,b)):n+=self._bit(t)
        if r!=self._anchors[a]+(n if b>=a else -n):raise ValueError('rank')
        return a,b,r
    def verify_compare(self,t,k,z):
        try:
            if type(t) is not int or type(k) is not int or min(t,k)<0 or max(t,k).bit_length()>4096 or type(z) is not dict or set(z)!={'index','time','threshold','left','right','lower','upper','status'} or type(z['index']) is not int or z['index']!=self.i or nat(z['time'])!=t or nat(z['threshold'])!=k:return False
            if t<=self.D:
                if z['left'] is not None or z['right'] is not None:return False
                L=U=sum(self.prefix>>j&1 for j in range(t))
            else:
                q,p=divmod(t-self.D,self.P);a,b=nat(z['left']),nat(z['right'])
                if not a<=p<=b or a not in self._anchors or b not in self._anchors:return False
                # Producer may use any admitted bracketing anchors; monotone
                # Lipschitz rank gives these two independent inequalities.
                offset=self.before+q*self.N;l=self._anchors[a];r=self._anchors[b]
                L=offset+max(l,r+p-b);U=offset+min(r,l+p-a)
            return (nat(z['lower']),nat(z['upper']),z['status'])==(L,U,'EXACT' if L==U else 'BELOW' if U<k else 'AT_LEAST' if L>=k else 'UNKNOWN')
        except (TypeError,ValueError,KeyError,IndexError,OverflowError):return False
    def admit_span(self,target,z,*,budget=4096):
        try:
            if type(z) is not dict or set(z)!={'index','anchor','end','rank','steps','target','status'} or type(z['index']) is not int or z['index']!=self.i:return False
            a,b,r=self._local(z,budget);p=nat(z['target'])
            if type(target) is not int or target!=p or p>self.P or not min(a,p)<=b<=max(a,p) or z['status']!=('EXACT' if b==p else 'UNKNOWN'):return False
            self._put(b,r);return True
        except (TypeError,ValueError,KeyError,IndexError,OverflowError):return False
    def admit_compact(self,k,z,*,budget=4096):
        """Return qualified result (or None on refusal); no absolute time on wire."""
        try:
            if type(k) is not int or k<1 or k.bit_length()>4096 or type(z) is not dict or set(z)!={'index','anchor','end','rank','steps','status'}:return None
            t=None
            if z['status']=='FOUND':
                if k<=self.before:
                    t=[j for j in range(self.D) if self.prefix>>j&1][k-1]
                else:
                    q,j=divmod(k-self.before-1,self.N);j+=1
                    a,b=nat(z['anchor']),nat(z['end'])
                    phase=b-1 if self._anchors[a]<j else b
                    t=self.D+q*self.P+phase
            r=dict(z,ordinal=str(k),time=None if t is None else str(t))
            if not self.admit_select(k,r,budget=budget):return None
            return dict(status=r['status'],time=r['time'])
        except (TypeError,ValueError,KeyError,IndexError,OverflowError,ZeroDivisionError):return None
    def admit_select(self,k,z,*,budget=4096):
        try:
            if type(k) is not int or k<1 or k.bit_length()>4096 or type(z) is not dict or set(z)!={'index','ordinal','anchor','end','rank','steps','status','time'} or type(z['index']) is not int or z['index']!=self.i or nat(z['ordinal'])!=k or type(z['steps']) is not int or type(budget) is not int or not 0<=budget<=100000:return False
            if k<=self.before or not self.N or (self.D+((k-self.before-1)//self.N+1)*self.P).bit_length()>4096:
                if any(z[x] is not None for x in ('anchor','end','rank')) or z['steps']!=0:return False
                if k<=self.before:
                    hits=[t for t in range(self.D) if self.prefix>>t&1];return z['status']=='FOUND' and z['time']==str(hits[k-1])
                return z['time'] is None and z['status']==('UNREACHABLE' if not self.N else 'UNKNOWN')
            q,j=divmod(k-self.before-1,self.N);j+=1
            a,b,r=self._local(z,budget);old=self._anchors[a]
            if old<j:
                if b<a:return False
                found=r==j and b>a and self._bit(b-1)==1;phase=b-1
                unresolved=r<j
            else:
                if b>a:return False
                found=r==j-1 and b<a and self._bit(b)==1;phase=b
                unresolved=r>=j
            if found:
                if z['status']!='FOUND' or nat(z['time'])!=self.D+q*self.P+phase:return False
            elif not (unresolved and z['status']=='UNKNOWN' and z['time'] is None):return False
            self._put(b,r);return True
        except (TypeError,ValueError,KeyError,IndexError,OverflowError,ZeroDivisionError):return False
