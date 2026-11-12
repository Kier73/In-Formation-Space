from __future__ import annotations

import unittest

from empirical_probe_costs import EmpiricalProbeCostModel, ProbeCostBinding
from operation_spans import OperationSpanRecorder, build_operation_cost_profiles
from proof_attention import ProofAttentionError, build_proof_attention_plan
from vgi.proof import ProofGroundAdapter, VerifiedKernelReceipt


ENVIRONMENT = {
    "assistant": "Lean",
    "assistant_version": "4.15.0",
    "environment_fingerprint": "env-sha256",
    "imports_fingerprint": "imports-sha256",
    "options_fingerprint": "options-sha256",
}


def proof_trace():
    return {
        "format": "VGI-LeanProofTrace-1",
        "environment": ENVIRONMENT,
        "obligations": [
            {"key": "root", "goal": {"kind": "root", "type": "Nat"}},
            {"key": "second-root", "goal": {"kind": "second-root", "type": "Nat"}},
            {"key": "shared", "goal": {"kind": "shared", "type": "Nat"}},
            {"key": "base", "goal": {"kind": "base", "type": "Nat"}},
            {"key": "step", "goal": {"kind": "step", "type": "Nat"}},
            {"key": "orphan", "goal": {"kind": "orphan", "type": "Nat"}},
        ],
        "transitions": [
            # The root's induction result is one AND bundle.
            {"source": "root", "tactic": "induction", "subgoals": ["shared", "base"],
             "attempt_status": "elaborated", "evidence_ref": "trace:1"},
            # Candidate alternatives stay separate OR choices.
            {"source": "root", "tactic": "simp", "subgoals": ["base"],
             "attempt_status": "candidate", "evidence_ref": "candidate:simp"},
            {"source": "root", "tactic": "rfl", "subgoals": [],
             "attempt_status": "candidate", "evidence_ref": "candidate:rfl"},
            {"source": "root", "tactic": "old-simp", "subgoals": [],
             "attempt_status": "timeout", "evidence_ref": "timeout:1"},
            {"source": "second-root", "tactic": "split", "subgoals": ["shared"],
             "attempt_status": "elaborated", "evidence_ref": "trace:2"},
            {"source": "shared", "tactic": "cases", "subgoals": ["step", "base"],
             "attempt_status": "elaborated", "evidence_ref": "trace:3"},
            {"source": "shared", "tactic": "constructor", "subgoals": ["step", "base"],
             "attempt_status": "candidate", "evidence_ref": "candidate:constructor"},
            {"source": "shared", "tactic": "old-cases", "subgoals": ["step"],
             "attempt_status": "rejected", "evidence_ref": "rejected:1"},
            {"source": "step", "tactic": "assumption", "subgoals": [],
             "attempt_status": "candidate", "evidence_ref": "candidate:assumption"},
            # A candidate edge does not make its proposed child reachable yet.
            {"source": "root", "tactic": "future-branch", "subgoals": ["orphan"],
             "attempt_status": "candidate", "evidence_ref": "candidate:future"},
            # An elaborated self-loop must not make traversal non-terminating.
            {"source": "shared", "tactic": "normalize", "subgoals": ["shared"],
             "attempt_status": "elaborated", "evidence_ref": "trace:loop"},
            # Not reachable from either active intention.
            {"source": "orphan", "tactic": "trivial", "subgoals": [],
             "attempt_status": "candidate", "evidence_ref": "candidate:orphan"},
        ],
        # This untrusted claim must never become an accepted receipt.
        "kernel_claims": ["root"],
    }


def make_ground(*, rejected_step=False):
    payload = proof_trace()
    unreceipted = ProofGroundAdapter.from_lean_trace(payload)
    base_id = unreceipted.obligation_ids[3]
    receipts = [
        VerifiedKernelReceipt(
            base_id,
            "proof-term-base-sha256",
            ENVIRONMENT["environment_fingerprint"],
            "Lean.kernel",
            "4.15.0",
            "accepted",
            "kernel-receipt:base",
        )
    ]
    if rejected_step:
        step_id = unreceipted.obligation_ids[4]
        receipts.append(VerifiedKernelReceipt(
            step_id,
            "rejected-proof-term-sha256",
            ENVIRONMENT["environment_fingerprint"],
            "Lean.kernel",
            "4.15.0",
            "rejected",
            "kernel-receipt:rejected-step",
        ))
    return ProofGroundAdapter.from_lean_trace(payload, verified_receipts=tuple(receipts))


