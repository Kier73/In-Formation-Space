"""Independent event receiver, source qualification through CIG-019.
Retains checked state; checks exactly the affected gate frontier and commits atomically.
"""
from copy import deepcopy
from hashlib import sha256
import json
from verify_shared_proof import verify

class EventReceiver:
    def __init__(self,n,source,q,targets,receipt,code,**budget):
        if not verify(n,source,q,targets,receipt,**budget):raise ValueError('unqualified circuit')
        self.k=len(q);self.circuit=deepcopy(receipt['circuit']);self.key=sha256(json.dumps([self.k,self.circuit],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if type(code)is not int or not 0<=code<2**self.k:raise ValueError('code')
        self.code=code;self.epoch=0;self.values={1:1,**{j+2:(code//2**j)%2 for j in range(self.k)}};self.users={i:set() for i in range(1,self.k+2+len(self.circuit['gates']))}
        def read(r):return self.values[abs(r)] if r>0 else 1-self.values[-r]
        for j,(op,a,b) in enumerate(self.circuit['gates'],self.k+2):
            self.values[j]=min(read(a),read(b)) if op=='and' else max(read(a),read(b));self.users[abs(a)].add(j);self.users[abs(b)].add(j)
    def accept(self,r):
        try:
            if r['schema']!='ifs.cig020.event.v1' or r['circuit']!=self.key or type(r['epoch'])is not int or r['epoch']!=self.epoch+1:return False
            raw=r['code'];code=int(raw)
            if type(raw)is not str or str(code)!=raw or not 0<=code<2**self.k:return False
            mode=r.get('mode','delta')
            if mode=='full':
                if r['checks']!=[] or type(r.get('attempted')) is not int or not 0<=r['attempted']<=len(self.circuit['gates']):return False
                fresh={1:1,**{i+2:(code//2**i)%2 for i in range(self.k)}}
                def read_full(r):return fresh[abs(r)] if r>0 else 1-fresh[-r]
                for j,(op,a,b) in enumerate(self.circuit['gates'],self.k+2):fresh[j]=min(read_full(a),read_full(b)) if op=='and' else max(read_full(a),read_full(b))
                out=[None if v is None else read_full(v) for v in self.circuit['outputs']]
                if any(v is not None and type(v)is not int for v in r['outputs']) or r['outputs']!=out:return False
                self.values=fresh;self.code=code;self.epoch+=1;return True
            if mode!='delta':return False
            # Overlay holds only changed values; malformed receipts cannot mutate admitted state.
            delta={};frontier=set();diff=self.code^code
            while diff:
                v=diff.bit_length()-1;diff-=2**v;i=v+2;delta[i]=1-self.values[i];frontier.update(self.users[i])
            def read(r):
                bit=delta.get(abs(r),self.values[abs(r)]);return bit if r>0 else 1-bit
            prev=self.k+1
            if type(r['checks'])is not list or len(r['checks'])>len(self.circuit['gates']):return False
            for item in r['checks']:
                if type(item)is not list or len(item)!=2:return False
                j,b=item
                if type(j)is not int or type(b)is not int or b not in (0,1) or j<=prev or j not in frontier:return False
                # A missing earlier gate will remain in frontier and fail at end. Any later
                # dependency is impossible in topological order, so each checked input is current.
                frontier.remove(j);prev=j;op,x,y=self.circuit['gates'][j-self.k-2];expected=min(read(x),read(y)) if op=='and' else max(read(x),read(y))
                if b!=expected:return False
                if b!=self.values[j]:delta[j]=b;frontier.update(self.users[j])
            if frontier:return False
            out=[None if v is None else read(v) for v in self.circuit['outputs']]
            if any(v is not None and type(v)is not int for v in r['outputs']) or r['outputs']!=out:return False
            self.values.update(delta);self.code=code;self.epoch+=1;return True
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False
