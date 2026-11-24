"""CIG-028: schedule/ordinal controls, native migration and process recovery."""
import copy
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from test_capacity_time import build
from run_temporal_ground import step
from run_output_time import expr_eval
from availability_time import AvailabilityNavigator
from verify_availability_time import AvailabilityAdmission
from continuation_checkpoint import save,recover

WINDOWS=((0,1,'host-A',6),(1,3,'host-A',5),
         (10,15,'host-B',4),(20,None,'host-C',4))


def setup(windows=WINDOWS):
    p=[0,2,1];f=[[0,0,0,1],list(range(4)),list(range(4))]
    proc,planner,cap=build(6,2,p,f,7,[2,1])
    cap.prepare_rank(planner.prepare_rank(0))
    cap.prepare_rank(planner.prepare_rank(1))
    return proc,planner,AvailabilityNavigator(planner,windows),AvailabilityAdmission(cap,windows)


def worker(path,digest):
    # Reconstruct the original proof/transport from the independent fixture.
    # No producer object or admitted rank from the previous process survives.
    old,planner,_,rec=setup()
    proc=recover(rec,old.nav,7,path,digest)
    planner.processor=proc
    nav=AvailabilityNavigator(planner,WINDOWS)
    r=nav.query(0,proc.time+1)
    move=proc.move(int(r['time']))
    assert rec.accept_move(0,proc.time+1,1,r,move)
    proc.commit(move)
    print(json.dumps(dict(key=proc.key,time=str(proc.time),rank=str(proc.rank),
                          host=rec.host,receipt=r,move=move)))


