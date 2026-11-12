import unittest
from fractions import Fraction

from hypothesis_revision import HypothesisDefinition, HypothesisRevisionLedger
from observation_path import ObservationPath
from partial_attention_navigator import (
    PartialAttentionNavigationError,
    PartialAttentionNavigator,
)
from vgi import GroundTransitionSystem, ObserverContext, TransitionObservation, TransitionOutcome
from vgi.partial_attention import (
    ProbeScenario,
    TransitionProbe,
    rank_partial_probes,
)


VGI_REVISION = "cedcc4540a9d75228cf83aaf21e1ba960fe8a555"


def make_ground():
    return GroundTransitionSystem(
        states=("a", "b", "c"),
        actions=("X", "Y"),
        initial_state="a",
        channels=("out",),
        observations=(
            TransitionObservation("a", "X", (TransitionOutcome("a", (0,)),)),
            TransitionObservation("b", "X", (TransitionOutcome("b", (0,)),)),
            TransitionObservation("c", "X", (TransitionOutcome("c", (1,)),)),
            TransitionObservation("a", "Y", (TransitionOutcome("a", (0,)),)),
        ),
    )


def candidates_for_unknown_y_cells(system, observer, cycle_index):
    probes = []
    if system.status("b", "Y") in ("unknown", "ambiguous"):
        probes.append(TransitionProbe(
            "b",
            "Y",
            (
                ProbeScenario(TransitionOutcome("a", (0,)), Fraction(1, 3)),
                ProbeScenario(TransitionOutcome("c", (1,)), Fraction(2, 3)),
            ),
            cost=Fraction(3, 2),
            label=f"observe-b-Y-cycle-{cycle_index}",
        ))
    if system.status("c", "Y") in ("unknown", "ambiguous"):
        probes.append(TransitionProbe(
            "c",
            "Y",
            (
                ProbeScenario(TransitionOutcome("a", (0,)), Fraction(1, 3)),
                ProbeScenario(TransitionOutcome("b", (1,)), Fraction(2, 3)),
            ),
            cost=Fraction(2, 1),
            label=f"observe-c-Y-cycle-{cycle_index}",
        ))
    return tuple(probes)


def make_navigator(*, probe_factory=candidates_for_unknown_y_cells):
    system = make_ground()
    observer = ObserverContext.full(system)
    navigator = PartialAttentionNavigator(
        system,
        observer,
        probe_factory,
        rank_partial_probes,
        2,
        attempt_id_prefix="attention-cycle",
        query_label="refine unknown Y transitions",
        vgi_revision=VGI_REVISION,
    )
    return navigator, observer


def complete_transport_path(execution):
    execution.mark_dispatched("probe-sender", "dispatch://sequence-1")
    execution.mark_admitted("probe-receiver", "admission://frame-1")
    execution.record_return(
        "probe-receiver",
        evidence_ref="encounter://observation-1",
        encounter_id="encounter-1",
        payload_digest="a" * 64,
        canonicalization="canonical-json-v1",
    )


def authorize_path(execution):
    execution.path.append(
        "evidence_authorized",
        "ecpu-consensus",
        evidence_ref="consensus://decision-1",
        details={
            "decision_status": "AUTHORIZED",
            "policy_digest": "policy-digest",
            "decision_digest": "decision-digest",
            "quorum": 2,
            "strict": True,
            "observed_sources": ["sensor-a", "sensor-b"],
            "dissenting_sources": [],
            "missing_sources": [],
            "representative_source": "sensor-a",
        },
    )


