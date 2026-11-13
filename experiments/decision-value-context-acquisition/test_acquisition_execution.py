import copy
import hashlib
import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path

import jsonschema

_ROOT = Path(__file__).resolve().parents[2]
_DECISION_VALUE = Path(__file__).resolve().parent
_OBSERVATION_PATH = _ROOT / "bridges" / "observation-path"
for item in (_OBSERVATION_PATH, _DECISION_VALUE):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from decision_value_acquisition import build_report
from acquisition_execution import (
    DecisionValueMeasurementError,
    DecisionValueMeasurementMismatch,
    build_acquisition_measurement_record,
    new_acquisition_observation_path,
    validate_acquisition_measurement_record,
)
from observation_path import ObservationIntent, ObservationPath
from test_decision_value_acquisition import fixture as decision_value_fixture


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_digest(value):
    return sha(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ))


def base_report():
    belief, candidates, _ = decision_value_fixture()
    return build_report(
        joint_belief=belief,
        candidate_sensors=candidates,
    )


class AcquisitionExecutionTests(unittest.TestCase):
    def setUp(self):
        self.report = base_report()
        self.selected = next(
            item for item in self.report["candidate_sensor_models"]
            if item["sensor_id"] == self.report["selection"]["selected_sensor_id"]
        )

    def make_path(self, *, outcome="good", authorize=True, attempt_id="context-read-001",
                  sensor_id=None, dimension=None, report=None):
        report = report or self.report
        selected = next(
            item for item in report["candidate_sensor_models"]
            if item["sensor_id"] == report["selection"]["selected_sensor_id"]
        )
        path = new_acquisition_observation_path(
            decision_value_report=report,
            attempt_id=attempt_id,
            query="measure the selected operating context",
        )
        path.append(
            "dispatched",
            "context-sensor-agent",
            evidence_ref="dispatch://context-read-001",
            details={"request_id": attempt_id},
        )
        path.append(
            "admitted",
            "context-receiver",
            evidence_ref="admission://context-read-001",
            details={"receiver_id": "receiver-context-01"},
        )
        path.append(
            "returned",
            "context-receiver",
            evidence_ref="encounter://context-read-001",
            details={
                "encounter_id": "context-encounter-001",
                "payload_digest": sha("context-reading-payload"),
                "canonicalization": "canonical-json-v1",
                "sensor_id": sensor_id or selected["sensor_id"],
                "dimension": dimension or selected["dimension"],
                "decision_value_report_digest": report["report_digest"],
                "observed_outcome": outcome,
            },
        )
        if authorize:
            path.append(
                "evidence_authorized",
                "ecpu-consensus",
                evidence_ref="consensus://context-read-001",
                details={
                    "decision_status": "AUTHORIZED",
                    "policy_digest": "policy-sha256",
                    "decision_digest": "decision-sha256",
                    "quorum": 2,
                    "strict": True,
                    "observed_sources": ["sensor-a", "sensor-b"],
                    "dissenting_sources": [],
                    "missing_sources": [],
                    "representative_source": "sensor-a",
                },
            )
            path.append(
                "interpreted",
                "context-interpreter",
                evidence_ref="interpretation://context-read-001",
                details={
                    "method": "exact-decision-value-context-outcome-v1",
                    "sensor_id": sensor_id or selected["sensor_id"],
                    "dimension": dimension or selected["dimension"],
                    "decision_value_report_digest": report["report_digest"],
                    "observed_outcome": outcome,
                },
            )
        return path

    def build_record(self, path=None, **kwargs):
        return build_acquisition_measurement_record(
            decision_value_report=self.report,
            observation_path=path or self.make_path(**kwargs),
        )

    def test_plan_creates_a_planned_authority_gated_observation_path(self):
        path = new_acquisition_observation_path(
            decision_value_report=self.report,
            attempt_id="planned-attempt",
        )
        self.assertEqual(path.status, "planned")
        self.assertFalse(path.terminal)
        self.assertTrue(path.intent.authority_required)
        self.assertFalse(path.intent.application_required)
        self.assertFalse(path.intent.sender_ack_required)
        self.assertEqual(
            path.intent.candidate_name,
            f"decision-value-context:{self.selected['sensor_id']}",
        )
        self.assertEqual(
            path.intent.hypothesis_set_digest,
            self.report["report_digest"],
        )
        self.assertEqual(
            path.intent.plan_ref,
            "urn:sha256:" + self.report["report_digest"],
        )
        self.assertEqual(
            path.intent.estimated_cost,
            float(Fraction(**self.selected["cost"])),
        )

    def test_authorized_outcome_creates_exact_immutable_joint_posterior_revision(self):
        path = self.make_path(outcome="good")
        record = self.build_record(path=path)
        self.assertEqual(record["measurement_status"], "interpreted_authorized_observation")
        self.assertEqual(record["belief_effect"], "new_immutable_joint_posterior_revision")
        self.assertEqual(record["ground_effect"], "none")
        self.assertEqual(record["model_effect"], "none")
        self.assertEqual(record["observed_outcome"], "good")
        self.assertEqual(record["sensor_id"], self.selected["sensor_id"])
        self.assertEqual(record["dimension"], self.selected["dimension"])
        posterior = record["updated_joint_belief"]["joint_posterior"]
        self.assertEqual(
            sum((Fraction(**item["probability"]) for item in posterior), Fraction(0)),
            Fraction(1),
        )
        self.assertEqual(
            record["updated_joint_belief"]["source_report_digest"],
            self.report["report_digest"],
        )
        self.assertEqual(
            record["updated_joint_belief"]["source_ref"],
            "urn:sha256:" + record["measurement_manifest_digest"],
        )
        self.assertEqual(
            record["observation_path_digest"],
            record["measurement_manifest"]["observation_path_digest"],
        )
        self.assertEqual(
            record["measurement_manifest"]["authority_decision_status"],
            "AUTHORIZED",
        )
        self.assertEqual(
            record["measurement_manifest"]["observed_outcome"],
            "good",
        )
        self.assertIsInstance(
            record["realized_bayes_risk_change_post_minus_pre"],
            dict,
        )
        self.assertEqual(
            validate_acquisition_measurement_record(record),
            record,
        )
        # The original report's joint belief is retained unchanged.
        self.assertEqual(
            record["decision_value_report"]["joint_belief"],
            self.report["joint_belief"],
        )

    def test_out_of_set_outcome_is_rejected_without_posterior_revision(self):
        path = self.make_path(outcome="unlisted-context")
        with self.assertRaises(DecisionValueMeasurementMismatch):
            self.build_record(path=path)
        self.assertEqual(self.report["joint_belief"], base_report()["joint_belief"])

    def test_declared_but_impossible_outcome_is_rejected(self):
        from decision_value_acquisition import build_joint_belief_document

        belief = build_joint_belief_document(
            joint_posterior=(
                {"hypothesis": "A", "context_state": "good", "probability": "1/2"},
                {"hypothesis": "B", "context_state": "good", "probability": "1/2"},
            ),
            source_ref="artifact://impossible-outcome-fixture",
            source_report_digest=sha("upstream-impossible-outcome"),
        )
        candidate = {
            "sensor_id": "deterministic-context-reader",
            "dimension": "regime",
            "cost": Fraction(1),
            "outcomes": (
                {
                    "outcome": "impossible",
                    "likelihoods": (
                        {"hypothesis": "A", "context_state": "good", "probability": 0},
                        {"hypothesis": "B", "context_state": "good", "probability": 0},
                    ),
                },
                {
                    "outcome": "possible",
                    "likelihoods": (
                        {"hypothesis": "A", "context_state": "good", "probability": 1},
                        {"hypothesis": "B", "context_state": "good", "probability": 1},
                    ),
                },
            ),
        }
        report = build_report(joint_belief=belief, candidate_sensors=(candidate,))
        selected = new_acquisition_observation_path(
            decision_value_report=report,
            attempt_id="impossible-read",
        )
        selected.append("dispatched", "sensor", evidence_ref="dispatch://impossible")
        selected.append("admitted", "receiver", evidence_ref="admission://impossible")
        selected.append(
            "returned", "receiver",
            evidence_ref="encounter://impossible",
            details={
                "encounter_id": "encounter-impossible",
                "payload_digest": sha("impossible"),
                "canonicalization": "canonical-json-v1",
                "sensor_id": "deterministic-context-reader",
                "dimension": "regime",
                "decision_value_report_digest": report["report_digest"],
                "observed_outcome": "impossible",
            },
        )
        selected.append(
            "evidence_authorized", "consensus",
            evidence_ref="consensus://impossible",
            details={
                "decision_status": "AUTHORIZED",
                "policy_digest": "policy",
                "decision_digest": "decision",
                "quorum": 1,
                "strict": True,
                "observed_sources": ["sensor-a"],
                "dissenting_sources": [],
                "missing_sources": [],
                "representative_source": "sensor-a",
            },
        )
        selected.append(
            "interpreted", "interpreter",
            evidence_ref="interpretation://impossible",
            details={
                "method": "exact-decision-value-context-outcome-v1",
                "sensor_id": "deterministic-context-reader",
                "dimension": "regime",
                "decision_value_report_digest": report["report_digest"],
                "observed_outcome": "impossible",
            },
        )
        with self.assertRaises(DecisionValueMeasurementMismatch):
            build_acquisition_measurement_record(
                decision_value_report=report,
                observation_path=selected,
            )

    def test_authority_is_required_before_interpretation(self):
        path = self.make_path(authorize=False)
        self.assertEqual(path.status, "returned")
        with self.assertRaises(ValueError):
            path.append(
                "interpreted",
                "interpreter",
                evidence_ref="interpretation://too-early",
                details={
                    "method": "exact-decision-value-context-outcome-v1",
                },
            )
        with self.assertRaises(DecisionValueMeasurementError):
            self.build_record(path=path)

    def test_wrong_sensor_or_dimension_is_rejected(self):
        with self.assertRaises(DecisionValueMeasurementError):
            self.build_record(path=self.make_path(sensor_id="other-sensor"))
        with self.assertRaises(DecisionValueMeasurementError):
            self.build_record(path=self.make_path(dimension="other-dimension"))

    def test_return_and_interpretation_must_agree_exactly_on_json_type(self):
        path = self.make_path(outcome="good")
        final = path.events[-1]
        details = final.details
        details["observed_outcome"] = True
        # Build a second legal path with a Boolean value on return and a
        # mismatching interpretation; the mismatch is rejected at ingestion.
        selected = new_acquisition_observation_path(
            decision_value_report=self.report,
            attempt_id="typed-mismatch",
        )
        selected.append("dispatched", "sensor", evidence_ref="dispatch://typed")
        selected.append("admitted", "receiver", evidence_ref="admission://typed")
        selected.append(
            "returned", "receiver",
            evidence_ref="encounter://typed",
            details={
                "encounter_id": "typed-encounter",
                "payload_digest": sha("typed"),
                "canonicalization": "canonical-json-v1",
                "sensor_id": self.selected["sensor_id"],
                "dimension": self.selected["dimension"],
                "decision_value_report_digest": self.report["report_digest"],
                "observed_outcome": True,
            },
        )
        selected.append(
            "evidence_authorized", "consensus",
            evidence_ref="consensus://typed",
            details={
                "decision_status": "AUTHORIZED",
                "policy_digest": "policy",
                "decision_digest": "decision",
                "quorum": 1,
                "strict": True,
                "observed_sources": ["sensor-a"],
                "dissenting_sources": [],
                "missing_sources": [],
                "representative_source": "sensor-a",
            },
        )
        selected.append(
            "interpreted", "interpreter",
            evidence_ref="interpretation://typed",
            details={
                "method": "exact-decision-value-context-outcome-v1",
                "sensor_id": self.selected["sensor_id"],
                "dimension": self.selected["dimension"],
                "decision_value_report_digest": self.report["report_digest"],
                "observed_outcome": "good",
            },
        )
        with self.assertRaises(DecisionValueMeasurementError):
            self.build_record(path=selected)

    def test_record_reconstruction_rejects_tampered_path_even_with_recomputed_outer_digest(self):
        record = self.build_record(outcome="degraded")
        changed = copy.deepcopy(record)
        changed["observation_path"]["events"][1]["evidence_ref"] = "dispatch://forged"
        core = {key: value for key, value in changed.items() if key != "record_digest"}
        changed["record_digest"] = canonical_digest(core)
        with self.assertRaises(DecisionValueMeasurementError):
            validate_acquisition_measurement_record(changed)

    def test_schema_accepts_valid_measurement_record(self):
        record = self.build_record(outcome="good")
        schema_path = Path(__file__).with_name(
            "decision-value-measurement.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(record, schema)


if __name__ == "__main__":
    unittest.main(verbosity=2)
