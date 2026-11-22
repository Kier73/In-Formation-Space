"""BENCH-01 adversarial, native integration and independent source reference tests."""
from __future__ import annotations

from pathlib import Path
import gzip
import json
import lzma
import random
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import bench01_3sat as b


class TestDIMACS(unittest.TestCase):
    def test_multiline_header_comments_round_trip(self):
        source=b"c test source\np cnf 4 3\nc marker\n1 -2\n 3 0\n-1 0\n2 4 0\n"
        item=b.parse_dimacs(source)
        self.assertEqual(item["n"],4)
        self.assertEqual(item["clauses"],[[1,-2,3],[-1],[2,4]])
        self.assertEqual(b.parse_dimacs(b.as_dimacs(item["n"],item["clauses"]))["clauses"],item["clauses"])
        self.assertEqual(item["bytes_sha256"],__import__('hashlib').sha256(source).hexdigest())

    def test_rejects_malformed_and_oversized(self):
        malformed=[b"1 -1 0",b"p cnf 2 1\n1 0\n2 0\n",
                   b"p cnf 2 2\n1 0",b"p cnf 2 1\n3 0",
                   b"p cnf 2 1\n1",b"p cnf 2 1\nx 0",
                   b"p cnf 2 1\n1 0\np cnf 2 0",
                   b"p cnf 2 1\n1 1 1 1 0"]
        for source in malformed:
            with self.subTest(source=source),self.assertRaises(ValueError):
                b.parse_dimacs(source)
        with self.assertRaises(ValueError):
            b.parse_dimacs(b"p cnf 1 0\n",max_bytes=3)

    def test_gzip_xz_bounded_and_corpus(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)
            data=b.as_dimacs(3,[[1],[-1,2]])
            (home/'a.cnf').write_bytes(data)
            (home/'b.cnf.gz').write_bytes(gzip.compress(data))
            (home/'c.cnf.xz').write_bytes(lzma.compress(data))
            (home/'malformed.cnf').write_bytes(b'p cnf 1 1\nx 0\n')
            for name in ('a.cnf','b.cnf.gz','c.cnf.xz'):
                self.assertEqual(b.read_cnf_file(home/name),data)
            with self.assertRaises(ValueError):
                b.read_cnf_file(home/'c.cnf.xz',max_bytes=4)
            cp=subprocess.run([__import__('sys').executable,str(Path(b.__file__)),
                'corpus',str(home),'--limit','4'],capture_output=True,text=True,timeout=20)
            self.assertEqual(cp.returncode,1)  # invalid input causes visible failure
            ans=json.loads(cp.stdout)
            self.assertEqual(ans['summary']['SAT'],3)
            self.assertEqual(ans['summary']['ERROR'],1)

    def test_conversion_is_equisatisfiable_on_original_variables(self):
        rng=random.Random(29)
        for i in range(35):
            n=6
            clauses=[]
            for _ in range(rng.randint(1,4)):
                names=rng.sample(range(1,n+1),rng.randint(1,6))
                clauses.append([v if rng.randrange(2) else -v for v in names])
            transformed_n,transformed=b.to_three_cnf(n,clauses)
            self.assertTrue(all(len(c)<=3 for c in transformed))
            self.assertLessEqual(transformed_n,n+12)
            for src in range(1<<n):
                original=b.satisfies(clauses,src)
                possible=any(b.satisfies(transformed,src|(x<<n))
                             for x in range(1<<(transformed_n-n)))
                self.assertEqual(original,possible,msg=f'instance {i}, assignment {src}')

    def test_empty_clause_and_tautology_exact(self):
        n=3
        original=[[1,-1],[2],[]]
        self.assertEqual(b.exhaustive_reference(n,original)['status'],'UNSAT')
        converted_n,converted=b.to_three_cnf(n,original)
        self.assertEqual(converted_n,n)
        self.assertIn([],converted)


