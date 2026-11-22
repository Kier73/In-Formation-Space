"""GRC-001: independent small-CNF references, forgery controls and budget refusal."""
from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from direct_sat_compiler import check_assignment
from language_choice_sat import compile_language
from ground_revision_continuity import (construct_revision,verify_revision,
                                        source_extension, normalized, loss_query)


def count_ref(clauses,n):
    return sum(check_assignment(clauses,[(mask>>i)&1 for i in range(n)])
               for mask in range(1<<n))


class ContinuityTests(unittest.TestCase):
    def old_count(self,clauses,n):
        return compile_language(clauses,n,goal='count',frontier_cell_cap=100000,
                                allow_sfi=False)

    def test_entailment_proves_no_models_lost(self):
        old=[(1,),(-2,3)]
        new=old+[(1,2,3)]
        base=self.old_count(old,4)
        answer=construct_revision(old,new,4,base)
        self.assertEqual(answer['result'],base['result'])
        self.assertEqual([s['kind'] for s in answer['steps']],['entailed'])
        self.assertEqual(verify_revision(old,new,4,answer),base['result'])

    def test_count_delta_exact(self):
        old=[(1,2),(-1,2)]
        new=old+[(1,)]
        base=self.old_count(old,3)
        result=construct_revision(old,new,3,base)
        self.assertEqual(result['result'],'2')
        self.assertEqual(result['steps'][0]['lost'],'2')
        self.assertEqual(result['steps'][0]['kind'],'counted_loss')
        self.assertEqual(verify_revision(old,new,3,result),'2')

    def test_more_than_one_clause_and_zero_monotone(self):
        old=[(1,2),(-1,2)]
        new=old+[(1,),(-3,)]
        base=self.old_count(old,3)
        receipt=construct_revision(old,new,3,base)
        self.assertEqual(int(receipt['result']),count_ref(new,3))
        self.assertEqual(len(receipt['steps']),2)
        self.assertEqual(verify_revision(old,new,3,receipt),receipt['result'])
        unsat=[(1,),(-1,)]
        base=self.old_count(unsat,5)
        receipt=construct_revision(unsat,unsat+[(2,),(3,)],5,base)
        self.assertEqual(receipt['result'],'0')
        self.assertEqual([x['kind'] for x in receipt['steps']],
                         ['monotone_zero','monotone_zero'])

    def test_semantic_renormalization_not_mislabeled_a_new_constraint(self):
        old=[(1,2),(-1,2),(1,-1)]
        new=[(-1,2),(2,1),(1,2),(1,-1),(3,-3)]
        base=self.old_count(old,5)
        receipt=construct_revision(old,new,5,base)
        self.assertEqual(receipt['steps'],[])
        self.assertEqual(receipt['result'],base['result'])
        self.assertEqual(verify_revision(old,new,5,receipt),receipt['result'])

    def test_oversized_count_proof_remains_unknown(self):
        old=[(1,2)];new=old+[(3,)]
        base=self.old_count(old,12)
        receipt=construct_revision(old,new,12,base,frontier_cell_cap=1)
        self.assertEqual(receipt['result'],'UNKNOWN')
        self.assertEqual(verify_revision(old,new,12,receipt),'UNKNOWN')
        self.assertEqual(len(receipt['steps']),0)

    def test_old_unsat_monotone_decision(self):
        old=[(1,),(-1,)]
        base=compile_language(old,4,goal='decision')
        r=construct_revision(old,old+[(2,3)],4,base)
        self.assertEqual(r['result'],'UNSAT')
        self.assertEqual(verify_revision(old,old+[(2,3)],4,r),'UNSAT')

    def test_old_sat_new_sat_and_unknown(self):
        old=[(1,)];new=old+[(2,)]
        base=compile_language(old,4,goal='decision')
        r=construct_revision(old,new,4,base)
        self.assertEqual(r['result'],'SAT')
        self.assertEqual(verify_revision(old,new,4,r),'SAT')
        # Adding the negation of an old unit can invalidate the old witness.
        impossible=old+[(-1,)]
        candidate=construct_revision(old,impossible,4,base,node_budget=128)
        self.assertEqual(candidate['result'],'UNKNOWN')
        self.assertEqual(verify_revision(old,impossible,4,candidate),'UNKNOWN')

    def test_large_exact_count_with_redundant_new_clause(self):
        n=200;old=[(1,)];new=old+[(1,2,3)]
        base=self.old_count(old,n)
        receipt=construct_revision(old,new,n,base)
        self.assertEqual(receipt['result'],str(1<<199))
        self.assertEqual(receipt['steps'][0]['kind'],'entailed')
        self.assertEqual(verify_revision(old,new,n,receipt),str(1<<199))

    def test_random_small_formulas_exhaustive(self):
        rng=random.Random(20261122)
        methods={'counted_loss':0,'entailed':0,'monotone_zero':0}
        for n in range(3,8):
            for trial in range(20):
                old=[]
                for _ in range(n+2):
                    vars=rng.sample(range(1,n+1),rng.randint(1,min(n,3)))
                    old.append(tuple(v if rng.randrange(2) else -v for v in vars))
                extra=[]
                for _ in range(2):
                    vs=rng.sample(range(1,n+1),rng.randint(1,min(n,3)))
                    extra.append(tuple(v if rng.randrange(2) else -v for v in vs))
                new=old+extra
                base=self.old_count(old,n)
                receipt=construct_revision(old,new,n,base)
                self.assertEqual(receipt['result'],str(count_ref(new,n)),(n,trial))
                self.assertEqual(verify_revision(old,new,n,receipt),receipt['result'])
                for step in receipt['steps']:
                    methods[step['kind']]+=1
        self.assertGreater(methods['counted_loss'],0)
        self.assertGreater(methods['monotone_zero'],0)

    def test_forged_claims_fail_with_same_producer_ledger(self):
        old=[(1,2),(-1,2)]
        new=old+[(1,)]
        base=self.old_count(old,3)
        receipt=construct_revision(old,new,3,base)
        variants=[]
        tamper=copy.deepcopy(receipt);tamper['result']='99';variants.append(tamper)
        tamper=copy.deepcopy(receipt);tamper['new_sha256']='0'*64;variants.append(tamper)
        tamper=copy.deepcopy(receipt);tamper['steps'][0]['lost']='1';variants.append(tamper)
        tamper=copy.deepcopy(receipt);tamper['steps'][0]['clause']=[3];variants.append(tamper)
        tamper=copy.deepcopy(receipt);tamper['steps'][0]['proof']['result']='3';variants.append(tamper)
        tamper=copy.deepcopy(receipt);tamper['previous_receipt']['result']='9';variants.append(tamper)
        for variant in variants:
            with self.assertRaises(ValueError):verify_revision(old,new,3,variant)
        with self.assertRaises(ValueError):
            construct_revision(old,[(1,)],3,base)
        valid=copy.deepcopy(receipt)
        valid['producer_ledger']={'total_ms':-9999}
        self.assertEqual(verify_revision(old,new,3,valid),'2')

    def test_json_clean_process_verifier(self):
        old=[(1,2),(-1,2)];new=old+[(1,)]
        receipt=construct_revision(old,new,3,self.old_count(old,3))
        with tempfile.TemporaryDirectory() as td:
            infile=Path(td)/'revision.json'
            infile.write_text(json.dumps({'n':3,'old_clauses':old,'new_clauses':new,
                                          'receipt':receipt}))
            result=subprocess.run([sys.executable,str(Path(__file__).parent/
                'verify_ground_revision_json.py'),str(infile)],
                capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(result.stdout)['result'],'2')

if __name__=='__main__':unittest.main()
