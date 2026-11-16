"""Real native VGI and E-CPU APIs; no mock policy, voting or planner.

The producers here are synthetic channel adapters. Passing these tests does
not prove external mTLS identity, source truth or physical stationarity.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import unittest

from vgi.channels import ChannelContract, ChannelExchangeLedger, ChannelMessage
from vgi.encounters import EncounterProvenance
from vgi.evidence import (
    EvidenceError, TransitionEvidenceLedger, TransitionEvidencePolicy,
    TransportFrameReceipt,
)

from native_reuse_bridge import (
    GROUND_ID, SOURCE_STATE, ACTION, ReuseRefused, prepare_native_intention,
    project_finalized_native_transition, conditionally_resolve_from_vgi,
)


CTX = sha256(b"iwi005/vgi-native-context-one").hexdigest()
CH = ChannelContract(
    "iwi.native.telemetry", "iwi.native.frame/1",
    observation_schema="vgi.transition-observation/1",
)


def build_ledger(first=2, second=2, *, finalize=True, unknown_second=False,
                 omit_second=False, context=CTX):
    policy = TransitionEvidencePolicy(
        GROUND_ID, context, ("receiver-a", "receiver-b"), 2, True
    )
    messages = []
    specs = [("receiver-a", first)]
    if not omit_second:
        specs.append(("receiver-b", second))
    exchange = ChannelExchangeLedger()
    for i, (source, target) in enumerate(specs, 1):
        payload = {"source_state": SOURCE_STATE, "action": ACTION}
        if unknown_second and i == 2:
            payload["status"] = "unknown"
        else:
            payload.update({"status": "known", "target": f"s{target}", "output": [0]})
        message = ChannelMessage(
            f"{source}-message-{i}", CH.channel_id, CH.protocol_id,
            "observation", payload,
            EncounterProvenance(source, f"capture://{source}/{i}", collector="synthetic-fixture"),
        )
        exchange = exchange.record_observation(CH, message)
        messages.append(message)
    encounter_ledger = exchange.to_encounter_ledger()
    ledger = TransitionEvidenceLedger(policy)
    for i, message in enumerate(messages, 1):
        frame = TransportFrameReceipt.capture(
            message, transport_id=f"fixture-transport-{message.provenance.source}",
            sequence=i,
        )
        ledger = ledger.ingest_channel_message(
            exchange, message.message_id, frame, encounter_ledger,
        )
    if finalize:
        ledger = ledger.finalize(SOURCE_STATE, ACTION)
    return ledger


class NativeReuseTests(unittest.TestCase):
    def test_vgi_finalization_and_ecpu_minimal_measurement_reuse(self):
        for target, expected in ((2, "finish-left"), (3, "finish-right")):
            with self.subTest(target=target):
                ledger = build_ledger(target, target)
                self.assertEqual(ledger.decision(SOURCE_STATE, ACTION).status, "AUTHORIZED")
                sample = project_finalized_native_transition(
                    ledger, expected_ground_id=GROUND_ID, expected_context_digest=CTX,
                )
                self.assertEqual(sample["status"], "VGI_FINALIZED_SAMPLE_ONLY")
                self.assertFalse(sample["ground_complete"])
                self.assertEqual(sample["unknown_pair_count"], 34)
                self.assertEqual(len(sample["evidence_ids"]), 2)
                self.assertFalse(sample["universal_law_proven"])
                self.assertRegex(sample["native_ground_fingerprint"], r"^[0-9a-f]{64}$")
                self.assertEqual(sample["candidate_branch"], target)
                result = conditionally_resolve_from_vgi(
                    ledger, expected_ground_id=GROUND_ID, expected_context_digest=CTX,
                    controlled_static_law_coverage=True,
                )
                self.assertEqual(result["status"], "CONDITIONAL_INTENTION_RESULT")
                self.assertEqual(result["selected_finishing_action"], expected)
                self.assertEqual(result["ecpu_selected_features"], ["persistent-branch"])
                self.assertEqual(result["ecpu_symbolic_cost"], 2)
                self.assertTrue(result["source_stability_assumed_not_proven"])
                self.assertFalse(result["ecpu_external_effect_authorized"])

    def test_ecpu_planner_not_a_new_query_optimizer(self):
        model, offers, plan = prepare_native_intention(CTX)
        self.assertEqual(plan["status"], "MEASURE")
        self.assertEqual(plan["candidate_count"], 2)
        self.assertEqual(plan["declared_cost_units"], 2)
        self.assertEqual(plan["selected_features"], ["persistent-branch"])
        self.assertEqual(len(model.states), 2)
        self.assertEqual(len(offers), 1)

    def test_unfinalized_vgi_quorum_is_not_admitted(self):
        ledger = build_ledger(finalize=False)
        self.assertEqual(ledger.status(SOURCE_STATE, ACTION).status, "QUORUM")
        with self.assertRaises(ReuseRefused):
            project_finalized_native_transition(
                ledger, expected_ground_id=GROUND_ID, expected_context_digest=CTX,
            )

    def test_partial_source_support_or_indeterminate_source_refuses(self):
        for ledger in (
            build_ledger(omit_second=True),
            build_ledger(unknown_second=True),
        ):
            self.assertEqual(ledger.decision(SOURCE_STATE, ACTION).status, "REFUSED")
            with self.assertRaises(ReuseRefused):
                project_finalized_native_transition(
                    ledger, expected_ground_id=GROUND_ID, expected_context_digest=CTX,
                )

    def test_declared_source_disagreement_stays_conflicted(self):
        ledger = build_ledger(2, 3)
        self.assertEqual(ledger.decision(SOURCE_STATE, ACTION).status, "CONFLICT")
        with self.assertRaises(ReuseRefused):
            conditionally_resolve_from_vgi(
                ledger, expected_ground_id=GROUND_ID, expected_context_digest=CTX,
                controlled_static_law_coverage=True,
            )

    def test_native_context_and_ground_identity_must_match(self):
        ledger = build_ledger()
        for ground, context in (
            ("other-ground", CTX),
            (GROUND_ID, sha256(b"changed-context").hexdigest()),
        ):
            with self.assertRaises(ReuseRefused):
                project_finalized_native_transition(
                    ledger, expected_ground_id=ground, expected_context_digest=context,
                )

    def test_declared_hypothesis_class_rejects_extra_successor(self):
        ledger = build_ledger(4, 4)
        with self.assertRaises(ReuseRefused):
            project_finalized_native_transition(
                ledger, expected_ground_id=GROUND_ID, expected_context_digest=CTX,
            )

    def test_single_vgi_sample_cannot_supply_static_coverage(self):
        ledger = build_ledger()
        with self.assertRaisesRegex(ReuseRefused, "persistent-law coverage"):
            conditionally_resolve_from_vgi(
                ledger, expected_ground_id=GROUND_ID, expected_context_digest=CTX,
                controlled_static_law_coverage=False,
            )

    def test_vgi_serialization_validator_rejects_tampered_finalization(self):
        ledger = build_ledger()
        data = ledger.to_dict()
        data["finalizations"][0]["decision_digest"] = "0" * 64
        with self.assertRaises(EvidenceError):
            TransitionEvidenceLedger.from_dict(data)


    def test_real_ecpu_sab002_retains_finite_witness_not_universal_law(self):
        from mailcpu.active_ground_discovery import (
            ObservedCodeHost, ProbeAuthority, discover,
        )
        from mailcpu.law_certifier import lcg_navigate
        mod, multiplier, increment, start = 17, 3, 5, 2
        def true_value(t):
            return lcg_navigate(multiplier, increment, mod, start, t)
        hidden = 100
        # A deceptive source follows the law at all SAB-002's probe coordinates
        # but differs at a later, untested point.
        def finite_deceiver(t):
            value = true_value(t)
            return (value + int(t == hidden)) % mod
        host = ObservedCodeHost(
            "synthetic-host", "controlled-synthetic-observer", mod,
            "permitted-probe", 200, finite_deceiver,
        )
        permission = ProbeAuthority(frozenset({"synthetic-host"}), "permitted-probe")
        candidate = discover(host, permission, coordinate=5)
        self.assertEqual(candidate.verification, "finite_witness_only")
        self.assertNotEqual(candidate.navigate(hidden), finite_deceiver(hidden))
        self.assertEqual(len(candidate.witness), 8)

    def test_no_new_authority_or_physical_execution_claim(self):
        result = conditionally_resolve_from_vgi(
            build_ledger(), expected_ground_id=GROUND_ID, expected_context_digest=CTX,
            controlled_static_law_coverage=True,
        )
        self.assertFalse(result["vgi_ground_admitted_by_bridge"])
        self.assertTrue(result["source_stability_assumed_not_proven"])
        self.assertEqual(result["vgi_sample"]["source_authenticated_by_this_adapter"], False)


if __name__ == "__main__":
    unittest.main()
