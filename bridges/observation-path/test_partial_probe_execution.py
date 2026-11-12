import unittest
from fractions import Fraction
from types import SimpleNamespace

from vgi import GroundTransitionSystem, ObserverContext, TransitionObservation, TransitionOutcome
from vgi.partial_attention import ProbeScenario, TransitionProbe, score_partial_probe

from partial_probe_execution import (
    HISTORY_KEY,
    PartialProbeExecution,
    PartialProbeExecutionError,
)


VGI_REVISION = "cedcc4540a9d75228cf83aaf21e1ba960fe8a555"


def make_ground(*, ambiguous=False):
    observations = [
        TransitionObservation("a", "X", (TransitionOutcome("a", (0,)),)),
        TransitionObservation("b", "X", (TransitionOutcome("b", (0,)),)),
        TransitionObservation("c", "X", (TransitionOutcome("c", (1,)),)),
        TransitionObservation("a", "Y", (TransitionOutcome("a", (0,)),)),
    ]
    if ambiguous:
        observations.append(TransitionObservation(
            "b", "Y",
            (TransitionOutcome("a", (0,)), TransitionOutcome("c", (1,))),
            support_count=2,
            evidence=("old-observation-a", "old-observation-b"),
        ))
    return GroundTransitionSystem(
        states=("a", "b", "c"),
        actions=("X", "Y"),
        initial_state="a",
        channels=("out",),
        observations=tuple(observations),
    )


def make_score(system):
    observer = ObserverContext.full(system)
    probe = TransitionProbe(
        "b",
        "Y",
        (
            ProbeScenario(TransitionOutcome("a", (0,)), Fraction(1, 3)),
            ProbeScenario(TransitionOutcome("c", (1,)), Fraction(2, 3)),
        ),
        cost=Fraction(3, 2),
        label="observe-b-under-Y",
    )
    return observer, score_partial_probe(system, observer, probe, 2)


def make_attempt(system, *, authority_required=True, application_required=False):
    observer, score = make_score(system)
    return PartialProbeExecution(
        system,
        observer,
        score,
        2,
        attempt_id="probe-attempt-0001",
        query_label="resolve the Y transition from b",
        vgi_revision=VGI_REVISION,
        authority_required=authority_required,
        application_required=application_required,
    )


def record_return(attempt):
    attempt.mark_dispatched("probe-sender", "dispatch-receipt")
    attempt.mark_admitted("probe-receiver", "admission-receipt")
    attempt.record_return(
        "probe-receiver",
        evidence_ref="encounter://probe-return-1",
        encounter_id="encounter-probe-1",
        payload_digest="a" * 64,
        canonicalization="canonical-json-v1",
    )


