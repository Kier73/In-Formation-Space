import unittest,random,json,math
from dataclasses import replace
from ground_network import View,Work,select
from skill_language import compile_view
from verify_skill_language import verify_pullback
from test_skill_language import random_view
from family_language import FamilyIntelligence,event_phases,partitions,express,eligible,crt
from verify_family_language import verify_expression,qualify_family


def pulse(seed,base=(29,31,37),cutoff=0,events=2):
    rng=random.Random(seed);P=math.prod(base);r=rng.randrange(P);nodes=[];unique={}
    phases=tuple((r+j)%P for j in range(events))
    def build(j,seq):
        if not seq:return 0
        if j==len(base):return 1
        ch=tuple(build(j+1,tuple(t for t in seq if t%base[j]==x)) for x in range(base[j]))
        if len(set(ch))==1:return ch[0]
        row=(j,ch)
        if row not in unique:unique[row]=len(nodes)+2;nodes.append(row)
        return unique[row]
    root=build(0,phases)
    return View('pulse:'+str(seed),base,tuple(nodes),root,cutoff,rng.getrandbits(cutoff)),phases


def anonymous(v,tag):return View('unseen:'+str(tag),v.base,v.nodes,v.root,v.cutoff,v.prefix)

def trace(form):
    a,b,c=form
    return (('advance',b),('stride',a))+((('flip',0),) if c else ())

def train():
    m=FamilyIntelligence()
    for i in range(6):
        for maker in (lambda:pulse(i)[0],lambda:random_view(i,cutoff=0)):
            a=maker();f=(2+i,7+3*i,i%2);b,_=compile_view(a,f)
            assert m.observe(a,anonymous(b,'train'+a.key),trace(f))
    assert len(m.induce())==2
    return m

