import itertools,json,os,unittest
from pathlib import Path
from intention_acquisition import INTENTS,Intention,learn,assess,run,validate_plan,campaign,external_plan,symbolic_inspect
from transfer_policy import PROBES,portable

class Acquisition(unittest.TestCase):
    def test_empirical_optimality(self):
        rows=[]
        for mask in (0,0,1,2,3,4,8,16,32,128):
            rows.append({'id':str(len(rows)),'a':1,'b':0,'eligible':mask==0,'bad':[int(bool(mask&(1<<i))) for i in range(8)],'values':[x+int(bool(mask&(1<<i))) for i,x in enumerate(PROBES)]})
        for intent in INTENTS:
            plans=[[]]
            for n in range(4):
                for seq in itertools.permutations(range(8),n):
                    for end in ([],['proof']):
                        plan=list(seq)+end
                        try:validate_plan(plan,intent)
                        except ValueError:continue
                        plans.append(plan)
            self.assertEqual(assess(rows,learn(rows,intent),intent)[0]['utility'],max(assess(rows,p,intent)[0]['utility'] for p in plans))
    def test_authority_and_budget(self):
        calls=[]
        def observe(x):calls.append(x);return x*x
        def check(a,b):raise AssertionError('forbidden proof')
        intent=INTENTS[0]
        for p in (['proof'],[0,0],[0,1,2,3],[True],None):
            with self.assertRaises(ValueError):run(p,intent,observe,check)
        self.assertEqual(calls,[])
        self.assertEqual(run([],intent,observe,check)['cost'],0);self.assertEqual(calls,[])
        self.assertEqual(run([0],intent,observe,check)['status'],'refuted');self.assertEqual(calls,[0,1,2])
        self.assertEqual(run([0],intent,lambda x:x,check)['status'],'unknown')
        self.assertEqual(run(['proof'],INTENTS[1],lambda x:x,lambda a,b:False)['status'],'unknown')
    def test_source_inspection(self):
        m=portable();p=m.Program((m.Node('input'),m.Node('mul',(0,0))),1);r=symbolic_inspect(m,p);self.assertEqual(r,{'status':'refuted','a':1,'b':0,'witness':[2,4]})
        p=m.Program(p.nodes+(m.Node('const',value=1<<31),m.Node('mul',(1,2))),3);self.assertEqual(symbolic_inspect(m,p),{'status':'certified','a':1<<31,'b':0})
        p=m.Program((m.Node('input'),m.Node('const',value=1),m.Node('xor',(0,1))),2);self.assertEqual(symbolic_inspect(m,p)['status'],'unknown')
    def test_external_intention(self):
        f=json.loads((Path(__file__).with_name('datasets')/'vlm015'/'hf-observation.json').read_bytes())
        self.assertEqual(external_plan(f,'describe',0,False)['status'],'described')
        self.assertIsNone(external_plan(f,'inspect-config',4096,True)['action']);self.assertIsNone(external_plan(f,'inspect-config',65536,False)['action'])
        self.assertEqual(external_plan(f,'inspect-config',65536,True)['action']['max_bytes'],65536)
        self.assertEqual(external_plan(f,'infer',65536,True)['status'],'unqualified')
    def test_campaign(self):
        r=campaign(os.environ['TRANSFER_DATA'],os.environ['VLK_ROOT']);a=r['reports'];expected={'observation_only':('target',160,0,80,720),'resolve_expensive_proof':('target',160,80,0,1200),'qualify':('inspect_only',40,80,120,1440),'resolve_cheap_proof':('inspect_then_probe',160,80,0,840)}
        for k,(plan,refuted,certified,unknown,cost) in expected.items():
            self.assertEqual(a[k]['selected'],plan);s=a[k]['final'][plan];self.assertEqual((s['refuted'],s['certified'],s['unknown'],s['cost']),(refuted,certified,unknown,cost));self.assertLessEqual(s['max_cost'],a[k]['intention']['budget'])
        self.assertEqual(r['trace_sha256'],'85728150c71300d60cab698155496da0a2dd34e9cc3e693d9558b69cee54cdaf')
if __name__=='__main__':unittest.main()
