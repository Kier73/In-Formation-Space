"""Independent availability proof and anchor-bound recovery for CIG-028."""
from hashlib import sha256
from math import prod
import json
from verify_temporal_image import _decimal,_time


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _schedule(windows,k):
    # Independent validation and canonical encoding, not the producer parser.
    if type(windows) is not tuple or len(windows)>4096:raise ValueError('schedule')
    encoded=[];end=0
    for row in windows:
        if type(row) is not tuple or len(row)!=4:raise ValueError('row')
        a,b,host,bits=row
        if (end is None or not _time(a) or a<end
            or (b is not None and (not _time(b) or b<=a))
            or type(host) is not str or not 1<=len(host)<=128
            or not host.isascii() or any(not(c.isalnum() or c in '._:-/') for c in host)
            or type(bits) is not int or not 0<=bits<=k):
            raise ValueError('schedule row')
        encoded.append([str(a),str(b) if b is not None else None,host,bits]);end=b
    return _hash(['ifs.cig028.schedule.v1',k,encoded])


class AvailabilityAdmission:
    """Local receiver-owned schedule; no claim of external host authorization."""
    def __init__(self,capacity,windows):
        self.capacity=capacity
        self.windows=windows
        self.schedule=_schedule(windows,capacity.image.receiver.k)
        self.host=None
        # Independent monotone threshold by finite height breakpoints.
        h=capacity.image.h
        cuts=sorted({0}|{v+1 for v in h if v>=0})
        # Cache exact thresholds for only the offered budgets; monotone scan
        # over the distinct breakpoints, never over the logical time horizon.
        self.thresholds={B:None for _,_,_,B in windows}
        pending=set(self.thresholds)
        for t in cuts:
            if not pending:break
            bits=capacity._bits(t)
            for B in tuple(pending):
                if bits<=B:self.thresholds[B]=t;pending.remove(B)

    def verify(self,i,start,ordinal,r):
        try:
            if (not _time(start) or type(ordinal) is not int or ordinal<1 or ordinal.bit_length()>4096
                or type(i) is not int or i not in self.capacity.ranks):return False
            if set(r)!={'schema','key','schedule','root','start','ordinal','status','time','window','host','evidence'}:return False
            if (r['schema']!='ifs.cig028.availability.v1' or r['key']!=self.capacity.image.key
                or r['schedule']!=self.schedule or type(r['root']) is not int or r['root']!=i
                or r['start']!=str(start) or r['ordinal']!=str(ordinal)
                or r['status'] not in ('FOUND','UNREACHABLE')):return False
            rank=self.capacity.ranks[i];remaining=ordinal
            for j,(a,b,host,B) in enumerate(self.windows):
                tau=self.thresholds[B]
                if tau is None:continue
                lo=max(a,start,tau)
                if b is not None and lo>=b:continue
                base=rank.rank(lo)
                count=(rank.rank(b)-base if b is not None else
                       (rank.before-base if rank.total==0 else None))
                if count is not None and remaining>count:
                    remaining-=count;continue
                if (r['status']!='FOUND' or type(r['window']) is not int or r['window']!=j
                    or r['host']!=host):return False
                t=_decimal(r['time'],4096)
                if t<lo or (b is not None and t>=b) or self.capacity._bits(t)>B:return False
                return (r['evidence']['time']==r['time'] and r['evidence']['status']=='FOUND'
                        and rank.verify_select(base+remaining,r['evidence']))
            return (r['status']=='UNREACHABLE' and all(r[x] is None for x in ('time','window','host','evidence')))
        except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError):return False

    def accept_move(self,i,start,ordinal,r,move):
        if not self.verify(i,start,ordinal,r) or r['status']!='FOUND':return False
        if not self.capacity.image.accept(int(r['time']),move):return False
        self.host=r['host'];return True

    def snapshot(self):
        """Export last accepted position; identity deliberately excludes host."""
        image=self.capacity.image
        if self.host is None:raise ValueError('no accepted hosted coordinate')
        state=dict(schema='ifs.cig028.checkpoint.v1',key=image.key,
                   schedule=self.schedule,time=str(image.time),rank=str(image.rank),host=self.host)
        return dict(state=state,sha256=_hash(state))

    def restore(self,packet,expected_digest):
        """Requalify coordinate on a fresh receiver using original source anchor.

        Caller must retain trusted latest digest; a digest alone is not authority.
        No old host object or old producer state is needed.
        """
        try:
            image=self.capacity.image
            if self.host is not None or image.time!=0:return False
            if (set(packet)!={'state','sha256'} or packet['sha256']!=expected_digest
                or packet['sha256']!=_hash(packet['state'])):return False
            s=packet['state']
            if (set(s)!={'schema','key','schedule','time','rank','host'}
                or s['schema']!='ifs.cig028.checkpoint.v1' or s['key']!=image.key
                or s['schedule']!=self.schedule):return False
            t=_decimal(s['time'],4096);r=_decimal(s['rank'],image.receiver.k)
            if t<=0:return False
            code,bits=image._decode(t,r)
            if not any(a<=t and (b is None or t<b) and host==s['host'] and bits<=B
                       for a,b,host,B in self.windows):return False
            # Independent native receiver reconstructs code and decoder outputs
            # from the retained original anchor. Recompute outputs locally to
            # submit the ordinary CIG-021 receipt; do not trust stored outputs.
            receiver=image.receiver
            vals={1:1,**{i+2:(code//2**i)%2 for i in range(receiver.k)}}
            def read(x):return vals[abs(x)] if x>0 else 1-vals[abs(x)]
            for j,(op,a,b) in enumerate(receiver.circuit['gates'],receiver.k+2):
                vals[j]=min(read(a),read(b)) if op=='and' else max(read(a),read(b))
            outputs=[read(x) for x in receiver.circuit['outputs']]
            move=dict(schema='ifs.cig026.move.v1',key=image.key,previous_time='0',
                      previous_rank=str(image.rank),time=str(t),rank=str(r),bits=bits,outputs=outputs)
            if not image.accept(t,move):return False
            self.host=s['host'];return True
        except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError):return False
