"""Receiver-owned bounded anchors and reusable full-rank admission.
Policy choices are untrusted; only exact verified facts enter the book.
"""
from verify_rank_anchors import CheckedAnchors, nat
from verify_temporal_rank import CheckedRank

class PortfolioReceiver(CheckedAnchors):
    def __init__(self,a,i):
        super().__init__(a,i);self.exact=None
    def open_rank(self,packet):
        try:
            if packet['index']!=self.i:return False
            checked=CheckedRank(self.a,packet)
            self.exact=checked;return True
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):return False
    def close_rank(self):self.exact=None
    def _from_select(self,k,z):
        if z['status']!='FOUND':return True
        t=int(z['time'])
        if t<self.D:return True
        q,p=divmod(t-self.D,self.P);j=k-self.before-q*self.N
        # Both exact adjacent ranks follow from the verified ordinal.
        additions={p:j-1,p+1:j}
        if not 1<=j<=self.N or any(x in self._anchors and self._anchors[x]!=r for x,r in additions.items()):return False
        self._anchors.update(additions);return True
    def admit_exact(self,k,z):
        return self.exact is not None and self.exact.verify_select(k,z) and self._from_select(k,z)
    def admit_partial(self,k,z,*,budget):
        return self.partial.verify_select(self.i,k,z,budget=budget) and self._from_select(k,z)
    def retain(self,phases,capacity):
        if type(capacity)is not int or capacity<0 or type(phases)is not list or any(type(p)is not int for p in phases):return False
        keys=set(phases)
        if len(keys)!=len(phases) or not {0,self.P}<=keys<=self._anchors.keys() or len(keys)-2>capacity:return False
        self._anchors={p:self._anchors[p] for p in phases};return True

    def admit_hit(self,k,z):
        try:
            if type(k)is not int or not 1<=k or k.bit_length()>4096 or k<=self.before or not self.N or type(z)is not dict or set(z)!={'index','phase'} or type(z['index'])is not int or z['index']!=self.i:return None
            q,j=divmod(k-self.before-1,self.N);p=nat(z['phase'])
            if self._anchors.get(p)!=j or self._anchors.get(p+1)!=j+1:return None
            t=self.D+q*self.P+p
            if (t+1).bit_length()>4096:return None
            return {'status':'FOUND','time':str(t)}
        except (TypeError,ValueError,KeyError,OverflowError):return None