class PartialAttentionNavigatorTests(unittest.TestCase):
    def test_one_outstanding_attempt_uses_the_existing_observation_path(self):
        navigator, _ = make_navigator()
        selection = navigator.begin_next()
        self.assertIsNotNone(selection)
        self.assertEqual(navigator.status, "active")
        self.assertIsInstance(selection.execution.path, ObservationPath)
        self.assertEqual(selection.execution.path.status, "planned")
        self.assertEqual(selection.prior_ground_fingerprint, navigator.system.fingerprint)
        self.assertEqual(selection.ranking[0]["rank"], 1)
        with self.assertRaisesRegex(PartialAttentionNavigationError, "navigator is active"):
            navigator.begin_next()

    def test_replans_against_each_new_ground_revision(self):
        navigator, _ = make_navigator()
        first = navigator.begin_next()
        first_cell = first.selected_cell
        self.assertEqual(len(first.ranking), 2)
        complete_transport_path(first.execution)
        authorize_path(first.execution)

        first_outcome = (
            TransitionOutcome("a", (0,))
            if first_cell[0] == "b"
            else TransitionOutcome("a", (0,))
        )
        first_result = navigator.complete_active(
            first_outcome,
            actor="vgi-interpreter",
            interpretation_ref="interpretation://first",
        )
        self.assertEqual(first_result.status, "ground_revised")
        self.assertEqual(first_result.prior_ground_fingerprint, first.prior_ground_fingerprint)
        self.assertNotEqual(
            first_result.current_ground_fingerprint,
            first_result.prior_ground_fingerprint,
        )
        self.assertEqual(navigator.status, "ready")
        self.assertEqual(navigator.system.status(*first_cell), "known")

        second = navigator.begin_next()
        self.assertIsNotNone(second)
        self.assertNotEqual(second.selected_cell, first_cell)
        self.assertEqual(len(second.ranking), 1)
        complete_transport_path(second.execution)
        authorize_path(second.execution)
        second_result = navigator.complete_active(
            TransitionOutcome("a", (0,)),
            actor="vgi-interpreter",
            interpretation_ref="interpretation://second",
        )
        self.assertEqual(second_result.status, "ground_revised")
        self.assertEqual(navigator.system.status(*second.selected_cell), "known")
        self.assertEqual(len(navigator.history), 2)

        self.assertIsNone(navigator.begin_next())
        self.assertEqual(navigator.status, "exhausted")
        record = navigator.to_dict()
        self.assertEqual(record["format"], "in-formation.partial-attention-navigation/0.1")
        self.assertEqual(record["cycle_index"], 2)
        self.assertEqual(len(record["history"]), 2)

    def test_authorization_gate_is_required_before_interpretation_or_revision(self):
        navigator, _ = make_navigator()
        selection = navigator.begin_next()
        complete_transport_path(selection.execution)
        with self.assertRaisesRegex(PartialAttentionNavigationError, "requires lifecycle stage"):
            navigator.complete_active(
                TransitionOutcome("a", (0,)),
                actor="vgi-interpreter",
                interpretation_ref="interpretation://too-early",
            )
        self.assertEqual(selection.execution.path.status, "returned")
        self.assertEqual(navigator.system.status(*selection.selected_cell), "unknown")

        authorize_path(selection.execution)
        result = navigator.complete_active(
            TransitionOutcome("a", (0,)),
            actor="vgi-interpreter",
            interpretation_ref="interpretation://authorized",
        )
        self.assertEqual(result.status, "ground_revised")

    def test_model_mismatch_proposes_but_does_not_activate_or_revise(self):
        navigator, _ = make_navigator()
        selection = navigator.begin_next()
        complete_transport_path(selection.execution)
        authorize_path(selection.execution)
        ledger = HypothesisRevisionLedger((
            HypothesisDefinition("H1", "The current transition explanation."),
        ))
        prior_fingerprint = navigator.system.fingerprint

        result = navigator.complete_active(
            TransitionOutcome("b", (2,)),
            actor="vgi-interpreter",
            interpretation_ref="interpretation://unexpected",
            hypothesis_proposal={
                "ledger": ledger,
                "hypothesis_id": "H2",
                "description": "A previously unmodelled outcome exists for this transition.",
                "proposal_method": "partial-attention-counterexample-v1",
            },
        )
        self.assertEqual(result.status, "model_mismatch_proposed")
        self.assertFalse(result.scenario_match)
        self.assertEqual(navigator.status, "model_mismatch")
        self.assertEqual(navigator.system.fingerprint, prior_fingerprint)
        self.assertEqual(navigator.system.status(*selection.selected_cell), "unknown")
        self.assertEqual(result.hypothesis_candidate.validation_result, None)
        self.assertEqual(
            tuple(item.hypothesis_id for item in ledger.current_revision.hypotheses),
            ("H1",),
        )
        self.assertEqual(ledger.events[-1].event_type, "hypothesis_proposed")
        with self.assertRaises(PartialAttentionNavigationError):
            navigator.begin_next()

        navigator.resume_after_mismatch(probe_factory=candidates_for_unknown_y_cells)
        self.assertEqual(navigator.status, "ready")
        resumed = navigator.begin_next()
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.prior_ground_fingerprint, prior_fingerprint)

    def test_mismatch_without_proposal_still_stops_the_navigation_cycle(self):
        navigator, _ = make_navigator()
        selection = navigator.begin_next()
        complete_transport_path(selection.execution)
        authorize_path(selection.execution)
        result = navigator.complete_active(
            TransitionOutcome("b", (2,)),
            actor="vgi-interpreter",
            interpretation_ref="interpretation://unexpected-without-ledger",
        )
        self.assertEqual(result.status, "model_mismatch")
        self.assertIsNone(result.hypothesis_candidate)
        self.assertEqual(navigator.system.fingerprint, selection.prior_ground_fingerprint)
        with self.assertRaises(PartialAttentionNavigationError):
            navigator.resume_after_mismatch(probe_factory=None)

    def test_empty_candidate_space_is_a_clean_exhausted_state(self):
        navigator, _ = make_navigator(
            probe_factory=lambda system, observer, cycle: ()
        )
        self.assertEqual(navigator.preview(), ())
        self.assertIsNone(navigator.begin_next())
        self.assertEqual(navigator.status, "exhausted")
        navigator.close()
        self.assertEqual(navigator.status, "closed")

    def test_ranker_must_preserve_each_candidate_exactly_once(self):
        def invalid_ranker(system, observer, probes, horizon):
            ranked = rank_partial_probes(system, observer, probes, horizon)
            return ranked[:-1]

        system = make_ground()
        observer = ObserverContext.full(system)
        navigator = PartialAttentionNavigator(
            system,
            observer,
            candidates_for_unknown_y_cells,
            invalid_ranker,
            2,
            attempt_id_prefix="bad-ranker",
            query_label="q",
            vgi_revision=VGI_REVISION,
        )
        with self.assertRaisesRegex(PartialAttentionNavigationError, "candidate count"):
            navigator.preview()

    def test_distinct_observation_methods_for_the_same_cell_can_compete(self):
        def multiple_methods(system, observer, cycle_index):
            return (
                TransitionProbe(
                    "b",
                    "Y",
                    (
                        ProbeScenario(TransitionOutcome("a", (0,)), Fraction(1, 2)),
                        ProbeScenario(TransitionOutcome("c", (1,)), Fraction(1, 2)),
                    ),
                    cost=Fraction(2),
                    label="wide-sensor",
                ),
                TransitionProbe(
                    "b",
                    "Y",
                    (
                        ProbeScenario(TransitionOutcome("a", (0,)), Fraction(1, 2)),
                        ProbeScenario(TransitionOutcome("b", (1,)), Fraction(1, 2)),
                    ),
                    cost=Fraction(1),
                    label="low-latency-sensor",
                ),
            )

        navigator, _ = make_navigator(probe_factory=multiple_methods)
        ranking = navigator.preview()
        self.assertEqual(len(ranking), 2)
        self.assertEqual(
            {(score.probe.state, score.probe.action) for score in ranking},
            {("b", "Y")},
        )
        self.assertEqual(
            {score.probe.label for score in ranking},
            {"wide-sensor", "low-latency-sensor"},
        )
        selection = navigator.begin_next()
        self.assertEqual(len(selection.ranking), 2)
        self.assertEqual(selection.selected_cell, ("b", "Y"))

    def test_exact_duplicate_probe_definitions_are_rejected(self):
        def duplicate_method(system, observer, cycle_index):
            one = candidates_for_unknown_y_cells(system, observer, cycle_index)[0]
            return (one, one)

        navigator, _ = make_navigator(probe_factory=duplicate_method)
        with self.assertRaisesRegex(
            PartialAttentionNavigationError,
            "exact duplicate probe definition",
        ):
            navigator.preview()

    def test_sender_ack_requirement_cannot_be_declared_without_application(self):
        system = make_ground()
        observer = ObserverContext.full(system)
        with self.assertRaisesRegex(PartialAttentionNavigationError, "implies application"):
            PartialAttentionNavigator(
                system,
                observer,
                candidates_for_unknown_y_cells,
                rank_partial_probes,
                2,
                attempt_id_prefix="bad-gates",
                query_label="q",
                vgi_revision=VGI_REVISION,
                sender_ack_required=True,
            )


if __name__ == "__main__":
    unittest.main()
