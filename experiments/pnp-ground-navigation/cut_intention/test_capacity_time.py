"""CIG-027: exact capacity-constrained chronology and continuing migrations."""
import copy
import random
import unittest
from math import prod
from test_output_time import prepare
from run_output_time import expr_eval
from run_temporal_ground import step
from temporal_algebra import compile_algebra,Language,Budget
from temporal_image import Processor,capacity
from capacity_time import CapacityNavigator,threshold
from verify_capacity_time import CapacityAdmission


def build(k,w,p,f,initial,exprs,codec=None):
    nav,receiver=prepare(k,w,p,f,initial,exprs)
    proc=Processor(nav,initial,codec=codec)
    d,receipt=compile_algebra(nav,initial)
    lang=Language(d,receipt)
    return proc,CapacityNavigator(proc,lang),CapacityAdmission(receiver,proc.proof,receipt)


class CapacityTests(unittest.TestCase):
    def test_random_full_domain_and_ordinal(self):
        rng=random.Random(27027)
        for _ in range(80):
            w=rng.choice((1,2));m=rng.randrange(2,5);k=w*m
            p=list(range(m));rng.shuffle(p)
            f=[[rng.randrange(1<<w) for _ in range(1<<w)] for j in p]
            initial=rng.getrandbits(k);expr=('xor',0,k-1)
            proc,nav,rec=build(k,w,p,f,initial,[expr])
            rec.prepare_rank(nav.prepare_rank(0))
            image=set(range(1<<k));caps=[]
            # Explicit full source image until the decreasing finite chain stabilizes.
            while True:
                caps.append((len(image)-1).bit_length())
                next_image={step(x,k,w,p,f) for x in image}
                if next_image==image:break
                self.assertLess(len(next_image),len(image))
                image=next_image
            x=initial;history=[];seen={}
            while x not in seen:
                seen[x]=len(history);history.append(x);x=step(x,k,w,p,f)
            D=seen[x];P=len(history)-D
            def actual(t):
                return history[t if t<len(history) else D+(t-D)%P]
            for B in range(k+1):
                tau=next((t for t,b in enumerate(caps) if b<=B),None)
                self.assertEqual(threshold(proc,B),tau)
                start=rng.randrange(20)
                def expected(ordinal):
                    hits=[]
                    end=max(start,D,len(caps))+ordinal*P
                    for t in range(start,end+1):
                        if caps[min(t,len(caps)-1)]<=B and expr_eval(expr,actual(t)):
                            hits.append(t)
                            if len(hits)==ordinal:return t
                    return None
                for route,ordinal in (('next',1),('rank',1),('rank',3)):
                    receipt=nav.query(0,start,B,route=route,ordinal=ordinal)
                    self.assertTrue(rec.verify(0,start,B,receipt,route=route,ordinal=ordinal))
                    self.assertEqual(int(receipt['time']) if receipt['time'] is not None else None,
                                     expected(ordinal))

    def test_continuous_process_and_migration(self):
        # Two-bit transient block contracts to zero, then a two-bit rotating
        # marker pair continues alternating without retaining that block.
        p=[0,2,1];f=[[0,0,0,1],list(range(4)),list(range(4))]
        initial=3|(1<<2);exprs=[2,1]
        proc,nav,rec=build(6,2,p,f,initial,exprs)
        self.assertEqual([capacity(proc.alphabets(t))[1] for t in range(4)],[6,5,4,4])
        for B,expected in ((6,0),(5,2),(4,2),(3,None)):
            r=nav.query(0,0,B)
            self.assertTrue(rec.verify(0,0,B,r))
            self.assertEqual(None if r['time'] is None else int(r['time']),expected)
        # A transient goal was possible at t=0, but never under five bits.
        r=nav.query(1,0,5)
        self.assertEqual(r['status'],'UNREACHABLE')
        self.assertTrue(rec.verify(1,0,5,r))
        # Repeated strict temporal progress, using only the compact producer state.
        for start in (1,3,5,10**1000+173):
            r=nav.query(0,start,4)
            t=int(r['time']);move=proc.move(t)
            self.assertTrue(rec.accept_move(0,start,4,r,move))
            proc.commit(move)
            self.assertEqual((proc.time,proc.rank),(rec.image.time,rec.image.rank))
            self.assertEqual(t%2,0)
        rec.prepare_rank(nav.prepare_rank(0))
        start=proc.time+1;ordinal=10**900+173
        r=nav.query(0,start,4,ordinal=ordinal,route='rank')
        self.assertTrue(rec.verify(0,start,4,r,ordinal=ordinal,route='rank'))
        self.assertEqual(int(r['time']),start+start%2+2*(ordinal-1))

    def test_derived_intention_and_invalid_receipts(self):
        p=[0,2,1];f=[[0,0,0,1],list(range(4)),list(range(4))]
        proc,nav,rec=build(6,2,p,f,7,[2,1])
        neg=nav.language.extend('not',1)
        root=nav.language.extend('and',0,neg)
        rec.extend(nav.language.export())
        r=nav.query(root,0,4)
        self.assertEqual(r['time'],'2')
        move=proc.move(2)
        for field,bad in [('threshold','1'),('time','4'),('root',0),
                          ('bits',5),('ordinal','2'),('start','1'),
                          ('key','bad'),('status','UNKNOWN'),('evidence',None)]:
            forged=copy.deepcopy(r);forged[field]=bad
            self.assertFalse(rec.accept_move(root,0,4,forged,move),field)
            self.assertEqual((rec.image.time,rec.image.rank),(0,7))
        forged=copy.deepcopy(move);forged['bits']=3
        self.assertFalse(rec.accept_move(root,0,4,r,forged))
        self.assertEqual(rec.image.time,0)
        self.assertTrue(rec.accept_move(root,0,4,r,move))
        self.assertFalse(rec.accept_move(root,0,4,r,move))
        proc.commit(move)
        for B in (-1,True,7):
            with self.assertRaises(ValueError):nav.query(root,0,B)
        with self.assertRaises(ValueError):nav.query(root,0,4,ordinal=0)

    def test_rank_budget_and_identity(self):
        proc,nav,rec=build(3,1,[2,0,1],[[0,1]]*3,1,[0])
        with self.assertRaises(Budget):nav.prepare_rank(0,max_work=1)
        packet=nav.prepare_rank(0)
        forged=copy.deepcopy(packet);forged['terms'][0][2]+=1
        with self.assertRaises(ValueError):rec.prepare_rank(forged)
        rec.prepare_rank(packet)
        r=nav.query(0,0,2,route='rank',ordinal=2)
        self.assertTrue(rec.verify(0,0,2,r,route='rank',ordinal=2))
        self.assertIsNone(r['threshold'])
        self.assertFalse(rec.verify(0,0,3,r,route='rank',ordinal=2))

if __name__=='__main__':unittest.main()
