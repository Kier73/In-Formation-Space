"""PGT-003: train a neural proposer on finite costed experiment decisions.

Teacher decisions are exact finite Bayes-optimal proposals within a bounded
hypothesis language; source/target truth is not made available at inference.
"""
from __future__ import annotations
import argparse,hashlib,io,json,time
from pathlib import Path
import numpy as np
import torch
from torch import nn
from decision_experiment import (ALL,N,context,indices,features,sampled_initial,
                                 terminal,optimal_action,greedy_action,rollout,canonical,fingerprint)

SCHEMA='ifs.pgt003.neural-observation-proposals.v1'

class ObserverPolicy(nn.Module):
    """Shared action scorer to avoid hard-wiring a privileged coordinate."""
    def __init__(self):
        super().__init__()
        self.scorer=nn.Sequential(nn.Linear(15,64),nn.GELU(),nn.Linear(64,48),
                                   nn.GELU(),nn.Linear(48,1))
    def forward(self,inputs):
        return self.scorer(inputs).squeeze(-1)


def make_data(seed,n,train_distribution=True,history_max=3):
    rng=np.random.default_rng(seed); xx=[];yy=[];contexts=[]
    for k in range(n):
        ctx=context(rng,training=train_distribution)
        truth=int(rng.choice(N,p=np.asarray(ctx.weights)/sum(ctx.weights)))
        mask,used,observed=sampled_initial(rng,truth,ctx,history_max)
        if terminal(ctx,mask):continue
        cost,q=optimal_action(ctx,mask,used,4)
        if q is None:continue
        x=features(ctx,mask,used)
        xx.append(x);yy.append(q)
        contexts.append((ctx,truth,mask,used,observed))
    return np.stack(xx),np.asarray(yy,dtype=np.int64),contexts


def action_mask(x):
    # Used observations must never be queried again; zero information also blocked.
    return (x[:,:,4]>.5)|(x[:,:,1]<1e-7)


def train(train_n=6000,valid_n=1200,epochs=18,seed=17,output='results'):
    torch.manual_seed(seed);torch.set_num_threads(3)
    start=time.monotonic()
    x,y,_=make_data(9031,train_n)
    vx,vy,_=make_data(9032,valid_n)
    model=ObserverPolicy();optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.0001)
    train_x=torch.from_numpy(x); train_y=torch.from_numpy(y)
    vx=torch.from_numpy(vx)
    best=-1.;best_state=None;hist=[]
    for epoch in range(epochs):
        model.train();perm=torch.randperm(len(x));losses=[]
        for batch in perm.split(256):
            scores=model(train_x[batch]);scores=scores.masked_fill(torch.from_numpy(action_mask(x[batch])),-1e7)
            loss=nn.functional.cross_entropy(scores,train_y[batch]);optimizer.zero_grad();loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),4.);optimizer.step();losses.append(float(loss))
        model.eval()
        with torch.no_grad():
            predicted=model(vx).masked_fill(torch.from_numpy(action_mask(vx.numpy())),-1e7).argmax(1).numpy()
        acc=float((predicted==vy).mean());hist.append({'epoch':epoch+1,'loss':round(float(np.mean(losses)),5),'valid_accuracy':round(acc,5)})
        if acc>best:best=acc;best_state={k:v.detach().clone() for k,v in model.state_dict().items()}
    model.load_state_dict(best_state);model.eval()
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    handle=io.BytesIO();np.savez_compressed(handle,**{k:v.detach().numpy() for k,v in model.state_dict().items()})
    raw=handle.getvalue();(out/'observer_student.npz').write_bytes(raw)
    manifest={'schema':SCHEMA+'.manifest','architecture':'shared-action-15-64-48-1-gelu',
              'weights_sha256':hashlib.sha256(raw).hexdigest(),
              'teacher':'exact-4-step-costed-bayesian-finite-query-decision-tree',
              'training_examples':len(x),'validation_examples':len(vx),'epoch_best':hist[int(np.argmax([p['valid_accuracy'] for p in hist]))]['epoch'],
              'training_seed':seed,'data_seeds':[9031,9032],
              'hypothesis_count':N,'hypothesis_sha256':fingerprint([list(v) for v in __import__('decision_experiment').H.tolist()]),
              'safety':'advisory-only-never-admit-hypothesis-implied-output'}
    manifest['manifest_digest']=fingerprint(manifest)
    (out/'manifest.json').write_bytes(canonical(manifest))
    report={'schema':SCHEMA+'.training','validation_accuracy':best,'history':hist,'training_duration_s':round(time.monotonic()-start,3),
            'parameter_count':sum(p.numel() for p in model.parameters()),'model_bytes':len(raw)}
    (out/'train-report.json').write_bytes(canonical(report))
    return model,report


