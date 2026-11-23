"""OFC-002: execute a guaranteed intention across multiple unknown static laws.

The actual original IWI-002 law-state product is formed by uncertain_ground.js.
Every model identity persists as a separate source-world component. The policy
does not receive which one is true; native E-CPU runs one hidden world.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from bridge import ConstructionRefused, _verified_models, run_intention, source_fixture


def rehash(packet):
    packet["source_digest"] = sha256(json.dumps(
        {"model": packet["model"], "certificate": packet["certificate"]},
        separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf8")).hexdigest()
    return packet


class MultiLawNativeRealization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {name: source_fixture(name) for name in (
            "safe_diagnosis", "silent_conflict", "silent_common_funnel",
        )}

    def test_multi_law_components_never_switch_world_under_any_action(self):
        for name, block in (("safe_diagnosis", 3), ("silent_conflict", 3),
                            ("silent_common_funnel", 2)):
            with self.subTest(case=name):
                m = self.cases[name]["model"]
                self.assertEqual(m["n"], block*2)
                for a in m["next"]:
                    for state in range(m["n"]):
                        expected_start = 0 if state < block else block
                        self.assertTrue(expected_start <= a[state] < expected_start+block)
                self.assertEqual(m["start"].bit_count(), 2)
                self.assertEqual(m["goal"].bit_count(), 2)

    def test_safe_observation_selects_action_before_dangerous_intervention(self):
        """Original IWI-002 law-identifying diagnostic is actually executed."""
        packet = self.cases["safe_diagnosis"]
        left = run_intention(packet, expected_source_digest=packet["source_digest"],
                             original_state=1, failover_after=1)
        right = run_intention(packet, expected_source_digest=packet["source_digest"],
                              original_state=4, failover_after=1)
        for report in (left, right):
            self.assertEqual(report["status"], "GOAL_REALIZED_WITHOUT_INITIAL_IDENTIFICATION")
            self.assertEqual(report["initial_belief_count"], 2)
            self.assertEqual(report["native_executions"], 2)
            self.assertEqual(report["final_belief_count"], 1)
            self.assertIn("worker.alpha", report["steps"][0]["execution"]["path"])
            self.assertIn("worker.beta", report["steps"][1]["execution"]["path"])
            self.assertEqual(len({s["execution"]["machine"] for s in report["steps"]}),1)
            self.assertEqual(report["ecpu_machine"], left["ecpu_machine"])
        self.assertEqual(left["steps"][0]["action"], 2)
        self.assertEqual(right["steps"][0]["action"], 2)
        self.assertNotEqual(left["steps"][0]["observed_visible"],
                            right["steps"][0]["observed_visible"])
        self.assertEqual(left["steps"][1]["action"], 0)
        self.assertEqual(right["steps"][1]["action"], 1)

    def test_common_policy_succeeds_without_identifying_which_law_is_true(self):
        """Both possible original laws remain live in the final successful belief."""
        packet = self.cases["silent_common_funnel"]
        reports = [run_intention(packet, expected_source_digest=packet["source_digest"],
                                 original_state=s) for s in (1, 3)]
        for report in reports:
            self.assertEqual(report["status"], "GOAL_REALIZED_WITHOUT_INITIAL_IDENTIFICATION")
            self.assertEqual(report["initial_belief_count"], 2)
            self.assertEqual(report["native_executions"], 1)
            self.assertEqual(report["final_belief_count"], 2)
            self.assertEqual(report["final_belief_mask"], 0b0101)
            self.assertEqual([s["action"] for s in report["steps"]], [0])
        self.assertEqual(reports[0]["ecpu_machine"], reports[1]["ecpu_machine"])
        self.assertEqual(reports[0]["steps"][0]["observed_visible"],
                         reports[1]["steps"][0]["observed_visible"])

    def test_each_separately_solvable_law_can_be_jointly_impossible(self):
        packet = self.cases["silent_conflict"]
        for original_state in (1, 4):
            report = run_intention(
                packet, expected_source_digest=packet["source_digest"],
                original_state=original_state,
            )
            self.assertEqual(report["status"], "UNREALIZABLE_FOR_ALL_DECLARED_INITIAL_STATES")
            self.assertEqual(report["observations"], 0)
            self.assertEqual(report["native_executions"], 0)

    def test_multi_law_vgi_and_native_ncr_are_verified_for_every_candidate(self):
        for name in ("safe_diagnosis","silent_common_funnel"):
            m = self.cases[name]["model"]
            vgi, source, nc, algebra = _verified_models(m)
            self.assertTrue(vgi.complete)
            self.assertEqual(len(source.states), m["n"])
            self.assertEqual(nc.source.states, tuple(range(m["n"])))
            self.assertEqual(nc.language.digest, algebra.language_sha256)

    def test_rehashed_multi_law_policy_cannot_install_fake_guaranteed_action(self):
        packet = deepcopy(self.cases["silent_conflict"])
        self.assertEqual(packet["certificate"]["rank"][packet["model"]["start"]], -1)
        packet["certificate"]["rank"][packet["model"]["start"]] = 1
        packet["certificate"]["policy"][packet["model"]["start"]] = 0
        rehash(packet)
        with self.assertRaisesRegex(ConstructionRefused, "ranks"):
            run_intention(packet, expected_source_digest=packet["source_digest"],
                          original_state=1)


if __name__ == "__main__":
    unittest.main()
