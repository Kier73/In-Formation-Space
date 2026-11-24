import unittest,random,json
from dataclasses import replace
from math import lcm,gcd
from ground_network import View,select
from ground_network_verify import verify_selection
from skill_language import Skill,Vocabulary,normalize,compile_view,PRIMITIVES
from verify_skill_language import verify_skill,verify_pullback

MOTIFS=(
    (('advance',1),('stride',2),('advance',2),('advance',2)),
    (('stride',3),('advance',2),('flip',0),('stride',2),('advance',1)),
    (('advance',2),('stride',3),('advance',1),('flip',0),('stride',3)),
)

def random_view(seed,base=(29,31,37),cutoff=7):
    rng=random.Random(seed);nodes=[];unique={};roots=(0,1)
    for j in reversed(range(len(base))):
        row=tuple(rng.randrange(2) for _ in range(base[j]));new=[]
        for flip in range(2):
            ch=tuple(roots[x^flip] for x in row)
            if len(set(ch))==1:new.append(ch[0]);continue
            v=(j,ch)
            if v not in unique:unique[v]=len(nodes)+2;nodes.append(v)
            new.append(unique[v])
        roots=tuple(new)
    return View('random:'+str(seed),base,tuple(nodes),roots[0],cutoff,rng.getrandbits(cutoff))

def sequential(v,tr):
    work=0
    for p in tr:
        f=normalize((p,));z,w=compile_view(v,f);ok,ww=verify_pullback(v,z,f)
        assert ok;v=z;work+=w+ww
    return v,work