def restore(output='results'):
    p=Path(output);m=json.loads((p/'manifest.json').read_bytes())
    digest=m.pop('manifest_digest',None)
    if digest!=fingerprint(m) or m['architecture']!='shared-action-15-64-48-1-gelu' or m['hypothesis_sha256']!=fingerprint([list(v) for v in __import__('decision_experiment').H.tolist()]):
        raise ValueError('model manifest identity mismatch')
    raw=(p/'observer_student.npz').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=m['weights_sha256']:raise ValueError('model weights integrity mismatch')
    model=ObserverPolicy()
    with np.load(io.BytesIO(raw),allow_pickle=False) as data:
        if set(data.files)!=set(model.state_dict()):raise ValueError('neural weight inventory changed')
        state={}
        for name,ref in model.state_dict().items():
            value=data[name]
            if value.dtype!=np.float32 or value.shape!=tuple(ref.shape) or not np.isfinite(value).all():raise ValueError('weight tensor invalid')
            state[name]=torch.from_numpy(value.copy())
    model.load_state_dict(state);model.eval();return model,m


def propose(model,ctx,mask,used):
    if terminal(ctx,mask):return None
    x=features(ctx,mask,used)
    with torch.no_grad():
        scores=model(torch.from_numpy(x[None])).squeeze(0).numpy()
    scores[action_mask(x[None])[0]]=-float('inf')
    if not np.isfinite(scores).any():return None
    return int(scores.argmax())


def benchmark(model,seed=9012,cases=1200,test_distribution=False):
    rng=np.random.default_rng(seed)
    methods=('neural','gain','disagreement','direct','oracle')
    totals={z:{'cost':0,'queries':0,'wrong_candidates':0,'unresolved':0,'correct':0,'episodes':0} for z in methods}
    for k in range(cases):
        ctx=context(rng,training=not test_distribution)
        truth=int(rng.choice(N,p=np.asarray(ctx.weights)/sum(ctx.weights)))
        initial=sampled_initial(rng,truth,ctx,2)
        for method in methods:
            if method=='neural':chooser=lambda c,m,u:propose(model,c,m,u)
            elif method=='oracle':chooser=lambda c,m,u:optimal_action(c,m,u,4)[1]
            else:chooser=lambda c,m,u,method=method:greedy_action(c,m,u,method)
            record=rollout(ctx,truth,chooser,seed*10000+k,initial)
            row=totals[method];row['episodes']+=1;row['cost']+=record['cost'];row['queries']+=record['queries']
            row['correct']+=int(record['target_candidate']==record['target_true'])
            row['wrong_candidates']+=int(record['target_candidate'] is not None and record['target_candidate']!=record['target_true'])
            row['unresolved']+=int(record['target_candidate'] is None)
    return {k:{**v,'mean_cost':round(v['cost']/cases,4),'mean_queries':round(v['queries']/cases,4)} for k,v in totals.items()}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--train',type=int,default=6000);p.add_argument('--valid',type=int,default=1200);p.add_argument('--epochs',type=int,default=18);p.add_argument('--seed',type=int,default=17);p.add_argument('--output',default='results');p.add_argument('--cases',type=int,default=1200)
    a=p.parse_args();model,meta=train(a.train,a.valid,a.epochs,a.seed,a.output)
    report={'training':meta,'evaluation':{'heldout':benchmark(model,9012,a.cases),'prior_shift':benchmark(model,9013,a.cases,True)}}
    (Path(a.output)/'audit.json').write_bytes(canonical(report));print(json.dumps({k:v for k,v in report.items() if k!='training'},indent=2))
