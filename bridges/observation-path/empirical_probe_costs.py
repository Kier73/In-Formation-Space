"""Bind measured operation-span distributions to VGI probe costs.

This module does not infer which operation implements a probe. Callers declare
that method-to-operation relationship explicitly, and every compared method
must be measured on the same monotonic clock actor and segment. Only successful,
sufficiently sampled profiles are eligible. The chosen percentile is an exact
integer number of nanoseconds and is inserted as a Fraction into the supplied
VGI TransitionProbe.

The resulting ranking remains model-derived information gain divided by an
empirical latency cost. It does not turn runtime latency into evidence about
the transition outcome, assign scenario probabilities, or authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
import hashlib
import json
from typing import Any, Mapping, Sequence

from operation_spans import (
    validate_operation_cost_profiles,
    validate_operation_span,
)


class EmpiricalProbeCostError(ValueError):
    """Invalid or insufficient measured cost evidence for candidate ranking."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EmpiricalProbeCostError(
            f"value must be finite canonical JSON: {exc}"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EmpiricalProbeCostError(f"{label} must be non-empty text")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EmpiricalProbeCostError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True)
class ProbeCostBinding:
    """Explicit link from one probe method label to one measured operation."""

    method_id: str
    operation_id: str
    clock_actor_id: str
    clock_segment_id: str
    statistic: str = "p90_ns"

    def __post_init__(self) -> None:
        for name in (
            "method_id", "operation_id", "clock_actor_id", "clock_segment_id"
        ):
            _text(getattr(self, name), name)
        if self.statistic not in {"p90_ns", "p95_ns"}:
            raise EmpiricalProbeCostError(
                "statistic must be p90_ns or p95_ns to preserve exact integer costs"
            )


@dataclass(frozen=True)
class AppliedProbeCosts:
    """Calibrated candidates and provenance records in their original order."""

    probes: tuple[object, ...]
    records: tuple[dict[str, Any], ...]


