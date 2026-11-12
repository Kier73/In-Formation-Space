import hashlib
import json
import unittest
from pathlib import Path

import jsonschema

from operation_spans import (
    OperationSpanRecorder,
    build_operation_cost_profiles,
    validate_operation_cost_profiles,
    validate_operation_span,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def recorder(values, *, actor="receiver-1", segment="process-boot-1"):
    ticks = iter(values)
    return OperationSpanRecorder(
        clock_actor_id=actor,
        clock_segment_id=segment,
        clock_ns=lambda: next(ticks),
    )


class OperationSpanTests(unittest.TestCase):
    def test_successful_call_is_invoked_once_and_result_is_unchanged(self):
        calls = []
        meter = recorder([100, 145])

        def operation():
            calls.append("called")
            return {"accepted": True, "value": 7}

        result = meter.measure(
            attempt_id="attempt-1",
            span_id="span-1",
            operation_id="receiver.ingest_available",
            operation=operation,
            context={"stage": "admitted", "component": "receiver"},
        )

        self.assertEqual(result, {"accepted": True, "value": 7})
        self.assertEqual(calls, ["called"])
        span = meter.spans[0]
        self.assertEqual(span["elapsed_ns"], 45)
        self.assertEqual(span["clock_status"], "measured")
        self.assertEqual(span["outcome"], "succeeded")
        self.assertEqual(span["exception_type"], None)
        self.assertEqual(validate_operation_span(span), span)

    def test_raised_operation_is_measured_and_original_exception_is_reraised(self):
        meter = recorder([200, 260])
        failure = RuntimeError("do not serialize exception messages")

        def operation():
            raise failure

        with self.assertRaises(RuntimeError) as raised:
            meter.measure(
                attempt_id="attempt-1",
                span_id="span-fail",
                operation_id="receiver.commit_event",
                operation=operation,
            )

        self.assertIs(raised.exception, failure)
        span = meter.spans[0]
        self.assertEqual(span["outcome"], "raised")
        self.assertEqual(span["exception_type"], "builtins.RuntimeError")
        self.assertNotIn("do not serialize", json.dumps(span))
        self.assertEqual(span["elapsed_ns"], 60)

    def test_clock_regression_is_preserved_but_not_given_a_duration(self):
        meter = recorder([90, 80])
        self.assertEqual(
            meter.measure(
                attempt_id="attempt-1",
                span_id="span-regressed",
                operation_id="transport.send",
                operation=lambda: "sent",
            ),
            "sent",
        )
        span = meter.spans[0]
        self.assertEqual(span["clock_status"], "regressed")
        self.assertIsNone(span["elapsed_ns"])
        report = build_operation_cost_profiles([span], minimum_samples=1)
        profile = report["profiles"][0]
        self.assertEqual(profile["clock_regressed_count"], 1)
        self.assertEqual(profile["measured_sample_count"], 0)
        self.assertIsNone(profile["median_ns"])

    def test_clock_failure_does_not_prevent_or_replace_operation(self):
        def broken_clock():
            raise OSError("clock unavailable")

        meter = OperationSpanRecorder(
            clock_actor_id="receiver-1",
            clock_segment_id="process-boot-1",
            clock_ns=broken_clock,
        )
        calls = []
        self.assertEqual(
            meter.measure(
                attempt_id="attempt-1",
                span_id="span-unmeasured",
                operation_id="transport.process_acks",
                operation=lambda: calls.append("called") or 42,
            ),
            42,
        )
        self.assertEqual(calls, ["called"])
        self.assertEqual(meter.spans, ())
        self.assertEqual(meter.measurement_errors[0]["phase"], "start")

    def test_duplicate_span_identity_is_rejected_before_second_call(self):
        meter = recorder([1, 2, 3, 4])
        meter.measure(
            attempt_id="attempt-1",
            span_id="same",
            operation_id="transport.send",
            operation=lambda: None,
        )
        calls = []
        with self.assertRaises(ValueError):
            meter.measure(
                attempt_id="attempt-1",
                span_id="same",
                operation_id="transport.send",
                operation=lambda: calls.append("must-not-run"),
            )
        self.assertEqual(calls, [])

    def test_profiles_partition_clock_segments_and_outcomes(self):
        spans = []
        for index, (actor, segment, outcome, start, end) in enumerate([
            ("receiver-1", "boot-a", "succeeded", 0, 10),
            ("receiver-1", "boot-a", "succeeded", 20, 40),
            ("receiver-1", "boot-a", "succeeded", 50, 80),
            ("receiver-1", "boot-b", "succeeded", 0, 100),
            ("receiver-2", "boot-a", "succeeded", 0, 1000),
            ("receiver-1", "boot-a", "raised", 100, 150),
        ]):
            meter = recorder([start, end], actor=actor, segment=segment)
            if outcome == "raised":
                def fail():
                    raise LookupError("failure")
                try:
                    meter.measure(
                        attempt_id="attempt-1",
                        span_id=f"span-{index}",
                        operation_id="receiver.commit_event",
                        operation=fail,
                    )
                except LookupError:
                    pass
            else:
                meter.measure(
                    attempt_id="attempt-1",
                    span_id=f"span-{index}",
                    operation_id="receiver.commit_event",
                    operation=lambda: None,
                )
            spans.extend(meter.spans)

        report = build_operation_cost_profiles(spans, minimum_samples=3)
        self.assertEqual(len(report["profiles"]), 4)
        local = next(
            item for item in report["profiles"]
            if item["clock_actor_id"] == "receiver-1"
            and item["clock_segment_id"] == "boot-a"
            and item["outcome"] == "succeeded"
        )
        self.assertEqual(local["measured_sample_count"], 3)
        self.assertEqual(local["median_ns"], 20)
        self.assertEqual(local["p90_ns"], 30)
        self.assertEqual(local["p95_ns"], 30)
        self.assertEqual(local["readiness"], "descriptive_only")
        raised = next(item for item in report["profiles"] if item["outcome"] == "raised")
        self.assertEqual(raised["measured_sample_count"], 1)
        self.assertEqual(raised["readiness"], "insufficient_samples")
        self.assertEqual(report["policy_effect"], "none")

    def test_profiles_require_minimum_sample_count_and_exclude_unmeasured_spans(self):
        meter = recorder([10, 20, 30, 40, 50, 40])
        for index in range(3):
            meter.measure(
                attempt_id="attempt-1",
                span_id=f"span-{index}",
                operation_id="receiver.admit",
                operation=lambda: None,
            )
        report = build_operation_cost_profiles(list(meter.spans), minimum_samples=4)
        profile = report["profiles"][0]
        self.assertEqual(profile["span_count"], 3)
        self.assertEqual(profile["measured_sample_count"], 2)
        self.assertEqual(profile["clock_regressed_count"], 1)
        self.assertEqual(profile["readiness"], "insufficient_samples")

    def test_source_reconstruction_rejects_a_self_consistently_rehashed_forgery(self):
        meter = recorder([100, 125])
        meter.measure(
            attempt_id="attempt-1",
            span_id="span-1",
            operation_id="receiver.admit",
            operation=lambda: None,
        )
        spans = list(meter.spans)
        report = build_operation_cost_profiles(spans, minimum_samples=1)
        self.assertEqual(validate_operation_cost_profiles(report, spans), report)

        altered = dict(report)
        altered["profiles"] = [dict(report["profiles"][0])]
        altered["profiles"][0]["median_ns"] = 999
        core = {key: value for key, value in altered.items() if key != "profile_digest"}
        altered["profile_digest"] = digest(core)
        with self.assertRaises(ValueError):
            validate_operation_cost_profiles(altered, spans)

    def test_portable_schemas_validate_span_and_profile_documents(self):
        meter = recorder([100, 135])
        meter.measure(
            attempt_id="attempt-1",
            span_id="span-1",
            operation_id="receiver.admit",
            operation=lambda: None,
        )
        span_schema = json.loads(
            Path(__file__).with_name("operation-span.schema.json").read_text(encoding="utf-8")
        )
        profile_schema = json.loads(
            Path(__file__).with_name("operation-cost-profiles.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator.check_schema(span_schema)
        jsonschema.Draft202012Validator.check_schema(profile_schema)
        jsonschema.validate(meter.spans[0], span_schema)
        report = build_operation_cost_profiles(list(meter.spans), minimum_samples=1)
        jsonschema.validate(report, profile_schema)

    def test_invalid_minimum_sample_count_is_rejected(self):
        with self.assertRaises(ValueError):
            build_operation_cost_profiles([], minimum_samples=True)
        with self.assertRaises(ValueError):
            build_operation_cost_profiles([], minimum_samples=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
