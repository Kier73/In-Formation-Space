import unittest

from run_tradeoff_v2 import (
    A_PARAM,
    B_PARAM,
    M_CHECK,
    M_PRIMARY,
    fault_injection_result,
    guard_accepts,
    inject_intermediate_bitflip,
    quotient_aware_guard_residue,
    raw_execution,
    shortcut_orbit,
)


class QuotientAwareGuardTests(unittest.TestCase):
    def test_guard_matches_primary_projection(self):
        for steps in (0, 1, 2, 10, 50, 100, 1_000, 10_000, 500_000):
            with self.subTest(steps=steps):
                primary = shortcut_orbit(42, steps, A_PARAM, B_PARAM, M_PRIMARY)
                guard = quotient_aware_guard_residue(
                    42, steps, A_PARAM, B_PARAM, M_PRIMARY, M_CHECK
                )
                self.assertEqual(primary % M_CHECK, guard)

    def test_old_independent_check_modulus_is_not_a_projection(self):
        steps = 10
        primary = shortcut_orbit(42, steps, A_PARAM, B_PARAM, M_PRIMARY)
        invalid_independent_orbit = shortcut_orbit(
            42, steps, A_PARAM, B_PARAM, M_CHECK
        )
        self.assertNotEqual(primary % M_CHECK, invalid_independent_orbit)

    def test_shortcut_matches_raw_execution(self):
        for steps in (0, 1, 2, 10, 50, 500, 1_000):
            with self.subTest(steps=steps):
                raw = raw_execution(42, steps, A_PARAM, B_PARAM, M_PRIMARY)
                shortcut = shortcut_orbit(42, steps, A_PARAM, B_PARAM, M_PRIMARY)
                self.assertEqual(raw, shortcut)

    def test_fault_detection_has_a_clean_nominal_baseline(self):
        result = fault_injection_result()
        self.assertTrue(result["nominal_guard_accepts"])
        self.assertFalse(result["faulty_guard_accepts"])
        self.assertTrue(result["fault_detected"])

    def test_bitflip_fixture_is_not_nominal_state(self):
        nominal = shortcut_orbit(42, 10_000, A_PARAM, B_PARAM, M_PRIMARY)
        faulty = inject_intermediate_bitflip(42, 10_000, 5_000)
        self.assertNotEqual(nominal, faulty)

    def test_residue_guard_documents_its_collision_limit(self):
        self.assertTrue(guard_accepts(123, 123 % M_CHECK))
        self.assertTrue(guard_accepts(123 + M_CHECK, 123 % M_CHECK))


if __name__ == "__main__":
    unittest.main()
