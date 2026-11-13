from __future__ import annotations

import copy
import hashlib
import json
import unittest
from fractions import Fraction

from finite_horizon_reference_policy import build_report as build_policy_report
from finite_horizon_policy_execution import (
    build_reference_policy_execution_record,
    new_reference_policy_observation_path,
)
from verified_reference_evidence_bundle import (
    ReferenceEvidenceMismatch,
    ReferenceEvidenceVerificationError,
    build_verified_reference_evidence_bundle,
    validate_verified_reference_evidence_bundle,
)
from validate_envelope import compute_payload_digest


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def channel(alpha, beta):
    return {
        "p_signal_a_given_hypothesis_a": alpha,
        "p_signal_a_given_hypothesis_b": beta,
    }


def build_policy():
    calibrations = (
        {
            "calibration_id": "profile-1",
            "prior_probability": "1/2",
            "sensor_models": {
                "sensor-0": channel("1/2", "1/2"),
                "sensor-1": channel("1/10", "4/5"),
                "sensor-2": channel("7/10", "7/10"),
            },
        },
        {
            "calibration_id": "profile-2",
            "prior_probability": "1/2",
            "sensor_models": {
                "sensor-0": channel("1/10", "9/10"),
                "sensor-1": channel("2/5", "4/5"),
                "sensor-2": channel("3/5", "1/5"),
            },
        },
    )
    specifications = (
        ("sensor-0-standard-A", "sensor-0", "A", "1/2"),
        ("sensor-0-standard-B", "sensor-0", "B", "1"),
        ("sensor-1-standard-A", "sensor-1", "A", "1/2"),
        ("sensor-1-standard-B", "sensor-1", "B", "1/4"),
        ("sensor-2-standard-A", "sensor-2", "A", "5/4"),
        ("sensor-2-standard-B", "sensor-2", "B", "5/4"),
    )
    candidates = tuple({
        "candidate_id": candidate_id,
        "sensor_id": sensor_id,
        "known_hypothesis": standard,
        "reference_standard_ref": f"fixture://standard/{candidate_id}",
        "reference_standard_sha256": sha(f"known standard: {candidate_id}"),
        "cost": cost,
    } for candidate_id, sensor_id, standard, cost in specifications)
    return build_policy_report(
        prior_hypothesis_a="1/2",
        calibrations=calibrations,
        target_sensor_schedule=("sensor-0", "sensor-1", "sensor-2"),
        reference_candidates=candidates,
        max_reference_steps=3,
        cost_budget="3/2",
    )


