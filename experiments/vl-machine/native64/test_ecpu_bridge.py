import copy
import tempfile
import unittest
from pathlib import Path
from capsule import sha
from test_capsule import Capsule
from ecpu_bridge import run_worker,admit_runtime,profile,Adapter,OP

class Bridge(unittest.TestCase):
    def test_fresh_worker(self):
        root=Path(__file__).resolve().parent
        for kind in (1,2):
            cap,expected=Capsule().fixture(kind)
            self.assertEqual(run_worker(root,cap)['observation'],expected)
            bad=copy.deepcopy(cap);bad['body']['witness'][1]^=1;bad['sha256']=sha(bad['body'])
            import subprocess
            with self.assertRaises(subprocess.CalledProcessError):run_worker(root,bad)
    def test_real_ecpu_m2(self):
        from mailcpu.computational_host import LocalComputationalHost,ComputationalHostRequest,ComputationalBackendError
        with tempfile.TemporaryDirectory() as tmp:
            manifest,root=admit_runtime(Path(tmp)/'artifact')
            host=LocalComputationalHost(host_id='vlm-a',manifest=manifest,artifact_root=root,profile=profile(manifest),adapter=Adapter())
            receiver=LocalComputationalHost(host_id='vlm-b',manifest=manifest,artifact_root=root,profile=profile(manifest),adapter=Adapter())
            cap,expected=Capsule().fixture(2)
            def req(operation=OP,capsule=cap):return ComputationalHostRequest(request_id='observe-1',artifact_manifest_digest=manifest.manifest_digest,operation=operation,input_value={'capsule':capsule},logical_time=1,workload_id='vlm-test')
            a=host.execute(req());b=receiver.execute(req())
            self.assertEqual(a.output['observation'],expected);self.assertEqual(a.output,b.output)
            self.assertEqual(a.receipt.output_digest,b.receipt.output_digest)
            self.assertEqual(a.receipt.artifact_manifest_digest,manifest.manifest_digest)
            self.assertEqual(a.receipt.backend_fingerprint,profile(manifest).fingerprint)
            self.assertEqual(a.receipt.status,'EXECUTED')
            with self.assertRaises(ComputationalBackendError):host.execute(req('python.eval'))
            bad=copy.deepcopy(cap);bad['body']['witness'][1]^=1;bad['sha256']=sha(bad['body'])
            with self.assertRaises(ComputationalBackendError):host.execute(req(capsule=bad))
            (root/'capsule.py').write_text('tampered')
            with self.assertRaises(ComputationalBackendError):host.execute(req())
            host.unload();receiver.unload()

if __name__=='__main__':unittest.main()
