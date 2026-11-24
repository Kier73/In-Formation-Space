import random, unittest
from copy import deepcopy
from adaptive_ground import initial,revise,realize,Memory,leaf,balanced,annotate,flatten,semantic
from verify_adaptive_ground import audit,verify_projection
from regional_memory import discover,realize as frozen
from run_composed_ground import chain,xor_clauses
from composed_ground import canonical


def brute(c,n):
    return sum(all(any(bool(x>>(abs(l)-1)&1)==(l>0) for l in r) for r in c) for x in range(1<<n))

class AdaptiveTests(unittest.TestCase):
    def test_random_revisions(self):
        rng=random.Random(12010)
        for trial in range(100):
            n=rng.randrange(3,9); c=[tuple(v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),rng.randrange(1,4))) for _ in range(8)]
            p=initial(c,n); m=Memory()
            for step in range(5):
                if step:
                    if rng.randrange(2) and c:c.pop(rng.randrange(len(c)))
                    else:c.append(tuple(v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),rng.randrange(1,4))))
                    p,_=revise(p,c,n,merge=bool(step%2))
                self.assertEqual(int(realize(c,n,p,m)['count']),brute(c,n))
    def test_bridge_and_remove(self):
        n,c=chain(32);p=initial(c,n);m=Memory();a=realize(c,n,p,m);perm=list(range(1,n+1));random.Random(73).shuffle(perm)
        d=c+[(perm[0],-perm[16])]
        with self.assertRaises(OverflowError):frozen(d,n,discover(c,n))
        q,s=revise(p,d,n);b=realize(d,n,q,m);self.assertEqual(b['count'],'18');self.assertEqual(s['inserted_bridge_regions'],1)
        r,s=revise(q,c,n);z=realize(c,n,r,m);self.assertEqual(z['count'],a['count']);self.assertEqual(z['root'],a['root']);self.assertGreater(s['removed_empty_regions'],0)
    def test_split_merge(self):
        c=[(1,2),(3,4)];p=leaf(range(1,5),c);m=Memory();a=realize(c,4,p,m)
        q,s=revise(p,c,4);self.assertEqual(s['split_regions'],1);self.assertEqual(realize(c,4,q,m)['count'],'9')
        r,s=revise(q,c,4,split=False,merge=True);self.assertEqual(s['merged_regions'],1);b=realize(c,4,r,m);self.assertEqual(b['root'],a['root']);self.assertEqual(b['metrics']['proof_reuse'],1)
    def test_semantic_quiescence(self):
        # (1 OR 2) follows from unit 1; leaf scope already contains 2.
        c=[(1,),(-2,3)]; p=[leaf([1,2],[(1,)]),leaf([2,3],[(-2,3)])];m=Memory();a=realize(c,3,p,m)
        d=c+[(1,2)];q,_=revise(p,d,3,split=False);b=realize(d,3,q,m)
        self.assertEqual(a['count'],b['count']);self.assertNotEqual(a['root'],b['root']);self.assertEqual(b['metrics']['semantic_join_reuse'],1);self.assertEqual(b['metrics']['new_full_checks'],1)
    def test_projection(self):
        c=[(1,2),(-2,3)];p=[leaf([1,2],[(1,2)]),leaf([2,3],[(-2,3)])];m=Memory();realize(c,3,p,m)
        d=[(1,2)];q=[leaf([1,2],[(1,2)]),leaf([3],[])];b=realize(d,3,q,m)
        self.assertEqual(b['count'],'6');self.assertEqual(b['metrics']['projected_leaf'],1)
    def test_changed_language(self):
        c=xor_clauses((1,2,3));p=leaf([1,2,3],c);m=Memory();a=realize(c,3,p,m);self.assertEqual(a['metrics']['affine'],1)
        d=c+[(1,2)];q,_=revise(p,d,3);b=realize(d,3,q,m);self.assertEqual(b['metrics']['boolean'],1);self.assertEqual(b['count'],'3')
    def test_missing_clause(self):
        p=leaf([1,2],[(1,)])
        with self.assertRaises(ValueError):realize([(1,),(-2,)],2,p)
    def test_duplicate_clause(self):
        p=[leaf([1],[(1,)]),leaf([1],[(1,)])]
        with self.assertRaises(ValueError):realize([(1,)],1,p)
    def test_missing_variable(self):
        with self.assertRaises(ValueError):realize([],2,leaf([1],[]))
    def test_forged_boundary(self):
        p=[leaf([1,2],[(1,2)]),leaf([2,3],[(-2,3)])];r=annotate(p);r['children'][0]['boundary']=[]
        self.assertFalse(audit([(1,2),(-2,3)],3,p,r))
    def test_bad_projection(self):
        self.assertFalse(verify_projection({'boundary':[1],'counts':['1','2']},{'boundary':[],'counts':['2']}))
    def test_memory_not_mutable(self):
        p=leaf([1,2],[(1,2)]);m=Memory();r=realize([(1,2)],2,p,m);next(iter(r['messages'].values()))['counts'][0]='999'
        self.assertEqual(realize([(1,2)],2,p,m)['count'],'3')
    def test_free_and_empty_clause(self):
        c=[];p=initial(c,8);m=Memory();self.assertEqual(realize(c,8,p,m)['count'],'256');d=[()];q,_=revise(p,d,8);self.assertEqual(realize(d,8,q,m)['count'],'0')
    def test_width_refusal(self):
        c=[];p=initial(c,13)
        with self.assertRaises(OverflowError):revise(p,[tuple(range(1,14))],13)
    def test_reassociate_commutative(self):
        c=[(1,2),(-2,3)];p=[leaf([1,2],[(1,2)]),leaf([2,3],[(-2,3)])];m=Memory();a=realize(c,3,p,m);b=realize(c,3,p[::-1],m)
        self.assertEqual(a['count'],b['count']);self.assertEqual(b['metrics']['semantic_join_reuse'],1)

if __name__=='__main__':unittest.main()
