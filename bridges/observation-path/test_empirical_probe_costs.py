import unittest
from dataclasses import dataclass
from fractions import Fraction

from operation_spans import OperationSpanRecorder, build_operation_cost_profiles
from empirical_probe_costs import (
    EmpiricalProbeCostError,
    EmpiricalProbeCostModel,
    ProbeCostBinding,
)
from vgi import (
    GroundTransitionSystem,
    ObserverContext,
    TransitionObservation,
    TransitionOutcome,
)
from vgi.partial_attention import (
    ProbeScenario,
    TransitionProbe,
    rank_partial_probes,
)
from partial_attention_navigator import PartialAttentionNavigator


def measured_fixture(*, samples=5, include_raised=False):
    values = []
    spans = []
    recorder = None
    cursor = 100
    for method, operation_id, durations in (
        ("fast-method", "sensor.fast", [10, 15, 20, 25, 30][:samples]),
        ("slow-method", "sensor.slow", [100, 150, 200, 250, 300][:samples]),
    ):
        ticks = []
        for index, duration in enumerate(durations):
            ticks.extend((cursor, cursor + duration))
            cursor += duration + 50
        recorder = OperationSpanRecorder(
            clock_actor_id="host-actor-1",
            clock_segment_id="process-segment-1",
            clock_ns=iter(ticks).__next__,
        )
        for index in range(len(durations)):
            recorder.measure(
                attempt_id=f"{method}-attempt-{index}",
                span_id=f"{method}-span-{index}",
                operation_id=operation_id,
                operation=lambda: None,
            )
        spans.extend(recorder.spans)

    if include_raised:
        ticks = iter((cursor, cursor + 100))
        failed = OperationSpanRecorder(
            clock_actor_id="host-actor-1",
            clock_segment_id="process-segment-1",
            clock_ns=ticks.__next__,
        )
        def fail():
            raise RuntimeError("do not use raised costs")
        try:
            failed.measure(
                attempt_id="failed-attempt",
                span_id="failed-span",
                operation_id="sensor.fast",
                operation=fail,
            )
        except RuntimeError:
            pass
        spans.extend(failed.spans)

    profile = build_operation_cost_profiles(spans, minimum_samples=5)
    bindings = (
        ProbeCostBinding(
            "fast-method", "sensor.fast", "host-actor-1", "process-segment-1"
        ),
        ProbeCostBinding(
            "slow-method", "sensor.slow", "host-actor-1", "process-segment-1"
        ),
    )
    return spans, profile, bindings


def candidate(label, prior_cost=Fraction(999)):
    return TransitionProbe(
        "state-0",
        "inspect",
        (
            ProbeScenario(TransitionOutcome("state-1", (1,)), Fraction(1, 2)),
            ProbeScenario(TransitionOutcome("state-2", (2,)), Fraction(1, 2)),
        ),
        cost=prior_cost,
        label=label,
    )


