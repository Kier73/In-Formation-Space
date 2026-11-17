"""COG-008: only membership probes during learning, independent checks after."""
import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cognitive_grounds import GroundRefused, digest
from predictive_state import (source_fixture, Teacher, ActiveMachineLearner,
                              conformance, minimality)
from partial_observation import (ObservedOracle, FrozenOracle, fit_table,
    challenge_plan, first_mismatch, experimental_revision, checkpoint, recover,
    resume_after_revision)


def observed(n=12,k=3,*,named=False):
    ground,learned=source_fixture(n,k)
    teacher=Teacher(ground,learned,named=named)
    return teacher,ObservedOracle(teacher)


class TestPartialPredictiveGround(unittest.TestCase):
    def test_without_global_equivalence_oracle_initial_guess_is_wrong(self):
        teacher,oracle=observed()
        learner=ActiveMachineLearner(oracle)
        early=fit_table(learner)
        self.assertEqual(len(early.representatives),4)
        self.assertEqual(first_mismatch(early,oracle,('mention:topic_0000','minutes','repeat')),
                         ('mention:topic_0000','minutes','repeat'))
        self.assertFalse(conformance(teacher,early).equivalent)

    def test_counterexample_revision_discovers_future_memory(self):
        teacher,oracle=observed(32,8)
        learner,model,report=experimental_revision(oracle)
        self.assertEqual(report['revisions'],1)
        self.assertEqual(len(model.representatives),25)
        self.assertEqual(report['status'],'provisional_finitely_challenged')
        self.assertEqual(report['unexplored_continuations'],'unknown')
        # The independent full reference is NEVER exposed to the learner.
        check=conformance(teacher,model)
        self.assertTrue(check.equivalent)
        self.assertTrue(minimality(teacher,model))

    def test_task_obligation_who_forces_identity_ground(self):
        teacher,oracle=observed(16,4,named=True)
        early=fit_table(ActiveMachineLearner(oracle))
        self.assertEqual(len(early.representatives),5)
        learner,model,report=experimental_revision(oracle)
        self.assertEqual(report['revisions'],2)
        self.assertEqual(len(model.representatives),49)
        self.assertTrue(conformance(teacher,model).equivalent)
        self.assertIn(('mention:topic_0004','who'),[tuple(p) for p in report['counterexamples']])

    def test_black_box_observation_recovery_does_not_call_source(self):
        teacher,oracle=observed(12,3)
        learner,model,report=experimental_revision(oracle)
        saved=checkpoint(oracle,learner,model,report)
        new,old= recover(json.loads(json.dumps(saved)),expected_checkpoint_digest=saved['digest'],
                         expected_ledger_head=oracle.head,expected_source_root=oracle.source_root)
        self.assertEqual(new.document(),model.document())
        self.assertEqual(old.external_calls,0)
        self.assertEqual(new.run(('mention:topic_0010','minutes','repeat')),
                         teacher.query(('mention:topic_0010','minutes','repeat')))
        with self.assertRaisesRegex(GroundRefused,'unobserved'):
            old.query(('mention:topic_0010','seconds','noise','seconds','repeat'))

    def test_hash_chain_altered_source_pin_and_rehashed_model_refused(self):
        _,oracle=observed(10,2)
        learner,model,report=experimental_revision(oracle)
        saved=checkpoint(oracle,learner,model,report)
        broken=copy.deepcopy(saved)
        broken['ledger']['witnesses'][3]['outputs']=[['invented'] for _ in broken['ledger']['witnesses'][3]['outputs']]
        # Rehashing wrapper cannot repair externally retained pins.
        broken['ledger']['digest']=digest({k:v for k,v in broken['ledger'].items() if k!='digest'})
        broken['digest']=digest({k:v for k,v in broken.items() if k!='digest'})
        with self.assertRaises(GroundRefused):
            recover(broken,expected_checkpoint_digest=saved['digest'],
                    expected_ledger_head=oracle.head,expected_source_root=oracle.source_root)
        with self.assertRaises(GroundRefused):
            recover(saved,expected_checkpoint_digest=saved['digest'],
                    expected_ledger_head='0'*64,expected_source_root=oracle.source_root)
        forged=copy.deepcopy(saved)
        forged['ground']['model']['emissions'][0][1]=['minutes',99999]
        forged['digest']=digest({k:v for k,v in forged.items() if k!='digest'})
        with self.assertRaises(GroundRefused):
            recover(forged,expected_checkpoint_digest=forged['digest'],
                    expected_ledger_head=oracle.head,expected_source_root=oracle.source_root)

    def test_recheck_detects_oracle_drift_inside_claimed_epoch(self):
        _,oracle=observed()
        word=('mention:topic_0000','minutes')
        oracle.query(word)
        self.assertTrue(oracle.recheck(word))
        original=oracle.source.query
        oracle.source.query=lambda actions: (('noted',),('minutes',999)) if tuple(actions)==word else original(actions)
        with self.assertRaisesRegex(GroundRefused,'changed'):
            oracle.recheck(word)
        self.assertEqual(len(oracle.witnesses),1)

    def test_replay_source_epoch_change_is_refused(self):
        teacher,oracle=observed(12,3)
        learner,model,report=experimental_revision(oracle)
        saved=checkpoint(oracle,learner,model,report)
        _,changed=observed(12,3,named=True)
        with self.assertRaisesRegex(GroundRefused,'incompatible'):
            recover(saved,expected_checkpoint_digest=saved['digest'],
                    expected_ledger_head=oracle.head,expected_source_root=changed.source_root)

    def test_symbolic_reinterpretation_needs_history_after_state_split(self):
        teacher,oracle=observed(16,4,named=True)
        early=fit_table(ActiveMachineLearner(oracle))
        _,new,_=experimental_revision(oracle)
        path=('mention:topic_0009','who')
        with self.assertRaisesRegex(GroundRefused,'history'):
            resume_after_revision(early,new,historical_actions=None)
        s,status=resume_after_revision(early,new,historical_actions=path)
        self.assertEqual(s,new.state_after(path))
        self.assertEqual(status,'reinterpreted_symbolic_history_without_external_execution')

    def test_bounded_failure_is_unknown_not_false_equivalence(self):
        _,oracle=observed(12,3)
        with self.assertRaisesRegex(GroundRefused,'budget'):
            experimental_revision(oracle,max_cycles=1)
        _,bounded=observed(12,3)
        bounded.limit=5
        with self.assertRaisesRegex(GroundRefused,'budget'):
            fit_table(ActiveMachineLearner(bounded))

    def test_challenge_is_not_automatically_global_proof(self):
        teacher,oracle=observed(16,4,named=True)
        _,machine,report=experimental_revision(oracle,max_challenges=15)
        self.assertEqual(report['status'],'provisional_finitely_challenged')
        self.assertEqual(report['unexplored_continuations'],'unknown')
        # The restricted probes can leave specific identities falsely merged.
        self.assertFalse(conformance(teacher,machine).equivalent)

    def test_cold_process_roundtrip_source_free_reconstruction(self):
        runner=Path(__file__).with_name('run_partial_observation.py')
        with tempfile.TemporaryDirectory() as d:
            saved=Path(d)/'checkpoint.json'
            first=subprocess.run([sys.executable,str(runner),'prepare','--path',str(saved)],
                                 text=True,capture_output=True,check=True,timeout=45)
            second=subprocess.run([sys.executable,str(runner),'resume','--path',str(saved),
                                  '--pins',first.stdout.strip()],
                                  text=True,capture_output=True,check=True,timeout=45)
            a=json.loads(first.stdout);b=json.loads(second.stdout)
            self.assertEqual(a['checkpoint_digest'],b['checkpoint_digest'])
            self.assertEqual(b['external_membership_calls'],0)
            self.assertEqual(b['response'],['minutes',24])
            self.assertEqual(b['epistemic_status'],'provisional_finitely_challenged')


if __name__=='__main__':unittest.main()
