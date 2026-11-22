"""BENCH-01F: adversarial policy proof, source identity, disjoint-cohort tests."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import random
import unittest
from unittest.mock import patch

from bench01_3sat import exhaustive_reference, satisfies, sha as source_hash
from bench01_policy import (
 SCHEMA, RULES, _satisfies_meta, _satisfiable_mask,
 _validate_observation, _encode_or, audit_policy, evaluate_final,
 meta_problem, selection, source_features, train_policy,validate_and_freeze)
from run_bench01_policy import catalog, verify_bytes, obtain


def sample(name, n, clauses, formed, direct, tf=10., td=100.):
    # Tests only use actual small SAT/UNSAT semantics or original-source SAT witnesses.
    src = exhaustive_reference(n, clauses, maximum_vars=14) if n<=14 else None
    if src and src["status"] == "SAT":
        witness = next(str(i) for i in range(1 << n) if satisfies(clauses,i))
    elif src and src["status"] == "UNSAT":
        witness = None
    else:
        # Larger source is kept trivially satisfiable for direct source-witness validation.
        assert satisfies(clauses,0)
        witness="0"
    def report(status,ms):
        return {"status":status,"wall_ms":float(ms),"witness":witness if status=="SAT" else None,
                "source_checked":True,"proof":None}
    return {"id":name,"n":n,"clauses":clauses,
      "source_sha256":source_hash({"n":n,"clauses":clauses}),
      "formed":report(formed,tf),"direct":report(direct,td)}


def large(name,seed,tf=100.,td=10.):
    # Balanced planted SAT with no unit, using only negated literals; x=0 is a witness.
    rng=random.Random(seed)
    n=28
    rows=[]
    for i in range(145):
        scope=rng.sample(range(1,n+1),3)
        rows.append([-scope[0],-scope[1],-scope[2]])
    return sample(name,n,rows,"SAT","SAT",tf,td)


def small(name,j,tf=10.,td=110.):
    # Distinct source hashes and same source-only feature structure.
    n=11
    a=j%11+1
    b=((j//11+j%10+1)%11)+1
    clauses=[[a],[-b,a]]
    return sample(name,n,clauses,"SAT","SAT",tf,td)


class SourceAndFeatureTests(unittest.TestCase):
    def test_features_exclude_hidden_sat_outcome(self):
        a=[[1,2,3],[-1,-2,-3]]
        b=[[1,2,3],[1,2,3]]
        feats,_=source_features(3,a)
        self.assertEqual(set(feats),set(RULES))
        self.assertTrue(source_features(3,b)[0]["repeated_scope"])
        self.assertFalse(source_features(3,[[1,2,3]])[0]["repeated_scope"])

    def test_pinned_sources_and_strict_file_identity(self):
        entries=catalog()
        self.assertEqual(len(entries),12)
        self.assertEqual({x['cohort'] for x in entries},{'training','validation','final'})
        self.assertEqual(len({x['path'] for x in entries}),12)
        self.assertTrue(all(len(x['blob_sha1'])==40 for x in entries))
        with self.assertRaises(ValueError):
            obtain({**entries[0],'blob_sha1':'0'*40},__import__('pathlib').Path('/tmp'))
        with self.assertRaises(ValueError):
            verify_bytes(b'p cnf 1 1\n1 0\n',entries[0])

    def test_tampered_witness_or_source_digest_refused(self):
        x=small('x',1)
        self.assertTrue(_validate_observation(x))
        f=deepcopy(x); f['formed']['witness']='0'
        with self.assertRaises(ValueError):_validate_observation(f)
        f=deepcopy(x);f['source_sha256']='0'*64
        with self.assertRaises(ValueError):_validate_observation(f)

    def test_forged_unsat_refused_even_with_source_checked_flag(self):
        x=small('x',1)
        x['formed']={'status':'UNSAT','wall_ms':1.,'witness':None,'proof':None,'source_checked':True}
        with self.assertRaises(ValueError):_validate_observation(x)
        y=large('y',33)
        y['direct']={'status':'UNSAT','wall_ms':1.,'witness':None,'proof':None,'source_checked':True}
        with self.assertRaises(ValueError):_validate_observation(y)

    def test_unknown_remains_unknown_and_carries_no_answer(self):
        x=small('x',1)
        x['formed']={'status':'UNKNOWN','wall_ms':3.,'witness':None,'proof':None,'source_checked':True}
        self.assertTrue(_validate_observation(x))
        x['formed']['witness']='0'
        with self.assertRaises(ValueError):_validate_observation(x)


class MetaSATTests(unittest.TestCase):
    def setUp(self):
        self.train=[small('a',0),small('b',2),large('c',3),large('d',5)]

    def test_constructed_meta_sat_is_3cnf(self):
        m=meta_problem(self.train)
        self.assertTrue(all(len(row)<=3 for row in m['clauses']))
        self.assertLessEqual(m['n'],16)
        self.assertEqual(m['n']>=len(RULES),True)
        self.assertTrue(any(_satisfiable_mask(m,i) for i in range(1<<len(RULES)) if i.bit_count()<=2))

    def test_tseitin_OR_has_exact_truth_table(self):
        clauses=[]
        n=_encode_or(clauses,[1,2,3,4,5,6],7)-1
        self.assertLessEqual(n,16)
        for mask in range(64):
            witness=any(_satisfies_meta(clauses,mask|(aux<<6)) for aux in range(1<<(n-6)))
            self.assertEqual(witness,mask!=0)

    def test_own_sat_solver_chooses_source_guard_and_is_audited(self):
        policy=train_policy(self.train)
        self.assertTrue(audit_policy(policy,self.train))
        self.assertTrue(policy['selected_rules'])
        self.assertEqual(selection(policy,small('heldout',3)['n'],small('heldout',3)['clauses'])[0], 'formed')
        self.assertEqual(selection(policy,large('heldout-large',8)['n'],large('heldout-large',8)['clauses'])[0], 'direct')
        self.assertIn(policy['meta']['backend'],('SPN-008-verified-DPLL/XOR','complete-exhaustive-meta-oracle'))

    def test_tampered_meta_proof_or_rule_rejected(self):
        policy=train_policy(self.train)
        f=deepcopy(policy);f['meta']['result']='UNSAT'; f['digest']=__import__('bench01_policy')._hash({k:v for k,v in f.items() if k!='digest'})
        with self.assertRaises(ValueError):audit_policy(f,self.train)
        f=deepcopy(policy); f['selected_rules']=[]
        f['digest']=__import__('bench01_policy')._hash({k:v for k,v in f.items() if k!='digest'})
        with self.assertRaises(ValueError):audit_policy(f,self.train)

    def test_duplicate_sources_forbidden_in_training_and_validation(self):
        with self.assertRaises(ValueError):meta_problem(self.train+[self.train[0]])
        p=train_policy(self.train)
        with self.assertRaises(ValueError):validate_and_freeze(p,self.train,[self.train[0]])

    def test_qualified_validation_can_admit_without_coverage_loss(self):
        policy=train_policy(self.train)
        valid=[small('v'+str(j),j) for j in range(12,20)]+[large('g',8),large('h',9)]
        frozen=validate_and_freeze(policy,self.train,valid)
        self.assertEqual(frozen['admission'],'ADMITTED')
        self.assertTrue(frozen['selected_rules'])
        self.assertEqual(frozen['validation']['coverage_losses'],0)
        final=[small('i',22),large('j',11)]
        test=evaluate_final(frozen,self.train,valid,final)
        self.assertEqual(test['coverage_losses'],0)
        self.assertLess(test['selected_total_ms'],test['direct_total_ms'])

    def test_rejected_policy_reverts_to_direct(self):
        policy=train_policy(self.train)
        valid=[small('e',3,tf=200.,td=5.),small('f',4,tf=180.,td=5.),large('g',8)]
        frozen=validate_and_freeze(policy,self.train,valid)
        self.assertEqual(frozen['admission'],'REJECTED')
        self.assertEqual(frozen['selected_rules'],[])
        self.assertTrue(__import__('bench01_policy').audit_policy(frozen,self.train))

    def test_out_of_sample_source_leakage_refused(self):
        policy=train_policy(self.train)
        with self.assertRaises(ValueError):selection(policy,self.train[0]['n'],self.train[0]['clauses'])

    def test_policy_never_elevates_unknown_to_sat_or_unsat(self):
        t=[small('u',3,tf=10.,td=50.),large('v',10)]
        t[0]['formed']={'status':'UNKNOWN','wall_ms':10.,'witness':None,'proof':None,'source_checked':True}
        policy=train_policy(t)
        self.assertTrue(audit_policy(policy,t))
        self.assertFalse(policy['selected_rules'])

if __name__=='__main__': unittest.main()
