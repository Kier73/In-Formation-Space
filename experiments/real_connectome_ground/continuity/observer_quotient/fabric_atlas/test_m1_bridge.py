"""Native M1 path tests, required by the dedicated GitHub Actions integration gate."""
import copy,hashlib,importlib.util,unittest
from test_atlas import SOURCE
from connectome_ground import ConnectomeGround
from observer_quotient import ExpandedSyntheticGround,discover
from atlas import prepare_atlas
from observer_quotient import QuotientRefused
from m1_bridge import NativeM1Atlas

NATIVE=importlib.util.find_spec('mailcpu') is not None

@unittest.skipUnless(NATIVE,'native E-CPU required for real M1 object and snapshot tests')
class NativeM1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        source=ConnectomeGround.from_csv(SOURCE.encode(),require_original=False)
        cls.op=ExpandedSyntheticGround(source,groups=8,copies=32,seed=11)
        cls.cert=discover(cls.op)
        cls.atlas=prepare_atlas(cls.op,cls.cert)
    def test_native_m1_cold_publish_warm_read_and_fresh_restore(self):
        src=SOURCE.encode()
        initial=NativeM1Atlas(src,hashlib.sha256(src).hexdigest(),self.cert,self.atlas,
                              require_original=False)
        self.assertLess(initial.manifest.size_bytes,100000)
        self.assertGreater(initial.manifest.size_bytes,0)
        self.assertEqual(initial.store.read_bytes(initial.manifest),initial.store.read_bytes(initial.manifest))
        batch=[{'sources':[[17,3],[41,4]],'tick':2**56+73,
                'readout':{'kind':'sum_squares','indices':[0,2,4,6]}}]
        result=initial.run(batch)
        checkpoint=initial.checkpoint()
        recovered=NativeM1Atlas.restore(src,checkpoint,checkpoint['digest'],require_original=False)
        self.assertEqual(recovered.identity,initial.identity)
        self.assertEqual(recovered.run(batch),result)
        self.assertGreaterEqual(len(checkpoint['page_backing']['local_pages']),1)
        wrong=copy.deepcopy(checkpoint)
        wrong['page_backing']['local_pages'].clear()
        with self.assertRaises((QuotientRefused,ValueError,KeyError)):
            NativeM1Atlas.restore(src,wrong,checkpoint['digest'],require_original=False)
        with self.assertRaisesRegex(QuotientRefused,'high-water'):
            NativeM1Atlas.restore(src,checkpoint,'0'*64,require_original=False)
        changed=src.replace(b'AWCL,ASER,1',b'AWCL,ASER,2')
        with self.assertRaisesRegex(QuotientRefused,'source'):
            NativeM1Atlas.restore(changed,checkpoint,checkpoint['digest'],require_original=False)

if __name__=='__main__':unittest.main()