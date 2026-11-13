import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

import jsonschema

from observation_path import ObservationIntent, ObservationPath
from robust_policy_evidence_bundle import (
    EVENT_KIND,
    RobustPolicyEvidenceMismatch,
    RobustPolicyEvidenceVerificationError,
    build_verified_robust_policy_evidence_bundle,
    validate_verified_robust_policy_evidence_bundle,
)

# Reuse the small RIV-017 policy fixture and completed-path factory. The
# envelope below is rebuilt around each completed path's exact return binding.
from test_robust_policy_execution import adaptive_policy, complete_path


_RETURN_BINDINGS = (
    "policy_report_digest",
    "policy_state_digest",
    "policy_node_digest",
    "outcome_history_prefix",
    "sensor_id",
    "dimension",
    "measurement_cost",
    "observed_outcome",
)


def digest(value):
    return hashlib.sha256(json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def rebuild_path(snapshot):
    intent = snapshot["intent"]
    path = ObservationPath(ObservationIntent(
        attempt_id=snapshot["attempt_id"],
        candidate_name=intent["candidate_name"],
        query=intent["query"],
        hypothesis_set_digest=intent["hypothesis_set_digest"],
        estimated_cost=intent["estimated_cost"],
        plan_ref=intent["plan_ref"],
        authority_required=intent["authority_required"],
        application_required=intent["application_required"],
        sender_ack_required=intent["sender_ack_required"],
    ))
    for event in snapshot["events"][1:]:
        path.append(
            event["stage"],
            event["actor"],
            clock_value=event["clock_value"],
            clock_domain=event["clock_domain"],
            evidence_ref=event["evidence_ref"],
            details=event["details"],
        )
    return path


def make_envelope(path, *, sources=("source-a", "source-b"), dissenting=(),
                  observed_sources=None, representative_source=None,
                  logical_time=0):
    snapshot = path.to_dict()
    returned = next(
        item for item in snapshot["events"]
        if item["stage"] == "returned"
    )
    returned_details = returned["details"]
    attempt_id = snapshot["attempt_id"]
    sensor_id = returned_details["sensor_id"]
    outcome = returned_details["observed_outcome"]
    source_records = []
    for sequence, source in enumerate(sources, start=1):
        source_payload = {
            "attempt_id": attempt_id,
            "observation_id": attempt_id,
            "sensor_id": sensor_id,
            "dimension": returned_details["dimension"],
            "observed_outcome": outcome,
            "source": source,
            "sample_sequence": sequence,
        }
        source_records.append({
            "attempt_id": attempt_id,
            "observation_id": attempt_id,
            "event": {"kind": EVENT_KIND, "logical_time": logical_time},
            "source": source,
            "channel": f"robust-sensor:{sensor_id}",
            "sequence": sequence,
            "payload_digest": digest(source_payload),
            "payload_value": source_payload,
        })
    value = {
        key: returned_details[key]
        for key in _RETURN_BINDINGS
    }
    value["source_evidence_records"] = source_records
    payload_digest = digest(value)
    returned_details["payload_digest"] = payload_digest

    envelope_id = returned_details["encounter_id"]
    envelope = {
        "format": "in-formation.encounter/0.1",
        "id": envelope_id,
        "source": {
            "kind": "sensor",
            "name": sensor_id,
            "reference": sensor_id,
        },
        "payload": {
            "media_type": "application/json",
            "value": value,
        },
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-utf8-v1",
            "digest": payload_digest,
        },
    }
    observed = sorted(sources) if observed_sources is None else observed_sources
    dissent = sorted(dissenting)
    winners = sorted(set(observed) - set(dissent))
    if representative_source is None:
        representative_source = winners[0] if winners else "source-a"

    authority = next(
        item for item in snapshot["events"]
        if item["stage"] == "evidence_authorized"
    )
    authority["details"].update({
        "observed_sources": observed,
        "dissenting_sources": dissent,
        "missing_sources": sorted(set(["source-missing"]) - set(observed)),
        "representative_source": representative_source,
    })
    # Rebuilding through ObservationPath rechecks all lifecycle transitions.
    return rebuild_path(snapshot), envelope


