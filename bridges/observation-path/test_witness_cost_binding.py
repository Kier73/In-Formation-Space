"""OE-002 tests: profile reconstruction, exact binding, active-plan-only output."""

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

# The production navigator lives in a sibling research bridge.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "observation-equivalence"))

from costed_navigation import CostedDistinctionNavigator
from operation_spans import OperationSpanRecorder, build_operation_cost_profiles
from witness_cost_binding import (
    plan_with_empirical_costs,
    propose_witness_cost_policy,
    reconstruct_witness_cost_policy,
)


def fixture():
    spans = []
    samples = {
        "action.expensive": [10] * 5,
        "action.cheap": [2] * 5,
        "test.read": [1] * 5,
    }
    for operation, durations in samples.items():
        ticks = iter(value for index, duration in enumerate(durations)
                     for value in (100 * index, 100 * index + duration))
        recorder = OperationSpanRecorder(
            clock_actor_id="host-A", clock_segment_id="boot-1",
            clock_ns=lambda: next(ticks),
        )
        for index in range(len(durations)):
            recorder.measure(
                attempt_id=f"{operation}-{index}", span_id="span",
                operation_id=operation, operation=lambda: None,
            )
        spans.extend(recorder.spans)
    return spans, build_operation_cost_profiles(spans, minimum_samples=5)


def navigator():
    states = ("a", "b", "x", "y", "c", "d")
    output = {state: 0 for state in states} | {"c": 1, "d": 2}
    transitions = {
        ("a", "expensive"): "c", ("b", "expensive"): "d",
        ("a", "cheap"): "x", ("b", "cheap"): "y",
        ("x", "cheap"): "c", ("y", "cheap"): "d",
    }
    return CostedDistinctionNavigator(
        states, ("expensive", "cheap"), ("read",),
        lambda state, test: output[state],
        lambda state, action: transitions.get((state, action), state),
    )


def proposal(spans, profiles, **overrides):
    params = dict(
        action_bindings=(("expensive", "action.expensive"), ("cheap", "action.cheap")),
        test_bindings=(("read", "test.read"),),
        clock_actor_id="host-A", clock_segment_id="boot-1",
        minimum_samples=5, explicit_planning_opt_in=True,
    )
    params.update(overrides)
    return propose_witness_cost_policy(profiles, spans, **params)


