import unittest

from distinction_space import DistinctionSpace


class DistinctionRefinementTests(unittest.TestCase):
    def test_independent_binary_distinction_refines_every_existing_block(self):
        states = [(x, y) for x in range(2) for y in range(2)]
        space = DistinctionSpace(states)

        first = space.add_distinction("x", lambda state: state[0])
        second = space.add_distinction("y", lambda state: state[1])

        self.assertEqual(first.previous_block_count, 1)
        self.assertEqual(first.refined_block_count, 2)
        self.assertEqual(first.split_pair_count, 4)
        self.assertEqual(second.previous_block_count, 2)
        self.assertEqual(second.refined_block_count, 4)
        self.assertEqual(second.split_pair_count, 2)
        self.assertAlmostEqual(second.conditional_entropy_bits, 1.0)
        self.assertAlmostEqual(space.conditional_entropy_bits("y"), 1.0)
        self.assertFalse(second.redundant)

    def test_derived_distinction_is_redundant(self):
        states = list(range(8))
        space = DistinctionSpace(states)
        space.add_distinction("parity", lambda value: value % 2)
        result = space.add_distinction("same_parity_again", lambda value: (value * 3) % 2)

        self.assertTrue(result.redundant)
        self.assertEqual(result.split_pair_count, 0)
        self.assertEqual(result.previous_block_count, result.refined_block_count)
        self.assertEqual(result.conditional_entropy_bits, 0.0)
        self.assertEqual(space.conditional_entropy_bits("same_parity_again"), 0.0)

    def test_partial_refinement_counts_only_pairs_that_are_newly_separated(self):
        states = ("a", "b", "c", "d")
        space = DistinctionSpace(states)
        space.add_distinction("coarse", lambda state: state in ("a", "b"))
        result = space.add_distinction(
            "refine_one_block",
            lambda state: state == "a",
        )

        self.assertEqual(result.previous_block_count, 2)
        self.assertEqual(result.refined_block_count, 3)
        self.assertEqual(result.split_pair_count, 1)
        self.assertFalse(result.redundant)

    def test_conditional_entropy_uses_supplied_state_weights(self):
        weights = {"a": 1.0, "b": 1.0, "c": 3.0, "d": 1.0}
        space = DistinctionSpace(("a", "b", "c", "d"), weights=weights)
        space.add_distinction("coarse", lambda state: state in ("a", "b"))
        result = space.add_distinction(
            "split_first_block",
            lambda state: state == "a",
        )
        self.assertAlmostEqual(result.conditional_entropy_bits, 1.0 / 3.0)

    def test_partition_refinement_never_merges_previous_blocks(self):
        states = list(range(16))
        space = DistinctionSpace(states)
        results = []
        results.append(space.add_distinction("mod2", lambda x: x % 2))
        results.append(space.add_distinction("mod4", lambda x: x % 4))
        results.append(space.add_distinction("mod8", lambda x: x % 8))
        for previous, current in zip(results, results[1:]):
            self.assertGreaterEqual(current.refined_block_count, previous.refined_block_count)

    def test_signatures_and_partitions_are_stable(self):
        space = DistinctionSpace(("north", "south", "east", "west"))
        space.add_distinction("hemisphere", lambda state: state in ("north", "south"))
        signatures = space.signatures()
        partition = space.partition()
        self.assertEqual(signatures["north"], signatures["south"])
        self.assertEqual(signatures["east"], signatures["west"])
        self.assertEqual(partition, (("north", "south"), ("east", "west")))

    def test_bad_states_weights_and_observations_are_rejected(self):
        with self.assertRaises(ValueError):
            DistinctionSpace(())
        with self.assertRaises(ValueError):
            DistinctionSpace(("a", "a"))
        with self.assertRaises(ValueError):
            DistinctionSpace(("a", "b"), weights={"a": 1.0})
        with self.assertRaises(ValueError):
            DistinctionSpace(("a", "b"), weights={"a": 1.0, "b": 0.0})

        space = DistinctionSpace(("a", "b"))
        with self.assertRaises(TypeError):
            space.add_distinction("unhashable", lambda state: [])
        self.assertEqual(space.distinction_names, ())
        with self.assertRaises(ValueError):
            space.add_distinction(" ", lambda state: 0)
        with self.assertRaises(ValueError):
            space.add_distinction("   ", lambda state: 0)

    def test_duplicate_names_and_non_callable_observations_are_rejected(self):
        space = DistinctionSpace((0, 1))
        space.add_distinction("bit", lambda value: value)
        with self.assertRaises(ValueError):
            space.add_distinction("bit", lambda value: value % 2)
        with self.assertRaises(TypeError):
            space.add_distinction("not_callable", 123)


if __name__ == "__main__":
    unittest.main()
