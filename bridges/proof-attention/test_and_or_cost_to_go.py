from __future__ import annotations

import unittest

from and_or_cost_to_go import (
    AndOrCostToGoError,
    build_and_or_cost_to_go,
)
from empirical_probe_costs import EmpiricalProbeCostModel, ProbeCostBinding
from operation_spans import OperationSpanRecorder, build_operation_cost_profiles
from proof_attention import build_proof_attention_plan
from vgi.proof import ProofGroundAdapter, VerifiedKernelReceipt


ENVIRONMENT = {
    "assistant": "Lean",
    "assistant_version": "4.15.0",
    "environment_fingerprint": "and-or-env-sha256",
    "imports_fingerprint": "and-or-imports-sha256",
    "options_fingerprint": "and-or-options-sha256",
}


def make_ground(obligation_keys, transitions, *, accepted=(), rejected=()):
    payload = {
        "format": "VGI-LeanProofTrace-1",
        "environment": ENVIRONMENT,
        "obligations": [
            {"key": key, "goal": {"kind": "fixture-goal", "name": key, "type": "Nat"}}
            for key in obligation_keys
        ],
        "transitions": [
            {
                "source": source,
                "tactic": tactic,
                "subgoals": list(children),
                "attempt_status": status,
                "evidence_ref": f"fixture:{index}:{tactic}",
            }
            for index, (source, tactic, children, status) in enumerate(transitions)
        ],
    }
    initial = ProofGroundAdapter.from_lean_trace(payload)
    ids = dict(zip(obligation_keys, initial.obligation_ids))
    receipts = []
    for key in accepted:
        receipts.append(VerifiedKernelReceipt(
            ids[key],
            f"accepted-term:{key}",
            ENVIRONMENT["environment_fingerprint"],
            "Lean.kernel",
            "4.15.0",
            "accepted",
            f"receipt:accepted:{key}",
        ))
    for key in rejected:
        receipts.append(VerifiedKernelReceipt(
            ids[key],
            f"rejected-term:{key}",
            ENVIRONMENT["environment_fingerprint"],
            "Lean.kernel",
            "4.15.0",
            "rejected",
            f"receipt:rejected:{key}",
        ))
    return ProofGroundAdapter.from_lean_trace(
        payload,
        verified_receipts=tuple(receipts),
    ), ids


def make_cost_model(costs):
    ticks = []
    cursor = 100
    for _method, duration in sorted(costs.items()):
        for _sample in range(3):
            ticks.extend((cursor, cursor + duration))
            cursor += duration + 7
    clock = iter(ticks)
    recorder = OperationSpanRecorder(
        clock_actor_id="proof-worker",
        clock_segment_id="proof-process-boot",
        clock_ns=lambda: next(clock),
    )
    for method, duration in sorted(costs.items()):
        for index in range(3):
            recorder.measure(
                attempt_id=f"{method}:sample:{index}",
                span_id=f"{method}:span:{index}",
                operation_id=f"lean.tactic.{method}",
                operation=lambda: None,
                context={"tactic": method, "fixture_duration_ns": duration},
            )
    spans = list(recorder.spans)
    profile = build_operation_cost_profiles(spans, minimum_samples=3)
    bindings = tuple(
        ProbeCostBinding(
            method_id=method,
            operation_id=f"lean.tactic.{method}",
            clock_actor_id="proof-worker",
            clock_segment_id="proof-process-boot",
            statistic="p90_ns",
        )
        for method in sorted(costs)
    )
    return EmpiricalProbeCostModel(
        spans,
        profile,
        bindings,
        minimum_samples=3,
    )


def transition_by_tactic(ground, tactic):
    return next(edge for edge in ground.transitions if edge.tactic == tactic)


