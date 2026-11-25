import unittest
from pathlib import Path
from hashlib import sha256
from struct import pack_into
from byte_ground import Source
from compose_ground import compose, restore
from typed_ground import elf_boundaries, typed_compose

class Typed(unittest.TestCase):
    def test_actual(self):
        p=Path(__file__).with_name('vlm64.elf').read_bytes();s=Source(p)
        g,c=typed_compose(s);base,_=compose(Source(p))
        self.assertTrue(c['boundaries']);self.assertLessEqual(len(g.encode()),len(base.encode()))
        self.assertEqual(restore(g.encode(),sha256(p).hexdigest()).read(0,len(p)),p)
        self.assertEqual(s.reads,len(p)+c['sensor_bytes'])
    def test_invalid(self):
        p=bytearray(Path(__file__).with_name('vlm64.elf').read_bytes())
        self.assertEqual(p[4],1)
        pack_into('<I',p,32,len(p)+1)
        for raw in (bytes(p),b'\x7fELF',b'not ELF',bytes(64)):
            s=Source(raw);self.assertEqual(elf_boundaries(s),())
            g,c=typed_compose(Source(raw));self.assertEqual(g.read(0,len(raw)),raw);self.assertEqual(c['selected'],'midpoint')
if __name__=='__main__':unittest.main()
