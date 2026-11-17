"""RCG-005 source-pinned portable nonlinear model for independent processes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from connectome_ground import ConnectomeGround
from temporal_ground import TemporalGroundRefused, SparseTransfer
from conjugate_ground import ConjugatedGround
from capsule import prepare_capsule,verify_capsule,read_json_strict,write_json,load_model
from test_temporal_ground import FIXTURE

class PortableCapsuleTests(unittest.TestCase):
    def setUp(self):
        self.source=ConnectomeGround.from_csv(FIXTURE.encode(),require_original=False)
        self.model=ConjugatedGround(SparseTransfer.from_ground(self.source,'AWCL','AWCL'),
                                    ('AWCL','ASER','ASIL','AIYL'))

    def test_immutable_capsule_receiver_recomputes_same_vector_ground(self):
        cap=prepare_capsule(self.model)
        self.assertEqual(verify_capsule(self.model,cap),cap['certificate'])
        with tempfile.TemporaryDirectory() as td:
            loc=Path(td)/'capsule.json'
            write_json(loc,cap)
            self.assertEqual(read_json_strict(loc),cap)
            with self.assertRaises(TemporalGroundRefused):
                loc.write_text('{"a":1,"a":2}')
                read_json_strict(loc)
            with self.assertRaises(TemporalGroundRefused):
                loc.write_text('{"a":NaN}')
                read_json_strict(loc)

    def test_three_process_export_verify_and_replay(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'source.csv';source.write_bytes(FIXTURE.encode())
            expected=hashlib.sha256(source.read_bytes()).hexdigest()
            args=['--source',str(source),'--expected-source-sha256',expected,
                  '--coordinates','AWCL','ASER','ASIL','AIYL','--fixture']
            artifact=root/'ground.json';result=root/'answer.json';replayed=root/'replayed.json'
            def execute(step,extra,output):
                return subprocess.run([sys.executable,'-m','capsule',step,*args,*extra,'--out',str(output)],
                    capture_output=True,text=True,timeout=20)
            a=execute('prepare',[],artifact);self.assertEqual(a.returncode,0,a.stderr)
            b=execute('verify',['--certificate',str(artifact),'--tick',str(2**56+73)],result)
            self.assertEqual(b.returncode,0,b.stderr)
            c=execute('replay',['--certificate',str(artifact),'--result',str(result)],replayed)
            self.assertEqual(c.returncode,0,c.stderr)
            self.assertEqual(read_json_strict(result),read_json_strict(replayed))
            tampered=read_json_strict(result);tampered['nonlinear_readout']+=1
            write_json(result,tampered)
            d=execute('replay',['--certificate',str(artifact),'--result',str(result)],replayed)
            self.assertEqual(d.returncode,2)
            e=execute('verify',['--certificate',str(artifact),'--tick','42',
                     '--expected-source-sha256','0'*64],result)
            self.assertEqual(e.returncode,2)

    def test_source_changed_or_model_seed_changed_fails(self):
        cap=prepare_capsule(self.model)
        changed=ConjugatedGround(self.model.operator,self.model.coordinates,seed='alternate')
        with self.assertRaises(TemporalGroundRefused):verify_capsule(changed,cap)
        with self.assertRaises(TemporalGroundRefused):
            load_model(Path('/does-not-exist'),'a'*64,self.model.coordinates,seed=self.model.seed)

if __name__=='__main__':unittest.main()
