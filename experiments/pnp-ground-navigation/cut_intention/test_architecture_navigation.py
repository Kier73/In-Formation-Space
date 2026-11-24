"""CIG-011 exact selection and independent source-replay controls."""
import random,unittest
from itertools import product
from architecture_navigation import (score,select,select_widths,packed,optimize_order,pareto)
from adaptive_ground import leaf,balanced,realize,Memory,initial,revise
from composed_ground import canonical
from run_architecture_navigation import cycle,oracle


def trees(xs):
    if len(xs)==1:yield xs[0];return
    for k in range(1,len(xs)):
        for a in trees(xs[:k]):
            for b in trees(xs[k:]):yield [a,b]


def brute(n,c):
    return sum(all(any(a[abs(l)-1]==(l>0) for l in row) for row in c) for a in product((0,1),repeat=n))


class ArchitectureTests(unittest.TestCase):
    def test_exact_ordered_optimum(self):
        # Independent exhaustive parenthesization oracle on 35 small sources.
        rng=random.Random(731)
        for _ in range(35):
            n=7;rows=canonical([tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),2)) for _ in range(6)],n)
            ls=[leaf(set(map(abs,c)),[c]) for c in rows];used=set(v for t in ls for v in t['scope'])
            if set(range(1,n+1))-used:ls.append(leaf(set(range(1,n+1))-used,[]))
            p,ledger=optimize_order(ls,window=16)
            vals=[(s['cells'],s['depth']) for t in trees(ls) for s in [score(rows,n,t)]]
            got=score(rows,n,p)
            self.assertEqual((got['cells'],got['depth']),min(vals))
            self.assertEqual(ledger['estimated_cells'],got['cells'])
    def test_cyclic_source_against_exhaustive(self):
        for seed in range(5):
            n,c,_=cycle(4,seed);p=select_widths(c,n)
            self.assertEqual(int(realize(c,n,p['tree'])['count']),brute(n,c))
    def test_arbitrary_small_cnf(self):
        rng=random.Random(119)
        for i in range(120):
            n=1+i%7;c=[tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),rng.randint(0,min(n,3)))) for _ in range(i%12)]
            p=select_widths(c,n)
            self.assertEqual(p['status'],'SELECTED')
            r=realize(c,n,p['tree'])
            self.assertEqual(int(r['count']),brute(n,c))
            self.assertLessEqual(r['metrics'].get('producer_cells',0),p['score']['cells'])
    def test_cycle_old_refuses_new_admits(self):
        n,c,_=cycle(32)
        with self.assertRaises(OverflowError):initial(c,n)
        p=select_widths(c,n);self.assertEqual(int(realize(c,n,p['tree'])['count']),oracle(32))
    def test_price_changes_architecture(self):
        n,c,_=cycle(64)
        a=select_widths(c,n,message_weight=0);b=select_widths(c,n,message_weight=1000)
        self.assertLess(a['score']['cells'],b['score']['cells']);self.assertGreater(a['score']['nodes'],b['score']['nodes'])
        self.assertEqual(realize(c,n,a['tree'])['count'],realize(c,n,b['tree'])['count'])
        self.assertEqual(b['score']['objective'],min(q['objective'] for q in b['candidates'] if q['status']=='ADMITTED'))
    def test_pareto(self):
        self.assertEqual(pareto([dict(status='ADMITTED',cells=a,nodes=b) for a,b in [(1,5),(2,6),(3,4),(3,3),(6,1)]]),[[1,5],[3,3],[6,1]])
    def test_bad_price(self):
        for v in (-1,True,0.5):
            with self.assertRaises(ValueError):select([(1,)],1,message_weight=v)
    def test_missing_clause_refused(self):
        n,c,_=cycle(4);p=select(c,n)['tree']
        with self.assertRaises(ValueError):score(c+[(1,)],n,p)
    def test_duplicate_clause_ownership_refused(self):
        with self.assertRaises(ValueError):score([(1,)],1,[leaf([1],[(1,)]),leaf([1],[(1,)])])
    def test_missing_free_coordinate_refused(self):
        with self.assertRaises(ValueError):score([(1,)],2,leaf([1],[(1,)]))
    def test_same_partition_reassociation(self):
        n,c,_=cycle(64);ls=packed(c,n,'walk',8);a=balanced(ls);b,_=optimize_order(ls);m=Memory()
        r=realize(c,n,a,m);s=realize(c,n,b,m);f=realize(c,n,b,Memory())
        self.assertEqual(r['count'],s['count']);self.assertEqual(s['root'],f['root']);self.assertGreater(s['metrics'].get('proof_reuse',0),0)
        restored=realize(c,n,a,m);self.assertEqual(restored['root'],r['root']);self.assertEqual(restored['metrics'].get('new_full_checks',0),0)
    def test_revision_after_rearchitecture(self):
        n,c,x=cycle(32);a=select_widths(c,n);m=Memory();realize(c,n,a['tree'],m)
        d=c+[(x[0],),(-x[1],)];b,_=revise(a['tree'],d,n,split=False)
        self.assertEqual(realize(d,n,b,m)['count'],'0')
    def test_budget_unknown(self):
        rng=random.Random(73);n=50;c=[tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),3)) for _ in range(213)]
        self.assertEqual(select_widths(c,n)['status'],'UNKNOWN')
    def test_free_variables_and_empty_clause(self):
        for c,expected in (([],16),([()],0)):
            p=select_widths(c,4);self.assertEqual(int(realize(c,4,p['tree'])['count']),expected)

if __name__=='__main__':unittest.main()
