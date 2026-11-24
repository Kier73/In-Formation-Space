import unittest,random,copy
from collections import Counter
from language_extension import Language, extend, LanguageRetained
from verify_language_extension import check_extension
from nonlinear_sufficient import make_seed
from composed_ground import canonical
from adaptive_ground import realize,leaf,balanced
from architecture_memory import Archive

class ExtensionTests(unittest.TestCase):
    def base(self):return Language(3,[1,2,3],[[-1,2],[1,-2]],[],[[1]])
    def test_semantic_equivalence(self):
        l=self.base();s=Counter();l.ensure([2],s);self.assertEqual(s['equivalence_extensions'],1);self.assertEqual(s['semantic_states'],0);self.assertEqual(len(l.snapshot()['bins']),2)
    def test_split_and_witness(self):
        l=self.base();old=l.snapshot();new,c,s=extend(old,[3]);self.assertEqual(c['splits'],[0,1]);self.assertTrue(check_extension(old,[3],c,new));self.assertEqual(len(new['bins']),4)
        c['pairs'][0][1]=c['pairs'][0][0];self.assertFalse(check_extension(old,[3],c,new))
    def test_symbolic_composition(self):
        l=self.base();s=Counter();l.ensure([2],s);l.ensure([3],s);before=s['semantic_states'];l.ensure([2,3],s);self.assertEqual(s['semantic_states'],before);self.assertEqual(s['symbolic_extensions'],2)
    def test_tampered_count(self):
        old=self.base().snapshot();new,c,s=extend(old,[3]);new['bins'][0][1]='2';self.assertFalse(check_extension(old,[3],c,new))
    def test_boolean_key_forgery(self):
        old=self.base().snapshot();new,c,s=extend(old,[3]);new['bins'][0][0]=False;self.assertFalse(check_extension(old,[3],c,new))
    def test_forged_split(self):
        old=self.base().snapshot();new,c,s=extend(old,[3]);c['splits']=[];c['pairs']=[];self.assertFalse(check_extension(old,[3],c,new))
    def test_forged_cover(self):
        old=self.base().snapshot();new,c,s=extend(old,[1,3]);c={'method':'cover','parts':[[0,0]],'splits':[],'pairs':[]};self.assertFalse(check_extension(old,[1,3],c,new))
    def test_unsat(self):
        l=Language(2,[1,2],[[1],[-1]],[],[]);s=Counter();l.ensure([2],s);self.assertEqual(l.snapshot()['bins'],[])
    def test_semantic_constant(self):
        l=Language(3,[1,2,3],[[1]],[],[]);s=Counter();l.ensure([1],s);self.assertEqual(s['semantic_sufficient'],1);self.assertEqual(len(l.snapshot()['bins']),1)
    def test_complement(self):
        l=self.base();s=Counter();l.ensure([-2],s);self.assertEqual(s['equivalence_extensions'],1);self.assertEqual(s['semantic_states'],0)
    def test_empty_clause(self):
        l=self.base();s=Counter();l.ensure([],s);self.assertEqual(len(l.snapshot()['bins']),2);self.assertEqual(s['symbolic_extensions'],1)
    def test_scope(self):
        with self.assertRaises(ValueError):self.base().ensure([4],Counter())
    def test_random(self):
        rng=random.Random(152)
        for _ in range(300):
            n=rng.randint(2,7);s=list(range(1,n+1));source=canonical([[v*rng.choice([-1,1]) for v in rng.sample(s,rng.randint(1,min(n,3)))] for _ in range(rng.randint(0,8))],n)
            l=Language(n,s,source,s[:1],[]);stats=Counter()
            for j in range(4):
                c=list(canonical([[v*rng.choice([-1,1]) for v in rng.sample(s,rng.randint(1,min(n,3)))]],n)[0]);l.ensure(c,stats)
                snap=l.snapshot();d=snap['descriptor'];p=d['predicates'];ref,_=make_seed(n,s,source,s[:1],p)
                # Canonical initial seed sorts predicates; reorder its signature.
                q=ref['descriptor']['predicates'];hist={}
                for k,z in ref['bins']:
                    code=(k&1)|sum(((k>>(1+q.index(c)))&1)<<(1+i) for i,c in enumerate(p));hist[code]=z
                self.assertEqual(dict(snap['bins']),hist)
    def test_regional(self):
        n=4;base=[[-1,2],[1,-2],[3,4]];t=balanced([leaf([1,2,3],base[:2]),leaf([3,4],base[2:])]);memory=LanguageRetained(base,n,t)
        for c in [[2],[-2],[1,2]]:
            src=base+[c];rev=balanced([leaf([1,2,3],src[:2]+[c]),leaf([3,4],base[2:])]);a=realize(src,n,rev,memory.session());b=realize(src,n,rev,Archive());self.assertEqual(a['count'],b['count'])

if __name__=='__main__':unittest.main()
