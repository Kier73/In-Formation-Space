"""Local operation-span measurement and conservative empirical cost summaries.

Spans time the synchronous call boundary supplied by the caller. They are
separate from checkpoint-to-checkpoint temporal frames: a span includes the
call's synchronous wall duration, including any blocking inside that call,
but is not CPU time and does not split internal sub-operations.

Measurement failures never replace the wrapped operation's result or exception.
The cost-profile builder is descriptive only and never changes an adaptive
policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from collections import defaultdict
from statistics import median
from typing import Any, Callable, Mapping, TypeVar

T = TypeVar("T")

_SPAN_SCHEMA = "in-formation.operation-span/0.1"
_PROFILE_SCHEMA = "in-formation.operation-cost-profiles/0.1"
_MEASUREMENT_SCOPE = (
    "Elapsed monotonic time between the recorder's immediately-before and "
    "immediately-after samples around one synchronous callable invocation; "
    "includes blocking within the call and excludes later work."
)
_PROFILE_SCOPE = (
    "Descriptive distributions of recorded synchronous call spans, partitioned "
    "by operation, clock actor, clock segment, and outcome."
)
_LIMITS = [
    "A span measures the supplied callable boundary, not CPU time or an isolated internal function.",
    "Samples from different clock actors or clock segments are never combined.",
    "Raised calls are profiled separately from successful calls.",
    "Regressed or unavailable clock samples are excluded from duration statistics, not treated as zero.",
    "Only invoked and successfully measured calls appear; uninvoked candidates have unknown cost.",
    "Profiles are descriptive evidence and do not alter, authorize, or rank adaptive policies.",
]


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _strict_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def validate_operation_span(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a span's structure, clock arithmetic, scope, and digest."""
    if not isinstance(document, Mapping):
        raise TypeError("operation span must be a mapping")
    fields = {
        "format", "schema", "attempt_id", "span_id", "operation_id",
        "clock_actor_id", "clock_segment_id", "monotonic_start_ns",
        "monotonic_end_ns", "elapsed_ns", "clock_status", "outcome",
        "exception_type", "context", "measurement_scope", "span_digest",
    }
    if set(document) != fields:
        raise ValueError("operation span fields are incomplete or unexpected")
    if document["format"] != "in-formation.operation-span":
        raise ValueError("unsupported operation-span format")
    if document["schema"] != _SPAN_SCHEMA:
        raise ValueError("unsupported operation-span schema")
    for field in ("attempt_id", "span_id", "operation_id", "clock_actor_id", "clock_segment_id"):
        _text(document[field], field)

    start = _strict_ns(document["monotonic_start_ns"], "monotonic_start_ns")
    end = _strict_ns(document["monotonic_end_ns"], "monotonic_end_ns")
    status = document["clock_status"]
    elapsed = document["elapsed_ns"]
    if status == "measured":
        if end < start:
            raise ValueError("measured span cannot have a regressed monotonic clock")
        if _strict_ns(elapsed, "elapsed_ns") != end - start:
            raise ValueError("elapsed_ns must equal monotonic_end_ns - monotonic_start_ns")
    elif status == "regressed":
        if end >= start or elapsed is not None:
            raise ValueError("regressed span must have end < start and null elapsed_ns")
    else:
        raise ValueError("clock_status must be measured or regressed")

    outcome = document["outcome"]
    exception_type = document["exception_type"]
    if outcome == "succeeded":
        if exception_type is not None:
            raise ValueError("successful span must not name an exception")
    elif outcome == "raised":
        _text(exception_type, "exception_type")
    else:
        raise ValueError("outcome must be succeeded or raised")

    context = document["context"]
    if not isinstance(context, Mapping):
        raise ValueError("context must be a JSON object")
    _canonical(dict(context))
    if document["measurement_scope"] != _MEASUREMENT_SCOPE:
        raise ValueError("operation-span measurement scope must retain its declared boundary")

    core = {key: document[key] for key in fields if key != "span_digest"}
    if document["span_digest"] != _digest(core):
        raise ValueError("operation-span digest does not match its contents")
    return dict(document)