class FamilyTests(unittest.TestCase):
    def test_sparse_full_period_and_contraction(self):
        m=train();rng=random.Random(30)
        for i in range(100):
            a,old=pulse(100+i,(4,9,5,7),cutoff=i%5)
            f=(rng.randrange(1,500),rng.randrange(0,600),i%2);b,_=compile_view(a,f);b=anonymous(b,i)
            z,d=m.discover(a,b)
            self.assertIsNotNone(z,(i,f,b.total,d))
            self.assertTrue(verify_pullback(a,b,z)[0]);self.assertTrue(all(b.bit(t)==a.bit(z[0]*t+z[1])^z[2] for t in range(a.period+8)))
    def test_dense_unknown_parameters(self):
        m=train();rng=random.Random(20)
        for i in range(60):
            a=random_view(500+i,(5,7,11),cutoff=i%6);aa=rng.randrange(1,a.period)
            while math.gcd(aa,a.period)!=1:aa+=1
            f=(aa,rng.randrange(a.period),i%2);b,_=compile_view(a,f);b=anonymous(b,i)
            z,d=m.discover(a,b);self.assertIsNotNone(z,(i,f,d));self.assertTrue(verify_pullback(a,b,z)[0]);self.assertTrue(all(b.bit(t)==a.bit(z[0]*t+z[1])^z[2] for t in range(a.period+6)))
    def test_prefix_lifts(self):
        # Same residue form but prefix changes on a large lift. Need full proof.
        m=train();a,ph=pulse(121,(2,3),cutoff=7,events=2)
        for f in [(1,0,0),(7,0,1),(1,6,0),(13,12,1),(2,0,0)]:
            b,_=compile_view(a,f);b=anonymous(b,f);z,d=m.discover(a,b)
            if b.total not in (0,b.period):self.assertIsNotNone(z,(f,d));self.assertTrue(verify_pullback(a,b,z)[0])
    def test_coupled_and_unrelated_same_basis(self):
        # Irregular full table, not a product of local Boolean predicates.
        # Use 3*5*7 so the sparse dispatcher cannot treat the dense table as rare.
        from itertools import product
        rng=random.Random(91);m=train();base=(3,5,7);P=math.prod(base)
        def table(tag,bits):
            nodes=[];unique={}
            def rec(j,res):
                if j==len(base):return bits[crt(zip(res,base))]
                kids=tuple(rec(j+1,res+(r,)) for r in range(base[j]))
                if len(set(kids))==1:return kids[0]
                key=(j,kids)
                if key not in unique:unique[key]=len(nodes)+2;nodes.append(key)
                return unique[key]
            root=rec(0,());return View(tag,base,tuple(nodes),root)
        bits=[int(t<52) for t in range(P)];rng.shuffle(bits);a=table('coupled',bits)
        f=(2,17,1);b=table('coupled-target',[bits[(2*t+17)%P]^1 for t in range(P)])
        z,d=m.discover(a,b,max_candidates=10000);self.assertIsNotNone(z);self.assertTrue(verify_pullback(a,b,z)[0]);self.assertGreater(d['attempts'],1)
        # Same cardinality and local basis, unrelated truth arrangement.
        other=bits.copy();rng.shuffle(other);c=table('coupled-other',other)
        self.assertFalse(any(all(other[t]==bits[(a0*t+b0)%P] for t in range(P)) for a0 in range(1,P) if math.gcd(a0,P)==1 for b0 in range(P)))
        self.assertIsNone(m.discover(a,c,max_candidates=10000,max_work=2_000_000)[0])
        self.assertIsNone(m.discover(a,b,max_candidates=1)[0])
    def test_partitions_exact(self):
        for i in range(25):
            a=random_view(i,(4,3,5),cutoff=0);p=partitions(a,Work(100000))
            for j,m in enumerate(a.base):
                for r in range(m):
                    for s in range(m):
                        same=all(a.bit(t)==a.bit(t+(s-r)* (a.period//m)*pow(a.period//m,-1,m) %a.period) for t in range(a.period) if t%m==r)
                        self.assertEqual(p[j][r]==p[j][s],same)
    def test_restore_and_forgery(self):
        m=train();p=m.packet();views={v.key:v for a,b,_ in m.examples.values() for v in (a,b)}
        n=FamilyIntelligence.restore(json.loads(json.dumps(p)),views);self.assertEqual(n.packet(),p)
        f=m.families['cofactor'];self.assertFalse(qualify_family(replace(f,examples=(f.examples[0],)*3),m.examples))
        p['examples'][0][2][2]^=1
        with self.assertRaises(ValueError):FamilyIntelligence.restore(p,views)
        a,_=pulse(999);b,_=compile_view(a,(17,43,0));z,d=n.discover(a,b);self.assertIsNotNone(z);k=10**900+173;out=express(a,b,z,k);self.assertTrue(verify_expression(a,b,z,k,out));out['time']=str(int(out['time'])+1);self.assertFalse(verify_expression(a,b,z,k,out))
    def test_budgets_and_untrained(self):
        m=train();a,_=pulse(999);b,_=compile_view(a,(17,43,0));self.assertIsNone(FamilyIntelligence().discover(a,b)[0]);self.assertIsNone(m.discover(a,b,max_work=1)[0]);self.assertIsNone(m.discover(a,View('unoffered',(13,),((0,tuple(int(i==0) for i in range(13))),),2),max_work=1000)[0]);self.assertFalse(m.observe(a,b,trace((17,43,1))))
        p=m.packet();v={v.key:v for a,b,_ in m.examples.values() for v in (a,b)};p['families'][0][2]=p['families'][0][2][:-1]
        with self.assertRaises(ValueError):FamilyIntelligence.restore(p,v)
    def test_constant_and_callable_family(self):
        m=train();a,ph=pulse(414,(29,31,37));d=29
        b0=next(x for x in range(d) if x not in {p%d for p in ph})
        for c in (0,1):
            b,_=compile_view(a,(d,b0,c));z,stats=m.discover(a,b);self.assertIsNotNone(z);self.assertEqual(b.total,c*b.period);self.assertTrue(verify_pullback(a,b,z)[0])
            # No target is supplied to the callable instantiation.
            a2,_=pulse(415,(29,31,37));new,stats=m.instantiate(a2,'sparse',z);self.assertTrue(verify_pullback(a2,new,z)[0])
        with self.assertRaises(ValueError):FamilyIntelligence().instantiate(a,'sparse',(1,0,0))
        self.assertIsNone(m.instantiate(a,'cofactor',(29,0,0)))
    def test_sparse_extraction_complement(self):
        for i in range(20):
            a,ph=pulse(i,(4,3,5),events=3);self.assertEqual(event_phases(a,1,Work(10000),32),sorted(ph));b,_=compile_view(a,(1,0,1));self.assertEqual(event_phases(b,0,Work(10000),32),sorted(ph));self.assertIsNone(event_phases(b,1,Work(10000),32))
