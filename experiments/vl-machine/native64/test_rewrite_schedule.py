import copy, unittest
from rewrite_schedule import portable, schedule, replay, campaign, RULES, semantic
from experience_contract import digest
from rewrite_ground import self_generated

class Scheduling(unittest.TestCase):
    def test_replay(self):
        m=portable();p=m.Program((m.Node('input'),m.Node('const',value=7),m.Node('xor',(0,1)),m.Node('xor',(2,1))),3)
        q,proof,_,_=schedule(m,p,'index');self.assertEqual(q,replay(m,p,proof));self.assertEqual(q.nodes[q.output].op,'input')
        for field,value in [('target','0'*64),('source','0'*64),('rules','0'*64),('events',[[3,[0]]]),('events',[[3,[True]]]),('events',[[3,[5]],[3,[5]]]),('events',[])]:
            bad=copy.deepcopy(proof);bad[field]=value
            with self.assertRaises(ValueError):replay(m,p,bad)
    def test_schedule(self):
        m=portable()
        for p in self_generated(m,RULES,1981,30):
            outputs=[]
            for mode in ('static','index','learned'):
                q,proof,w,_=schedule(m,p,mode);self.assertEqual(replay(m,p,proof),q);outputs.append(q.identity)
                for x in (0,1,2,4294967295):self.assertEqual(m.reference(p,x),m.reference(q,x))
            self.assertEqual(len(set(outputs)),1)
    def test_campaign(self):
        r=campaign();self.assertEqual(len(r['cohorts']['final']),240)
        self.assertEqual(r['final']['static']['queries'],7680)
        for route in ('static','index','learned'):
            self.assertEqual(r['final'][route]['work']['certified'],r['final']['static']['work']['certified'])
        self.assertLess(r['final']['index']['work']['matches'],r['final']['static']['work']['matches'])
if __name__=='__main__':unittest.main()
