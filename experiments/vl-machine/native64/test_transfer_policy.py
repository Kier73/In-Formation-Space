import json,os,unittest
from pathlib import Path
from transfer_policy import campaign,portable,polynomial_affine,live_assess,PROBES
from external_descriptor import identity,parse,projection,record,MAX

class Transfer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=portable();cls.report=campaign(json.loads(Path(os.environ['VLK_DATA']).read_bytes()),os.environ['VLK_ROOT'])
    def test_transfer(self):
        r=self.report;self.assertEqual(r['offline_probe_calls'],18000)
        self.assertEqual(r['policies']['transferred'],{'default':0,'contexts':{}})
        self.assertEqual(r['policies']['target_adapted'],{'default':5,'contexts':{}})
        s=r['live_paths'];self.assertEqual(s['source_final']['counterexamples'],3);self.assertEqual(s['target_transferred']['counterexamples'],82);self.assertEqual(s['target_adapted']['counterexamples'],160)
        self.assertEqual(s['target_transferred']['admitted'],40);self.assertEqual(s['target_adapted']['admitted'],40)
        self.assertEqual(r['polynomial_extension'],{'original':40,'polynomial':80,'newly_verified':40})
    def test_polynomial_identity(self):
        m=self.m;p=m.Program((m.Node('input'),m.Node('mul',(0,0)),m.Node('const',value=1<<31),m.Node('mul',(1,2))),3)
        self.assertFalse(m.verify(p,m.Ground(p.identity,1<<31,0)))
        self.assertTrue(polynomial_affine(m,p,1<<31,0));self.assertFalse(polynomial_affine(m,p,0,0))
        for x in (0,1,2,3,65536,0xffffffff,0x12345678):self.assertEqual(m.reference(p,x),x*(1<<31)&m.MASK)
        q=m.Program((m.Node('input'),m.Node('mul',(0,0))),1);self.assertFalse(polynomial_affine(m,q,1,0))
        r=m.Program((m.Node('input'),m.Node('mul',(0,0)),m.Node('mul',(1,1)),m.Node('mul',(2,2)),m.Node('mul',(3,3))),4);self.assertFalse(polynomial_affine(m,r,1,0));self.assertFalse(polynomial_affine(m,p,True,0))
    def test_live_only_selected(self):
        calls=[];checks=[]
        def adapter(source):
            def observe(x):calls.append(x);return x*x
            def check(a,b):checks.append((a,b));return False
            return observe,check
        r=live_assess([{'source':{},'a':1,'b':0,'eligible':False}],{'default':0,'contexts':{}},adapter)
        self.assertEqual(calls,[0,1,PROBES[0]]);self.assertEqual(checks,[]);self.assertEqual(r['counterexamples'],1)

class Descriptors(unittest.TestCase):
    def setUp(self):
        self.f=json.loads((Path(__file__).with_name('datasets')/'vlm015'/'hf-observation.json').read_bytes());self.model=self.f['model'];self.rev=self.f['revision'];self.raw=json.dumps(self.f['observed_fields']).encode()
    def test_projection(self):
        desc=parse(self.raw,self.model,self.rev);r=record(desc,'web-field-projection',self.f['source_url']);self.assertEqual(r['authority'],'descriptive-only');self.assertIsNone(r['raw_response_sha256']);self.assertTrue(desc['safetensors_declared']);self.assertEqual(desc['parameter_count_declared'],134515008)
        self.assertIn(self.rev,r['next_observation']['url'])
    def test_reject(self):
        for raw in (self.raw+b' '*MAX,b'{"id":1,"id":2}',b'{}'):
            with self.assertRaises(ValueError):parse(raw,self.model,self.rev)
        with self.assertRaises(ValueError):parse(self.raw,self.model,'0'*40)
        with self.assertRaises(ValueError):identity('https://invalid/x',self.rev)
        with self.assertRaises(ValueError):record(parse(self.raw,self.model,self.rev),'raw-https-json',self.f['source_url'],'0'*64)
        with self.assertRaises(ValueError):record(parse(self.raw,self.model,self.rev),'web-field-projection',self.f['source_url'],'0'*64)
    def test_missing_config(self):
        data={'id':self.model,'sha':self.rev};desc=projection(data,self.model,self.rev);r=record(desc,'web-field-projection',self.f['source_url']);self.assertIsNone(r['next_observation']);self.assertFalse(desc['safetensors_declared'])
if __name__=='__main__':unittest.main()