class TestReferenceAndGeneration(unittest.TestCase):
    def test_parity_source_and_pigeonhole(self):
        for rhs in (0,1):
            clauses=b.parity3(1,2,3,rhs)
            self.assertEqual(len(clauses),4)
            for bits in range(8):
                self.assertEqual(b.satisfies(clauses,bits),bool(((bits&1)^((bits>>1)&1)^((bits>>2)&1))==rhs))
        n,c=b.pigeonhole(3,2)
        self.assertEqual(b.exhaustive_reference(n,c)['status'],'UNSAT')
        n,c=b.coloring_clique(4)
        self.assertEqual(b.exhaustive_reference(n,c)['status'],'UNSAT')
        for item in b.suite():
            self.assertTrue(all(len(row)<=3 for row in item['clauses']))
            if item.get('known_witness') is not None:
                self.assertTrue(b.satisfies(item['clauses'],int(item['known_witness'])))

    def test_sat_native_qualified_against_independent_reference(self):
        for item in b.suite()[:8]:
            with self.subTest(id=item['id']):
                ans=b.run_case(item,timeout=6)
                self.assertIn(ans['status'],('SAT','UNSAT','UNKNOWN'))
                self.assertNotEqual(ans['status'],'ERROR')
                if ans['reference_status']!='NOT_RUN' and ans['status']!='UNKNOWN':
                    self.assertEqual(ans['reference_status'],ans['status'])
                if ans['status']=='SAT':
                    self.assertTrue(b.satisfies(item['clauses'],int(ans['witness'])))

    @unittest.skipUnless((b.SOURCE_DIR/'spectral_phase_navigation'/'direct_sat_compiler.py').is_file(),
                         'SPN-008 predecessor not installed in the local copy')
    def test_spn008_qualified_fallback(self):
        # This is the actual IFS SPN-008 module; no replacement solver stub.
        for name,expected in [('planted-3sat-24','SAT'),('php-5-into-4','UNSAT')]:
            item=next(x for x in b.suite() if x['id']==name)
            result=b.run_case(item,spn_fallback=True,timeout=16,spn_nodes=8192)
            self.assertEqual(result['status'],expected)
            self.assertIn('spn-008',result['selected'])
            self.assertTrue(result['spn_original_proof_verified'])
            if expected=='SAT':
                self.assertTrue(b.satisfies(item['clauses'],int(result['witness'])))

    def test_unknown_is_never_unsat(self):
        item=next(x for x in b.suite() if x['id']=='planted-3sat-24')
        ans=b.run_case(item,max_source_vars=12)
        self.assertEqual(ans['status'],'UNKNOWN')
        self.assertEqual(ans['reason'],'native-input-admission-budget')
        self.assertIsNone(ans.get('witness'))

    def test_composite_reassembles_source_witness(self):
        item={'id':'split-sat','n':6,'clauses':[[1],[-2,3],[4],[5,-6]]}
        ans=b.run_case(item,composite=True,timeout=9)
        self.assertEqual(ans['status'],'SAT')
        self.assertTrue(b.satisfies(item['clauses'],int(ans['witness'])))
        self.assertIn('composite:',ans['selected'])

    def test_self_refining_path_is_source_qualified(self):
        item={'id':'meta-control','n':4,'clauses':[[1,-2],[-1,3],[4,-3]]}
        ans=b.run_case(item,self_refine=True,timeout=9)
        self.assertEqual(ans['status'],'SAT')
        self.assertTrue(b.satisfies(item['clauses'],int(ans['witness'])))


class TestRefusals(unittest.TestCase):
    def setUp(self):
        self.example={'id':'guard','n':3,'clauses':[[1],[2,-3]]}

    def test_malicious_native_sat_witness_rejected(self):
        forged=subprocess.CompletedProcess(args=[],returncode=0,
            stdout=json.dumps({'status':'SAT','witness':'0'}),stderr='')
        with patch.object(b.subprocess,'run',return_value=forged):
            with self.assertRaisesRegex(ValueError,'SAT witness'):
                b.run_case(self.example)

    def test_invalid_native_witness_encoding_rejected(self):
        with self.assertRaises(ValueError):
            b.normalize_native_witness([1,0],3)
        with self.assertRaises(ValueError):
            b.normalize_native_witness('01',3)
        with self.assertRaises(ValueError):
            b.normalize_native_witness([1,0,2],3)

    def test_false_native_unsat_rejected(self):
        forged=subprocess.CompletedProcess(args=[],returncode=0,
            stdout=json.dumps({'status':'UNSAT','witness':None}),stderr='')
        with patch.object(b.subprocess,'run',return_value=forged):
            with self.assertRaisesRegex(ValueError,'independent exhaustive'):
                b.run_case(self.example)

    def test_false_large_native_unsat_downgraded_without_parent_proof(self):
        large={'id':'large-guard','n':17,'clauses':[[1,2,3]]}
        forged=subprocess.CompletedProcess(args=[],returncode=0,
            stdout=json.dumps({'status':'UNSAT','selected':'local-Boolean-functions',
                'checked':131072,'witness':None}),stderr='')
        with patch.object(b.subprocess,'run',return_value=forged):
            ans=b.run_case(large)
            self.assertEqual(ans['status'],'UNKNOWN')
            self.assertIn('without-parent-checkable',ans['reason'])

    def test_worker_spn_proof_claim_requires_original_certificate(self):
        forged=subprocess.CompletedProcess(args=[],returncode=0,
            stdout=json.dumps({'status':'UNSAT','selected':'spn-008-source-verified',
                'spn_original_proof_verified':True,'witness':None}),stderr='')
        with patch.object(b.subprocess,'run',return_value=forged):
            with self.assertRaisesRegex(ValueError,'falsely claimed'):
                b.run_case(self.example)

    def test_forged_empty_clause_label_requires_real_source_clause(self):
        forged=subprocess.CompletedProcess(args=[],returncode=0,
            stdout=json.dumps({'status':'UNSAT','selected':'source-empty-clause',
                'witness':None}),stderr='')
        with patch.object(b.subprocess,'run',return_value=forged):
            with self.assertRaisesRegex(ValueError,'not present'):
                b.run_case(self.example)

    def test_timeout_produces_unknown(self):
        with patch.object(b.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',0.01)):
            ans=b.run_case(self.example,timeout=0.01)
            self.assertEqual(ans['status'],'UNKNOWN')
            self.assertEqual(ans['verification'],'no-decision-claim')

    def test_bad_expected_source_witness_is_refused_before_execution(self):
        item={**self.example,'known_witness':'0'}
        with self.assertRaisesRegex(ValueError,'planted witness'):
            b.run_case(item)

    def test_unsat_empty_clause_is_verified_syntactically(self):
        item={'id':'empty','n':10,'clauses':[[]]}
        ans=b.run_case(item,timeout=6)
        self.assertEqual(ans['status'],'UNSAT')
        self.assertEqual(ans['verification'],'source-empty-clause')

    def test_huge_problem_refuses_fast_without_bogus_result(self):
        item={'id':'huge','n':1200,'clauses':[[1,2,3]]}
        ans=b.run_case(item,max_source_vars=64)
        self.assertEqual(ans['status'],'UNKNOWN')
        self.assertIn('admission',ans['reason'])


if __name__=='__main__':
    unittest.main()
