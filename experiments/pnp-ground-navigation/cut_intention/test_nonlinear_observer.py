"""CIG-003 source-checked nonlinear observer search, adversarial controls."""
from __future__ import annotations

from copy import deepcopy
import random
import unittest

from cut_intention import analyze, make_source, GroundRefusal
from coupled_ground import compile_ground as baseline_compiler, SCHEMA as COUPLED
from nonlinear_observer_ground import (make_gated_source,compile_ground,source_reduce,
   _accepts,MAX_COMPONENT)
from verify_nonlinear_observer import verify,Refused


class CIG003Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source,cls.cut=make_gated_source(groups=8)
        cls.certificate,_=compile_ground(cls.source,cls.cut)

    def test_nonlinear_source_discovery_without_gate_annotations(self):
        c=self.certificate
        self.assertEqual(len(c['active_labels']),24)
        self.assertEqual(c['nonlinear_gate_count'],8)
        self.assertEqual(sorted(len(x['variables']) for x in c['components']),[3]*6+[6])
        self.assertEqual(sum(2**len(x['variables']) for x in c['components']), 6*8+64)
        self.assertEqual(c['ledger']['global_active_state_count'],str(2**24))
        self.assertTrue(verify(self.source,c))

    def test_exact_counts_and_cut_rank(self):
        c=self.certificate
        self.assertEqual(int(c['result']['count']),7*4**6*2**(66-24))
        self.assertEqual(int(c['result']['rank']),3*2**34)
        self.assertEqual(int(c['observation_policy']['selected']['worst_rank']),2**34)
        self.assertEqual(c['observation_policy']['selected']['worst_rank_bits'],34)
        self.assertEqual(c['observation_policy']['selected']['methods'],
                         {str(v):'derived-anf' for v in c['observation_policy']['selected']['observe_indices']})

    def test_budget_improvement_over_previous_active_envelope(self):
        with self.assertRaises(GroundRefusal):
            baseline_compiler(self.source,'#SAT')
        self.assertTrue(verify(self.source,self.certificate))

    def test_two_gate_direct_original_cnf_truth(self):
        s,cut=make_gated_source(groups=2)
        cert,_=compile_ground(s,cut)
        self.assertTrue(verify(s,cert))
        self.assertEqual(cert['nonlinear_gate_count'],2)
        self.assertEqual(int(cert['result']['count']),7*2**(66-6))
        self.assertEqual(int(cert['result']['rank']),3*2**34)
        proof,active,clauses=source_reduce(s)
        self.assertEqual(sum(_accepts(clauses,b) for b in range(1<<len(active))),7)
        self.assertTrue(all(any(cert['result']['witness'][abs(l)-1]==int(l>0) for l in clause)
                            for clause in s['base']['clauses']+s['coupling']))

    def test_exact_anf_and_nonlinear_pullback_closure(self):
        c=self.certificate
        for gate in c['gates']:
            out=gate['output_index'];i,j=gate['inputs_indices']
            masks=[int(m) for m in gate['anf_masks']]
            self.assertTrue(any(mask.bit_count()>=2 for mask in masks))
            for state in range(8):
                x=(state&1);y=(state>>1)&1;z=(state>>2)&1
                original=(x<<i)|(y<<j)|(z<<out)
                nonlinear=sum((original&mask)==mask for mask in masks)&1
                self.assertEqual(nonlinear,gate['table'][x|(y<<1)])
                self.assertEqual(nonlinear, x&y)
                # T replaces output by exact ANF, preserving its input bits.
                moved=(original&~(1<<out))|(nonlinear<<out)
                lifted=( (moved>>out)&1, sum((moved&mask)==mask for mask in masks)&1)
                self.assertEqual(lifted,(nonlinear,nonlinear))
                if z==nonlinear:self.assertEqual(original,moved)
            # T* basis coordinates [z, f] maps to [f,f].
            self.assertEqual(gate['pullback_matrix_rows'],[2,2])

    def test_observer_price_selection_adapts(self):
        low,_=compile_ground(self.source,self.cut,native_price=5,anf_price=0)
        costly,_=compile_ground(self.source,self.cut,native_price=0,anf_price=5)
        high,_=compile_ground(self.source,self.cut,native_price=5,anf_price=3)
        self.assertEqual(len(low['observation_policy']['selected']['observe_indices']),2)
        self.assertEqual(len(costly['observation_policy']['selected']['observe_indices']),2)
        self.assertTrue(all(m=='native-output' for m in costly['observation_policy']['selected']['methods'].values()))
        self.assertEqual(high['observation_policy']['selected']['observe_indices'],[])
        for case in (low,costly,high):self.assertTrue(verify(self.source,case))

    def test_policy_covers_every_counterfactual_outcome(self):
        policy=self.certificate['observation_policy']
        self.assertEqual(len(policy['selected']['outcome_ranks']),4)
        self.assertEqual(policy['selected']['outcome_ranks'][0],'0')
        for plan in policy['alternatives']:
            self.assertEqual(len(plan['outcome_ranks']),1<<len(plan['observe_indices']))
            self.assertEqual(int(plan['worst_rank']),max(map(int,plan['outcome_ranks'])))

    def test_adversarial_changed_ground_fields_rejected(self):
        for modify in (
            lambda c: c['gates'][0]['anf_masks'].append('0'),
            lambda c: c['components'][0].__setitem__('cut_rank','999'),
            lambda c: c['result'].__setitem__('rank','1'),
            lambda c: c['observation_policy']['selected'].__setitem__('worst_rank','1'),
            lambda c: c['observation_policy']['alternatives'][0].__setitem__('total_declared_cost',0),
            lambda c: c['gates'][0]['proof_clauses'].clear(),
            lambda c: c['ledger'].__setitem__('enumerated_component_states',1),
            lambda c: c['active_labels'].reverse(),
            lambda c: c['observation_policy']['cost_contract'].__setitem__('derived_anf',-1),
        ):
            with self.subTest(modify=modify):
                c=deepcopy(self.certificate);modify(c)
                with self.assertRaises(Refused):verify(self.source,c)

    def test_source_mutation_not_a_legal_unchanged_receipt(self):
        src=deepcopy(self.source)
        src['coupling'][-1]=[-src['coupling'][-1][0],src['coupling'][-1][1]]
        with self.assertRaises(Refused):verify(src,self.certificate)
        produced,_=compile_ground(src,self.cut)
        self.assertTrue(verify(src,produced))
        self.assertNotEqual(produced['source_sha256'],self.certificate['source_sha256'])

    def test_dense_components_decline_without_false_unsat(self):
        src=deepcopy(self.source)
        outputs=[src['coupling'][3*i][0] for i in range(8)]
        src['coupling'].extend([[a,b] for a,b in zip(outputs,outputs[1:])])
        with self.assertRaises(GroundRefusal):compile_ground(src,self.cut)

    def test_invalid_observation_contract_refused(self):
        for opts in ({'max_observations':3},{'anf_price':-1},{'native_price':101}):
            with self.assertRaises(GroundRefusal):compile_ground(self.source,self.cut,**opts)
        with self.assertRaises(GroundRefusal):compile_ground(self.source,[0,0])

    def test_normalized_source_permutation_receipt_changes_source_digest_only(self):
        s=deepcopy(self.source);random.Random(19).shuffle(s['coupling'])
        c,_=compile_ground(s,self.cut)
        self.assertTrue(verify(s,c))
        self.assertEqual(c['result']['count'],self.certificate['result']['count'])
        self.assertEqual(c['result']['rank'],self.certificate['result']['rank'])
        self.assertNotEqual(c['source_sha256'],self.certificate['source_sha256'])

    def test_small_random_residuals_match_previous_exact_rank(self):
        base=make_source(6,1);pairs=analyze(base)['pairs']
        for seed in range(25):
            rng=random.Random(seed)
            # Six source labels only; original CNF constructed directly from copies.
            ids=rng.sample(range(len(pairs)),6)
            added=[]
            for j in range(5):
                v=rng.sample(ids,2)
                added.append([(1 if rng.getrandbits(1) else -1)*pairs[x][0] for x in v])
            s={'schema':COUPLED,'base':base,'coupling':added}
            cut=(0,1,2)
            c,_=compile_ground(s,cut)
            self.assertTrue(verify(s,c))
            oldc,_=baseline_compiler(s,'#SAT')
            oldr,_=baseline_compiler(s,'CUT_RANK',cut)
            self.assertEqual(c['result']['count'],oldc['result']['count'])
            self.assertEqual(c['result']['rank'],oldr['result']['rank'])


if __name__=='__main__':unittest.main()
