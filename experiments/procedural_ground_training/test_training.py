"""PGT-001 deterministic Ground and advisory-model verification."""
from __future__ import annotations
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import torch
from procedural_ground_training import World, exact_plan, encode, dataset, can_resolve, make_world, sha
from train_ground_model import restore, GroundStudent
from http_artifact_path import Refused, get_verified, server

RESULTS=Path(__file__).resolve().parent/'results'

class GroundTests(unittest.TestCase):
    def test_ready(self):
        w=World(((0,0,0),(0,0,1),(1,1,1)),(1,1,1),(2,3,4),17)
        self.assertEqual(exact_plan(w),0)
    def test_refusal_due_to_identical_observations(self):
        w=World(((0,0,0),(0,0,0)),(0,1),(2,3,4),17)
        self.assertEqual(exact_plan(w),8)
    def test_cheapest_correlated_measurement(self):
        w=World(((0,0,0),(1,1,0),(0,0,1),(1,1,1)),(0,1,0,1),(3,1,2),17)
        self.assertEqual(exact_plan(w),2)
    def test_pairwise_state_order_invariant(self):
        w=World(((0,0,0),(0,0,1),(1,1,1)),(1,0,1),(2,3,4),17)
        z=World(tuple(reversed(w.features)),tuple(reversed(w.targets)),w.costs,33)
        np.testing.assert_array_equal(encode(w),encode(z))
    def test_random_exact_sufficient(self):
        rng=np.random.default_rng(42)
        for k in range(250):
            w=make_world(rng,k)
            correct=exact_plan(w)
            if correct<8:self.assertTrue(can_resolve(w,correct))
            for mask in range(8):
                if can_resolve(w,mask):
                    cost=sum(w.costs[i] for i in range(3) if mask&(1<<i))
                    good_cost=sum(w.costs[i] for i in range(3) if correct&(1<<i)) if correct<8 else None
                    self.assertLessEqual(good_cost,cost)
    def test_training_report_and_independent_safety_gate(self):
        r=json.loads((RESULTS/'training-report.json').read_bytes())
        self.assertGreater(r['heldout_16']['accuracy'],0.95)
        self.assertGreater(r['heldout_32_ood']['accuracy'],0.90)
        self.assertEqual(r['split_identical_world_overlap'],0)
        self.assertGreater(r['unsafe_student_proposals_not_admitted'],0)
        # Validity is always checked by the exact Ground relation, not logits.
        rng=np.random.default_rng(4400)
        for k in range(50):
            world=make_world(rng,k)
            optimum=exact_plan(world)
            if optimum!=8:self.assertTrue(can_resolve(world,optimum))

    def test_neural_checkpoint_roundtrip_and_integrity(self):
        model, digest=restore(RESULTS)
        x,labels,_=dataset(5001,60)
        with torch.no_grad():
            a=model(torch.tensor(x)); b=model(torch.tensor(x))
        self.assertTrue(torch.equal(a,b))
        self.assertEqual(a.shape,(60,9))
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td);(dest/'ground_student.npz').write_bytes((RESULTS/'ground_student.npz').read_bytes())
            (dest/'manifest.json').write_bytes((RESULTS/'manifest.json').read_bytes())
            broken=bytearray((dest/'ground_student.npz').read_bytes()); broken[-30]^=1
            (dest/'ground_student.npz').write_bytes(broken)
            with self.assertRaises(ValueError):restore(dest)
    def test_http_two_local_origins_and_corruption(self):
        raw=(RESULTS/'ground_student.npz').read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td); a=path/'a';b=path/'b'
            for p in (a,b):
                (p/'objects').mkdir(parents=True)
                (p/'objects'/(digest+'.npz')).write_bytes(raw)
            processes=[]
            try:
                for root in (a,b):
                    child=subprocess.Popen([sys.executable,'-u',str(Path(__file__).parent/'http_artifact_path.py'),
                        '--root',str(root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                    assert child.stdout is not None
                    announced=child.stdout.readline().strip()
                    self.assertTrue(announced.startswith('LISTEN_PORT='),announced)
                    processes.append((child,f'http://127.0.0.1:{announced.split("=",1)[1]}/'))
                urls=[url for _,url in processes]
                data,origin,failures=get_verified(urls,digest)
                self.assertEqual(data,raw);self.assertEqual(origin,urls[0]);self.assertEqual(failures,[])
                # A fresh receiver loads the ACTUAL retrieved artifact, with the
                # publisher-independent manifest supplied from trusted local policy.
                with tempfile.TemporaryDirectory() as receiver:
                    receiver=Path(receiver)
                    (receiver/'ground_student.npz').write_bytes(data)
                    (receiver/'manifest.json').write_bytes((RESULTS/'manifest.json').read_bytes())
                    remote_model,_=restore(receiver)
                    source_model,_=restore(RESULTS)
                    x,_,_=dataset(7001,22)
                    with torch.no_grad():
                        self.assertTrue(torch.equal(remote_model(torch.tensor(x)),source_model(torch.tensor(x))))
                processes[0][0].kill();processes[0][0].wait(timeout=4)
                data,origin,failures=get_verified(urls,digest)
                self.assertEqual(data,raw);self.assertEqual(origin,urls[1]);self.assertGreater(len(failures),0)
                (b/'objects'/(digest+'.npz')).write_bytes(b'evil')
                with self.assertRaises(Refused):get_verified(urls,digest)
                with self.assertRaises(Refused):get_verified(['http://example.com/'],digest)
            finally:
                for child,_ in processes:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=4)
                    if child.stdout: child.stdout.close()
                    if child.stderr: child.stderr.close()

class NativeECPUOracle(unittest.TestCase):
    @unittest.skipUnless(__import__('importlib').util.find_spec('mailcpu') is not None,
                         'native E-CPU is hard-required only in hosted CI')
    def test_exact_source_matches_native_ios001(self):
        from mailcpu.intention_sufficiency import FiniteState, FiniteGround, MeasurementCapability, plan_sufficiency
        rng=np.random.default_rng(75)
        for k in range(100):
            w=make_world(rng,k)
            model=FiniteGround(*(sha({'role':role}) for role in ('ground','public','intention','context')),
                tuple(FiniteState.create(f's{i:02d}',0,int(w.targets[i]),
                       {'f0':int(w.features[i][0]),'f1':int(w.features[i][1]),'f2':int(w.features[i][2])})
                       for i in range(len(w.targets))))
            offers=tuple(MeasurementCapability('f'+str(i),sha({'test':i}),'observer-'+str(i),w.costs[i]) for i in range(3))
            plan=plan_sufficiency(model,0,offers,sha({'role':'policy'}))
            actual=8 if plan['status']=='REFUSE' else sum(1<<int(s[-1]) for s in plan['selected_features'])
            self.assertEqual(actual,exact_plan(w))

if __name__=='__main__':unittest.main()
