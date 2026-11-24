"""Independent CIG-027 capacity and time-set admission."""
from math import prod
from copy import deepcopy
from verify_temporal_image import Admission as ImageAdmission
from verify_temporal_algebra import Admission as AlgebraAdmission
from verify_temporal_rank import CheckedRank


class CapacityAdmission:
    """Both image and temporal set proofs are bound to the same native receiver."""
    def __init__(self,receiver,image_proof,algebra_receipt):
        self.image=ImageAdmission(receiver,image_proof)
        self.algebra=AlgebraAdmission(receiver,algebra_receipt)
        self.ranks={}

    def extend(self,packet):
        self.algebra.extend(packet)

    def prepare_rank(self,packet,max_work=4_000_000):
        checked=CheckedRank(self.algebra,packet,max_work)
        self.ranks[packet['index']]=checked

    def _bits(self,t):
        """Independent alphabet product directly from admitted graph heights."""
        a=self.image.receiver.a;h=self.image.h
        count=prod(sum(v==-1 or v>=t for v in h[j:j+a])
                   for j in range(0,len(h),a))
        return (count-1).bit_length()

    def verify(self,i,start,bits,r,*,ordinal=1,route='next',max_states=100_000):
        """Check capacity boundary and exact ordinal/earliest time separately."""
        try:
            if (type(start) is not int or start<0 or start.bit_length()>4096
                or type(bits) is not int or not 0<=bits<=self.image.receiver.k
                or type(i) is not int or not 0<=i<len(self.algebra.roots)
                or type(ordinal) is not int or ordinal<1 or ordinal.bit_length()>4096
                or route not in ('next','rank') or (route=='next' and ordinal!=1)):
                return False
            if set(r)!={'schema','key','root','start','bits','ordinal','route','threshold','status','time','evidence'}:
                return False
            if (r['schema']!='ifs.cig027.capacity.v1' or r['key']!=self.image.key
                or type(r['root']) is not int or r['root']!=i
                or r['start']!=str(start) or type(r['bits']) is not int or r['bits']!=bits
                or r['ordinal']!=str(ordinal) or r['route']!=route):
                return False
            end=max(self.image.h,default=-1)+1
            if r['threshold'] is None:
                return (self._bits(end)>bits and r['status']=='UNREACHABLE'
                        and r['time'] is None and r['evidence'] is None)
            s=r['threshold']
            if type(s) is not str or len(s)>len(str(end)) or not s.isascii() or not s.isdecimal():
                return False
            tau=int(s)
            if (str(tau)!=s or not 0<=tau<=end or self._bits(tau)>bits
                or (tau>0 and self._bits(tau-1)<=bits)):
                return False
            lower=max(start,tau)
            ev=r['evidence']
            if not isinstance(ev,dict) or r['status'] not in ('FOUND','UNREACHABLE'):
                return False
            if r['status']!=ev.get('status') or r['time']!=ev.get('time'):
                return False
            if route=='next':
                return self.algebra.verify_next(i,lower,ev,max_states=max_states)
            rank=self.ranks[i]
            target=rank.rank(lower)+ordinal
            return rank.verify_select(target,ev)
        except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError):
            return False

    def accept_move(self,i,start,bits,r,migration,*,ordinal=1,route='next',max_states=100_000):
        """Verify intended destination then atomically advance the local image."""
        if not self.verify(i,start,bits,r,ordinal=ordinal,route=route,max_states=max_states) or r['status']!='FOUND':
            return False
        return self.image.accept(int(r['time']),migration)
