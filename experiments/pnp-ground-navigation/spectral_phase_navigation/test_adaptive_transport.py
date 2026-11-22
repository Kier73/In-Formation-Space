"""Round-trip a proof through an independent process, with tamper rejection."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from adaptive_ground_compiler import produce_adaptive_receipt
from test_direct_sum_grounds import shared_variable_cycle_cnf

CHECKER=Path(__file__).with_name('verify_adaptive_json.py')


def envelope(clauses,n,receipt):
    return {'n':n,'clauses':[{'variables':list(v),'forbidden':list(f)}
                                 for v,f in clauses],'receipt':receipt}


def check_subprocess(payload):
    return subprocess.run([sys.executable,str(CHECKER)],
        input=json.dumps(payload,separators=(',',':')),text=True,capture_output=True,
        timeout=15,check=False)


class PortableReceiptTests(unittest.TestCase):
    def test_transportable_exact_unsat_certificate(self):
        clauses,n=shared_variable_cycle_cnf(16)
        receipt=produce_adaptive_receipt(clauses,n,goal='exact_ground',rank_cap=2)
        process=check_subprocess(envelope(clauses,n,receipt))
        self.assertEqual(process.returncode,0,process.stderr)
        output=json.loads(process.stdout)
        self.assertEqual(output['result'],'UNSAT')
        self.assertEqual(output['ground_energy'],[16,1])
        self.assertTrue(output['verified'])

    def test_source_mismatch_and_proof_tampering_refused(self):
        clauses,n=shared_variable_cycle_cnf(2)
        receipt=produce_adaptive_receipt(clauses,n,goal='exact_ground',rank_cap=2)
        payload=envelope(clauses,n,receipt)
        bad=copy.deepcopy(payload)
        bad['clauses'][0]['forbidden']=[1,1,1]
        process=check_subprocess(bad)
        self.assertEqual(process.returncode,2)
        self.assertFalse(json.loads(process.stderr)['verified'])
        bad=copy.deepcopy(payload)
        bad['receipt']['proof']['receipt']['ground_energy']=[0,1]
        process=check_subprocess(bad)
        self.assertEqual(process.returncode,2)
        self.assertFalse(json.loads(process.stderr)['verified'])

    def test_unknown_transport_is_not_a_verified_unsat_proof(self):
        from random import Random
        rng=Random(772)
        clauses=[(tuple(rng.sample(range(12),3)),tuple(rng.randrange(2) for _ in range(3))) for _ in range(45)]
        receipt=produce_adaptive_receipt(clauses,12,goal='exact_ground',rank_cap=2)
        self.assertEqual(receipt['result'],'UNKNOWN')
        process=check_subprocess(envelope(clauses,12,receipt))
        self.assertEqual(process.returncode,0,process.stderr)
        output=json.loads(process.stdout)
        self.assertEqual(output['result'],'UNKNOWN')
        self.assertFalse(output['verified'])

if __name__=='__main__':
    unittest.main()
