"""GSM-002: distinguish exact key authority from learned relative addressing."""
import argparse,copy,json,random,time
from pathlib import Path
from collections import Counter
from statistics import median
import torch
import torch.nn.functional as F
import gsm as g
NEW={'rewrite':'native64/rewrite_ground.py','measurement':'native64/measured_acquisition.py'}
NEW_PINS={'rewrite':'0e7eb55591d29c5a967ca4960b7a37f650920d2a60a93027490eae524e11255f','measurement':'34d387d9765e14041e23d430b1bde1edbaf1f2b2daa0b3e39067d2db34cb2853'}
NEW_NAMES=('rewrite','measurement','multilingual-new','binary-new')

def new_sources(root):
    s=g.sources(root)
    s.update({k:(root/p).read_bytes() for k,p in NEW.items()})
    for k,pin in NEW_PINS.items():
        if g.digest(s[k])!=pin:raise ValueError('source identity '+k)
    s['multilingual-new']=''.join(f'ข้อมูล {i:04d} | θερμοκρασία {i%29} | 記憶 {i%31} | данные {i%37}\n' for i in range(320)).encode()
    s['binary-new']=bytes(range(255,-1,-1))+random.Random(990).randbytes(16384)
    return s

def fresh(s,n,count=384):
    old=g.N;g.N=n
    try:
        r=random.Random(32000+n);return [g.episode(s,r.choice(NEW_NAMES),r,r.choice(g.KINDS)) for _ in range(count)]
    finally:g.N=old

def pack(s,es,mode):
    old=g.N;g.N=len(es[0]['positions'])
    try:x,v,y,ans,truth,active=g.batch(s,es,'ground' if mode in ('cardinality','stable') else mode)
    finally:g.N=old
    if mode in ('cardinality','stable'):
        # Exact sensor: one matching record, not the target byte or offset.
        x[:,0,4]=(v.sum(1)==5).long()
    return x,v,y,ans,truth,active

def acquire(s,e):
    """Scan only keys; payload acquired only for unique match. No label read."""
    src=s[e['source']];hits=[];cost=0
    for i,(k,p) in enumerate(e['positions']):
        if not(0<=k<=len(src)-2 and 0<=p<=len(src)-g.W):raise ValueError('bounds')
        cost+=2
        if list(src[k:k+2])==e['key']:hits.append(i)
    if len(hits)!=1:return None,cost
    p=e['positions'][hits[0]][1];return list(src[p:p+g.W]),cost+g.W

def guarded(s,es):
    fs=[];labels=[];answers=[];indices=[];cost=0
    for i,e in enumerate(es):
        payload,charge=acquire(s,e);cost+=charge
        if payload is None:continue
        q=e['key'];off=e['offset'];fs.append([[q[0],q[1],0,off,1,1]]+[[q[0],q[1],b,j,1,0] for j,b in enumerate(payload)]);labels.append(off);answers.append(payload);indices.append(i)
    x=torch.tensor(fs,dtype=torch.long).reshape(-1,5,6);return x,torch.tensor(labels,dtype=torch.long),torch.tensor(answers,dtype=torch.long).reshape(-1,4),indices,cost

def infer(model,s,es,mode):
    if mode=='qualified':
        x,labels,answers,indices,cost=guarded(s,es);result=[g.NULL]*len(es);coordinates=[-1]*len(es)
        if len(indices):
            pred=model(x,torch.ones(x.shape[:2],dtype=torch.bool))[:,1:].argmax(-1)
            for i,j,b in zip(indices,pred.tolist(),answers.gather(1,pred[:,None])[:,0].tolist()):result[i]=b;coordinates[i]=j
        return result,coordinates,cost,len(indices)*25,len(indices)
    x,v,y,ans,truth,_=pack(s,es,mode);pred=model(x,v).argmax(-1);result=ans.gather(1,pred[:,None])[:,0].tolist()
    # Correct record as well as coordinate is checked by comparing pointer label.
    coords=[(-1 if p==0 else (p-1)%4) if p==q else -2 for p,q in zip(pred.tolist(),y.tolist())]
    return result,coords,6*len(es[0]['positions'])*len(es),len(es)*x.shape[1]**2,len(es)

