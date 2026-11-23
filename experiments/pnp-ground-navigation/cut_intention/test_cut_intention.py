"""CIG-001 finite independent oracles, semantic attacks and scaling tests."""
import copy
import itertools
import unittest

from cut_intention import (GroundRefusal, analyze, compile_ground, cut_geometry,
                           make_source, min_balanced_hub_norm_sq_numerator,
                           source_accepts)
from verify_cut_intention import GroundVerificationError, verify


def brute(source):
    n=source['n']
    return sum(source_accepts(source, [(z>>i)&1 for i in range(n)]) for z in range(1<<n))


def literal_rank(source, selected):
    """Naive coefficient flattening over GF2; source CNF evaluated per entry."""
    nodes=source['nodes']; left=[v for i,group in enumerate(nodes) if i in selected for v in group]
    right=[v for i,group in enumerate(nodes) if i not in selected for v in group]
    assert len(left)+len(right)==source['n']
    rows=[]
    for a in range(1<<len(left)):
        row=0
        for b in range(1<<len(right)):
            bits=[0]*source['n']
            for j,v in enumerate(left):bits[v-1]=(a>>j)&1
            for j,v in enumerate(right):bits[v-1]=(b>>j)&1
            if source_accepts(source,bits):row|=1<<b
        rows.append(row)
    basis={}
    for row in rows:
        while row:
            pivot=row.bit_length()-1
            if pivot in basis:row^=basis[pivot]
            else:
                basis[pivot]=row
                break
    return len(basis)


class CutIntentionTests(unittest.TestCase):
    def test_small_original_source_oracle(self):
        for k in range(2,5):
            src=make_source(k)
            expected=1<<(k*(k-1)//2)
            self.assertEqual(brute(src),expected)
            for intent in ('SAT','#SAT','CUT_RANK'):
                cut=[0] if intent=='CUT_RANK' else None
                cert,ledger=compile_ground(src,intent,cut)
                self.assertTrue(verify(src,cert))
                self.assertEqual(ledger['source_variables'],src['n'])
                if intent=='#SAT':self.assertEqual(int(cert['result']['count']),expected)
                if intent=='CUT_RANK':self.assertEqual(int(cert['result']['rank']),literal_rank(src,{0}))
                if intent=='SAT':self.assertTrue(source_accepts(src,cert['result']['witness']))

    def test_rank_all_nontrivial_cuts(self):
        src=make_source(4)
        for r in range(1,4):
            for cut in itertools.combinations(range(4),r):
                cert,_=compile_ground(src,'CUT_RANK',cut)
                self.assertTrue(verify(src,cert))
                self.assertEqual(int(cert['result']['rank']),literal_rank(src,set(cut)))
                self.assertEqual(cert['result']['log2_rank'],2*r*(4-r)//2)
                self.assertEqual(cert['proof']['crossing_edges'],sum(map(abs,cert['geometry']['hub_twice'])))

    def test_large_symbolic_without_matrix(self):
        for k,l in [(6,2),(12,1),(24,2)]:
            src=make_source(k,l)
            a,_=compile_ground(src,'#SAT')
            b,_=compile_ground(src,'CUT_RANK',tuple(range(k//2)))
            self.assertTrue(verify(src,a));self.assertTrue(verify(src,b))
            self.assertEqual(int(a['result']['count']).bit_length()-1,l*k*(k-1)//2)
            self.assertEqual(b['result']['log2_rank'],l*(k//2)*(k-k//2))

    def test_cnf_mutations_rejected(self):
        src=make_source(4)
        good,_=compile_ground(src,'#SAT')
        attacks=[]
        one=copy.deepcopy(src);one['clauses'][0][0]*=-1;attacks.append(one)
        one=copy.deepcopy(src);one['clauses'].pop();attacks.append(one)
        one=copy.deepcopy(src);one['clauses'].append([1]);attacks.append(one)
        one=copy.deepcopy(src);one['nodes'][0],one['nodes'][1]=one['nodes'][1],one['nodes'][0]
        # Swapping whole node groups merely renames observers, so use a single var move instead.
        one['nodes'][0].append(one['nodes'][1].pop());attacks.append(one)
        for bad in attacks:
            with self.assertRaises((GroundRefusal,GroundVerificationError)):
                analyze(bad)
            with self.assertRaises(GroundVerificationError):verify(bad,good)

    def test_receipt_forgery_rejected(self):
        src=make_source(5)
        for intent in ('SAT','#SAT','CUT_RANK'):
            cert,_=compile_ground(src,intent,[0,1] if intent=='CUT_RANK' else None)
            altered=copy.deepcopy(cert)
            if intent=='SAT':altered['result']['witness'][0]=1
            elif intent=='#SAT':altered['result']['count']='0'
            else:altered['result']['log2_rank']+=1
            with self.assertRaises(GroundVerificationError):verify(src,altered)
            altered=copy.deepcopy(cert)
            altered['proof']['variable_equalities'][0][0]=3
            with self.assertRaises(GroundVerificationError):verify(src,altered)

    def test_unadmitted_semantics_and_cuts(self):
        src=make_source(4)
        for bad in ([0,0],[],[4],[2,0]):
            with self.assertRaises(GroundRefusal):compile_ground(src,'CUT_RANK',bad)
        with self.assertRaises(GroundRefusal):compile_ground(src,'SAT',[0])
        with self.assertRaises(GroundRefusal):compile_ground(src,'UNSAT')

    def test_hub_dynamic_program_exact(self):
        for k in range(3,11):
            lo=(k+2)//3;hi=2*k//3
            exhaustive=min(cut_geometry(k,[j for j in range(k) if (mask>>j)&1])['hub_norm_sq_numerator']
                           for mask in range(1<<k) if lo<=mask.bit_count()<=hi)
            self.assertEqual(min_balanced_hub_norm_sq_numerator(k),exhaustive)

    def test_boolean_semantics_guard(self):
        # The complementary-block linear decomposition is false under x²=x.
        P=Q={0b010101}
        boolean_product={a|b for a in P for b in Q}
        free_product=set()  # x_0²x_2²x_4² has block degree two, excluded
        self.assertEqual(boolean_product,{0b010101})
        self.assertNotEqual(boolean_product,free_product)
        self.assertEqual(1|1,1)  # Boolean OR semiring absorption
        self.assertNotEqual((1+1)%2,1)  # XOR Boolean ring cannot absorb 1


if __name__=='__main__':unittest.main()
