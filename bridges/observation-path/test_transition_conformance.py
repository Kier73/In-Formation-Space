import hashlib
import unittest

from transition_conformance import (
    TransitionConformanceError,
    TransitionModelRevisionLedger,
    build_transition_conformance_record,
    validate_transition_conformance_record,
)
from intervention_attention import build_intervention_attention_frontier
from observation_path import ObservationIntent, ObservationPath
from operation_spans import OperationSpanRecorder


def sha(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_model():
    return build_intervention_attention_frontier(
        world_states=("s0", "s1", "s2"),
        hypotheses=(
            {"hypothesis_id": "initial-yes", "initial_state": "s0",
             "query_value": True, "prior": "1/2"},
            {"hypothesis_id": "initial-no", "initial_state": "s1",
             "query_value": False, "prior": "1/2"},
        ),
        probes=(
            {
                "probe_id": "inspect",
                "observation_cost": 1,
                "transitions": {
                    "s0": {"outcome": "yes", "next_state": "s1", "intervention_cost": 2},
                    "s1": {"outcome": "no", "next_state": "s1", "intervention_cost": 0},
                    "s2": {"outcome": "unknown", "next_state": "s2", "intervention_cost": 1},
                },
            },
        ),
        max_depth=1,
    )


def make_path(*, observed_outcome="yes", attempt_id="attempt-001",
              authority_required=False, application_required=False,
              sender_ack_required=False, include_admission=True):
    path = ObservationPath(ObservationIntent(
        attempt_id=attempt_id,
        candidate_name="inspect",
        query="was the initial hypothesis true?",
        hypothesis_set_digest=sha("hypotheses"),
        estimated_cost=1.0,
        plan_ref="artifact://trial08/plan-001",
        authority_required=authority_required,
        application_required=application_required,
        sender_ack_required=sender_ack_required,
    ))
    path.append("dispatched", "host", evidence_ref="dispatch://001")
    if include_admission:
        path.append("admitted", "receiver", evidence_ref="admission://001")
    if include_admission:
        path.append(
            "returned",
            "sensor",
            evidence_ref="encounter://001",
            details={
                "encounter_id": "encounter-001",
                "payload_digest": sha("payload-001"),
                "canonicalization": "canonical-json-v1",
            },
        )
        if authority_required:
            path.append(
                "evidence_authorized",
                "authority",
                evidence_ref="decision://001",
                details={
                    "decision_status": "AUTHORIZED",
                    "policy_digest": sha("policy"),
                    "decision_digest": sha("decision"),
                    "quorum": 1,
                    "strict": True,
                    "observed_sources": ["source-a"],
                    "dissenting_sources": [],
                    "missing_sources": [],
                    "representative_source": "source-a",
                },
            )
        if application_required:
            path.append(
                "applied",
                "receiver",
                evidence_ref="application://001",
                details={
                    "application_id": "application-001",
                    "target_id": "target-001",
                    "projection_digest": sha("projection"),
                    "register_prefix": "r0",
                },
            )
        if sender_ack_required:
            path.append(
                "sender_acknowledged",
                "sender",
                evidence_ref="ack://001",
                details={
                    "event_kind": "probe",
                    "logical_time": 1,
                    "sources": ["source-a"],
                    "acknowledged_sequences": [
                        {"source": "source-a", "channel": "probe", "sequence": 1}
                    ],
                    "expected_event_sequences": [
                        {"source": "source-a", "channel": "probe", "sequence": 1}
                    ],
                    "missing_event_sequences": [],
                    "ack_digest": sha("ack"),
                },
            )
        path.append(
            "interpreted",
            "interpreter",
            evidence_ref="interpretation://001",
            details={"method": "exact-test-interpreter", "interpreted_value": observed_outcome},
        )
    return path


def build_record(model, path, *, observed_outcome="yes", observed_next_state="s1",
                 conformance_id="conformance-001", operation_span=None):
    return build_transition_conformance_record(
        conformance_id=conformance_id,
        model_document=model,
        model_ref="artifact://trial08/model-001",
        observation_path=path.to_dict(),
        probe_id="inspect",
        current_state="s0",
        observed_outcome=observed_outcome,
        observed_next_state=observed_next_state,
        before_state_ref="state://before-001",
        before_state_digest=sha("before-state"),
        after_state_ref=None if observed_next_state is None else "state://after-001",
        after_state_digest=None if observed_next_state is None else sha("after-state"),
        operation_span=operation_span,
    )


class TransitionConformanceTests(unittest.TestCase):
    def setUp(self):
        self.model = make_model()
        self.path = make_path()

    def test_matching_outcome_and_state_are_full_conformance(self):
        record = build_record(self.model, self.path)
        self.assertEqual(record["conformance_status"], "matched")
        self.assertEqual(record["predicted_transition"]["outcome"], "yes")
        self.assertEqual(record["predicted_transition"]["next_state"], "s1")
        self.assertEqual(record["observed_transition"]["next_state"], "s1")
        self.assertEqual(
            record["predicted_transition"]["intervention_cost"],
            {"numerator": 2, "denominator": 1},
        )
        self.assertEqual(
            validate_transition_conformance_record(
                record, model_document=self.model, observation_path=self.path.to_dict()
            ),
            record,
        )

    def test_outcome_mismatch_and_next_state_mismatch_are_distinguished(self):
        outcome_only = build_record(
            self.model, make_path(observed_outcome="unexpected"), observed_outcome="unexpected", observed_next_state="s1"
        )
        self.assertEqual(outcome_only["conformance_status"], "outcome_mismatch")
        state_only = build_record(
            self.model, self.path, observed_outcome="yes", observed_next_state="s2"
        )
        self.assertEqual(state_only["conformance_status"], "next_state_mismatch")
        both = build_record(
            self.model, make_path(observed_outcome="unexpected"), observed_outcome="unexpected", observed_next_state="s2"
        )
        self.assertEqual(both["conformance_status"], "transition_mismatch")

    def test_outcome_only_is_not_misreported_as_transition_conformance(self):
        record = build_record(self.model, self.path, observed_next_state=None)
        self.assertEqual(record["conformance_status"], "outcome_only_match")
        self.assertIsNone(record["observed_transition"]["next_state"])
        self.assertIsNone(record["state_evidence"]["after"])
        ledger = TransitionModelRevisionLedger(self.model)
        with self.assertRaises(TransitionConformanceError):
            ledger.propose_transition("candidate-001", record, proposer="test")

    def test_interpreted_value_must_match_the_observed_value_supplied_to_builder(self):
        path = make_path(observed_outcome="yes")
        with self.assertRaises(TransitionConformanceError):
            build_record(self.model, path, observed_outcome="not-the-interpreted-value")

    def test_admission_is_required_and_timeout_cannot_become_transition_evidence(self):
        path = make_path(include_admission=False)
        with self.assertRaises(TransitionConformanceError):
            build_record(self.model, path)

    def test_authority_application_and_ack_gates_must_precede_interpretation(self):
        path = make_path(
            authority_required=True,
            application_required=True,
            sender_ack_required=True,
        )
        record = build_record(self.model, path)
        self.assertEqual(record["conformance_status"], "matched")
        stages = [event["stage"] for event in path.to_dict()["events"]]
        self.assertLess(stages.index("returned"), stages.index("evidence_authorized"))
        self.assertLess(stages.index("evidence_authorized"), stages.index("applied"))
        self.assertLess(stages.index("applied"), stages.index("sender_acknowledged"))
        self.assertLess(stages.index("sender_acknowledged"), stages.index("interpreted"))

    def test_operation_span_is_retained_as_performance_not_intervention_cost(self):
        path = self.path
        clock_values = iter((100, 137))
        recorder = OperationSpanRecorder(
            clock_actor_id="probe-host",
            clock_segment_id="segment-01",
            clock_ns=lambda: next(clock_values),
        )
        recorder.measure(
            attempt_id="attempt-001",
            span_id="span-001",
            operation_id="inspect",
            operation=lambda: "ok",
            context={"probe_id": "inspect"},
        )
        span = recorder.spans[0]
        record = build_record(self.model, path, operation_span=span)
        self.assertEqual(record["operation_timing"]["elapsed_ns"], 37)
        self.assertEqual(
            record["operation_timing"]["semantic_role"],
            "performance_only_not_intervention_cost",
        )
        self.assertEqual(
            record["predicted_transition"]["intervention_cost"],
            {"numerator": 2, "denominator": 1},
        )
        self.assertEqual(
            record["operation_timing"]["span"]["measurement_scope"],
            span["measurement_scope"],
        )

    def test_operation_span_from_another_attempt_is_rejected(self):
        clock_values = iter((1, 5))
        recorder = OperationSpanRecorder(
            clock_actor_id="probe-host",
            clock_segment_id="segment-01",
            clock_ns=lambda: next(clock_values),
        )
        recorder.measure(
            attempt_id="different-attempt",
            span_id="span-001",
            operation_id="inspect",
            operation=lambda: "ok",
            context={"probe_id": "inspect"},
        )
        with self.assertRaises(TransitionConformanceError):
            build_record(self.model, self.path, operation_span=recorder.spans[0])

    def test_tampered_conformance_record_is_rejected(self):
        record = build_record(self.model, self.path)
        tampered = dict(record)
        tampered["conformance_status"] = "transition_mismatch"
        with self.assertRaises(TransitionConformanceError):
            validate_transition_conformance_record(
                tampered, model_document=self.model, observation_path=self.path.to_dict()
            )

    def test_model_revision_requires_mismatch_validation_before_activation(self):
        mismatch = build_record(
            self.model, make_path(observed_outcome="unexpected"), observed_outcome="unexpected", observed_next_state="s2"
        )
        ledger = TransitionModelRevisionLedger(self.model)
        candidate = ledger.propose_transition("candidate-001", mismatch, proposer="test-agent")
        self.assertEqual(candidate["status"], "proposed")
        self.assertEqual(
            ledger.current_model_document["model_digest"],
            self.model["model_digest"],
        )
        with self.assertRaises(ValueError):
            ledger.activate_supported(
                ["candidate-001"], revision_id="transition-model-0002", actor="test-agent"
            )

        ledger.validate_candidate(
            "candidate-001", "supported",
            validation_ref="validation://independent-review-001",
            validator="independent-reviewer",
        )
        revision = ledger.activate_supported(
            ["candidate-001"],
            revision_id="transition-model-0002",
            actor="model-steward",
        )
        self.assertEqual(revision["parent_revision_id"], "transition-model-0001")
        self.assertEqual(revision["activated_candidate_ids"], ["candidate-001"])
        self.assertEqual(ledger.current_revision_id, "transition-model-0002")
        new_probe = next(
            probe for probe in ledger.current_model_document["model"]["probes"]
            if probe["probe_id"] == "inspect"
        )
        self.assertEqual(new_probe["transitions"]["s0"]["outcome"], "unexpected")
        self.assertEqual(new_probe["transitions"]["s0"]["next_state"], "s2")
        # The observed transition changes; the abstract intervention cost does not.
        self.assertEqual(
            new_probe["transitions"]["s0"]["intervention_cost"],
            {"numerator": 2, "denominator": 1},
        )
        # The parent revision remains byte-for-byte intact.
        self.assertEqual(
            ledger.revisions[0]["model_document"],
            self.model,
        )
        self.assertEqual(ledger.candidates[0]["status"], "activated")

    def test_rejected_or_inconclusive_proposals_never_activate(self):
        mismatch = build_record(
            self.model, make_path(observed_outcome="unexpected"), observed_outcome="unexpected", observed_next_state="s2"
        )
        for result in ("rejected", "inconclusive"):
            ledger = TransitionModelRevisionLedger(self.model)
            ledger.propose_transition("candidate-001", mismatch, proposer="test-agent")
            ledger.validate_candidate(
                "candidate-001", result,
                validation_ref="validation://result",
                validator="reviewer",
            )
            with self.assertRaises(ValueError):
                ledger.activate_supported(
                    ["candidate-001"], revision_id="transition-model-0002", actor="steward"
                )
            self.assertEqual(ledger.current_revision_id, "transition-model-0001")

    def test_stale_model_evidence_cannot_propose_against_new_revision(self):
        mismatch = build_record(
            self.model, make_path(observed_outcome="unexpected"), observed_outcome="unexpected", observed_next_state="s2"
        )
        ledger = TransitionModelRevisionLedger(self.model)
        ledger.propose_transition("candidate-001", mismatch, proposer="test-agent")
        ledger.validate_candidate(
            "candidate-001", "supported",
            validation_ref="validation://independent-review",
            validator="reviewer",
        )
        ledger.activate_supported(
            ["candidate-001"], revision_id="transition-model-0002", actor="steward"
        )
        with self.assertRaises(TransitionConformanceError):
            ledger.propose_transition("candidate-002", mismatch, proposer="test-agent")

    def test_unknown_state_vocabulary_is_not_silently_expanded(self):
        with self.assertRaises(TransitionConformanceError):
            build_transition_conformance_record(
                conformance_id="conformance-unknown-state",
                model_document=self.model,
                model_ref="artifact://trial08/model-001",
                observation_path=self.path.to_dict(),
                probe_id="inspect",
                current_state="s0",
                observed_outcome="yes",
                before_state_ref="state://before",
                before_state_digest=sha("before"),
                observed_next_state="state-not-in-model",
                after_state_ref="state://after",
                after_state_digest=sha("after"),
            )


    def test_conformance_record_matches_published_json_schema(self):
        import json
        from pathlib import Path
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is installed by the focused CI workflow")

        record = build_record(self.model, self.path)
        schema = json.loads(
            Path(__file__).with_name("transition-conformance.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(record, schema)


if __name__ == "__main__":
    unittest.main()