def make_cost_model(*, bind_simp=True):
    clock = {"now": 0}
    meter = OperationSpanRecorder(
        clock_actor_id="proof-worker-1",
        clock_segment_id="process-boot-1",
        clock_ns=lambda: clock["now"],
    )
    durations = {
        "simp": ("lean.tactic.simp", (90, 100, 110)),
        "rfl": ("lean.tactic.rfl", (20, 25, 30)),
        "constructor": ("lean.tactic.constructor", (40, 45, 50)),
        "assumption": ("lean.tactic.assumption", (30, 35, 40)),
        "future-branch": ("lean.tactic.future-branch", (250, 260, 270)),
    }
    for tactic, (operation_id, samples) in durations.items():
        for index, duration in enumerate(samples):
            meter.measure(
                attempt_id=f"{tactic}-sample-{index}",
                span_id=f"{tactic}-span-{index}",
                operation_id=operation_id,
                operation=lambda elapsed=duration: clock.update(now=clock["now"] + elapsed),
                context={"tactic": tactic},
            )
    spans = list(meter.spans)
    profile = build_operation_cost_profiles(spans, minimum_samples=3)
    tactics = tuple(durations) if bind_simp else ("rfl", "constructor", "assumption", "future-branch")
    bindings = tuple(
        ProbeCostBinding(
            method_id=tactic,
            operation_id=durations[tactic][0],
            clock_actor_id="proof-worker-1",
            clock_segment_id="process-boot-1",
            statistic="p90_ns",
        )
        for tactic in tactics
    )
    return EmpiricalProbeCostModel(spans, profile, bindings, minimum_samples=3)


