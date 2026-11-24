import random, unittest
from itertools import product
from collections import Counter
from architecture_memory import Archive, choose, coarsen, region
from verify_architecture_memory import check_transfer,check_join_coverage
from adaptive_ground import realize, balanced, leaf, Memory
from architecture_navigation import packed
from run_architecture_navigation import cycle,oracle

class ArchitectureMemoryTests(unittest.TestCase):
    def test_cross_partition(self):
        n,c,_=cycle(32);a=balanced(packed(c,n,'walk',3));b=coarsen(a);m=Archive()
        x=realize(c,n,a,m);y=realize(c,n,b,m);z=realize(c,n,b,Memory())
        self.assertEqual(x['count'],y['count']);self.assertEqual(y['count'],z['count'])
        self.assertGreater(y['metrics']['architecture_transfer'],0)
        self.assertEqual(y['metrics'].get('new_full_checks',0),0)
        self.assertEqual(y['root'],z['root']);self.assertIsNotNone(y['witness'])
    def test_reverse_and_restore(self):
        n,c,_=cycle(32);a=balanced(packed(c,n,'walk',3));b=coarsen(a);m=Archive()
        realize(c,n,b,m);r=realize(c,n,a,m);self.assertGreater(r['metrics']['new_full_checks'],0)
        self.assertEqual(int(r['count']),oracle(32));q=realize(c,n,b,m);self.assertEqual(q['metrics'].get('new_full_checks',0),0)
    def test_projection_and_not_inverse(self):
        # x1 OR x2 with a separately owned empty scope exposing x2.
        c=[(1,2),(3,)];a=[leaf([1,2],[(1,2)]),leaf([2,3],[(3,)])];b=[leaf([1,2],[(1,2)]),leaf([3],[(3,)])];m=Archive()
        x=realize(c,3,a,m);y=realize(c,3,b,m)
        self.assertEqual(x['count'],y['count']);self.assertEqual(y['metrics']['interface_projection'],1)
        fresh=Archive();realize(c,3,b,fresh);r=realize(c,3,a,fresh)
        self.assertGreater(r['metrics']['new_full_checks'],0)
    def test_source_and_free_scope_binding(self):
        old=region([1],[(1,)]);new=region([1,2],[(1,)])
        a={'boundary':[],'counts':['1']};b=dict(a)
        self.assertFalse(check_transfer(old,new,a,b))
        self.assertFalse(check_transfer(old,region([1],[(-1,)]),a,b))
    def test_forged_marginal(self):
        r=region([1,2],[(1,2)]);a={'boundary':[2],'counts':['1','2']}
        self.assertFalse(check_transfer(r,r,a,{'boundary':[],'counts':['2']}))
        self.assertFalse(check_transfer(r,r,{'boundary':[],'counts':['3']},a))
        self.assertTrue(check_transfer(r,r,a,{'boundary':[],'counts':['3']}))
    def test_shared_hidden_rejected(self):
        a=region([1,2],[(1,2)]);b=region([2,3],[(-2,3)])
        self.assertFalse(check_join_coverage(a,b,[],[2],[]));self.assertTrue(check_join_coverage(a,b,[2],[2],[]))
        self.assertFalse(check_join_coverage(a,a,[1,2],[1,2],[]))
    def test_duplicate_clauses_and_missing_free_var(self):
        a=leaf([1],[(1,)]);m=Archive()
        with self.assertRaises(ValueError):realize([(1,)],2,a,m)
        with self.assertRaises(ValueError):realize([(1,)],1,[a,a],m)
    def test_cost_selection_changes(self):
        n,c,_=cycle(32);a=balanced(packed(c,n,'walk',3));b=coarsen(a);cat={'fine':a,'coarse':b}
        self.assertEqual(choose(c,n,cat,Archive())['selected'],'fine')
        m=Archive();realize(c,n,b,m)
        self.assertEqual(choose(c,n,cat,m)['selected'],'coarse')
    def test_revision_and_reversal(self):
        c=[(1,2)];a=leaf([1,2],c);m=Archive();x=realize(c,2,a,m)
        d=[*c,(-1,)];b=leaf([1,2],d);y=realize(d,2,b,m);z=realize(c,2,a,m)
        self.assertEqual((x['count'],y['count'],z['count']),('3','1','3'));self.assertEqual(x['root'],z['root'])
    def test_exhaustive_random(self):
        rng=random.Random(1201);m=Archive()
        for _ in range(200):
            n=rng.randrange(2,8);c=[tuple(v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),rng.randint(1,min(3,n)))) for _ in range(rng.randint(0,12))]
            from composed_ground import canonical
            c=canonical(c,n);a=leaf(range(1,n+1),c);b=balanced(packed(c,n,'walk',3))
            want=sum(all(any(bits[abs(l)-1]==(l>0) for l in row) for row in c) for bits in product([0,1],repeat=n))
            for tree in (b,a,b,a):self.assertEqual(int(realize(c,n,tree,m)['count']),want)
    def test_unadmitted_child(self):
        m=Archive()
        with self.assertRaises(ValueError):m.obtain({'boundary':[]},[{'key':'invented'}]*2,Counter())
    def test_estimator_does_not_mutate(self):
        n,c,_=cycle(16);a=balanced(packed(c,n,'walk',3));m=Archive()
        x=m.estimate(c,n,a);y=m.estimate(c,n,a);self.assertEqual(x,y);self.assertEqual(x['new_full_checks'],x['nodes'])
        r=realize(c,n,a,m);self.assertEqual(x['producer_cells'],r['metrics']['producer_cells'])
if __name__=='__main__': unittest.main()
