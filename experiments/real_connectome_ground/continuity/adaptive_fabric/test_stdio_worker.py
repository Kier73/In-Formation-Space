"""One real host boundary: subprocess stdio and a receiver-owned source pin."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:sys.path.insert(0,str(BASE))
if str(BASE/'continuity') not in sys.path:sys.path.insert(0,str(BASE/'continuity'))
from connectome_ground import Query, canonical
from test_connectome_ground import small_ground, ACTUAL_SOURCE_ROWS
from adaptive_fabric.fabric_policy import (
    Workload, candidates, canonical_hash, fit, navigate, training_data,
    synthesize_workloads,
)
from adaptive_fabric.receiver_stdio import receive


class StdIOBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.ground = small_ground()
        tasks = synthesize_workloads(self.ground, 14, seed=91)
        self.model = fit(self.ground, training_data(self.ground, tasks, seed=92))
        self.workload = Workload.from_ground(self.ground, Query('AWCL','AIYL',2))
        self.path = [p for p in candidates() if p.host == 'local-worker' and p.method=='cone']
        self.selected = navigate(self.model, self.ground, self.workload, self.path,
                                 {'local-worker': 0})
        self.request = {'schema':'ifs.rcg003.fabric-adaptation.v1.request.v1',
                        'ground':self.ground.fingerprint,
                        'workload':self.workload.describe(), 'selection': self.selected}
        self.source = ACTUAL_SOURCE_ROWS.encode()
        self.source_sha = hashlib.sha256(self.source).hexdigest()

    def test_actual_fresh_subprocess_observes_exact_source(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'connectome.csv'
            path.write_bytes(self.source)
            worker=Path(__file__).with_name('receiver_stdio.py')
            args=[sys.executable, str(worker),'--source',str(path),
                  '--expected-source-sha256',self.source_sha,'--fixture']
            r=subprocess.run(args,input=canonical(self.request),capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr.decode())
            received=json.loads(r.stdout)
            self.assertEqual(received['medium'],'local-ipc')
            self.assertEqual(received['status'],
                             'separate-interpreter-observation; no-network-mtls-authority')
            self.assertEqual(received['verified']['transfer'],str(self.ground.verify(self.ground.plan(Query('AWCL','AIYL',2)),
                                                    self.ground.run(self.ground.plan(Query('AWCL','AIYL',2))))))
            self.assertEqual(received['digest'],canonical_hash({k:v for k,v in received.items() if k!='digest'}))
            # Re-enter as a new process with the same retained Ground: semantic identity.
            again=subprocess.run(args,input=canonical(self.request),capture_output=True,timeout=30)
            self.assertEqual(again.returncode,0,again.stderr.decode())
            self.assertEqual(r.stdout,again.stdout)
            wrong=subprocess.run(args[:-2]+['0'*64,'--fixture'],input=canonical(self.request),
                                 capture_output=True,timeout=30)
            self.assertNotEqual(wrong.returncode,0)
            self.assertIn(b'REFUSED:',wrong.stderr)

    def test_receivers_refuse_other_path_and_changed_source(self):
        request=dict(self.request)
        selection=dict(self.selected)
        selection['chosen']=candidates()[2].to_dict()
        selection['digest']=canonical_hash({k:v for k,v in selection.items() if k!='digest'})
        request['selection']=selection
        with self.assertRaises(ValueError):
            receive(self.source,canonical(request),expected_source_sha256=self.source_sha,
                    require_original=False)
        with self.assertRaises(ValueError):
            receive(self.source+b'X',canonical(self.request),
                    expected_source_sha256=self.source_sha,require_original=False)


if __name__=='__main__':unittest.main()
