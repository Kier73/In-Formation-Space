import os,unittest
from measured_acquisition import portable,stress,program,Source,execute,learn_probes,bench,native_profile,select
from transfer_policy import target_rows

class Measured(unittest.TestCase):
    def test_routes(self):
        m=portable();rows=list(target_rows(m,1781,24));probes=learn_probes(rows)
        for mode in ('local','ipc'):
            r=bench(m,rows,mode,probes,1)['routes'];self.assertEqual(r['inspect_first']['status'],{'certified':8,'refuted':16});self.assertEqual(r['probe_first']['status'],r['inspect_first']['status']);self.assertEqual(r['inspect_first']['actions']['observe'],36);self.assertEqual(r['inspect_first']['payload_bytes'],432 if mode=='ipc' else 0)
            self.assertIn(select(r),('inspect_first','probe_first','two_probes'))
    def test_unknown(self):
        m=portable();rows=list(stress(m,1782,12));src=Source(m,rows,'local')
        try:
            for i in range(1,12,3):
                out,_,_=execute(src,i,'inspect_first',[0xffffffff,2]);self.assertEqual(out['status'],'unknown');p=program(m,rows[i]['source']);self.assertEqual(m.reference(p,123),(123+p.nodes[2].value)&m.MASK)
        finally:src.close()
    def test_native(self):
        r=native_profile(os.environ['VLK_ROOT'],1);self.assertEqual(r['programs'],240);self.assertEqual(r['certified']+r['unknown'],240);self.assertEqual(r['routes']['basis_then_check']['observations'],480)
    def test_selection(self):
        from measured_acquisition import ROUTES
        r={n:{'status':{'unknown':1},'median_ns':1} for n in ROUTES};r['inspect_first']={'status':{'unknown':0},'median_ns':100};self.assertEqual(select(r),'inspect_first')
if __name__=='__main__':unittest.main()
