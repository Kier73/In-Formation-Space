"""Verify inline Encounter Envelopes and Authority Lineage for robust policy steps.

RIV-017 reconstructs an authorized, interpreted prefix of a robust adaptive
policy. RIV-018 adds inline Encounter Envelope integrity and per-source
evidence reconstruction, then records each AUTHORIZED path decision in an
append-only Authority Lineage ledger. It deliberately uses a generic
robust-policy observation payload, not RIV-013's reference-standard-specific
schema.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.robust-policy-envelope-authority/0.1"
SCHEMA = "in-formation.robust-policy-envelope-authority/0.1"
CANONICALIZATION = "json-sort-keys-utf8-v1"
EVENT_KIND = "robust-policy-observation"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_FIELDS = {
    "attempt_id", "observation_id", "event", "source", "channel",
    "sequence", "payload_digest", "payload_value",
}
_RETURN_BINDINGS = (
    "policy_report_digest",
    "policy_state_digest",
    "policy_node_digest",
    "outcome_history_prefix",
    "sensor_id",
    "dimension",
    "measurement_cost",
    "observed_outcome",
)


class RobustPolicyEvidenceVerificationError(ValueError):
    """Invalid Encounter Envelope, source evidence, or Authority Lineage."""


class RobustPolicyEvidenceMismatch(RobustPolicyEvidenceVerificationError):
    """Envelope or source evidence conflicts with the authorized policy path."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load required module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[2]
_POLICY_DIR = Path(__file__).resolve().parent
for _directory in (
    _POLICY_DIR,
    _ROOT / "bridges" / "observation-path",
    _ROOT / "bridges" / "authority-lineage",
    _ROOT / "formats" / "encounter-envelope",
):
    _directory_text = str(_directory)
    if _directory_text not in sys.path:
        sys.path.insert(0, _directory_text)

from robust_policy_execution import (  # noqa: E402
    validate_robust_policy_execution_record,
)

_AUTHORITY = _load_module(
    "authority_lineage",
    _ROOT / "bridges" / "authority-lineage" / "authority_lineage.py",
)
_OBSERVATION_ADAPTER = _load_module(
    "observation_adapter",
    _ROOT / "bridges" / "authority-lineage" / "observation_adapter.py",
)
_ENCOUNTER = _load_module(
    "robust_policy_encounter_envelope_validator",
    _ROOT / "formats" / "encounter-envelope" / "validate_envelope.py",
)


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise RobustPolicyEvidenceVerificationError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise RobustPolicyEvidenceVerificationError(
            f"{label} must be finite JSON data"
        ) from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _HEX_256.fullmatch(value) is None:
        raise RobustPolicyEvidenceVerificationError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise RobustPolicyEvidenceVerificationError(
            f"{label} must be non-empty text without NUL"
        )
    return value.strip()


def _validate_execution_record(raw: object) -> dict[str, Any]:
    try:
        return validate_robust_policy_execution_record(raw)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise RobustPolicyEvidenceVerificationError(
            f"RIV-017 execution record failed reconstruction: {error}"
        ) from error


