import copy
import hashlib
import json
import unittest
from fractions import Fraction
from pathlib import Path

import jsonschema
import vgi

from test_transition_context import assignment, make_model, make_record
from transition_context import (
    build_transition_context_analysis,
    validate_transition_context_analysis,
)
from context_attention import ContextProbeMethod, build_context_attention_plan
from context_measurement import (
    ContextMeasurementError,
    ContextMeasurementMismatch,
    build_context_measurement_record,
    new_context_measurement_path,
    validate_context_measurement_record,
)


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_digest(value):
    return sha(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ))


class ContextMeasurementEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.model = make_model()
        self.records = [
            make_record(self.model, attempt_id="a", outcome="ready", next_state="s1"),
            make_record(self.model, attempt_id="b", outcome="other", next_state="s2"),
        ]
        self.assignments = [
            assignment(
                self.records[0],
                {
                    "host": {"status": "observed", "value": "machine-a"},
                    "region": {"status": "unknown", "reason": "not collected"},
                },
                source_ref="artifact://prior-context/a",
            ),
            assignment(
                self.records[1],
                {"region": {"status": "unknown", "reason": "not collected"}},
            ),
        ]
        self.analysis = build_transition_context_analysis(
            model_document=self.model,
            conformance_records=self.records,
            context_assignments=self.assignments,
        )
        self.method = ContextProbeMethod(
            "capture-region",
            "region",
            ("east", "west"),
            cost=Fraction(3, 2),
            source_ref="protocol://capture-region-v1",
        )
        self.policy = self.build_policy(self.analysis)

    def build_policy(self, analysis):
        return build_context_attention_plan(
            context_analysis=analysis,
            model_document=self.model,
            probe_id="inspect",
            current_state="s0",
            methods=(self.method,),
            vgi_api=vgi,
            max_probes=2,
        )

    def make_path(self, *, value="east", attempt_id=None, report=None,
                  method_id=None, dimension=None, authorize=True):
        report = report or self.policy
        selected = report["next_measurement"]
        path = new_context_measurement_path(
            context_analysis=self.analysis,
            policy_report=report,
            model_document=self.model,
            vgi_api=vgi,
            query="capture the selected context value",
        )
        intent = path.intent
        if attempt_id is not None or method_id is not None:
            from observation_path import ObservationIntent, ObservationPath
            path = ObservationPath(ObservationIntent(
                attempt_id=attempt_id or intent.attempt_id,
                candidate_name=f"context-capture:{method_id or selected['method_id']}",
                query=intent.query,
                hypothesis_set_digest=intent.hypothesis_set_digest,
                estimated_cost=intent.estimated_cost,
                plan_ref=intent.plan_ref,
                authority_required=True,
            ))
        path.append(
            "dispatched", "context-capture-agent",
            evidence_ref="dispatch://context-attempt-a",
            details={
                "method_id": method_id or selected["method_id"],
                "dimension": dimension or selected["dimension"],
                "context_attention_report_digest": report["report_digest"],
            },
        )
        path.append(
            "admitted", "context-receiver",
            evidence_ref="admission://context-attempt-a",
            details={"receiver": "context-observation-boundary"},
        )
        path.append(
            "returned", "context-receiver",
            evidence_ref="encounter://context-attempt-a",
            details={
                "encounter_id": "context-encounter-a",
                "payload_digest": sha("context-payload-a"),
                "canonicalization": "canonical-json-v1",
                "method_id": method_id or selected["method_id"],
                "dimension": dimension or selected["dimension"],
                "context_attention_report_digest": report["report_digest"],
                "context_value": value,
            },
        )
        if authorize:
            path.append(
                "evidence_authorized", "ecpu-consensus",
                evidence_ref="consensus://context-attempt-a",
                details={
                    "decision_status": "AUTHORIZED",
                    "policy_digest": "policy-context-sha256",
                    "decision_digest": "decision-context-sha256",
                    "quorum": 2,
                    "strict": True,
                    "observed_sources": ["sensor-a", "sensor-b"],
                    "dissenting_sources": [],
                    "missing_sources": [],
                    "representative_source": "sensor-a",
                },
            )
        path.append(
            "interpreted", "context-interpreter",
            evidence_ref="interpretation://context-attempt-a",
            details={
                "method": "exact-context-scalar-v1",
                "method_id": method_id or selected["method_id"],
                "dimension": dimension or selected["dimension"],
                "context_attention_report_digest": report["report_digest"],
                "context_value": value,
            },
        ) if authorize else None
        return path

    def build_record(self, **kwargs):
        path = kwargs.pop("path", None) or self.make_path(**kwargs)
        return build_context_measurement_record(
            context_analysis=self.analysis,
            policy_report=self.policy,
            model_document=self.model,
            observation_path=path,
            vgi_api=vgi,
        )

    def test_authorized_measurement_creates_new_assignment_and_analysis(self):
        path = self.make_path(value="east")
        record = self.build_record(path=path)
        self.assertEqual(record["execution_status"],
                         "interpreted_authorized_context_measurement")
        self.assertEqual(record["context_analysis_effect"],
                         "new_immutable_analysis_revision")
        self.assertEqual(record["ground_effect"], "none")
        self.assertEqual(record["model_effect"], "none")
        self.assertEqual(record["attempt_id"], "a")
        self.assertEqual(record["observed_value"], "east")
        self.assertEqual(record["context_assignment"]["dimensions"]["region"], {
            "status": "observed", "value": "east"
        })
        self.assertEqual(record["context_assignment"]["dimensions"]["host"], {
            "status": "observed", "value": "machine-a"
        })
        self.assertEqual(
            record["prior_context_assignment"]["assignment_digest"],
            self.assignments[0]["assignment_digest"],
        )
        manifest = record["measurement_manifest"]
        self.assertEqual(manifest["prior_assignment_digest"],
                         self.assignments[0]["assignment_digest"])
        self.assertEqual(manifest["prior_source_ref"], "artifact://prior-context/a")
        self.assertEqual(
            record["context_assignment"]["source_ref"],
            "urn:sha256:" + record["measurement_manifest_digest"],
        )
        self.assertEqual(
            record["observation_path_digest"],
            record["measurement_manifest"]["observation_path_digest"],
        )
        # The original evidence and assignment remain unchanged.
        self.assertEqual(
            self.analysis["source_context_assignments"][0]["dimensions"]["region"],
            {"status": "unknown", "reason": "not collected"},
        )
        updated = validate_transition_context_analysis(
            record["updated_context_analysis"], model_document=self.model
        )
        updated_assignment = next(
            item for item in updated["source_context_assignments"]
            if item["attempt_id"] == "a"
        )
        self.assertEqual(updated_assignment, record["context_assignment"])

    def test_updated_analysis_replans_next_unknown_attempt(self):
        record = self.build_record(path=self.make_path(value="east"))
        updated_analysis = record["updated_context_analysis"]
        next_policy = self.build_policy(updated_analysis)
        self.assertEqual(next_policy["source_context_analysis_digest"],
                         updated_analysis["analysis_digest"])
        self.assertEqual(next_policy["next_measurement"]["attempt_id"], "b")
        self.assertEqual(next_policy["next_measurement"]["dimension"], "region")

    def test_record_reconstructs_path_and_rejects_tampering(self):
        record = self.build_record(path=self.make_path(value="west"))
        self.assertEqual(
            validate_context_measurement_record(
                record,
                context_analysis=self.analysis,
                policy_report=self.policy,
                model_document=self.model,
                vgi_api=vgi,
            ),
            record,
        )
        changed = copy.deepcopy(record)
        changed["observation_path"]["events"][1]["evidence_ref"] = "dispatch://forged"
        changed["record_digest"] = canonical_digest({
            key: value for key, value in changed.items() if key != "record_digest"
        })
        with self.assertRaises(ContextMeasurementError):
            validate_context_measurement_record(
                changed,
                context_analysis=self.analysis,
                policy_report=self.policy,
                model_document=self.model,
                vgi_api=vgi,
            )

    def test_out_of_set_value_is_rejected_without_context_revision(self):
        with self.assertRaises(ContextMeasurementMismatch):
            self.build_record(path=self.make_path(value="north"))
        self.assertEqual(
            self.analysis["source_context_assignments"][0]["dimensions"]["region"],
            {"status": "unknown", "reason": "not collected"},
        )

    def test_wrong_attempt_method_or_dimension_is_rejected(self):
        selected = self.policy["next_measurement"]
        with self.assertRaises(ContextMeasurementError):
            self.build_record(path=self.make_path(attempt_id="b"))
        with self.assertRaises(ContextMeasurementError):
            self.build_record(path=self.make_path(method_id="capture-host"))
        with self.assertRaises(ContextMeasurementError):
            self.build_record(path=self.make_path(dimension="timezone"))

    def test_context_measurement_requires_authorized_evidence_before_interpretation(self):
        path = self.make_path(authorize=False)
        # Without the authority event the existing ObservationPath rejects an
        # interpreted event, so this helper returns a deliberately unadvanced path.
        self.assertEqual(path.status, "returned")
        with self.assertRaises(ContextMeasurementError):
            self.build_record(path=path)

    def test_stale_policy_cannot_be_used_after_source_analysis_changes(self):
        wrong = copy.deepcopy(self.analysis)
        wrong["analysis_digest"] = sha("other-analysis")
        with self.assertRaises(ContextMeasurementError):
            new_context_measurement_path(
                context_analysis=wrong,
                policy_report=self.policy,
                model_document=self.model,
                vgi_api=vgi,
            )

    def test_new_assignment_is_bound_to_complete_measurement_manifest(self):
        record = self.build_record(path=self.make_path(value="west"))
        manifest = dict(record["measurement_manifest"])
        digest = manifest.pop("measurement_manifest_digest")
        self.assertEqual(digest, canonical_digest(manifest))
        self.assertEqual(
            record["context_assignment"]["source_ref"],
            "urn:sha256:" + digest,
        )
        self.assertEqual(
            record["observation_path"]["events"][-1]["details"]["context_attention_report_digest"],
            self.policy["report_digest"],
        )

    def test_published_schema_accepts_context_measurement_record(self):
        record = self.build_record(path=self.make_path(value="east"))
        schema_path = Path(__file__).with_name(
            "context-measurement-evidence.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(record, schema)


if __name__ == "__main__":
    unittest.main(verbosity=2)
