"""Original CNF replay and adversarial certificates for CIG-014."""
import copy,random,unittest
from nonlinear_sufficient import make_seed,plan,translate,PredicateRetained
from verify_nonlinear_sufficient import check_seed,check_translation
from anticipatory_memory import descriptor
from architecture_memory import region
from composed_ground import canonical
from verify_regional_memory import verify_message
from adaptive_ground import realize
from run_nonlinear_sufficient import fixture,oracle

class TestPredicateFibers(unittest.TestCase):
    def setUp(self):
        self.n=6;self.s=list(range(1,7));self.c=[[-1,2,3]];self.v=[1,2];self.p=[[3,4],[-3,-4],[5,6]]
        self.seed,self.stats=make_seed(self.n,self.s,self.c,self.v,self.p)
    def query(self,extra,b=(1,2)):
        return descriptor(region(self.s,canonical(self.c+extra,self.n)),b)
    def test_seed(self):
        self.assertTrue(check_seed(self.n,self.s,self.c,self.v,self.p,self.seed));self.assertEqual(sum(int(v) for _,v in self.seed['bins']),56)
    def test_exact_and_union(self):
        for extras in ([[3,4]],[[3,4,5,6]],[[1,3,4]],[[3,4],[-3,-4]], [[]]):
            d=self.query(extras,(1,));p=plan(self.seed,d);self.assertIsNotNone(p);m=translate(self.seed,d,p);self.assertTrue(check_translation(self.n,self.seed,d,p,m));self.assertTrue(verify_message(d,None,m))
    def test_missing_predicate(self): self.assertIsNone(plan(self.seed,self.query([[3]])))
    def test_missing_output(self): self.assertIsNone(plan(self.seed,self.query([], (3,))))
    def test_deletion_and_scope(self):
        d=self.query([]);d['clauses']=[];self.assertIsNone(plan(self.seed,d));d=self.query([]);d['scope']=d['scope'][:-1];self.assertIsNone(plan(self.seed,d))
    def test_forged_histogram(self):
        bad=copy.deepcopy(self.seed);bad['bins'][0][1]='999';self.assertFalse(check_seed(self.n,self.s,self.c,self.v,self.p,bad))
    def test_forged_width(self):
        bad=copy.deepcopy(self.seed);bad['bits']+=1;self.assertFalse(check_seed(self.n,self.s,self.c,self.v,self.p,bad))
    def test_contract_binding(self):
        self.assertFalse(check_seed(self.n,self.s,self.c,self.v,self.p+[[5]],self.seed))
    def test_forged_cover(self):
        d=self.query([[3,4,5,6]]);p=plan(self.seed,d);m=translate(self.seed,d,p);p[0][1].pop();self.assertFalse(check_translation(self.n,self.seed,d,p,m))
    def test_forged_output(self):
        d=self.query([[3,4]]);p=plan(self.seed,d);m=translate(self.seed,d,p);m['counts'][0]='999';self.assertFalse(check_translation(self.n,self.seed,d,p,m))
    def test_empty_source_model_set(self):
        seed,_=make_seed(2,[1,2],[[1],[-1]],[2],[[1,2]]);self.assertEqual(seed['bins'],[]);self.assertTrue(check_seed(2,[1,2],[[1],[-1]],[2],[[1,2]],seed))
    def test_random_original_cnf(self):
        rng=random.Random(73)
        for _ in range(350):
            n=rng.randint(2,8);s=list(range(1,n+1));v=sorted(rng.sample(s,rng.randint(0,n)))
            def row():return [u*rng.choice((-1,1)) for u in rng.sample(s,rng.randint(1,min(n,4)))]
            c=canonical([row() for _ in range(rng.randint(0,8))],n);p=canonical([row() for _ in range(5)],n)
            seed,_=make_seed(n,s,c,v,p);self.assertTrue(check_seed(n,s,c,v,p,seed))
            # Arbitrary disjunctions of retained clauses; tautologies are normalized away.
            extra=canonical([list(set(p[0])|set(p[-1])),*p[:2]],n)
            d=descriptor(region(s,canonical(c+extra,n)),v[:len(v)//2]);q=plan(seed,d);self.assertIsNotNone(q)
            m=translate(seed,d,q);self.assertTrue(check_translation(n,seed,d,q,m));self.assertTrue(verify_message(d,None,m))
    def test_connected_heldout(self):
        n,(source,t),qs=fixture(5);r=PredicateRetained(source,n,t,qs[:4]);self.assertLess(r.stats['bins'],r.stats['coordinate_cells'])
        for j,(s,t) in enumerate(qs):
            m=realize(s,n,t,r.session());self.assertEqual(int(m['count']),oracle(5,j));self.assertEqual(m['metrics'].get('predicate_reuse',0),5)
            if j in (5,6):self.assertEqual(m['metrics']['novel_clause_covers'],5)
    def test_fallback_to_fresh(self):
        from adaptive_ground import leaf
        s=[[1,2,3]];t=leaf([1,2,3],s);r=PredicateRetained(s,3,t,[])
        revised=[[1,2,3],[1]];m=realize(revised,3,leaf([1,2,3],revised),r.session());self.assertEqual(m['count'],'4');self.assertEqual(m['metrics']['new_full_checks'],1)

if __name__=='__main__':unittest.main()