def _normalize_source_records(
    raw: object,
    *,
    attempt_id: str,
    logical_time: int,
) -> list[dict[str, Any]]:
    if not isinstance(raw, (tuple, list)) or not raw:
        raise RobustPolicyEvidenceVerificationError(
            "Encounter Envelope payload.value.source_evidence_records must be non-empty"
        )
    expected_event = {"kind": EVENT_KIND, "logical_time": logical_time}
    normalized = []
    seen_sources = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != _SOURCE_FIELDS:
            raise RobustPolicyEvidenceVerificationError(
                f"source_evidence_records[{index}] must contain exactly {sorted(_SOURCE_FIELDS)}"
            )
        if item["attempt_id"] != attempt_id or item["observation_id"] != attempt_id:
            raise RobustPolicyEvidenceMismatch(
                f"source_evidence_records[{index}] belongs to another attempt/observation"
            )
        if not isinstance(item["event"], Mapping) or dict(item["event"]) != expected_event:
            raise RobustPolicyEvidenceMismatch(
                f"source_evidence_records[{index}] belongs to another logical event"
            )
        source = _text(item["source"], f"source_evidence_records[{index}].source")
        channel = _text(item["channel"], f"source_evidence_records[{index}].channel")
        sequence = item["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise RobustPolicyEvidenceVerificationError(
                f"source_evidence_records[{index}].sequence must be a positive integer"
            )
        if source in seen_sources:
            raise RobustPolicyEvidenceVerificationError(
                f"duplicate source evidence record for {source!r}"
            )
        seen_sources.add(source)
        payload_value = _copy_json(
            item["payload_value"],
            f"source_evidence_records[{index}].payload_value",
        )
        payload_digest = _sha256(
            item["payload_digest"],
            f"source_evidence_records[{index}].payload_digest",
        )
        if _digest(payload_value) != payload_digest:
            raise RobustPolicyEvidenceMismatch(
                f"source_evidence_records[{index}] digest does not match payload_value"
            )
        normalized.append({
            "attempt_id": attempt_id,
            "observation_id": attempt_id,
            "event": expected_event,
            "source": source,
            "channel": channel,
            "sequence": sequence,
            "payload_digest": payload_digest,
            "payload_value": payload_value,
        })
    return sorted(normalized, key=lambda row: row["source"])


def _validate_envelope_for_path(
    raw: object,
    *,
    path_snapshot: Mapping[str, Any],
    execution_manifest: Mapping[str, Any],
    logical_time: int,
):
    if not isinstance(raw, Mapping):
        raise TypeError("each Encounter Envelope must be a mapping")
    envelope = _copy_json(raw, "Encounter Envelope")
    valid, errors = _ENCOUNTER.validate_encounter(envelope)
    if not valid:
        raise RobustPolicyEvidenceVerificationError(
            "Encounter Envelope is structurally invalid: " + "; ".join(errors)
        )
    integrity_status, detail = _ENCOUNTER.verify_integrity(envelope)
    if integrity_status != "VERIFIED":
        raise RobustPolicyEvidenceVerificationError(
            f"Encounter Envelope integrity must be VERIFIED, got {integrity_status}: {detail}"
        )
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("value"), Mapping):
        raise RobustPolicyEvidenceVerificationError(
            "RIV-018 requires an inline Encounter Envelope payload.value object"
        )
    value = payload["value"]
    returned_matches = [
        row for row in path_snapshot["events"]
        if row["stage"] == "returned"
    ]
    if len(returned_matches) != 1:
        raise RobustPolicyEvidenceVerificationError(
            "executed ObservationPath must have exactly one returned event"
        )
    returned_details = returned_matches[0]["details"]
    if envelope["id"] != returned_details.get("encounter_id"):
        raise RobustPolicyEvidenceMismatch(
            "Encounter Envelope id differs from returned encounter_id"
        )
    integrity = envelope["integrity"]
    if integrity.get("canonicalization") != CANONICALIZATION:
        raise RobustPolicyEvidenceVerificationError(
            f"Encounter Envelope canonicalization must be {CANONICALIZATION!r}"
        )
    if returned_details.get("canonicalization") != CANONICALIZATION:
        raise RobustPolicyEvidenceMismatch(
            "ObservationPath canonicalization differs from Encounter Envelope contract"
        )
    if returned_details.get("payload_digest") != integrity.get("digest"):
        raise RobustPolicyEvidenceMismatch(
            "ObservationPath payload digest differs from Encounter Envelope integrity digest"
        )
    for field in _RETURN_BINDINGS:
        if value.get(field) != returned_details.get(field):
            raise RobustPolicyEvidenceMismatch(
                f"Encounter Envelope payload.value.{field} differs from returned ObservationPath"
            )
        if execution_manifest.get(field) != returned_details.get(field):
            raise RobustPolicyEvidenceMismatch(
                f"Encounter Envelope payload.value.{field} differs from reconstructed RIV-017 execution manifest"
            )
    if envelope["source"].get("kind") != "sensor":
        raise RobustPolicyEvidenceMismatch(
            "Encounter Envelope source kind must be 'sensor'"
        )
    if envelope["source"].get("reference") != returned_details["sensor_id"]:
        raise RobustPolicyEvidenceMismatch(
            "Encounter Envelope source reference must identify the selected sensor"
        )
    source_records = _normalize_source_records(
        value.get("source_evidence_records"),
        attempt_id=path_snapshot["attempt_id"],
        logical_time=logical_time,
    )
    summary = {
        "attempt_id": path_snapshot["attempt_id"],
        "encounter_id": envelope["id"],
        "envelope_digest": _digest(envelope),
        "payload_digest": integrity["digest"],
        "integrity_status": integrity_status,
        "canonicalization": CANONICALIZATION,
        "source_kind": envelope["source"]["kind"],
        "source_reference": envelope["source"].get("reference"),
        "source_evidence_count": len(source_records),
        "source_ids": [row["source"] for row in source_records],
        "logical_event": {"kind": EVENT_KIND, "logical_time": logical_time},
    }
    return envelope, source_records, summary


