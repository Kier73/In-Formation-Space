"""COG-008: finite real-PyBot observational membership, not equivalence proof.

The externally checked out pinned PyBot runs its own observe/propose/arbiter
runtime. Its replies are retained with evidence witnesses. No PyBot source
internals are imported by the partial-state synthesizer, and no sampling of
finite responses is promoted to a universal law.
"""
from __future__ import annotations
import argparse
import importlib
import json
from pathlib import Path
import random
import subprocess
import sys
from cognitive_grounds import canonical, digest
from partial_observation import ObservedOracle, FrozenOracle

PYBOT_SHA='7d63c7fbebb44c7e466e5c8b5c1f341ab767929e'
ACTIONS=("hi, i'm Sam","what's my name?","actually, call me Alex",
         "my kettle is full of limescale, how do i get rid of it?",
         "how long does that take","thanks","hello","what about rice?")
CASES=(
    ("hi, i'm Sam","what's my name?"),
    ("hi, i'm Sam","actually, call me Alex","what's my name?"),
    ("my kettle is full of limescale, how do i get rid of it?","how long does that take"),
    ("hello","thanks"),
    ("what's my name?",),
    ("hi, i'm Sam","thanks","what's my name?"),
    ("my kettle is full of limescale, how do i get rid of it?","thanks","how long does that take"),
    ("hello","what about rice?"),
)


class PyBotMembership:
    alphabet=ACTIONS

    def __init__(self,root:Path):
        if not (root/'bot'/'runtime.py').is_file() or not (root/'pybot.py').is_file():
            raise ValueError('pinned source checkout missing')
        sha=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,
                           text=True,check=True,timeout=20).stdout.strip()
        if sha!=PYBOT_SHA:raise ValueError('PyBot checkout changed from pinned source commit')
        sys.path.insert(0,str(root.resolve()))
        self.runtime=importlib.import_module('bot.runtime')
        self.source_root=digest({'schema':'COG008/actual-PyBot-epoch/1','git':PYBOT_SHA,
                                 'runtime':'bot.runtime.turn','seed':18181,
                                 'alphabet':list(ACTIONS),'response':'module-and-actual-reply'})
        self.calls=0

    def query(self,actions):
        if len(actions)>64 or any(a not in ACTIONS for a in actions):
            raise ValueError('outside task contract')
        random.seed(18181)
        memory={};responses=[]
        for text in actions:
            result=self.runtime.turn(text,memory)
            response=result['reply']
            if not isinstance(response,str) or not response.strip():
                raise ValueError('source produced no eligible response')
            responses.append((result.get('module') or 'none',response))
        self.calls+=1
        return tuple(responses)


def collect(root:Path)->dict:
    source=PyBotMembership(root)
    recorded=ObservedOracle(source,max_queries=128)
    for case in CASES:recorded.query(case)
    # Re-execute one real oracle path to test source determinism under the pin.
    recorded.recheck(CASES[0])
    saved=recorded.document()
    reconstructed=FrozenOracle(saved,expected_head=saved['head'],expected_source_root=source.source_root)
    if any(reconstructed.query(c)!=recorded.query(c) for c in CASES):
        raise ValueError('source-free evidence reconstruction differs')
    assert reconstructed.external_calls==0
    core={'schema':'COG008/actual-PyBot-membership-collection/1','source_commit':PYBOT_SHA,
          'task_cases':[list(case) for case in CASES],
          'observation_ledger':saved,
          'epistemic_status':'actual finite source observations; no general PyBot equivalence',
          'source_free_replay_calls':0,
          'actual_pybot_source_calls':source.calls}
    return {**core,'digest':digest(core)}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--pybot-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--expected',type=Path)
    args=p.parse_args()
    result=collect(args.pybot_root)
    if args.expected is not None:
        expected=json.loads(args.expected.read_bytes())
        if canonical(expected)!=canonical(result):
            raise ValueError('independent real-PyBot membership responses changed')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(canonical(result))
    print(json.dumps({'git':PYBOT_SHA,'queries':len(result['task_cases']),
                      'actual_turns':sum(len(x) for x in result['task_cases']),
                      'ledger_head':result['observation_ledger']['head'],
                      'digest':result['digest'],
                      'independently_replayed':args.expected is not None},sort_keys=True))
