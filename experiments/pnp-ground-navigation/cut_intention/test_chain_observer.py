"""CIG-004: exact source-derived nonlinear depth, feature lift and adversarial checks."""
from __future__ import annotations
from copy import deepcopy
import json
import unittest

from chain_observer_ground import (make_chain_source,compile_ground,_operator,_eval,
   _pullback,_navigate,GroundRefusal,source_reduce)
from verify_chain_observer import verify,Reject


class CIG004Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source,cls.cut=make_chain_source(depth=4)
        cls.doc,_=compile_ground(cls.source,cls.cut)

    def test_source_qualified_chain_and_independent_count(self):
        c=self.doc
        self.assertEqual(c['features']['dimension'],5)
        self.assertEqual(len(c['gates']),4)
        self.assertEqual(len(c['registers']),4)
        self.assertEqual(c['source_result']['count'],str(2**41))
        self.assertEqual(c['ledger']['source_clause_count'],106) # 90 equality + 16 gate clauses
        self.assertTrue(verify(self.source,c))

    def test_annealed_observer_one_invariant_feature(self):
        future=self.doc['future_alignment']
        self.assertEqual(future['stabilization_steps'],4)
        self.assertEqual(future['anf_masks'],[3,5,8])
        self.assertEqual(future['dimension'],1)
        self.assertEqual(future['symbolic_pullbacks'],5)
        self.assertEqual(self.doc['features']['matrix_rows'],[2,4,8,16,16])
        self.assertTrue(verify(self.source,self.doc))

    def test_nontrivial_four_step_future_not_one_step_rewrite(self):
        rows=_operator(self.doc['gates'],len(self.doc['active_labels']))
        def move(s):return sum(_eval(poly,s)<<i for i,poly in enumerate(rows))
        state=3;timeline=[(state>>self.doc['observer'])&1]
        observed_states=[state]
        for _ in range(6):
            state=move(state);observed_states.append(state)
            timeline.append((state>>self.doc['observer'])&1)
        self.assertEqual(timeline[:5],[0,0,0,0,1])
        self.assertEqual(timeline[4:],[1,1,1])
        self.assertNotEqual(observed_states[1],observed_states[2])
        self.assertEqual(observed_states[4],observed_states[5])

    def test_source_fixed_points_iff_original_reduced_cnf(self):
        _,_,clauses=source_reduce(self.source)
        rows=_operator(self.doc['gates'],len(self.doc['active_labels']))
        for state in range(1<<8):
            satisfying=all(any((state>>(abs(l)-1)&1)==int(l>0) for l in clause) for clause in clauses)
            fixed=sum(_eval(r,state)<<i for i,r in enumerate(rows))==state
            self.assertEqual(satisfying,fixed)
        self.assertEqual(sum(all(any((s>>(abs(l)-1)&1)==int(l>0) for l in clause)
            for clause in clauses) for s in range(256)),16)

    def test_exact_navigation_at_all_small_times_and_huge_time(self):
        rows=_operator(self.doc['gates'],len(self.doc['active_labels']))
        def move(s):return sum(_eval(p,s)<<i for i,p in enumerate(rows))
        basis=[tuple(x) for x in self.doc['features']['basis']]
        for state in range(256):
            raw=state
            features=sum(_eval(p,state)<<i for i,p in enumerate(basis))
            for t in range(7):
                new,_=_navigate(self.doc['features']['matrix_rows'],features,t)
                self.assertEqual((new&self.doc['features']['read_mask']).bit_count()&1,
                                 (raw>>self.doc['observer'])&1)
                raw=move(raw)
        big=10**100+173
        c,_=compile_ground(self.source,self.cut,steps=big)
        self.assertTrue(verify(self.source,c))
        self.assertEqual(c['navigation']['observed'],1)
        self.assertLess(c['navigation']['matrix_products'],700)
        self.assertEqual(c['future_alignment']['observed'],1)

    def test_idempotent_overlap_survives_nested_substitution(self):
        p=self.doc['future_alignment']['anf_masks']
        self.assertEqual(p,[3,5,8])
        # x0**2*x1 == x0*x1 because masks multiply using OR, not exponent sum.
        # Under the nonlinear operation x0'=x0, x1'=x0,
        # T*(x0*x1) = x0*x0 = x0. A free polynomial ring would not.
        self.assertEqual(_pullback((3,),[(1,), (1,)]),(1,))

    def test_all_chain_depths_and_source_full_model_counts(self):
        for depth in range(2,9):
            with self.subTest(depth=depth):
                s,cut=make_chain_source(depth=depth)
                c,_=compile_ground(s,cut)
                self.assertEqual(c['features']['dimension'],depth+1)
                self.assertEqual(c['future_alignment']['stabilization_steps'],depth)
                self.assertEqual(c['source_result']['count'],str(2**(45-depth)))
                self.assertTrue(verify(s,c))

    def test_budget_refusal_is_not_unsat(self):
        with self.assertRaisesRegex(GroundRefusal,'feature budget'):
            compile_ground(self.source,self.cut,max_features=3)
        with self.assertRaisesRegex(GroundRefusal,'logical time budget'):
            compile_ground(self.source,self.cut,steps=1<<4096)
        with self.assertRaisesRegex(GroundRefusal,'initial state'):
            compile_ground(self.source,self.cut,initial=256)

    def test_break_original_equality_proof_rejected(self):
        s=deepcopy(self.source)
        s['base']['clauses'][0]=[1,2]
        with self.assertRaises((GroundRefusal,Reject)):
            compile_ground(s,self.cut)
        with self.assertRaises(Reject):verify(s,self.doc)

    def test_removed_gate_clause_rejected_or_reclassified(self):
        s=deepcopy(self.source);s['coupling'].pop()
        with self.assertRaises(GroundRefusal):compile_ground(s,self.cut)
        with self.assertRaises(Reject):verify(s,self.doc)

    def test_extra_external_residual_clause_refused(self):
        s=deepcopy(self.source);s['coupling'].append([1])
        with self.assertRaises(GroundRefusal):compile_ground(s,self.cut)

    def test_source_digests_and_forged_certificate_variants_rejected(self):
        changes=[
          lambda d:d['source_result'].__setitem__('count','1'),
          lambda d:d['source_result']['witness'].__setitem__(0,9),
          lambda d:d['gates'][0]['anf_masks'].append(0),
          lambda d:d['features']['basis'][3].append(0),
          lambda d:d['features']['matrix_rows'].__setitem__(1,0),
          lambda d:d['features'].__setitem__('dimension',1),
          lambda d:d['future_alignment'].__setitem__('stabilization_steps',3),
          lambda d:d['future_alignment']['anf_masks'].__setitem__(0,7),
          lambda d:d['navigation'].__setitem__('observed',0),
          lambda d:d['navigation'].__setitem__('matrix_products',0),
          lambda d:d['ledger'].__setitem__('closure_pullbacks',0),
          lambda d:d['operator_rows'][4].append(0),
          lambda d:d.__setitem__('active_labels',[]),
          lambda d:d.__setitem__('cut',[]),
        ]
        for idx,change in enumerate(changes):
            with self.subTest(modification=idx):
                cert=deepcopy(self.doc);change(cert)
                with self.assertRaises(Reject):verify(self.source,cert)

    def test_json_round_trip_and_fresh_process_verification(self):
        from pathlib import Path
        import subprocess,sys
        cert=json.loads(json.dumps(self.doc))
        self.assertTrue(verify(self.source,cert))
        here=Path(__file__).resolve().parent
        response=subprocess.run([sys.executable,str(here/'verify_chain_cli.py')],
             input=json.dumps({'source':self.source,'certificate':cert}),
             text=True,capture_output=True,check=False)
        self.assertEqual(response.returncode,0,response.stderr)
        self.assertIn('verified',response.stdout)
        cert['future_alignment']['observed']=999
        response=subprocess.run([sys.executable,str(here/'verify_chain_cli.py')],
             input=json.dumps({'source':self.source,'certificate':cert}),
             text=True,capture_output=True,check=False)
        self.assertNotEqual(response.returncode,0)

    def test_observer_is_intention_scoped_not_all_time_trace(self):
        self.assertEqual(self.doc['navigation']['observed'],self.doc['future_alignment']['observed'])
        self.assertNotEqual(self.doc['features']['dimension'],self.doc['future_alignment']['dimension'])
        # The reduced final polynomial is *not* equal to the original output
        # at time zero. Dimension-one is valid for eventual observation only.
        initial=3
        self.assertEqual((initial>>self.doc['observer'])&1,0)
        self.assertEqual(self.doc['future_alignment']['observed'],1)


if __name__=='__main__':unittest.main()