def _validate_authority_fields(
    details: Mapping[str, Any],
    source_records: Sequence[Mapping[str, Any]],
):
    if details.get("decision_status") != "AUTHORIZED":
        raise RobustPolicyEvidenceMismatch(
            "robust policy evidence bundle requires an AUTHORIZED ObservationPath decision"
        )
    observed = details.get("observed_sources")
    dissenting = details.get("dissenting_sources")
    missing = details.get("missing_sources")
    representative = _text(details.get("representative_source"), "authority.representative_source")
    for rows, label in (
        (observed, "authority.observed_sources"),
        (dissenting, "authority.dissenting_sources"),
        (missing, "authority.missing_sources"),
    ):
        if not isinstance(rows, list) or not all(isinstance(row, str) and row.strip() for row in rows):
            raise RobustPolicyEvidenceVerificationError(f"{label} must be a source list")
        if rows != sorted(set(rows)):
            raise RobustPolicyEvidenceVerificationError(f"{label} must be sorted and unique")
    if set(observed) & set(missing):
        raise RobustPolicyEvidenceMismatch(
            "a source cannot be both observed and missing"
        )
    if not set(dissenting).issubset(set(observed)):
        raise RobustPolicyEvidenceMismatch(
            "dissenting sources must be a subset of observed sources"
        )
    evidence_sources = [row["source"] for row in source_records]
    if evidence_sources != observed:
        raise RobustPolicyEvidenceMismatch(
            "Encounter Envelope source records differ from AUTHORIZED observed_sources"
        )
    quorum = details.get("quorum")
    if isinstance(quorum, bool) or not isinstance(quorum, int) or quorum < 1:
        raise RobustPolicyEvidenceVerificationError(
            "authority.quorum must be a positive integer"
        )
    strict = details.get("strict")
    if type(strict) is not bool:
        raise RobustPolicyEvidenceVerificationError(
            "authority.strict must be Boolean"
        )
    winners = sorted(set(observed) - set(dissenting))
    if len(winners) < quorum:
        raise RobustPolicyEvidenceMismatch(
            "AUTHORIZED source evidence does not meet the declared quorum"
        )
    if representative not in winners:
        raise RobustPolicyEvidenceMismatch(
            "authority representative is not in the non-dissenting source set"
        )
    policy_digest = _sha256(details.get("policy_digest"), "authority.policy_digest")
    decision_digest = _sha256(details.get("decision_digest"), "authority.decision_digest")
    return {
        "observed_sources": observed,
        "dissenting_sources": dissenting,
        "missing_sources": missing,
        "representative_source": representative,
        "winners": winners,
        "quorum": quorum,
        "strict": strict,
        "policy_digest": policy_digest,
        "decision_digest": decision_digest,
    }


