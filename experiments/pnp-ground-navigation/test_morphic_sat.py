"""Adversarial and independent source-CNF checks for SFI-002."""
from __future__ import annotations

import copy
import random
import unittest

from morphic_sat import (compile_ground, decode, encode_function,
                        execute, execute_partition, normalize, seeded_circuit, digest)
from morphic_verifier import verify, check_partition, independent_count


def literal_truth(clauses,state):
    return all(any(bool(state & (1 << (abs(l)-1)))==(l>0)
                   for l in clause) for clause in clauses)


def truth_count(clauses,n):
    return sum(literal_truth(clauses,bits) for bits in range(1 << n))


class NonAffineMachineTests(unittest.TestCase):
    def test_96_small_random_sources_with_independent_truth_tables(self):
        rng=random.Random(26013)
        for index in range(96):
            n=rng.randrange(2,10)
            clauses=[]
            for _ in range(rng.randrange(0,24)):
                variables=rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))
                clauses.append([v if rng.randrange(2) else -v for v in variables])
            ground,ledger=compile_ground(clauses,n)
            self.assertTrue(verify(ground)['proven'],index)
            result=execute(ground,max_coordinates=512,partition_size=127)
            self.assertEqual(result['models'],truth_count(clauses,n),index)
            self.assertEqual(independent_count(ground),result['models'],index)
            for receipt in result['partition_receipts']:
                self.assertTrue(check_partition(ground,receipt,maximum=512,partition_size=127))

    def test_unlabelled_nonaffine_towers_form_56_gates(self):
        for seed,expected in ((5,168),(17,188)):
            clauses,n,fixture=seeded_circuit(seed,gates=56,mixed=True)
            source=normalize(clauses,n)
            ground,ledger=compile_ground(clauses,n)
            self.assertEqual(n,64)
            self.assertEqual(ledger['instructions'],56)
            self.assertEqual(ground['registers'],list(range(1,9)))
            self.assertTrue(verify(ground)['proven'])
            result=execute(ground,max_coordinates=256,partition_size=32)
            self.assertEqual(result['models'],expected)
            self.assertEqual(independent_count(ground),expected)
            self.assertEqual(sum(r['checked'] for r in result['partition_receipts']),256)
            for receipt in result['partition_receipts']:
                self.assertTrue(check_partition(ground,receipt,maximum=256,partition_size=32))
            self.assertGreater(ledger['covered_clauses'],150)
            self.assertEqual(len(source),ledger['covered_clauses']+ledger['residual_clauses'])

    def test_compact_and_or_tseitin_and_arbitrary_truth_tables(self):
        # Neither known operator labels nor generator's truth values are passed
        # to the compiler. It only sees the complete CNF relation.
        tables=(
            (2,[0,0,0,1]),  # AND
            (2,[0,1,1,1]),  # OR
            (2,[1,1,1,0]),  # NAND
            (2,[0,1,1,0]),  # XOR
            (3,[0,0,0,1,0,1,1,1]), # majority
            (3,[0,1,0,1,0,0,1,1]), # arbitrary 3-input LUT
        )
        for arity,table in tables:
            n=arity+1
            clause_set=encode_function(n,tuple(range(1,n)),table,compact=True)
            ground,ledger=compile_ground(clause_set,n)
            self.assertEqual(ledger['instructions'],1)
            self.assertEqual(len(ground['registers']),arity)
            self.assertTrue(verify(ground)['proven'])
            for value in range(1<<arity):
                actual=decode(ground,value)
                self.assertTrue(literal_truth(clause_set,actual))
                # Verify the output coordinate on original source using truth table
                self.assertEqual((actual>>(n-1))&1,table[value])

    def test_incomplete_relation_is_not_a_function(self):
        encoded=encode_function(3,(1,2),[0,1,1,0],compact=False)
        source=encoded[:-1]
        ground,ledger=compile_ground(source,3)
        self.assertEqual(len(ground['instructions']),0)
        self.assertEqual(ledger['register_bits'],3)
        self.assertEqual(execute(ground)['models'],truth_count(source,3))

    def test_cyclic_relation_is_not_wrongly_oriented_as_acyclic(self):
        # y = NOT x ; x = y. Both are functional, but their intersection is
        # inconsistent. The compiler must not construct a circular decoder.
        source=encode_function(2,(1,),[1,0])+encode_function(1,(2,),[0,1])
        ground,stats=compile_ground(source,2)
        self.assertTrue(verify(ground)['proven'])
        self.assertEqual(execute(ground)['models'],0)
        self.assertEqual(truth_count(source,2),0)

    def test_mixed_residual_can_rule_out_every_generated_coordinate(self):
        source,n,_=seeded_circuit(7,gates=32,mixed=False)
        source.extend([(1,),(-1,)])
        ground,_=compile_ground(source,n)
        self.assertTrue(verify(ground)['proven'])
        self.assertEqual(execute(ground,max_coordinates=1024)['status'],'UNSAT')
        self.assertEqual(independent_count(ground),0)

    def test_budget_fails_unknown_without_falsely_claiming_unsat(self):
        # No complete gate block; 35 free bits exceed explicit search budget.
        rng=random.Random(602)
        source=[tuple(v if rng.randrange(2) else -v
                      for v in rng.sample(range(1,36),3)) for _ in range(135)]
        ground,_=compile_ground(source,35)
        self.assertTrue(verify(ground)['proven'])
        self.assertEqual(execute(ground,max_coordinates=1<<16)['status'],'UNKNOWN')
        self.assertEqual(execute(ground,max_coordinates=1<<16)['models'],None)

    def test_intention_changes_evaluation_without_changing_ground(self):
        source,n,_=seeded_circuit(3,gates=20)
        ground,_=compile_ground(source,n)
        sat=execute(ground,intent='SAT',max_coordinates=256,partition_size=16)
        cnt=execute(ground,intent='COUNT',max_coordinates=256,partition_size=16)
        self.assertEqual(sat['status'],'SAT')
        self.assertEqual(cnt['status'],'SAT')
        self.assertEqual(cnt['models'],independent_count(ground))
        self.assertLess(sat['checked'],cnt['checked'])
        for r in sat['partition_receipts']:
            self.assertTrue(check_partition(ground,r,maximum=256,partition_size=16))

    def test_reject_forged_clause_and_truth_table_even_with_new_digest(self):
        source,n,_=seeded_circuit(17,gates=9)
        ground,_=compile_ground(source,n)
        for mutation in ('table','block','residual','register','dependency'):
            candidate=copy.deepcopy(ground)
            if mutation=='table':candidate['instructions'][0]['table'][0]^=1
            elif mutation=='block':candidate['instructions'][0]['clauses'].pop()
            elif mutation=='residual':candidate['residual'].append([1])
            elif mutation=='register':candidate['registers'].append(n)
            else: candidate['instructions'][0]['inputs'][0]=candidate['instructions'][0]['output']
            candidate['digest']=digest({k:v for k,v in candidate.items() if k!='digest'})
            with self.assertRaises(ValueError,msg=mutation):verify(candidate)

    def test_reject_forged_partition_receipt_even_with_new_hash(self):
        source,n,_=seeded_circuit(3,gates=8)
        ground,_=compile_ground(source,n)
        result=execute_partition(ground,0,budget=256,partition_size=256)
        result['models']+=1
        result['digest']=digest({k:v for k,v in result.items() if k!='digest'})
        with self.assertRaises(ValueError):check_partition(ground,result,maximum=256,partition_size=256)

    def test_noncanonical_source_refused(self):
        for clauses in ([[0]],[[999]],[['x']], [[1,-1]], [[2,2]]):
            if clauses==[[1,-1]] or clauses==[[2,2]]:
                # Tautologies and duplicate literals correctly normalize away.
                self.assertTrue(verify(compile_ground(clauses,2)[0])['proven'])
            else:
                with self.assertRaises(ValueError):compile_ground(clauses,2)


if __name__=='__main__':unittest.main()
