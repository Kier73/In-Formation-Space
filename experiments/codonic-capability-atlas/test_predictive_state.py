"""COG-007: counterexample-guided predictive state, exact finite semantics."""
import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cognitive_grounds import Fact, FactGround, GroundRefused
from predictive_state import (Teacher, ActiveMachineLearner, Machine, conformance,
                              minimality, receipt, restore, source_fixture)


def fit(n=16,k=4,named=False):
    ground,learned=source_fixture(n,k)
    teacher=Teacher(ground,learned,named=named)
    learning=ActiveMachineLearner(teacher)
    model,check=learning.learn()
    return teacher,learning,model,check


class PredictiveCognitiveGroundTests(unittest.TestCase):
    def test_answer_relevance_quotient_is_exactly_minimal(self):
        t,learning,model,proof=fit(32,8,False)
        self.assertTrue(proof.equivalent)
        self.assertEqual(proof.source_states,97)
        self.assertEqual(len(model.representatives),25)
        self.assertTrue(minimality(t,model))
        self.assertGreater(len(learning.counterexamples),0)
        self.assertLess(len(model.representatives),proof.source_states)

    def test_identity_obligation_restores_the_necessary_distinctions(self):
        t,learning,model,proof=fit(16,4,True)
        self.assertTrue(proof.equivalent)
        self.assertEqual(len(model.representatives),49)
        self.assertTrue(minimality(t,model))
        self.assertIn('who',t.alphabet)
        out=model.run(('mention:topic_0010','who'))
        self.assertEqual(out[-1],('subject','topic_0010'))

    def test_memoryless_and_current_output_aliases_are_insufficient(self):
        t,_,model,_=fit(12,3)
        sequence=('mention:topic_0000','minutes','seconds','repeat')
        self.assertEqual(model.run(sequence),t.query(sequence))
        self.assertEqual(model.run(sequence)[-1],('seconds',23*60))
        # Both prefixes have the same next minutes answer, but different
        # subsequent repeat behavior; one test is not a congruence proof.
        self.assertEqual(t.continuation(('mention:topic_0000',),('minutes',)),
                         t.continuation(('mention:topic_0000','seconds'),('minutes',)))
        self.assertNotEqual(t.continuation(('mention:topic_0000',),('repeat',)),
                            t.continuation(('mention:topic_0000','seconds'),('repeat',)))

    def test_random_unseen_continuations_match_independent_source(self):
        t,learning,model,proof=fit(20,5,named=True)
        rng=random.Random(704)
        for i in range(3500):
            path=tuple(rng.choice(t.alphabet) for _ in range(rng.randrange(1,13)))
            self.assertEqual(model.run(path),t.query(path),(i,path))
        self.assertTrue(conformance(t,model).equivalent)

    def test_out_of_contract_and_oversized_oracle_requests_refused(self):
        t,_,model,_=fit(8,2)
        with self.assertRaises(GroundRefused): t.query(('who',))
        with self.assertRaises(GroundRefused): model.run(('who',))
        with self.assertRaises(GroundRefused): t.query(('noise',)*65)
        with self.assertRaises(GroundRefused): source_fixture(4,6)

    def test_current_evidence_and_external_pins_restore_model(self):
        t,learning,model,proof=fit(16,4)
        doc=receipt(t,model,proof,learning)
        checkpoint=json.loads(json.dumps(doc))
        replicated=restore(t,checkpoint,external_digest=doc['digest'])
        self.assertEqual(replicated,model)
        self.assertEqual(replicated.fingerprint,model.fingerprint)
        self.assertEqual(model.run(('mention:topic_0006','minutes','repeat')),
                         (('noted',),('minutes',25),('minutes',25)))
        self.assertEqual(checkpoint['evidence']['minimal_state_count'],len(model.representatives))

    def test_rehashed_false_claim_refused_by_independent_semantics(self):
        t,learning,model,proof=fit(10,2)
        doc=receipt(t,model,proof,learning)
        wrong=copy.deepcopy(doc)
        wrong['hypothesis']['emissions'][0][1]=['minutes',999]
        wrong['digest']=__import__('cognitive_grounds').digest({k:v for k,v in wrong.items() if k!='digest'})
        with self.assertRaisesRegex(GroundRefused,'independent'):
            restore(t,wrong,external_digest=wrong['digest'])
        with self.assertRaisesRegex(GroundRefused,'pinned'):
            restore(t,doc,external_digest='0'*64)

    def test_extra_unreachable_fabricated_state_is_not_minimal(self):
        t,learning,model,proof=fit(8,2)
        doc=receipt(t,model,proof,learning)
        forged=copy.deepcopy(doc)
        count=len(forged['hypothesis']['representatives'])
        forged['hypothesis']['representatives'].append(['noise','noise','noise'])
        forged['hypothesis']['transitions'].append([count]*len(t.alphabet))
        forged['hypothesis']['emissions'].append([['invented'] for _ in t.alphabet])
        forged['digest']=__import__('cognitive_grounds').digest(
            {k:v for k,v in forged.items() if k!='digest'})
        with self.assertRaisesRegex(GroundRefused,'independent'):
            restore(t,forged,external_digest=forged['digest'])

    def test_forged_row_and_wrong_source_scope_fail(self):
        t,learning,model,proof=fit(12,3)
        doc=receipt(t,model,proof,learning)
        t2,_,_,_=fit(12,3,True)
        with self.assertRaises(GroundRefused):restore(t2,doc,external_digest=doc['digest'])
        records=list(t.ground.facts)
        old=records[0]
        records[0]=Fact(old.subject,(11,22),2,'different-source')
        changed=FactGround(tuple(records))
        from cognitive_grounds import Learner
        changed_learn=Learner(changed).admit(records[0].subject,sum(records[0].steps))
        t3=Teacher(changed,changed_learn)
        with self.assertRaises(GroundRefused):restore(t3,doc,external_digest=doc['digest'])

    def test_long_history_is_represented_by_state_not_repeated_history(self):
        t,learning,model,proof=fit(8,4)
        rng=random.Random(987)
        path=tuple(rng.choice(t.alphabet) for _ in range(60))
        self.assertEqual(model.run(path),t.query(path))
        self.assertEqual(len(model.representatives),13)

    def test_real_repo_transition_congruence_refiner(self):
        path=Path(__file__).resolve().parents[2]/'bridges'/'observation-equivalence'
        if not (path/'transition_congruence.py').is_file():
            self.skipTest('native IFS transition-congruence module available in in-repo CI')
        sys.path.insert(0,str(path))
        from transition_congruence import refine_to_transition_congruence
        teacher,learning,model,proof=fit(12,3)
        states=[(None,None)]+[(f.subject,last) for f in teacher.ground.facts
                              for last in (None,'minutes','seconds')]
        from predictive_state import _source_step
        report=refine_to_transition_congruence(
            states,teacher.alphabet,teacher.alphabet,
            lambda state, test: _source_step(teacher.ground,state,test)[1],
            lambda state,action: _source_step(teacher.ground,state,action)[0])
        self.assertEqual(report.stable_block_count,len(model.representatives))
        self.assertEqual(report.initial_block_count,report.stable_block_count)

    def test_separate_process_structural_handoff(self):
        script=Path(__file__).with_name('run_predictive_state.py')
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'machine.json'
            a=subprocess.run([sys.executable,str(script),'prepare','--path',str(file)],
                             capture_output=True,text=True,check=True,timeout=45)
            b=subprocess.run([sys.executable,str(script),'resume','--path',str(file)],
                             capture_output=True,text=True,check=True,timeout=45)
            pins=json.loads(a.stdout)
            result=json.loads(b.stdout)
            self.assertEqual(pins['digest'],result['digest'])
            self.assertEqual(result['final_response'],['seconds',24*60])
            self.assertTrue(result['independent_conformance'])
            self.assertEqual(result['query_calls_for_recovery'],0)


if __name__=='__main__':unittest.main()
