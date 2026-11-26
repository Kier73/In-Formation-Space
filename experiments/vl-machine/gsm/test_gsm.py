import random,unittest
from pathlib import Path
import torch
from gsm import sources,episode,episodes,realize,batch,Learner,NULL,SPLITS
class StructuralAttention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2);cls.s=sources(Path(__file__).parent/'sources' if (Path(__file__).parent/'sources').exists() else Path(__file__).parent.parent)
    def test_sources(self):
        allnames=[v for names in SPLITS.values() for v in names];self.assertEqual(len(set(allnames)),len(allnames));self.assertEqual(set(self.s['binary-final'][:256]),set(range(256)))
    def test_tasks(self):
        r=random.Random(9)
        for name in SPLITS['final']:
            for kind,n in [('unique',1),('ambiguous',2),('absent',0)]:
                e=episode(self.s,name,r,kind);rows,hits,y=realize(self.s,e);self.assertEqual(len(hits),n);self.assertEqual(y,rows[hits[0]][2+e['offset']] if n==1 else NULL)
                for mode,L in [('dense',33),('sensor',33),('ground',9)]:
                    x,mask,label,ans,truth,active=batch(self.s,[e],mode);self.assertEqual(tuple(x.shape),(1,L,6));self.assertEqual(ans[0,label.item()].item(),truth.item());self.assertEqual(mask.sum().item(),active)
    def test_model(self):
        m=Learner();es=episodes(self.s,'final',32,123)
        for mode in ('dense','sensor','ground'):
            x,v,y,ans,truth,_=batch(self.s,es,mode);z=m(x,v);self.assertEqual(z.shape,v.shape);self.assertTrue(torch.isfinite(z).all());self.assertTrue((z[~v]<-1e8).all());torch.nn.functional.cross_entropy(z,y).backward()
    def test_bad_bounds(self):
        e=episode(self.s,'binary-final',random.Random(1),'unique');e['positions'][0][1]=len(self.s['binary-final']);self.assertRaises(ValueError,realize,self.s,e)
if __name__=='__main__':unittest.main()