def build_verified_robust_policy_evidence_bundle(
    *,
    policy_execution_record: Mapping[str, Any],
    encounter_envelopes: Sequence[Mapping[str, Any]],
    authority_ledger_id: str,
    ledger_created_by: str,
) -> dict[str, Any]:
    """Verify each inline policy-step envelope and reconstruct Authority Lineage.

    Exactly one inline Encounter Envelope is required for each executed policy
    path. Logical times are zero-based execution-order coordinates for the
    bundle; they are not physical timestamps or a claim of global clock order.
    """
    execution = _validate_execution_record(policy_execution_record)
    paths = execution["observation_paths"]
    manifests = execution["measurement_manifests"]
    if not isinstance(encounter_envelopes, (tuple, list)) or len(encounter_envelopes) != len(paths):
        raise RobustPolicyEvidenceVerificationError(
            "encounter_envelopes must contain exactly one envelope per executed policy path"
        )
    ledger_id = _text(authority_ledger_id, "authority_ledger_id")
    created_by = _text(ledger_created_by, "ledger_created_by")
    ledger = _AUTHORITY.create_ledger(ledger_id, created_by=created_by)
    verified_envelopes = []
    summaries = []
    receipts = []
    for index, (path, envelope, manifest) in enumerate(
        zip(paths, encounter_envelopes, manifests)
    ):
        envelope_doc, source_records, summary = _validate_envelope_for_path(
            envelope,
            path_snapshot=path,
            execution_manifest=manifest,
            logical_time=index,
        )
        auth_events = [
            row for row in path["events"]
            if row["stage"] == "evidence_authorized"
        ]
        if len(auth_events) != 1:
            raise RobustPolicyEvidenceVerificationError(
                "each executed path requires exactly one evidence_authorized event"
            )
        auth_event = auth_events[0]
        authority = _validate_authority_fields(auth_event["details"], source_records)
        attempt_id = path["attempt_id"]
        event_key = {"kind": EVENT_KIND, "logical_time": index}
        attempt = {
            "attempt_id": attempt_id,
            "observation_id": attempt_id,
            "final_status": "AUTHORIZED",
            "evidence_received_sources": authority["observed_sources"],
            "evidence_received_count": len(source_records),
            "representative_source": authority["representative_source"],
            "evidence_partition": {
                "observed_sources": authority["observed_sources"],
                "source_count": len(source_records),
                "winner_sources": authority["winners"],
                "dissenting_sources": authority["dissenting_sources"],
                "missing_sources": authority["missing_sources"],
            },
        }
        try:
            ledger, decision_id, receipt = _OBSERVATION_ADAPTER.issue_initial_decision_from_attempt(
                ledger,
                attempt,
                source_records,
                event_key=event_key,
                policy_digest=authority["policy_digest"],
                issued_by=auth_event["actor"],
                rationale=(
                    "Authority Lineage decision reconstructed from an AUTHORIZED "
                    "robust-policy ObservationPath and an inline integrity-verified Encounter Envelope."
                ),
            )
        except (TypeError, ValueError, KeyError) as error:
            raise RobustPolicyEvidenceVerificationError(
                f"Authority Lineage rejected robust policy attempt {attempt_id!r}: {error}"
            ) from error
        frontier = _AUTHORITY.decision_frontier(ledger, event_key)
        if frontier["status"] != "SINGLE_DECISION" or frontier["decision_ids"] != [decision_id]:
            raise AssertionError("Authority Lineage did not produce one unique decision frontier")
        decisions = _AUTHORITY.decision_history(ledger, event_key)
        decision = next(row for row in decisions if row["decision_id"] == decision_id)
        if (
            decision["status"] != "AUTHORIZED"
            or decision["evidence_set_digest"] != receipt["evidence_set_digest"]
        ):
            raise AssertionError(
                "Authority Lineage decision differs from reconstructed evidence receipt"
            )
        verified_envelopes.append(envelope_doc)
        summaries.append(summary)
        receipts.append({
            "attempt_id": attempt_id,
            "event_key": event_key,
            "observation_path_authority_evidence_ref": auth_event["evidence_ref"],
            "observation_path_decision_digest": authority["decision_digest"],
            "authority_lineage_decision_id": decision_id,
            "authority_lineage_decision_digest": decision["decision_digest"],
            "authority_lineage_evidence_set_digest": receipt["evidence_set_digest"],
            "authority_lineage_receipt": receipt,
            "verified_envelope_digest": summary["envelope_digest"],
        })
    _AUTHORITY.validate_ledger(ledger)
    core = {
        "format": FORMAT,
        "schema": SCHEMA,
        "policy_execution_record": execution,
        "policy_execution_record_digest": execution["record_digest"],
        "encounter_envelopes": verified_envelopes,
        "encounter_envelope_summaries": summaries,
        "authority_ledger": ledger,
        "authority_ledger_digest": ledger["ledger_digest"],
        "authority_receipts": receipts,
        "verification_status": "robust_policy_envelopes_verified_and_authority_lineage_reconstructed",
        "logical_time_contract": "zero-based execution-path order within this bundle; not physical time or global clock order",
        "trust_boundary": [
            "Each inline Encounter Envelope is structurally validated and its payload digest verified using json-sort-keys-utf8-v1; external references are not fetched.",
            "Every per-source payload_value is independently canonicalized and checked against its own SHA-256 payload_digest before Authority Lineage reconstruction.",
            "The envelope payload is bound to the exact returned ObservationPath details and the independently reconstructed RIV-017 execution manifest.",
            "The authority event is structurally checked for AUTHORIZED status, source-set agreement, dissent partition, representative, quorum, policy digest and decision digest; issuer and sources are not authenticated by this bundle.",
            "The Authority Lineage ledger is reconstructed as an append-only hash chain and each decision is bound to the per-source evidence set; this does not authenticate a signer or trust root.",
            "The supplied finite likelihood ambiguity set may omit the true physical response model. Envelope integrity and authority lineage do not prove model truth.",
            "The RIV-017 scenario-conditioned masses and policy report are unchanged; this bundle adds integrity and authority provenance only.",
            "SHA-256 digests and hash chains provide content integrity and deterministic reconstruction, not source identity authentication, non-repudiation, or physical truth.",
        ],
    }
    return {**core, "bundle_digest": _digest(core)}


