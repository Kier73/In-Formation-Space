"""OFG-002: exhaustive small source oracles, tamper tests, and large symbolic fibers."""
from __future__ import annotations

from copy import deepcopy
from random import Random
import unittest

from separator_fiber_ground import (
    GroundRefusal, SeparatorSource, compile_ground, decode_observation,
    encode_observation, new_coordinates, old_coordinates, shared_switch_source,
    source_accepts, verify_ground,
)


class SeparatorFiberGroundTests(unittest.TestCase):
    def assert_source_oracle(self, source):
        ground = compile_ground(source)
        self.assertTrue(verify_ground(source, ground))
        fibers = {}
        models = 0
        for assignment in range(1 << source.n):
            if source_accepts(source, assignment):
                models += 1
                old = old_coordinates(source, assignment)
                new = new_coordinates(source, assignment)
                fibers.setdefault(old, set()).add(new)
                label, code = encode_observation(source, ground, assignment)
                self.assertEqual(label, old)
                reconstructed = decode_observation(source, ground, label, code)
                self.assertTrue(source_accepts(source, reconstructed))
                self.assertEqual(old_coordinates(source, reconstructed), old)
                self.assertEqual(new_coordinates(source, reconstructed), new)
            else:
                with self.assertRaises(GroundRefusal):
                    encode_observation(source, ground, assignment)
        maximum = max((len(v) for v in fibers.values()), default=0)
        self.assertEqual(ground["models"], models)
        self.assertEqual(ground["maximum_fiber_size"], maximum)
        self.assertEqual(ground["minimum_aux_bits"], (maximum - 1).bit_length() if maximum else 0)
        for old, outputs in fibers.items():
            codes = {encode_observation(source, ground, a)[1]
                     for a in range(1 << source.n)
                     if source_accepts(source, a) and old_coordinates(source, a) == old}
            self.assertEqual(codes, set(range(len(outputs))))
            with self.assertRaises(GroundRefusal):
                decode_observation(source, ground, old, len(outputs))
        if models == 0:
            with self.assertRaises(GroundRefusal):
                decode_observation(source, ground, (0,) * (len(source.bags) + int(source.separator_visible)), 0)
        return ground

    def test_hidden_separator_union_has_more_observables_than_each_branch(self):
        for b in (2, 3, 4, 5):
            with self.subTest(blocks=b):
                visible = shared_switch_source(b, separator_visible=True)
                hidden = shared_switch_source(b, separator_visible=False)
                g1 = self.assert_source_oracle(visible)
                g2 = self.assert_source_oracle(hidden)
                self.assertEqual(g1["models"], 1 << b)
                self.assertEqual(g2["models"], 1 << b)
                self.assertEqual(g1["maximum_fiber_size"], 1 << (b - 1))
                self.assertEqual(g2["maximum_fiber_size"], 3 << (b - 2))
                self.assertEqual(g1["minimum_aux_bits"], b - 1)
                self.assertEqual(g2["minimum_aux_bits"], b)

    def test_large_symbolic_union_avoids_global_enumeration(self):
        b = 256
        for visible, expected_max, expected_bits in (
            (True, 1 << 255, 255), (False, 3 << 254, 256)
        ):
            with self.subTest(visible=visible):
                s = shared_switch_source(b, separator_visible=visible)
                ground = compile_ground(s)
                self.assertTrue(verify_ground(s, ground))
                self.assertEqual(ground["models"], 1 << b)
                self.assertEqual(ground["local_states_checked"], 4 * b)
                self.assertEqual(ground["maximum_fiber_size"], expected_max)
                self.assertEqual(ground["minimum_aux_bits"], expected_bits)
                # Assignment with separator=0, x1=0 and selected other bits.
                a = sum(1 << i for i in range(2, b + 1, 3))
                self.assertTrue(source_accepts(s, a))
                old, code = encode_observation(s, ground, a)
                rebuilt = decode_observation(s, ground, old, code)
                self.assertEqual(new_coordinates(s, rebuilt), new_coordinates(s, a))
                self.assertEqual(old_coordinates(s, rebuilt), old)

    def test_unsat_separator_only_and_bag_obstructions(self):
        for extra in (((1,), (-1,)), ((2,), (-2,))):
            source = shared_switch_source(2, separator_visible=True)
            source = SeparatorSource(source.n, source.separator, source.bags,
                                     source.clauses + extra, source.old_tables,
                                     source.new_tables, source.separator_visible)
            ground = self.assert_source_oracle(source)
            self.assertEqual(ground["status"], "UNSAT")
            self.assertEqual(ground["maximum_fiber_size"], 0)

    def test_source_revision_tampering_and_identity(self):
        s = shared_switch_source(3, separator_visible=False)
        ground = compile_ground(s)
        bad = []
        for key, val in (("models", 1), ("maximum_fiber_size", 7),
                         ("minimum_aux_bits", 0), ("source_sha256", "0" * 64),
                         ("separator_configurations", 1), ("local_states_checked", 0)):
            fake = deepcopy(ground)
            fake[key] = val
            bad.append(fake)
        fake = deepcopy(ground)
        fake["rows"][0]["blocks"][0]["fibers"][0]["representatives"][0] = 1
        bad.append(fake)
        fake = deepcopy(ground)
        fake["rows"][1]["blocks"][0]["models"] += 1
        bad.append(fake)
        fake = deepcopy(ground)
        fake["rows"][0]["allowed"] = 1  # bool-as-int forgery
        bad.append(fake)
        for fake in bad:
            with self.assertRaises(GroundRefusal):
                verify_ground(s, fake)
        revised = SeparatorSource(s.n, s.separator, s.bags, s.clauses + ((-2,),),
                                  s.old_tables, s.new_tables, s.separator_visible)
        with self.assertRaises(GroundRefusal):
            verify_ground(revised, ground)
        with self.assertRaises(GroundRefusal):
            encode_observation(revised, ground, 0)
        with self.assertRaises(GroundRefusal):
            decode_observation(revised, ground, (0, 0, 0), 0)

    def test_cross_bag_nonconstant_hidden_and_budget_refused(self):
        s = shared_switch_source(3, separator_visible=True)
        cross = SeparatorSource(s.n, s.separator, s.bags, s.clauses + ((2, 4),),
                                s.old_tables, s.new_tables, True)
        with self.assertRaisesRegex(GroundRefusal, "crosses"):
            compile_ground(cross)
        hidden = shared_switch_source(3, separator_visible=False)
        old = list(hidden.old_tables)
        old[0] = (0, 1, 0, 1)
        nonconstant = SeparatorSource(hidden.n, hidden.separator, hidden.bags,
                                      hidden.clauses, tuple(old), hidden.new_tables, False)
        with self.assertRaisesRegex(GroundRefusal, "constant"):
            compile_ground(nonconstant)
        for kwargs in ({"max_bag_width": 1}, {"max_local_states": 4},
                       {"max_separator_width": 0}):
            with self.assertRaises(GroundRefusal):
                compile_ground(s, **kwargs)
        with self.assertRaises(GroundRefusal):
            decode_observation(hidden, compile_ground(hidden), (0,) * 3, 7)

    def test_random_exhaustive_global_oracle(self):
        rng = Random(62002)
        for trial in range(100):
            sep_width = rng.randint(1, 2)
            bag_count = rng.randint(1, 3)
            sep = tuple(range(1, sep_width + 1))
            bags = tuple((sep_width + i + 1,) for i in range(bag_count))
            n = sep_width + bag_count
            clauses = []
            for _ in range(rng.randrange(1, 9)):
                bag = rng.choice(bags)
                variables = tuple(rng.sample(sep + bag, rng.randint(1, sep_width + 1)))
                clauses.append(tuple(v if rng.randrange(2) else -v for v in variables))
            # Add separator-only clauses as independent global controls.
            if rng.randrange(3) == 0:
                clauses.append(tuple(v if rng.randrange(2) else -v for v in sep))
            visible = rng.choice((True, False))
            entries = 1 << (sep_width + 1)
            old = tuple(tuple(rng.randrange(3) for _ in range(entries)) if visible
                        else (rng.randrange(3),) * entries for _ in bags)
            new = tuple(tuple(rng.randrange(4) for _ in range(entries)) for _ in bags)
            source = SeparatorSource(n, sep, bags, tuple(clauses), old, new, visible)
            with self.subTest(trial=trial):
                self.assert_source_oracle(source)

    def test_noncontiguous_separator_variables_and_three_bit_separator(self):
        # The separator need not occupy the first bit of the source assignment.
        source = SeparatorSource(4, (2,), ((1,), (3, 4)),
                                 ((2, -1), (-2, 3), (4, -2)),
                                 ((5, 6, 6, 5), (0,) * 8),
                                 ((7, 8, 9, 10), tuple(i % 5 for i in range(8))), True)
        self.assert_source_oracle(source)
        for visible in (True, False):
            sep = (1, 2, 3)
            bags = ((4,), (5,))
            base = tuple(tuple((i ^ (i >> 2)) % 5 for i in range(16)) for _ in bags)
            old = ((0,) * 16,) * 2 if not visible else base
            formula = SeparatorSource(5, sep, bags, ((1, -4), (-3, 5), (2, 3)),
                                      old, base, visible)
            self.assert_source_oracle(formula)

    def test_nontrivial_labels_and_unobserved_separator_sign(self):
        source = shared_switch_source(3, separator_visible=False)
        # Intentionally map the target x labels to nonlinear, noncontiguous codes.
        tables = tuple(tuple((11 if x == 1 else 5) for x in t) for t in source.new_tables)
        changed = SeparatorSource(source.n, source.separator, source.bags,
                                  source.clauses, source.old_tables, tables, False)
        g = self.assert_source_oracle(changed)
        self.assertEqual(g["maximum_fiber_size"], 6)


if __name__ == "__main__":
    unittest.main()
