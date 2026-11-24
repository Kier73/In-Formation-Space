import copy,json,random,unittest
from run_output_time import circuit_source,expr_eval,fixture,oracle_time
from run_temporal_ground import encode_law,step
from temporal_ground import compile_transport,Navigator
from shared_proof import synthesize_shared
from source_section import compile_section,section_witness
from verify_temporal_ground import Receiver
from output_time import seek_outputs
from verify_output_time import verify_output_seek
from inverse_time import spatial_groups


def prepare(k,w,p,f,initial,exprs):
    n,s,q,fs=circuit_source(k,exprs);d=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q)
    ts=encode_law(k,w,p,f);g=compile_transport(ts,k,w)
    return Navigator(k,w,g,d),Receiver(n,s,q,fs,d,ts,w,g,initial,section=sec)


class OutputTimeTests(unittest.TestCase):
    def test_random_exhaustive(self):
        rng=random.Random(22022)
        for j in range(30):
            k=rng.randrange(2,8);w=1
            # Two different nonlinear outputs; leaves may be shared.
            exprs=[(rng.choice(('and','or','xor')),0,1),('xor',('and',0,k-1),1)]
            p=list(range(k));rng.shuffle(p);f=[[rng.randrange(2) for _ in range(2)] for _ in p];initial=rng.getrandbits(k)
            nav,rec=prepare(k,w,p,f,initial,exprs)
            for _ in range(10):
                targets=[rng.choice((0,1,None)) for e in exprs];start=rng.randrange(30);c=initial
                for t in range(start):c=step(c,k,w,p,f)
                t=start;seen=set();expect=None
                while c not in seen:
                    if all(b is None or b==expr_eval(e,c) for e,b in zip(exprs,targets)):expect=t;break
                    seen.add(c);c=step(c,k,w,p,f);t+=1
                for grouped in (True,False):
                    r=seek_outputs(nav,initial,targets,start,grouped=grouped)
                    self.assertTrue(verify_output_seek(rec,targets,start,r,grouped=grouped))
                    self.assertEqual(int(r['time']) if r['status']=='FOUND' else None,expect)
    def test_transient(self):
        nav,rec=prepare(2,1,[0,1],[[0,0],[0,1]],3,[('and',0,1)])
        r=seek_outputs(nav,3,[1]);self.assertEqual(r['method'],'transient');self.assertTrue(verify_output_seek(rec,[1],0,r))
        r=seek_outputs(nav,3,[1],1);self.assertEqual(r['status'],'UNREACHABLE');self.assertTrue(verify_output_seek(rec,[1],1,r))
    def test_dontcare(self):
        nav,rec=prepare(2,1,[1,0],[[0,1],[0,1]],1,[('xor',0,1)])
        t=10**1000+7;r=seek_outputs(nav,1,[None],t);self.assertEqual(int(r['time']),t);self.assertTrue(verify_output_seek(rec,[None],t,r))
    def test_large_coupling(self):
        n,s,q,fs,ts,g,p,f,initial,P,start,exprs,markers,desired=fixture(1023);d=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q);nav=Navigator(len(q),3,g,d);rec=Receiver(n,s,q,fs,d,ts,3,g,initial,section=sec)
        targets=[1]*(len(fs)-1)+[None];r=seek_outputs(nav,initial,targets,start);t,classes=oracle_time([len(z) for z in spatial_groups(p)],desired,start)
        self.assertEqual(int(r['time']),t);self.assertEqual(len(r['residues']),classes);self.assertTrue(verify_output_seek(rec,targets,start,r));self.assertTrue(all(len(f['groups'])==2 for f in r['factors']))
        u=seek_outputs(nav,initial,targets,start,grouped=False);self.assertEqual(r['residues'],u['residues']);self.assertGreater(u['pairs'],r['pairs']);self.assertTrue(verify_output_seek(rec,targets,start,u,grouped=False))
    def test_forged_receipts(self):
        nav,rec=prepare(2,1,[1,0],[[0,1],[0,1]],1,[('or',0,1),('and',0,1)])
        target=[1,0];r=seek_outputs(nav,1,target,2);self.assertTrue(verify_output_seek(rec,target,2,r))
        for key,value in [('key','wrong'),('time','4'),('targets',[0,0]),('pairs',True),('status','UNREACHABLE'),('grouped',False),('modulus','17'),('residues',[])]:
            bad=copy.deepcopy(r);bad[key]=value;self.assertFalse(verify_output_seek(rec,target,2,bad),key)
        for field,change in [('roots',[]),('groups',[]),('period',3),('residues',[])]:
            bad=copy.deepcopy(r);bad['factors'][0][field]=change;self.assertFalse(verify_output_seek(rec,target,2,bad),field)
        bad=copy.deepcopy(r);bad['terminal']['outputs'][0]=0;self.assertFalse(verify_output_seek(rec,target,2,bad))
        self.assertFalse(verify_output_seek(rec,[0,0],2,r));self.assertFalse(verify_output_seek(rec,target,3,r))
        self.assertTrue(verify_output_seek(rec,target,2,json.loads(json.dumps(r))))
    def test_budgets(self):
        nav,rec=prepare(3,1,[2,0,1],[[0,1]]*3,1,[('or',0,1)])
        for budget in [dict(max_cells=1),dict(max_pairs=1)]:
            r=seek_outputs(nav,1,[1],**budget);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(verify_output_seek(rec,[1],0,r,**budget))
    def test_requires_total_image(self):
        k=2;n,s,q,fs=circuit_source(k,[('and',0,1)]);d=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q);ts=encode_law(k,1,[1,0],[[0,1]]*2);g=compile_transport(ts,k,1);nav=Navigator(k,1,g,d);r=seek_outputs(nav,3,[1]);rec=Receiver(n,s,q,fs,d,ts,1,g,3,section_witness(n,q,sec,3));self.assertFalse(verify_output_seek(rec,[1],0,r))
    def test_invalid_contract(self):
        nav,rec=prepare(2,1,[1,0],[[0,1]]*2,1,[('and',0,1)])
        for targets in [[],[True],[2],(1,)]:self.assertRaises(ValueError,seek_outputs,nav,1,targets)
        self.assertRaises(ValueError,seek_outputs,nav,1,[1],-1)
    def test_repeated_cycle_overlap(self):
        nav,rec=prepare(3,1,[2,0,1],[[0,1]]*3,1,[('xor',0,1),('or',1,2)])
        for target in [[1,1],[1,0],[0,1],[0,0]]:
            r=seek_outputs(nav,1,target);self.assertTrue(verify_output_seek(rec,target,0,r))
            possible=[i for i in range(3) if all(expr_eval(e,nav.jump(1,i))==b for e,b in zip([('xor',0,1),('or',1,2)],target))];self.assertEqual(int(r['time']) if r['status']=='FOUND' else None,min(possible) if possible else None)

if __name__=='__main__':unittest.main()
