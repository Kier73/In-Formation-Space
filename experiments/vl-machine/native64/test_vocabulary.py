import unittest,random
from hashlib import sha256
from vocabulary import Vocabulary,Ref,Program,tokenize,discover,qualify,apply,receive,compile_source,decode_program
from byte_ground import Ground
from benchmark_vocabulary import synthetic

class VocabularyTests(unittest.TestCase):
    def test_tokenization_optimal(self):
        r=random.Random(5);v=Vocabulary((b'abcdefgh',b'abcdefghijklmno!',b'ijklmnop'))
        for _ in range(100):
            data=b''.join(r.choice(v.words+(r.randbytes(3),)) for _ in range(5));n=len(data);dp=[0]*(n+1)
            for i in range(n-1,-1,-1):
                dp[i]=min([5+j-i+dp[j] for j in range(i+1,n+1)]+[2+dp[i+len(w)] for w in v.words if data.startswith(w,i)])
            leaves=tokenize(data,v);self.assertEqual(sum(2 if isinstance(g,Ref) else g.size() for g in leaves),dp[0]);self.assertEqual(Program(v,leaves).read(0,n),data)
    def test_learn_and_holdout(self):
        tr=[compile_source(p) for p in synthetic(1,6)];va=[compile_source(p) for p in synthetic(2,4)];v,options=qualify(discover(tr),va);self.assertTrue(v.words);self.assertEqual(Vocabulary.decode(v.encode()),v)
        total=len(v.encode());base=0
        for p in synthetic(3,8):
            b=compile_source(p);w=apply(b,v);base+=len(b.encode());total+=len(w);g=receive(w,v,sha256(p).hexdigest());self.assertEqual(g.read(0,len(p)),p);self.assertEqual(g.total(19,len(p)-8),sum(p[19:-8]))
        self.assertLess(total,base)
    def test_reject(self):
        v=Vocabulary((b'abcdefgh',));g=Program(v,(Ref(0,v.words[0]),Ground('raw',1,(b'Z',))));w=g.encode();d=sha256(b'abcdefghZ').hexdigest()
        self.assertEqual(receive(w,v,d).read(0,9),b'abcdefghZ')
        for bad in (w[:-1],w+b'X',w[:44]+b'\x04\xff'+w[46:],w[:12]+bytes(32)+w[44:]):
            with self.assertRaises(ValueError):decode_program(bad,v)
        with self.assertRaises(ValueError):receive(w,Vocabulary((b'ABCDEFGH',)),d)
        with self.assertRaises(ValueError):receive(w,v,'0'*64)
        for bad in (v.encode()[:-1],v.encode()+b'X',b'VLV1\x02\x08abcdefgh\x08abcdefgh'):
            with self.assertRaises(ValueError):Vocabulary.decode(bad)
    def test_no_admission(self):
        r=random.Random(4);tr=[compile_source(r.randbytes(128)) for _ in range(3)];v,options=qualify(discover(tr),tr);self.assertFalse(v.words)
        p=r.randbytes(512);b=compile_source(p);self.assertEqual(apply(b,v),b.encode())
if __name__=='__main__':unittest.main()
