"""Strict DIMACS and portable receipt controls, including a second process."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from direct_sat_cli import parse_dimacs
from direct_sat_compiler import produce_direct_sat

class DirectSatCliTests(unittest.TestCase):
    def test_multiline_clause_and_comments(self):
        clauses,n=parse_dimacs('c example\np cnf 3 2\n1 -2\n3 0\nc after\n-1 0\n')
        self.assertEqual((clauses,n), ([(1,-2,3),(-1,)],3))

    def test_bad_headers_and_clauses(self):
        bad=['', '1 0', 'p cnf 3 1\n1', 'p cnf 3 1\n4 0',
             'p cnf 3 2\n1 0','p cnf 3 1\n1 2 3 4 0',
             'p cnf 3 1\n1 0\n2 0','p cnf 3 0\np cnf 3 0',
             'p cnf a 0','p cnf 3 1\n2 1 x 0']
        for text in bad:
            with self.subTest(text=text),self.assertRaises(ValueError):parse_dimacs(text)

    def test_cross_process_round_trip_and_forgery(self):
        root=Path(__file__).resolve().parent
        source='c direct 3SAT\np cnf 3 8\n'+'\n'.join(' '.join(map(str,c))+' 0'
                 for c in [(1,2,3),(1,2,-3),(1,-2,3),(1,-2,-3),
                           (-1,2,3),(-1,2,-3),(-1,-2,3),(-1,-2,-3)])+'\n'
        with tempfile.TemporaryDirectory() as tmp:
            cnf=Path(tmp)/'case.cnf';receipt=Path(tmp)/'receipt.json'
            cnf.write_text(source)
            produce=subprocess.run([sys.executable,str(root/'direct_sat_cli.py'),
                                    str(cnf),'--out',str(receipt)],
                                   capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(produce.stdout)['verified_status'],'UNSAT')
            verified=subprocess.run([sys.executable,str(root/'direct_sat_cli.py'),
                                     str(cnf),'--verify',str(receipt)],
                                    capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(verified.stdout)['proof_kind'],'split')
            forged=json.loads(receipt.read_text());forged['proof']={'kind':'conflict'}
            receipt.write_text(json.dumps(forged))
            invalid=subprocess.run([sys.executable,str(root/'direct_sat_cli.py'),
                                    str(cnf),'--verify',str(receipt)],
                                   capture_output=True,text=True)
            self.assertNotEqual(invalid.returncode,0)

if __name__=='__main__':unittest.main()