class AndOrCostToGoTests(unittest.TestCase):
    def test_selects_lowest_total_cost_instead_of_cheapest_first_tactic(self):
        ground, ids = make_ground(
            ("root", "left", "right", "done"),
            (
                ("root", "branch", ("left", "right"), "candidate"),
                ("root", "direct", ("done",), "candidate"),
                ("left", "left-close", (), "candidate"),
                ("right", "right-close", (), "candidate"),
            ),
            accepted=("done",),
        )
        model = make_cost_model({
            "branch": 10,
            "direct": 50,
            "left-close": 30,
            "right-close": 40,
        })

        result = build_and_or_cost_to_go(
            ground, (ids["root"],), cost_model=model
        )
        root = result["roots"][0]
        self.assertEqual(root["selected_transition_id"], transition_by_tactic(ground, "direct").transition_id)
        self.assertEqual(root["summed_component_cost_ns"], 50)
        self.assertEqual(root["candidate_action_count"], 1)
        self.assertEqual(root["plan"]["requires_verified_kernel_receipt"], True)
        self.assertEqual(ground.kernel_status(ids["root"]), "unverified")

    def test_and_bundle_cost_adds_every_required_child_route(self):
        ground, ids = make_ground(
            ("root", "left", "right", "done"),
            (
                ("root", "branch", ("left", "right"), "candidate"),
                ("root", "direct", ("done",), "candidate"),
                ("left", "left-close", (), "candidate"),
                ("right", "right-close", (), "candidate"),
            ),
            accepted=("done",),
        )
        model = make_cost_model({
            "branch": 5,
            "direct": 100,
            "left-close": 30,
            "right-close": 40,
        })

        root = build_and_or_cost_to_go(
            ground, (ids["root"],), cost_model=model
        )["roots"][0]
        self.assertEqual(root["selected_transition_id"], transition_by_tactic(ground, "branch").transition_id)
        self.assertEqual(root["summed_component_cost_ns"], 75)
        selected = root["plan"]["selected_transition"]
        self.assertEqual(selected["subgoal_ids"], [ids["left"], ids["right"]])
        self.assertEqual(
            [child["selected_transition"]["tactic"] for child in root["plan"]["children"]],
            ["left-close", "right-close"],
        )

    def test_cost_to_go_can_choose_different_first_action_than_structural_attention(self):
        ground, ids = make_ground(
            ("root", "left", "right", "done"),
            (
                ("root", "branch", ("left", "right"), "candidate"),
                ("root", "direct", ("done",), "candidate"),
                ("left", "left-close", (), "candidate"),
                ("right", "right-close", (), "candidate"),
            ),
            accepted=("done",),
        )
        structural = build_proof_attention_plan(ground, (ids["root"],))
        structural_first = structural["candidate_actions"][0]["transition_id"]
        structural_edge = next(
            edge for edge in ground.transitions
            if edge.transition_id == structural_first
        )
        if structural_edge.tactic == "branch":
            costs = {
                "branch": 200,
                "direct": 10,
                "left-close": 20,
                "right-close": 20,
            }
        else:
            costs = {
                "branch": 1,
                "direct": 200,
                "left-close": 20,
                "right-close": 20,
            }

        result = build_and_or_cost_to_go(
            ground,
            (ids["root"],),
            cost_model=make_cost_model(costs),
        )
        self.assertNotEqual(
            result["roots"][0]["selected_transition_id"],
            structural_first,
        )
        self.assertEqual(
            result["structural_frontier_action_order"][0],
            structural_first,
        )

    def test_elaborated_edge_is_sunk_cost_and_exposes_current_child_action(self):
        ground, ids = make_ground(
            ("root", "child", "done"),
            (
                ("root", "already-elaborated", ("child",), "elaborated"),
                ("root", "redo-at-root", ("done",), "candidate"),
                ("child", "finish-child", ("done",), "candidate"),
            ),
            accepted=("done",),
        )
        model = make_cost_model({"redo-at-root": 50, "finish-child": 20})

        result = build_and_or_cost_to_go(
            ground, (ids["root"],), cost_model=model
        )
        root = result["roots"][0]
        self.assertEqual(
            root["selected_transition_id"],
            transition_by_tactic(ground, "already-elaborated").transition_id,
        )
        self.assertEqual(root["summed_component_cost_ns"], 20)
        self.assertEqual(
            root["next_action_transition_ids"],
            [transition_by_tactic(ground, "finish-child").transition_id],
        )
        child_plan = root["plan"]["children"][0]
        self.assertEqual(child_plan["activation"], "confirmed_frontier")

    def test_candidate_descendants_are_conditional_and_not_dispatchable_yet(self):
        ground, ids = make_ground(
            ("root", "proposed-child", "done"),
            (
                ("root", "open-branch", ("proposed-child",), "candidate"),
                ("proposed-child", "close-child", ("done",), "candidate"),
            ),
            accepted=("done",),
        )
        result = build_and_or_cost_to_go(
            ground,
            (ids["root"],),
            cost_model=make_cost_model({"open-branch": 10, "close-child": 15}),
        )
        root = result["roots"][0]
        child = root["plan"]["children"][0]
        self.assertEqual(root["summed_component_cost_ns"], 25)
        self.assertEqual(child["activation"], "conditional_on_candidate_elaboration")
        self.assertEqual(
            root["next_action_transition_ids"],
            [transition_by_tactic(ground, "open-branch").transition_id],
        )
        self.assertNotIn(
            ids["proposed-child"],
            result["confirmed_frontier_obligation_ids"],
        )

    def test_empty_candidate_bundle_still_requires_verified_kernel_receipt(self):
        ground, ids = make_ground(
            ("root",),
            (("root", "trivial", (), "candidate"),),
        )
        root = build_and_or_cost_to_go(
            ground,
            (ids["root"],),
            cost_model=make_cost_model({"trivial": 12}),
        )["roots"][0]
        self.assertEqual(root["estimate_status"], "finite_route_found")
        self.assertEqual(root["summed_component_cost_ns"], 12)
        self.assertTrue(root["requires_verified_kernel_receipt"])
        self.assertEqual(root["kernel_status"], "unverified")

    def test_cycle_without_a_finite_exit_has_no_route(self):
        ground, ids = make_ground(
            ("root", "child"),
            (
                ("root", "enter-child", ("child",), "candidate"),
                ("child", "return-to-root", ("root",), "candidate"),
            ),
        )
        result = build_and_or_cost_to_go(
            ground,
            (ids["root"],),
            cost_model=make_cost_model({
                "enter-child": 5,
                "return-to-root": 2,
            }),
        )
        self.assertEqual(result["roots"][0]["estimate_status"], "no_finite_route")
        self.assertIsNone(result["roots"][0]["summed_component_cost_ns"])

    def test_positive_cycle_does_not_displace_a_finite_exit(self):
        ground, ids = make_ground(
            ("root", "child"),
            (
                ("root", "enter-child", ("child",), "candidate"),
                ("child", "return-to-root", ("root",), "candidate"),
                ("child", "exit", (), "candidate"),
            ),
        )
        result = build_and_or_cost_to_go(
            ground,
            (ids["root"],),
            cost_model=make_cost_model({
                "enter-child": 5,
                "return-to-root": 1,
                "exit": 10,
            }),
        )
        root = result["roots"][0]
        self.assertEqual(root["estimate_status"], "finite_route_found")
        self.assertEqual(root["summed_component_cost_ns"], 15)
        child_plan = root["plan"]["children"][0]
        self.assertEqual(child_plan["selected_transition"]["tactic"], "exit")

    def test_failed_attempts_are_history_not_available_routes(self):
        ground, ids = make_ground(
            ("root", "done"),
            (
                ("root", "timed-out", ("done",), "timeout"),
                ("root", "rejected", ("done",), "rejected"),
            ),
        )
        result = build_and_or_cost_to_go(ground, (ids["root"],))
        self.assertEqual(result["cost_comparison"]["status"], "not_required")
        self.assertEqual(result["roots"][0]["estimate_status"], "no_finite_route")

    def test_kernel_accepted_root_is_terminal_without_cost_evidence(self):
        ground, ids = make_ground(("root",), (), accepted=("root",))
        root = build_and_or_cost_to_go(ground, (ids["root"],))["roots"][0]
        self.assertEqual(root["estimate_status"], "kernel_accepted")
        self.assertEqual(root["summed_component_cost_ns"], 0)
        self.assertFalse(root["requires_verified_kernel_receipt"])

    def test_missing_candidate_binding_fails_closed(self):
        ground, ids = make_ground(
            ("root", "done"),
            (
                ("root", "known", ("done",), "candidate"),
                ("root", "unknown", ("done",), "candidate"),
            ),
            accepted=("done",),
        )
        model = make_cost_model({"known": 10})
        with self.assertRaisesRegex(AndOrCostToGoError, "no valid empirical cost"):
            build_and_or_cost_to_go(ground, (ids["root"],), cost_model=model)

    def test_kernel_rejection_does_not_become_a_terminal_success(self):
        ground, ids = make_ground(
            ("root",),
            (("root", "retry-with-new-context", (), "candidate"),),
            rejected=("root",),
        )
        root = build_and_or_cost_to_go(
            ground,
            (ids["root"],),
            cost_model=make_cost_model({"retry-with-new-context": 18}),
        )["roots"][0]
        self.assertEqual(root["kernel_status"], "kernel_rejected")
        self.assertEqual(root["estimate_status"], "finite_route_found")
        self.assertTrue(root["requires_verified_kernel_receipt"])

    def test_result_is_deterministic_and_has_a_content_digest(self):
        ground, ids = make_ground(
            ("root", "done"),
            (("root", "close", ("done",), "candidate"),),
            accepted=("done",),
        )
        model = make_cost_model({"close": 22})
        first = build_and_or_cost_to_go(ground, (ids["root"],), cost_model=model)
        second = build_and_or_cost_to_go(ground, (ids["root"],), cost_model=model)
        self.assertEqual(first, second)
        self.assertEqual(len(first["plan_digest"]), 64)
        self.assertEqual(first["policy_effect"], "analysis_only")


if __name__ == "__main__":
    unittest.main(verbosity=2)
