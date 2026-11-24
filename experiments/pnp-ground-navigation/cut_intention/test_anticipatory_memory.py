import random
import unittest
from collections import Counter
from itertools import product
from adaptive_ground import leaf, realize, balanced
from architecture_memory import Archive
from anticipatory_memory import (Portfolio, Retained, RevisionArchive, descriptor, region,
                                 restrict, required, options, cold)
from verify_anticipatory_memory import verify_restriction
from regional_memory import produce


def direct(n, cs, b):
    out = [0]*(1 << len(b))
    for a in product((0, 1), repeat=n):
        if all(any(a[abs(l)-1] == int(l > 0) for l in c) for c in cs):
            out[sum(a[v-1] << j for j,v in enumerate(b))] += 1
    return list(map(str, out))


class AnticipatoryTests(unittest.TestCase):
    def test_independent_mask_and_projection(self):
        rng = random.Random(1301)
        for _ in range(250):
            n = rng.randrange(2, 9)
            cs = [(1, 2), (-1, -2)]
            a = tuple(sorted(rng.sample(range(1, n+1), rng.randrange(1,n+1))))
            b = tuple(sorted(rng.sample(a, rng.randrange(len(a)+1))))
            extra = [tuple(v*rng.choice((-1,1)) for v in rng.sample(a,rng.randrange(len(a)+1)))]
            from composed_ground import canonical
            base = region(range(1,n+1), canonical(cs,n)); target = region(range(1,n+1),canonical(cs+extra,n))
            oldd, newd = descriptor(base,a), descriptor(target,b)
            old, _, _ = produce(oldd,None)
            new = restrict(oldd,old,newd)
            self.assertTrue(verify_restriction(n,oldd,old,newd,new))
            self.assertEqual(new['counts'],direct(n,target[1],b))
    def test_hidden_or_deleted_source_rejected(self):
        base=region([1,2],[(1,2)]); oldd=descriptor(base,(1,)); old,_,_=produce(oldd,None)
        for target in (region([1,2],[(1,2),(-2,)]),region([1,2],[]),region([1,2,3],[(1,2)])):
            d=descriptor(target,()); m,_,_=produce(d,None)
            self.assertFalse(verify_restriction(3,oldd,old,d,m))
    def test_forged_count_and_key(self):
        base=region([1,2],[(1,2)]); d=descriptor(base,(1,)); old,_,_=produce(d,None)
        newd=descriptor(region([1,2],[(1,2),(-1,)]),()); new=restrict(d,old,newd)
        self.assertTrue(verify_restriction(2,d,old,newd,new))
        self.assertFalse(verify_restriction(2,d,old,newd,dict(new,counts=['9'])))
        self.assertFalse(verify_restriction(2,d,old,newd,dict(new,key='invented')))
    def test_receiver_not_accept_arbitrary_table(self):
        with self.assertRaises(ValueError): RevisionArchive({})
    def test_noncanonical_and_boolean_counts_rejected(self):
        d=descriptor(region([1,2],[(1,2)]),(1,)); old,_,_=produce(d,None)
        newd=descriptor(region([1,2],[(1,2),(-1,)]),()); new=restrict(d,old,newd)
        for forged in (['01'],[True],['-1']):
            self.assertFalse(verify_restriction(2,d,old,newd,dict(new,counts=forged)))
    def test_anticipates_constraint(self):
        cs=[(1,2)]; n=8; t=leaf(range(1,n+1),cs); p=Portfolio(cs,n,t,price=1)
        target=cs+[(-1,)]; revised=leaf(range(1,n+1),target)
        p.add('pin',target,revised,weight=10)
        self.assertEqual(list(p.selection()[0].values()),[(1,)])
        cache=Retained(p); r=realize(target,n,revised,cache.session()); f=realize(target,n,revised,Archive())
        self.assertEqual(r['count'],f['count']); self.assertEqual(r['metrics']['restriction_cells'],2)
        self.assertEqual(r['metrics']['anticipatory_reuse'],1)
        self.assertEqual(r['metrics'].get('producer_cells',0),0)
        self.assertEqual(int(r['count']),64)
    def test_price_refuses_unhelpful_retention(self):
        base=region([1,2],[(1,2)]); target=region([1,2],[(1,2),(-1,)])
        r=Counter({(target,(),(1,)):1})
        self.assertIsNone(options(base,(),r,100)[0])
    def test_replace_incremental_exact(self):
        cs=[(1,2),(3,4)]; a=leaf([1,2],[(1,2)]); b=leaf([3,4],[(3,4)]); t=[a,b]
        u=[leaf([1,2],[(1,2),(-1,)]),b]; c=cs+[(-1,)]
        p=Portfolio(cs,4,t); p.add('one',cs,t,10); prev=p.touched
        p.replace('one',c,u,10); self.assertEqual(p.touched-prev,1)
        q=Portfolio(cs,4,t); q.add('one',c,u,10)
        self.assertEqual(p.selection()[0],q.selection()[0]); self.assertEqual(p.selection()[1]['objective'],q.selection()[1]['objective'])
        p.remove('one');self.assertEqual(p.selection()[1]['objective'],0)
    def test_cold_fallback_for_out_of_catalog_revision(self):
        cs=[(1,2)];n=8;t=leaf(range(1,n+1),cs);p=Portfolio(cs,n,t)
        target=cs+[(-1,)];p.add('known',target,leaf(range(1,n+1),target),10);m=Retained(p)
        unknown=cs+[(-2,)];r=realize(unknown,n,leaf(range(1,n+1),unknown),m.session())
        self.assertEqual(int(r['count']),64);self.assertEqual(r['metrics']['new_full_checks'],1)
    def test_zero_source_and_free_coordinates(self):
        cs=[()]; t=leaf([1,2],cs);p=Portfolio(cs,2,t);p.add('zero',cs,t,10)
        self.assertEqual(realize(cs,2,t,Retained(p).session())['count'],'0')
    def test_missing_forecast_clause_refused(self):
        cs=[(1,2)];t=leaf([1,2],cs);p=Portfolio(cs,2,t)
        with self.assertRaises(ValueError):p.add('bad',cs+[(-1,)],t)
    def test_tampered_retained_bytes_refused(self):
        from regional_memory import wire
        import json
        cs=[(1,2)];t=leaf(range(1,9),cs);p=Portfolio(cs,8,t);p.add('base',cs,t,10)
        m=Retained(p);s=tuple(range(1,9));d,r=m._entries[s][0];bad=json.loads(r);bad['counts']=['999']
        m._entries[s][0]=(d,wire(bad))
        with self.assertRaises(ValueError):realize(cs,8,t,m.session())
    def test_independent_packing_fallback(self):
        cs=[(1,2),(2,3),(3,4)];t=[leaf([1,2],cs[:1]),leaf([2,3,4],cs[1:])]
        p=Portfolio(cs,4,t);p.add('base',cs,t,10);m=Retained(p)
        revised=leaf(range(1,5),cs);r=realize(cs,4,revised,m.session())
        self.assertEqual(r['count'],realize(cs,4,t)['count']);self.assertEqual(r['metrics']['new_full_checks'],1)

if __name__ == '__main__': unittest.main()
