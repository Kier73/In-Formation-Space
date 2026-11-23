"""OFC-001: five real repository algorithms in one falsifiable intention loop."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from bridge import (
    ConstructionRefused, HiddenSourceHost, _affine_action, _host_inventory,
    _verified_models, _world, run_intention, source_fixture,
)
from mailcpu.intention_formed_fabric import form_observer_machine, realize_formed_intention
from mailcpu.substrate_bootstrap import BootstrapPolicy, BootstrapRefused
from vgi.transitions import (
    GroundTransitionSystem, TransitionObservation, TransitionOutcome,
    UnknownTransitionError,
)


def load(name):
    packet = source_fixture(name)
    assert packet["fixture"] == name
    return packet


def rehash(packet):
    packet["source_digest"] = sha256(json.dumps(
        {"model": packet["model"], "certificate": packet["certificate"]},
        separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf8")).hexdigest()
    return packet


class ObservationSufficientComputationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = {name: load(name) for name in ("funnel", "branch", "erased")}

    def test_all_hidden_origins_reach_goal_without_receiving_initial_state(self):
        for name in ("funnel", "branch"):
            source = self.models[name]
            n = source["model"]["n"]
            for original_state in range(n):
                with self.subTest(fixture=name, hidden_source=original_state):
                    report = run_intention(
                        source, expected_source_digest=source["source_digest"],
                        original_state=original_state,
                        failover_after=1 if name == "branch" else None,
                    )
                    self.assertEqual(report["status"], "GOAL_REALIZED_WITHOUT_INITIAL_IDENTIFICATION")
                    self.assertEqual(report["initial_belief_count"], n)
                    self.assertGreater(report["native_executions"], 0)
                    self.assertLessEqual(report["native_executions"],
                                         source["certificate"]["rank"][source["model"]["start"]])
                    self.assertTrue(report["final_belief_mask"] & ~source["model"]["goal"] == 0)
                    self.assertTrue(all("hidden" not in json.dumps(step)
                                        for step in report["steps"]))
                    self.assertEqual(len({step["execution"]["machine"] for step in report["steps"]}), 1)
                    self.assertEqual(len(report["receipt_sha256"]), 64)

    def test_blind_action_is_formed_and_executed_without_initial_state_read(self):
        source = self.models["funnel"]
        report = run_intention(
            source, expected_source_digest=source["source_digest"], original_state=2)
        self.assertEqual([r["action"] for r in report["steps"]], [1])
        self.assertEqual(report["observations"], 1)
        self.assertEqual(report["initial_belief_count"], 3)
        self.assertEqual(report["final_belief_count"], 1)
        self.assertEqual(report["vld_redundant_executions"], 1)
        self.assertEqual(report["steps"][0]["execution"]["vld_alternative"],
                         "fluid_in_transit_stream")

    def test_conditional_observations_change_action_and_survive_host_loss(self):
        source = self.models["branch"]
        traces = [run_intention(source, expected_source_digest=source["source_digest"],
                                original_state=i, failover_after=1) for i in range(3)]
        self.assertTrue(any(len(t["steps"]) > 1 for t in traces))
        self.assertGreater(len({tuple(s["action"] for s in t["steps"]) for t in traces}), 1)
        self.assertEqual(len({t["ecpu_machine"] for t in traces}), 1)
        for tr in traces:
            self.assertIn("worker.alpha", tr["steps"][0]["execution"]["path"])
            for step in tr["steps"][1:]:
                self.assertIn("worker.beta", step["execution"]["path"])
                self.assertNotIn("worker.alpha", step["execution"]["path"])

    def test_original_iwi_losing_belief_refuses_without_native_execution(self):
        source = self.models["erased"]
        report = run_intention(source, expected_source_digest=source["source_digest"],
                               original_state=2)
        self.assertEqual(report["status"], "UNREALIZABLE_FOR_ALL_DECLARED_INITIAL_STATES")
        self.assertEqual(report["native_executions"], 0)
        self.assertEqual(report["observations"], 0)

    def test_changed_source_head_refused_before_any_execution(self):
        source = self.models["funnel"]
        with self.assertRaisesRegex(ConstructionRefused, "source head"):
            run_intention(source, expected_source_digest="0"*64, original_state=2)

    def test_rehashed_forgery_of_winning_policy_is_not_admitted(self):
        source = rehash(deepcopy(self.models["funnel"]))
        source["certificate"]["rank"][source["model"]["start"]] = 0
        rehash(source)
        with self.assertRaisesRegex(ConstructionRefused, "ranks"):
            run_intention(source, expected_source_digest=source["source_digest"],
                          original_state=2)
        source = rehash(deepcopy(self.models["branch"]))
        source["certificate"]["policy"][source["model"]["start"]] = 99
        rehash(source)
        with self.assertRaisesRegex(ConstructionRefused, "rank-decreasing"):
            run_intention(source, expected_source_digest=source["source_digest"],
                          original_state=2)

    def test_vgi_unknown_transition_cannot_be_silently_executed(self):
        system = GroundTransitionSystem(
            ("s0", "s1"), ("a0",), "s0", ("visible",),
            (TransitionObservation("s0", "a0",
                                   (TransitionOutcome("s1", (1,)),)),),
        )
        self.assertFalse(system.complete)
        self.assertEqual(system.status("s1", "a0"), "unknown")
        with self.assertRaises(UnknownTransitionError):
            system.step("s1", "a0")

    def test_original_vgi_nc_ecpu_semantics_align_under_every_state_action(self):
        for name in ("funnel", "branch"):
            model, _ = _world(self.models[name])
            vgi, ecpu, nc, algebra = _verified_models(model)
            self.assertTrue(vgi.complete)
            self.assertEqual(len(nc.source.states), model["n"])
            self.assertGreaterEqual(algebra.dimension, 1)
            self.assertEqual(len(ecpu.states), len(nc.source.states))

    def test_non_affine_behavior_is_not_relabelled_as_a_vld_affine_operator(self):
        model = self.models["branch"]["model"]
        self.assertIsNone(_affine_action(model["next"][1], model["n"]))
        self.assertEqual(_affine_action(model["next"][0], model["n"]), (2, 0))

    def test_receiver_policy_revocation_refuses_native_execution(self):
        model, _ = _world(self.models["funnel"])
        _, law, _, _ = _verified_models(model)
        machine = form_observer_machine(law, ("visible", "goal"))
        inventory, policy, carriers = _host_inventory(machine.operation, alpha_available=True)
        revoked = BootstrapPolicy(frozenset(), policy.allowed_channels,
                                  "receiver-execution-revoked")
        with self.assertRaises(BootstrapRefused):
            realize_formed_intention(
                law, ("visible", "goal"), "s2", ("a1",),
                inventory, revoked, carriers,
                admitted_interpreters=("worker.alpha", "worker.beta"),
                admitted_observers=("witness",),
                ingress="input", observer="witness", coordinate=5,
            )


if __name__ == "__main__":
    unittest.main()
