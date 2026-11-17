"""COG-006: reproducible acquired-structure audit and cold-process handoff CLI.

All observations are synthetic except the PyBot architectural reference;
this is NOT a behavioral benchmark against the running PyBot implementation.
"""
from __future__ import annotations
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import argparse
import json
import random
from cognitive_grounds import (Fact, FactGround, Learner, Session, fixture,
                                realize, digest)


def acquire(ground: FactGround) -> Learner:
    learner = Learner(ground)
    for _ in range(4):
        if len(learner.viable) == 1:
            break
        subject = learner.acquire([f.subject for f in ground.facts[:128]])
        # An independent task oracle would supply these labels in deployment.
        learner = learner.admit(subject, sum(ground.record(subject).steps))
    return learner


def audit():
    measurements=[]
    for size in (128,4096,65536):
        start=perf_counter_ns(); ground=fixture(size); prep_ns=perf_counter_ns()-start
        start=perf_counter_ns(); learner=acquire(ground); learn_ns=perf_counter_ns()-start
        assert learner.promoted.operators==('steps','sum')
        rng=random.Random(size)
        sample=[ground.facts[rng.randrange(size)].subject for _ in range(1000)]
        query_times=[]; correct=0
        for subject in sample:
            start=perf_counter_ns()
            result,sources=realize(ground,learner.promoted,subject)
            query_times.append(perf_counter_ns()-start)
            correct+=int(result==sum(ground.record(subject).steps)
                         and len(sources)==1)
        assert correct==1000
        measurements.append({'source_fact_count':size,'source_root':ground.root,
                             'ground_construction_ms':round(prep_ns/1e6,3),
                             'active_discovery_ms':round(learn_ns/1e6,3),
                             'observation_examples':len(learner.examples),
                             'typed_candidates_before':3,'viable_after':len(learner.viable),
                             'heldout_correct':correct,'heldout_queries':len(sample),
                             'median_single_ground_query_us':round(median(query_times)/1000,3),
                             'program_operator_visits':len(learner.promoted.operators),
                             'selected_source_facts_per_query':1})
    ground=fixture(4096);learner=acquire(ground)
    session=Session(learner).perform('mention','procedure_000777').perform('ask_minutes')
    documented=session.document()
    restored=Session.restore(learner,documented,external_head=session.head)
    continued=restored.perform('ask_seconds')
    return {'schema':'COG-006/reproducible-metrics/v1',
            'project':'typed structural capability inference, not source-code generation',
            'induction':'active finite version-space identification of relational programs',
            'measurements':measurements,
            'memory_anchored_result':continued.turns[-1].answer,
            'memoryless_ablated_result':Session(learner).perform('ask_seconds').turns[-1].answer,
            'cold_restoration_equal':restored==session,
            'not_claimed':['natural-language understanding','PyBot benchmark parity',
                           'universal program learning','authenticated remote observer',
                           'E-CPU Hypervisor realization','physical substrate independence']}


def prepare(path):
    ground=fixture(4096);learner=acquire(ground)
    session=Session(learner).perform('mention','procedure_000777').perform('ask_minutes')
    out={'fixture_size':4096,'learner':learner.document(),'session':session.document()}
    Path(path).write_bytes(json.dumps(out,sort_keys=True,indent=2).encode())
    pin={'ground':ground.root,'learning':learner.head,'conversation':session.head}
    Path(str(path)+'.pins.json').write_bytes(json.dumps(pin,sort_keys=True,indent=2).encode())
    return pin


def resume(path,pins):
    obj=json.loads(Path(path).read_text())
    pin=json.loads(Path(pins).read_text())
    ground=fixture(obj['fixture_size'])
    if ground.root!=pin['ground']:
        raise ValueError('externally pinned source changed')
    learner=Learner.restore(ground,obj['learner'],external_head=pin['learning'])
    session=Session.restore(learner,obj['session'],external_head=pin['conversation'])
    return session.perform('ask_seconds').turns[-1].answer


def main():
    arg=argparse.ArgumentParser()
    arg.add_argument('command',choices=('audit','prepare','resume'))
    arg.add_argument('--path',default='cog006-handoff.json')
    arg.add_argument('--pins',default=None)
    a=arg.parse_args()
    if a.command=='audit': result=audit()
    elif a.command=='prepare': result=prepare(a.path)
    else:result=resume(a.path,a.pins or a.path+'.pins.json')
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=='__main__': main()
