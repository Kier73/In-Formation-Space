"""COG-008 audit, source-epoch-pinned preparation, and cold recovery."""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
from cognitive_grounds import canonical, GroundRefused
from predictive_state import source_fixture, Teacher, conformance, minimality, ActiveMachineLearner
from partial_observation import ObservedOracle, fit_table, experimental_revision, checkpoint, recover


def audit():
    cases=[]
    for n,k,named in ((12,3,False),(32,8,False),(64,8,False),
                       (128,8,False),(16,4,True),(32,8,True)):
        g,l=source_fixture(n,k)
        source=Teacher(g,l,named=named);observer=ObservedOracle(source)
        first=fit_table(ActiveMachineLearner(observer))
        early_check=conformance(source,first)
        learning,machine,report=experimental_revision(observer)
        check=conformance(source,machine)
        snapshot=checkpoint(observer,learning,machine,report)
        restored,replay=recover(snapshot,expected_checkpoint_digest=snapshot['digest'],
                                expected_ledger_head=observer.head,expected_source_root=observer.source_root)
        assert restored.fingerprint==machine.fingerprint
        randomizer=random.Random(n*13+k*31+int(named))
        heldout=500
        correct=0
        for i in range(heldout):
            query=tuple(randomizer.choice(source.alphabet) for _ in range(randomizer.randrange(1,12)))
            correct+=int(machine.run(query)==source.query(query))
        if not (check.equivalent and minimality(source,machine) and correct==heldout and replay.external_calls==0):
            raise GroundRefused('independent synthetic benchmark refused learned Ground')
        cases.append({'subjects':n,'distinct_durations':k,'identity_required':named,
                      'source_states':check.source_states,'initial_candidate_states':len(first.representatives),
                      'initial_candidate_exact_conformance':early_check.equivalent,
                      'final_candidate_states':len(machine.representatives),
                      'counterexamples':report['counterexamples'],'revision_count':report['revisions'],
                      'membership_queries':report['membership_calls'],
                      'source_epoch':observer.source_root,
                      'evidence_head':observer.head,
                      'checkpoints':len(observer.witnesses),
                      'source_free_replay_calls':replay.external_calls,
                      'heldout_correct':correct,'heldout_count':heldout,
                      'independent_complete_model_audit':check.equivalent,
                      'independent_conformance_edges':check.checked_edges,
                      'independently_minimal':minimality(source,machine)})
    return {'schema':'COG008/partial-observer-synthetic-audit/1',
            'experiment':'unknown-preserving membership learning; complete model for audit only',
            'cases':cases,
            'observation_authentication':'no; hash chain with externally provided pins only',
            'native_ecpu_execution':'not performed',
            'source_pybot':'separate source-pinned hosted observation experiment'}


def prepare(path:Path):
    g,l=source_fixture(12,3);teacher=Teacher(g,l);observer=ObservedOracle(teacher)
    learning,machine,report=experimental_revision(observer)
    doc=checkpoint(observer,learning,machine,report)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(canonical(doc))
    print(json.dumps({'checkpoint_digest':doc['digest'],'ledger_head':observer.head,
                      'source_root':observer.source_root,'states':len(machine.representatives),
                      'status':'provisional_finitely_challenged'},sort_keys=True))


def resume(path:Path,pins:dict):
    doc=json.loads(path.read_bytes())
    model,replay=recover(doc,expected_checkpoint_digest=pins['checkpoint_digest'],
                         expected_ledger_head=pins['ledger_head'],expected_source_root=pins['source_root'])
    query=('mention:topic_0001','minutes')
    result=model.run(query)[-1]
    print(json.dumps({'checkpoint_digest':doc['digest'],
                      'response':list(result),'external_membership_calls':replay.external_calls,
                      'epistemic_status':doc['ground']['status'],
                      'source_free_reconstructed':True},sort_keys=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('audit','prepare','resume'))
    parser.add_argument('--path',type=Path)
    parser.add_argument('--pins')
    args=parser.parse_args()
    if args.command=='audit':print(json.dumps(audit(),indent=2,sort_keys=True))
    elif args.command=='prepare':
        if args.path is None:parser.error('--path required')
        prepare(args.path)
    else:
        if args.path is None or not args.pins:parser.error('resume needs --path and --pins')
        resume(args.path,json.loads(args.pins))
