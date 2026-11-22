"""SPN-008 direct source SAT proof and tamper regressions."""
import copy
import random
import unittest

from direct_sat_compiler import (
    VERSION, check_assignment, dpll_produce, gaussian_ground, parity_blocks,
    produce_direct_sat, source_digest, spectral_form, validate_cnf,
    verify_direct_sat,
)


def encode_xor_equations(equations,n):
    """Independent reference encoder: every forbidden k-bit pattern is a clause."""
    clauses=[]
    for variables,target in equations:
        if not 1<=len(variables)<=3 or len(set(variables))!=len(variables):
            raise ValueError('bad test equation')
        for mask in range(1<<len(variables)):
            if (mask.bit_count()%2)==target:
                continue
            clauses.append(tuple((-v if (mask>>j)&1 else v)
                                  for j,v in enumerate(variables)))
    return clauses


def parity_cycle_family(blocks,frustrated):
    n=6*blocks
    equations=[]
    for j in range(blocks):
        a,b,c,d,e,f=tuple(range(6*j+1,6*j+7))
        equations.extend([((a,b,c),0),((a,d,e),0),((b,d,f),0),
                          ((c,e,f),int(frustrated and j==0))])
    return encode_xor_equations(equations,n),n


def brute_sat(clauses,n):
    return any(check_assignment(clauses,[(mask>>j)&1 for j in range(n)])
               for mask in range(1<<n))


