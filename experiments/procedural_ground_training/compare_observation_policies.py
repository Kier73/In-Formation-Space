"""PGT-002: paired active-counterexample versus uniform state observation.

An independent finite teacher holds a complete Ground table. Active policy
may query its candidate-plan verifier for counterexample state coordinates,
but no model receives the teacher's exact answer label. The random control
receives the same number of full state observations.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from procedural_ground_training import encode, exact_plan, can_resolve, canonical
from cross_family_curriculum import world_for, partial, counterexample
from train_transfer import restore


def action(model,full,ids):
    inp=encode(partial(full,ids))
    with torch.no_grad():
        return int(model(torch.from_numpy(inp[None,:])).argmax(1).item())


def run(output:Path,root:Path,*,cases=500,extra=4,seed=7351):
    model,head=restore(root)
    rng=np.random.default_rng(seed)
    results=[]
    teacher_challenge_calls=0
    for i in range(cases):
        n=16 if i%2==0 else 32
        world=world_for('finite_automaton',rng,seed*10**7+i,n)
        initial=list(int(v) for v in rng.choice(n,4,replace=False))
        observed={name:list(initial) for name in ('counterexample','random','symbolic_counterexample','symbolic_random')}
        truth=exact_plan(world)
        before=action(model,world,initial)
        for kind in ('counterexample','random','symbolic_counterexample','symbolic_random'):
            ids=observed[kind]
            for _ in range(extra):
                choices=[j for j in range(n) if j not in ids]
                if not choices:break
                current=exact_plan(partial(world,ids)) if kind.startswith('symbolic') else action(model,world,ids)
                if kind in ('counterexample','symbolic_counterexample') and current!=8:
                    teacher_challenge_calls+=1
                    witness=counterexample(world,current)
                    if witness is not None:
                        target=next((j for j in witness if j not in ids),None)
                    else:
                        target=None
                else:target=None
                if target is None:
                    target=int(rng.choice(choices))
                ids.append(target)
        active=action(model,world,observed['counterexample'])
        random=action(model,world,observed['random'])
        active_symbolic=exact_plan(partial(world,observed['symbolic_counterexample']))
        random_symbolic=exact_plan(partial(world,observed['symbolic_random']))
        observed_partial=exact_plan(partial(world,initial))
        results.append({'truth':truth,'before':before,'partial':observed_partial,
                        'active':active,'random':random,
                        'active_symbolic':active_symbolic,'random_symbolic':random_symbolic})
    def metrics(field):
        count=sum(row[field]==row['truth'] for row in results)
        return {'exact':count,'exact_rate':round(count/cases,5)}
    # Reconstruct only exact-match counts here; full safety tracked in other tests.
    score={k:metrics(k) for k in ('before','partial','active','random','active_symbolic','random_symbolic')}
    report={'schema':'ifs.pgt002.paired-observation-control.v1',
            'model_manifest_digest':head,'cases':cases,'initial_observed':4,
            'additional_observed_per_arm':extra,
            'heldout_source':'finite_automaton-16-and-32-alternating',
            'score':score,'active_minus_random':score['active']['exact']-score['random']['exact'],
            'active_neural_minus_active_symbolic':score['active']['exact']-score['active_symbolic']['exact'],
            'teacher_counterexample_queries':teacher_challenge_calls,
            'claim_scope':'finite_reference_teacher_needed_for_source-counterexamples'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(canonical(report))
    print(json.dumps(report,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,default=Path('results'))
    p.add_argument('--output',type=Path,default=Path('results/paired-observation-report.json'))
    p.add_argument('--cases',type=int,default=500);p.add_argument('--extra',type=int,default=4)
    args=p.parse_args();run(args.output,args.model_dir,cases=args.cases,extra=args.extra)
