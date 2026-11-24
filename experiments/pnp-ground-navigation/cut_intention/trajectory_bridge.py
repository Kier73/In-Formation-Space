"""CIG-033A: discover equality/shift of two independently admitted trajectories.
No assertion of uniform state-space correspondence. Common prime-power CRT
coordinates are traversed symbolically; no global-period table is constructed.
"""
from temporal_algebra import Budget
from adaptive_seed import Work


def prime(q):
    return next((p for p in range(2,q+1) if q%p==0),q)


def equal_shift(old,oi,new,ni,delta,work):
    cutoff=max(new.D,max(0,old.D-delta))
    if (delta+cutoff).bit_length()>4096:return False
    for t in range(cutoff):
        work.charge()
        if old.membership(oi,t+delta)!=new.membership(ni,t):return False
    d,e=old.d,new.d;P={prime(b):b for b in d.base};Q={prime(b):b for b in e.base}
    lp=[prime(b) for b in d.base];rp=[prime(b) for b in e.base];sentinel=max([1]+lp+rp)+1
    stack=[(old.roots[oi],new.roots[ni])];seen=set()
    while stack:
        a,b=stack.pop()
        if (a,b) in seen:continue
        seen.add((a,b));work.charge()
        if a<2 and b<2:
            if a!=b:return False
            continue
        x=lp[d.level(a)] if a>=2 else sentinel;y=rp[e.level(b)] if b>=2 else sentinel;p=min(x,y);L=max(P.get(p,1),Q.get(p,1));work.charge(L)
        for r in range(L):
            aa=d.at(a,d.level(a),(r+delta)%P[p]) if x==p else a
            bb=e.at(b,e.level(b),r%Q[p]) if y==p else b
            stack.append((aa,bb))
    return True


def discover_trajectory(old,oi,new,ni,*,deltas=(0,1,2,3,4),max_work=500000):
    work=Work(max_work);ds=tuple(deltas)
    if len(ds)>64 or any(type(t)is not int or t<0 or t.bit_length()>4096 for t in ds):raise ValueError('shift palette')
    if type(oi)is not int or not 0<=oi<len(old.roots) or type(ni)is not int or not 0<=ni<len(new.roots):raise ValueError('output')
    try:
        for dt in ds:
            work.charge()
            if equal_shift(old,oi,new,ni,dt,work):return dict(status='FOUND',delta=dt,work=work.used)
    except (Budget,RecursionError):pass
    return dict(status='UNKNOWN',delta=None,work=work.used)
