"""CIG-002: exact full-original-source finite and adversarial regressions."""
import copy
import itertools
import random
import unittest

from cut_intention import analyze, make_source, GroundRefusal
from coupled_ground import (SCHEMA,compile_ground,make_one_clause_source,source_accepts)
from verify_coupled_ground import verify,VerificationFailure


def rank_of_rows(rows):
    basis={}
    for x in rows:
        while x:
            p=(x&-x).bit_length()-1
            if p not in basis:
                basis[p]=x;break
            x^=basis[p]
    return len(basis)


def direct_full_tensor_rank(source,cut):
    nodes=source['base']['nodes']
    left=[v for i in cut for v in nodes[i]]
    right=[v for j in range(len(nodes)) if j not in cut for v in nodes[j]]
    rows=[]
    for a in range(1<<len(left)):
        row=0
        bits=[0]*source['base']['n']
        for i,v in enumerate(left):bits[v-1]=(a>>i)&1
        for b in range(1<<len(right)):
            for j,v in enumerate(right):bits[v-1]=(b>>j)&1
            if source_accepts(source,bits):row|=1<<b
        rows.append(row)
    return rank_of_rows(rows)


def direct_source_count(source):
    n=source['base']['n']
    return sum(source_accepts(source,[(i>>j)&1 for j in range(n)]) for i in range(1<<n))