class OperationSpanRecorder:
    """Measure synchronous call boundaries without changing call semantics.

    The caller supplies a stable clock actor and segment identity. A new
    segment identifier should be used when continuity of the monotonic clock
    cannot be guaranteed (for example, after process restart).
    """

    def __init__(
        self,
        *,
        clock_actor_id: str,
        clock_segment_id: str,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.clock_actor_id = _text(clock_actor_id, "clock_actor_id")
        self.clock_segment_id = _text(clock_segment_id, "clock_segment_id")
        if not callable(clock_ns):
            raise TypeError("clock_ns must be callable")
        self._clock_ns = clock_ns
        self._spans: list[dict[str, Any]] = []
        self._span_ids: set[tuple[str, str]] = set()
        self._measurement_errors: list[dict[str, str]] = []

    @property
    def spans(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(span) for span in self._spans)

    @property
    def measurement_errors(self) -> tuple[dict[str, str], ...]:
        return tuple(dict(error) for error in self._measurement_errors)

    def _read_clock(self, phase: str) -> int | None:
        try:
            value = self._clock_ns()
            return _strict_ns(value, "clock_ns result")
        except Exception as error:
            self._measurement_errors.append({
                "phase": phase,
                "exception_type": f"{type(error).__module__}.{type(error).__qualname__}",
            })
            return None

    def _append(
        self,
        *,
        attempt_id: str,
        span_id: str,
        operation_id: str,
        start: int,
        end: int,
        outcome: str,
        exception_type: str | None,
        context: Mapping[str, Any],
    ) -> None:
        core = {
            "format": "in-formation.operation-span",
            "schema": _SPAN_SCHEMA,
            "attempt_id": attempt_id,
            "span_id": span_id,
            "operation_id": operation_id,
            "clock_actor_id": self.clock_actor_id,
            "clock_segment_id": self.clock_segment_id,
            "monotonic_start_ns": start,
            "monotonic_end_ns": end,
            "elapsed_ns": end - start if end >= start else None,
            "clock_status": "measured" if end >= start else "regressed",
            "outcome": outcome,
            "exception_type": exception_type,
            "context": json.loads(_canonical(dict(context))),
            "measurement_scope": _MEASUREMENT_SCOPE,
        }
        document = {**core, "span_digest": _digest(core)}
        validate_operation_span(document)
        self._spans.append(document)

    def measure(
        self,
        *,
        attempt_id: str,
        span_id: str,
        operation_id: str,
        operation: Callable[[], T],
        context: Mapping[str, Any] | None = None,
    ) -> T:
        """Run operation once, record its duration when possible, and preserve its outcome."""
        attempt_id = _text(attempt_id, "attempt_id")
        span_id = _text(span_id, "span_id")
        operation_id = _text(operation_id, "operation_id")
        if not callable(operation):
            raise TypeError("operation must be callable")
        key = (attempt_id, span_id)
        if key in self._span_ids:
            raise ValueError("span_id must be unique within an attempt")
        normalized_context = {} if context is None else dict(context)
        if not isinstance(normalized_context, dict):
            raise TypeError("context must be a mapping")
        _canonical(normalized_context)
        self._span_ids.add(key)

        start = self._read_clock("start")
        if start is None:
            # Telemetry is optional: do not suppress the operation because a
            # measurement clock is unavailable.
            return operation()

        try:
            result = operation()
        except BaseException as error:
            end = self._read_clock("end")
            if end is not None:
                self._append(
                    attempt_id=attempt_id, span_id=span_id, operation_id=operation_id,
                    start=start, end=end, outcome="raised",
                    exception_type=f"{type(error).__module__}.{type(error).__qualname__}",
                    context=normalized_context,
                )
            raise
        else:
            end = self._read_clock("end")
            if end is not None:
                self._append(
                    attempt_id=attempt_id, span_id=span_id, operation_id=operation_id,
                    start=start, end=end, outcome="succeeded",
                    exception_type=None, context=normalized_context,
                )
            return result


def _nearest_rank(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _validated_span_collection(
    span_documents: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(span_documents, list):
        raise TypeError("span_documents must be a list")
    validated = [validate_operation_span(span) for span in span_documents]
    identities: set[tuple[str, str]] = set()
    for span in validated:
        identity = (span["attempt_id"], span["span_id"])
        if identity in identities:
            raise ValueError("duplicate operation-span identity in source collection")
        identities.add(identity)
    return validated


def build_operation_cost_profiles(
    span_documents: list[Mapping[str, Any]],
    *,
    minimum_samples: int = 5,
) -> dict[str, Any]:
    """Summarize measured spans without mixing clock segments or outcomes."""
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
        raise ValueError("minimum_samples must be a positive integer")
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    validated = _validated_span_collection(span_documents)
    for span in validated:
        key = (
            span["operation_id"], span["clock_actor_id"],
            span["clock_segment_id"], span["outcome"],
        )
        groups[key].append(span)

    profiles = []
    for (operation_id, actor_id, segment_id, outcome), spans in sorted(groups.items()):
        measured = [
            span["elapsed_ns"] for span in spans
            if span["clock_status"] == "measured" and span["elapsed_ns"] is not None
        ]
        ready = len(measured) >= minimum_samples
        profiles.append({
            "operation_id": operation_id,
            "clock_actor_id": actor_id,
            "clock_segment_id": segment_id,
            "outcome": outcome,
            "span_count": len(spans),
            "measured_sample_count": len(measured),
            "clock_regressed_count": sum(span["clock_status"] == "regressed" for span in spans),
            "median_ns": median(measured) if measured else None,
            "p90_ns": _nearest_rank(measured, 0.90) if measured else None,
            "p95_ns": _nearest_rank(measured, 0.95) if measured else None,
            "minimum_ns": min(measured) if measured else None,
            "maximum_ns": max(measured) if measured else None,
            "readiness": "descriptive_only" if ready else "insufficient_samples",
        })

    core = {
        "schema": _PROFILE_SCHEMA,
        "minimum_samples": minimum_samples,
        "profiles": profiles,
        "source_span_digests": sorted(span["span_digest"] for span in validated),
        "policy_effect": "none",
        "measurement_scope": _PROFILE_SCOPE,
        "interpretation_limits": list(_LIMITS),
    }
    return {**core, "profile_digest": _digest(core)}


def validate_operation_cost_profiles(
    report: Mapping[str, Any],
    span_documents: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Independently rebuild profiles from source spans and require exact equality."""
    if not isinstance(report, Mapping):
        raise TypeError("cost-profile report must be a mapping")
    supplied = dict(report)
    digest = supplied.pop("profile_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise ValueError("cost-profile digest does not match its contents")
    if supplied.get("schema") != _PROFILE_SCHEMA:
        raise ValueError("unsupported operation cost-profile schema")
    rebuilt = build_operation_cost_profiles(
        span_documents, minimum_samples=supplied.get("minimum_samples")
    )
    if rebuilt != dict(report):
        raise ValueError("cost profile differs from independent reconstruction from source spans")
    return dict(report)


def load_operation_span_artifact(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON span array or the CI artifact shape {"spans": [...]}."""
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read operation-span artifact {source}: {error}") from error
    if isinstance(document, Mapping):
        spans = document.get("spans")
    else:
        spans = document
    if not isinstance(spans, list):
        raise ValueError(f"operation-span artifact {source} must contain a spans array")
    return [validate_operation_span(span) for span in spans]


def main(argv: list[str] | None = None) -> int:
    """Command-line reader for one or more saved operation-span artifacts."""
    parser = argparse.ArgumentParser(
        description=(
            "Build conservative operation-cost profiles from saved operation spans. "
            "Clock actors, clock segments, and outcomes remain separate."
        )
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="JSON",
        help="span artifact JSON; repeat to analyze multiple artifacts",
    )
    parser.add_argument(
        "--minimum-samples",
        type=int,
        default=5,
        help="measured samples required for descriptive_only (default: 5)",
    )
    parser.add_argument(
        "--output",
        metavar="JSON",
        help="write the profile document to this path (default: stdout)",
    )
    args = parser.parse_args(argv)

    try:
        spans = []
        for artifact in args.input:
            spans.extend(load_operation_span_artifact(artifact))
        if not spans:
            raise ValueError("no operation spans were supplied")
        report = build_operation_cost_profiles(
            spans,
            minimum_samples=args.minimum_samples,
        )
        validate_operation_cost_profiles(report, spans)
        rendered = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
