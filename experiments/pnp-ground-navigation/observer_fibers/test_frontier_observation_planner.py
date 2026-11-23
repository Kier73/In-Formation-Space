"""OFG-003 independent global truth-table and adversarial certificate tests."""
from __future__ import annotations

from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path
from random import Random
import unittest

from frontier_observation_planner import (GroundRefusal, Intention, compile_plan,
    decode, discover, encode, observe_source_state, requested_projection, verify_plan,
    _condition, _source)
from separator_fiber_ground import source_accepts


def shared_switch(blocks=5, cost=0):
    return Intention(blocks+1, ((1,-2),(-1,-3)), tuple(range(2,blocks+2)), ((1,cost),))


def double_hub(blocks=5, first_cost=0, second_cost=0):
    clauses=tuple(clause for i in range(3,blocks+3) for clause in ((1,i),(2,-i)))
    return Intention(blocks+2,clauses,tuple(range(3,blocks+3)),
                    ((1,first_cost),(2,second_cost)))


class FrontierObservationTests(unittest.TestCase):
    def oracle(self,q,plan):
        source=_source(q,plan['geometry'])
        observation=tuple(plan['selected_policy']['observe'])
        fibers={}
        models=0
        for a in range(1 << q.n):
            if not source_accepts(source,a):
                continue
            models+=1
            bits=sum(bool(a & (1<<(v-1)))<<i for i,v in enumerate(observation))
            fibers.setdefault(bits,set()).add(requested_projection(q,a))
            rank=encode(q,plan,a,bits)
            recovered=decode(q,plan,bits,rank)
            self.assertTrue(source_accepts(source,recovered))
            self.assertEqual(requested_projection(q,recovered),requested_projection(q,a))
            self.assertEqual(observe_source_state(q,plan,recovered),bits)
        self.assertEqual(models,plan['ground']['models'])
        sep=tuple(plan['geometry']['separator'])
        observed=observation
        maximum=0
        for outcome in range(1 << len(observed)):
            _,_,count=_condition(plan['ground'],sep,observed,outcome)
            actual=len(fibers.get(outcome,set()))
            self.assertEqual(count,actual)
            maximum=max(maximum,count)
            for code in range(actual):
                rebuilt=decode(q,plan,outcome,code)
                self.assertIn(requested_projection(q,rebuilt),fibers[outcome])
            with self.assertRaises(GroundRefusal):
                decode(q,plan,outcome,actual)
        self.assertEqual(maximum, max(plan['selected_policy']['outcome_fiber_sizes']))
        self.assertEqual((maximum-1).bit_length() if maximum else 0,
                         plan['selected_policy']['minimum_aux_bits_worst'])

    def test_single_frontier_cut_and_policy_cost_switch(self):
        cheap=shared_switch(8,0)
        expensive=shared_switch(8,1_000_000)
        c=compile_plan(cheap)
        e=compile_plan(expensive)
        self.assertEqual(c['geometry']['separator'],[1])
        self.assertEqual(e['geometry']['separator'],[1])
        self.assertEqual(c['selected_policy']['observe'],[1])
        self.assertEqual(e['selected_policy']['observe'],[])
        self.assertTrue(verify_plan(cheap,c))
        self.assertTrue(verify_plan(expensive,e))
        self.oracle(cheap,c)
        self.oracle(expensive,e)

    def test_two_bit_cut_from_png_frontier(self):
        q=double_hub(4,0,0)
        plan=compile_plan(q,max_separator=2,max_bag=3)
        self.assertEqual(plan['geometry']['separator'],[1,2])
        self.assertTrue(verify_plan(q,plan))
        self.oracle(q,plan)
        self.assertIn(len(plan['selected_policy']['observe']), (1,2))

    def test_mixed_offer_costs_may_choose_partial_subset(self):
        q=double_hub(6,10_000_000,0)
        p=compile_plan(q,max_separator=2,max_bag=3)
        self.assertEqual(p['geometry']['separator'],[1,2])
        self.assertNotIn(1,p['selected_policy']['observe'])
        self.oracle(q,p)
        self.assertTrue(verify_plan(q,p))

    def test_json_roundtrip_and_mutation_rejection(self):
        q=shared_switch(6,0)
        p=compile_plan(q)
        loaded=json.loads(json.dumps(p))
        self.assertTrue(verify_plan(q,loaded))
        self.oracle(q,loaded)
        for location, key, value in (
            ('geometry','separator',[2]),('selected_policy','observe',[]),
            ('selected_policy','total_declared_cost',-1),('ground','models',0),
            ('ground','source_sha256','0'*64),('geometry','candidate_count',1_000_000),
            ('preparation_ledger','total_preparation_units',-1)):
            bad=deepcopy(loaded)
            bad[location][key]=value
            with self.assertRaises(GroundRefusal):
                verify_plan(q,bad)
        modified=Intention(q.n,q.clauses+((-2,),),q.requested_vars,q.offers)
        with self.assertRaises(GroundRefusal):
            verify_plan(modified,p)

    def test_refusal_on_dense_unseparable_graph(self):
        q=Intention(9,tuple((i,j) for i in range(1,10) for j in range(i+1,10)),
                    tuple(range(1,10)))
        with self.assertRaisesRegex(GroundRefusal,'no PNG frontier'):
            compile_plan(q,max_separator=2,max_bag=3)

    def test_source_change_can_force_new_separator_or_refusal(self):
        q=shared_switch(6)
        changed=Intention(q.n,q.clauses+((2,4),),q.requested_vars,q.offers)
        p=compile_plan(changed,max_separator=2,max_bag=4)
        self.assertTrue(verify_plan(changed,p))
        self.oracle(changed,p)
        with self.assertRaises(GroundRefusal):
            verify_plan(changed,compile_plan(q))

    def test_randomized_global_oracle_and_empty_clause(self):
        rng=Random(903)
        accepted=0
        for _ in range(65):
            n=rng.randrange(3,9)
            clauses=tuple(tuple(v if rng.getrandbits(1) else -v
                           for v in rng.sample(range(1,n+1),rng.randrange(1,min(4,n)+1)))
                          for _ in range(rng.randrange(0,9)))
            requested=tuple(sorted(v for v in range(1,n+1) if rng.getrandbits(1)))
            q=Intention(n,clauses,requested,tuple((v,rng.randrange(0,300))
                                                   for v in range(1,n+1)))
            try:
                p=compile_plan(q,max_separator=2,max_bag=6)
            except GroundRefusal:
                continue
            accepted+=1
            self.assertTrue(verify_plan(q,p))
            self.oracle(q,p)
        self.assertGreaterEqual(accepted,10)
        q=Intention(4,((),),tuple(range(1,5)))
        p=compile_plan(q,max_separator=1,max_bag=4)
        self.assertEqual(p['ground']['status'],'UNSAT')
        self.assertTrue(verify_plan(q,p))

    def test_fresh_process_verification(self):
        q=shared_switch(4,0)
        p=compile_plan(q)
        payload={'intention':{'n':q.n,'clauses':q.clauses,
            'requested_vars':q.requested_vars,'offers':q.offers},'plan':p}
        script=Path(__file__).with_name('verify_frontier_plan.py')
        clean=subprocess.run([sys.executable,str(script)],input=json.dumps(payload),
                             text=True,capture_output=True,check=False)
        self.assertEqual(clean.returncode,0,clean.stderr)
        self.assertTrue(json.loads(clean.stdout)['verified'])
        payload['plan']['selected_policy']['total_declared_cost']=-9
        bad=subprocess.run([sys.executable,str(script)],input=json.dumps(payload),
                           text=True,capture_output=True,check=False)
        self.assertNotEqual(bad.returncode,0)
        self.assertFalse(json.loads(bad.stderr)['verified'])

    def test_original_source_disallows_incorrect_observation(self):
        q=shared_switch(4)
        p=compile_plan(q)
        assignment=0
        outcome=observe_source_state(q,p,assignment)
        code=encode(q,p,assignment,outcome)
        self.assertEqual(requested_projection(q,decode(q,p,outcome,code)),
                         requested_projection(q,assignment))
        with self.assertRaises(GroundRefusal):
            encode(q,p,assignment,outcome ^ 1)
        with self.assertRaises(GroundRefusal):
            decode(q,p,outcome,-1)


if __name__=='__main__':
    unittest.main()
