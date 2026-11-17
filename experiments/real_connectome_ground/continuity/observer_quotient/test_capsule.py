"""Separate-receiver-process compatibility and tamper refusal."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_observer_quotient import FIXTURE

CLI=Path(__file__).resolve().with_name('capsule.py')


class PortableObserverTests(unittest.TestCase):
    def test_three_independent_processes_and_source_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            source=d/'observed-source.csv';source.write_text(FIXTURE)
            pinned=hashlib.sha256(source.read_bytes()).hexdigest()
            cert=d/'cert.json';verified=d/'verified.json';query=d/'query.json';replayed=d/'replayed.json'
            basis=[sys.executable,str(CLI)]
            shared=['--source',str(source),'--expected-source-sha256',pinned,'--fixture']
            def go(action,out,extras=(),success=True):
                proc=subprocess.run([*basis,action,*shared,*extras,'--out',str(out)],
                                    capture_output=True,text=True,timeout=30)
                if success:
                    self.assertEqual(proc.returncode,0,proc.stderr)
                else:
                    self.assertEqual(proc.returncode,2,proc.stderr)
                return proc
            go('train',cert,['--groups','8','--copies','32','--seed','11'])
            go('verify',verified,['--certificate',str(cert)])
            verified_doc=json.loads(verified.read_text())
            self.assertEqual(verified_doc['checked_micro_columns'],256)
            go('query',query,['--certificate',str(cert),'--micro-source','19','--tick',str(2**56+73)])
            go('replay',replayed,['--certificate',str(cert),'--receipt',str(query)])
            self.assertIn('independently-recomputed',json.loads(replayed.read_text())['status'])
            tampered=json.loads(query.read_text())
            tampered['neural_result']['nonlinear_readout']=(tampered['neural_result']['nonlinear_readout']+1)%1000000007
            tampered['digest']='0'*64
            bad=d/'bad-receipt.json';bad.write_text(json.dumps(tampered))
            go('replay',d/'rejected.json',['--certificate',str(cert),'--receipt',str(bad)],success=False)
            unpinned=[*basis,'verify','--source',str(source),'--expected-source-sha256','0'*64,
                      '--fixture','--certificate',str(cert),'--out',str(d/'not_admitted.json')]
            process=subprocess.run(unpinned,capture_output=True,text=True,timeout=30)
            self.assertEqual(process.returncode,2)
            self.assertIn('source SHA-256',process.stderr)
            malicious=cert.read_text().replace('"schema":','"schema":"injected","schema":',1)
            dupe=d/'duplicate.json';dupe.write_text(malicious)
            go('verify',d/'refused-duplicate.json',['--certificate',str(dupe)],success=False)


if __name__=='__main__':
    unittest.main()
