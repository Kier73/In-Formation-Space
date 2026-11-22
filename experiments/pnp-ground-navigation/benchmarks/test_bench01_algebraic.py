"""Source-level and adversarial checks for exact 3-SAT Fourier coordinates."""
import copy
import random
import unittest
from bench01_algebraic import (build, verify, cycle_xor, hub_not_all_equal, xor_three, _digest,
                               _canonical_source, _coefficients, _source_independent_coefficients)
from bench01_separator import run as variable_run, select_separator


def _truth(n,clauses):
    return [x for x in range(1<<n) if all(
        any(bool((x>>(abs(l)-1))&1)==(l>0) for l in c) for c in clauses)]


class ExactCoordinateTests(unittest.TestCase):
    def test_connected_nonvariable_coordinates_sat(self):
        for n in (5,7,10,19,20,31,50,80):
            with self.subTest(n=n):
                clauses=cycle_xor(n)
                self.assertEqual(select_separator(clauses,n),[])
                p=build(clauses,n,max_rank=5,max_cells=512)
                self.assertEqual((p['status'],p['count']),('SAT',1))
                self.assertEqual(p['global_rank'],n)
                self.assertEqual(len(p['components']),n)
                self.assertEqual(verify(clauses,n,p)['count'],1)
                self.assertEqual(variable_run(clauses,n)['status'],'UNKNOWN')

    def test_nonaffine_not_all_equal_exact_model_count(self):
        for blocks in (1,3,7,12,20):
            with self.subTest(blocks=blocks):
                clauses,n=hub_not_all_equal(blocks)
                p=build(clauses,n,max_rank=4,max_cells=4096)
                self.assertEqual((p['status'],p['count']),('SAT',2*3**blocks))
                self.assertEqual(p['global_rank'],2*blocks)
                self.assertEqual([len(g['basis']) for g in p['components']],[2]*blocks)
                self.assertEqual(verify(clauses,n,p)['count'],2*3**blocks)
                if n<=15:self.assertEqual(len(_truth(n,clauses)),2*3**blocks)

    def test_connected_unsat_in_exact_coordinates(self):
        for n in (5,7,19,31,80):
            clauses=cycle_xor(n,unsat=True)
            receipt=build(clauses,n)
            self.assertEqual((receipt['status'],receipt['count']),('UNSAT',0))
            self.assertEqual(verify(clauses,n,receipt)['status'],'UNSAT')

    def test_full_exhaustive_random_width_three(self):
        rng=random.Random(731231)
        for i in range(96):
            n=rng.randint(3,8)
            clauses=[]
            for _ in range(rng.randrange(2,23)):
                ids=rng.sample(range(1,n+1),3)
                clauses.append([v * rng.choice((-1,1)) for v in ids])
            p=build(clauses,n,max_rank=8,max_cells=8192)
            a=verify(clauses,n,p)
            expected=_truth(n,clauses)
            self.assertEqual(a['status'],'SAT' if expected else 'UNSAT')
            self.assertEqual(a['count'],len(expected))
            if expected:self.assertIn(int(a['witness_decimal']),expected)

    def test_exact_source_coefficients_are_derived_independently(self):
        s=cycle_xor(17,unsat=True)
        src=_canonical_source(s,17)
        self.assertEqual(_coefficients(src),_source_independent_coefficients(src))

    def test_large_coupled_support_budget_refusal(self):
        # Clauses from one full-rank generic CNF cause a high-rank component.
        rng=random.Random(18);n=14
        clauses=[]
        for _ in range(32):
            variables=rng.sample(range(1,n+1),3)
            clauses.append([v*rng.choice((-1,1)) for v in variables])
        result=build(clauses,n,max_rank=3,max_cells=48)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertIsNone(result['count'])
        self.assertEqual(verify(clauses,n,result)['status'],'UNKNOWN')

    def test_coordinate_invariance_under_variable_renaming(self):
        n=13
        original=cycle_xor(n)
        rng=random.Random(510)
        mapping=list(range(1,n+1));rng.shuffle(mapping)
        renamed=[[int(l>0)*mapping[abs(l)-1] if l>0 else -mapping[abs(l)-1]
                  for l in clause] for clause in original]
        p=build(renamed,n)
        self.assertEqual(verify(renamed,n,p)['count'],1)
        self.assertEqual(p['global_rank'],n)

    def test_forged_linear_independence_is_rejected(self):
        # On a 9-cycle, triple parities are dependent: 9 terms, rank 7.
        clauses=[]
        for i in range(9):
            clauses+=xor_three(i+1,(i+1)%9+1,(i+2)%9+1,rhs=i%2)
        original=build(clauses,9,max_rank=8,max_cells=4096)
        self.assertEqual(verify(clauses,9,original)['global_rank'],7)
        coeff=_coefficients(_canonical_source(clauses,9))
        masks=sorted(s for s in coeff if s)
        forged=copy.deepcopy(original)
        forged['components']=[{'supports':[s],'basis':[s],
             'terms':[[s,coeff[s],1]],'minimum':-abs(coeff[s]),
             'minimizers':1,'first_coordinate':0 if coeff[s]<0 else 1,
             'coordinates_evaluated':2} for s in masks]
        forged['digest']=_digest({k:v for k,v in forged.items() if k!='digest'})
        with self.assertRaises(ValueError):verify(clauses,9,forged)

    def test_rank_is_charged_not_source_variable_count(self):
        clauses=xor_three(1,2,3,0)
        p=build(clauses,9)
        self.assertEqual(p['global_rank'],1)
        self.assertEqual(p['count'],1<<(9-1))
        self.assertEqual(verify(clauses,9,p)['count'],256)

    def test_identity_bound_to_original_source(self):
        s=cycle_xor(7)
        p=build(s,7)
        with self.assertRaises(ValueError):verify(s[:-1],7,p)
        with self.assertRaises(ValueError):verify(cycle_xor(7,unsat=True),7,p)

    def test_reject_nonstrict_and_wrong_budget(self):
        with self.assertRaises(ValueError):build([[1,2]],3)
        with self.assertRaises(ValueError):build([[1,1,2]],3)
        with self.assertRaises(ValueError):build([[1,2,3]],3,max_rank=99)


