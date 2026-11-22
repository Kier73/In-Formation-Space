"""Direct SAT and #SAT machine morphogenesis; independent exhaustive oracles."""
import copy
import random
import unittest
from algebraic_ground import planted_dense, random_cubic_tseitin, encode_xor
from derived_ground import compile_proven_ground, split_guard, implication_equalities
from frontier_ground import brute_count,random_3cnf
from self_forming_sat import (form,verify_program,execute_partition,
                              aggregate,check_segment,digest)


def run(clauses,n,intention='#SAT',**kwargs):
    receipt=compile_proven_ground(clauses,n,**kwargs)
    program,stats=form(receipt,intention=intention,partition_size=256)
    assert verify_program(program,receipt)
    pieces=[execute_partition(program,i) for i in range(len(program['partitions']))]
    return program,aggregate(program,pieces,source_receipt=receipt),stats,receipt

class DirectSatTests(unittest.TestCase):
    def test_small_random_exact_counts_against_independent_brute(self):
        rng=random.Random(713)
        for n in range(2,10):
            for case in range(12):
                clauses=[]
                for _ in range(n+4):
                    vs=rng.sample(range(1,n+1),rng.randrange(1,min(n,3)+1))
                    clauses.append(tuple(v if rng.getrandbits(1) else -v for v in vs))
                program,result,stats,_=run(clauses,n)
                count=brute_count(clauses,n)
                self.assertEqual(result['count'],count,(n,case))
                self.assertEqual(result['status'],'SAT' if count else 'UNSAT')
                self.assertEqual(program['free_dimension'],n if not program['source_relation']['equations'] else program['free_dimension'])

    def test_observer_intention_rebuilds_processor(self):
        clauses=[(1,2),(-1,2),(1,-2)]
        p1,r1,_,_=run(clauses,2,'SAT')
        p2,r2,_,_=run(clauses,2,'#SAT')
        self.assertNotEqual(p1['digest'],p2['digest'])
        self.assertEqual(r1['status'],'SAT')
        self.assertIsNone(r1['count'])
        self.assertEqual(r2['count'],1)
        self.assertEqual(p1['operator_graph'][-1]['op'],'stop-on-witness')
        self.assertEqual(p2['operator_graph'][-1]['op'],'accumulate-count')
        self.assertLessEqual(r1['evaluated'],r2['evaluated'])

    def test_guarded_hidden_parity_forms_smaller_computer(self):
        core=encode_xor(0b1111,1)
        guarded=split_guard(split_guard(core,guard_id=5),guard_id=6)
        p,r,stats,_=run(guarded,6)
        self.assertEqual(p['free_dimension'],5) # 6 source dims - one independent XOR
        self.assertEqual(r['count'],32) # one 4-XOR and two free guards = 32
        self.assertEqual(stats['generated_registers'],5)

    def test_global_xor_contradiction_has_no_search_partition(self):
        clauses,n,_=random_cubic_tseitin(12,7301)
        p,r,_,proof=run(clauses,n)
        self.assertEqual(p['mode'],'refutation')
        self.assertEqual(r['status'],'UNSAT')
        self.assertEqual(r['count'],0)
        self.assertEqual(len(p['partitions']),0)
        bad=copy.deepcopy(proof);bad['source_sha256']='0'*64
        with self.assertRaises(ValueError):aggregate(p,[],source_receipt=bad)

    def test_large_source_rank_reduces_generated_registers(self):
        clauses,_,_=planted_dense(48,8,22,False)
        p,r,stats,_=run(clauses,48)
        self.assertEqual(p['free_dimension'],8)
        self.assertEqual(r['count'],256)
        self.assertLess(stats['generated_registers'],stats['original_vars'])

    def test_nonlocal_implication_uses_proven_equations(self):
        clauses,n=implication_equalities(8)
        p,r,stats,_=run(clauses,n)
        self.assertEqual(r['count'],2)
        self.assertLess(p['free_dimension'],n)

    def test_large_unresolved_general_sat_refuses(self):
        p,r,stats,proof=run(random_3cnf(35,140,73),35,
             max_resolution_attempts=1)
        self.assertEqual(p['mode'],'undetermined')
        self.assertEqual(r['status'],'UNDETERMINED')
        with self.assertRaises(ValueError):execute_partition(p,0)

    def test_incomplete_guard_is_not_treated_as_proven_xor(self):
        guarded=split_guard(encode_xor(0b1111,1),guard_id=5)
        incomplete=guarded[:-1]
        p,r,_,proof=run(incomplete,5)
        self.assertEqual(r['count'],brute_count(incomplete,5))
        self.assertEqual(p['free_dimension'],5)

    def test_partitions_fail_closed_without_full_coverage(self):
        clauses=random_3cnf(9,20,73)
        program,result,stats,receipt=run(clauses,9)
        chunks=[execute_partition(program,i) for i in range(len(program['partitions']))]
        self.assertGreater(len(chunks),1)
        with self.assertRaises(ValueError): aggregate(program,chunks[:-1])
        with self.assertRaises(ValueError): aggregate(program,chunks+[chunks[0]])
        forged=copy.deepcopy(chunks[0]);forged['models']+=1
        forged['sha256']=digest({k:v for k,v in forged.items() if k!='sha256'})
        with self.assertRaises(ValueError):check_segment(program,forged)
        bad=copy.deepcopy(program);bad['operator_graph'][-1]['op']='accept-everything'
        bad['digest']=digest({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaises(ValueError):verify_program(bad,receipt)

if __name__=='__main__':unittest.main()
