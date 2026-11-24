"""CIG-025: native decoder, exact images, migration and cross-repo codec."""
import copy
import random
import unittest
from itertools import product
from temporal_ground import compile_transport,Navigator
from verify_temporal_ground import Receiver,verify_transport
from temporal_image import Processor,heights,image_at,capacity,pack,unpack
from verify_temporal_image import Admission,verify_image
from run_temporal_ground import encode_law,law,source,step
from shared_proof import synthesize_shared
from source_section import compile_section

D={'contract':'test','circuit':{'gates':[],'outputs':[]}}


def qualified(k=24,initial=12345):
    n,s,q,fs,_=source(k,True)
    d=synthesize_shared(n,s,q,fs)
    section=compile_section(n,s,q)
    ts,_,_,_,_=law(k,3)
    g=compile_transport(ts,k,3)
    return Navigator(k,3,g,d),Receiver(n,s,q,fs,d,ts,3,g,initial,section=section)


class ImageTests(unittest.TestCase):
    def test_random_full_images(self):
        rng=random.Random(2501)
        for _ in range(80):
            w=rng.randrange(1,4);m=rng.randrange(1,4);k=w*m;a=1<<w
            p=list(range(m));rng.shuffle(p)
            f=[[rng.randrange(a) for _ in range(a)] for j in p]
            ts=encode_law(k,w,p,f);g=compile_transport(ts,k,w)
            self.assertTrue(verify_transport(ts,k,w,g))
            nav=Navigator(k,w,g,D);h=heights(nav)
            actual=set(range(1<<k))
            for t in range(12):
                alph=image_at(h,w,t);count,bits=capacity(alph)
                self.assertEqual(count,len(actual))
                self.assertEqual(bits,(len(actual)-1).bit_length())
                self.assertEqual({unpack(alph,w,i) for i in range(count)},actual)
                for i in range(count):
                    self.assertEqual(pack(alph,w,unpack(alph,w,i)),i)
                actual={step(x,k,w,p,f) for x in actual}

    def test_native_migrations_and_tampering(self):
        nav,receiver=qualified()
        p=Processor(nav,receiver.initial);a=Admission(receiver,p.proof)
        self.assertTrue(verify_image(receiver,p.proof))
        for t in (1,2,5,17,10**1000+173):
            r=p.move(t)
            for field,bad in [('previous_time','999'),('rank',str(1<<nav.k)),
                              ('bits',r['bits']+1),('key','bad'),
                              ('outputs',[True]*len(r['outputs']))]:
                forged=copy.deepcopy(r);forged[field]=bad
                old=(a.time,a.rank)
                self.assertFalse(a.accept(t,forged))
                self.assertEqual((a.time,a.rank),old)
            self.assertTrue(a.accept(t,r))
            self.assertFalse(a.accept(t,r))
            p.commit(r)
            self.assertEqual((a.time,a.rank),(p.time,p.rank))
            self.assertEqual(unpack(p.alphabets(t),nav.w,p.rank),nav.jump(receiver.initial,t))
        bad=copy.deepcopy(p.proof);bad['heights'][0]=(bad['heights'][0]+1)%len(nav.edges)
        self.assertFalse(verify_image(receiver,bad))
        receiver.total_image=False
        self.assertFalse(verify_image(receiver,p.proof))

    def test_constant_and_bijective(self):
        for table,expected in [([0,0],1),([1,0],2)]:
            ts=encode_law(1,1,[0],[table]);g=compile_transport(ts,1,1)
            nav=Navigator(1,1,g,D);h=heights(nav)
            self.assertEqual(capacity(image_at(h,1,10**1000)),(expected,expected-1))
        with self.assertRaises(ValueError):
            pack(((0,),),1,1)
        with self.assertRaises(ValueError):
            unpack(((0,),),1,1)

    def test_cross_repository_codec(self):
        # Required in the pinned cross-repository CI job; ordinary local CIG
        # regression stays dependency-free.
        import os
        if os.environ.get('CIG025_NATIVE_NCR')!='1':
            self.skipTest('native NCR codec checkout not requested')
        from navigable_compute.realized_image import Factor,ImageCertificate
        from navigable_compute.realized_image import pack as ncr_pack,unpack as ncr_unpack
        from ncr_image_codec import NCRCodec
        nav,r=qualified();p=Processor(nav,r.initial,codec=NCRCodec())
        admission=Admission(r,p.proof)
        for t in (0,1,7,10**1000+173):
            alph=p.alphabets(t)
            # Adapter is only a radix layout; CIG height proof, not NCR ANF
            # image admission, establishes the alphabets.
            layout=ImageCertificate(tuple(Factor(tuple(range(j*nav.w,(j+1)*nav.w)),
                                               0,values) for j,values in enumerate(alph)),0)
            code=nav.jump(r.initial,t)
            rank=pack(alph,nav.w,code)
            self.assertEqual(ncr_pack(layout,code),rank)
            self.assertEqual(ncr_unpack(layout,rank),code)
            self.assertEqual(layout.bits,capacity(alph)[1])
            if t:
                receipt=p.move(t)
                self.assertTrue(admission.accept(t,receipt))
                p.commit(receipt)
                self.assertEqual(p.rank,rank)


if __name__=='__main__':
    unittest.main()