class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.clauses=cycle_xor(11)
        self.receipt=build(self.clauses,11)

    def forged(self,mutate):
        p=copy.deepcopy(self.receipt)
        mutate(p)
        p['digest']=_digest({k:v for k,v in p.items() if k!='digest'})
        with self.assertRaises(ValueError):verify(self.clauses,11,p)

    def test_forged_source_term(self):
        self.forged(lambda p:p['components'][0]['terms'][0].__setitem__(1,99))

    def test_forged_support_reconstruction(self):
        self.forged(lambda p:p['components'][0]['terms'][0].__setitem__(2,0))

    def test_fake_model_count(self):
        self.forged(lambda p:p.__setitem__('count',2**11))

    def test_fake_unsat_minimum(self):
        self.forged(lambda p:p.__setitem__('minimum_scaled_eight',8))

    def test_omitted_independent_component(self):
        self.forged(lambda p:p['components'].pop())

    def test_invented_overlap_between_spans(self):
        self.forged(lambda p:p['components'][0]['supports'].__setitem__(0,p['components'][1]['supports'][0]))

    def test_changed_witness(self):
        self.forged(lambda p:p.__setitem__('witness_decimal',str(int(p['witness_decimal'])^1)))

    def test_reject_forged_bounded_unknown(self):
        self.forged(lambda p:p.__setitem__('status','UNKNOWN'))

    def test_untrusted_cost_values_not_proof(self):
        p=copy.deepcopy(self.receipt)
        p['observation']['construction_ms']=1e5
        p['digest']=_digest({k:v for k,v in p.items() if k!='digest'})
        self.assertEqual(verify(self.clauses,11,p)['status'],'SAT')


if __name__=='__main__':unittest.main()
