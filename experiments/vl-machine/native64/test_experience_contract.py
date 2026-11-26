import copy,json,os,unittest
from pathlib import Path
from experience_contract import campaign,record,verify,digest,interpret,VLK,NEURAL,features,neural

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vlm=Path(os.environ['VLM_LEDGER']);cls.vlk=Path(os.environ['VLK_DATA']);cls.weights=json.loads(cls.vlk.read_bytes())['report']['weights']
        cls.report,cls.rows=campaign(cls.vlm,cls.vlk,os.environ['VLK_ROOT'])
    def test_campaign(self):
        r=self.report;self.assertEqual(r['counts']['paired'],56);self.assertEqual(r['counts']['basis_replayed'],6000);self.assertEqual(r['counts']['native_archive_replay'],2400);self.assertEqual(r['proposal_records'],600);self.assertEqual(r['exact_records'],1552);self.assertEqual(r['counts']['outside_scalar_contract'],960)
        for i in range(0,112,2):
            a,b=self.rows[i:i+2];self.assertEqual(a['action_id'],b['action_id']);self.assertNotEqual(a['source_id'],b['source_id'])
    def test_rehash_tamper(self):
        for field,value in [('value',0),('authority','proposal-only'),('action_id','0'*64),('source_id','0'*64)]:
            r=copy.deepcopy(self.rows[0]);r[field]=value;r['record_id']=digest({k:v for k,v in r.items() if k!='record_id'})
            with self.assertRaises(ValueError):verify(r,self.weights)
        r=copy.deepcopy(self.rows[0]);r['source']['program']='00'+r['source']['program'][2:];r['request']['time']^=1;r['record_id']=digest({k:v for k,v in r.items() if k!='record_id'})
        with self.assertRaises(ValueError):verify(r,self.weights)
    def test_projection_boundary(self):
        for p in ([['mulr',0,1]],[['addr',0,1]]):
            s={'kind':'vlk.k1','revision':VLK,'program':p,'observer':0}
            with self.assertRaises(ValueError):interpret(s,{'seed':[1,2,3,4],'time':0},self.weights)
        s={'kind':'vlk.k1','revision':VLK,'program':[['add',0,1]],'observer':0}
        a,v,scope=interpret(s,{'seed':[0xffffffff,2,3,4],'time':1},self.weights);self.assertEqual(v,0);self.assertEqual(scope,'exact-source-replay')
        with self.assertRaises(ValueError):interpret(s,{'seed':[True,2,3,4],'time':1},self.weights)
    def test_proposal_boundary(self):
        r=next(r for r in self.rows if r['authority']=='proposal-only');self.assertTrue(verify(r,self.weights))
        s=copy.deepcopy(r);s['authority']='exact-source-replay';s['record_id']=digest({k:v for k,v in s.items() if k!='record_id'})
        with self.assertRaises(ValueError):verify(s,self.weights)
        w=self.weights[:];w[0]=(w[0]+1) if w[0]<127 else 126
        with self.assertRaises(ValueError):verify(r,w)
        s=copy.deepcopy(r);s['request']['features'][0]=float(s['request']['features'][0]);s['record_id']=digest({k:v for k,v in s.items() if k!='record_id'})
        with self.assertRaises(ValueError):verify(s,self.weights)
    def test_deterministic(self):
        r,rows=campaign(self.vlm,self.vlk,os.environ['VLK_ROOT']);self.assertEqual(r,self.report);self.assertEqual(rows,self.rows)
if __name__=='__main__':unittest.main()