class CouplingExperiment(unittest.TestCase):
    def test_rank_increase_by_added_clause(self):
        source,cut=make_one_clause_source(4,1,'left-right')
        cert,_=compile_ground(source,'CUT_RANK',cut)
        self.assertTrue(verify(source,cert))
        self.assertEqual(int(cert['result']['baseline_rank']),16)
        self.assertEqual(int(cert['result']['rank']),32)
        self.assertEqual(cert['result']['rank_ratio'],[2,1])
        self.assertEqual(direct_full_tensor_rank(source,cut),32)
        count,_=compile_ground(source,'#SAT')
        self.assertTrue(verify(source,count))
        self.assertEqual(int(count['result']['count']),48)
        self.assertEqual(direct_source_count(source),48)

    def test_rank_decrease_by_added_clause(self):
        source,cut=make_one_clause_source(4,1,'cross-cross')
        cert,_=compile_ground(source,'CUT_RANK',cut)
        self.assertTrue(verify(source,cert))
        self.assertEqual(int(cert['result']['rank']),12)
        self.assertEqual(cert['result']['rank_ratio'],[3,4])
        self.assertEqual(direct_full_tensor_rank(source,cut),12)
        count,_=compile_ground(source,'#SAT')
        self.assertEqual(int(count['result']['count']),48)
        self.assertEqual(direct_source_count(source),48)

    def test_rank_unchanged_despite_removed_models(self):
        source,cut=make_one_clause_source(4,1,'left-cross')
        cert,_=compile_ground(source,'CUT_RANK',cut)
        self.assertTrue(verify(source,cert))
        self.assertEqual(cert['result']['rank_ratio'],[1,1])
        self.assertEqual(direct_full_tensor_rank(source,cut),16)
        cnt,_=compile_ground(source,'#SAT')
        self.assertEqual(int(cnt['result']['count']),48)

    def test_multiple_cuts_and_intentions(self):
        for kind in ('none','left-right','left-cross','cross-cross','right-cross'):
            source,_=make_one_clause_source(4,1,kind)
            direct=direct_source_count(source)
            for intent in ('SAT','#SAT'):
                g,_=compile_ground(source,intent)
                self.assertTrue(verify(source,g))
                self.assertEqual(g['result']['status'],'SAT')
                if intent=='#SAT':self.assertEqual(int(g['result']['count']),direct)
                else:self.assertTrue(source_accepts(source,g['result']['witness']))
            for size in (1,2,3):
                for cut in itertools.combinations(range(4),size):
                    g,_=compile_ground(source,'CUT_RANK',list(cut))
                    self.assertTrue(verify(source,g))
                    self.assertEqual(int(g['result']['rank']),direct_full_tensor_rank(source,cut))

    def test_unsat_and_tautological_lift(self):
        source,_=make_one_clause_source(4,1,'none')
        v=source['base']['nodes'][0][0]
        source['coupling']=[[v],[-v]]
        for intent in ('SAT','#SAT','CUT_RANK'):
            g,_=compile_ground(source,intent,[0,1] if intent=='CUT_RANK' else None)
            self.assertTrue(verify(source,g))
            if intent=='CUT_RANK':self.assertEqual(int(g['result']['rank']),0)
            else:self.assertEqual(g['result']['status'],'UNSAT')
        source,_=make_one_clause_source(4,1,'none')
        pair=analyze(source['base'])['pairs'][0]
        source['coupling']=[[pair[0],-pair[1]]]
        cnt,_=compile_ground(source,'#SAT')
        self.assertTrue(verify(source,cnt))
        self.assertEqual(int(cnt['result']['count']),64)

    def test_original_clause_tampering_and_forged_ground(self):
        source,cut=make_one_clause_source(4,1,'left-right')
        c,_=compile_ground(source,'CUT_RANK',cut)
        for field,value in [('result',{'rank':'32'}),('active_labels',[]),('source_digest','fake'),('label_pairs',[]),('work',{})]:
            forged=copy.deepcopy(c);forged[field]=value
            with self.assertRaises(VerificationFailure):verify(source,forged)
        changed=copy.deepcopy(source)
        changed['coupling'][0][1]*=-1
        with self.assertRaises(VerificationFailure):verify(changed,c)
        changed=copy.deepcopy(source)
        changed['base']['clauses'].pop()
        with self.assertRaises((GroundRefusal,VerificationFailure)):
            compile_ground(changed,'#SAT')
            verify(changed,c)

    def test_budgets_and_invalid_intentions(self):
        source,cut=make_one_clause_source(6,1,'none')
        proof=analyze(source['base'])
        source['coupling']=[[pair[0]] for pair in proof['pairs'][:15]]
        with self.assertRaises(GroundRefusal):compile_ground(source,'#SAT')
        source['coupling']=[]
        for invalid in ([-1],[0,0],[0,6],[]):
            with self.assertRaises(GroundRefusal):compile_ground(source,'CUT_RANK',invalid)
        with self.assertRaises(GroundRefusal):compile_ground(source,'#SAT',[0,1])
        with self.assertRaises(GroundRefusal):compile_ground(source,'UNKNOWN')

    def test_large_symbolic_coupling(self):
        for k,ell in ((12,1),(24,2)):
            for kind,ratio in (('cross-cross',[3,4]),('left-right',[2,1]),('left-cross',[1,1])):
                source,cut=make_one_clause_source(k,ell,kind)
                cert,_=compile_ground(source,'CUT_RANK',cut)
                self.assertTrue(verify(source,cert))
                self.assertEqual(cert['result']['rank_ratio'],ratio)
                cnt,_=compile_ground(source,'#SAT')
                self.assertTrue(verify(source,cnt))
                self.assertEqual(int(cnt['result']['count']),3*(1<<(len(analyze(source['base'])['pairs'])-2)))

    def test_random_extra_clauses_exhaustive(self):
        rng=random.Random(73)
        for i in range(45):
            src,_=make_one_clause_source(4,1,'none')
            proof=analyze(src['base'])
            ids=[p[rng.randrange(2)] for p in proof['pairs']]
            src['coupling']=[[rng.choice((-1,1))*ids[j] for j in rng.sample(range(6),rng.randint(1,3))]
                             for _ in range(rng.randrange(0,5))]
            cnt,_=compile_ground(src,'#SAT')
            self.assertTrue(verify(src,cnt))
            self.assertEqual(int(cnt['result']['count']),direct_source_count(src))
            for cut in ((0,1),(0,2)):
                rank,_=compile_ground(src,'CUT_RANK',cut)
                self.assertTrue(verify(src,rank))
                self.assertEqual(int(rank['result']['rank']),direct_full_tensor_rank(src,cut))

if __name__=='__main__':unittest.main()
