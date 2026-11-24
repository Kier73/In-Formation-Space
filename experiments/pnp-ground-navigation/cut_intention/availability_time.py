"""CIG-028: exact intention navigation through changing host availability."""
from temporal_ground import contract_time
from composed_ground import digest
from capacity_time import threshold


def schedule_key(windows,k):
    """Validate disjoint, ordered half-open windows. Gaps have no host."""
    if type(windows) is not tuple or len(windows)>4096:
        raise ValueError('schedule')
    rows=[];previous=0
    for row in windows:
        if type(row) is not tuple or len(row)!=4 or previous is None:
            raise ValueError('window')
        lo,hi,host,bits=row
        contract_time(lo)
        if hi is not None:contract_time(hi)
        if (lo<previous or (hi is not None and hi<=lo)
            or type(host) is not str or not 1<=len(host)<=128
            or not host.isascii() or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-/' for c in host)
            or type(bits) is not int or not 0<=bits<=k):
            raise ValueError('window contract')
        rows.append([str(lo),None if hi is None else str(hi),host,bits])
        previous=hi
    return digest(['ifs.cig028.schedule.v1',k,rows])


class AvailabilityNavigator:
    """Use existing capacity thresholds and prepared CIG-025 rank language."""
    def __init__(self,planner,windows,*,revision=0):
        if type(revision) is not int or not 0<=revision<1<<63:raise ValueError('revision')
        self.revision=revision
        self.planner=planner
        self.windows=windows
        self.schedule=schedule_key(windows,planner.processor.nav.k)
        self.thresholds={B:threshold(planner.processor,B) for B in {r[3] for r in windows}}

    def revise(self,windows,effective,expected_revision):
        """Replace future offers without changing the computational identity."""
        contract_time(effective)
        if type(expected_revision) is not int or expected_revision!=self.revision or effective<=self.planner.processor.time:
            raise ValueError('stale or retroactive schedule')
        candidate=AvailabilityNavigator(self.planner,windows,revision=self.revision+1)
        def prefix(rows):
            return tuple((a,min(b,effective) if b is not None else effective,h,B)
                         for a,b,h,B in rows if a<effective)
        if prefix(self.windows)!=prefix(windows):raise ValueError('changed historical windows')
        self.windows,self.schedule,self.thresholds,self.revision=(
            candidate.windows,candidate.schedule,candidate.thresholds,candidate.revision)

    def query(self,i,start,ordinal=1):
        contract_time(start)
        if type(ordinal) is not int or ordinal<1 or ordinal.bit_length()>4096:
            raise ValueError('ordinal')
        if type(i) is not int or i not in self.planner.ranks:
            raise ValueError('unprepared rank')
        rank=self.planner.ranks[i]
        r=dict(schema='ifs.cig028.availability.v1',key=self.planner.processor.key,
               schedule=self.schedule,revision=self.revision,root=i,start=str(start),ordinal=str(ordinal),
               status='UNREACHABLE',time=None,window=None,host=None,evidence=None)
        left=ordinal
        for j,(lo,hi,host,B) in enumerate(self.windows):
            tau=self.thresholds[B]
            if tau is None:continue
            lower=max(lo,start,tau)
            if hi is not None and lower>=hi:continue
            before=rank.rank(lower)
            if hi is not None:count=rank.rank(hi)-before
            elif not rank.total:count=rank.before-before
            else:count=None
            if count is not None and left>count:
                left-=count;continue
            target=before+left
            if target.bit_length()>4096:
                r['status']='UNKNOWN';return r
            ev=rank.select(target)
            if ev['status']=='UNKNOWN':
                r['status']='UNKNOWN';return r
            if ev['status']!='FOUND':
                raise AssertionError('rank inconsistency')
            t=int(ev['time'])
            if t<lower or (hi is not None and t>=hi):
                raise AssertionError('selection outside feasible window')
            r.update(status='FOUND',time=str(t),window=j,host=host,evidence=ev)
            return r
        return r
