"""Learn an exact parameterized byte operator from equal-length source examples."""
from bisect import bisect_left
from dataclasses import dataclass
from hashlib import sha256
from struct import pack, unpack_from
from vocabulary import compile_source, receive as receive_base, Vocabulary

MAX=65536

@dataclass(frozen=True)
class Template:
    fixed:bytes
    groups:tuple
    def __post_init__(self):
        if type(self.fixed) is not bytes or not 1<=len(self.fixed)<=MAX or type(self.groups) is not tuple or len(self.groups)>MAX:raise ValueError('template geometry')
        used=set();previous=-1
        for g in self.groups:
            if type(g) is not tuple or not g or len(g)>MAX or any(type(i) is not int or not 0<=i<len(self.fixed) for i in g) or tuple(sorted(set(g)))!=g or g[0]<=previous:raise ValueError('group')
            if any(i in used or self.fixed[i] for i in g):raise ValueError('overlap or nonzero placeholder')
            used.update(g);previous=g[0]
        sums=[0]
        for v in self.fixed:sums.append(sums[-1]+v)
        object.__setattr__(self,'prefix',tuple(sums))
        object.__setattr__(self,'positions',tuple(sorted((i,j) for j,g in enumerate(self.groups) for i in g)))
    def encode(self):
        return b'VLT1'+pack('<II',len(self.fixed),len(self.groups))+self.fixed+b''.join(pack('<I',len(g))+b''.join(pack('<H',i) for i in g) for g in self.groups)
    @property
    def digest(self):return sha256(self.encode()).digest()
    @classmethod
    def decode(cls,wire):
        if type(wire) is not bytes or not 12<=len(wire)<=12+7*MAX or wire[:4]!=b'VLT1':raise ValueError('wire')
        n,k=unpack_from('<II',wire,4)
        if not 1<=n<=MAX or k>n or 12+n>len(wire):raise ValueError('header')
        fixed=wire[12:12+n];p=12+n;groups=[];count=0
        for _ in range(k):
            if p+4>len(wire):raise ValueError('truncated group')
            m,=unpack_from('<I',wire,p);p+=4;count+=m
            if not m or count>n or p+2*m>len(wire):raise ValueError('group count')
            groups.append(tuple(unpack_from('<H',wire,p+2*i)[0] for i in range(m)));p+=2*m
        if p!=len(wire):raise ValueError('trailing data')
        return cls(fixed,tuple(groups))
    def match(self,source):
        if type(source) is not bytes or len(source)!=len(self.fixed):return None
        values=bytes(source[g[0]] for g in self.groups)
        instance=Instance(self,values)
        return instance if instance.read(0,instance.n)==source else None

@dataclass(frozen=True)
class Instance:
    template:Template
    values:bytes
    def __post_init__(self):
        if type(self.values) is not bytes or len(self.values)!=len(self.template.groups):raise ValueError('values')
    @property
    def n(self):return len(self.template.fixed)
    def read(self,a,b):
        if not 0<=a<=b<=self.n:raise ValueError('range')
        p=self.template.positions;out=bytearray(self.template.fixed[a:b])
        for i,j in p[bisect_left(p,(a,0)):bisect_left(p,(b,0))]:out[i-a]=self.values[j]
        return bytes(out)
    def total(self,a,b):
        if not 0<=a<=b<=self.n:raise ValueError('range')
        t=self.template
        return t.prefix[b]-t.prefix[a]+sum(v*(bisect_left(g,b)-bisect_left(g,a)) for v,g in zip(self.values,t.groups))
    def encode(self):return b'VLA1'+self.template.digest+self.values

def learn(examples):
    if not examples or len(examples)>256 or any(type(p) is not bytes or len(p)!=len(examples[0]) for p in examples) or not 1<=len(examples[0])<=MAX:raise ValueError('training geometry')
    fixed=bytearray(examples[0]);classes={}
    for i,col in enumerate(zip(*examples)):
        if len(set(col))>1:fixed[i]=0;classes.setdefault(col,[]).append(i)
    return Template(bytes(fixed),tuple(tuple(g) for g in classes.values()))

def apply(source,template):
    base=compile_source(source).encode()
    if template is None:return base
    inst=template.match(source)
    if inst is None:return base
    wire=inst.encode();return wire if len(wire)<len(base) else base

def qualify(template,validation):
    base=sum(len(apply(p,None)) for p in validation);candidate=len(template.encode())+sum(len(apply(p,template)) for p in validation)
    return (template if candidate<base else None),{'baseline':base,'template':candidate}

def receive(wire,template,expected_sha):
    if wire[:4]==b'VLG1':return receive_base(wire,Vocabulary(()),expected_sha)
    if template is None or type(wire) is not bytes or len(wire)!=36+len(template.groups) or wire[:4]!=b'VLA1' or wire[4:36]!=template.digest:raise ValueError('template identity or wire')
    inst=Instance(template,wire[36:]);h=sha256()
    for a in range(0,inst.n,64):h.update(inst.read(a,min(inst.n,a+64)))
    if h.hexdigest()!=expected_sha:raise ValueError('source identity')
    return inst
