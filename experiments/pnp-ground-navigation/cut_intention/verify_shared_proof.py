"""Independent CIG-019/020 source, colored resolution and compact circuit replay.
No imports from the new producer. UNKNOWN goals carry no admitted result.
"""
from hashlib import sha256
import json
from verify_global_sufficiency import contract,value
from verify_composed_ground import accepted


def premises(n,s,q):
    rows=[];left=[]
    for side in range(2):
        def shift(l):return l if side==0 else (abs(l)+n)*(1 if l>0 else -1)
        part=[set(map(shift,c)) for c in s]
        for j,c in enumerate(q,1):
            u=2*n+j;terms=[shift(l) for l in c]
            part.append(set(terms+[-u]));part.extend({u,-l} for l in terms)
        rows.extend(part);left.extend([side==0]*len(part))
    return rows,left

class Replay:
    def __init__(self,k):self.k=k;self.nodes=[];self.ids={}
    def op(self,operation,x,y):
        if x==y:return x
        if operation=='and':
            if -1 in (x,y) or x==-y:return -1
            if x==1:return y
            if y==1:return x
        else:
            if 1 in (x,y) or x==-y:return 1
            if x==-1:return y
            if y==-1:return x
        negate=x<0 and y<0
        if negate:x,y=-x,-y;operation={'and':'or','or':'and'}[operation]
        key=(operation,min(x,y),max(x,y))
        if key not in self.ids:self.ids[key]=len(self.nodes)+self.k+2;self.nodes.append(key)
        return -self.ids[key] if negate else self.ids[key]
    def leaf(self,n,row,left):
        a=-1 if left else 1
        if left:
            for v in sorted(row,key=abs):
                if abs(v)>2*n:a=self.op('or',a, (abs(v)-2*n+1) if v>0 else -(abs(v)-2*n+1))
        return a
    def compact(self,outputs):
        # Reverse topological liveness; no producer graph traversal.
        live={abs(v) for v in outputs if v is not None}
        for i in range(len(self.nodes)-1,-1,-1):
            if i+self.k+2 in live:live.update(map(abs,self.nodes[i][1:]))
        mapping={i:i for i in range(1,self.k+2)};gates=[]
        def ref(x):return mapping[abs(x)]*(1 if x>0 else -1)
        for i,(op,x,y) in enumerate(self.nodes,self.k+2):
            if i in live:mapping[i]=self.k+2+len(gates);gates.append([op,ref(x),ref(y)])
        return {'gates':gates,'outputs':[None if x is None else ref(x) for x in outputs]}

def replay(n,k,rows,refs,steps,circuit,max_steps,max_width,protected=None):
    if type(steps)is not list or len(steps)>max_steps:raise ValueError('proof budget')
    for item in steps:
        if type(item)is not list or len(item)!=3 or any(type(v)is not int for v in item):raise ValueError('step format')
        a,b,p=item
        if not (0<=a<len(rows) and 0<=b<len(rows) and 1<=p<=2*n+k):raise ValueError('step references')
        if protected is not None and (p<=2*n and (p-1)%n+1 in protected):raise ValueError('prefix pivot')
        if p not in rows[a] or -p not in rows[b]:raise ValueError('pivot absent')
        c=(rows[a]|rows[b])-{p,-p}
        if len(c)>max_width or any(-v in c for v in c):raise ValueError('resolvent')
        rows.append(c);refs.append(circuit.op('or' if p<=n else 'and',refs[a],refs[b]))


def verify(n,source,q,targets,r,*,max_pairs=500000,max_steps=200000,max_width=32):
    try:
        if not targets or len(targets)>128 or any(type(x)is not int or x<1 for x in (max_pairs,max_steps,max_width)):return False
        s,q,_=contract(n,source,q,targets[0]);fs=[contract(n,[],[],f)[2] for f in targets]
        if len(fs)!=len(set(fs)):return False
        key=sha256(json.dumps([n,s,q,fs],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if r['schema']!='ifs.cig019.shared.v1' or r['contract']!=key or r['status']!='COMPLETE' or len(r['goals'])!=len(fs):return False
        rows,left=premises(n,s,q);c=Replay(len(q));refs=[c.leaf(n,row,side) for row,side in zip(rows,left)]
        replay(n,len(q),rows,refs,r['prefix'],c,min(max_pairs,max_steps),max_width,{abs(v) for f in fs for v in f})
        # Residual active indices are producer search hints, never evidence of source equivalence.
        active=r['active']
        if any(type(i)is not int or not 0<=i<len(rows) for i in active) or active!=sorted(set(active)):return False
        outputs=[]
        for f,g in zip(fs,r['goals']):
            if g['status']=='UNKNOWN':outputs.append(None);continue
            if g['status']=='INSUFFICIENT':
                w=g['witness']
                if len(w)!=2 or any(type(z)is not str or not z.isascii() or not z.isdecimal() or str(int(z))!=z for z in w):return False
                x,y=map(int,w)
                if not all(0<=z<2**n and accepted(s,z) for z in (x,y)) or any(value(p,x)!=value(p,y) for p in q) or value(f,x)==value(f,y):return False
                outputs.append(None);continue
            if g['status']!='SUFFICIENT':return False
            extra=[set(f)]+[{(abs(l)+n)*(-1 if l>0 else 1)} for l in f]
            rr=rows+extra;ii=refs+[c.leaf(n,extra[0],True)]+[1]*len(f)
            replay(n,len(q),rr,ii,g['steps'],c,min(max_pairs,max_steps),max_width)
            z=g['root']
            if type(z)is not int or not 0<=z<len(rr) or rr[z]:return False
            outputs.append(ii[z])
        d=r['circuit']
        if any(type(x)is not int for row in d['gates'] for x in row[1:]) or any(v is not None and type(v)is not int for v in d['outputs']):return False
        return d==c.compact(outputs)
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False
