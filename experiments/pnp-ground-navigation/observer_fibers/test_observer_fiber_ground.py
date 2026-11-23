"""OFG-001 source-bound observer and adversarial certificate tests."""
import copy
import unittest
from random import Random

from observer_fiber_ground import (GroundRefusal, Source, compile_ground, verify_ground,
    encode_observation, decode_observation, source_accepts, new_coordinates,
    old_coordinates, disjoint_three_state_source)


class ObserverFiberGroundTests(unittest.TestCase):
    def test_minimality_and_replay_for_every_valid_small_assignment(self):
        for mode, expected in (("constant", 5), ("parity", 3), ("identity", 0)):
            with self.subTest(mode=mode):
                source = disjoint_three_state_source(3, old_mode=mode)
                ground = compile_ground(source)
                self.assertTrue(verify_ground(source, ground))
                self.assertEqual(ground["models"], 27)
                self.assertEqual(ground["minimum_aux_bits"], expected)
                for a in range(1 << source.n):
                    if source_accepts(source, a):
                        old, code = encode_observation(source, ground, a)
                        decoded = decode_observation(source, ground, old, code)
                        self.assertTrue(source_accepts(source, decoded))
                        self.assertEqual(old_coordinates(source, a), old_coordinates(source, decoded))
                        self.assertEqual(new_coordinates(source, a), new_coordinates(source, decoded))
                    else:
                        with self.assertRaises(GroundRefusal):
                            encode_observation(source, ground, a)

    def test_exponential_possible_models_with_linear_ground(self):
        blocks = 64
        source = disjoint_three_state_source(blocks)
        ground = compile_ground(source)
        self.assertTrue(verify_ground(source, ground))
        self.assertEqual(ground["models"], 3 ** blocks)
        self.assertEqual(ground["minimum_aux_bits"], (3 ** blocks - 1).bit_length())
        self.assertEqual(ground["local_states_checked"], 4 * blocks)
        x = sum(1 << (2 * i) for i in range(blocks))
        old, code = encode_observation(source, ground, x)
        self.assertEqual(decode_observation(source, ground, old, code), x)
        self.assertEqual(compile_ground(disjoint_three_state_source(blocks, old_mode="parity"))["minimum_aux_bits"], 64)
        self.assertEqual(compile_ground(disjoint_three_state_source(blocks, old_mode="identity"))["minimum_aux_bits"], 0)

    def test_incomplete_observation_and_cross_block_are_refused(self):
        source = disjoint_three_state_source(2)
        cross = Source(source.n, source.clauses + ((1, 3),), source.scopes,
                       source.old_tables, source.new_tables)
        with self.assertRaisesRegex(GroundRefusal, "cross-block"):
            compile_ground(cross)
        with self.assertRaises(GroundRefusal):
            compile_ground(source, max_width=1)
        missing = Source(source.n, source.clauses, source.scopes,
                         source.old_tables[:1], source.new_tables)
        with self.assertRaises(GroundRefusal):
            compile_ground(missing)

    def test_unsat_is_proved_locally_and_no_witness_is_emitted(self):
        source = disjoint_three_state_source(2)
        # Both polarities for each literal: no assignment survives the first block.
        first = ((1, 2), (1, -2), (-1, 2), (-1, -2))
        source = Source(source.n, source.clauses + first, source.scopes,
                        source.old_tables, source.new_tables)
        ground = compile_ground(source)
        self.assertTrue(verify_ground(source, ground))
        self.assertEqual((ground["status"], ground["models"], ground["maximum_fiber_size"]), ("UNSAT", 0, 0))
        with self.assertRaises(GroundRefusal):
            decode_observation(source, ground, (0, 0), 0)

    def test_adversarial_mutations(self):
        source = disjoint_three_state_source(4)
        ground = compile_ground(source)
        mutations = []
        for key, value in (("models", 1), ("minimum_aux_bits", 0),
                           ("maximum_fiber_size", 1), ("source_sha256", "0" * 64),
                           ("local_states_checked", 0)):
            f = copy.deepcopy(ground)
            f[key] = value
            mutations.append(f)
        f = copy.deepcopy(ground)
        f["blocks"][0]["fibers"][0]["representatives"][0] = 3
        mutations.append(f)
        f = copy.deepcopy(ground)
        f["blocks"][0]["fibers"][0]["new"].remove(1)
        mutations.append(f)
        for m in mutations:
            with self.subTest(mutation=m):
                with self.assertRaises(GroundRefusal):
                    verify_ground(source, m)

    def test_random_bounded_cnf_and_nonlinear_observer_fibers(self):
        rng = Random(61001)
        for case in range(120):
            block_count = rng.randrange(1, 4)
            scopes = tuple((2 * i + 1, 2 * i + 2) for i in range(block_count))
            clauses = []
            for a, b in scopes:
                for _ in range(rng.randrange(0, 5)):
                    clauses.append(tuple(rng.choice((-v, v)) for v in (a, b)))
            old = tuple(tuple(rng.randrange(0, 3) for _ in range(4)) for _ in scopes)
            new = tuple(tuple(rng.randrange(0, 4) for _ in range(4)) for _ in scopes)
            source = Source(2 * block_count, tuple(clauses), scopes, old, new)
            ground = compile_ground(source)
            self.assertTrue(verify_ground(source, ground))
            independent_fibers = {}
            solutions = 0
            for assignment in range(1 << source.n):
                if not source_accepts(source, assignment):
                    continue
                solutions += 1
                key = old_coordinates(source, assignment)
                independent_fibers.setdefault(key, set()).add(new_coordinates(source, assignment))
                o, code = encode_observation(source, ground, assignment)
                rebuilt = decode_observation(source, ground, o, code)
                self.assertEqual(new_coordinates(source, rebuilt), new_coordinates(source, assignment))
            max_fiber = max((len(v) for v in independent_fibers.values()), default=0)
            with self.subTest(case=case):
                self.assertEqual(ground["models"], solutions)
                self.assertEqual(ground["maximum_fiber_size"], max_fiber)
                self.assertEqual(ground["minimum_aux_bits"], (max_fiber - 1).bit_length() if max_fiber else 0)

    def test_out_of_fiber_code_and_source_revision_refused(self):
        source = disjoint_three_state_source(1)
        ground = compile_ground(source)
        with self.assertRaises(GroundRefusal):
            decode_observation(source, ground, (0,), 3)
        revised = Source(source.n, source.clauses + ((1,),), source.scopes,
                         source.old_tables, source.new_tables)
        with self.assertRaises(GroundRefusal):
            decode_observation(revised, ground, (0,), 1)
        with self.assertRaises(GroundRefusal):
            verify_ground(revised, ground)


if __name__ == "__main__":
    unittest.main()
