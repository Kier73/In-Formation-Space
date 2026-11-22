"""BENCH-01G source-only cutset construction, exact counts, refusal and tampering."""
from __future__ import annotations

from copy import deepcopy
import random
import unittest

from bench01_separator import (_digest, run, verify_receipt, select_separator,
                               _parts, _restrict)
from self_selecting_sat import choose_composite
from morphic_sat import encode_function
from algebraic_ground import random_cubic_tseitin, parity_formula


def fixture():
    """Two coupled 3-CNF regions, not pre-labelled to the compiler."""
    rng=random.Random(17)
    base_bits=6
    gates=24
    clauses=[]
    for j in range(gates):
        out=base_bits+j+1
        a=1 if j%3 else (2+j//3%5)
        b=(2+(j%5)) if j<5 else rng.choice(list(range(2,base_bits+1))+
                                                   list(range(base_bits+1,out)))
        if a==b:b=(b%base_bits)+1
        table=([0,0,0,1] if j%3==0 else ([0,1,1,1] if j%3==1 else [1,1,1,0]))
        clauses.extend(encode_function(out,(a,b),table))
    source_n=base_bits+gates
    # The original graph generator produces an odd global parity obstruction.
    # Here all vertex charges are zero so the graph is SAT and retains a
    # 12-dimensional affine solution space. The formula is still ordinary 3-CNF.
    _,edge_n,eq=random_cubic_tseitin(22,seed=7301)
    clauses.extend(tuple((abs(l)+source_n)*(1 if l>0 else -1) for l in c)
                   for c in parity_formula(edge_n,[(mask,0) for mask,_ in eq]))
    clauses.append((1,source_n+1))
    return clauses,source_n+edge_n


def seven():
    return [(1,3),(-1,5),(3,5),(2,4),(-2,6),(4,6),(7,1),(-7,2)],7


def brute(clauses,n):
    return sum(all(any(((a>>(abs(l)-1))&1)==int(l>0) for l in row)
                   for row in clauses) for a in range(1<<n))


class SeparatorTests(unittest.TestCase):
    def test_interleaved_cutset_preserves_exact_source_models(self):
        clauses,n=seven()
        self.assertEqual(len(_parts(clauses,n)),1)
        self.assertEqual(select_separator(clauses,n),[7])
        result=run(clauses,n,maximum_coordinates=256)
        self.assertEqual(result['status'],'SAT')
        self.assertEqual(result['count'],brute(clauses,n))
        self.assertEqual(verify_receipt(clauses,n,result),'SAT')
        self.assertEqual(len(result['branches']),2)
        self.assertTrue(all(b['component_count']>=2 for b in result['branches']))

    def test_exact_random_relabelings_and_extra_clauses(self):
        base,n=seven()
        for seed in range(8):
            r=random.Random(seed)
            perm=list(range(1,n+1));r.shuffle(perm)
            changed=[tuple((perm[abs(l)-1] if l>0 else -perm[abs(l)-1])
                           for l in row) for row in base]
            # Added terminal unary restriction changes count, not source validity.
            changed.append((perm[0] if seed%2 else -perm[0],))
            result=run(changed,n,maximum_coordinates=256)
            self.assertEqual(result['count'],brute(changed,n),seed)
            self.assertEqual(verify_receipt(changed,n,result),result['status'])

    def test_contradictory_source_restriction_is_not_cached_sat(self):
        clauses,n=seven()
        clauses += [(7,),(-7,)]
        result=run(clauses,n,maximum_coordinates=256)
        self.assertEqual(result['status'],'UNSAT')
        self.assertEqual(result['count'],0)
        self.assertEqual(verify_receipt(clauses,n,result),'UNSAT')

    def test_forged_branch_count_rejected_even_with_recomputed_digest(self):
        c,n=seven();r=run(c,n,maximum_coordinates=256)
        forged=deepcopy(r)
        forged['branches'][0]['count']+=1
        forged['count']+=1
        forged['digest']=_digest({k:v for k,v in forged.items() if k!='digest'})
        with self.assertRaises(ValueError):verify_receipt(c,n,forged)

    def test_forged_selected_separator_rejected_even_with_recomputed_digest(self):
        c,n=seven();r=run(c,n,maximum_coordinates=256)
        r['separator']=[1]
        r['digest']=_digest({k:v for k,v in r.items() if k!='digest'})
        with self.assertRaises(ValueError):verify_receipt(c,n,r)

    def test_source_change_rejected(self):
        c,n=seven();r=run(c,n,maximum_coordinates=256)
        with self.assertRaises(ValueError):verify_receipt(c+[(1,)],n,r)

    def test_direct_random_graph_has_no_articulation_and_refuses(self):
        n=9
        clauses=[(i,i+1,(i%9)+3 if (i%9)+3<=9 else (i%9)+3-9)
                 for i in range(1,9)]
        clauses += [(1,5,9),(2,5,8),(2,3,6),(4,7,9)]
        # Explicitly create a complete graph via all binary pairs to exclude cuts.
        clauses=[(i,j) for i in range(1,n+1) for j in range(i+1,n+1)]
        r=run(clauses,n,maximum_coordinates=256)
        self.assertEqual(r['status'],'UNKNOWN')
        self.assertEqual(r['reason'],'no qualified variable separator')
        self.assertEqual(verify_receipt(clauses,n,r),'UNKNOWN')

    def test_bad_cut_budget_and_not_three_cnf_refused(self):
        with self.assertRaises(ValueError):select_separator([(1,2,3,4)],5)
        with self.assertRaises(ValueError):select_separator([(1,2)],5,max_cut=3)
        with self.assertRaises(ValueError):run([(1,2)],5,partition_size=0)

    def test_connected_larger_3sat_unknown_without_cut_but_solved_with_it(self):
        c,n=fixture()
        self.assertEqual(n,63)
        self.assertEqual(max(map(len,c)),3)
        self.assertEqual(len(_parts(c,n)),1)
        self.assertEqual(choose_composite(c,n)['status'],'UNKNOWN')
        r=run(c,n)
        self.assertEqual(r['separator'],[31])
        self.assertEqual(r['status'],'SAT')
        self.assertEqual(r['count'],196608)
        self.assertEqual(verify_receipt(c,n,r),'SAT')
        self.assertEqual(sorted(b['count'] for b in r['branches']),[65536,131072])


if __name__=='__main__':unittest.main()
