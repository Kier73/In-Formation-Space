import unittest
from adaptive_experience import campaign,load_parent,generate,hypotheses,oracle
from experience import decode, digest
from test_application import execute

class AdaptiveExperience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=campaign()
    def test_refine(self):
        r=self.r;self.assertTrue(r['admitted']);self.assertEqual(r['old_final_coverage'],32);self.assertEqual(r['new_final_coverage'],64);self.assertGreater(r['new_parameters'],r['old_parameters']);self.assertLess(r['validation_cost_new'],r['validation_cost_old']);self.assertEqual(r['experience_digest'],digest(r['rows']))
    def test_recipe(self):
        t=load_parent()[self.r['parent_shape']];p,q=generate(t,'probe',0,(hypotheses(t)[0],));self.assertIsNotNone(t.match(p));self.assertIsNone(t.match(q));self.assertEqual(execute(decode(q))[:2],(True,oracle(q)))
        with self.assertRaises(ValueError):generate(t,'probe',0,(0,))
    def test_deterministic(self):self.assertEqual(campaign(),self.r)
if __name__=='__main__':unittest.main()