def validate_verified_robust_policy_evidence_bundle(
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild all inline envelopes, source records, decisions and ledger entries."""
    if not isinstance(bundle, Mapping):
        raise TypeError("verified robust policy evidence bundle must be a mapping")
    supplied = _copy_json(bundle, "verified robust policy evidence bundle")
    digest = supplied.pop("bundle_digest", None)
    if not isinstance(digest, str) or not _HEX_256.fullmatch(digest) or digest != _digest(supplied):
        raise RobustPolicyEvidenceVerificationError(
            "bundle_digest does not match bundle contents"
        )
    if supplied.get("format") != FORMAT or supplied.get("schema") != SCHEMA:
        raise RobustPolicyEvidenceVerificationError(
            "unsupported robust policy evidence bundle format/schema"
        )
    execution = supplied.get("policy_execution_record")
    ledger = supplied.get("authority_ledger")
    if not isinstance(execution, Mapping) or not isinstance(ledger, Mapping):
        raise RobustPolicyEvidenceVerificationError(
            "bundle omits execution record or authority ledger"
        )
    try:
        _AUTHORITY.validate_ledger(ledger)
    except (TypeError, ValueError, KeyError) as error:
        raise RobustPolicyEvidenceVerificationError(
            f"Authority Lineage ledger failed reconstruction: {error}"
        ) from error
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        raise RobustPolicyEvidenceVerificationError(
            "Authority Lineage ledger has no creation entry"
        )
    ledger_id = entries[0]["payload"]["ledger_id"]
    created_by = entries[0]["actor"]
    rebuilt = build_verified_robust_policy_evidence_bundle(
        policy_execution_record=execution,
        encounter_envelopes=supplied.get("encounter_envelopes"),
        authority_ledger_id=ledger_id,
        ledger_created_by=created_by,
    )
    if rebuilt != dict(bundle):
        raise RobustPolicyEvidenceVerificationError(
            "bundle differs from independent reconstruction from RIV-017 paths, inline Envelopes and per-source records"
        )
    return dict(bundle)


__all__ = [
    "FORMAT",
    "SCHEMA",
    "RobustPolicyEvidenceVerificationError",
    "RobustPolicyEvidenceMismatch",
    "build_verified_robust_policy_evidence_bundle",
    "validate_verified_robust_policy_evidence_bundle",
]
