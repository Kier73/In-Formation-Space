"""VLM-003 portable local reconstruction, with source and witness revalidation."""
import ctypes as c
import hashlib
import json
import sys
from pathlib import Path

U=c.c_uint32
T=c.c_uint64
MASK=2**32-1
class Node(c.Structure):
    _fields_=[(n,U) for n in ('op','a','b','c','k')]
L=c.CDLL(str(Path(__file__).resolve().with_name('libcore.so')))
for name,args,result in [
    ('begin',[U,U],c.c_int),('put',[U,Node],c.c_int),('commit',[],c.c_int),
    ('admit',[U,U],c.c_int),('admit_chart',[U,U],c.c_int),
    ('graph_publish',[],U),('graph_release',[U],c.c_int),
    ('proc_restore',[U,U,T],U),('proc_close',[U],c.c_int),
    ('proc_read',[U,c.POINTER(U),c.POINTER(U)],c.c_int),
    ('proc_checkpoint',[U,c.POINTER(U),c.POINTER(U),c.POINTER(T)],c.c_int),
    ('graph_info',[U]+[c.POINTER(U)]*5,c.c_int),('graph_node',[U,U,c.POINTER(Node)],c.c_int)]:
    f=getattr(L,name);f.argtypes=args;f.restype=result

def canonical(o):return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
def sha(o):return hashlib.sha256(canonical(o)).hexdigest()
def uint(x,bits):return type(x) is int and 0<=x<1<<bits

def export(h):
    g,s,t=U(),U(),T()
    if not L.proc_checkpoint(h,c.byref(g),c.byref(s),c.byref(t)):raise ValueError('not a grounded process')
    n,o,k,a,b=[U() for _ in range(5)]
    if not L.graph_info(g,*map(c.byref,[n,o,k,a,b])):raise ValueError('graph unavailable')
    nodes=[]
    for i in range(n.value):
        node=Node()
        if not L.graph_node(g,i,c.byref(node)):raise ValueError('graph unavailable')
        nodes.append([getattr(node,f) for f,_ in Node._fields_])
    source={'nodes':nodes,'output':o.value,'semantics':'vlm-word32-v1'}
    body={'version':1,'source':source,'source_sha256':sha(source),'witness':[k.value,a.value,b.value],'seed':s.value,'time':t.value}
    return {'body':body,'sha256':sha(body)}

def validate(cap):
    if type(cap) is not dict or set(cap)!={'body','sha256'}:raise ValueError('capsule envelope')
    b=cap['body']
    if type(b) is not dict or set(b)!={'version','source','source_sha256','witness','seed','time'}:raise ValueError('capsule body')
    if type(b['version']) is not int or b['version']!=1 or not uint(b['seed'],32) or not uint(b['time'],64):raise ValueError('coordinate')
    s=b['source']
    if type(s) is not dict or set(s)!={'nodes','output','semantics'} or s['semantics']!='vlm-word32-v1':raise ValueError('source')
    ns=s['nodes'];o=s['output'];w=b['witness']
    if type(ns) is not list or not 1<=len(ns)<=1024 or not uint(o,32) or o>=len(ns):raise ValueError('graph bounds')
    if any(type(n) is not list or len(n)!=5 or not all(uint(x,32) for x in n) for n in ns):raise ValueError('node fields')
    if type(w) is not list or len(w)!=3 or not all(uint(x,32) for x in w) or w[0] not in (1,2):raise ValueError('witness')
    if b['source_sha256']!=sha(s) or cap['sha256']!=sha(b):raise ValueError('digest mismatch')
    return b

def restore(cap):
    b=validate(cap);s=b['source'];k,a,d=b['witness']
    if not L.begin(len(s['nodes']),s['output']):raise ValueError('begin failed')
    for i,n in enumerate(s['nodes']):
        if not L.put(i,Node(*n)):raise ValueError('invalid descriptor')
    if not L.commit():raise ValueError('commit failed')
    if not (L.admit(a,d) if k==1 else L.admit_chart(a,d)):raise ValueError('Ground rejected by receiver')
    g=L.graph_publish()
    if not g:raise ValueError('graph capacity')
    h=L.proc_restore(g,b['seed'],b['time'])
    if not h:L.graph_release(g);raise ValueError('process capacity')
    return g,h

def observe(h):
    y,w=U(),U()
    if not L.proc_read(h,c.byref(y),c.byref(w)):raise ValueError('process unavailable')
    return {'value':y.value,'work':w.value}

def main():
    raw=sys.stdin.buffer.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('capsule too large')
    g,h=restore(json.loads(raw));print(json.dumps(observe(h),sort_keys=True));L.proc_close(h);L.graph_release(g)

if __name__=='__main__':main()
