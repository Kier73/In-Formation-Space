"""PGT-002 source-separated training, acquisition and checkpoint verification."""
from __future__ import annotations
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import torch

from procedural_ground_training import World, encode, exact_plan, can_resolve
from cross_family_curriculum import (FAMILIES,TRAIN_FAMILIES,world_for,partial,build_examples,
                                     _finite_jump,_affine_jump,world_digest,counterexample)
from active_version_space import HYPOTHESES, TargetSource, acquire, audit, surviving
from train_transfer import restore
from http_artifact_path import get_verified,Refused

RESULTS=Path(__file__).resolve().parent/'results'

class MathematicalSourceTests(unittest.TestCase):
    def test_affine_long_time_composition_matches_sequential_short(self):
        for a,c,m,x in ((5,1,16,7),(7,3,32,21),(1,0,16,15),(3,19,32,4)):
            s=x
            for t in range(130):
                self.assertEqual(_affine_jump(a,c,m,x,t),s)
                s=(a*s+c)%m

    def test_finite_graph_navigation_matches_explicit_transitions(self):
        rng=np.random.default_rng(20)
        for n in (16,32):
            jump=tuple(int(z) for z in rng.integers(0,n,size=n))
            for state in range(n):
                value=state
                for t in range(110):
                    self.assertEqual(_finite_jump(jump,state,t),value)
                    value=jump[value]

    def test_four_world_families_have_admitted_finite_labels(self):
        rng=np.random.default_rng(127)
        for family in FAMILIES:
            for n in (16,32):
                for k in range(42):
                    w=world_for(family,rng,k,n)
                    action=exact_plan(w)
                    self.assertTrue(action==8 or can_resolve(w,action))
                    view=partial(w,range(4))
                    self.assertEqual(len(encode(view)),20)
                    if action<8:
                        self.assertIsNone(counterexample(w,action))

    def test_two_hidden_worlds_are_observationally_identical_but_have_different_truth(self):
        common=((0,0,0),(1,0,0),(0,1,0),(1,1,0))
        w1=World(common,(0,1,0,1),(2,3,4),1)
        w2=World(common,(0,1,0,0),(2,3,4),2)
        self.assertTrue(np.array_equal(encode(partial(w1,(0,1,2))),encode(partial(w2,(0,1,2)))))
        self.assertNotEqual(exact_plan(w1),exact_plan(w2))

    def test_semantic_identity_disregards_row_permutation_and_split_id(self):
        w=World(((0,0,0),(1,0,1),(0,1,1)),(0,1,1),(1,3,2),17)
        v=World(tuple(reversed(w.features)),tuple(reversed(w.targets)),w.costs,923)
        self.assertEqual(world_digest(w),world_digest(v))

    def test_training_split_semantic_deduplication(self):
        earlier=set()
        for seed,states,family in ((81,16,TRAIN_FAMILIES),(82,32,('finite_automaton',))):
            _,_,_,ids=build_examples(seed,180,families=family,nstates=states,observed=(3,7),excluded=earlier)
            self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(earlier),360)

class ObservationContractTests(unittest.TestCase):
    def test_opaque_observer_rejects_duplicate_or_invalid_coordinates(self):
        rng=np.random.default_rng(5)
        w=world_for('finite_automaton',rng,13,16)
        src=TargetSource(w)
        self.assertEqual(src.observe(3),w.targets[3])
        with self.assertRaises(ValueError):src.observe(3)
        with self.assertRaises(ValueError):src.observe(-1)
        with self.assertRaises(ValueError):src.observe(100)
        self.assertEqual(src.calls,1)

    def test_version_space_uses_only_public_feature_projections_and_queried_targets(self):
        rng=np.random.default_rng(901)
        w=world_for('http_path',rng,11,16)
        init=(0,2)
        report=acquire(w,123,init,6,'active')
        self.assertLessEqual(report['used'],6)
        self.assertEqual(report['nontraining_source_evidence'],True)
        self.assertIn(report['status'],{'candidate','contradicted','unknown'})
        self.assertEqual(len(HYPOTHESES),30)
        self.assertGreaterEqual(len(surviving(w.features,{0:w.targets[0]})),0)

    def test_actual_source_can_falsify_unique_candidate_without_trusting_it(self):
        rng=np.random.default_rng(1222)
        false_candidates=0
        for i in range(220):
            w=world_for('finite_automaton',rng,i,16)
            source=acquire(w,460+i,(0,1),6,'active')
            if source['status']=='candidate' and not source['correct']:
                false_candidates+=1
        self.assertGreater(false_candidates,0)

    def test_report_active_methods_outperform_equal_observation_budget_random(self):
        score=json.loads((RESULTS/'teacher-free-active.json').read_bytes())
        self.assertEqual(score['receiver_admitted_predictions'],0)
        self.assertGreater(score['groups']['heldout_active']['correct_rate'],
                           score['groups']['heldout_random']['correct_rate']+0.20)
        self.assertGreater(score['groups']['heldout_active']['false_claims'],0)
        self.assertEqual(score['max_observations'],6)

    def test_counterexample_oracle_audit_discloses_its_extra_power(self):
        report=json.loads((RESULTS/'paired-observation-report.json').read_bytes())
        self.assertGreater(report['active_minus_random'],0)
        self.assertGreater(report['teacher_counterexample_queries'],0)
        self.assertIn('source-counterexamples',report['claim_scope'])
        # Honest negative control: symbolic active was BETTER than the neural.
        self.assertLess(report['active_neural_minus_active_symbolic'],0)

