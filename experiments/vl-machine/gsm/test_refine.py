import random,unittest
from pathlib import Path
import torch
import gsm as g
from refine import new_sources,acquire,guarded,fresh,evaluate
class RefinedAttention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2);p=Path(__file__).parent;cls.s=new_sources(p/'sources' if (p/'sources').exists() else p.parent)
    def test_lazy_reads(self):
        for n in (8,32,64):
            for e in fresh(self.s,n,60):
                rows,hits,y=g.realize(self.s,e);p,cost=acquire(self.s,e)
                self.assertEqual(cost,2*n+(4 if len(hits)==1 else 0));self.assertEqual(p[e['offset']] if p is not None else g.NULL,y)
    def test_many_matches(self):
        e=g.episode(self.s,'binary-new',random.Random(3),'unique');i=g.realize(self.s,e)[1][0]
        for j in range(len(e['positions'])):e['positions'][j][0]=e['positions'][i][0]
        e['kind']='ambiguous';self.assertEqual(acquire(self.s,e),(None,16));x,y,a,indices,cost=guarded(self.s,[e]);self.assertEqual((len(x),indices,cost),(0,[],16))
    def test_qualified_inference(self):
        m=g.Learner();rows=fresh(self.s,64,32);r=evaluate(m,self.s,rows,'qualified');self.assertEqual(r['false_answer'],0);self.assertEqual(r['neural_episodes'],r['unique']);self.assertEqual(r['padded_attention_pairs_per_head'],25*r['unique'])
    def test_exact_byte_255(self):
        s={'x':b'ab'+bytes([0,255,1,2])+b'cd1234'};e={'source':'x','positions':[[0,2],[6,8]],'key':[97,98],'offset':1,'kind':'unique'};self.assertEqual(acquire(s,e),([0,255,1,2],8));self.assertEqual(g.realize(s,e)[2],255)
if __name__=='__main__':unittest.main()