def evaluate(model,s,es,mode,repeats=1):
    model.eval();samples=[];last=None
    with torch.no_grad():
        for _ in range(repeats):
            t=time.perf_counter_ns();values=[];coords=[];cost=pairs=neural=0
            for i in range(0,len(es),32):
                v,c,b,p,n=infer(model,s,es[i:i+32],mode);values+=v;coords+=c;cost+=b;pairs+=p;neural+=n
            samples.append(time.perf_counter_ns()-t)
            if last is not None:assert last==(values,coords)
            last=values,coords
    stats=Counter()
    for e,v,c in zip(es,values,coords):
        _,hits,y=g.realize(s,e);expected=e['offset'] if len(hits)==1 else -1;ok=c==expected
        stats[e['kind']]+=1;stats[e['kind']+'_correct']+=v==y;stats['correct']+=v==y;stats['coordinate_correct']+=ok;stats['false_answer']+=y==g.NULL and v!=g.NULL;stats['wrong_coordinate']+=not ok and v!=g.NULL
        # Independent authority checks structural address, not just numerical coincidence.
        stats['verified_answers']+=v!=g.NULL and ok and v==y
    return dict(stats)|{'n':len(es),'logical_source_bytes':cost,'padded_attention_pairs_per_head':pairs,'neural_episodes':neural,'median_ns':int(median(samples)),'samples_ns':samples}

def train(s,mode,val,steps,seed):
    torch.manual_seed(seed);model=g.Learner();opt=torch.optim.AdamW(model.parameters(),lr=.002);weights=[.6,.2,.2];best=None;history=[];start=time.perf_counter_ns()
    for step in range(steps):
        model.train();es=g.episodes(s,'train',48,31001+seed*10000+step,weights)
        if mode=='qualified':
            x,y,_,_,_=guarded(s,es);assert len(y);z=model(x,torch.ones(x.shape[:2],dtype=torch.bool))[:,1:]
        else:x,v,y,_,_,_=pack(s,es,mode);z=model(x,v)
        loss=F.cross_entropy(z,y);opt.zero_grad();loss.backward();opt.step()
        if (step+1)%45==0 or step+1==steps:
            q=evaluate(model,s,val,mode);history.append({'step':step+1,'weights':weights[:],'validation':q});key=(q['coordinate_correct'],-q['false_answer'])
            if best is None or key>best[0]:best=(key,copy.deepcopy(model.state_dict()),step+1)
            if mode=='stable':
                # Preserve at least 50% unique examples, distribute the remaining 20%
                # above a fixed 15% floor for each nonunique case.
                err=[1-q[k+'_correct']/max(1,q[k]) for k in g.KINDS];total=sum(err)
                weights=[.5+.2*err[0]/total,.15+.2*err[1]/total,.15+.2*err[2]/total] if total else [.6,.2,.2]
    model.load_state_dict(best[1]);return model,{'mode':mode,'seed':seed,'selected_step':best[2],'training_ns':time.perf_counter_ns()-start,'history':history}

def campaign(root,out,initial):
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True);s=new_sources(root);val=g.episodes(s,'validation',480,31002,(1/3,)*3);cohorts={str(n):fresh(s,n) for n in (8,32,64)}
    report={'schema':'gsm-002-v1','sources':{k:{'sha256':g.digest(s[k]),'bytes':len(s[k])} for k in NEW_NAMES},'cohorts':cohorts,'cohort_digests':{k:g.digest(g.canonical(v)) for k,v in cohorts.items()},'runs':[],'oracle':{k:{'n':len(es),'correct':sum((acquire(s,e)[0] is None and g.realize(s,e)[2]==g.NULL) or (acquire(s,e)[0] is not None and acquire(s,e)[0][e['offset']]==g.realize(s,e)[2]) for e in es)} for k,es in cohorts.items()}}
    out.mkdir(exist_ok=True,parents=True)
    for seed in (1,2):
        for mode in ('dense','sensor','ground','adaptive','cardinality','stable','qualified'):
            if mode in ('dense','sensor','ground','adaptive'):
                m=g.Learner();m.load_state_dict(torch.load(initial/f'{mode}-{seed}.pt',weights_only=True));r={'mode':mode,'seed':seed,'selected_step':180,'retained':True}
            else:m,r=train(s,mode,val,180,seed);torch.save(m.state_dict(),out/f'{mode}-{seed}.pt')
            r['final']={k:evaluate(m,s,es,mode,3) for k,es in cohorts.items()};report['runs'].append(r);(out/'report.json').write_bytes(g.canonical(report)+b'\n');print(mode,seed,[(k,a['correct'],a['coordinate_correct'],a['false_answer'],round(a['median_ns']/1e6,2)) for k,a in r['final'].items()],flush=True)
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--initial',type=Path,required=True);a=p.parse_args();campaign(a.root,a.out,a.initial)