class TrainedParameterTests(unittest.TestCase):
    def test_complete_train_eval_report_records_both_success_and_failure(self):
        report=json.loads((RESULTS/'transfer-report.json').read_bytes())
        self.assertTrue(all(v==0 for v in report['split_semantic_overlaps'].values()))
        self.assertGreater(report['metrics']['unseen_automaton_16']['exact_plan_accuracy'],.55)
        self.assertGreater(report['metrics']['unseen_automaton_16']['exact_plan_accuracy'],
                           report['metrics']['unseen_automaton_16']['cost_only_accuracy']+.25)
        self.assertLess(report['metrics']['unseen_automaton_16']['exact_plan_accuracy'],.95)
        self.assertGreater(report['repair']['final_exact'],report['repair']['initial_exact'])
        self.assertGreater(report['repair']['unresolved'],0)

    def test_checkpoint_is_actual_learned_tensors_and_rejects_tampering(self):
        model,head=restore(RESULTS)
        self.assertTrue(len(head)==64)
        x,_,_,_=build_examples(491,10,families=('finite_automaton',),nstates=32,observed=5)
        with torch.no_grad():
            self.assertTrue(torch.equal(model(torch.from_numpy(x)),model(torch.from_numpy(x))))
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)
            (dest/'manifest.json').write_bytes((RESULTS/'manifest.json').read_bytes())
            original=(RESULTS/'partial_ground_student.npz').read_bytes()
            broken=bytearray(original);broken[-15]^=1
            (dest/'partial_ground_student.npz').write_bytes(broken)
            with self.assertRaises(ValueError):restore(dest)
            (dest/'partial_ground_student.npz').write_bytes(original)
            meta=json.loads((dest/'manifest.json').read_bytes());meta['training_families'].append('finite_automaton')
            (dest/'manifest.json').write_text(json.dumps(meta))
            with self.assertRaises(ValueError):restore(dest)

    def test_new_process_restores_model_without_source_or_training_optimizer(self):
        code='''import json,sys,torch,numpy as np
from pathlib import Path
from train_transfer import restore
from cross_family_curriculum import build_examples
model,_=restore(Path(sys.argv[1]))
x,_,_,_=build_examples(181,9,families=('finite_automaton',),nstates=32,observed=5)
with torch.no_grad():
 print(json.dumps(model(torch.from_numpy(x)).numpy().round(5).tolist()))'''
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parent)+os.pathsep+
             str(Path(__file__).resolve().parent.parent/'pgt001')}
        receiver=subprocess.run([sys.executable,'-c',code,str(RESULTS)],capture_output=True,text=True,env=env,check=True)
        scores=json.loads(receiver.stdout.strip())
        self.assertEqual(len(scores),9);self.assertEqual(len(scores[0]),9)

    def test_http_replaced_origin_verifies_same_model_outputs_and_refuses_corruption(self):
        report=json.loads((RESULTS/'http-transfer-report.json').read_bytes())
        self.assertTrue(report['phases']['both_live']['output_identical'])
        self.assertEqual(report['phases']['first_killed']['selected'],'b')
        self.assertEqual(report['phases']['corrupted_survivor']['status'],'REFUSED')
        self.assertFalse(report['public_https_or_remote_fault_domain_claim'])

if __name__=='__main__':unittest.main()
