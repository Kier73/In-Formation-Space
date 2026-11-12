"""Exhaustive finite authority-rule comparison for four binary evidence sources.

Each source is absent, supports HIT, or supports MISS. The 3**4 states are
enumerated exactly; no probabilities are assigned to patterns.
"""
from __future__ import annotations

from itertools import product
from typing import Any, Mapping, Sequence

SOURCES = ("S00", "S01", "S02", "S03")
SOURCE_STATES = ("-", "H", "M")
QUORUM = 2
CONFIGURED_MAJORITY = len(SOURCES) // 2 + 1

POLICY_NAMES = (
    "runtime_strict",
    "runtime_permissive",
    "observed_unanimity_quorum",
    "unique_plurality_quorum",
    "observed_strict_majority",
    "configured_majority",
    "plurality_margin_two",
    "complete_roster_unique_plurality",
)

POLICY_DESCRIPTIONS = {
    "runtime_strict": (
        "Pinned E-CPU strict=True: all configured sources must be present, "
        "all observed values must agree, and quorum must be met."
    ),
    "runtime_permissive": (
        "Pinned E-CPU strict=False: authorize whenever the deterministically "
        "selected largest group reaches quorum, including tied groups."
    ),
    "observed_unanimity_quorum": (
        "Require at least quorum agreeing sources and no observed dissent; "
        "unobserved configured sources are allowed."
    ),
    "unique_plurality_quorum": (
        "Require a unique largest evidence group of at least quorum; missing "
        "sources and dissenting minorities are allowed, exact top ties abstain."
    ),
    "observed_strict_majority": (
        "Require the largest group to meet quorum and exceed half of all "
        "observed sources; exact ties and non-majorities do not authorize."
    ),
    "configured_majority": (
        "Require a unique group of at least ceil(N/2) + 1 configured sources; "
        "missing sources are allowed, dissenting sources do not count for it."
    ),
    "plurality_margin_two": (
        "Require the largest group to meet quorum and lead the runner-up by "
        "at least two sources; smaller margins are treated as conflict."
    ),
    "complete_roster_unique_plurality": (
        "Require every configured source to have reported, then require a "
        "unique winning group of at least quorum; dissent may be retained."
    ),
}


def evidence_counts(pattern: Sequence[str]) -> dict[str, Any]:
    if len(pattern) != len(SOURCES):
        raise ValueError(f"pattern must contain exactly {len(SOURCES)} source states")
    if any(state not in SOURCE_STATES for state in pattern):
        raise ValueError("source state must be one of absent '-', hit 'H', or miss 'M'")
    hit = pattern.count("H")
    miss = pattern.count("M")
    observed = hit + miss
    top = max(hit, miss)
    runner = min(hit, miss)
    tied = hit > 0 and miss > 0 and hit == miss
    return {
        "pattern": "".join(pattern),
        "source_states": {source: state for source, state in zip(SOURCES, pattern)},
        "hit_count": hit,
        "miss_count": miss,
        "observed_count": observed,
        "missing_count": len(SOURCES) - observed,
        "top_count": top,
        "runner_up_count": runner,
        "top_tie": tied,
        "dissent_present": hit > 0 and miss > 0,
        "all_observed_agree": observed > 0 and (hit == 0 or miss == 0),
        "full_roster": observed == len(SOURCES),
        "canonical_runtime_tie_value": "MISS" if tied else None,
    }


def _result(status: str, reason: str) -> dict[str, str]:
    return {"status": status, "reason": reason}


