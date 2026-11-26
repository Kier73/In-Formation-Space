"""GSM-001: source-bound synthetic navigation and structural attention.
Exact key equality supplies a sensor; gathering is not dense-attention equivalence.
"""
import argparse,hashlib,json,random,time
from pathlib import Path
from collections import Counter
import torch
from torch import nn
import torch.nn.functional as F
N,W,D,NULL=8,4,32,256
KINDS=('unique','ambiguous','absent')
MODES=('corpus','dense','sensor','ground','adaptive')
PATHS={'machine':'machine.py','transfer':'native64/transfer_policy.py','ledger':'native64/datasets/vlm011/experience.jsonl','intention':'native64/intention_acquisition.py','schedule':'native64/rewrite_schedule.py','catalogue':'native64/datasets/vlm011/experience-summary.json'}
PINS=dict(zip(PATHS,('c3e85fb026bb8dc0ad520ac88752475f06bde32ec734710893442254196d6950','155aadccbeaab5dafdec42f85d1a042185ce16345ede85fc3c356bed834fa164','994d2c9bd23e17209803c4faeedbb84409705eb687a4537ffaff51f0119cb413','3ecc81d20d27ac66b68551141444969ab76598b15370c79bf8f3550b567434d4','34426c5a519e443408cce0f7577760f03adf89dc3736b35286d3188af38c8e70','32a034bf40a36f694346bea6a7e0c3daf3d0e9006bdf0ffc2cbcbc2ee925fdb9')))
SPLITS={'train':('machine','transfer','ledger','binary-train'),'validation':('intention','binary-validation'),'final':('schedule','catalogue','multilingual','binary-final')}
def digest(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def sources(root):
    s={k:(root/p).read_bytes() for k,p in PATHS.items()}
    for k,v in s.items():
        if digest(v)!=PINS[k]:raise ValueError('source identity '+k)
    for i,p in enumerate(('train','validation','final')):s['binary-'+p]=bytes(range(256))+random.Random(840+i).randbytes(8192)
    s['multilingual']=''.join(f'記録 {i:04d} | température {i%23} | سجل {i%17} | तापमान {i%19}\n' for i in range(256)).encode()
    return s

def episode(s,name,r,kind):
    data=s[name];pos=[];keys=set()
    for _ in range(10000):
        p=r.randrange(len(data)-W-1);k=data[p:p+2]
        if k not in keys:pos.append([p,p+2]);keys.add(k)
        if len(pos)==N:break
    if len(pos)!=N:raise ValueError('insufficient key diversity')
    a,b=r.sample(range(N),2);key=data[pos[a][0]:pos[a][0]+2]
    if kind=='ambiguous':pos[b][0]=pos[a][0]
    if kind=='absent':
        while key in keys:key=r.randbytes(2)
    return {'source':name,'positions':pos,'key':list(key),'offset':r.randrange(W),'kind':kind}

def realize(s,e):
    data=s[e['source']];rows=[]
    for k,p in e['positions']:
        if not(0<=k<=len(data)-2 and 0<=p<=len(data)-W):raise ValueError('range')
        rows.append(list(data[k:k+2]+data[p:p+W]))
    hits=[i for i,row in enumerate(rows) if row[:2]==e['key']]
    if KINDS[0 if len(hits)==1 else 1 if hits else 2]!=e['kind']:raise ValueError('label')
    return rows,hits,rows[hits[0]][2+e['offset']] if len(hits)==1 else NULL

def episodes(s,phase,n,seed,weights=(.6,.2,.2)):
    r=random.Random(seed);return [episode(s,r.choice(SPLITS[phase]),r,r.choices(KINDS,weights)[0]) for _ in range(n)]

def batch(s,es,mode):
    width=N if mode in ('dense','sensor','corpus') else 2
    features=[];valid=[];labels=[];answers=[];truth=[];active=0
    for e in es:
        rows,hits,y=realize(s,e);q=e['key'];off=e['offset'];sel=list(range(N)) if width==N else hits
        if len(sel)>width:raise ValueError('gather extent')
        fs=[[q[0],q[1],0,off,0,1]];mask=[True];out=[NULL];active+=1+W*len(sel)
        label=1+W*sel.index(hits[0])+off if len(hits)==1 else 0
        for i in sel:
            row=rows[i];match=int(i in hits) if mode not in ('dense','corpus') else 0
            for j in range(W):fs.append([row[0],row[1],row[2+j],j,match,0]);mask.append(True);out.append(row[2+j])
        for _ in range(W*(width-len(sel))):fs.append([0,0,0,0,0,0]);mask.append(False);out.append(NULL)
        features.append(fs);valid.append(mask);labels.append(label);answers.append(out);truth.append(y)
    return tuple(map(torch.tensor,(features,valid,labels,answers,truth)))+(active,)

class Learner(nn.Module):
    def __init__(self):
        super().__init__();self.byte=nn.Embedding(256,D);self.offset=nn.Embedding(W,D);self.sensor=nn.Embedding(2,D);self.role=nn.Embedding(2,D);self.pos=nn.Embedding(33,D)
        self.block=nn.TransformerEncoderLayer(D,4,64,dropout=0.,batch_first=True,norm_first=True);self.norm=nn.LayerNorm(D);self.q=nn.Linear(D,D);self.k=nn.Linear(D,D);self.reject=nn.Linear(D,1);self.lm=nn.Linear(D,257)
    def forward(self,x,valid,corpus=False):
        h=self.byte(x[:,:,0])+self.byte(x[:,:,1])+self.byte(x[:,:,2])+self.offset(x[:,:,3])+self.sensor(x[:,:,4])+self.role(x[:,:,5])
        if corpus:h=h+self.pos(torch.arange(x.shape[1]))
        h=self.norm(self.block(h,src_key_padding_mask=~valid));q=h[:,0]
        if corpus:return self.lm(q)
        logits=(self.q(q)[:,None,:]*self.k(h)).sum(-1)/D**.5
        return torch.cat([self.reject(q),logits[:,1:]],1).masked_fill(~valid,-1e9)

def corpus_batch(s,r,n):
    rows=[];ys=[]
    for _ in range(n):
        data=s[r.choice(SPLITS['train'])];p=r.randrange(len(data)-32);v=data[p:p+33];ys.append(v[-1]);rows.append([[0,0,b,i%W,0,int(i==31)] for i,b in enumerate(v[:-1])][::-1])
    return torch.tensor(rows),torch.ones((n,32),dtype=torch.bool),torch.tensor(ys)

def score(model,s,es,mode):
    model.eval();c=Counter();start=time.perf_counter_ns();tokens=0
    with torch.no_grad():
        for j in range(0,len(es),64):
            part=es[j:j+64];x,v,label,ans,y,active=batch(s,part,mode);tokens+=active
            pred=model(x,v,mode=='corpus').argmax(-1)
            if mode=='corpus':value=pred;right=torch.zeros_like(pred,dtype=torch.bool)
            else:value=ans.gather(1,pred[:,None])[:,0];right=pred==label
            for e,a,b,ok in zip(part,value.tolist(),y.tolist(),right.tolist()):
                k=e['kind'];c[k]+=1;c[k+'_correct']+=a==b;c['correct']+=a==b;c['coordinate_correct']+=ok;c['false_answer']+=b==NULL and a!=NULL;c['wrong_byte']+=b!=NULL and a!=NULL and a!=b;c['abstained_unique']+=b!=NULL and a==NULL
    return dict(c)|{'n':len(es),'active_tokens':tokens,'elapsed_ns':time.perf_counter_ns()-start}

def train(s,mode,val,final,steps,seed):
    torch.manual_seed(seed);model=Learner();opt=torch.optim.AdamW(model.parameters(),lr=.002);r=random.Random(31001+seed);weights=[.6,.2,.2];history=[];tokens=0;start=time.perf_counter_ns()
    for step in range(steps):
        model.train()
        if mode=='corpus':x,v,y=corpus_batch(s,r,48);tokens+=x.shape[0]*x.shape[1]
        else:x,v,y,_,_,active=batch(s,episodes(s,'train',48,31001+seed*10000+step,weights),mode);tokens+=active
        loss=F.cross_entropy(model(x,v,mode=='corpus'),y);opt.zero_grad();loss.backward();opt.step()
        if (step+1)%max(1,steps//4)==0 or step+1==steps:
            z=score(model,s,val,mode);history.append({'step':step+1,'loss':float(loss.detach()),'validation':z,'weights':weights[:]})
            if mode=='adaptive':
                err=[1-z[k+'_correct']/max(1,z[k]) for k in KINDS];weights=[.15+.55*a/sum(err) for a in err] if sum(err)>0 else [1/3]*3
    elapsed=time.perf_counter_ns()-start
    return model,{'mode':mode,'seed':seed,'parameters':sum(p.numel() for p in model.parameters()),'updates':steps,'training_examples':steps*48,'training_active_tokens':tokens,'train_ns':elapsed,'history':history,'final':score(model,s,final,mode),'by_source':{n:score(model,s,[e for e in final if e['source']==n],mode) for n in SPLITS['final']}}

def campaign(root,out,steps=180,seeds=(1,2)):
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True);s=sources(root);val=episodes(s,'validation',480,31002,(1/3,)*3);final=episodes(s,'final',960,31003,(1/3,)*3)
    report={'schema':'gsm-001-v1','sources':{k:{'sha256':digest(v),'bytes':len(v)} for k,v in s.items()},'splits':SPLITS,'validation':val,'final':final,'final_digest':digest(canonical(final)),'oracle':{'n':len(final),'correct':sum(realize(s,e)[2]==(s[e['source']][e['positions'][next(i for i,p in enumerate(e['positions']) if list(s[e['source']][p[0]:p[0]+2])==e['key'])][1]+e['offset']] if e['kind']=='unique' else NULL) for e in final),'status_counts':dict(Counter(e['kind'] for e in final))},'steps':steps,'seeds':list(seeds),'torch':torch.__version__,'runs':[]}
    out.mkdir(parents=True,exist_ok=True)
    for seed in seeds:
        for mode in MODES:
            model,r=train(s,mode,val,final,steps,seed);report['runs'].append(r);torch.save(model.state_dict(),out/f'{mode}-{seed}.pt');(out/'report.json').write_bytes(canonical(report)+b'\n');print(mode,seed,r['final'],'train_s',r['train_ns']/1e9,flush=True)
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--steps',type=int,default=180);p.add_argument('--seeds',type=int,nargs='+',default=[1,2]);a=p.parse_args();campaign(a.root,a.output,a.steps,a.seeds)
