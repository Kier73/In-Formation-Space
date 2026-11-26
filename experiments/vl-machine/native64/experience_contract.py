"""VLM-014: portable, source-checked observation and proposal records."""
import json
from hashlib import sha256, sha1
from pathlib import Path
from struct import iter_unpack
from collections import Counter
import importlib.util
import os

MASK=(1<<32)-1
VLM='8ca6d5e4fdfe3612cdae660473f1e3cbfb834c7a'
VLK='ad6dd45d06b9f349526783d45d0e5706a49ade79'
NEURAL='617e106b0fd1e0298083d92f85cf6b4edddc0ec0'
HEAD='1be534aa2e623c3b0f17c6250fcf47f3fc55c7abda74935807995079850388b0'
BLOBS={'src/vlk1.c':'cd9568e3246ec3eda10ecb7f6e6f5452a695935a','python/vlk.py':'e14e8fe8f372ecb707d53df29d2dcb53e75161d4'}
SCHEMA='vlm.experience-action.v1'
COHORT_PINS={'train':'7fd878ab57b1cb85703fa4a727cfd6f7f21f2150a2b7d638803388cd7d89d584','validation':'47e1915c097279c4ad84d33a4c42d88556f458e5dcfba364d66bd80c3e9e1bd1','heldout':'b5fc7a9c1dce9c59d6cde281692a8f921d5cc3a70ff9e1e77a8d1881e9bfdbe4','stress':'4b9e9e5a5f9d71e35426afa691da209cf0a01f570696d3f4331edcfe74223c77'}

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x):return sha256(canonical(x)).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)
def uint(x,bits):
    require(type(x) is int and 0<=x<1<<bits,'unsigned domain');return x
def keys(x,expected):require(type(x) is dict and set(x)==set(expected.split()),'schema fields')
def power(a,b,t):
    r,s=1,0
    while t:
        if t&1:r,s=r*a&MASK,(r*b+s)&MASK
        a,b=a*a&MASK,(a*b+b)&MASK;t>>=1
    return r,s

def k1_program(p,o):
    require(type(p) is list and 1<=len(p)<=64,'K1 program extent');uint(o,2)
    for row in p:
        require(type(row) is list and len(row)==3,'K1 instruction');op,d,x=row
        require(op in ('set','copy','add','mul','addr','mulr'),'K1 opcode');uint(d,2);uint(x,2 if op in ('copy','addr','mulr') else 32)
    return p

def k1_step(p,seed):
    v=seed[:]
    for op,d,x in p:
        if op=='set':v[d]=x
        elif op=='copy':v[d]=v[x]
        elif op=='add':v[d]=(v[d]+x)&MASK
        elif op=='mul':v[d]=v[d]*x&MASK
        elif op=='addr':v[d]=(v[d]+v[x])&MASK
        else:v[d]=v[d]*v[x]&MASK
    return v

def k1_law(p,o):
    m=[[int(i==j) for j in range(5)] for i in range(4)]
    for op,d,x in p:
        if op=='mulr':return None
        if op=='set':m[d]=[0,0,0,0,x]
        elif op=='copy':m[d]=m[x][:]
        elif op=='add':m[d][4]=(m[d][4]+x)&MASK
        elif op=='mul':m[d]=[x*y&MASK for y in m[d]]
        else:m[d]=[(a+b)&MASK for a,b in zip(m[d],m[x])]
    return None if any(m[o][j] for j in range(4) if j!=o) else (m[o][o],m[o][4])

def vlm_law(source,request):
    keys(source,'kind revision program');require(source['revision']==VLM,'VLM revision')
    raw=source['program'];require(type(raw) is str and len(raw)==480 and all(ch in '0123456789abcdef' for ch in raw),'VLM navigate extent')
    p=list(iter_unpack('<6I',bytes.fromhex(raw)));require(len(p)==10,'VLM navigate instructions')
    a,b,x=p[0][4],p[1][4],p[2][4];depth=p[3][4];t=(p[7][5]<<32)|p[7][4]
    require(1<=depth<=510,'VLM graph bound')
    expected=[(0,0,0,0,a,0),(0,1,0,0,b,0),(0,2,0,0,x,0),(1,0,0,1,depth,0),(2,3,0,0,0,0),(3,4,0,0,0,0),(4,5,4,2,0,0),(5,0,5,0,t&MASK,t>>32),(6,6,5,0,0,0),(10,0,6,0,0,0)]
    require(p==expected,'VLM navigate grammar');keys(request,'seed time');require(uint(request['seed'],32)==x and uint(request['time'],64)==t,'embedded request')
    return (*power(a,b,depth),x,t)

