import unittest,random,copy
from test_skill_language import random_view
from skill_language import compile_view
from family_rank import seed_packet,TransportedRank
from verify_family_rank import RankSeedAdmission

class RankFamilyTests(unittest.TestCase):
    def test_random_transport_and_ordinals(self):
        rng=random.Random(399)
        for i in range(100):
            a=random_view(i,(4,9,5),cutoff=i%9);p=seed_packet(a);v=RankSeedAdmission(a,p)
            for j in range(3):
                f=(rng.randrange(1,100),rng.randrange(100),rng.randrange(2));b,_=compile_view(a,f);r=TransportedRank(a,b,p,f);c=v.activate(b,r.recipe)
                self.assertEqual(r.terms,c.terms)
                n=0
                for t in range(b.cutoff+2*b.period):
                    self.assertEqual(c.rank(t),n);n+=b.bit(t)
                for k in (1,2,7,10**900+173):
                    out=r.select(k);self.assertTrue(c.verify(k,out),(i,f,k,out))
    def test_forgery_refusal(self):
        a=random_view(9,(4,3,5),cutoff=5);p=seed_packet(a);v=RankSeedAdmission(a,p);b,_=compile_view(a,(17,5,1));r=TransportedRank(a,b,p,(17,5,1));c=v.activate(b,r.recipe)
        q=copy.deepcopy(p);q['terms'][0][2]+=1
        with self.assertRaises(ValueError):RankSeedAdmission(a,q)
        q=copy.deepcopy(r.recipe);q['form'][2]^=1
        with self.assertRaises(ValueError):v.activate(b,q)
        q=copy.deepcopy(r.recipe);q['source']=b.key
        with self.assertRaises(ValueError):v.activate(b,q)
        out=r.select(100);self.assertTrue(c.verify(100,out));out['time']=str(int(out['time'])+1);self.assertFalse(c.verify(100,out))
    def test_empty_and_full(self):
        from test_family_language import pulse
        a,ph=pulse(7,(4,3,5),cutoff=0);p=seed_packet(a);v=RankSeedAdmission(a,p)
        b0=next(b for b in range(a.period) if b not in ph)
        for c in (0,1):
            f=(a.period,b0,c);b,_=compile_view(a,f);r=TransportedRank(a,b,p,f);z=v.activate(b,r.recipe)
            k=10**900+1;out=r.select(k);self.assertTrue(z.verify(k,out));self.assertEqual(out['status'],'FOUND' if c else 'UNREACHABLE')