def authorize(attempt):
    attempt.path.append(
        "evidence_authorized",
        "ecpu-consensus",
        evidence_ref="consensus://decision-1",
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


def apply(attempt):
    attempt.path.append(
        "applied",
        "ecpu-vm",
        evidence_ref="application://commit-1",
        details={
            "application_id": "application-1",
            "target_id": "receiver-ground",
            "projection_digest": "projection-sha256",
            "register_prefix": "ground.b.Y",
        },
    )


def finish_authorized_attempt(attempt, outcome, *, application=False):
    record_return(attempt)
    authorize(attempt)
    if application:
        apply(attempt)
    return attempt.interpret(
        outcome,
        actor="vgi-interpreter",
        interpretation_ref="interpretation://probe-1",
    )


class PartialProbeExecutionTests(unittest.TestCase):
    def test_unknown_cell_is_added_only_after_authorized_observation(self):
        system = make_ground()
        attempt = make_attempt(system, application_required=True)
        proposal = attempt.plan
        self.assertEqual(proposal["probe"]["cost"], {"numerator": 3, "denominator": 2})
        self.assertEqual(
            proposal["probe"]["scenarios"][0]["weight"],
            {"numerator": 1, "denominator": 3},
        )
        self.assertEqual(system.status("b", "Y"), "unknown")

        record_return(attempt)
        authorize(attempt)
        self.assertEqual(system.status("b", "Y"), "unknown")
        with self.assertRaises(ValueError):
            attempt.interpret(
                TransitionOutcome("a", (0,)),
                actor="vgi-interpreter",
                interpretation_ref="interpretation://too-early",
            )

        apply(attempt)
        result = attempt.interpret(
            TransitionOutcome("a", (0,)),
            actor="vgi-interpreter",
            interpretation_ref="interpretation://probe-1",
        )
        self.assertEqual(result["status"], "scenario_matched_not_yet_adjudicated")
        self.assertEqual(system.status("b", "Y"), "unknown")

        revision = attempt.build_ground_revision(system)
        self.assertEqual(revision.prior_cell_status, "unknown")
        self.assertEqual(revision.revised_cell_status, "known")
        self.assertEqual(revision.system.status("b", "Y"), "known")
        self.assertEqual(system.status("b", "Y"), "unknown")
        self.assertEqual(revision.system.step("b", "Y").target, "a")
        self.assertEqual(revision.evidence_refs, (
            attempt.plan_ref,
            "dispatch-receipt",
            "admission-receipt",
            "encounter://probe-return-1",
            "consensus://decision-1",
            "application://commit-1",
            "interpretation://probe-1",
        ))
        history = revision.system.metadata[HISTORY_KEY]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["vgi_revision"], VGI_REVISION)
        self.assertEqual(history[0]["plan_digest"], attempt.plan_digest)
        self.assertEqual(history[0]["prior_cell_status"], "unknown")
        self.assertEqual(
            revision.system.to_dict()["observations"][-1]["evidence"],
            list(revision.evidence_refs),
        )

    def test_ambiguous_cell_retains_every_prior_alternative(self):
        system = make_ground(ambiguous=True)
        attempt = make_attempt(system)
        result = finish_authorized_attempt(attempt, TransitionOutcome("a", (0,)))
        self.assertEqual(result["status"], "scenario_matched_not_yet_adjudicated")

        revision = attempt.build_ground_revision(system)
        self.assertEqual(revision.prior_cell_status, "ambiguous")
        self.assertEqual(revision.revised_cell_status, "ambiguous")
        self.assertEqual(revision.system.status("b", "Y"), "ambiguous")
        record = next(
            item for item in revision.system.to_dict()["observations"]
            if item["source"] == "b" and item["action"] == "Y"
        )
        self.assertEqual(
            record["outcomes"],
            [
                {"target": "a", "output": [0]},
                {"target": "c", "output": [1]},
            ],
        )
        self.assertEqual(record["support_count"], 3)
        self.assertIn("old-observation-a", record["evidence"])
        self.assertIn("old-observation-b", record["evidence"])
        self.assertIn("encounter://probe-return-1", record["evidence"])

    def test_unmodeled_outcome_is_retained_as_unresolved_not_admitted(self):
        system = make_ground()
        attempt = make_attempt(system)
        record_return(attempt)
        authorize(attempt)
        result = attempt.interpret(
            TransitionOutcome("b", (2,)),
            actor="vgi-interpreter",
            interpretation_ref="interpretation://unexpected",
        )
        self.assertEqual(result["status"], "unmodeled_outcome")
        self.assertEqual(attempt.status, "unresolved")
        self.assertEqual(system.status("b", "Y"), "unknown")
        with self.assertRaises(PartialProbeExecutionError):
            attempt.build_ground_revision(system)

    def test_unauthorized_path_can_be_interpreted_but_cannot_change_ground(self):
        system = make_ground()
        attempt = make_attempt(system, authority_required=False)
        record_return(attempt)
        result = attempt.interpret(
            TransitionOutcome("a", (0,)),
            actor="vgi-interpreter",
            interpretation_ref="interpretation://untrusted",
        )
        self.assertEqual(result["status"], "scenario_matched_not_yet_adjudicated")
        with self.assertRaises(PartialProbeExecutionError):
            attempt.build_ground_revision(system)
        self.assertEqual(system.status("b", "Y"), "unknown")

    def test_stale_ground_revision_is_rejected(self):
        system = make_ground()
        attempt = make_attempt(system)
        finish_authorized_attempt(attempt, TransitionOutcome("a", (0,)))
        changed = system.to_dict()
        changed["metadata"] = {"independent_change": True}
        stale = GroundTransitionSystem.from_dict(changed)
        with self.assertRaisesRegex(PartialProbeExecutionError, "stale proposal"):
            attempt.build_ground_revision(stale)
        self.assertEqual(system.status("b", "Y"), "unknown")

    def test_unadmitted_return_cannot_be_interpreted_or_applied(self):
        system = make_ground()
        attempt = make_attempt(system)
        attempt.mark_dispatched("probe-sender", "dispatch-receipt")
        attempt.record_unadmitted_return(
            "unadmitted-receiver",
            evidence_ref="encounter://unadmitted",
            encounter_id="encounter-unadmitted",
            payload_digest="b" * 64,
            canonicalization="canonical-json-v1",
        )
        self.assertEqual(attempt.status, "returned_unadmitted")
        with self.assertRaises(PartialProbeExecutionError):
            attempt.interpret(
                TransitionOutcome("a", (0,)),
                actor="vgi-interpreter",
                interpretation_ref="interpretation://unadmitted",
            )
        with self.assertRaises(PartialProbeExecutionError):
            attempt.build_ground_revision(system)

    def test_plan_digest_and_exact_scenario_weights_are_reproducible(self):
        system = make_ground()
        left = make_attempt(system)
        right = make_attempt(system)
        self.assertEqual(left.plan_digest, right.plan_digest)
        self.assertEqual(left.scenario_digest, right.scenario_digest)
        self.assertEqual(left.plan_ref, right.plan_ref)
        self.assertEqual(left.plan["source"]["revision"], VGI_REVISION)
        self.assertEqual(
            [item["weight"] for item in left.plan["probe"]["scenarios"]],
            [
                {"numerator": 1, "denominator": 3},
                {"numerator": 2, "denominator": 3},
            ],
        )

    def test_known_cell_is_rejected_as_a_probe(self):
        system = make_ground()
        observer = ObserverContext.full(system)
        known_probe = TransitionProbe(
            "a", "X", (ProbeScenario(TransitionOutcome("a", (0,))),)
        )
        fake_score = SimpleNamespace(
            probe=known_probe,
            estimation_kind="scenario_bounds_only",
            affected_pairs=0,
            minimum_resolved_pairs=0,
            maximum_resolved_pairs=0,
        )
        with self.assertRaisesRegex(PartialProbeExecutionError, "must be unknown or ambiguous"):
            PartialProbeExecution(
                system, observer, fake_score, 1,
                attempt_id="known-cell",
                query_label="reject known probe",
                vgi_revision=VGI_REVISION,
            )

    def test_inexact_float_cost_is_rejected_even_for_compatible_objects(self):
        system = make_ground()
        observer = ObserverContext.full(system)
        fake_probe = SimpleNamespace(
            state="b",
            action="Y",
            scenarios=(SimpleNamespace(
                outcome=TransitionOutcome("a", (0,)),
                weight=None,
            ),),
            cost=0.1,
        )
        fake_score = SimpleNamespace(
            probe=fake_probe,
            estimation_kind="scenario_bounds_only",
            affected_pairs=0,
            minimum_resolved_pairs=0,
            maximum_resolved_pairs=0,
        )
        with self.assertRaisesRegex(PartialProbeExecutionError, "exact integer or Fraction"):
            PartialProbeExecution(
                system, observer, fake_score, 1,
                attempt_id="float-cost",
                query_label="reject float cost",
                vgi_revision=VGI_REVISION,
            )

    def test_application_gate_is_enforced_before_interpretation(self):
        system = make_ground()
        attempt = make_attempt(system, application_required=True)
        record_return(attempt)
        authorize(attempt)
        with self.assertRaises(ValueError):
            attempt.interpret(
                TransitionOutcome("a", (0,)),
                actor="vgi-interpreter",
                interpretation_ref="interpretation://before-apply",
            )


if __name__ == "__main__":
    unittest.main()