class ProofAttentionTests(unittest.TestCase):
    def setUp(self):
        self.ground = make_ground()
        self.root = self.ground.obligation_ids[0]
        self.second_root = self.ground.obligation_ids[1]
        self.shared = self.ground.obligation_ids[2]
        self.base = self.ground.obligation_ids[3]
        self.step = self.ground.obligation_ids[4]
        self.orphan = self.ground.obligation_ids[5]

    def test_active_intentions_scope_the_confirmed_frontier(self):
        plan = build_proof_attention_plan(self.ground, (self.root, self.second_root))
        self.assertEqual(plan["summary"]["reachable_obligation_count"], 5)
        self.assertNotIn(self.orphan, {item["obligation_id"] for item in plan["frontier"]})
        self.assertEqual(plan["active_root_obligation_ids"], sorted((self.root, self.second_root)))

    def test_and_bundles_and_or_alternatives_remain_structurally_distinct(self):
        plan = build_proof_attention_plan(self.ground, (self.root, self.second_root))
        actions = plan["candidate_actions"]
        induction_source = next(item for item in plan["frontier"] if item["obligation_id"] == self.root)
        shared_source = next(item for item in plan["frontier"] if item["obligation_id"] == self.shared)
        self.assertEqual(induction_source["elaborated_alternative_count"], 1)
        self.assertEqual(shared_source["elaborated_alternative_count"], 2)
        shared_action = next(item for item in actions if item["source_obligation_id"] == self.shared)
        self.assertEqual(shared_action["and_bundle_width"], 2)
        self.assertEqual(
            [item["obligation_id"] for item in shared_action["and_bundle"]],
            [self.step, self.base],
        )
        root_actions = [item for item in actions if item["source_obligation_id"] == self.root]
        self.assertEqual({item["tactic"] for item in root_actions}, {"simp", "rfl", "future-branch"})
        self.assertTrue(all(item["requires_parent_kernel_receipt"] for item in actions))

    def test_shared_subgoal_carries_both_root_intentions(self):
        plan = build_proof_attention_plan(self.ground, (self.root, self.second_root))
        shared = next(item for item in plan["frontier"] if item["obligation_id"] == self.shared)
        self.assertEqual(shared["intent_root_count"], 2)
        self.assertEqual(set(shared["intent_root_ids"]), {self.root, self.second_root})
        # The planner exposes structural leverage but makes no probability claim.
        self.assertIsNone(plan["interpretation"]["success_probability"])

    def test_candidate_children_are_conditional_until_elaboration(self):
        plan = build_proof_attention_plan(self.ground, (self.root,))
        reachable = {item["obligation_id"] for item in plan["frontier"]}
        self.assertNotIn(self.orphan, reachable)
        future = next(item for item in plan["candidate_actions"] if item["tactic"] == "future-branch")
        self.assertEqual(future["and_bundle"][0]["obligation_id"], self.orphan)
        self.assertNotIn(self.orphan, reachable)

    def test_accepted_children_do_not_promote_parent_to_kernel_accepted(self):
        plan = build_proof_attention_plan(self.ground, (self.root,))
        simp = next(item for item in plan["candidate_actions"] if item["tactic"] == "simp")
        self.assertEqual(simp["and_bundle"][0]["kernel_status"], "kernel_accepted")
        self.assertEqual(simp["bundle_status"], "all_children_accepted_parent_still_unverified")
        self.assertTrue(simp["requires_parent_kernel_receipt"])
        self.assertEqual(self.ground.kernel_status(self.root), "unverified")

    def test_kernel_rejected_receipt_is_not_treated_as_success_or_terminal_failure(self):
        ground = make_ground(rejected_step=True)
        plan = build_proof_attention_plan(ground, (self.root, self.second_root))
        step = next(item for item in plan["frontier"] if item["obligation_id"] == self.step)
        self.assertEqual(step["kernel_status"], "kernel_rejected")
        action = next(item for item in plan["candidate_actions"] if item["tactic"] == "assumption")
        self.assertEqual(action["source_obligation_id"], self.step)

    def test_timeout_and_rejected_attempts_remain_history_not_retry_actions(self):
        plan = build_proof_attention_plan(self.ground, (self.root, self.second_root))
        root = next(item for item in plan["frontier"] if item["obligation_id"] == self.root)
        shared = next(item for item in plan["frontier"] if item["obligation_id"] == self.shared)
        self.assertEqual(root["failed_attempt_count"], 1)
        self.assertEqual(shared["failed_attempt_count"], 1)
        self.assertNotIn("old-simp", {item["tactic"] for item in plan["candidate_actions"]})
        self.assertNotIn("old-cases", {item["tactic"] for item in plan["candidate_actions"]})

    def test_measured_costs_are_used_only_when_all_candidate_methods_are_bound(self):
        model = make_cost_model()
        plan = build_proof_attention_plan(self.ground, (self.root, self.second_root), cost_model=model)
        self.assertEqual(plan["cost_comparison"]["status"], "comparable")
        self.assertTrue(plan["cost_comparison"]["ranking_applied"])
        root_actions = [item for item in plan["candidate_actions"] if item["source_obligation_id"] == self.root]
        self.assertEqual([item["tactic"] for item in root_actions], ["rfl", "simp", "future-branch"])
        self.assertTrue(all(item["cost_provenance"] is not None for item in plan["candidate_actions"]))

    def test_missing_measured_method_never_becomes_zero_cost(self):
        model = make_cost_model(bind_simp=False)
        plan = build_proof_attention_plan(self.ground, (self.root, self.second_root), cost_model=model)
        self.assertEqual(plan["cost_comparison"]["status"], "incomplete_bindings")
        self.assertFalse(plan["cost_comparison"]["ranking_applied"])
        self.assertEqual(plan["cost_comparison"]["missing_methods"], ["simp"])
        self.assertTrue(all(item["cost_provenance"] is None for item in plan["candidate_actions"]))

    def test_cycles_terminate_and_plan_digest_is_deterministic(self):
        first = build_proof_attention_plan(self.ground, (self.root, self.second_root))
        second = build_proof_attention_plan(self.ground, (self.root, self.second_root))
        self.assertEqual(first["plan_digest"], second["plan_digest"])
        self.assertEqual(len(first["frontier"]), 5)

    def test_intentions_are_required_unique_and_must_exist(self):
        with self.assertRaisesRegex(ProofAttentionError, "at least one"):
            build_proof_attention_plan(self.ground, ())
        with self.assertRaisesRegex(ProofAttentionError, "unique"):
            build_proof_attention_plan(self.ground, (self.root, self.root))
        with self.assertRaisesRegex(ProofAttentionError, "unknown active root"):
            build_proof_attention_plan(self.ground, ("missing",))

    def test_non_comparable_cost_domains_are_rejected(self):
        class BadCostModel:
            def __init__(self):
                self.model = make_cost_model()

            def provenance_for(self, method_id):
                record = self.model.provenance_for("simp")
                record["method_id"] = method_id
                if method_id == "rfl":
                    record["clock_segment_id"] = "another-process-boot"
                return record
        with self.assertRaisesRegex(ProofAttentionError, "clock domain"):
            build_proof_attention_plan(self.ground, (self.root,), cost_model=BadCostModel())


if __name__ == "__main__":
    unittest.main(verbosity=2)
