"""Finite state-space comparison for explicit revision-review policies.

The proposer is R00; R01 and R02 are independent review participants.
Each participant is ABSENT, APPROVE, REJECT, or ABSTAIN. No reviewer
reliability probabilities are assigned.
"""
from __future__ import annotations

from itertools import product
from typing import Any, Mapping, Sequence

REVIEWERS = ("R00", "R01", "R02")
PROPOSER = "R00"
REVIEW_STATES = ("ABSENT", "APPROVE", "REJECT", "ABSTAIN")
OUTCOMES = ("ACCEPTED", "REJECTED", "INCONCLUSIVE")

POLICIES: dict[str, dict[str, Any]] = {
    "single_approval_permissive": {
        "include_proposer": True,
        "minimum_distinct_reviewers": 1,
        "approvals_required": 1,
        "rejections_required": 3,
        "description": "One approval is sufficient; rejection requires all three reviewers.",
    },
    "simple_majority_three": {
        "include_proposer": True,
        "minimum_distinct_reviewers": 2,
        "approvals_required": 2,
        "rejections_required": 2,
        "description": "Two approvals or two rejections; split and underspecified reviews remain inconclusive.",
    },
    "two_approval_veto": {
        "include_proposer": True,
        "minimum_distinct_reviewers": 2,
        "approvals_required": 2,
        "rejections_required": 1,
        "description": "Two approvals are required, but a single rejection blocks acceptance.",
    },
    "unanimous_three": {
        "include_proposer": True,
        "minimum_distinct_reviewers": 3,
        "approvals_required": 3,
        "rejections_required": 1,
        "description": "All three must approve; any rejection rejects the proposal.",
    },
    "independent_two_of_two": {
        "include_proposer": False,
        "minimum_distinct_reviewers": 2,
        "approvals_required": 2,
        "rejections_required": 2,
        "description": "The proposer cannot review; both independent reviewers must agree.",
    },
    "independent_two_of_two_veto": {
        "include_proposer": False,
        "minimum_distinct_reviewers": 2,
        "approvals_required": 2,
        "rejections_required": 1,
        "description": "The proposer cannot review; both independent reviewers must approve and one rejection is a veto.",
    },
    "independent_one_of_two": {
        "include_proposer": False,
        "minimum_distinct_reviewers": 1,
        "approvals_required": 1,
        "rejections_required": 2,
        "description": "The proposer cannot review; one independent approval suffices, while both reject to refuse.",
    },
}


