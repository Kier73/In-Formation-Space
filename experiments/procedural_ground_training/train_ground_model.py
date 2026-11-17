"""Reproducible small-neural-model training and verified checkpoint export."""
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
from procedural_ground_training import SCHEMA, canonical, dataset, sha, make_world, encode, exact_plan, can_resolve

class GroundStudent(nn.Module):
    def __init__(self):
        super().__init__()
        self.phi=nn.Sequential(nn.Linear(20,96),nn.GELU(),nn.Linear(96,64),nn.GELU())
        self.head=nn.Linear(64,9)
    def forward(self,x):
        z=self.phi(x)
        return self.head(z)
    def embed(self,x):
        return self.phi(x)


def training(args):
    torch.manual_seed(args.seed)
    torch.set_num_threads(3)
    t0=time.monotonic()
    x,y,h=dataset(4001,args.train)
    xv,yv,hv=dataset(4002,args.valid)
    xt,yt,ht=dataset(4003,args.test)
    xo,yo,ho=dataset(4004,args.ood,nstates=32,extended=True)
    sets=[set(z) for z in (h,hv,ht,ho)]
    if any(sets[i]&sets[j] for i in range(4) for j in range(i+1,4)):
        raise RuntimeError('leaked identical Ground across splits')
    xs=torch.from_numpy(x);ys=torch.from_numpy(y)
    v=torch.from_numpy(xv); vy=torch.from_numpy(yv)
    model=GroundStudent()
    opt=torch.optim.AdamW(model.parameters(),lr=args.lr,weight_decay=1e-4)
    # Different actions have highly unequal base rates; train against explicit class balance.
    weights=np.bincount(y,minlength=9).astype(np.float64)
    weight=torch.from_numpy((len(y)/(9*np.maximum(weights,1))).astype(np.float32))
    loss_fn=nn.CrossEntropyLoss(weight=weight)
    best=None; best_score=-1.;history=[]
    for ep in range(args.epochs):
        model.train();rng=torch.randperm(len(xs)); losses=[]
        for inds in rng.split(args.batch):
            opt.zero_grad();logits=model(xs[inds]);loss=loss_fn(logits,ys[inds]);loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),3.0)
            opt.step();losses.append(float(loss))
        model.eval()
        with torch.no_grad():
            pred=model(v).argmax(1)
            correct=float((pred==vy).float().mean().item())
        history.append({'epoch':ep+1,'train_loss':round(sum(losses)/len(losses),6),'validation_accuracy':round(correct,6)})
        if correct>best_score:
            best_score=correct;best={k:val.detach().cpu().clone() for k,val in model.state_dict().items()}
    assert best is not None
    model.load_state_dict(best);model.eval()
    def metrics(inp, labels, seed, *,states=16,ext=False):
        with torch.no_grad():
            proba=torch.softmax(model(torch.from_numpy(inp)),dim=1).cpu().numpy()
        pred=proba.argmax(1)
        wrong=int((pred!=labels).sum())
        # Rebuild exact generated Worlds independently and compare proposed plan to source table.
        rng=np.random.default_rng(seed)
        unsafe=0; abstained=0;needless_cost=0;full_mask_cost=0;oracle_cost=0;selected_cost=0;ready=0
        for i,(action,ref) in enumerate(zip(pred,labels)):
            w=make_world(rng,seed*10000000+i,nstates=states,extended=ext)
            if exact_plan(w)!=ref or not np.array_equal(encode(w),inp[i]):
                raise RuntimeError('training evaluator world reconstruction changed')
            if action!=8 and not can_resolve(w,int(action)):
                unsafe+=1
            if action==8 and ref!=8:
                abstained+=1
            if ref==0: ready+=1
            if ref!=8:
                cost=sum(c for j,c in enumerate(w.costs) if ref&(1<<j))
                oracle_cost+=cost
                full_mask_cost+=sum(w.costs)
            if action!=8:
                selected_cost+=sum(c for j,c in enumerate(w.costs) if action&(1<<j))
        return {'size':len(labels),'accuracy':round(1-wrong/len(labels),5),
                'wrong':wrong,'unsafe_nonrefusal':unsafe,'false_refusals':abstained,
                'ready_examples':ready,'oracle_selected_symbolic_cost':oracle_cost,
                'full_measurement_symbolic_cost':full_mask_cost,
                'student_selected_symbolic_cost_unverified':selected_cost,
                'confusion':[[int(((pred==a)&(labels==b)).sum()) for b in range(9)] for a in range(9)]}
    train_metrics=metrics(xt,yt,4003)
    ood_metrics=metrics(xo,yo,4004,states=32,ext=True)
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    tensors={k:v.detach().cpu().numpy() for k,v in model.state_dict().items()}
    buffer=io.BytesIO()
    np.savez_compressed(buffer,**tensors)
    raw=buffer.getvalue()
    (output/'ground_student.npz').write_bytes(raw)
    weights_sha=hashlib.sha256(raw).hexdigest()
    policy={ 'schema':SCHEMA+'.checkpoint', 'architecture':'20-96-64-9-gelu-v1',
        'weights_sha256':weights_sha,'input_encoder':'pairwise-difference-histogram-20-v1',
        'output_semantics':'mask-0..7-or-refuse-8-exact-plan-recheck-required',
        'train_worlds':args.train,'train_source_seed':4001,'validation_source_seed':4002,
        'training_algorithm':{'torch':str(torch.__version__),'epochs':args.epochs,
             'seed':args.seed,'lr':args.lr,'batch':args.batch},
        'ground_oracle_contract':'finite-exhaustive-subset-min-cost-v1',
        'checkpoint_untrusted_without_receiver_policy':True }
    policy['manifest_digest']=sha(policy)
    (output/'manifest.json').write_bytes(canonical(policy))
    report={'schema':SCHEMA+'.report','source':'pure-procedural-finite-ground',
        'heldout_16':train_metrics,'heldout_32_ood':ood_metrics,'best_validation_accuracy':round(best_score,5),
        'training_duration_s':round(time.monotonic()-t0,3),
        'split_identical_world_overlap':0,'semantic_manifest_digest':policy['manifest_digest'],
        'training_history':history,'training_is_real_optimization':True,
        'unsafe_student_proposals_not_admitted':train_metrics['unsafe_nonrefusal']+ood_metrics['unsafe_nonrefusal']}
    (output/'training-report.json').write_bytes(canonical(report))
    print(json.dumps({k:v for k,v in report.items() if k!='training_history'},indent=2))
    return report


