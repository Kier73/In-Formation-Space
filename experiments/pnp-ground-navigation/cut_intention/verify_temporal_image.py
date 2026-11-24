"""CIG-026 receiver: independent exact-image proof and atomic local admission."""
from copy import deepcopy
from math import prod
from verify_temporal_ground import digest,Receiver


def _time(t):
    return type(t)is int and 0<=t and t.bit_length()<=4096


def _decimal(s,limit):
    if type(s)is not str or not s or len(s)>limit*30103//100000+3 or not s.isascii() or not s.isdecimal():
        raise ValueError('noncanonical integer')
    x=int(s)
    if str(x)!=s or x.bit_length()>limit:
        raise ValueError('integer outside contract')
    return x


def verify_image(receiver,proof):
    """Check longest predecessor path recurrence using admitted CIG-021 edges.

    Noncycle predecessor subgraph is acyclic by the transport proof. The
    recurrence therefore uniquely determines every finite height.
    """
    try:
        if not isinstance(receiver,Receiver) or not receiver.total_image:
            return False
        if set(proof)!={'schema','key','heights'} or proof['schema']!='ifs.cig026.image.v1' or proof['key']!=receiver.key:
            return False
        n=len(receiver.edges);h=proof['heights']
        if type(h)is not list or len(h)!=n or any(type(x)is not int or not -1<=x<n for x in h):
            return False
        incoming=[[] for _ in range(n)]
        for v,u in enumerate(receiver.edges):
            incoming[u].append(v)
        for v in range(n):
            if receiver.g['depth'][v]==0:
                if h[v]!=-1:
                    return False
            else:
                if any(h[u]<0 for u in incoming[v]):
                    return False
                if h[v]!=max((h[u]+1 for u in incoming[v]),default=0):
                    return False
        return True
    except (TypeError,ValueError,KeyError,IndexError,AttributeError):
        return False


class Admission:
    """Trusted local receiver state; rejected migrations leave state unchanged."""
    def __init__(self,receiver,proof):
        if not verify_image(receiver,proof):
            raise ValueError('unqualified full-source image or height proof')
        self.receiver=deepcopy(receiver)
        self.h=tuple(proof['heights'])
        self.key=digest([proof,str(receiver.initial)])
        self.time=0
        self.rank=receiver.initial

    def _alphabets(self,t):
        a=self.receiver.a
        groups=[[] for _ in range(self.receiver.k//self.receiver.w)]
        for v,h in enumerate(self.h):
            if h<0 or t<=h:
                j,x=divmod(v,a)
                groups[j].append(x)
        return groups

    def _decode(self,t,rank):
        groups=self._alphabets(t)
        count=prod(len(g) for g in groups)
        if not 0<=rank<count:
            raise ValueError('rank outside exact image')
        # Independent positional quotient, not the producer's successive divmod.
        stride=1;code=0
        for j,g in enumerate(groups):
            code+=g[(rank//stride)%len(g)]*2**(j*self.receiver.w)
            stride*=len(g)
        return code,(count-1).bit_length()

    def accept(self,t,receipt):
        """Verify compact migration against the original admitted anchor."""
        try:
            if not _time(t) or t<=self.time:
                return False
            if set(receipt)!={'schema','key','previous_time','previous_rank','time','rank','bits','outputs'} or receipt['schema']!='ifs.cig026.move.v1':
                return False
            if (receipt['key']!=self.key or receipt['previous_time']!=str(self.time)
                    or receipt['previous_rank']!=str(self.rank) or receipt['time']!=str(t)):
                return False
            rank=_decimal(receipt['rank'],self.receiver.k)
            code,bits=self._decode(t,rank)
            if type(receipt['bits'])is not int or receipt['bits']!=bits:
                return False
            # Native CIG-021 independent receiver checks full endpoint semantics
            # from the original anchor, including the independently proved decoder.
            packet=dict(schema='ifs.cig021.jump.v1',key=self.receiver.key,
                        initial=str(self.receiver.initial),time=str(t),
                        code=str(code),outputs=receipt['outputs'],witness=None)
            if not self.receiver.accept(t,packet):
                return False
            self.time,self.rank=t,rank
            return True
        except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError):
            return False