class WitnessCostBindingTests(unittest.TestCase):
    def test_reconstructs_measurements_and_selects_cheaper_longer_path(self):
        spans, profiles = fixture()
        cost_policy = proposal(spans, profiles)
        self.assertEqual(cost_policy["scope"], "single-clock-actor-segment-successful-synchronous-calls-p95")
        self.assertEqual([c["cost_ns"] for c in cost_policy["action_costs"]], [10, 2])
        self.assertEqual([c["cost_ns"] for c in cost_policy["test_costs"]], [1])
        self.assertEqual(reconstruct_witness_cost_policy(
            cost_policy, profiles, spans, explicit_planning_opt_in=True
        ), cost_policy)
        nav = navigator()
        self.assertEqual(nav.compare("a", "b").actions, ("expensive",))
        plan = plan_with_empirical_costs(
            nav, "a", "b", cost_policy, profiles, spans, explicit_planning_opt_in=True,
        )
        self.assertEqual(plan.witness.actions, ("cheap", "cheap"))
        self.assertEqual((plan.action_cost, plan.test_cost, plan.total_cost), (4, 1, 5))

    def test_explicit_operator_opt_in_is_required_at_all_stages(self):
        spans, profiles = fixture()
        with self.assertRaisesRegex(ValueError, "explicit opt-in"):
            proposal(spans, profiles, explicit_planning_opt_in=False)
        policy = proposal(spans, profiles)
        with self.assertRaisesRegex(ValueError, "explicit opt-in"):
            reconstruct_witness_cost_policy(policy, profiles, spans)
        with self.assertRaisesRegex(ValueError, "explicit opt-in"):
            plan_with_empirical_costs(navigator(), "a", "b", policy, profiles, spans)

    def test_missing_operation_and_different_clock_context_refused(self):
        spans, profiles = fixture()
        with self.assertRaisesRegex(ValueError, "no successful measured profile"):
            proposal(spans, profiles, clock_segment_id="another-boot")
        with self.assertRaisesRegex(ValueError, "no successful measured profile"):
            proposal(spans, profiles, clock_actor_id="another-host")
        with self.assertRaisesRegex(ValueError, "no successful measured profile"):
            proposal(spans, profiles, action_bindings=(("cheap", "not-in-spans"),))

    def test_descriptive_readiness_is_not_a_prediction_guarantee(self):
        spans, profiles = fixture()
        with self.assertRaisesRegex(ValueError, "too few measured samples"):
            proposal(spans, profiles, minimum_samples=6)
        not_ready = build_operation_cost_profiles(spans, minimum_samples=6)
        with self.assertRaisesRegex(ValueError, "insufficient profiler readiness"):
            proposal(spans, not_ready)
        with self.assertRaises(ValueError):
            proposal(spans, profiles, minimum_samples=True)

    def test_raised_operation_record_refuses_cost_estimate(self):
        spans, _ = fixture()
        meter = OperationSpanRecorder(
            clock_actor_id="host-A", clock_segment_id="boot-1",
            clock_ns=iter([12, 25]).__next__,
        )
        def fail():
            raise RuntimeError("unreliable operation")
        with self.assertRaises(RuntimeError):
            meter.measure(
                attempt_id="failure-0", span_id="f", operation_id="action.cheap", operation=fail,
            )
        spans += list(meter.spans)
        with self.assertRaisesRegex(ValueError, "raised-call evidence"):
            proposal(spans, build_operation_cost_profiles(spans, minimum_samples=5))

    def test_regressed_clock_sample_refuses_cost_estimate(self):
        spans, _ = fixture()
        meter = OperationSpanRecorder(
            clock_actor_id="host-A", clock_segment_id="boot-1",
            clock_ns=iter([20, 19]).__next__,
        )
        meter.measure(
            attempt_id="regressed-0", span_id="r", operation_id="test.read", operation=lambda: None,
        )
        spans += list(meter.spans)
        with self.assertRaisesRegex(ValueError, "regressed-clock evidence"):
            proposal(spans, build_operation_cost_profiles(spans, minimum_samples=5))

    def test_self_consistently_rehashed_profile_rejected_from_source_spans(self):
        spans, profiles = fixture()
        forged = copy.deepcopy(profiles)
        forged["profiles"][0]["p95_ns"] = 987654321
        core = {key: value for key, value in forged.items() if key != "profile_digest"}
        forged["profile_digest"] = hashlib.sha256(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "source spans"):
            proposal(spans, forged)

    def test_self_consistently_rehashed_proposal_rejected_from_source_spans(self):
        spans, profiles = fixture()
        forged = copy.deepcopy(proposal(spans, profiles))
        forged["action_costs"][0]["cost_ns"] = 0
        core = {key: value for key, value in forged.items() if key != "proposal_digest"}
        forged["proposal_digest"] = hashlib.sha256(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "differs from exact reconstruction"):
            reconstruct_witness_cost_policy(forged, profiles, spans, explicit_planning_opt_in=True)

    def test_position_mismatch_and_unlisted_reading_are_refused(self):
        spans, profiles = fixture()
        reversed_bindings = proposal(
            spans, profiles, action_bindings=(("cheap", "action.cheap"), ("expensive", "action.expensive")),
        )
        with self.assertRaisesRegex(ValueError, "action order differs"):
            plan_with_empirical_costs(
                navigator(), "a", "b", reversed_bindings, profiles, spans,
                explicit_planning_opt_in=True,
            )
        with self.assertRaisesRegex(ValueError, "test order differs"):
            plan_with_empirical_costs(
                navigator(), "a", "b", proposal(spans, profiles, test_bindings=(("other", "test.read"),)),
                profiles, spans, explicit_planning_opt_in=True,
            )

    def test_duplicate_labels_and_missing_scope_are_refused(self):
        spans, profiles = fixture()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            proposal(spans, profiles, action_bindings=(("same", "action.cheap"), ("same", "action.expensive")))
        with self.assertRaisesRegex(ValueError, "nonempty text"):
            proposal(spans, profiles, test_bindings=(("", "test.read"),))
        with self.assertRaisesRegex(ValueError, "at least one"):
            proposal(spans, profiles, action_bindings=(), test_bindings=())


if __name__ == "__main__":
    unittest.main()
