"""Source-bound CLI and serialized proof checks in a clean Python process."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class LanguageCliTests(unittest.TestCase):
    def test_count_and_decision_roundtrip(self):
        cli=Path(__file__).with_name('language_choice_cli.py')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            cnf=folder/'source.cnf'
            cnf.write_text('c source identity\np cnf 3 2\n1 2 3 0\n-1 2 3 0\n')
            for goal,expected in [('decision','SAT'),('count','6')]:
                out=folder/f'{goal}.json'
                produced=subprocess.run([sys.executable,str(cli),str(cnf),'--goal',goal,
                                          '--out',str(out)],capture_output=True,text=True,check=True)
                self.assertEqual(json.loads(produced.stdout)['result'],expected)
                checked=subprocess.run([sys.executable,str(cli),str(cnf),'--verify',str(out)],
                                       capture_output=True,text=True,check=True)
                self.assertEqual(json.loads(checked.stdout)['verified'],expected)
                bad=json.loads(out.read_text())
                bad['result']='UNSAT' if goal=='decision' else '9'
                out.write_text(json.dumps(bad))
                failing=subprocess.run([sys.executable,str(cli),str(cnf),'--verify',str(out)],
                                       capture_output=True,text=True)
                self.assertNotEqual(failing.returncode,0)

if __name__=='__main__':unittest.main()
