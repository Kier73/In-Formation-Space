"""Reconstructible information outcomes for deterministic observation models.

Expected mutual information is averaged over every modelled outcome. The
entropy change on one realized branch is reported separately and may be
positive, zero, or negative. Evidence is referenced, not authenticated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.observation-outcome"
SCHEMA = "in-formation.observation-outcome/0.1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOLERANCE = 1e-9
LIMITS = [
    "Predicted outcomes and query values are supplied model claims, not independently established external facts.",
    "Expected information gain is mutual information averaged over every predicted outcome under the supplied prior.",
    "Realized entropy change describes only the observed branch and may be positive, zero, or negative.",
    "A model-mismatching observation has no computed posterior; it is preserved as model_mismatch.",
    "This version assumes deterministic predicted outcomes; noisy likelihood models are not yet represented.",
    "Evidence references and digests are retained but not fetched, authenticated, or validated by this module.",
    "Information metrics do not include operational cost and do not alter an adaptive policy.",
]


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def json_copy(value: object, label: str) -> Any:
    try:
        return json.loads(canonical(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a finite JSON value: {error}") from error


def entropy(probabilities: Sequence[float]) -> float:
    return -sum(p * math.log2(p) for p in probabilities if p > 0.0)


def rounded(value: float) -> float:
    value = round(value, 12)
    return 0.0 if value == 0 else value


def normalize_hypotheses(hypotheses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(hypotheses, (list, tuple)) or not hypotheses:
        raise ValueError("prior_hypotheses must be a non-empty sequence")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    query_values: list[object] = []
    total = 0.0
    required = {"hypothesis_id", "prior_probability", "predicted_outcome"}
    allowed = required | {"query_value"}
    for index, raw in enumerate(hypotheses):
        if not isinstance(raw, Mapping) or not required.issubset(raw) or set(raw) - allowed:
            raise ValueError(f"prior_hypotheses[{index}] has missing or unexpected fields")
        hypothesis_id = text(raw["hypothesis_id"], f"prior_hypotheses[{index}].hypothesis_id")
        if hypothesis_id in seen:
            raise ValueError(f"duplicate hypothesis_id: {hypothesis_id}")
        seen.add(hypothesis_id)
        raw_probability = raw["prior_probability"]
        if isinstance(raw_probability, bool) or not isinstance(raw_probability, (int, float)):
            raise ValueError(f"prior_probability for {hypothesis_id} must be numeric")
        probability = float(raw_probability)
        if not math.isfinite(probability) or not 0.0 < probability <= 1.0:
            raise ValueError(f"prior_probability for {hypothesis_id} must be in (0, 1]")
        predicted = json_copy(raw["predicted_outcome"], f"predicted_outcome for {hypothesis_id}")
        query_value = raw.get("query_value")
        if query_value is not None and not isinstance(query_value, bool):
            raise ValueError(f"query_value for {hypothesis_id} must be Boolean or null")
        query_values.append(query_value)
        total += probability
        normalized.append({
            "hypothesis_id": hypothesis_id,
            "prior_probability": probability,
            "predicted_outcome": predicted,
            "query_value": query_value,
        })
    if not math.isclose(total, 1.0, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
        raise ValueError("prior probabilities must sum to 1")
    if any(v is None for v in query_values) and any(v is not None for v in query_values):
        raise ValueError("query_value must be supplied for every hypothesis or for none")
    normalized = [
        {**item, "prior_probability": item["prior_probability"] / total}
        for item in normalized
    ]
    return sorted(normalized, key=lambda item: item["hypothesis_id"])


def analyze(hypotheses: list[dict[str, Any]], observed_outcome: Any) -> dict[str, Any]:
    prior_entropy = entropy([item["prior_probability"] for item in hypotheses])
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in hypotheses:
        groups.setdefault(canonical(item["predicted_outcome"]), []).append(item)

    expected_posterior_entropy = 0.0
    has_query = hypotheses[0]["query_value"] is not None
    expected_query_resolution = 0.0 if has_query else None
    observed_key = canonical(observed_outcome)
    observed_group = None
    observed_mass = None

    for key, group in groups.items():
        mass = sum(item["prior_probability"] for item in group)
        expected_posterior_entropy += mass * entropy(
            [item["prior_probability"] / mass for item in group]
        )
        if key == observed_key:
            observed_group, observed_mass = group, mass
        if has_query and len({item["query_value"] for item in group}) == 1:
            expected_query_resolution += mass

    # I(H;O) = H(H) - E_O[H(H|O)] for this deterministic model.
    # Clamp numerical roundoff only; never clamp the realized branch delta.
    expected_information_gain = max(0.0, prior_entropy - expected_posterior_entropy)
    posterior = []
    posterior_entropy = None
    realized_entropy_change = None
    query_status = "not_scoped" if not has_query else "model_mismatch"
    query_value = None

    if observed_group is not None and observed_mass is not None:
        posterior = [
            {
                "hypothesis_id": item["hypothesis_id"],
                "probability": item["prior_probability"] / observed_mass,
            }
            for item in observed_group
        ]
        posterior_entropy = entropy([item["probability"] for item in posterior])
        realized_entropy_change = posterior_entropy - prior_entropy
        if has_query:
            values = {item["query_value"] for item in observed_group}
            if len(values) == 1:
                query_value = next(iter(values))
                query_status = "resolved"
            else:
                query_status = "undetermined"

    return {
        "prior_entropy_bits": rounded(prior_entropy),
        "expected_posterior_entropy_bits": rounded(expected_posterior_entropy),
        "expected_information_gain_bits": rounded(expected_information_gain),
        "expected_query_resolution_probability": (
            None if expected_query_resolution is None else round(expected_query_resolution, 12)
        ),
        "observed_outcome_probability": (
            None if observed_mass is None else round(observed_mass, 12)
        ),
        "posterior_entropy_bits": None if posterior_entropy is None else rounded(posterior_entropy),
        "realized_entropy_change_bits": (
            None if realized_entropy_change is None else rounded(realized_entropy_change)
        ),
        "posterior": posterior,
        "model_status": "matched" if observed_group is not None else "model_mismatch",
        "query_status": query_status,
        "query_value": query_value,
    }


def build_observation_outcome(
    *,
    attempt_id: str,
    observation_id: str,
    evidence_ref: str,
    evidence_digest: str,
    model_ref: str,
    prior_hypotheses: Sequence[Mapping[str, Any]],
    observed_outcome: Any,
) -> dict[str, Any]:
    """Build a deterministic observation record and derived information metrics."""
    attempt_id = text(attempt_id, "attempt_id")
    observation_id = text(observation_id, "observation_id")
    evidence_ref = text(evidence_ref, "evidence_ref")
    evidence_digest = text(evidence_digest, "evidence_digest")
    model_ref = text(model_ref, "model_ref")
    if SHA256.fullmatch(evidence_digest) is None:
        raise ValueError("evidence_digest must be a lowercase SHA-256 hex digest")
    hypotheses = normalize_hypotheses(prior_hypotheses)
    prior_model = {"hypotheses": hypotheses}
    observed = json_copy(observed_outcome, "observed_outcome")
    core = {
        "format": FORMAT,
        "schema": SCHEMA,
        "attempt_id": attempt_id,
        "observation_id": observation_id,
        "evidence_ref": evidence_ref,
        "evidence_digest": evidence_digest,
        "model_ref": model_ref,
        "model_digest": digest(prior_model),
        "prior_model": prior_model,
        "observed_outcome": observed,
        "analysis": analyze(hypotheses, observed),
        "interpretation_limits": list(LIMITS),
    }
    return {**core, "outcome_digest": digest(core)}


def validate_observation_outcome(document: Mapping[str, Any]) -> dict[str, Any]:
    """Independently rebuild metrics and digests, requiring exact equality."""
    if not isinstance(document, Mapping):
        raise TypeError("observation outcome must be a mapping")
    required = {
        "format", "schema", "attempt_id", "observation_id", "evidence_ref",
        "evidence_digest", "model_ref", "model_digest", "prior_model",
        "observed_outcome", "analysis", "interpretation_limits", "outcome_digest",
    }
    if set(document) != required:
        raise ValueError("observation outcome fields are incomplete or unexpected")
    if document["format"] != FORMAT or document["schema"] != SCHEMA:
        raise ValueError("unsupported observation-outcome format or schema")
    prior_model = document["prior_model"]
    if not isinstance(prior_model, Mapping) or set(prior_model) != {"hypotheses"}:
        raise ValueError("prior_model must contain exactly a hypotheses array")
    rebuilt = build_observation_outcome(
        attempt_id=document["attempt_id"],
        observation_id=document["observation_id"],
        evidence_ref=document["evidence_ref"],
        evidence_digest=document["evidence_digest"],
        model_ref=document["model_ref"],
        prior_hypotheses=prior_model["hypotheses"],
        observed_outcome=document["observed_outcome"],
    )
    if rebuilt != dict(document):
        raise ValueError("observation outcome differs from independent reconstruction")
    return dict(document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a digest-checked information-outcome record from a deterministic observation model."
    )
    parser.add_argument("--input", required=True, metavar="JSON", help="JSON request with model and observed outcome")
    parser.add_argument("--output", metavar="JSON", help="write the record here (default: stdout)")
    args = parser.parse_args(argv)
    try:
        request = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(request, Mapping):
            raise ValueError("input document must be a JSON object")
        document = build_observation_outcome(
            attempt_id=request["attempt_id"],
            observation_id=request["observation_id"],
            evidence_ref=request["evidence_ref"],
            evidence_digest=request["evidence_digest"],
            model_ref=request["model_ref"],
            prior_hypotheses=request["prior_hypotheses"],
            observed_outcome=request["observed_outcome"],
        )
        validate_observation_outcome(document)
        rendered = json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