class EmpiricalProbeCostModelTests(unittest.TestCase):
    def test_calibrates_vgi_costs_from_exact_successful_p90_profiles(self):
        spans, profile, bindings = measured_fixture(include_raised=True)
        model = EmpiricalProbeCostModel(spans, profile, bindings)
        applied = model.apply_all((
            candidate("fast-method"),
            candidate("slow-method"),
        ))

        self.assertEqual(applied.probes[0].cost, Fraction(30, 1))
        self.assertEqual(applied.probes[1].cost, Fraction(300, 1))
        self.assertEqual(applied.records[0]["statistic"], "p90_ns")
        self.assertEqual(applied.records[0]["outcome"], "succeeded")
        self.assertEqual(applied.records[0]["measured_sample_count"], 5)
        self.assertEqual(len(applied.records[0]["source_span_digests"]), 5)
        self.assertEqual(
            applied.records[0]["clock_actor_id"],
            applied.records[1]["clock_actor_id"],
        )
        self.assertEqual(
            applied.records[0]["clock_segment_id"],
            applied.records[1]["clock_segment_id"],
        )
        self.assertEqual(model.clock_domain, ("host-actor-1", "process-segment-1"))
        self.assertEqual(model.to_dict()["policy_effect"], "candidate_cost_only")

    def test_does_not_mutate_supplied_probe_cost(self):
        spans, profile, bindings = measured_fixture()
        model = EmpiricalProbeCostModel(spans, profile, bindings)
        original = candidate("fast-method", Fraction(7, 3))
        calibrated = model.apply_all((original,)).probes[0]
        self.assertEqual(original.cost, Fraction(7, 3))
        self.assertEqual(calibrated.cost, Fraction(30, 1))
        self.assertIsNot(original, calibrated)

    def test_unbound_probe_method_fails_closed(self):
        spans, profile, bindings = measured_fixture()
        model = EmpiricalProbeCostModel(spans, profile, bindings)
        with self.assertRaisesRegex(EmpiricalProbeCostError, "no empirical cost binding"):
            model.apply_all((candidate("unmeasured-method"),))

    def test_under_sampled_profile_cannot_set_candidate_cost(self):
        spans, profile, bindings = measured_fixture(samples=4)
        with self.assertRaisesRegex(EmpiricalProbeCostError, "insufficient successful samples"):
            EmpiricalProbeCostModel(spans, profile, bindings)

    def test_incomparable_clock_actors_or_segments_cannot_be_compared(self):
        spans, profile, bindings = measured_fixture()
        mismatched = (
            bindings[0],
            ProbeCostBinding(
                "slow-method", "sensor.slow", "other-actor", "process-segment-1"
            ),
        )
        with self.assertRaisesRegex(EmpiricalProbeCostError, "share one clock actor and segment"):
            EmpiricalProbeCostModel(spans, profile, mismatched)

    def test_different_percentiles_cannot_be_mixed(self):
        spans, profile, bindings = measured_fixture()
        mismatched = (
            bindings[0],
            ProbeCostBinding(
                "slow-method", "sensor.slow", "host-actor-1",
                "process-segment-1", statistic="p95_ns"
            ),
        )
        with self.assertRaisesRegex(EmpiricalProbeCostError, "same percentile statistic"):
            EmpiricalProbeCostModel(spans, profile, mismatched)

    def test_profile_must_rebuild_from_the_supplied_source_spans(self):
        spans, profile, bindings = measured_fixture()
        altered = dict(profile)
        altered["profiles"] = [dict(item) for item in profile["profiles"]]
        altered["profiles"][0]["p90_ns"] += 1
        with self.assertRaises(ValueError):
            EmpiricalProbeCostModel(spans, altered, bindings)

    def test_clock_segment_must_match_the_actual_source_spans(self):
        spans, profile, _ = measured_fixture()
        wrong = (
            ProbeCostBinding(
                "fast-method", "sensor.fast", "host-actor-1", "other-segment"
            ),
        )
        with self.assertRaisesRegex(EmpiricalProbeCostError, "expected exactly one successful"):
            EmpiricalProbeCostModel(spans, profile, wrong)

    def test_zero_resolution_cost_does_not_get_invented_as_a_positive_value(self):
        ticks = []
        cursor = 100
        for index in range(5):
            ticks.extend((cursor, cursor))
            cursor += 10
        meter = OperationSpanRecorder(
            clock_actor_id="host-actor",
            clock_segment_id="boot",
            clock_ns=iter(ticks).__next__,
        )
        for index in range(5):
            meter.measure(
                attempt_id=f"zero-{index}",
                span_id=f"zero-span-{index}",
                operation_id="sensor.zero",
                operation=lambda: None,
            )
        spans = list(meter.spans)
        profile = build_operation_cost_profiles(spans, minimum_samples=5)
        binding = (ProbeCostBinding(
            "zero-method", "sensor.zero", "host-actor", "boot"
        ),)
        with self.assertRaisesRegex(EmpiricalProbeCostError, "must be a positive integer"):
            EmpiricalProbeCostModel(spans, profile, binding)

    def test_navigator_uses_measured_costs_and_preserves_their_provenance(self):
        spans, profile, bindings = measured_fixture()
        model = EmpiricalProbeCostModel(spans, profile, bindings)
        system = GroundTransitionSystem(
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
        observer = ObserverContext.full(system)

        def probes(current, current_observer, cycle_index):
            return (
                TransitionProbe(
                    "b", "Y",
                    (
                        ProbeScenario(TransitionOutcome("a", (0,)), Fraction(1, 3)),
                        ProbeScenario(TransitionOutcome("c", (1,)), Fraction(2, 3)),
                    ),
                    cost=Fraction(1),
                    label="fast-method",
                ),
                TransitionProbe(
                    "c", "Y",
                    (
                        ProbeScenario(TransitionOutcome("a", (0,)), Fraction(1, 3)),
                        ProbeScenario(TransitionOutcome("b", (1,)), Fraction(2, 3)),
                    ),
                    cost=Fraction(1),
                    label="slow-method",
                ),
            )

        navigator = PartialAttentionNavigator(
            system,
            observer,
            probes,
            rank_partial_probes,
            2,
            attempt_id_prefix="empirical-cost",
            query_label="compare measured probe cost integration",
            vgi_revision="cedcc4540a9d75228cf83aaf21e1ba960fe8a555",
            cost_model=model,
        )
        selection = navigator.begin_next()
        self.assertIsNotNone(selection)
        records = {item["label"]: item for item in selection.ranking}
        self.assertEqual(records["fast-method"]["cost"], {"numerator": 30, "denominator": 1})
        self.assertEqual(records["slow-method"]["cost"], {"numerator": 300, "denominator": 1})
        self.assertEqual(
            records["fast-method"]["cost_provenance"]["model_digest"],
            model.model_digest,
        )
        self.assertEqual(
            records["slow-method"]["cost_provenance"]["profile_digest"],
            model.profile_digest,
        )
        self.assertEqual(
            navigator.to_dict()["cost_model_digest"],
            model.model_digest,
        )
        selected_label = selection.execution.score.probe.label
        self.assertEqual(
            selection.execution.score.probe.cost,
            Fraction(records[selected_label]["cost"]["numerator"], 1),
        )

    def test_binding_rejects_non_integer_cost_statistics(self):
        with self.assertRaisesRegex(EmpiricalProbeCostError, "preserve exact integer costs"):
            ProbeCostBinding(
                "sensor", "sensor.call", "actor", "segment", statistic="median_ns"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
