"""Independent semantic checker for CIG-024. No producer imports.
Validates local atom truth, Boolean gate identities and shifted roots by
synchronized traversal, not by trusting the producer's unique table.
"""
from math import gcd,lcm,prod
from itertools import product
from verify_temporal_ground import Receiver

class Checked:
    def __init__(self,base,nodes,max_work=4_000_000):
        self.base=tuple(base);self.nodes=[];self.work=0;self.limit=max_work;unique=set();self.memo=set()
        if type(nodes)is not list:raise ValueError('nodes')
        for i,row in enumerate(nodes,2):
            j,kids=row
            if type(j)is not int or not 0<=j<len(base) or type(kids)is not list or len(kids)!=base[j] or any(type(v)is not int or not 0<=v<i or self.level(v)<=j for v in kids) or len(set(kids))<2:raise ValueError('invalid diagram')
            key=j,tuple(kids)
            if key in unique:raise ValueError('duplicate node')
            self.charge(len(kids));unique.add(key);self.nodes.append(key)
    def charge(self,n=1):
        self.work+=n
        if self.work>self.limit:raise ValueError('checker budget')
    def root(self,x):
        if type(x)is not int or not 0<=x<len(self.nodes)+2:raise ValueError('root')
        return x
    def level(self,v):return len(self.base) if v<2 else self.nodes[v-2][0]
    def arc(self,v,j,r):return self.nodes[v-2][1][r] if self.level(v)==j else v
    def value(self,v,t):
        while v>=2:
            j,z=self.nodes[v-2];v=z[t%self.base[j]]
        return v
    def relation(self,op,a,b,z,delta=0):
        a,b,z=map(self.root,(a,b,z));delta%=prod(self.base)
        def check(a,b,z):
            key=op,a,b,z,delta
            if key in self.memo:return
            self.charge();j=min(map(self.level,(a,b,z)))
            if j==len(self.base):
                want=1-a if op=='not' else a if op=='shift' else a*b if op=='and' else max(a,b) if op=='or' else (a+b)%2
                if z!=want:raise ValueError('incorrect operation')
            else:
                for r in range(self.base[j]):
                    check(self.arc(a,j,(r+delta)%self.base[j] if op=='shift' else r),self.arc(b,j,r),self.arc(z,j,r))
            self.memo.add(key)
        check(a,b,z)
    def atom(self,v,L,yes):
        self.root(v);seen=set();stack=[v]
        while stack:
            x=stack.pop()
            if x<2 or x in seen:continue
            seen.add(x);j,kids=self.nodes[x-2]
            if gcd(L,self.base[j])==1:raise ValueError('extraneous atom coordinate')
            # Full prime-power coordinates may be larger than the local period.
            d=gcd(L,self.base[j]);self.charge(len(kids))
            if any(kids[r]!=kids[r%d] for r in range(len(kids))):raise ValueError('atom phase')
            stack.extend(kids[:d])
        for t in range(L):
            self.charge()
            if self.value(v,t)!=int(t in yes):raise ValueError('atom truth')
    def count(self,v):
        self.root(v);counts=[0,1];tail=[prod(self.base[j:]) for j in range(len(self.base)+1)]
        for j,kids in self.nodes:counts.append(sum(counts[x]*(tail[j+1]//tail[self.level(x)]) for x in kids))
        return counts[v]*tail[0]//tail[self.level(v)]

class Admission:
    def __init__(self,receiver,receipt,*,max_cells=2_000_000,max_work=4_000_000):
        if type(receiver)is not Receiver or not receiver.total_image:raise ValueError('total image required')
        r=receipt;k,w,a,g,c,initial=receiver.k,receiver.w,receiver.a,receiver.g,receiver.circuit,receiver.initial
        if set(r)!={'schema','key','initial','cutoff','base','refs','outputs','prefix','nodes','cells','work'} or r['schema']!='ifs.cig024.algebra.v1' or r['key']!=receiver.key or r['initial']!=str(initial):raise ValueError('identity')
        vertices=[i*a+(initial//2**(i*w))%a for i in range(k//w)];D=max(g['depth'][v] for v in vertices)
        if type(r['cutoff'])is not int or r['cutoff']!=D:raise ValueError('cutoff')
        def code_at(z,t):
            code=0
            for i in z:
                v=vertices[i];d=g['depth'][v]
                if t<d:
                    for _ in range(t):v=receiver.edges[v]
                else:
                    cy,j=receiver.pos[g['entry'][v]];v=cy[(j+t-d)%len(cy)]
                j,b=divmod(v,a);code+=b*2**(j*w)
            return code
        def outputs(code):
            v=[0,1]+[code//2**i%2 for i in range(k)]
            def read(i):return v[i] if i>0 else 1-v[-i]
            for op,x,y in c['gates']:v.append(min(read(x),read(y)) if op=='and' else max(read(x),read(y)))
            return [read(x) for x in c['outputs']]
        cells=D*(len(vertices)+len(c['gates'])+1)
        if cells>max_cells or type(r['prefix'])is not list or any(type(row)is not list or any(type(v)is not int or v not in (0,1) for v in row) for row in r['prefix']) or r['prefix']!=[outputs(code_at(range(len(vertices)),t)) for t in range(D)]:raise ValueError('prefix')
        p={i:j for j,i in enumerate(g['pred'])};unused=set(p);groups=[];periods=[]
        while unused:
            z=set();i=min(unused)
            while i not in z:z.add(i);i=p[i]
            unused-=z;groups.append(sorted(z));periods.append(lcm(*(len(receiver.pos[g['entry'][vertices[i]]][0]) for i in z)))
        base=r['base'];P=lcm(*periods)
        if type(base)is not list or any(type(b)is not int or b<2 for b in base) or prod(base)!=P or any(gcd(x,y)!=1 for i,x in enumerate(base) for y in base[i+1:]):raise ValueError('CRT basis')
        # Canonical sorted prime-power basis, factored by independent trial division.
        ps=[]
        for b in base:
            q=next((i for i in range(2,b+1) if b%i==0),b);v=b
            while v%q==0:v//=q
            if v!=1:raise ValueError('prime power')
            ps.append(q)
        if ps!=sorted(ps):raise ValueError('basis order')
        d=Checked(base,r['nodes'],max_work)
        if type(r['refs'])is not list or any(type(row)is not list or len(row)!=2 or any(type(v)is not int for v in row) for row in r['refs']):raise ValueError('reference contract')
        refs=dict(r['refs']);live={abs(x) for x in c['outputs']}
        for j in reversed(range(k+2,k+2+len(c['gates']))):
            if j in live:live.update(map(abs,c['gates'][j-k-2][1:]))
        if set(refs)!=live|{1} or refs[1]!=1 or r['refs']!=[[j,refs[j]] for j in sorted(refs)]:raise ValueError('references')
        for z,L in zip(groups,periods):
            bits=[v-2 for v in live if 2<=v<=k+1 and (v-2)//w in z]
            if not bits:continue
            cells+=L*(len(z)+len(bits))
            if cells>max_cells:raise ValueError('cells')
            yes={i:set() for i in bits}
            for dt in range(L):
                code=code_at(z,D+dt)
                for i in bits:
                    if code//2**i%2:yes[i].add((D+dt)%L)
            for i in bits:d.atom(refs[i+2],L,yes[i])
        # Signed literals need not have explicit complement nodes. Find the
        # unique candidate complement from the admitted DAG and check it.
        neg={0:1,1:0};lookup={key:i for i,key in enumerate(d.nodes,2)}
        def comp(i):
            if i not in neg:
                j,z=d.nodes[i-2];key=(j,tuple(comp(x) for x in z))
                if key not in lookup:raise ValueError('missing complement')
                neg[i]=lookup[key];d.relation('not',i,0,neg[i])
            return neg[i]
        def get(v):return d.root(refs[v]) if v>0 else comp(d.root(refs[-v]))
        for j,(op,x,y) in enumerate(c['gates'],k+2):
            if j in live:d.relation(op,get(x),get(y),refs[j])
        if type(r['outputs'])is not list or any(type(v)is not int for v in r['outputs']) or r['outputs']!=[get(v) for v in c['outputs']] or type(r['cells'])is not int or r['cells']!=cells or type(r['work'])is not int or r['work']<0:raise ValueError('outputs')
        self.d=d;self.D=D;self.roots=list(r['outputs']);self.prefix=[sum(row[i]*2**t for t,row in enumerate(r['prefix'])) for i in range(len(self.roots))];self.base_nodes=len(d.nodes);self.max_work=max_work;self.ops=[]
    def extend(self,packet):
        # Atomic admission: independent validation, then publish state.
        if set(packet)!={'nodes','ops'}:raise ValueError('packet contract')
        d=Checked(self.d.base,packet['nodes'],self.max_work)
        if d.nodes[:len(self.d.nodes)]!=self.d.nodes:raise ValueError('changed admitted prefix')
        if type(packet['ops']) is not list or any(type(row)is not list or len(row)!=5 or type(row[1])is not int or type(row[3])is not int or type(row[4])is not str or (row[2] is not None and type(row[2])is not int) for row in packet['ops']) or packet['ops'][:len(self.ops)]!=self.ops:raise ValueError('changed admitted operations')
        d.memo.update(self.d.memo)
        roots=self.roots[:];prefix=self.prefix[:];mask=(1<<self.D)-1
        for op,x,y,r,z in packet['ops'][len(self.ops):]:
            if type(x)is not int or not 0<=x<len(roots):raise ValueError('operand')
            a=roots[x];p=prefix[x]
            if op=='shift':
                if type(y)is not int or y<0 or y.bit_length()>4096:raise ValueError('shift')
                d.relation(op,a,0,r,y);v=sum(((p//2**(t+y)%2) if t+y<self.D else d.value(a,t+y))*2**t for t in range(self.D))
            elif op=='not':
                if y is not None:raise ValueError('not operand')
                d.relation(op,a,0,r);v=mask-p
            else:
                if op not in ('and','or','xor') or type(y)is not int or not 0<=y<len(roots):raise ValueError('operation')
                d.relation(op,a,roots[y],r);q=prefix[y];v=p&q if op=='and' else p|q if op=='or' else p^q
            if z!=str(v):raise ValueError('prefix result')
            roots.append(r);prefix.append(v)
        # Full cumulative packet, with an immutable admitted prefix.
        from copy import deepcopy
        self.d=d;self.roots=roots;self.prefix=prefix;self.ops=deepcopy(packet['ops'])
    def count(self,i):return self.d.count(self.roots[i])
    def verify_next(self,i,start,r,max_states=100_000):
        try:
            if type(start)is not int or start<0 or start.bit_length()>4096 or set(r)!={'status','time','trace'} or r['status'] not in ('FOUND','UNREACHABLE') or type(r['trace'])is not list:return False
            for t in range(start,self.D):
                if self.prefix[i]>>t&1:return r==dict(status='FOUND',time=str(t),trace=[])
            start=max(start,self.D);d=self.d;states=[];active=set()
            def add(v,x,m):
                if v:active.add(len(states));states.append((v,x,m))
            add(self.roots[i],0,1)
            for j in r['trace']:
                if type(j)is not int or j not in active or len(states)>max_states:return False
                v,x,m=states[j]
                if v<2:return False
                active.remove(j);level,kids=d.nodes[v-2];b=d.base[level];inv=pow(m,-1,b)
                for a,u in enumerate(kids):add(u,(x+m*((a-x)*inv%b))%(m*b),m*b)
            if len(states)>max_states:return False
            if not active:return r['status']=='UNREACHABLE' and r['time'] is None
            t=min(start+(states[j][1]-start)%states[j][2] for j in active)
            return t.bit_length()<=4096 and r['status']=='FOUND' and r['time']==str(t) and d.value(self.roots[i],t)==1
        except (TypeError,ValueError,KeyError,IndexError,OverflowError):return False
    def verify_interval(self,i,lo,hi,r,max_states=100_000):
        from collections import deque
        try:
            if any(type(t)is not int or t<0 or t.bit_length()>4096 for t in (lo,hi)) or hi<lo or type(max_states)is not int or max_states<1:return False
            if set(r)!={'status','count','states'} or r['status']!='EXACT' or type(r['count'])is not str or type(r['states'])is not int:return False
            # Separately traverse by breadth-first congruence classes, using
            # quotient differences instead of the producer's first-hit arithmetic.
            total=sum(self.prefix[i]//2**t%2 for t in range(lo,min(hi,self.D)));lo=max(lo,self.D);P=prod(self.d.base);states=0
            if hi>lo:
                q,rem=divmod(hi-lo,P);total+=q*self.count(i);hi=lo+rem
                todo=deque([(self.roots[i],0,1)] if rem else [])
                while todo:
                    v,x,m=todo.popleft();states+=1
                    if states>max_states:return False
                    amount=(hi-1-x)//m-(lo-1-x)//m
                    if amount==0 or not v:continue
                    if v==1:total+=amount;continue
                    j,kids=self.d.nodes[v-2];b=self.d.base[j];inv=pow(m,-1,b)
                    for a,u in enumerate(kids):
                        if u:todo.append((u,(x+m*((a-x)*inv%b))%(m*b),m*b))
            return r==dict(status='EXACT',count=str(total),states=states)
        except (ValueError,TypeError,IndexError,KeyError,OverflowError):return False
