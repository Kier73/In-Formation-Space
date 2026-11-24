import copy,random,unittest
from math import prod
from test_output_time import prepare
from run_temporal_ground import step
from run_output_time import expr_eval
from temporal_algebra import compile_algebra, Language, Diagram, Budget
from verify_temporal_algebra import Admission

class AlgebraTests(unittest.TestCase):
    def test_random(self):
        rng=random.Random(24024)
        for _ in range(120):
            w=rng.choice([1,2]);k=w*rng.randrange(3,6);p=list(range(k//w));rng.shuffle(p)
            f=[[rng.randrange(2**w) for j in range(2**w)] for i in p];initial=rng.getrandbits(k)
            expr=[('xor',0,k-1),('and',1,k-1),('or',0,1)]
            nav,rec=prepare(k,w,p,f,initial,expr);d,r=compile_algebra(nav,initial);a=Admission(rec,r);l=Language(d,r)
            D=r['cutoff'];P=prod(r['base']);u=initial;rows=[]
            # Explicit independent trajectory over two complete periods plus shifts.
            for t in range(D+2*P+40):rows.append([expr_eval(e,u) for e in expr]);u=step(u,k,w,p,f)
            limit=len(rows)
            for op,x,y in [('and',0,1),('not',2,None),('xor',3,4),('shift',5,7),('or',5,6)]:
                j=l.extend(op,x,y)
                if op=='shift':limit-=y
                for t in range(limit):
                    if op=='shift':z=rows[t+y][x]
                    else:
                        z=1-rows[t][x] if op=='not' else rows[t][x]&rows[t][y] if op=='and' else rows[t][x]^rows[t][y] if op=='xor' else rows[t][x]|rows[t][y]
                    rows[t].append(z)
                # later unshifted operations only need the initialized range
                a.extend(l.export());self.assertEqual(a.count(j),l.count(j))
            for i in range(len(l.roots)):
                self.assertEqual(l.count(i),sum(row[i] for row in rows[D:D+P]))
                for t in range(D+P):self.assertEqual(l.membership(i,t),rows[t][i])
                start=rng.randrange(D+P+1);want=next((t for t in range(start,max(start,D)+P) if rows[t][i]),None);z=l.next(i,start)
                self.assertTrue(a.verify_next(i,start,z));self.assertEqual(int(z['time']) if z['time'] is not None else None,want)
                lo=rng.randrange(D+P+1);hi=lo+rng.randrange(P+2);z=l.interval(i,lo,hi);self.assertTrue(a.verify_interval(i,lo,hi,z));self.assertEqual(int(z['count']),sum(row[i] for row in rows[lo:hi]))
    def test_prime_power_repetition(self):
        # 2 and 4 cycle; one coordinate embeds the smaller period.
        n,r=prepare(6,1,[1,0,5,2,3,4],[[0,1]]*6,5,[('and',0,2)])
        d,p=compile_algebra(n,5);a=Admission(r,p);self.assertEqual(p['base'],[4]);self.assertEqual(a.count(0),1)
    def test_shift_large_and_transient(self):
        n,r=prepare(3,1,[0,2,1],[[0,0],[0,1],[0,1]],3,[0,('or',1,2)])
        d,p=compile_algebra(n,3);l=Language(d,p);a=Admission(r,p);self.assertEqual(p['cutoff'],1)
        j=l.extend('shift',0,10**1000);a.extend(l.export());self.assertEqual(a.count(j),0);self.assertTrue(a.verify_next(j,0,l.next(j,0)));self.assertEqual(l.next(j,0)['status'],'UNREACHABLE')
        self.assertEqual(l.next(0,0)['time'],'0');self.assertTrue(a.verify_next(0,0,l.next(0,0)))
    def test_forged_source(self):
        n,r=prepare(3,1,[2,0,1],[[0,1]]*3,1,[('xor',0,1)])
        d,p=compile_algebra(n,1)
        for key,val in [('initial','2'),('key','wrong'),('base',[2]),('outputs',[0]),('prefix',[[1]]),('cutoff',1),('refs',[[1,1]])]:
            z=copy.deepcopy(p);z[key]=val;self.assertRaises(ValueError,Admission,r,z)
        z=copy.deepcopy(p);z['nodes'][0][1]=[0,0,0];self.assertRaises(ValueError,Admission,r,z)
    def test_forged_extension_and_trace(self):
        n,r=prepare(5,1,[4,0,1,2,3],[[0,1]]*5,1,[('and',0,1),('xor',2,3)])
        d,p=compile_algebra(n,1);a=Admission(r,p);l=Language(d,p);i=l.extend('not',0);a.extend(l.export());self.assertEqual(len(a.roots),3)
        a.extend(l.export());self.assertEqual(len(a.roots),3)
        j=l.extend('shift',1,2);z=l.export();z['ops'][-1][-2]=0;self.assertRaises(ValueError,a.extend,z);self.assertEqual(len(a.roots),3)
        z=l.export();z['ops'][0][1]=1;self.assertRaises(ValueError,a.extend,z)
        a.extend(l.export());r=l.next(j,0);self.assertTrue(a.verify_next(j,0,r));z=copy.deepcopy(r);z['time']=str(int(r['time'])+5);self.assertFalse(a.verify_next(j,0,z));
        # Omitted work is invalid when the initial class lower bound is strictly earlier.
        start=next(t for t in range(5) if not l.membership(j,t));r=l.next(j,start);z=copy.deepcopy(r);z['trace']=[];self.assertFalse(a.verify_next(j,start,z))
    def test_budget(self):
        n,r=prepare(3,1,[2,0,1],[[0,1]]*3,1,[('xor',0,1)])
        self.assertRaises(Budget,compile_algebra,n,1,max_cells=1);self.assertRaises(Budget,compile_algebra,n,1,max_work=1)
        d,p=compile_algebra(n,1);l=Language(d,p);a=Admission(r,p);z=l.next(0,0,max_states=1);self.assertEqual(z['status'],'UNKNOWN');self.assertFalse(a.verify_next(0,0,z,max_states=1))
    def test_interval_huge_and_forgery(self):
        n,r=prepare(5,1,[4,0,1,2,3],[[0,1]]*5,1,[0]);d,p=compile_algebra(n,1);l=Language(d,p);a=Admission(r,p)
        lo=10**1000;hi=lo+5*10**900+3;z=l.interval(0,lo,hi);self.assertEqual(int(z['count']),10**900+1);self.assertTrue(a.verify_interval(0,lo,hi,z))
        z['count']='1';self.assertFalse(a.verify_interval(0,lo,hi,z));z=l.interval(0,0,2,max_states=1);self.assertEqual(z['status'],'UNKNOWN');self.assertFalse(a.verify_interval(0,0,2,z,max_states=1))
    def test_set_identities(self):
        n,r=prepare(5,1,[4,0,1,2,3],[[0,1]]*5,1,[('xor',0,1),('or',3,4)])
        d,p=compile_algebra(n,1);l=Language(d,p);a=Admission(r,p);i=l.extend('not',0);u=l.extend('or',0,i);v=l.extend('and',0,i);j=l.extend('xor',0,1);q=l.extend('shift',j,5);a.extend(l.export());self.assertEqual(a.count(u),5);self.assertEqual(a.count(v),0);self.assertEqual(l.roots[q],l.roots[j])
if __name__=='__main__':unittest.main()
