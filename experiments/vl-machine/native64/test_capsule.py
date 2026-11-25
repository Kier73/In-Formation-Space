import copy
import json
import subprocess
import sys
import unittest
from capsule import L,Node,export,restore,observe,sha
from test_core import chart,affine

class Capsule(unittest.TestCase):
    def fixture(self,kind):
        if kind==1:nodes,out=affine(3,7,1);a,b=3,7
        else:nodes,out=chart(65536,1);a,b=65536,1
        self.assertTrue(L.begin(len(nodes),out))
        for i,n in enumerate(nodes):self.assertTrue(L.put(i,Node(*n)))
        self.assertTrue(L.commit());self.assertTrue((L.admit if kind==1 else L.admit_chart)(a,b))
        g=L.graph_publish();h=L.proc_restore(g,11,10**12);self.assertTrue(h)
        cap=export(h);expected=observe(h);self.assertTrue(L.proc_close(h));self.assertTrue(L.graph_release(g))
        return cap,expected
    def test_fresh_authority(self):
        for kind in [1,2]:
            cap,expected=self.fixture(kind)
            p=subprocess.run([sys.executable,'capsule.py'],input=json.dumps(cap),text=True,capture_output=True,check=True)
            self.assertEqual(json.loads(p.stdout),expected)
            g,h=restore(cap);self.assertEqual(observe(h),expected);self.assertEqual(export(h),cap);L.proc_close(h);L.graph_release(g)
    def test_tamper(self):
        cap,_=self.fixture(2)
        for mode in ['digest','witness','graph','time']:
            x=copy.deepcopy(cap);b=x['body']
            if mode=='digest':b['seed']^=1
            elif mode=='witness':b['witness'][1]^=65536
            elif mode=='graph':b['source']['nodes'][14][0]=2;b['source_sha256']=sha(b['source'])
            else:b['time']=1<<64
            if mode!='digest':x['sha256']=sha(b)
            with self.assertRaises(ValueError):restore(x)

if __name__=='__main__':unittest.main()