def evaluate_policy(name: str, counts: Mapping[str, Any]) -> dict[str, str]:
    hit = counts["hit_count"]
    miss = counts["miss_count"]
    observed = counts["observed_count"]
    missing = counts["missing_count"]
    top = counts["top_count"]
    runner = counts["runner_up_count"]
    tied = counts["top_tie"]
    dissent = counts["dissent_present"]
    full = counts["full_roster"]
    if name == "runtime_strict":
        if dissent:
            return _result("CONFLICT", "strict policy treats any observed dissent as conflict")
        if top < QUORUM or missing:
            return _result("REFUSED", "strict policy lacks complete source coverage and quorum")
        return _result("AUTHORIZED", "all configured sources agree and quorum is met")
    if name == "runtime_permissive":
        if top < QUORUM:
            return _result("REFUSED", "no evidence group reaches quorum")
        return _result(
            "AUTHORIZED",
            "permissive policy authorizes the canonical largest group, including a tied top",
        )
    if name == "observed_unanimity_quorum":
        if top < QUORUM:
            return _result("REFUSED", "no agreeing group reaches quorum")
        if dissent:
            return _result("CONFLICT", "observed sources do not agree unanimously")
        return _result("AUTHORIZED", "observed sources agree and quorum is met")
    if name == "unique_plurality_quorum":
        if top < QUORUM:
            return _result("REFUSED", "no evidence group reaches quorum")
        if tied:
            return _result("CONFLICT", "top evidence groups are tied")
        return _result("AUTHORIZED", "a unique largest group reaches quorum")
    if name == "observed_strict_majority":
        if top < QUORUM:
            return _result("REFUSED", "no evidence group reaches quorum")
        if 2 * top <= observed:
            return _result("CONFLICT", "largest group is not a strict majority of observed sources")
        return _result("AUTHORIZED", "largest group is a strict majority of observed sources")
    if name == "configured_majority":
        if tied:
            return _result("CONFLICT", "top evidence groups are tied")
        if top < CONFIGURED_MAJORITY:
            return _result("REFUSED", "no group reaches a majority of configured sources")
        return _result("AUTHORIZED", "one group holds a majority of configured sources")
    if name == "plurality_margin_two":
        if top < QUORUM:
            return _result("REFUSED", "no evidence group reaches quorum")
        if top - runner < 2:
            return _result("CONFLICT", "winner does not lead the runner-up by two sources")
        return _result("AUTHORIZED", "largest group meets quorum and two-source margin")
    if name == "complete_roster_unique_plurality":
        if not full:
            return _result("REFUSED", "not all configured sources have reported")
        if top < QUORUM:
            return _result("REFUSED", "no evidence group reaches quorum")
        if tied:
            return _result("CONFLICT", "top evidence groups are tied")
        return _result("AUTHORIZED", "complete roster has a unique quorum-sized plurality")
    raise ValueError(f"unknown authority policy: {name}")


def enumerate_evidence_space() -> list[dict[str, Any]]:
    records = []
    for pattern in product(SOURCE_STATES, repeat=len(SOURCES)):
        counts = evidence_counts(pattern)
        decisions = {
            name: evaluate_policy(name, counts)
            for name in POLICY_NAMES
        }
        records.append({
            **counts,
            "decisions": decisions,
        })
    return records


def summarize_policy_space(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(records) != len(SOURCE_STATES) ** len(SOURCES):
        raise ValueError("policy-space report must contain every finite evidence pattern exactly once")
    expected_patterns = {"".join(pattern) for pattern in product(SOURCE_STATES, repeat=len(SOURCES))}
    actual_patterns = [record.get("pattern") for record in records]
    if len(set(actual_patterns)) != len(actual_patterns) or set(actual_patterns) != expected_patterns:
        raise ValueError("policy-space report has missing, duplicate, or unknown patterns")
    summary: dict[str, Any] = {}
    for name in POLICY_NAMES:
        status_counts = {
            status: sum(record["decisions"][name]["status"] == status for record in records)
            for status in ("AUTHORIZED", "CONFLICT", "REFUSED")
        }
        summary[name] = {
            "description": POLICY_DESCRIPTIONS[name],
            "state_counts": status_counts,
            "authorized_with_missing_sources": sum(
                record["decisions"][name]["status"] == "AUTHORIZED"
                and record["missing_count"] > 0
                for record in records
            ),
            "authorized_with_dissent": sum(
                record["decisions"][name]["status"] == "AUTHORIZED"
                and record["dissent_present"]
                for record in records
            ),
            "authorized_on_exact_top_tie": sum(
                record["decisions"][name]["status"] == "AUTHORIZED"
                and record["top_tie"]
                for record in records
            ),
            "unanimous_partial_patterns_authorized": sum(
                record["decisions"][name]["status"] == "AUTHORIZED"
                and record["all_observed_agree"]
                and 0 < record["observed_count"] < len(SOURCES)
                for record in records
            ),
        }
    return {
        "source_ids": list(SOURCES),
        "source_states": list(SOURCE_STATES),
        "source_count": len(SOURCES),
        "quorum": QUORUM,
        "configured_majority": CONFIGURED_MAJORITY,
        "pattern_count": len(records),
        "probability_assignment": None,
        "interpretation": (
            "Counts enumerate a finite state space; they are not frequencies, "
            "priors, likelihoods, or estimated probabilities."
        ),
        "policies": summary,
    }


def validate_policy_space(
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> None:
    rebuilt_records = enumerate_evidence_space()
    if list(records) != rebuilt_records:
        raise ValueError("policy-space records differ from exhaustive reconstruction")
    rebuilt_summary = summarize_policy_space(rebuilt_records)
    if dict(summary) != rebuilt_summary:
        raise ValueError("policy-space summary differs from exhaustive reconstruction")
