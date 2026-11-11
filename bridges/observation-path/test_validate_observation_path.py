import json
import unittest
from pathlib import Path

from validate_observation_path import validate_path_record


HERE = Path(__file__).parent
SCHEMA = json.loads((HERE / "observation-path.schema.json").read_text(encoding="utf-8"))


class ObservationPathSchemaTests(unittest.TestCase):
    def test_example_record_passes_schema_and_lifecycle_validation(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        validate_path_record(record, SCHEMA)

    def test_status_must_match_final_event(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["status"] = "admitted"
        with self.assertRaises(ValueError):
            validate_path_record(record, SCHEMA)

    def test_terminal_flag_must_match_lifecycle_stage(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["terminal"] = False
        with self.assertRaises(ValueError):
            validate_path_record(record, SCHEMA)

    def test_invalid_transition_is_rejected(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["events"][3]["stage"] = "query_determined"
        with self.assertRaises(Exception):
            validate_path_record(record, SCHEMA)

    def test_authority_required_path_accepts_explicit_authorization_stage(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["intent"]["authority_required"] = True
        returned_index = next(i for i, event in enumerate(record["events"]) if event["stage"] == "returned")
        authorization = {
            "stage": "evidence_authorized",
            "actor": "consensus",
            "clock_value": None,
            "clock_domain": None,
            "evidence_ref": "consensus/decision.json",
            "details": {
                "decision_status": "AUTHORIZED",
                "policy_digest": "sha256:policy",
                "decision_digest": "sha256:decision",
                "quorum": 2,
                "strict": True,
                "observed_sources": ["source-a", "source-b"],
                "dissenting_sources": [],
                "missing_sources": [],
                "representative_source": "source-a",
            },
        }
        record["events"].insert(returned_index + 1, authorization)
        validate_path_record(record, SCHEMA)

    def test_application_required_implies_authority_and_requires_application_event(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["intent"]["authority_required"] = True
        record["intent"]["application_required"] = True
        returned_index = next(i for i, event in enumerate(record["events"]) if event["stage"] == "returned")
        record["events"].insert(returned_index + 1, {
            "stage": "evidence_authorized", "actor": "consensus",
            "clock_value": None, "clock_domain": None, "evidence_ref": "consensus/decision.json",
            "details": {
                "decision_status": "AUTHORIZED", "policy_digest": "sha256:policy",
                "decision_digest": "sha256:decision", "quorum": 2, "strict": True,
                "observed_sources": ["A", "B"], "dissenting_sources": [],
                "missing_sources": [], "representative_source": "A",
            },
        })
        interpreted_index = next(i for i, event in enumerate(record["events"]) if event["stage"] == "interpreted")
        record["events"].insert(interpreted_index, {
            "stage": "applied", "actor": "receiver-vm",
            "clock_value": None, "clock_domain": None, "evidence_ref": "vm/apply-receipt.json",
            "details": {
                "application_id": "event-01", "target_id": "vm-task-7",
                "projection_digest": "sha256:projection", "register_prefix": "gated",
            },
        })
        validate_path_record(record, SCHEMA)

    def test_application_requirement_without_authority_is_invalid(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["intent"]["application_required"] = True
        with self.assertRaises(Exception):
            validate_path_record(record, SCHEMA)

    def test_authority_refusal_is_terminal_and_schema_valid(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["events"] = record["events"][:4]
        record["events"].append({
            "stage": "evidence_refused", "actor": "consensus",
            "clock_value": None, "clock_domain": None, "evidence_ref": "consensus/refusal.json",
            "details": {
                "decision_status": "CONFLICT", "policy_digest": "sha256:policy",
                "decision_digest": "sha256:decision", "quorum": 2, "strict": True,
                "observed_sources": ["A", "B"], "dissenting_sources": ["B"],
                "missing_sources": [], "reason": "sources disagreed",
            },
        })
        record["status"] = "evidence_refused"
        record["terminal"] = True
        validate_path_record(record, SCHEMA)
    def test_authority_required_record_validates_distinct_consensus_stage(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["intent"]["authority_required"] = True
        returned_index = next(i for i, event in enumerate(record["events"]) if event["stage"] == "returned")
        record["events"].insert(returned_index + 1, {
            "stage": "evidence_authorized", "actor": "consensus",
            "clock_value": None, "clock_domain": None, "evidence_ref": "consensus/decision.json",
            "details": {
                "decision_status": "AUTHORIZED", "policy_digest": "sha256:policy",
                "decision_digest": "sha256:decision", "quorum": 2, "strict": True,
                "observed_sources": ["A", "B"], "dissenting_sources": [],
                "missing_sources": [], "representative_source": "A",
            },
        })
        validate_path_record(record, SCHEMA)

    def test_application_required_record_validates_application_event(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["intent"]["authority_required"] = True
        record["intent"]["application_required"] = True
        returned_index = next(i for i, event in enumerate(record["events"]) if event["stage"] == "returned")
        record["events"].insert(returned_index + 1, {
            "stage": "evidence_authorized", "actor": "consensus",
            "clock_value": None, "clock_domain": None, "evidence_ref": "consensus/decision.json",
            "details": {
                "decision_status": "AUTHORIZED", "policy_digest": "sha256:policy",
                "decision_digest": "sha256:decision", "quorum": 2, "strict": True,
                "observed_sources": ["A", "B"], "dissenting_sources": [],
                "missing_sources": [], "representative_source": "A",
            },
        })
        interpreted_index = next(i for i, event in enumerate(record["events"]) if event["stage"] == "interpreted")
        record["events"].insert(interpreted_index, {
            "stage": "applied", "actor": "receiver-vm",
            "clock_value": None, "clock_domain": None, "evidence_ref": "vm/apply-receipt.json",
            "details": {
                "application_id": "event-01", "target_id": "vm-task-7",
                "projection_digest": "sha256:projection", "register_prefix": "gated",
            },
        })
        validate_path_record(record, SCHEMA)

    def test_application_required_without_authority_is_rejected(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["intent"]["application_required"] = True
        with self.assertRaises(Exception):
            validate_path_record(record, SCHEMA)

    def test_evidence_refusal_validates_as_terminal_outcome(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["events"] = record["events"][:4]
        record["events"].append({
            "stage": "evidence_refused", "actor": "consensus",
            "clock_value": None, "clock_domain": None, "evidence_ref": "consensus/refusal.json",
            "details": {
                "decision_status": "CONFLICT", "policy_digest": "sha256:policy",
                "decision_digest": "sha256:decision", "quorum": 2, "strict": True,
                "observed_sources": ["A", "B"], "dissenting_sources": ["B"],
                "missing_sources": [], "reason": "source disagreement",
            },
        })
        record["status"] = "evidence_refused"
        record["terminal"] = True
        validate_path_record(record, SCHEMA)
    def test_authority_required_record_cannot_skip_consensus(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["intent"]["authority_required"] = True
        with self.assertRaises(ValueError):
            validate_path_record(record, SCHEMA)

    def test_application_required_record_cannot_skip_vm_application(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["intent"]["authority_required"] = True
        record["intent"]["application_required"] = True
        returned_index = next(i for i, event in enumerate(record["events"]) if event["stage"] == "returned")
        record["events"].insert(returned_index + 1, {
            "stage": "evidence_authorized", "actor": "consensus",
            "clock_value": None, "clock_domain": None, "evidence_ref": "consensus/decision.json",
            "details": {
                "decision_status": "AUTHORIZED", "policy_digest": "sha256:policy",
                "decision_digest": "sha256:decision", "quorum": 2, "strict": True,
                "observed_sources": ["A", "B"], "dissenting_sources": [],
                "missing_sources": [], "representative_source": "A",
            },
        })
        with self.assertRaises(ValueError):
            validate_path_record(record, SCHEMA)

if __name__ == "__main__":
    unittest.main()
