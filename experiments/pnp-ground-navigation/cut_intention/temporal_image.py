"""CIG-025: exact temporal images of CIG-021 admitted block transport."""
from collections import deque
from math import prod
from temporal_ground import contract_time, contract_code
from composed_ground import digest
from shared_proof import evaluate


def heights(nav):
    """Longest incoming transient paths; -1 denotes admitted cycle vertices."""
    n=len(nav.edges)
    indegree=[0]*n
    for u in nav.edges:
        indegree[u]+=1
    queue=deque(v for v in range(n) if indegree[v]==0)
    h=[0]*n
    while queue:
        v=queue.popleft()
        u=nav.edges[v]
        h[u]=max(h[u],h[v]+1)
        indegree[u]-=1
        if indegree[u]==0:
            queue.append(u)
    return [-1 if indegree[v] else h[v] for v in range(n)]


def image_at(h,w,t):
    """Local alphabets of T^t(full observation cube), in block order."""
    contract_time(t)
    a=1<<w
    return tuple(tuple(x for x in range(a) if h[j+x]==-1 or h[j+x]>=t)
                 for j in range(0,len(h),a))


def capacity(alphabets):
    """Exact Cartesian image size and optimal fixed-width state bits."""
    count=prod(map(len,alphabets))
    if count==0:
        raise ValueError('empty image')
    return count,(count-1).bit_length()


def pack(alphabets,w,code):
    """Mixed-radix rank, least significant block first (NCR-008 convention)."""
    contract_code(code,len(alphabets)*w)
    rank,stride=0,1
    for j,a in enumerate(alphabets):
        x=(code>>(j*w))&((1<<w)-1)
        if x not in a:
            raise ValueError('code outside temporal image')
        rank+=a.index(x)*stride
        stride*=len(a)
    return rank


def unpack(alphabets,w,rank):
    """Recover native CIG observation code without enumerating global image."""
    count,_=capacity(alphabets)
    if type(rank)is not int or not 0<=rank<count:
        raise ValueError('rank outside temporal image')
    code=0
    for j,a in enumerate(alphabets):
        rank,digit=divmod(rank,len(a))
        code|=a[digit]<<(j*w)
    return code


class Processor:
    """Local producer; admission and migrations checked by a separate receiver."""
    def __init__(self,nav,initial):
        contract_code(initial,nav.k)
        self.nav=nav
        self.initial=initial
        self.h=tuple(heights(nav))
        self.proof=dict(schema='ifs.cig025.image.v1',key=nav.key,
                        heights=list(self.h))
        self.key=digest([self.proof,str(initial)])
        self.time=0
        self.rank=initial

    def alphabets(self,t):
        return image_at(self.h,self.nav.w,t)

    def move(self,t):
        """Propose migration without committing producer state."""
        contract_time(t)
        if t<=self.time:
            raise ValueError('migration must advance time')
        old=unpack(self.alphabets(self.time),self.nav.w,self.rank)
        new=self.nav.jump(old,t-self.time)
        alph=self.alphabets(t)
        rank=pack(alph,self.nav.w,new)
        count,bits=capacity(alph)
        return dict(schema='ifs.cig025.move.v1',key=self.key,
                    previous_time=str(self.time),previous_rank=str(self.rank),
                    time=str(t),rank=str(rank),bits=bits,
                    outputs=evaluate(self.nav.decoder['circuit'],new,self.nav.k))

    def commit(self,receipt):
        """Advance local producer only after caller's receiver acceptance."""
        if receipt!=self.move(int(receipt['time'])):
            raise ValueError('not the proposed migration')
        self.time=int(receipt['time'])
        self.rank=int(receipt['rank'])
