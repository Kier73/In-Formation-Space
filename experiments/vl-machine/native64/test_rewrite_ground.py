import random,unittest
from rewrite_ground import certify,discover,grammar,Rewriter,DirectBits,Hybrid,portable,generated,self_generated,campaign,semantic,MASK
from intention_acquisition import symbolic_inspect

class Rewrite(unittest.TestCase):
    def test_certificate(self):
        x,y,z=('v',0),('v',1),('v',2)
        self.assertTrue(certify(('xor',('xor',x,y),y),x))
        self.assertFalse(certify(('xor',('xor',x,y),z),x))
        self.assertFalse(certify(('xor',x,y),z))
        self.assertFalse(certify(('add',x,y),x))
        self.assertFalse(certify(('xor',x,y),('c',1)))
        rules,stats=discover(grammar(1)[1],samples=[(0,0,0)])
        self.assertGreater(stats['rejected'],0);self.assertTrue(all(certify(*r) for r in rules))
    def test_substitution_and_opaque_arithmetic(self):
        m=portable();x,y=('v',0),('v',1);rules=((('xor',('xor',x,y),y),x),)
        p=m.Program((m.Node('input'),m.Node('const',value=7),m.Node('add',(0,1)),m.Node('xor',(2,1)),m.Node('xor',(3,1))),4)
        q,w=Rewriter(m,rules).rewrite(p);self.assertEqual(w['before'],3);self.assertEqual(w['after'],1);self.assertEqual(symbolic_inspect(m,q),{'status':'certified','a':1,'b':7})
        bad=m.Program(p.nodes[:-1]+(m.Node('xor',(3,0)),),4);z,w=Rewriter(m,rules).rewrite(bad);self.assertFalse(w['hits'])
        with self.assertRaises(ValueError):Rewriter(m,((('xor',x,y),x),))
    def test_direct_and_hybrid(self):
        m=portable();r=random.Random(77);rules,_=discover(grammar(2)[2]);rules=rules[:100]
        for p in generated(m,71,40,6):
            for rw in (DirectBits(m),Hybrid(m,rules)):
                q,_=rw.rewrite(p)
                for x in (0,1,MASK,*[r.getrandbits(32) for _ in range(8)]):self.assertEqual(m.reference(p,x),m.reference(q,x))
    def test_campaign(self):
        r=campaign();a=r['reports'];self.assertEqual(len(r['first_rules']),1);self.assertEqual(len(r['combined_rules']),6);self.assertEqual(len(r['refined_rules']),8)
        self.assertEqual(a['prior']['first']['stats']['after_certified'],80)
        self.assertEqual(a['final']['combined']['stats']['after_certified'],152);self.assertEqual(a['final']['direct']['stats']['after_certified'],176)
        self.assertEqual(a['epoch_final']['refined']['stats']['after_certified'],115);self.assertEqual(a['epoch_final']['combined']['stats']['after_certified'],118)
        self.assertEqual(a['epoch_final'][r['epoch_selected']]['stats']['after_certified'],128)
        self.assertEqual(len({p['id'] for ps in r['cohorts'].values() for p in ps}),sum(map(len,r['cohorts'].values())))
        self.assertEqual(semantic(r),'f6b481fcf5c99153c9d1cb6ccf9888ab46498513f595270fb5d85dbcb7ae5dd0')
if __name__=='__main__':unittest.main()