class EmpiricalProbeCostModel:
    """Strict, evidence-backed cost mapping for candidate probe methods.

    Source spans are independently validated and used to rebuild the profile.
    All method bindings share a single clock actor and segment so VGI does not
    compare nanoseconds from incomparable clocks.

    Probe label is the method identifier and must have an explicit binding.
    No pre-existing probe cost is used as a fallback.
    """

    def __init__(
        self,
        span_documents: Sequence[Mapping[str, Any]],
        profile_report: Mapping[str, Any],
        bindings: Sequence[ProbeCostBinding],
        *,
        minimum_samples: int = 5,
    ) -> None:
        self._minimum_samples = _positive_integer(minimum_samples, "minimum_samples")
        if not isinstance(span_documents, (tuple, list)) or not span_documents:
            raise EmpiricalProbeCostError("span_documents must be a non-empty sequence")
        self._spans = tuple(validate_operation_span(item) for item in span_documents)
        if not isinstance(profile_report, Mapping):
            raise EmpiricalProbeCostError("profile_report must be a mapping")

        self._profile = validate_operation_cost_profiles(
            dict(profile_report), list(self._spans)
        )
        if not isinstance(bindings, (tuple, list)) or not bindings:
            raise EmpiricalProbeCostError("at least one explicit probe cost binding is required")
        normalized: dict[str, ProbeCostBinding] = {}
        clock_domains = set()
        statistics = set()
        for index, binding in enumerate(bindings):
            if not isinstance(binding, ProbeCostBinding):
                raise EmpiricalProbeCostError(
                    f"bindings[{index}] must be a ProbeCostBinding"
                )
            if binding.method_id in normalized:
                raise EmpiricalProbeCostError(
                    f"duplicate method cost binding: {binding.method_id}"
                )
            normalized[binding.method_id] = binding
            clock_domains.add((binding.clock_actor_id, binding.clock_segment_id))
            statistics.add(binding.statistic)
        if len(clock_domains) != 1:
            raise EmpiricalProbeCostError(
                "all compared probe methods must share one clock actor and segment"
            )
        if len(statistics) != 1:
            raise EmpiricalProbeCostError(
                "all compared probe methods must use the same percentile statistic"
            )

        self._bindings = normalized
        self._profiles: dict[str, dict[str, Any]] = {}
        self._profile_source_digests: dict[str, tuple[str, ...]] = {}
        for method_id, binding in normalized.items():
            matches = [
                profile for profile in self._profile["profiles"]
                if (
                    profile["operation_id"] == binding.operation_id
                    and profile["clock_actor_id"] == binding.clock_actor_id
                    and profile["clock_segment_id"] == binding.clock_segment_id
                    and profile["outcome"] == "succeeded"
                )
            ]
            if len(matches) != 1:
                raise EmpiricalProbeCostError(
                    f"{method_id}: expected exactly one successful operation profile; "
                    f"found {len(matches)}"
                )
            profile = matches[0]
            measured_count = profile["measured_sample_count"]
            if (
                profile["readiness"] != "descriptive_only"
                or isinstance(measured_count, bool)
                or not isinstance(measured_count, int)
                or measured_count < self._minimum_samples
            ):
                raise EmpiricalProbeCostError(
                    f"{method_id}: operation cost profile has insufficient successful samples"
                )
            statistic_value = profile.get(binding.statistic)
            if (
                isinstance(statistic_value, bool)
                or not isinstance(statistic_value, int)
                or statistic_value <= 0
            ):
                raise EmpiricalProbeCostError(
                    f"{method_id}: {binding.statistic} must be a positive integer nanosecond value"
                )
            source_digests = tuple(sorted(
                span["span_digest"]
                for span in self._spans
                if (
                    span["operation_id"] == binding.operation_id
                    and span["clock_actor_id"] == binding.clock_actor_id
                    and span["clock_segment_id"] == binding.clock_segment_id
                    and span["outcome"] == "succeeded"
                    and span["clock_status"] == "measured"
                    and span["elapsed_ns"] is not None
                )
            ))
            if len(source_digests) != measured_count:
                raise EmpiricalProbeCostError(
                    f"{method_id}: measured source-span count does not match its profile"
                )
            self._profiles[method_id] = dict(profile)
            self._profile_source_digests[method_id] = source_digests

        self._profile_digest = self._profile["profile_digest"]
        model_core = {
            "format": "in-formation.empirical-probe-cost-model",
            "schema": "in-formation.empirical-probe-cost-model/0.1",
            "profile_digest": self._profile_digest,
            "minimum_samples": self._minimum_samples,
            "bindings": [
                {
                    "method_id": binding.method_id,
                    "operation_id": binding.operation_id,
                    "clock_actor_id": binding.clock_actor_id,
                    "clock_segment_id": binding.clock_segment_id,
                    "statistic": binding.statistic,
                }
                for binding in sorted(normalized.values(), key=lambda item: item.method_id)
            ],
            "cost_unit": "nanoseconds",
            "policy_effect": "candidate_cost_only",
        }
        self._model_core = model_core
        self._model_digest = _digest(model_core)

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def profile_digest(self) -> str:
        return self._profile_digest

    @property
    def clock_domain(self) -> tuple[str, str]:
        binding = next(iter(self._bindings.values()))
        return binding.clock_actor_id, binding.clock_segment_id

    def provenance_for(self, method_id: str) -> dict[str, Any]:
        """Return the measured basis for a single method's exact cost."""
        method_id = _text(method_id, "method_id")
        binding = self._bindings.get(method_id)
        if binding is None:
            raise EmpiricalProbeCostError(f"no empirical cost binding for method: {method_id}")
        profile = self._profiles[method_id]
        value = profile[binding.statistic]
        return {
            "method_id": method_id,
            "operation_id": binding.operation_id,
            "clock_actor_id": binding.clock_actor_id,
            "clock_segment_id": binding.clock_segment_id,
            "outcome": "succeeded",
            "statistic": binding.statistic,
            "cost_value_ns": value,
            "cost_exact": {"numerator": value, "denominator": 1},
            "measured_sample_count": profile["measured_sample_count"],
            "minimum_samples": self._minimum_samples,
            "profile_digest": self._profile_digest,
            "model_digest": self._model_digest,
            "source_span_digests": list(self._profile_source_digests[method_id]),
            "measurement_scope": self._profile["measurement_scope"],
            "interpretation_limits": list(self._profile["interpretation_limits"]),
        }

    def apply_all(self, probes: Sequence[object]) -> AppliedProbeCosts:
        """Return copies of probes with measured nanosecond costs and provenance."""
        if not isinstance(probes, (tuple, list)) or not probes:
            raise EmpiricalProbeCostError("probes must be a non-empty sequence")
        calibrated = []
        records = []
        for index, probe in enumerate(probes):
            method_id = _text(getattr(probe, "label", None), f"probes[{index}].label")
            record = self.provenance_for(method_id)
            try:
                calibrated_probe = replace(
                    probe,
                    cost=Fraction(record["cost_value_ns"], 1),
                )
            except (TypeError, ValueError) as exc:
                raise EmpiricalProbeCostError(
                    f"probe {method_id} must be a dataclass supporting cost replacement"
                ) from exc
            calibrated.append(calibrated_probe)
            records.append(record)
        return AppliedProbeCosts(tuple(calibrated), tuple(records))

    def to_dict(self) -> dict[str, Any]:
        """Portable model declaration; source spans remain separately addressable."""
        return {
            **self._model_core,
            "model_digest": self._model_digest,
            "profile_source_span_digests": list(self._profile["source_span_digests"]),
            "bindings": list(self._model_core["bindings"]),
            "method_costs": [
                self.provenance_for(method_id)
                for method_id in sorted(self._bindings)
            ],
        }


__all__ = [
    "EmpiricalProbeCostError",
    "ProbeCostBinding",
    "AppliedProbeCosts",
    "EmpiricalProbeCostModel",
]