def full_execution_and_envelopes(*, first_outcome="yes", second_outcome="yes"):
    report = adaptive_policy()
    first = complete_path(report, (), "robust-step-001", first_outcome)
    first, first_envelope = make_envelope(first, logical_time=0)
    second = complete_path(
        report,
        (first,),
        "robust-step-002",
        second_outcome,
    )
    second, second_envelope = make_envelope(second, logical_time=1)
    from robust_policy_execution import build_robust_policy_execution_record
    execution = build_robust_policy_execution_record(
        policy_report=report,
        observation_paths=(first, second),
    )
    return report, execution, (first_envelope, second_envelope)


class VerifiedRobustPolicyEvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.report, self.execution, self.envelopes = full_execution_and_envelopes()
        self.bundle = build_verified_robust_policy_evidence_bundle(
            policy_execution_record=self.execution,
            encounter_envelopes=self.envelopes,
            authority_ledger_id="robust-policy-evidence-ledger-test",
            ledger_created_by="riv018-test-suite",
        )

    def test_inline_envelopes_and_per_source_evidence_reconstruct_authority_lineage(self):
        self.assertEqual(
            self.bundle["verification_status"],
            "robust_policy_envelopes_verified_and_authority_lineage_reconstructed",
        )
        summaries = self.bundle["encounter_envelope_summaries"]
        self.assertEqual(len(summaries), 2)
        self.assertTrue(all(row["integrity_status"] == "VERIFIED" for row in summaries))
        self.assertEqual(
            [row["source_ids"] for row in summaries],
            [["source-a", "source-b"], ["source-a", "source-b"]],
        )
        self.assertEqual(len(self.bundle["authority_ledger"]["entries"]), 3)
        self.assertEqual(len(self.bundle["authority_receipts"]), 2)
        self.assertTrue(all(
            row["authority_lineage_receipt"]["decision_status"] == "AUTHORIZED"
            for row in self.bundle["authority_receipts"]
        ))
        self.assertEqual(
            validate_verified_robust_policy_evidence_bundle(self.bundle),
            self.bundle,
        )

    def test_payload_tampering_without_outer_digest_update_fails_envelope_integrity(self):
        changed = copy.deepcopy(self.envelopes[0])
        changed["payload"]["value"]["observed_outcome"] = "no"
        with self.assertRaises(RobustPolicyEvidenceVerificationError):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed, self.envelopes[1]),
                authority_ledger_id="tampered-payload",
                ledger_created_by="test",
            )

    def test_recomputed_envelope_digest_does_not_hide_path_mismatch(self):
        changed = copy.deepcopy(self.envelopes[0])
        changed["payload"]["value"]["observed_outcome"] = "no"
        changed["integrity"]["digest"] = digest(changed["payload"]["value"])
        with self.assertRaises(RobustPolicyEvidenceMismatch):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed, self.envelopes[1]),
                authority_ledger_id="path-mismatch",
                ledger_created_by="test",
            )

    def test_source_payload_digest_is_verified_independently(self):
        changed = copy.deepcopy(self.envelopes[0])
        changed["payload"]["value"]["source_evidence_records"][0][
            "payload_value"
        ]["observed_outcome"] = "forged"
        changed["integrity"]["digest"] = digest(changed["payload"]["value"])
        with self.assertRaises(RobustPolicyEvidenceMismatch):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed, self.envelopes[1]),
                authority_ledger_id="source-payload-mismatch",
                ledger_created_by="test",
            )

    def test_source_records_must_equal_authorized_observed_source_set(self):
        first_path = complete_path(self.report, (), "mismatch-source-set", "yes")
        first_path, envelope = make_envelope(
            first_path,
            sources=("source-a",),
            observed_sources=["source-a", "source-b"],
            logical_time=0,
        )
        from robust_policy_execution import build_robust_policy_execution_record
        execution = build_robust_policy_execution_record(
            policy_report=self.report,
            observation_paths=(first_path,),
        )
        with self.assertRaises(RobustPolicyEvidenceMismatch):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=execution,
                encounter_envelopes=(envelope,),
                authority_ledger_id="wrong-source-set",
                ledger_created_by="test",
            )

    def test_representative_must_be_in_the_non_dissenting_quorum(self):
        path = complete_path(self.report, (), "dissenting-representative", "yes")
        path, envelope = make_envelope(
            path,
            sources=("source-a", "source-b"),
            dissenting=("source-a", "source-b"),
            representative_source="source-a",
            logical_time=0,
        )
        from robust_policy_execution import build_robust_policy_execution_record
        execution = build_robust_policy_execution_record(
            policy_report=self.report,
            observation_paths=(path,),
        )
        with self.assertRaises(RobustPolicyEvidenceMismatch):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=execution,
                encounter_envelopes=(envelope,),
                authority_ledger_id="bad-quorum",
                ledger_created_by="test",
            )

    def test_envelope_identifier_must_match_the_returned_encounter(self):
        changed = copy.deepcopy(self.envelopes[0])
        changed["id"] = "another-encounter"
        with self.assertRaises(RobustPolicyEvidenceMismatch):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed, self.envelopes[1]),
                authority_ledger_id="wrong-envelope-id",
                ledger_created_by="test",
            )

    def test_exactly_one_inline_envelope_is_required_per_observation_path(self):
        with self.assertRaises(RobustPolicyEvidenceVerificationError):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(self.envelopes[0],),
                authority_ledger_id="missing-envelope",
                ledger_created_by="test",
            )
        referenced = copy.deepcopy(self.envelopes[0])
        referenced["payload"] = {"reference": "artifact://external-sensor-payload"}
        with self.assertRaises(RobustPolicyEvidenceVerificationError):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(referenced, self.envelopes[1]),
                authority_ledger_id="external-reference",
                ledger_created_by="test",
            )

    def test_source_records_must_bind_to_the_bundle_logical_event(self):
        changed = copy.deepcopy(self.envelopes[0])
        changed["payload"]["value"]["source_evidence_records"][0]["event"]["logical_time"] = 99
        changed["integrity"]["digest"] = digest(changed["payload"]["value"])
        with self.assertRaises(RobustPolicyEvidenceMismatch):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed, self.envelopes[1]),
                authority_ledger_id="wrong-logical-time",
                ledger_created_by="test",
            )

    def test_bad_schema_or_integrity_algorithm_is_rejected(self):
        changed = copy.deepcopy(self.envelopes[0])
        changed["format"] = "other/0.1"
        with self.assertRaises(RobustPolicyEvidenceVerificationError):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed, self.envelopes[1]),
                authority_ledger_id="bad-envelope-format",
                ledger_created_by="test",
            )
        changed = copy.deepcopy(self.envelopes[0])
        changed["integrity"]["algorithm"] = "md5"
        with self.assertRaises(RobustPolicyEvidenceVerificationError):
            build_verified_robust_policy_evidence_bundle(
                policy_execution_record=self.execution,
                encounter_envelopes=(changed, self.envelopes[1]),
                authority_ledger_id="bad-envelope-algorithm",
                ledger_created_by="test",
            )

    def test_outer_bundle_tampering_is_rejected_even_when_redigested(self):
        changed = copy.deepcopy(self.bundle)
        changed["authority_receipts"][0]["authority_lineage_decision_id"] = "forged"
        core = {
            key: value for key, value in changed.items()
            if key != "bundle_digest"
        }
        changed["bundle_digest"] = digest(core)
        with self.assertRaises(RobustPolicyEvidenceVerificationError):
            validate_verified_robust_policy_evidence_bundle(changed)

    def test_schema_accepts_reconstructed_verified_bundle(self):
        schema_path = Path(__file__).with_name(
            "robust-policy-evidence-bundle.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(self.bundle, schema)


if __name__ == "__main__":
    unittest.main(verbosity=2)