class AvailabilityTests(unittest.TestCase):
    def test_continuity_and_ordinal(self):
        proc,planner,nav,rec=setup()
        for ordinal,t in enumerate((0,2,10,12,14,20,22),1):
            r=nav.query(0,0,ordinal)
            self.assertEqual(int(r['time']),t)
            self.assertTrue(rec.verify(0,0,ordinal,r))
        r=nav.query(0,0,2);m=proc.move(2)
        self.assertTrue(rec.accept_move(0,0,2,r,m));proc.commit(m)
        r=nav.query(0,3);self.assertEqual(r['host'],'host-B')
        self.assertEqual(r['time'],'10')
        m=proc.move(10)
        self.assertTrue(rec.accept_move(0,3,1,r,m));proc.commit(m)
        r=nav.query(0,15);self.assertEqual(r['time'],'20')
        m=proc.move(20)
        self.assertTrue(rec.accept_move(0,15,1,r,m));proc.commit(m)
        self.assertEqual(rec.host,'host-C')
        start=10**1000+173;j=10**900+173
        r=nav.query(0,start,j)
        self.assertTrue(rec.verify(0,start,j,r))
        self.assertEqual(int(r['time']),start+start%2+2*(j-1))

    def test_gaps_and_refusals(self):
        for windows in ((),((1,None,'tiny',3),),((1,2,'A',6),)):
            _,_,n,r=setup(windows)
            z=n.query(0,0)
            self.assertEqual(z['status'],'UNREACHABLE')
            self.assertTrue(r.verify(0,0,1,z))
        # Zero-bit capacity is an available host, not a gap.
        proc,p,cap=build(2,1,[0,1],[[0,0],[1,1]],0,[1])
        cap.prepare_rank(p.prepare_rank(0))
        windows=((1,2,'zero',0),)
        n=AvailabilityNavigator(p,windows);r=AvailabilityAdmission(cap,windows)
        z=n.query(0,0);self.assertEqual(z['time'],'1')
        self.assertTrue(r.accept_move(0,0,1,z,proc.move(1)))
        for windows in (((0,3,'A',6),(2,None,'B',6)),
                        ((0,None,'A',6),(10,None,'B',6)),
                        ((0,1,'',6),),((0,1,'A',True),)):
            with self.assertRaises(ValueError):AvailabilityNavigator(p,windows)
            with self.assertRaises(ValueError):AvailabilityAdmission(cap,windows)

    def test_forgery_and_checkpoint(self):
        proc,planner,nav,rec=setup()
        r=nav.query(0,1);m=proc.move(2)
        for field,value in [('time','4'),('host','host-C'),('window',2),
                            ('ordinal','2'),('schedule','bad'),('status','UNREACHABLE')]:
            z=copy.deepcopy(r);z[field]=value
            self.assertFalse(rec.accept_move(0,1,1,z,m),field)
            self.assertEqual(rec.capacity.image.time,0)
        self.assertTrue(rec.accept_move(0,1,1,r,m));proc.commit(m)
        old=rec.snapshot()
        z=nav.query(0,3);m=proc.move(10)
        self.assertTrue(rec.accept_move(0,3,1,z,m));proc.commit(m)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'checkpoint.json'
            digest=save(rec,path)
            fresh,p,n,admitted=setup()
            self.assertFalse(admitted.restore(old,digest))
            bad=rec.snapshot();bad['state']['rank']='0'
            self.assertFalse(admitted.restore(bad,digest))
            replacement=recover(admitted,fresh.nav,7,path,digest)
            self.assertEqual((replacement.key,replacement.time,replacement.rank),
                             (proc.key,proc.time,proc.rank))
            self.assertFalse(admitted.restore(rec.snapshot(),digest))
            # Spawn a wholly separate Python process from the durable coordinate.
            out=subprocess.check_output([sys.executable,__file__,'worker',str(path),digest],
                                         text=True,timeout=60)
            result=json.loads(out)
            self.assertEqual(result['key'],proc.key)
            self.assertEqual(result['host'],'host-B')
            self.assertEqual(result['time'],'12')
            self.assertTrue(rec.accept_move(0,11,1,result['receipt'],result['move']))

    def test_random_explicit_chronology(self):
        rng=random.Random(28028)
        for _ in range(40):
            w=rng.choice((1,2));m=rng.randrange(2,5);k=w*m
            p=list(range(m));rng.shuffle(p)
            f=[[rng.randrange(1<<w) for _ in range(1<<w)] for j in p]
            initial=rng.getrandbits(k);expr=('xor',0,k-1)
            _,planner,cap=build(k,w,p,f,initial,[expr])
            cap.prepare_rank(planner.prepare_rank(0))
            image=set(range(1<<k));caps=[]
            while True:
                caps.append((len(image)-1).bit_length())
                z={step(x,k,w,p,f) for x in image}
                if z==image:break
                image=z
            history=[];seen={};x=initial
            while x not in seen:
                seen[x]=len(history);history.append(x);x=step(x,k,w,p,f)
            D=seen[x];P=len(history)-D
            for j in range(8):
                windows=((0,3,'A',rng.randrange(k+1)),
                         (6,12,'B',rng.randrange(k+1)),
                         (15,None if j%2 else 30,'C',rng.randrange(k+1)))
                nav=AvailabilityNavigator(planner,windows);rec=AvailabilityAdmission(cap,windows)
                start=rng.randrange(20);ordinal=rng.randrange(1,5);hits=[]
                for t in range(start,max(30,D,len(caps))+ordinal*P+1):
                    x=history[t if t<len(history) else D+(t-D)%P]
                    if expr_eval(expr,x) and any(a<=t and (b is None or t<b) and
                        caps[min(t,len(caps)-1)]<=B for a,b,_,B in windows):
                        hits.append(t)
                        if len(hits)==ordinal:break
                expected=hits[-1] if len(hits)==ordinal else None
                r=nav.query(0,start,ordinal)
                self.assertTrue(rec.verify(0,start,ordinal,r))
                self.assertEqual(int(r['time']) if r['time'] is not None else None,expected)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='worker':worker(sys.argv[2],sys.argv[3])
    else:unittest.main()
