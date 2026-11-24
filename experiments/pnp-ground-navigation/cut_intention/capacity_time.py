"""CIG-027: temporal intention under exact retained-coordinate capacity."""
from temporal_ground import contract_time
from temporal_image import capacity
from temporal_rank import Rank
from temporal_algebra import Budget


def budget(bits,k):
    """Capacity is a nonnegative integer number of logical retained bits."""
    if type(bits) is not int or not 0<=bits<=k:
        raise ValueError('capacity budget')


def threshold(processor,bits):
    """First time at which the full endpoint image fits, or None forever."""
    budget(bits,processor.nav.k)
    lo=0;hi=max(processor.h,default=-1)+1
    def fits(t):
        return capacity(processor.alphabets(t))[1]<=bits
    if not fits(hi):
        return None
    while lo<hi:
        mid=(lo+hi)//2
        if fits(mid):hi=mid
        else:lo=mid+1
    return lo


class CapacityNavigator:
    """Producer reuses admitted temporal image and time-set language."""
    def __init__(self,processor,language):
        self.processor=processor
        self.language=language
        self.ranks={}

    def prepare_rank(self,i,max_work=2_000_000):
        """Retain CIG-025 rank compiler output; checker admits it separately."""
        r=Rank(self.language,i,max_work)
        self.ranks[i]=r
        return r.packet()

    def query(self,i,start,bits,*,ordinal=1,route='next',max_states=100_000):
        contract_time(start);budget(bits,self.processor.nav.k)
        if type(i) is not int or not 0<=i<len(self.language.roots):
            raise ValueError('root')
        if type(ordinal) is not int or ordinal<1 or ordinal.bit_length()>4096:
            raise ValueError('ordinal')
        if route not in ('next','rank') or (route=='next' and ordinal!=1):
            raise ValueError('route')
        tau=threshold(self.processor,bits)
        r=dict(schema='ifs.cig027.capacity.v1',key=self.processor.key,
               root=i,start=str(start),bits=bits,ordinal=str(ordinal),route=route,
               threshold=None if tau is None else str(tau),status='UNREACHABLE',
               time=None,evidence=None)
        if tau is None:return r
        lower=max(start,tau)
        if route=='next':
            ev=self.language.next(i,lower,max_states=max_states)
        else:
            if i not in self.ranks:raise ValueError('rank not prepared')
            rank=self.ranks[i]
            target=rank.rank(lower)+ordinal
            if target.bit_length()>4096:
                r['status']='UNKNOWN';return r
            ev=rank.select(target)
        r.update(status=ev['status'],time=ev['time'],evidence=ev)
        return r
