"""SPN-010 trusted-proof gates and self-use meta-SAT tests."""
import copy
import random
import unittest

from direct_sat_compiler import (produce_direct_sat,parity_blocks,
    verify_direct_sat)
from language_choice_sat import (compile_language,verify_language_receipt)
from self_use_cycle import (VERSION,RULES,_hash,source_features,
    validate_policy,chosen_engine,produce_self_use_receipt,
    verify_self_use_receipt,compile_meta_cnf,train_policy,observe,evaluate_frozen)
from test_direct_sum_grounds import shared_variable_cycle_cnf


def source_from_spectral(rows):
    return [tuple(v+1 if b==0 else -(v+1) for v,b in zip(scope,bits))
            for scope,bits in rows]


def policy(rules=()):
    p={'version':VERSION,'selected_rules':sorted(rules),
       'training_digest':'0'*64,'training_sources':[]}
    p['policy_sha256']=_hash(p)
    return p


class SelfUseTests(unittest.TestCase):
    def test_source_only_features(self):
        rows,n=shared_variable_cycle_cnf(16,frustrated=True)
        clauses=source_from_spectral(rows)
        feature=source_features(clauses,n)
        self.assertTrue(feature['many_variables'])
        self.assertTrue(feature['hub_and_repeated'])
        p=policy(['hub_and_repeated'])
        self.assertEqual(chosen_engine(clauses,n,p),'portfolio')
        self.assertEqual(chosen_engine([(1,2,3)],3,p),'direct')

    def test_policy_source_bound_and_forged_proofs(self):
        clauses=[(1,2,3),(1,-2,-3),(-1,2,-3),(-1,-2,3),
                 (1,2,-3),(1,-2,3),(-1,2,3),(-1,-2,-3)]
        p=policy()
        receipt=produce_self_use_receipt(clauses,3,p,node_budget=256)
        self.assertEqual(verify_self_use_receipt(clauses,3,p,receipt),'UNSAT')
        for corrupt in ('source','engine','result','nested'):
            altered=copy.deepcopy(receipt)
            if corrupt=='source':altered['source_sha256']='f'*64
            elif corrupt=='engine':altered['engine']='portfolio'
            elif corrupt=='result':altered['result']='SAT'
            else:altered['proof']['proof']={'kind':'conflict'}
            with self.assertRaises(ValueError):
                verify_self_use_receipt(clauses,3,p,altered)
        # The producer's timing estimates are not mathematical claims.
        changed=copy.deepcopy(receipt)
        changed['producer_ledger']={'total_ms':-5000}
        self.assertEqual(verify_self_use_receipt(clauses,3,p,changed),'UNSAT')

    def test_unknown_never_becomes_unsat(self):
        rng=random.Random(100)
        clauses=[tuple(v if rng.randrange(2) else -v for v in
                       rng.sample(range(1,13),3)) for _ in range(54)]
        r=produce_self_use_receipt(clauses,12,policy(),node_budget=1)
        self.assertEqual(r['result'],'UNKNOWN')
        bad=copy.deepcopy(r);bad['result']='UNSAT'
        with self.assertRaises(ValueError):
            verify_self_use_receipt(clauses,12,policy(),bad)

    def test_meta_cnf_width_three_and_tseitin(self):
        features={k:True for k in RULES}
        sample={'features':features,
                'direct':{'result':'UNKNOWN'},'portfolio':{'result':'SAT'}}
        clauses=compile_meta_cnf([sample],max_rules=2)
        self.assertTrue(all(len(c)<=3 for c in clauses))
        self.assertGreater(max(abs(v) for c in clauses for v in c),len(RULES))
        from direct_sat_compiler import produce_direct_sat
        n=max(abs(v) for c in clauses for v in c)
        for mask in range(1<<len(RULES)):
            units=[(j+1 if mask>>j&1 else -(j+1),) for j in range(len(RULES))]
            receipt=produce_direct_sat(clauses+units,n,node_budget=200)
            status=verify_direct_sat(clauses+units,n,receipt)
            expectation=('SAT' if 1<=mask.bit_count()<=2 else 'UNSAT')
            self.assertEqual(status,expectation,mask)

    def test_training_replay_and_heldout_integrity(self):
        rows,n=shared_variable_cycle_cnf(10,frustrated=True)
        structure=source_from_spectral(rows)
        cases=[([(1,2,3),(1,-2,-3),(-1,2,-3)],3),
               ([(1,2,3)],3),(structure,n)]
        training=[observe(c,n,8) for c,n in cases]
        p,audit=train_policy(training,max_rules=2)
        self.assertTrue(validate_policy(p))
        self.assertEqual(audit['meta_proof_calls'],64)
        self.assertLessEqual(len(p['selected_rules']),2)
        self.assertEqual(audit['training_examples'],3)
        with self.assertRaises(ValueError):evaluate_frozen(p,[training[0]])
        tampered=copy.deepcopy(training)
        tampered[0]['portfolio']['result']='UNSAT'  # not source-verified
        with self.assertRaises(ValueError):train_policy(tampered)
        with self.assertRaises(ValueError):train_policy(training+[training[0]])
        forged=copy.deepcopy(p);forged['selected_rules']=['many_variables']
        with self.assertRaises(ValueError):validate_policy(forged)

    def test_redundant_scan_elimination_preserves_decisions(self):
        # The SPN-009 selector has already established the source formula is
        # NOT a complete XOR. The optimized DPLL producer may safely avoid
        # scanning for the same structure a second time.
        rng=random.Random(12244)
        for n in range(3,12):
            for case in range(18):
                clauses=[tuple(v if rng.randrange(2) else -v for v in
                         rng.sample(range(1,n+1),3)) for _ in range(3*n+5)]
                if parity_blocks(clauses,n) is not None:continue
                baseline=produce_direct_sat(clauses,n,node_budget=64)
                optimized=produce_direct_sat(clauses,n,node_budget=64,
                                            skip_complete_xor=True)
                self.assertEqual(baseline['result'],optimized['result'])
                self.assertEqual(baseline['proof'],optimized['proof'])
                self.assertEqual(verify_direct_sat(clauses,n,optimized),baseline['result'])
                self.assertEqual(optimized['producer_ledger']['attempts'][0]['status'],
                                 'skipped_prechecked')

    def test_shortcut_can_only_change_search_not_proof_truth(self):
        # A false negative screening may give UNKNOWN rather than an easy XOR
        # decision. It must never authorize an unsupported assertion.
        from test_direct_sat_compiler import parity_cycle_family
        clauses,n=parity_cycle_family(4,True)
        authentic=produce_direct_sat(clauses,n,node_budget=1)
        skipped=produce_direct_sat(clauses,n,node_budget=1,skip_complete_xor=True)
        self.assertEqual(authentic['result'],'UNSAT')
        self.assertEqual(skipped['result'],'UNKNOWN')
        self.assertEqual(verify_direct_sat(clauses,n,skipped),'UNKNOWN')

if __name__=='__main__':unittest.main()
