"""Independent trajectory-only bridge across unrelated CRT coordinate bases."""
from verify_temporal_algebra import Admission
from verify_compositional_rank import MemoryReceiver
from verify_temporal_ground import digest


def verify_shift(a,i,b,j,delta,*,max_work=500000):
    try:
        if type(a)is not Admission or type(b)is not Admission or type(i)is not int or type(j)is not int or not 0<=i<len(a.roots) or not 0<=j<len(b.roots) or type(delta)is not int or delta<0 or delta.bit_length()>4096 or type(max_work)is not int or max_work<1:return False
        def value(s,n,t):return (s.prefix[n]>>t)&1 if t<s.D else s.d.value(s.roots[n],t)
        cutoff=max(b.D,a.D-delta,0);work=cutoff
        if work>max_work or (delta+cutoff).bit_length()>4096:return False
        if any(value(a,i,t+delta)!=value(b,j,t) for t in range(cutoff)):return False
        def factor(q):
            p=2
            while q%p:p+=1
            return p
        aa=[factor(q) for q in a.d.base];bb=[factor(q) for q in b.d.base];pos1={p:k for k,p in enumerate(aa)};pos2={p:k for k,p in enumerate(bb)}
        memo=set()
        def check(x,y):
            nonlocal work
            if (x,y) in memo:return True
            work+=1
            if work>max_work:raise ValueError('budget')
            if x<2 and y<2:return x==y
            p1=aa[a.d.level(x)] if x>=2 else float('inf');p2=bb[b.d.level(y)] if y>=2 else float('inf');p=min(p1,p2)
            u=a.d.base[pos1[p]] if p in pos1 else 1;v=b.d.base[pos2[p]] if p in pos2 else 1
            for r in range(max(u,v)):
                work+=1
                if work>max_work:raise ValueError('budget')
                xx=a.d.arc(x,pos1[p],(r+delta)%u) if p1==p else x;yy=b.d.arc(y,pos2[p],r%v) if p2==p else y
                if not check(xx,yy):return False
            memo.add((x,y));return True
        return check(a.roots[i],b.roots[j])
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError):return False


class TrajectoryAdmission:
    def __init__(self,old,new,old_receipt,new_receipt,memory,i,j,delta,*,max_work=500000):
        if type(memory)is not MemoryReceiver:raise ValueError('memory')
        a,b=Admission(old,old_receipt),Admission(new,new_receipt);live=memory.a
        if not verify_shift(a,i,b,j,delta,max_work=max_work):raise ValueError('trajectory relationship')
        if live.D!=a.D or live.d.base!=a.d.base or live.roots[i]!=a.roots[i] or live.prefix[i]!=a.prefix[i] or live.d.nodes[:len(a.d.nodes)]!=a.d.nodes:raise ValueError('old Ground binding')
        self.book=memory.book(i);self.delta=delta;self.target=j;self.key=digest([old.key,str(old.initial),new.key,str(new.initial),i,j,str(delta)])
        if delta<=self.book.D:self.offset=(self.book.prefix&((1<<delta)-1)).bit_count()
        else:
            q,p=divmod(delta-self.book.D,self.book.P)
            if p not in self.book.anchors:raise ValueError('shift offset rank not admitted')
            self.offset=self.book.before+q*self.book.N+self.book.anchors[p]
    def accept(self,k,z,*,budget=128):
        try:
            if type(k)is not int or k<1 or k.bit_length()>4096 or type(z)is not dict or set(z)!={'bridge','output','ordinal','rank'} or z['bridge']!=self.key or type(z['output'])is not int or z['output']!=self.target or z['ordinal']!=str(k):return None
            result=self.book.admit_compact(k+self.offset,z['rank'],budget=budget)
            if result is None:return None
            if result['status']=='FOUND':
                t=int(result['time'])-self.delta
                if t<0:return None
                return dict(status='FOUND',time=str(t))
            return result
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):return None
