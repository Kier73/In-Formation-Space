"""PGT-002: train partial-observation advisory model across mathematical Ground families."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from procedural_ground_training import canonical, sha, exact_plan, encode
from cross_family_curriculum import (build_examples, world_for, sample_observations,
                                     TRAIN_FAMILIES, counterexample, proposed_action_status)

SCHEMA="ifs.pgt002.cross-family-partial-ground.v1"

class PartialGroundStudent(nn.Module):
    def __init__(self):
        super().__init__()
        self.phi=nn.Sequential(nn.Linear(20,96),nn.GELU(),nn.Linear(96,64),nn.GELU())
        self.head=nn.Linear(64,9)
    def forward(self,x):
        return self.head(self.phi(x))


def _examples(seed,n,families,states,excluded=None):
    return build_examples(seed,n,families=families,nstates=states,observed=(3,7),excluded=excluded)


def _eval(model,inp,labels,partial_labels):
    model.eval()
    with torch.no_grad():
        raw=torch.softmax(model(torch.from_numpy(inp)),dim=1).numpy()
    pred=raw.argmax(axis=1)
    conf=raw.max(axis=1)
    return {
        "n":int(len(labels)),"exact_plan_accuracy":float(np.mean(pred==labels)),
        "partial_naive_accuracy":float(np.mean(partial_labels==labels)),
        "cost_only_accuracy":None,
        "confidence_gate":{str(t):{"coverage":float(np.mean(conf>=t)),
                                  "exact_plan_accuracy":float(np.mean(pred[conf>=t]==labels[conf>=t])) if np.any(conf>=t) else None}
                           for t in (.7,.8,.9,.95)},
        "confusion":[[int(np.sum((pred==a)&(labels==b))) for b in range(9)] for a in range(9)],
        "predictions":pred,
    }


def _repair_audit(model, seed, n=160, nstates=16):
    """Counterexample-guided acquisition: all complete-domain checks are teacher-owned."""
    rng=np.random.default_rng(seed)
    results=[]
    for i in range(n):
        w=world_for('finite_automaton',rng,seed*10**7+i,nstates)
        part,obs=sample_observations(w,rng,4)
        seen=list(obs)
        original_view=encode(part)
        with torch.no_grad():
            original=int(model(torch.from_numpy(original_view[None,:])).argmax(1).item())
        cur=original; steps=0; added=[]
        while steps<12 and len(seen)<len(w.targets):
            if cur==exact_plan(w):
                break
            if 0<=cur<=7:
                witness=counterexample(w,cur)
                if witness is None:
                    # Sufficient but nonminimal: source has no refuting pair;
                    # continue only by sampling additional state evidence.
                    choices=[j for j in range(len(w.targets)) if j not in seen]
                    targets=[int(rng.choice(choices))] if choices else []
                else:
                    targets=[j for j in witness if j not in seen]
            else:
                choices=[j for j in range(len(w.targets)) if j not in seen]
                targets=[int(rng.choice(choices))] if choices else []
            if not targets:
                break
            seen.extend(targets);added.extend(targets)
            from cross_family_curriculum import partial
            part=partial(w,seen)
            with torch.no_grad():
                cur=int(model(torch.from_numpy(encode(part)[None,:])).argmax(1).item())
            steps+=1
        results.append({"initial_exact":original==exact_plan(w),"final_exact":cur==exact_plan(w),
                        "initial_safe":proposed_action_status(w,original)!='insufficient',
                        "final_safe":proposed_action_status(w,cur)!='insufficient',
                        "additional_state_observations":len(added),"final_observed_states":len(seen),
                        "unresolved_after_budget":cur!=exact_plan(w)})
    return {"n":n,"initial_exact":sum(z['initial_exact'] for z in results),
            "final_exact":sum(z['final_exact'] for z in results),
            "initial_safe":sum(z['initial_safe'] for z in results),
            "final_safe":sum(z['final_safe'] for z in results),
            "mean_additional_states":round(float(np.mean([z['additional_state_observations'] for z in results])),3),
            "max_additional_states":max(z['additional_state_observations'] for z in results),
            "unresolved":sum(z['unresolved_after_budget'] for z in results)}


def train(args):
    torch.manual_seed(args.seed);torch.set_num_threads(3)
    start=time.monotonic()
    nonoverlap=set()
    xs,ys,yps,h=_examples(7301,args.train,TRAIN_FAMILIES,16,nonoverlap)
    xv,yv,ypv,hv=_examples(7302,args.valid,TRAIN_FAMILIES,16,nonoverlap)
    xt,yt,ypt,ht=_examples(7303,args.test,TRAIN_FAMILIES,16,nonoverlap)
    xa,ya,ypa,ha=_examples(7304,args.ood,('finite_automaton',),16,nonoverlap)
    xb,yb,ypb,hb=_examples(7305,args.ood32,('finite_automaton',),32,nonoverlap)
    hashes=[set(x) for x in (h,hv,ht,ha,hb)]
    overlaps={f'{i}-{j}':len(hashes[i]&hashes[j]) for i in range(5) for j in range(i+1,5)}
    # Repeated finite models across splits are reported. The OOD family is
    # generator-heldout, not an assertion of disjoint mathematical functions.
    model=PartialGroundStudent();optim=torch.optim.AdamW(model.parameters(),lr=args.lr,weight_decay=1e-4)
    src=torch.from_numpy(xs);tar=torch.from_numpy(ys)
    count=np.bincount(ys,minlength=9)
    weight=torch.from_numpy((len(ys)/(9*np.maximum(count,1))).astype(np.float32))
    lossfn=nn.CrossEntropyLoss(weight=weight)
    best=-1.;state=None;hist=[]
    for epoch in range(args.epochs):
        model.train();shuff=torch.randperm(len(xs));losses=[]
        for batch in shuff.split(args.batch):
            optim.zero_grad();loss=lossfn(model(src[batch]),tar[batch]);loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),3);optim.step()
            losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            acc=float((model(torch.from_numpy(xv)).argmax(1)==torch.from_numpy(yv)).float().mean())
        hist.append({"epoch":epoch+1,"loss":round(float(np.mean(losses)),5),"validation":round(acc,5)})
        if acc>best:
            best=acc;state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
    model.load_state_dict(state);model.eval()
    sets={'in_family':(xt,yt,ypt),'unseen_automaton_16':(xa,ya,ypa),
          'unseen_automaton_32':(xb,yb,ypb)}
    metrics={}
    for name,(x,y,yp) in sets.items():
        report=_eval(model,x,y,yp)
        report.pop('predictions');metrics[name]=report

    # Cost-only control: masks all 16 relational bins; same training configuration.
    baseline=PartialGroundStudent();baseline.load_state_dict({k:v.detach().clone() for k,v in state.items()})
    base_optim=torch.optim.AdamW(baseline.parameters(),lr=args.lr,weight_decay=1e-4)
    masked=src.clone();masked[:,:16]=0
    baseline_best=-1.;baseline_state=None
    for epoch in range(args.epochs):
        baseline.train();shuff=torch.randperm(len(xs))
        for batch in shuff.split(args.batch):
            base_optim.zero_grad();loss=lossfn(baseline(masked[batch]),tar[batch]);loss.backward();base_optim.step()
        baseline.eval()
        with torch.no_grad():
            vv=torch.from_numpy(xv.copy());vv[:,:16]=0
            acc=float((baseline(vv).argmax(1)==torch.from_numpy(yv)).float().mean())
        if acc>baseline_best:
            baseline_best=acc;baseline_state={k:v.detach().clone() for k,v in baseline.state_dict().items()}
    baseline.load_state_dict(baseline_state)
    for name,(x,y,yp) in sets.items():
        t=torch.from_numpy(x.copy());t[:,:16]=0
        with torch.no_grad():
            pred=baseline(t).argmax(1).numpy()
        metrics[name]['cost_only_accuracy']=float(np.mean(pred==y))
    repair=_repair_audit(model,7306,args.repair)

    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    data={k:v.detach().numpy() for k,v in model.state_dict().items()}
    handle=io.BytesIO();np.savez_compressed(handle,**data);raw=handle.getvalue()
    (output/'partial_ground_student.npz').write_bytes(raw)
    manifestation={"schema":SCHEMA+'.checkpoint',"architecture":"20-96-64-9-gelu-v1",
                   "input_semantics":"partial-source-pair-histogram-20-v1",
                   "training_families":list(TRAIN_FAMILIES),"heldout_family":"finite_automaton",
                   "weights_sha256":hashlib.sha256(raw).hexdigest(),
                   "teacher":"complete-finite-ground-exhaustive-plan", "params_optimized":True,
                   "data_seeds":[7301,7302,7303,7304,7305,7306],
                   "training":{"seed":args.seed,"epochs":args.epochs,"lr":args.lr,
                               "batch":args.batch,"train":args.train,"valid":args.valid},
                   "safety":"advisory-only-exact-receiver-verification-required",
                   "provenance_scope":"synthetic-data-and-parameters-not-external-truth"}
    manifestation['manifest_digest']=sha(manifestation)
    (output/'manifest.json').write_bytes(canonical(manifestation))
    result={"schema":SCHEMA+'.audit',"metrics":metrics,"repair":repair,
            "train_families":list(TRAIN_FAMILIES),"ood_family":"finite_automaton",
            "split_semantic_overlaps":overlaps,"trained_parameters":sum(v.numel() for v in model.parameters()),
            "artifact_bytes":len(raw),"artifact_sha256":hashlib.sha256(raw).hexdigest(),
            "training_duration_s":round(time.monotonic()-start,3),
            "best_validation_accuracy":round(best,5),"epochs":hist,
            "authoritative_verification":"not_provided_by_neural_policy"}
    (output/'transfer-report.json').write_bytes(canonical(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ('epochs',)},indent=2))
    return result


def restore(directory:Path):
    p=Path(directory)
    policy=json.loads((p/'manifest.json').read_bytes())
    digest=policy.pop('manifest_digest')
    if sha(policy)!=digest or policy['architecture']!='20-96-64-9-gelu-v1' or policy['input_semantics']!='partial-source-pair-histogram-20-v1':
        raise ValueError('model manifest changed or unsupported')
    raw=(p/'partial_ground_student.npz').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=policy['weights_sha256']:
        raise ValueError('model artifact does not match pinned manifest')
    model=PartialGroundStudent()
    with np.load(io.BytesIO(raw),allow_pickle=False) as data:
        if set(data.files)!=set(model.state_dict()):
            raise ValueError('model tensor inventory is invalid')
        state={}
        for k,v in model.state_dict().items():
            a=data[k]
            if a.shape!=tuple(v.shape) or a.dtype!=np.float32 or not np.isfinite(a).all():
                raise ValueError('model tensor invalid')
            state[k]=torch.from_numpy(a.copy())
    model.load_state_dict(state);model.eval()
    return model,digest

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--train',type=int,default=14000)
    p.add_argument('--valid',type=int,default=2000)
    p.add_argument('--test',type=int,default=2000)
    p.add_argument('--ood',type=int,default=1800)
    p.add_argument('--ood32',type=int,default=1200)
    p.add_argument('--repair',type=int,default=160)
    p.add_argument('--epochs',type=int,default=30)
    p.add_argument('--seed',type=int,default=167)
    p.add_argument('--batch',type=int,default=384)
    p.add_argument('--lr',type=float,default=.002)
    p.add_argument('--output',default='results-pgt002')
    args=p.parse_args();train(args)