class SkillTests(unittest.TestCase):
    def test_random_exact(self):
        rng=random.Random(751)
        for i in range(300):
            v=random_view(i,(4,9,5),rng.randrange(12));tr=tuple(rng.choice(PRIMITIVES) for _ in range(rng.randrange(1,9)))
            f=normalize(tr);s=Skill(tr,f);self.assertTrue(verify_skill(s));z,_=compile_view(v,f);q,_=sequential(v,tr)
            self.assertTrue(verify_pullback(v,q,f)[0]);self.assertTrue(verify_pullback(v,z,f)[0]);self.assertEqual(z.period,v.period//gcd(v.period,f[0]))
            wide,_=compile_view(v,f,compact=False);self.assertEqual(wide.period,v.period);self.assertTrue(verify_pullback(v,wide,f)[0])
            for t in range(max(q.cutoff,z.cutoff)+v.period):
                x=t;c=0
                for op,n in reversed(tr):
                    if op=='advance':x+=n
                    elif op=='stride':x*=n
                    else:c^=1
                self.assertEqual(z.bit(t),v.bit(x)^c);self.assertEqual(q.bit(t),z.bit(t))
    def test_cross_basis_and_prefix(self):
        a=View('a',(4,),((0,(1,0,1,0)),),2,3,2)
        b=View('b',(2,),((0,(0,1)),),2,1,1)
        # a(t+2) has prefix 0, then odd false/even true: use exact derived view
        q,_=compile_view(a,(1,2,0));target=View('target',(2,),((0,(1,0)),),2,q.cutoff,q.prefix)
        self.assertTrue(verify_pullback(a,target,(1,2,0))[0]);self.assertFalse(verify_pullback(a,b,(1,2,0))[0])
        self.assertFalse(verify_pullback(a,target,(1,2,0),max_work=1)[0])
    def test_forgery_and_restore(self):
        v=Vocabulary();tr=MOTIFS[0];a=random_view(1);b,_=sequential(a,tr)
        self.assertFalse(v.observe(a,tr,View('bad',(),(),0)));self.assertTrue(v.observe(a,tr,b));self.assertTrue(v.observe(a,tr,b));self.assertFalse(v.induce())
        a=random_view(2);b,_=sequential(a,tr);self.assertTrue(v.observe(a,tr,b));self.assertTrue(v.induce());p=v.packet();restored=Vocabulary.restore(json.loads(json.dumps(p)));self.assertEqual(p,restored.packet())
        p['skills'][0][2][0]+=1
        with self.assertRaises(ValueError):Vocabulary.restore(p)
    def test_goal_only(self):
        v=Vocabulary()
        for i in range(12):
            a=random_view(i);tr=MOTIFS[i%3];b,_=sequential(a,tr);self.assertTrue(v.observe(a,tr,b))
        v.induce();a=random_view(123);b,_=sequential(a,MOTIFS[1]);s,stats=v.discover(a,b,depth=1,max_candidates=64)
        self.assertIsNotNone(s);self.assertTrue(verify_skill(s));self.assertTrue(verify_pullback(a,b,s.form)[0])
        self.assertIsNone(v.discover(a,b,depth=1,learned=False)[0]);self.assertIsNone(v.discover(a,b,max_work=1)[0])
    def test_huge_and_rank(self):
        v=View('pulse',(31,37),((1,tuple(int(i==12) for i in range(37))),(0,tuple(2 if i==7 else 0 for i in range(31)))),3,4,5)
        z,_=compile_view(v,(2,9,0));self.assertTrue(verify_pullback(v,z,(2,9,0))[0]);hits=[i for i in range(z.cutoff,z.cutoff+z.period) if v.bit(2*i+9)]
        k=10**900+17;q,r=divmod(k-1-z.prefix.bit_count(),len(hits));out=select(z,k);self.assertEqual(out['time'],q*z.period+hits[r]);self.assertTrue(verify_selection(z,k,out['time']))
    def test_composition_and_expression(self):
        from ground_intelligence import Intelligence,checkpoint
        from verify_ground_intelligence import restore_checkpoint
        from skill_language import SkillIntelligence
        from verify_skill_language import verify_skill_expression
        v=Vocabulary()
        for i in range(12):
            a=random_view(i);tr=MOTIFS[i%3];b,_=sequential(a,tr);self.assertTrue(v.observe(a,tr,b))
        v.induce();old=set(v.skills);v=Vocabulary.restore(v.packet());v.induce();self.assertEqual(set(v.skills),old)
        tr=MOTIFS[1]+MOTIFS[2];form=normalize(tr);self.assertNotIn(form,v.skills)
        for i in range(2):
            a=random_view(9100+i);b,_=sequential(a,tr)
            self.assertIsNone(v.discover(a,b,depth=5,learned=False)[0])
            s,_=v.discover(a,b,depth=1,compose_skills=True);self.assertEqual(s.form,form);self.assertTrue(v.observe(a,s.trace,b))
        v.induce();self.assertIn(form,v.skills);self.assertTrue(old<=set(v.skills))
        agent=Intelligence();a=random_view(9200,(5,7,11),3);A=agent.observe(a,memory=True);s=v.skills[form]
        result=SkillIntelligence(agent,v).express(A,s.key,10**100+17);self.assertIsNotNone(result);packet,_=result
        self.assertTrue(verify_skill_expression(agent.graph,v,A,s.key,10**100+17,packet))
        fresh=restore_checkpoint(checkpoint(agent),expected_views=agent.graph.views);saved=Vocabulary.restore(v.packet())
        self.assertTrue(verify_skill_expression(fresh.graph,saved,A,s.key,10**100+17,packet))
        forged=dict(packet,time=str(int(packet['time'])+1));self.assertFalse(verify_skill_expression(fresh.graph,saved,A,s.key,10**100+17,forged))
        self.assertFalse(verify_skill_expression(fresh.graph,saved,A,s.key,10**100+18,packet))
    def test_wrong_skill_and_boolean(self):
        tr=MOTIFS[0];self.assertFalse(verify_skill(Skill(tr,(2,8,0))));self.assertFalse(verify_skill(Skill((('advance',True),),(1,1,0))))
        with self.assertRaises(ValueError):normalize((('stride',0),))
        a=random_view(3);b,_=compile_view(a,normalize(tr));self.assertFalse(verify_pullback(a,b,(2,9,1))[0])

if __name__=='__main__':unittest.main()