def _validate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "include_proposer",
        "minimum_distinct_reviewers",
        "approvals_required",
        "rejections_required",
        "description",
    }
    if set(policy) != required:
        raise ValueError("review policy fields differ from the declared schema")
    if type(policy["include_proposer"]) is not bool:
        raise ValueError("include_proposer must be Boolean")
    for field in (
        "minimum_distinct_reviewers", "approvals_required", "rejections_required"
    ):
        value = policy[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must be a positive integer")
        if value > len(REVIEWERS):
            raise ValueError(f"{field} exceeds the configured reviewer count")
    if not isinstance(policy["description"], str) or not policy["description"].strip():
        raise ValueError("review policy description must be non-empty")
    return dict(policy)


def review_counts(pattern: Sequence[str]) -> dict[str, Any]:
    if len(pattern) != len(REVIEWERS):
        raise ValueError(f"review pattern must contain exactly {len(REVIEWERS)} reviewer states")
    if any(state not in REVIEW_STATES for state in pattern):
        raise ValueError("review state must be ABSENT, APPROVE, REJECT, or ABSTAIN")
    return {
        "pattern": tuple(pattern),
        "reviewer_states": {
            reviewer: state for reviewer, state in zip(REVIEWERS, pattern)
        },
        "present_reviewers": [
            reviewer for reviewer, state in zip(REVIEWERS, pattern)
            if state != "ABSENT"
        ],
        "approvers": [
            reviewer for reviewer, state in zip(REVIEWERS, pattern)
            if state == "APPROVE"
        ],
        "rejectors": [
            reviewer for reviewer, state in zip(REVIEWERS, pattern)
            if state == "REJECT"
        ],
        "abstainers": [
            reviewer for reviewer, state in zip(REVIEWERS, pattern)
            if state == "ABSTAIN"
        ],
    }


def evaluate_review_policy(
    policy_name: str,
    pattern: Sequence[str],
) -> dict[str, Any]:
    if policy_name not in POLICIES:
        raise ValueError(f"unknown review policy: {policy_name}")
    policy = _validate_policy(POLICIES[policy_name])
    counts = review_counts(pattern)
    eligible_reviewers = [
        reviewer for reviewer in REVIEWERS
        if policy["include_proposer"] or reviewer != PROPOSER
    ]
    eligible_states = {
        reviewer: counts["reviewer_states"][reviewer]
        for reviewer in eligible_reviewers
    }
    present = [
        reviewer for reviewer, state in eligible_states.items()
        if state != "ABSENT"
    ]
    approvals = [
        reviewer for reviewer, state in eligible_states.items()
        if state == "APPROVE"
    ]
    rejections = [
        reviewer for reviewer, state in eligible_states.items()
        if state == "REJECT"
    ]
    abstentions = [
        reviewer for reviewer, state in eligible_states.items()
        if state == "ABSTAIN"
    ]

    if len(present) < policy["minimum_distinct_reviewers"]:
        outcome = "INCONCLUSIVE"
        reason = "insufficient_distinct_reviewers"
    else:
        approve_threshold = len(approvals) >= policy["approvals_required"]
        reject_threshold = len(rejections) >= policy["rejections_required"]
        if approve_threshold and reject_threshold:
            outcome = "INCONCLUSIVE"
            reason = "conflicting_approval_and_rejection_thresholds"
        elif approve_threshold:
            outcome = "ACCEPTED"
            reason = "approval_threshold_met"
        elif reject_threshold:
            outcome = "REJECTED"
            reason = "rejection_threshold_met"
        else:
            outcome = "INCONCLUSIVE"
            reason = "no_decision_threshold_met"

    return {
        "outcome": outcome,
        "reason": reason,
        "eligible_reviewers": eligible_reviewers,
        "present_eligible_reviewers": present,
        "approval_count": len(approvals),
        "rejection_count": len(rejections),
        "abstention_count": len(abstentions),
        "proposer_vote_counted": (
            policy["include_proposer"]
            and counts["reviewer_states"][PROPOSER] != "ABSENT"
        ),
        "conflicting_thresholds": reason == "conflicting_approval_and_rejection_thresholds",
    }


def enumerate_review_space() -> list[dict[str, Any]]:
    records = []
    for pattern in product(REVIEW_STATES, repeat=len(REVIEWERS)):
        counts = review_counts(pattern)
        records.append({
            "pattern": list(pattern),
            "reviewer_states": counts["reviewer_states"],
            "present_reviewers": counts["present_reviewers"],
            "approvers": counts["approvers"],
            "rejectors": counts["rejectors"],
            "abstainers": counts["abstainers"],
            "decisions": {
                name: evaluate_review_policy(name, pattern)
                for name in POLICIES
            },
        })
    return records


def summarize_review_space(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_patterns = {
        tuple(pattern)
        for pattern in product(REVIEW_STATES, repeat=len(REVIEWERS))
    }
    actual_patterns = [tuple(record.get("pattern", ())) for record in records]
    if (
        len(records) != len(expected_patterns)
        or len(set(actual_patterns)) != len(actual_patterns)
        or set(actual_patterns) != expected_patterns
    ):
        raise ValueError("review-space records do not cover each finite pattern exactly once")

    policies: dict[str, Any] = {}
    for name, policy in POLICIES.items():
        decisions = [record["decisions"][name] for record in records]
        policies[name] = {
            "description": policy["description"],
            "policy": {
                key: value for key, value in policy.items() if key != "description"
            },
            "outcome_counts": {
                outcome: sum(item["outcome"] == outcome for item in decisions)
                for outcome in OUTCOMES
            },
            "accepted_with_proposer_vote": sum(
                item["outcome"] == "ACCEPTED" and item["proposer_vote_counted"]
                for item in decisions
            ),
            "accepted_with_abstention": sum(
                item["outcome"] == "ACCEPTED" and item["abstention_count"] > 0
                for item in decisions
            ),
            "inconclusive_due_to_insufficient_reviewers": sum(
                item["reason"] == "insufficient_distinct_reviewers"
                for item in decisions
            ),
            "inconclusive_due_to_conflicting_thresholds": sum(
                item["conflicting_thresholds"] for item in decisions
            ),
        }
    return {
        "reviewers": list(REVIEWERS),
        "proposer": PROPOSER,
        "review_states": list(REVIEW_STATES),
        "pattern_count": len(records),
        "policy_count": len(POLICIES),
        "probability_assignment": None,
        "interpretation": (
            "Every reviewer-state pattern is enumerated once. Counts are finite "
            "configuration coverage, not vote probabilities, frequencies, or reliability estimates."
        ),
        "policies": policies,
    }


def validate_review_space(
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> None:
    rebuilt = enumerate_review_space()
    if list(records) != rebuilt:
        raise ValueError("review-space records differ from exhaustive reconstruction")
    if dict(summary) != summarize_review_space(rebuilt):
        raise ValueError("review-space summary differs from exhaustive reconstruction")
