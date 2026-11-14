"""GCI-003 adversarial bounded contract tests independent of hosted runtimes."""
from __future__ import annotations

import copy
import unittest

import intention_model as m


def fixture(state: int):
    # Fixture uses a synthetic binding; real hosts bind all fields to the
    # independently verified GCI-002 source/certificate report.
    binding = {
        "source_digest": "a"*64,
        "ground_fingerprint": "b"*64,
        "orbit_certificate_fingerprint": "c"*64,
        "gci002_report_digest": "d"*64,
    }
    orbit = [m.cag.state_at(t) % 8 for t in range(8)]
    tick = orbit.index(state)
    public, private = m.make_context(binding, tick, state, "e"*64)
    planned = m.plan(public, binding)
    measurements = m.measure(public, private, planned, binding)
    resolved = m.resolve(public, planned, measurements, binding)
    return binding, public, private, planned, measurements, resolved


def reseal(record):
    record["report_digest"] = m.cag.digest(
        {key:value for key,value in record.items() if key != "report_digest"})


class GCI003Tests(unittest.TestCase):
    def test_all_eight_possible_hidden_states_are_realized(self):
        for state in range(8):
            with self.subTest(state=state):
                binding, public, private, planned, measurements, resolved = fixture(state)
                self.assertEqual(public["observer"]["value"], int(state >= 4))
                self.assertEqual([row["status"] for row in planned["cases"]],
                                 ["READY", "MEASURE", "MEASURE", "REFUSE"])
                self.assertEqual([row["selected"] for row in planned["cases"]],
                                 [[], ["parity"], ["low2"], []])
                self.assertEqual([row["symbolic_cost"] for row in planned["cases"]],
                                 [0, 1, 2, 0])
                self.assertEqual([row["status"] for row in resolved["results"]],
                                 ["RESOLVED_WITHOUT_QUERY", "RESOLVED_AFTER_QUERY",
                                  "RESOLVED_AFTER_QUERY", "REFUSED_INSUFFICIENT_CONTEXT"])
                for task, got in zip(m.TASKS, resolved["results"]):
                    if got["status"] == "REFUSED_INSUFFICIENT_CONTEXT":
                        self.assertIsNone(got["result"])
                    else:
                        self.assertEqual(got["result"], m.intention_value(task, state))

    def test_large_time_navigation_is_affine_not_iteration(self):
        for state in range(8):
            self.assertEqual(m.jump_mod8(state, m.HUGE_MULTIPLE_EIGHT), state)
            self.assertEqual(m.jump_mod8(state, m.HUGE_ODD), (5*state+1) % 8)
        for bad in (True, -1, 10**19):
            with self.assertRaises(m.SufficiencyRefused):
                m.jump_mod8(7, bad)

    def test_global_insufficiency_witness_is_real_and_reachable(self):
        for state in (0, 7):
            _, public, _, planned, _, _ = fixture(state)
            last = planned["cases"][-1]
            a, b = last["counterexample"]["a"], last["counterexample"]["b"]
            self.assertNotEqual(a, b)
            self.assertEqual(m.threshold(a), m.threshold(b))
            self.assertEqual(m.feature("parity", a), m.feature("parity", b))
            self.assertNotEqual(
                m.intention_value(m.TASKS[-1], a),
                m.intention_value(m.TASKS[-1], b),
            )

    def test_private_state_tamper_even_with_rehash_is_rejected(self):
        binding, public, private, *_ = fixture(6)
        private["state"] = 5
        reseal(private)
        with self.assertRaises(m.SufficiencyRefused):
            m.validate_private(private, public, binding)

    def test_private_tick_tamper_even_with_rehash_is_rejected(self):
        binding, public, private, *_ = fixture(6)
        private["tick"] = (private["tick"]+1) % 8
        reseal(private)
        with self.assertRaises(m.SufficiencyRefused):
            m.validate_private(private, public, binding)

    def test_public_value_tamper_even_with_rehash_refused(self):
        binding, public, private, planned, _, _ = fixture(6)
        public["observer"]["value"] ^= 1
        reseal(public)
        with self.assertRaises(m.SufficiencyRefused):
            m.validate_private(private, public, binding)
        with self.assertRaises(m.SufficiencyRefused):
            m.validate_plan(planned, public, binding)

    def test_unnecessary_query_is_not_minimum(self):
        binding, public, private, planned, *_ = fixture(6)
        planned["cases"][0]["status"] = "MEASURE"
        planned["cases"][0]["selected"] = ["parity"]
        reseal(planned)
        with self.assertRaises(m.SufficiencyRefused):
            m.measure(public, private, planned, binding)

    def test_forged_ready_result_is_refused(self):
        binding, public, private, planned, *_ = fixture(6)
        planned["cases"][1]["status"] = "READY"
        planned["cases"][1]["selected"] = []
        planned["cases"][1]["result"] = 0
        reseal(planned)
        with self.assertRaises(m.SufficiencyRefused):
            m.validate_plan(planned, public, binding)

    def test_forbidden_measurement_cannot_be_added(self):
        binding, public, private, planned, measured, _ = fixture(6)
        measured["entries"][-1]["readings"].append({"name":"low2","value":2})
        reseal(measured)
        with self.assertRaises(m.SufficiencyRefused):
            m.resolve(public, planned, measured, binding)

    def test_measured_feature_value_forgery_disagrees_with_held_phase(self):
        binding, public, private, planned, measured, _ = fixture(6)
        measured["entries"][1]["readings"][0]["value"] ^= 1
        reseal(measured)
        # This remains mathematically *plausible* for an unknown phase;
        # the blind resolver cannot detect an authorized host lying. The
        # later independent witness auditor must compare it to private state.
        plausible = m.resolve(public, planned, measured, binding)
        self.assertNotEqual(plausible["results"][1]["result"],
                            m.intention_value(m.TASKS[1], private["state"]))
        self.assertNotEqual(measured, m.measure(public, private, planned, binding))

    def test_unexpected_feature_name_fails_closed(self):
        binding, public, private, planned, measured, _ = fixture(6)
        measured["entries"][1]["readings"][0] = {"name":"full-state","value":6}
        reseal(measured)
        with self.assertRaises(m.SufficiencyRefused):
            m.resolve(public, planned, measured, binding)

    def test_old_source_or_ground_binding_refused(self):
        binding, public, private, planned, *_ = fixture(6)
        changed = dict(binding)
        changed["ground_fingerprint"] = "f"*64
        with self.assertRaises(m.SufficiencyRefused):
            m.validate_public(public, changed)
        with self.assertRaises(m.SufficiencyRefused):
            m.validate_plan(planned, public, changed)

    def test_boolean_feature_response_refused(self):
        binding, public, private, planned, measured, _ = fixture(6)
        measured["entries"][1]["readings"][0]["value"] = False
        reseal(measured)
        with self.assertRaises(m.SufficiencyRefused):
            m.resolve(public, planned, measured, binding)

    def test_missing_feature_measurement_refused(self):
        binding, public, private, planned, measured, _ = fixture(6)
        measured["entries"][2]["readings"] = []
        reseal(measured)
        with self.assertRaises(m.SufficiencyRefused):
            m.resolve(public, planned, measured, binding)

    def test_noncongruent_threshold_still_allows_periodic_target(self):
        for state in range(8):
            binding, public, *_ = fixture(state)
            ready = m.choose_task(m.TASKS[0], public)
            self.assertEqual(ready["status"], "READY")
            self.assertEqual(ready["result"], int(state >= 4))
        # Intention-relative sufficiency is different from transition congruence:
        # threshold is not one-step congruent, yet horizon 8k is sufficient.


if __name__ == "__main__":
    unittest.main()
