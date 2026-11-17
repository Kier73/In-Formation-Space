"""Reproducible, source-pinned PyBot observations (separate from COG007 proof).

Only runs in a CI job which checks out the actual pinned external PyBot source.
It does NOT assert the COG007 symbolic learner reproduces PyBot, and outputs
no proof about untested messages. The generated transcript is a teacher-data
candidate for future program/representation learning.
"""
from __future__ import annotations
import argparse
import importlib
import json
from pathlib import Path
import random
import sys
from cognitive_grounds import canonical,digest

SOURCE_SHA='7d63c7fbebb44c7e466e5c8b5c1f341ab767929e'
CASES=(
    ('name-recall',('hi, i\'m Sam','what\'s my name?')),
    ('procedure-followup',('my kettle is full of limescale, how do i get rid of it?',
                           'how long does that take')),
    ('short-followup',('how long should i boil an egg?','what about rice?')),
    ('correction',('my name is Sam','actually, call me Alex','what\'s my name?')),
)


def collect(path:Path)->dict:
    if not (path/'bot'/'runtime.py').is_file() or not (path/'pybot.py').is_file():
        raise ValueError('actual pinned PyBot source checkout is required')
    sys.path.insert(0,str(path))
    runtime=importlib.import_module('bot.runtime')
    histories=[]
    for idx,(name,inputs) in enumerate(CASES):
        random.seed(111+idx)
        memory={};turns=[]
        for message in inputs:
            result=runtime.turn(message,memory)
            reply=result['reply'];chosen=result['module']
            if not isinstance(reply,str) or not reply.strip():
                raise ValueError('source bot did not return a reply')
            turns.append({'input':message,'output':reply,'module':chosen,
                          'candidate_count':len(result['candidates']),
                          'candidate_modules':[c['module'] for c in result['candidates']]})
        histories.append({'case':name,'turns':turns})
    core={'schema':'COG007/source-pinned-pybot-observations/1',
          'source_repo':'huggingface/pybot','source_commit':SOURCE_SHA,
          'runtime_contract':'bot.runtime.turn; stochastic sources seeded per case',
          'observed':histories,'scope':'finite public source behavior, not complete program semantics'}
    return {**core,'digest':digest(core)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pybot-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--expected',type=Path)
    args=parser.parse_args()
    result=collect(args.pybot_root)
    if args.expected:
        original=json.loads(args.expected.read_bytes())
        if canonical(result)!=canonical(original):
            raise ValueError('independent PyBot process did not reproduce pinned source observations')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(canonical(result))
    print(json.dumps({'source_commit':SOURCE_SHA,'cases':len(result['observed']),
                      'turns':sum(len(x['turns']) for x in result['observed']),
                      'observation_digest':result['digest'],
                      'independently_replayed':bool(args.expected)},sort_keys=True))

if __name__=='__main__':main()
