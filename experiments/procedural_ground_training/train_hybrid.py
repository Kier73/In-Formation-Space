"""PGT-002B: symbolic partial-ground planner as an *observable* auxiliary input.

Only the observed subset is passed to the IOS-001-style exact partial solver.
No hidden-source labels or verification witness is exposed to this learner.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn

from procedural_ground_training import canonical, sha
from train_transfer import _examples
from cross_family_curriculum import TRAIN_FAMILIES

class HybridStudent(nn.Module):
    def __init__(self):
        super().__init__()
        self.phi=nn.Sequential(nn.Linear(29,96),nn.GELU(),nn.Linear(96,64),nn.GELU())
        self.head=nn.Linear(64,9)
    def forward(self,x):return self.head(self.phi(x))

def add_partial_plan(x,partial_plan):
    onehot=np.eye(9,dtype=np.float32)[np.asarray(partial_plan,dtype=np.int64)]
    return np.concatenate((x,onehot),axis=1)

def train(args):
    torch.manual_seed(args.seed);torch.set_num_threads(3)
    started=time.monotonic()
    arrays={}
    nonoverlap=set()
    for key,seed,n,fam,states in (
        ('train',7301,args.train,TRAIN_FAMILIES,16),
        ('valid',7302,args.valid,TRAIN_FAMILIES,16),
        ('in_family',7303,args.test,TRAIN_FAMILIES,16),
        ('unseen_automaton_16',7304,args.ood,('finite_automaton',),16),
        ('unseen_automaton_32',7305,args.ood32,('finite_automaton',),32)):
        x,y,yp,h=_examples(seed,n,fam,states,nonoverlap)
        arrays[key]=(add_partial_plan(x,yp),y,yp,h)
    model=HybridStudent();opt=torch.optim.AdamW(model.parameters(),lr=args.lr,weight_decay=1e-4)
    x,y,_,_=arrays['train']; xs=torch.from_numpy(x);ys=torch.from_numpy(y)
    vc=np.bincount(y,minlength=9).astype(np.float32)
    weights=torch.from_numpy((len(y)/(9*np.maximum(vc,1))).astype(np.float32))
    lossfn=nn.CrossEntropyLoss(weight=weights)
    best=-1;best_state=None;history=[]
    for ep in range(args.epochs):
        model.train();idx=torch.randperm(len(xs));losses=[]
        for batch in idx.split(args.batch):
            opt.zero_grad();loss=lossfn(model(xs[batch]),ys[batch]);loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),3);opt.step();losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            vx,vy,_,_=arrays['valid']
            acc=float((model(torch.from_numpy(vx)).argmax(1)==torch.from_numpy(vy)).float().mean())
        if acc>best:
            best=acc;best_state={k:v.detach().clone() for k,v in model.state_dict().items()}
        history.append({'epoch':ep+1,'loss':round(float(np.mean(losses)),5),'validation_accuracy':round(acc,5)})
    model.load_state_dict(best_state);model.eval()
    metrics={}
    for key in ('in_family','unseen_automaton_16','unseen_automaton_32'):
        x,y,yp,_=arrays[key]
        with torch.no_grad():
            prob=torch.softmax(model(torch.from_numpy(x)),dim=1).numpy()
        pred=prob.argmax(1);conf=prob.max(1)
        metrics[key]={"n":int(len(y)),"accuracy":float(np.mean(pred==y)),
                      "symbolic_partial_baseline":float(np.mean(yp==y)),
                      "confident_0_8_coverage":float(np.mean(conf>=.8)),
                      "confident_0_8_accuracy":float(np.mean(pred[conf>=.8]==y[conf>=.8])) if (conf>=.8).any() else None,
                      "predicted_refusal_rate":float(np.mean(pred==8))}
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    buf=io.BytesIO();np.savez_compressed(buf,**{k:v.detach().numpy() for k,v in model.state_dict().items()})
    raw=buf.getvalue();(output/'hybrid_student.npz').write_bytes(raw)
    manifest={'schema':'ifs.pgt002.hybrid.v1','architecture':'29-96-64-9-gelu-v1',
              'input_semantics':'partial-20-plus-exact-partial-mask-onehot-9',
              'weights_sha256':hashlib.sha256(raw).hexdigest(),'seed':args.seed,
              'train_worlds':args.train,'epochs':args.epochs,'training_families':list(TRAIN_FAMILIES),
              'heldout_family':'finite_automaton','receiver_exact_check':'mandatory','algorithm':'adamw-crossentropy'}
    manifest['manifest_digest']=sha(manifest)
    (output/'hybrid-manifest.json').write_bytes(canonical(manifest))
    report={'metrics':metrics,'artifact_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
            'validation_best':best,'duration_s':round(time.monotonic()-started,3),'history':history}
    (output/'hybrid-report.json').write_bytes(canonical(report))
    print(json.dumps({k:v for k,v in report.items() if k!='history'},indent=2))
    return report

def restore(directory:Path):
    p=Path(directory);meta=json.loads((p/'hybrid-manifest.json').read_bytes())
    digest=meta.pop('manifest_digest')
    if sha(meta)!=digest or meta['architecture']!='29-96-64-9-gelu-v1' or meta['input_semantics']!='partial-20-plus-exact-partial-mask-onehot-9':
        raise ValueError('wrong hybrid policy')
    raw=(p/'hybrid_student.npz').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['weights_sha256']:
        raise ValueError('invalid hybrid weights identity')
    model=HybridStudent()
    with np.load(io.BytesIO(raw),allow_pickle=False) as data:
        if set(data.files)!=set(model.state_dict()):raise ValueError('model inventory invalid')
        state={}
        for k,v in model.state_dict().items():
            a=data[k]
            if a.dtype!=np.float32 or a.shape!=tuple(v.shape) or not np.isfinite(a).all():
                raise ValueError('unsafe hybrid tensor')
            state[k]=torch.from_numpy(a.copy())
    model.load_state_dict(state);model.eval()
    return model,digest

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--train',type=int,default=14000);p.add_argument('--valid',type=int,default=2000)
    p.add_argument('--test',type=int,default=2000);p.add_argument('--ood',type=int,default=1800)
    p.add_argument('--ood32',type=int,default=1200);p.add_argument('--epochs',type=int,default=30)
    p.add_argument('--seed',type=int,default=168);p.add_argument('--batch',type=int,default=384)
    p.add_argument('--lr',type=float,default=.002);p.add_argument('--output',default='results-pgt002')
    args=p.parse_args();train(args)