class DirectSatTests(unittest.TestCase):
    def test_validate_and_conversion(self):
        for bad,n in [([[0]],2),([[3]],2),([['1']],2),([list(range(4))],4),([],0)]:
            with self.assertRaises(ValueError):validate_cnf(bad,n)
        self.assertEqual(spectral_form([(2,-3,1)],3),
                         [((0,1,2),(0,0,1))])
        self.assertIsNone(spectral_form([(1,1,3)],3))

    def test_xor_recognizer_is_semantically_exact(self):
        for n in range(3,9):
            rng=random.Random(n*31)
            for _ in range(20):
                equations=[]
                for _ in range(3):
                    scope=tuple(sorted(rng.sample(range(1,n+1),3)))
                    equations.append((scope,rng.randrange(2)))
                cls=encode_xor_equations(equations,n)
                # duplicate scope with opposite RHS is not a complete XOR block
                got=parity_blocks(cls,n)
                if len({tuple(c[0]) for c in equations})<len(equations):
                    if any(len({rhs for scope,rhs in equations if scope==v})>1
                           for v in set(scope for scope,_ in equations)):
                        self.assertIsNone(got)
                    continue
                self.assertIsNotNone(got)
                self.assertEqual(brute_sat(cls,n),
                                 any(all(((mask&mm).bit_count()&1)==rhs for mm,rhs in got)
                                     for mask in range(1<<n)))
        cls=encode_xor_equations([((1,2,3),0)],3)
        self.assertIsNone(parity_blocks(cls[:-1],3))
        self.assertEqual(parity_blocks([(1,-1,2)],3),[])

    def test_xor_lift_sat_and_contradiction(self):
        for blocks in (1,3,10,20):
            for frustrated in (False,True):
                clauses,n=parity_cycle_family(blocks,frustrated)
                result=produce_direct_sat(clauses,n,node_budget=1)
                self.assertEqual(result['result'],'UNSAT' if frustrated else 'SAT')
                self.assertIn(result['proof']['kind'],('xor_sat','xor_unsat'))
                self.assertEqual(result['producer_ledger']['attempts'][0]['status'],'recognized')
                self.assertEqual(verify_direct_sat(clauses,n,result),result['result'])
                if frustrated:self.assertEqual(len(result['proof']['conflict_indices']),4)
                else:self.assertTrue(check_assignment(clauses,result['proof']['witness']))

    def test_random_mixed_cnf_exhaustive(self):
        rng=random.Random(81244)
        results=[]
        for n in (4,5,6,7,8):
            for case in range(45):
                cls=[]
                for _ in range(n*3+2):
                    k=rng.randint(1,min(3,n))
                    vs=rng.sample(range(1,n+1),k)
                    cls.append(tuple(v if rng.randrange(2) else -v for v in vs))
                receipt=produce_direct_sat(cls,n,node_budget=2048)
                truth='SAT' if brute_sat(cls,n) else 'UNSAT'
                self.assertEqual(receipt['result'],truth,(n,case))
                self.assertEqual(verify_direct_sat(cls,n,receipt),truth)
                results.append(truth)
        self.assertIn('SAT',results);self.assertIn('UNSAT',results)

    def test_forged_proofs_rejected(self):
        source=[(1,2),(1,-2),(-1,2),(-1,-2)]
        authentic=produce_direct_sat(source,2,node_budget=200)
        self.assertEqual(authentic['result'],'UNSAT')
        forged=copy.deepcopy(authentic)
        forged['proof']={'kind':'conflict'}
        with self.assertRaises(ValueError):verify_direct_sat(source,2,forged)
        forged=copy.deepcopy(authentic)
        forged['source_sha256']='0'*64
        with self.assertRaises(ValueError):verify_direct_sat(source,2,forged)
        forged=copy.deepcopy(authentic)
        forged['proof'].pop('one')
        with self.assertRaises(ValueError):verify_direct_sat(source,2,forged)
        xor_cnf,n=parity_cycle_family(2,True)
        good=produce_direct_sat(xor_cnf,n)
        forged=copy.deepcopy(good)
        forged['proof']['conflict_indices']=forged['proof']['conflict_indices'][:-1]
        with self.assertRaises(ValueError):verify_direct_sat(xor_cnf,n,forged)
        forged=copy.deepcopy(good)
        forged['proof']={'kind':'xor_sat','witness':[0]*n}
        forged['result']='SAT'
        with self.assertRaises(ValueError):verify_direct_sat(xor_cnf,n,forged)

    def test_unknown_budget_no_false_unsat(self):
        src=[(1,2,3),(1,-2,-3),(-1,2,-3),(-1,-2,3),
             (1,2,-3),(1,-2,3),(-1,2,3),(-1,-2,-3)]
        receipt=produce_direct_sat(src,3,node_budget=1)
        self.assertEqual(receipt['result'],'UNKNOWN')
        self.assertEqual(verify_direct_sat(src,3,receipt),'UNKNOWN')
        forged=copy.deepcopy(receipt);forged['result']='UNSAT'
        with self.assertRaises(ValueError):verify_direct_sat(src,3,forged)

    def test_spectral_fallback_proves_yes(self):
        # A strict one-node DPLL budget can miss a solution while SPN's
        # conditional mean constructs one. Search for a seeded deterministic
        # negative-control rather than assume all CNF representations agree.
        rng=random.Random(681)
        found=False
        for _ in range(250):
            n=7
            cls=[tuple(v if rng.randrange(2) else -v
                       for v in rng.sample(range(1,n+1),3)) for _ in range(18)]
            plain=produce_direct_sat(cls,n,node_budget=1)
            if plain['result']!='UNKNOWN':continue
            extended=produce_direct_sat(cls,n,node_budget=1,spectral_budget=50)
            if extended['proof']['kind']=='spectral_fallback':
                self.assertEqual(extended['result'],'SAT')
                self.assertEqual(verify_direct_sat(cls,n,extended),'SAT')
                forged=copy.deepcopy(extended)
                forged['proof']['receipt']['result']='UNSAT'
                with self.assertRaises(ValueError):verify_direct_sat(cls,n,forged)
                found=True;break
        self.assertTrue(found)

    def test_empty_and_tautology(self):
        self.assertEqual(produce_direct_sat([],5)['result'],'SAT')
        self.assertEqual(produce_direct_sat([()],5)['result'],'UNSAT')
        self.assertEqual(produce_direct_sat([(1,-1)],5)['result'],'SAT')
        src,n=parity_cycle_family(2,True)
        noisy=src+[(1,-1)]+[src[0]]+[(1,1,-1)]
        receipt=produce_direct_sat(noisy,n,node_budget=1)
        self.assertEqual(receipt['result'],'UNSAT')
        self.assertEqual(receipt['proof']['kind'],'xor_unsat')
        self.assertEqual(verify_direct_sat(noisy,n,receipt),'UNSAT')


if __name__=='__main__': unittest.main()
