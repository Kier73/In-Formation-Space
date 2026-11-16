import random
import unittest
from capability_atlas import (
    Affine, ContextualArbiter, cardinality, compile_regions, decode, diagonal, encode,
    point_label, run_audit, swap, translation, upper
)


class AlgebraicCapabilityAtlasTests(unittest.TestCase):
    def test_every_valid_small_field_map_has_unique_address_and_proven_plan(self):
        for p in (3,5):
            ids=set()
            for address in range(cardinality(p)):
                target=decode(p,address)
                self.assertEqual(encode(target),address)
                self.assertEqual(compile_regions(target).realization,target)
                ids.add(target)
            self.assertEqual(len(ids),cardinality(p))

    def test_large_field_arbitrary_intents_and_corner_pivots(self):
        rng=random.Random(29);p=257
        addresses={0,1,2,42,cardinality(p)//2,cardinality(p)-1}
        addresses.update(rng.randrange(cardinality(p)) for _ in range(300))
        for j in addresses:
            target=decode(p,j)
            self.assertEqual(encode(target),j)
            plan=compile_regions(target)
            self.assertEqual(plan.realization,target)
            for v in ((0,0),(1,0),(0,1),(3,5)):
                current=v
                for step in plan.steps:
                    current=step.transform.apply(current)
                self.assertEqual(current,target.apply(v))

    def test_generator_regions_are_individually_incomplete(self):
        p=257
        demand=Affine(p,((2,1),(1,1)),(7,9))
        self.assertNotEqual(demand.mat,translation(p,7,9).mat)
        self.assertNotEqual(demand.mat,diagonal(p,2,1).mat)
        self.assertNotEqual(demand.mat,upper(p,1).mat)
        self.assertEqual(compile_regions(demand).realization,demand)
        # Order matters: operators do not commute, geometric path is meaningful.
        self.assertNotEqual(translation(p,0,1).after(upper(p,3)),
                            upper(p,3).after(translation(p,0,1)))

    def test_time_jump_matches_steps_and_does_not_require_replay(self):
        p=257
        sample=decode(p,0x123456789)
        for t in (0,1,2,9,128,1000):
            state=(2,13)
            for _ in range(t):state=sample.apply(state)
            self.assertEqual(sample.jump(t).apply((2,13)),state)
        far=(1<<63)+73
        self.assertEqual(sample.jump(far).jump(2),sample.jump(far*2))

    def test_changing_hash_labels_cannot_change_geometry(self):
        p=257
        target=decode(p,200123)
        first=point_label('seed-A',encode(target))
        second=point_label('seed-B',encode(target))
        self.assertNotEqual(first,second)
        self.assertEqual(compile_regions(target).realization,target)
        self.assertEqual(target.apply((7,9)),decode(p,encode(target)).apply((7,9)))

    def test_dynamic_context_arbitration_produces_non_affine_function(self):
        p=257
        even=Affine(p,((2,1),(0,3)),(5,7))
        odd=Affine(p,((1,2),(1,1)),(7,9))
        a=ContextualArbiter(even,odd)
        for x in range(8):
            for y in range(8):
                expected=(odd if x%2 else even).apply((x,y))
                self.assertEqual(a.realize((x,y)),expected)
        audit=run_audit()
        self.assertTrue(audit['contextual_behaviour_not_single_affine'])
        self.assertNotEqual(audit['arbiter_parallelogram_violation'],[0,0])

    def test_invalid_coordinates_and_noninvertible_intents_refuse(self):
        for value in (-1,cardinality(257),1.0):
            with self.assertRaises(ValueError):decode(257,value)
        with self.assertRaises(ValueError):Affine(257,((0,0),(0,0)),(0,0))
        with self.assertRaises(ValueError):decode(257,True)


if __name__=='__main__':unittest.main()