def features(p,o):
    n=len(p);cross=('copy','addr','mulr')
    return [round(16*sum(d==o for op,d,x in p)/n),round(16*sum(d==o and op in cross and x!=o for op,d,x in p)/n),round(16*sum(op in cross for op,d,x in p)/n),16*int(any(op=='set' and d==o for op,d,x in p)),16*int(any(op=='mulr' for op,d,x in p)),min(16,n)]

def neural(w,x):
    require(type(w) is list and len(w)==147 and all(type(v) is int and -127<=v<=127 for v in w),'weight domain')
    require(type(x) is list and len(x)==6 and all(type(v) is int and -127<=v<=127 for v in x),'feature domain')
    h=[min(127,max(0,(16*w[112+i]+sum(w[6*i+j]*x[j] for j in range(6)))//16)) for i in range(8)]
    z=[16*w[144+i]+sum(w[120+8*i+j]*h[j] for j in range(8)) for i in range(3)]
    return max(range(3),key=lambda i:z[i])

def interpret(source,request,weights):
    require(type(source) is dict,'source')
    kind=source.get('kind')
    if kind=='vlm.navigate':a,b,x,t=vlm_law(source,request)
    elif kind=='vlk.k1':
        keys(source,'kind revision program observer');require(source['revision']==VLK,'VLK revision');p=k1_program(source['program'],source['observer']);o=source['observer']
        keys(request,'seed time');v=request['seed'];require(type(v) is list and len(v)==4,'K1 seed');v=[uint(z,32) for z in v];t=uint(request['time'],64)
        law=k1_law(p,o);require(law is not None,'not a scalar affine observation');a,b=law;x=v[o]
    elif kind=='vlm.q4.proposer':
        keys(source,'kind revision weights_sha256 program observer');require(source['revision']==NEURAL,'neural revision');p=k1_program(source['program'],source['observer']);keys(request,'features');f=features(p,source['observer']);require(canonical(f)==canonical(request['features']),'feature binding')
        require(source['weights_sha256']==digest(weights),'weight identity');result=neural(weights,f)
        return {'operator':'q4.propose.v1','weights_sha256':digest(weights),'features':f},result,'proposal-only'
    else:raise ValueError('unknown source kind')
    m,c=power(a,b,t)
    return {'operator':'word32.affine.observe.v1','a':a,'b':b,'seed':x,'time':t},(m*x+c)&MASK,'exact-source-replay'

def record(source,request,value,evidence,weights):
    action,expected,authority=interpret(source,request,weights);require(type(value) is int and value==expected,'observed value mismatch')
    keys(evidence,'kind parent record');require(evidence['kind'] in ('retained-vlm','retained-vlk','retained-neural','fresh-vlk'),'evidence kind')
    for k in ('parent','record'):require(type(evidence[k]) is str and len(evidence[k])==64 and all(c in '0123456789abcdef' for c in evidence[k]),'evidence locator')
    body={'schema':SCHEMA,'source':source,'source_id':digest(source),'request':request,'action':action,'action_id':digest(action),'value':value,'authority':authority,'evidence':evidence}
    return body|{'record_id':digest(body)}

def verify(r,weights):
    keys(r,'schema source source_id request action action_id value authority evidence record_id')
    require(canonical(record(r['source'],r['request'],r['value'],r['evidence'],weights))==canonical(r),'record binding');return True

def kernel(root):
    root=Path(root)
    for name,pin in BLOBS.items():
        b=(root/name).read_bytes();require(sha1(('blob %d\0'%len(b)).encode()+b).hexdigest()==pin,'K1 source identity')
    spec=importlib.util.spec_from_file_location('contract_vlk',root/'python/vlk.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.Kernel(root/'dist/libvlk.so')

def campaign(vlm_path,vlk_path,root):
    raw=Path(vlm_path).read_bytes();archive=Path(vlk_path).read_bytes();data=json.loads(archive);weights=data['report']['weights'];require(data['report']['vlk_commit']==VLK,'archive revision')
    vhash=sha256(raw).hexdigest();khash=sha256(archive).hexdigest();k=kernel(root);out=[];counts=Counter();head='0'*64
    def add(s,q,v,e):out.append(record(s,q,v,e,weights));counts[s['kind']]+=1
    for i,line in enumerate(raw.splitlines()):
        row=json.loads(line);require(row['sequence']==i and row['previous']==head and digest({a:b for a,b in row.items() if a!='digest'})==row['digest'],'ledger chain');head=row['digest'];e=row['experience'];p=bytes.fromhex(e['source_hex']);require(sha256(p).hexdigest()==e['source_sha256'],'ledger source')
        if e['task']['arm']!='navigate':continue
        require(e['status']=='verified' and e['native_ok'] is True and e['output']==e['reference'] and len(e['output'])==1,'retained encounter')
        q={'seed':e['task']['z'],'time':e['task']['time']};s={'kind':'vlm.navigate','revision':VLM,'program':p.hex()};v=e['output'][0]
        add(s,q,v,{'kind':'retained-vlm','parent':vhash,'record':head})
        a,b,x,t=vlm_law(s,q);program=[['mul',0,a],['add',0,b]];seed=[x,0,0,0];r=k.evaluate(seed,program,t,mode='ground');require(r['status']==0 and r['registers'][0]==v,'cross-substrate native result')
        add({'kind':'vlk.k1','revision':VLK,'program':program,'observer':0},{'seed':seed,'time':t},v,{'kind':'fresh-vlk','parent':vhash,'record':head});require(out[-1]['action_id']==out[-2]['action_id'] and out[-1]['source_id']!=out[-2]['source_id'],'cross-source equivalence');counts['paired']+=1
    require(head==HEAD,'retained head')
    for cohort in ('training','validation','heldout','stress'):
        rows=data[cohort];name='train' if cohort=='training' else cohort;require(digest(rows)==data['report'][name+'_digest']==COHORT_PINS[name],'cohort identity')
        for row in rows:
            p,o=row['program'],row['observer'];k1_program(p,o);require(row['source_sha256']==digest([p,o]),'K1 source identity')
            require(len(row['basis'])==5,'basis extent')
            for i,v in enumerate(row['basis']):
                seed=[int(j==i-1) for j in range(4)] if i else [0]*4
                require(k1_step(p,seed)==v,'basis replay');counts['basis_replayed']+=1
        if cohort=='training':continue
        qkey={'validation':'validation_queries','heldout':'queries','stress':'stress_queries'}[cohort];results=data[qkey];require(len(results)==len(rows),'cohort length')
        if cohort in ('heldout','stress'):require(digest(results)==data['report'][('stress_' if cohort=='stress' else '')+'result_digest'],'result identity')
        for row,obs in zip(rows,results):
            p,o=row['program'],row['observer'];sid=row['source_sha256'];require(obs['source_sha256']==sid,'query source')
            add({'kind':'vlm.q4.proposer','revision':NEURAL,'weights_sha256':digest(weights),'program':p,'observer':o},{'features':row['features']},obs['proposal'],{'kind':'retained-neural','parent':khash,'record':digest(obs)})
            law=k1_law(p,o)
            require(len(obs['queries'])==4,'query extent')
            for q in obs['queries']:
                seed,t,v=q['seed'],q['time'],q['value'];r=k.evaluate(seed,p,t);require(r['status']==0 and r['registers'][o]==v,'fresh K1 archive replay');counts['native_archive_replay']+=1
                if law is None:counts['outside_scalar_contract']+=1;continue
                add({'kind':'vlk.k1','revision':VLK,'program':p,'observer':o},{'seed':seed,'time':t},v,{'kind':'retained-vlk','parent':khash,'record':digest([sid,q])})
    for r in out:verify(r,weights)
    groups={}
    for r in out:groups.setdefault(r['action_id'],[]).append(r)
    for g in groups.values():require(len({r['value'] for r in g})==1,'semantic disagreement')
    report={'schema':'vlm-experience-contract-campaign-v1','parents':{'vlm':vhash,'vlk':khash},'counts':dict(counts),'records':len(out),'unique_actions':len(groups),'cross_source_actions':sum(len({r['source_id'] for r in g})>1 for g in groups.values()),'cross_source_exact_actions':sum(g[0]['authority']=='exact-source-replay' and len({r['source_id'] for r in g})>1 for g in groups.values()),'cross_source_proposal_actions':sum(g[0]['authority']=='proposal-only' and len({r['source_id'] for r in g})>1 for g in groups.values()),'exact_records':sum(r['authority']=='exact-source-replay' for r in out),'proposal_records':sum(r['authority']=='proposal-only' for r in out),'records_sha256':digest(out),'weights_sha256':digest(weights)}
    return report,out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--vlm',required=True);p.add_argument('--vlk',required=True);p.add_argument('--root',default=os.environ.get('VLK_ROOT'));p.add_argument('--output',required=True);a=p.parse_args();report,rows=campaign(a.vlm,a.vlk,a.root);Path(a.output).write_bytes(canonical({'report':report,'records':rows})+b'\n');print(json.dumps(report,indent=2,sort_keys=True))