def make_path_and_envelope(policy, *, signal="A", sources=("source-a", "source-b"), dissenting=()):
    attempt_id = "reference-attempt-001"
    path = new_reference_policy_observation_path(
        policy_report=policy,
        attempt_id=attempt_id,
    )
    node = policy["finite_horizon_policy"]["root"]
    state_digest = path.intent.hypothesis_set_digest
    node_digest = digest(node)
    standard_payload_records = []
    logical_event = {"kind": "reference-calibration", "logical_time": 0}
    for index, source in enumerate(sources, start=1):
        source_payload = {
            "sensor_id": node["sensor_id"],
            "known_hypothesis": node["known_hypothesis"],
            "signal": signal,
            "source": source,
            "sample_index": index,
        }
        standard_payload_records.append({
            "attempt_id": attempt_id,
            "observation_id": attempt_id,
            "event": logical_event,
            "source": source,
            "channel": f"reference:{node['sensor_id']}",
            "sequence": index,
            "payload_digest": digest(source_payload),
            "payload_value": source_payload,
        })
    returned_value = {
        "policy_report_digest": policy["report_digest"],
        "policy_state_digest": state_digest,
        "policy_node_digest": node_digest,
        "history_signal_prefix": [],
        "candidate_id": node["candidate_id"],
        "sensor_id": node["sensor_id"],
        "dimension": "calibration-reference",
        "known_hypothesis": node["known_hypothesis"],
        "reference_standard_ref": node["reference_standard_ref"],
        "reference_standard_sha256": node["reference_standard_sha256"],
        "observed_outcome": signal,
        "source_evidence_records": standard_payload_records,
    }
    envelope_id = "reference-encounter-001"
    envelope = {
        "format": "in-formation.encounter/0.1",
        "id": envelope_id,
        "source": {
            "kind": "sensor",
            "name": node["sensor_id"],
            "reference": node["sensor_id"],
        },
        "payload": {
            "media_type": "application/json",
            "value": returned_value,
        },
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-utf8-v1",
            "digest": digest(returned_value),
        },
    }
    returned_details = {
        **{key: returned_value[key] for key in (
            "policy_report_digest",
            "policy_state_digest",
            "policy_node_digest",
            "history_signal_prefix",
            "candidate_id",
            "sensor_id",
            "dimension",
            "known_hypothesis",
            "reference_standard_ref",
            "reference_standard_sha256",
            "observed_outcome",
        )},
        "encounter_id": envelope_id,
        "payload_digest": envelope["integrity"]["digest"],
        "canonicalization": "json-sort-keys-utf8-v1",
    }

    path.append(
        "dispatched", "reference-sensor-agent",
        evidence_ref="dispatch://reference-attempt-001",
        details={"request_id": attempt_id},
    )
    path.append(
        "admitted", "reference-receiver",
        evidence_ref="admission://reference-attempt-001",
        details={"receiver_id": "reference-receiver-01"},
    )
    path.append(
        "returned", "reference-receiver",
        evidence_ref="encounter://reference-attempt-001",
        details=returned_details,
    )
    path.append(
        "evidence_authorized", "reference-consensus",
        evidence_ref="authority://reference-attempt-001",
        details={
            "decision_status": "AUTHORIZED",
            "policy_digest": sha("reference sensor quorum policy"),
            "decision_digest": sha("finalized reference authority decision"),
            "quorum": 2,
            "strict": True,
            "observed_sources": sorted(sources),
            "dissenting_sources": sorted(dissenting),
            "missing_sources": [],
            "representative_source": "source-a",
        },
    )
    path.append(
        "interpreted", "reference-interpreter",
        evidence_ref="interpretation://reference-attempt-001",
        details={
            "method": "finite-horizon-reference-signal-v1",
            **{key: returned_value[key] for key in (
                "policy_report_digest",
                "policy_state_digest",
                "policy_node_digest",
                "history_signal_prefix",
                "candidate_id",
                "sensor_id",
                "dimension",
                "known_hypothesis",
                "reference_standard_ref",
                "reference_standard_sha256",
                "observed_outcome",
            )},
        },
    )
    execution_record = build_reference_policy_execution_record(
        policy_report=policy,
        observation_paths=(path,),
    )
    return execution_record, envelope


class VerifiedReferenceEvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.policy = build_policy()
        self.execution, self.envelope = make_path_and_envelope(self.policy)
        self.bundle = build_verified_reference_evidence_bundle(
            policy_execution_record=self.execution,
            encounter_envelopes=(self.envelope,),
            authority_ledger_id="reference-policy-ledger-test",
            ledger_created_by="riv013-test-suite",
        )

    def test_inline_envelope_and_source_records_are_verified_and_bound_to_lineage(self):
        self.assertEqual(
            self.bundle["verification_status"],
            "inline_envelope_integrity_verified_and_authority_lineage_reconstructed",
        )
        summary = self.bundle["encounter_envelope_summaries"][0]
        self.assertEqual(summary["integrity_status"], "VERIFIED")
        self.assertEqual(summary["source_ids"], ["source-a", "source-b"])
        self.assertEqual(len(self.bundle["authority_ledger"]["entries"]), 2)
        self.assertEqual(len(self.bundle["authority_receipts"]), 1)
        receipt = self.bundle["authority_receipts"][0]
        self.assertEqual(receipt["event_key"], {"kind": "reference-calibration", "logical_time": 0})
        self.assertEqual(
            receipt["authority_lineage_receipt"]["decision_status"],
            "AUTHORIZED",
        )
        self.assertEqual(
            receipt["authority_lineage_receipt"]["evidence_sources"],
            ["source-a", "source-b"],
        )
        self.assertEqual(
            validate_verified_reference_evidence_bundle(self.bundle),
            self.bundle,
        )

    def test_payload_tampering_without_digest_update_is_rejected(self):
        changed = copy.deepcopy(self.envelope)
        changed["payload"]["value"]["observed_outcome"] = "B"
        with self.assertRaises(ReferenceEvidenceVerificationError):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed,),
                authority_ledger_id="tampered-envelope",
                ledger_created_by="test",
            )

    def test_recomputed_envelope_digest_does_not_hide_path_mismatch(self):
        changed = copy.deepcopy(self.envelope)
        changed["payload"]["value"]["observed_outcome"] = "B"
        changed["integrity"]["digest"] = digest(changed["payload"]["value"])
        with self.assertRaises(ReferenceEvidenceMismatch):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed,),
                authority_ledger_id="changed-envelope",
                ledger_created_by="test",
            )

    def test_source_payload_digest_is_verified_independently(self):
        changed = copy.deepcopy(self.envelope)
        changed["payload"]["value"]["source_evidence_records"][0]["payload_value"]["signal"] = "B"
        changed["integrity"]["digest"] = digest(changed["payload"]["value"])
        with self.assertRaises(ReferenceEvidenceMismatch):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed,),
                authority_ledger_id="changed-source-payload",
                ledger_created_by="test",
            )

    def test_source_records_must_cover_authorized_observed_source_set(self):
        changed = copy.deepcopy(self.envelope)
        changed["payload"]["value"]["source_evidence_records"].pop()
        changed["integrity"]["digest"] = digest(changed["payload"]["value"])
        with self.assertRaises(ReferenceEvidenceMismatch):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed,),
                authority_ledger_id="missing-source",
                ledger_created_by="test",
            )

    def test_authorized_representative_must_be_in_the_non_dissenting_group(self):
        execution, _ = make_path_and_envelope(
            self.policy,
            sources=("source-a", "source-b"),
            dissenting=("source-a",),
        )
        with self.assertRaises(ReferenceEvidenceMismatch):
            build_verified_reference_evidence_bundle(
                policy_execution_record=execution,
                encounter_envelopes=(self.envelope,),
                authority_ledger_id="bad-representative",
                ledger_created_by="test",
            )

    def test_encounter_envelope_identifier_must_match_returned_encounter(self):
        changed = copy.deepcopy(self.envelope)
        changed["id"] = "another-encounter"
        with self.assertRaises(ReferenceEvidenceMismatch):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed,),
                authority_ledger_id="wrong-id",
                ledger_created_by="test",
            )

    def test_reference_requires_one_inline_integrity_verified_envelope_per_path(self):
        referenced = copy.deepcopy(self.envelope)
        referenced["payload"] = {
            "reference": "artifact://external/reference-payload",
        }
        referenced["integrity"]["digest"] = sha("external payload")
        with self.assertRaises(ReferenceEvidenceVerificationError):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(referenced,),
                authority_ledger_id="external-reference",
                ledger_created_by="test",
            )
        with self.assertRaises(ReferenceEvidenceVerificationError):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(),
                authority_ledger_id="missing-envelope",
                ledger_created_by="test",
            )

    def test_bad_schema_or_integrity_algorithm_is_rejected(self):
        changed = copy.deepcopy(self.envelope)
        changed["format"] = "other/0.1"
        with self.assertRaises(ReferenceEvidenceVerificationError):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed,),
                authority_ledger_id="bad-schema",
                ledger_created_by="test",
            )
        changed = copy.deepcopy(self.envelope)
        changed["integrity"]["algorithm"] = "md5"
        with self.assertRaises(ReferenceEvidenceVerificationError):
            build_verified_reference_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed,),
                authority_ledger_id="bad-algorithm",
                ledger_created_by="test",
            )

    def test_bundle_tampering_is_rejected_even_with_recomputed_outer_digest(self):
        changed = copy.deepcopy(self.bundle)
        changed["authority_receipts"][0]["authority_lineage_decision_id"] = "forged"
        core = {key: value for key, value in changed.items() if key != "bundle_digest"}
        changed["bundle_digest"] = digest(core)
        with self.assertRaises(ReferenceEvidenceVerificationError):
            validate_verified_reference_evidence_bundle(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
