import copy
import itertools
import random
import unittest
from regional_memory import discover,bind,realize,VerifiedMemory,wire,identity,produce
from verify_regional_memory import audit_layout,verify_message
from run_composed_ground import chain,xor_clauses
from composed_ground import compile_ground
from verify_composed_ground import verify


def brute(n,c):
    return sum(all(any(x>>(abs(l)-1)&1==int(l>0) for l in row) for row in c) for x in range(1<<n))


def pivot(stages,n,seed=73):
    perm=list(range(1,n+1));random.Random(seed).shuffle(perm)
    return perm[stages//2]

class RegionalTests(unittest.TestCase):
    def test_250_random_source_counts(self):
        rng=random.Random(619)
        for _ in range(250):
            n=rng.randrange(1,10); c=[tuple(v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),rng.randrange(0,min(n,3)+1))) for i in range(rng.randrange(0,20))]
            plan=discover(c,n,width=10); r=realize(c,n,plan)
            self.assertEqual(int(r['count']),brute(n,c))
            if r['witness'] is not None:
                self.assertTrue(all(any(int(r['witness'][abs(l)-1])==int(l>0) for l in row) for row in c))
    def test_cig008_same_source(self):
        n,c=chain(16); old=compile_ground(c,n); self.assertTrue(verify(c,n,old));r=realize(c,n,discover(c,n));self.assertEqual(r['count'],old['count'])
    def test_revision_positive_and_restore(self):
        n,c=chain(32);p=discover(c,n);m=VerifiedMemory();a=realize(c,n,p,m);v=pivot(32,n);b=realize(c+[(v,)],n,p,m);d=realize(c,n,p,m)
        self.assertEqual((a['count'],b['count'],d['count']),('34','17','34'))
        self.assertEqual(b['metrics']['reuse'],57);self.assertEqual(d['metrics']['reuse'],63);self.assertEqual(a['root'],d['root'])
    def test_revision_unsat_and_weakening(self):
        n,c=chain(8);p=discover(c,n);m=VerifiedMemory();v=pivot(8,n);a=realize(c+[(v,),(-v,)],n,p,m);b=realize(c,n,p,m);self.assertEqual((a['count'],b['count']),('0','10'))
    def test_receiver_delta(self):
        n,c=chain(16);p=discover(c,n);producer=VerifiedMemory();receiver=VerifiedMemory();a=realize(c,n,p,producer);b=realize(c,n,p,receiver,incoming=a['messages']);self.assertEqual(a['root'],b['root']);d=c+[(pivot(16,n),)];r=realize(d,n,p,producer);delta={k:v for k,v in r['messages'].items() if k not in a['messages']};rr=realize(d,n,p,receiver,incoming=delta);self.assertEqual(r['root'],rr['root']);self.assertEqual(rr['metrics']['received'],len(delta))
    def test_forged_wire(self):
        n,c=chain(4);p=discover(c,n);r=realize(c,n,p);packet=copy.deepcopy(r['messages']);k=next(iter(packet));packet[k]['counts'][0]=str(int(packet[k]['counts'][0])+1)
        with self.assertRaises(ValueError):realize(c,n,p,incoming=packet)
    def test_stale_messages(self):
        n,c=chain(4);p=discover(c,n);r=realize(c,n,p)
        with self.assertRaises(KeyError):realize(c+[(pivot(4,n),)],n,p,incoming=r['messages'])
    def test_unadmitted_child(self):
        m=VerifiedMemory();d={'version':'ifs.cig009.count-message.v1','scope':[1],'boundary':[1],'clauses':[]};a,_,_=produce(d,None);parent={'version':d['version'],'boundary':[],'children':[identity(a),identity(a)]}
        with self.assertRaises(ValueError):m.obtain(parent,[a,a])
    def test_returned_message_mutation_does_not_poison(self):
        n,c=chain(4);p=discover(c,n);m=VerifiedMemory();a=realize(c,n,p,m);next(iter(a['messages'].values()))['counts'][0]='999';b=realize(c,n,p,m);self.assertEqual(b['count'],'6')
    def test_cross_region_refused(self):
        n,c=chain(8);p=discover(c,n);pair=next((a,b) for a in range(1,n+1) for b in range(a+1,n+1) if not any({a,b}<=set(s) for s in p['leaves']))
        with self.assertRaises(OverflowError):realize(c+[pair],n,p)
    def test_layout_tamper(self):
        n,c=chain(4);p=discover(c,n);rows,cs,t=bind(c,n,p);self.assertTrue(audit_layout(c,n,p,cs,t));t['children'][0]['boundary']=();self.assertFalse(audit_layout(c,n,p,cs,t))
    def test_missing_source_clause(self):
        n,c=chain(4);p=discover(c,n);rows,cs,t=bind(c,n,p);cs[0].pop();self.assertFalse(audit_layout(c,n,p,cs,t))
    def test_free_coordinates(self):
        self.assertEqual(realize([],100,discover([],100))['count'],str(2**100))
    def test_affine_and_boolean_interfaces(self):
        c=[(-1,-2,3),(1,-3),(2,-3)]+xor_clauses((3,4,5)); p={'n':5,'leaves':[[1,2,3],[3,4,5]]};r=realize(c,5,p);self.assertEqual(r['count'],'8');self.assertEqual(r['metrics']['affine'],1);self.assertEqual(r['metrics']['boolean'],1)
    def test_count_typed_strictly(self):
        d={'version':'ifs.cig009.count-message.v1','scope':[1],'boundary':[],'clauses':[]};r,_,_=produce(d,None);r['counts']=[2];self.assertFalse(verify_message(d,None,r))
    def test_dense_block_refusal(self):
        c=[(i,j) for i in range(1,12) for j in range(i+1,12)]
        with self.assertRaises(OverflowError):discover(c,11)
    def test_unchanged_canonical_source(self):
        n,c=chain(8);p=discover(c,n);m=VerifiedMemory();a=realize(c,n,p,m);b=realize(list(reversed(c))+[c[0],(1,-1)],n,p,m);self.assertEqual(a['source'],b['source']);self.assertEqual(b['metrics']['reuse'],15)

if __name__=='__main__': unittest.main()
