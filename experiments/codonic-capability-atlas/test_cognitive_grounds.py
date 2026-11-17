"""COG-006: source-grounded compositional intelligence structures and refusals."""
import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cognitive_grounds import (Fact, FactGround, Program, GroundRefused, Learner,
                               Session, enumerate_programs, realize, fixture)


def train(ground):
    state=Learner(ground)
    for _ in range(4):
        if len(state.viable)==1: break
        subject=state.acquire([f.subject for f in ground.facts[:min(128,len(ground.facts))]])
        state=state.admit(subject,sum(ground.record(subject).steps))
    return state


class StructureTests(unittest.TestCase):
    def test_typed_compiler_discovers_multiple_structures(self):
        paths=enumerate_programs()
        self.assertEqual(len(paths),3)
        self.assertEqual({p.operators for p in paths}, {('direct',),('steps','sum'),
                          ('steps','first','first_minutes')})
        self.assertEqual(len(enumerate_programs('seconds')),3)
        with self.assertRaises(GroundRefused): Program(('seconds',),'minutes')

    def test_active_acquisition_promotes_new_composition(self):
        ground=fixture(128)
        state=train(ground)
        self.assertEqual(len(state.viable),1)
        self.assertEqual(state.promoted.operators,('steps','sum'))
        for fact in ground.facts[24:]:
            self.assertEqual(realize(ground,state.promoted,fact.subject)[0],sum(fact.steps))

    def test_inconclusive_examples_do_not_promote(self):
        ground=fixture(128)
        state=Learner(ground).admit('procedure_000000',sum(ground.record('procedure_000000').steps))
        with self.assertRaises(GroundRefused): _=state.promoted

    def test_counterexample_rejects_all_structures(self):
        ground=fixture(128)
        with self.assertRaises(GroundRefused):
            Learner(ground).admit('procedure_000001',999)

    def test_multi_turn_references_and_composition(self):
        ground=fixture(128); learner=train(ground)
        session=Session(learner).perform('mention','procedure_000042').perform('ask_minutes').perform('ask_seconds')
        total=sum(ground.record('procedure_000042').steps)
        self.assertEqual(session.turns[-2].answer['value'],total)
        self.assertEqual(session.turns[-1].answer['value'],total*60)
        self.assertEqual(session.turns[-1].answer['source_evidence'],['synthetic-case-000042'])
        self.assertEqual(Session(learner).perform('ask_minutes').turns[-1].answer['status'],'unresolved')
        session=session.perform('clear').perform('ask_minutes')
        self.assertEqual(session.turns[-1].answer['status'],'unresolved')

    def test_handoff_and_external_pins(self):
        ground=fixture(128); learner=train(ground)
        session=Session(learner).perform('mention','procedure_000042').perform('ask_minutes')
        fresh=Learner.restore(ground,json.loads(json.dumps(learner.document())),external_head=learner.head)
        replica=Session.restore(fresh,json.loads(json.dumps(session.document())),external_head=session.head)
        self.assertEqual(replica.perform('ask_seconds').turns[-1].answer['value'],
                         sum(ground.record('procedure_000042').steps)*60)
        with self.assertRaises(GroundRefused):
            Session.restore(fresh,session.document(),external_head='0'*64)
        changed=copy.deepcopy(session.document()); changed['turns'][-1]['answer']['value']=99
        with self.assertRaises(GroundRefused):
            Session.restore(fresh,changed,external_head=session.head)
        altered=copy.deepcopy(learner.document()); altered['examples'][0]['expected']+=1
        with self.assertRaises(GroundRefused):
            Learner.restore(ground,altered,external_head=learner.head)

    def test_source_changed_refusal(self):
        g=fixture(128); learner=train(g)
        facts=list(g.facts)
        old=facts[4]
        facts[4]=Fact(old.subject,(old.steps[0]+1,)+old.steps[1:],old.direct_minutes,old.source)
        altered=FactGround(tuple(facts))
        with self.assertRaises(GroundRefused):
            Learner.restore(altered,learner.document(),external_head=learner.head)

    def test_context_value_vs_memoryless_ablated(self):
        ground=fixture(512); learner=train(ground)
        rng=random.Random(74)
        correct_memory=0;correct_no_context=0
        for _ in range(250):
            key=ground.facts[rng.randrange(len(ground.facts))].subject
            expected=sum(ground.record(key).steps)
            with_memory=Session(learner).perform('mention',key).perform('ask_minutes')
            stateless=Session(learner).perform('ask_minutes')
            correct_memory+=with_memory.turns[-1].answer.get('value')==expected
            correct_no_context+=stateless.turns[-1].answer.get('value')==expected
        self.assertEqual((correct_memory,correct_no_context),(250,0))

    def test_selected_execution_visits_only_one_subject(self):
        ground=fixture(4096); learner=train(ground)
        result,sources=realize(ground,learner.promoted,'procedure_004095')
        self.assertEqual(result,sum(ground.record('procedure_004095').steps))
        self.assertEqual(sources,('synthetic-case-004095',))
        self.assertLessEqual(learner.promoted.cost,2)

    def test_source_fact_validation(self):
        with self.assertRaises(GroundRefused):
            FactGround((Fact('x',(1,2),4,'source'),Fact('x',(2,3),6,'source')))
        with self.assertRaises(GroundRefused):
            Fact('bad name',(1,2),2,'source')

    def test_active_distinguishes_behavioral_aliases_before_admission(self):
        # Most training items cannot distinguish three rival structures.
        # This is a deliberately adversarial finite pool, not natural language.
        facts=[]
        for i in range(100):
            length=1 if i<90 else 2
            parts=tuple(range(1,length+1))
            facts.append(Fact(f'case_{i:03d}',parts,parts[0],f'src-{i}'))
        ground=FactGround(tuple(facts)); pool=[f.subject for f in facts]
        active_ok=passive_ok=0
        for seed in range(100):
            target=Learner(ground).acquire(pool)
            a=Learner(ground).admit(target,sum(ground.record(target).steps))
            active_ok+=int(len(a.viable)==1 and a.promoted.operators==('steps','sum'))
            passive_target=random.Random(seed).choice(pool)
            b=Learner(ground).admit(passive_target,sum(ground.record(passive_target).steps))
            passive_ok+=int(len(b.viable)==1)
        self.assertEqual(active_ok,100)
        self.assertLess(passive_ok,30)

    def test_real_pybot_readme_followup_contract_fixture(self):
        # Demonstration grounded in PyBot README's *displayed* half-hour
        # kettle example. The natural-language parser is not reproduced.
        base=fixture(128)
        g=FactGround(tuple(sorted(base.facts+(Fact('kettle_descaling',(30,),30,
            'pybot-readme-kettle-demonstration'),),key=lambda f:f.subject)))
        learner=train(g)
        s=Session(learner).perform('mention','kettle_descaling').perform('ask_minutes')
        self.assertEqual(s.turns[-1].answer['value'],30)
        self.assertEqual(s.turns[-1].answer['source_evidence'],['pybot-readme-kettle-demonstration'])

    def test_separate_process_checkpoint_resume(self):
        script=Path(__file__).with_name('run_cognitive_grounds.py')
        with tempfile.TemporaryDirectory() as directory:
            filename=str(Path(directory)/'handoff.json')
            proc=subprocess.run([sys.executable,str(script),'prepare','--path',filename],
                               capture_output=True,text=True,check=True,timeout=30)
            pins=json.loads(proc.stdout)
            nxt=subprocess.run([sys.executable,str(script),'resume','--path',filename],
                               capture_output=True,text=True,check=True,timeout=30)
            self.assertEqual(json.loads(nxt.stdout)['value'],960)
            self.assertEqual(pins['conversation'],json.loads(Path(filename).read_text())['session']['head'])

    def test_native_ifs_task_equivalence_engine_if_available(self):
        path=Path(__file__).resolve().parents[2]/'bridges'/'observation-equivalence'
        if not (path/'transition_congruence.py').exists():
            self.skipTest('native IFS observation-equivalence module absent locally')
        sys.path.insert(0,str(path))
        from transition_congruence import refine_to_transition_congruence
        g=fixture(40); learning=train(g)
        states=[None]+[f.subject for f in g.facts]
        actions=['clear']+[('mention',s) for s in states[1:]]
        def step(state,action):
            return None if action=='clear' else action[1]
        def observe(state,test):
            if state is None: return None
            return realize(g,learning.promoted,state)[0] if test=='duration' else state
        coarse=refine_to_transition_congruence(states,actions,['duration'],observe,step)
        fine=refine_to_transition_congruence(states,actions,['duration','subject'],observe,step)
        self.assertLess(coarse.stable_block_count,fine.stable_block_count)
        self.assertEqual(fine.stable_block_count,len(states))

if __name__=='__main__':unittest.main()