def restore(directory:Path):
    meta=json.loads((directory/'manifest.json').read_bytes())
    require=meta.pop('manifest_digest')
    if sha(meta)!=require:
        raise ValueError('checkpoint manifest changed')
    if meta['architecture']!='20-96-64-9-gelu-v1' or meta['input_encoder']!='pairwise-difference-histogram-20-v1':
        raise ValueError('unadmitted architecture or encoder')
    raw=(directory/'ground_student.npz').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['weights_sha256']:
        raise ValueError('checkpoint weights altered')
    with np.load(io.BytesIO(raw),allow_pickle=False) as weights:
        model=GroundStudent()
        expected=set(model.state_dict());actual=set(weights.files)
        if expected!=actual:
            raise ValueError('invalid learned weight keys')
        state={}
        for key,template in model.state_dict().items():
            arr=weights[key]
            if arr.shape!=tuple(template.shape) or arr.dtype!=np.float32 or not np.isfinite(arr).all():
                raise ValueError('invalid learned tensor shape, dtype or values')
            state[key]=torch.from_numpy(arr.copy())
        model.load_state_dict(state);model.eval()
    return model,require


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',default='results');p.add_argument('--train',type=int,default=18000)
    p.add_argument('--valid',type=int,default=2500);p.add_argument('--test',type=int,default=2000)
    p.add_argument('--ood',type=int,default=1500);p.add_argument('--epochs',type=int,default=40)
    p.add_argument('--batch',type=int,default=384);p.add_argument('--lr',type=float,default=0.002)
    p.add_argument('--seed',type=int,default=73)
    args=p.parse_args();training(args)

if __name__=='__main__':main()
