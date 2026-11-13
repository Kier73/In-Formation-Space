"""Verify inline reference Encounter Envelopes and bind source evidence to authority lineage.

RIV-012 reconstructs an authorized interpreted policy prefix. RIV-013 adds
another evidence layer: the caller must supply each inline Encounter Envelope,
the envelope payload digest must verify over its exact declared canonicalization,
and its per-source evidence records must reconstruct one append-only
Authority Lineage decision.

This validates supplied content and consistency. It does not authenticate
source identities, the signer/issuer, or the truth of the physical standard.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.reference-envelope-authority-lineage/0.1"
ENVELOPE_CANONICALIZATION = "json-sort-keys-utf8-v1"
AUTHORITY_EVENT_KIND = "reference-calibration"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_RECORD_FIELDS = {
    "attempt_id",
    "observation_id",
    "event",
    "source",
    "channel",
    "sequence",
    "payload_digest",
    "payload_value",
}
_RETURN_BINDINGS = (
    "policy_report_digest",
    "policy_state_digest",
    "policy_node_digest",
    "history_signal_prefix",
    "candidate_id",
    "sensor_id",
    "dimension",
    "known_hypothesis",
    "reference_standard_ref",
    "reference_standard_sha256",
    "observed_outcome",
)


class ReferenceEvidenceVerificationError(ValueError):
    """Invalid Encounter Envelope, source evidence set, or authority binding."""


class ReferenceEvidenceMismatch(ReferenceEvidenceVerificationError):
    """An envelope, source record, or authority decision disagrees with the policy path."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load required module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[2]
# These repositories intentionally keep the bridge modules dependency-light
# and executable from source rather than requiring package installation.
for _directory in (
    _ROOT / "bridges" / "observation-path",
    _ROOT / "bridges" / "authority-lineage",
    _ROOT / "formats" / "encounter-envelope",
):
    directory_string = str(_directory)
    if directory_string not in sys.path:
        sys.path.insert(0, directory_string)

_RIV012 = _load_module(
    "riv013_riv012",
    Path(__file__).resolve().with_name("finite_horizon_policy_execution.py"),
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
    "riv013_encounter_envelope_validator",
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
        raise ReferenceEvidenceVerificationError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise ReferenceEvidenceVerificationError(
            f"{label} must be finite JSON data"
        ) from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise ReferenceEvidenceVerificationError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ReferenceEvidenceVerificationError(
            f"{label} must be non-empty text without NUL"
        )
    return value.strip()


def _validate_policy_execution_record(raw: object) -> dict[str, Any]:
    try:
        return _RIV012.validate_reference_policy_execution_record(raw)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise ReferenceEvidenceVerificationError(
            f"RIV-012 policy execution record failed reconstruction: {error}"
        ) from error


def _normalize_source_records(
    raw: object,
    *,
    attempt_id: str,
    logical_time: int,
) -> list[dict[str, Any]]:
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ReferenceEvidenceVerificationError(
            "Encounter Envelope payload must contain a non-empty source_evidence_records list"
        )
    expected_event = {
        "kind": AUTHORITY_EVENT_KIND,
        "logical_time": logical_time,
    }
    normalized: list[dict[str, Any]] = []
    sources: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != _SOURCE_RECORD_FIELDS:
            raise ReferenceEvidenceVerificationError(
                f"source_evidence_records[{index}] must contain exactly {sorted(_SOURCE_RECORD_FIELDS)}"
            )
        if item["attempt_id"] != attempt_id or item["observation_id"] != attempt_id:
            raise ReferenceEvidenceMismatch(
                f"source_evidence_records[{index}] belongs to another attempt/observation"
            )
        event = item["event"]
        if not isinstance(event, Mapping) or dict(event) != expected_event:
            raise ReferenceEvidenceMismatch(
                f"source_evidence_records[{index}] belongs to another logical event"
            )
        source = _text(item["source"], f"source_evidence_records[{index}].source")
        channel = _text(item["channel"], f"source_evidence_records[{index}].channel")
        sequence = item["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ReferenceEvidenceVerificationError(
                f"source_evidence_records[{index}].sequence must be a positive integer"
            )
        if source in sources:
            raise ReferenceEvidenceVerificationError(
                f"duplicate source evidence record for {source!r}"
            )
        sources.add(source)
        payload_value = _copy_json(
            item["payload_value"],
            f"source_evidence_records[{index}].payload_value",
        )
        payload_digest = _sha256(
            item["payload_digest"],
            f"source_evidence_records[{index}].payload_digest",
        )
        computed = _digest(payload_value)
        if computed != payload_digest:
            raise ReferenceEvidenceMismatch(
                f"source_evidence_records[{index}] payload digest does not match payload_value"
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
    return sorted(normalized, key=lambda item: item["source"])


def _validate_envelope_for_path(
    envelope: object,
    *,
    path_snapshot: Mapping[str, Any],
    logical_time: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(envelope, Mapping):
        raise TypeError("each Encounter Envelope must be a mapping")
    document = _copy_json(envelope, "Encounter Envelope")
    valid, errors = _ENCOUNTER.validate_encounter(document)
    if not valid:
        raise ReferenceEvidenceVerificationError(
            "Encounter Envelope is structurally invalid: " + "; ".join(errors)
        )
    status, detail = _ENCOUNTER.verify_integrity(document)
    if status != "VERIFIED":
        raise ReferenceEvidenceVerificationError(
            f"Encounter Envelope integrity must be VERIFIED, got {status}: {detail}"
        )

    intent = path_snapshot["intent"]
    returned = next(
        item for item in path_snapshot["events"]
        if item["stage"] == "returned"
    )
    returned_details = returned["details"]
    payload = document["payload"]
    if "value" not in payload:
        raise ReferenceEvidenceVerificationError(
            "RIV-013 requires inline Encounter Envelope payload.value; references are not fetched"
        )
    value = payload["value"]
    if not isinstance(value, Mapping):
        raise ReferenceEvidenceVerificationError(
            "Encounter Envelope payload.value must be an object"
        )
    if document["id"] != returned_details["encounter_id"]:
        raise ReferenceEvidenceMismatch(
            "Encounter Envelope id differs from the returned encounter_id"
        )
    if value.get("source_evidence_records") is None:
        raise ReferenceEvidenceVerificationError(
            "Encounter Envelope payload.value lacks source_evidence_records"
        )
    integrity = document["integrity"]
    canonicalization = integrity.get("canonicalization")
    if canonicalization != ENVELOPE_CANONICALIZATION:
        raise ReferenceEvidenceVerificationError(
            f"Encounter Envelope must use {ENVELOPE_CANONICALIZATION!r}"
        )
    if returned_details.get("canonicalization") != canonicalization:
        raise ReferenceEvidenceMismatch(
            "ObservationPath canonicalization differs from the Encounter Envelope integrity contract"
        )
    if returned_details.get("payload_digest") != integrity.get("digest"):
        raise ReferenceEvidenceMismatch(
            "ObservationPath returned payload digest differs from the Encounter Envelope integrity digest"
        )

    for field in _RETURN_BINDINGS:
        expected = returned_details.get(field)
        if value.get(field) != expected:
            raise ReferenceEvidenceMismatch(
                f"Encounter Envelope payload.value.{field} differs from returned ObservationPath details"
            )
    source = document["source"]
    if source.get("kind") != "sensor" or source.get("reference") != returned_details["sensor_id"]:
        raise ReferenceEvidenceMismatch(
            "Encounter Envelope source must identify the selected sensor"
        )
    records = _normalize_source_records(
        value["source_evidence_records"],
        attempt_id=intent["attempt_id"] if isinstance(intent, Mapping) else path_snapshot["attempt_id"],
        logical_time=logical_time,
    )
    evidence_summary = {
        "encounter_id": document["id"],
        "envelope_digest": _digest(document),
        "payload_digest": integrity["digest"],
        "integrity_status": status,
        "canonicalization": canonicalization,
        "source_kind": source["kind"],
        "source_reference": source.get("reference"),
        "source_evidence_count": len(records),
        "source_ids": [item["source"] for item in records],
    }
    return document, records, evidence_summary


def build_verified_reference_evidence_bundle(
    *,
    policy_execution_record: Mapping[str, Any],
    encounter_envelopes: Sequence[Mapping[str, Any]],
    authority_ledger_id: str,
    ledger_created_by: str,
) -> dict[str, Any]:
    """Verify every inline Encounter Envelope and reconstruct authority lineage.

    One Encounter Envelope is required for each ObservationPath return in the
    RIV-012 execution prefix. The source evidence records are embedded in the
    envelope payload, digest checked individually, and used to create one
    initial Authority Lineage decision per reference attempt.
    """
    execution = _validate_policy_execution_record(policy_execution_record)
    paths = execution["observation_paths"]
    if not isinstance(encounter_envelopes, (list, tuple)) or len(encounter_envelopes) != len(paths):
        raise ReferenceEvidenceVerificationError(
            "encounter_envelopes must contain exactly one envelope per executed reference path"
        )
    ledger_id = _text(authority_ledger_id, "authority_ledger_id")
    created_by = _text(ledger_created_by, "ledger_created_by")
    ledger = _AUTHORITY.create_ledger(ledger_id, created_by=created_by)
    verified_envelopes: list[dict[str, Any]] = []
    authority_receipts: list[dict[str, Any]] = []
    evidence_summaries: list[dict[str, Any]] = []

    for index, (path_snapshot, envelope) in enumerate(zip(paths, encounter_envelopes)):
        logical_time = index
        document, source_records, envelope_summary = _validate_envelope_for_path(
            envelope,
            path_snapshot=path_snapshot,
            logical_time=logical_time,
        )
        auth_event = next(
            item for item in path_snapshot["events"]
            if item["stage"] == "evidence_authorized"
        )
        details = auth_event["details"]
        if details.get("decision_status") != "AUTHORIZED":
            raise ReferenceEvidenceMismatch(
                "RIV-012 prefix includes a non-AUTHORIZED reference decision"
            )
        observed = details.get("observed_sources")
        dissenting = details.get("dissenting_sources")
        missing = details.get("missing_sources")
        representative = details.get("representative_source")
        quorum = details.get("quorum")
        strict = details.get("strict")
        if not isinstance(observed, list) or observed != sorted(set(observed)):
            raise ReferenceEvidenceVerificationError(
                "authority observed_sources must be sorted and unique"
            )
        if not isinstance(dissenting, list) or dissenting != sorted(set(dissenting)):
            raise ReferenceEvidenceVerificationError(
                "authority dissenting_sources must be sorted and unique"
            )
        if not isinstance(missing, list) or missing != sorted(set(missing)):
            raise ReferenceEvidenceVerificationError(
                "authority missing_sources must be sorted and unique"
            )
        if any(source not in observed for source in dissenting):
            raise ReferenceEvidenceMismatch(
                "authority dissenting_sources must be a subset of observed_sources"
            )
        if [item["source"] for item in source_records] != observed:
            raise ReferenceEvidenceMismatch(
                "Encounter Envelope source evidence set differs from AUTHORIZED observed_sources"
            )
        if isinstance(quorum, bool) or not isinstance(quorum, int) or quorum < 1:
            raise ReferenceEvidenceVerificationError(
                "authority quorum must be a positive integer"
            )
        if type(strict) is not bool:
            raise ReferenceEvidenceVerificationError("authority strict must be Boolean")
        winners = sorted(set(observed) - set(dissenting))
        if len(winners) < quorum:
            raise ReferenceEvidenceMismatch(
                "AUTHORIZED source evidence does not meet its declared quorum"
            )
        if representative not in winners:
            raise ReferenceEvidenceMismatch(
                "authority representative is not in the non-dissenting source set"
            )
        policy_digest = _sha256(details.get("policy_digest"), "authority.policy_digest")
        decision_digest = _sha256(details.get("decision_digest"), "authority.decision_digest")
        attempt_id = path_snapshot["attempt_id"]
        event_key = {
            "kind": AUTHORITY_EVENT_KIND,
            "logical_time": logical_time,
        }
        attempt = {
            "attempt_id": attempt_id,
            "observation_id": attempt_id,
            "final_status": "AUTHORIZED",
            "evidence_received_sources": observed,
            "evidence_received_count": len(source_records),
            "representative_source": representative,
            "evidence_partition": {
                "observed_sources": observed,
                "source_count": len(source_records),
                "winner_sources": winners,
                "dissenting_sources": dissenting,
                "missing_sources": missing,
            },
        }
        try:
            ledger, decision_id, receipt = _OBSERVATION_ADAPTER.issue_initial_decision_from_attempt(
                ledger,
                attempt,
                source_records,
                event_key=event_key,
                policy_digest=policy_digest,
                issued_by=auth_event["actor"],
                rationale=(
                    "Authority Lineage record reconstructed from an AUTHORIZED "
                    "finite-horizon reference ObservationPath and its verified Encounter Envelope."
                ),
            )
        except (TypeError, ValueError, KeyError) as error:
            raise ReferenceEvidenceVerificationError(
                f"Authority Lineage rejected reference attempt {attempt_id!r}: {error}"
            ) from error
        frontier = _AUTHORITY.decision_frontier(ledger, event_key)
        if frontier["status"] != "SINGLE_DECISION" or frontier["decision_ids"] != [decision_id]:
            raise AssertionError("Authority Lineage did not produce one unique decision frontier")
        authority_decisions = _AUTHORITY.decision_history(ledger, event_key)
        decision = next(item for item in authority_decisions if item["decision_id"] == decision_id)
        if decision["status"] != "AUTHORIZED" or decision["evidence_set_digest"] != receipt["evidence_set_digest"]:
            raise AssertionError("Authority Lineage decision differs from its evidence receipt")

        verified_envelopes.append(document)
        evidence_summaries.append(envelope_summary)
        authority_receipts.append({
            "attempt_id": attempt_id,
            "event_key": event_key,
            "observation_path_authority_evidence_ref": auth_event["evidence_ref"],
            "observation_path_decision_digest": decision_digest,
            "authority_lineage_decision_id": decision_id,
            "authority_lineage_decision_digest": decision["decision_digest"],
            "authority_lineage_evidence_set_digest": receipt["evidence_set_digest"],
            "authority_lineage_receipt": receipt,
            "verified_envelope_digest": envelope_summary["envelope_digest"],
        })

    _AUTHORITY.validate_ledger(ledger)
    core = {
        "format": FORMAT,
        "schema": "in-formation.reference-envelope-authority-lineage/0.1",
        "policy_execution_record": execution,
        "policy_execution_record_digest": execution["record_digest"],
        "encounter_envelopes": verified_envelopes,
        "encounter_envelope_summaries": evidence_summaries,
        "authority_ledger": ledger,
        "authority_ledger_digest": ledger["ledger_digest"],
        "authority_receipts": authority_receipts,
        "verification_status": "inline_envelope_integrity_verified_and_authority_lineage_reconstructed",
        "trust_boundary": [
            "Encounter Envelope validation proves structural conformance and that each inline payload matches its declared SHA-256 digest under json-sort-keys-utf8-v1; it does not authenticate the source or prove the physical standard is true.",
            "Authority Lineage records immutable hash-chained decisions from supplied source records and AUTHORIZED path details; it does not authenticate the issuer, source identities, quorum membership, policy correctness, or a signature.",
            "Per-source payload digests are checked against payload_value documents retained inside the verified Encounter Envelope. This proves internal content consistency, not that a physical source generated those values.",
            "A digest or hash chain is not a substitute for a signature, independently pinned trust root, verified transport identity, or external evidence retrieval.",
            "The cumulative RIV-009 report remains the Bayesian calibration inference result; this bundle adds provenance and integrity evidence only and does not change its posterior.",
        ],
    }
    return {**core, "bundle_digest": _digest(core)}


def validate_verified_reference_evidence_bundle(
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct every envelope, source record, Authority Lineage entry and digest."""
    if not isinstance(bundle, Mapping):
        raise TypeError("verified reference evidence bundle must be a mapping")
    supplied = _copy_json(bundle, "verified reference evidence bundle")
    digest = supplied.pop("bundle_digest", None)
    if not isinstance(digest, str) or not _HEX_256.fullmatch(digest) or digest != _digest(supplied):
        raise ReferenceEvidenceVerificationError("bundle_digest does not match bundle contents")
    if supplied.get("format") != FORMAT:
        raise ReferenceEvidenceVerificationError("unsupported reference evidence bundle format")
    execution = supplied.get("policy_execution_record")
    ledger = supplied.get("authority_ledger")
    if not isinstance(execution, Mapping) or not isinstance(ledger, Mapping):
        raise ReferenceEvidenceVerificationError("bundle omits execution record or authority ledger")
    try:
        _AUTHORITY.validate_ledger(ledger)
    except (TypeError, ValueError, KeyError) as error:
        raise ReferenceEvidenceVerificationError(
            f"Authority Lineage ledger failed reconstruction: {error}"
        ) from error
    rebuilt = build_verified_reference_evidence_bundle(
        policy_execution_record=execution,
        encounter_envelopes=supplied.get("encounter_envelopes"),
        authority_ledger_id=ledger["entries"][0]["payload"]["ledger_id"],
        ledger_created_by=ledger["entries"][0]["actor"],
    )
    if rebuilt != dict(bundle):
        raise ReferenceEvidenceVerificationError(
            "bundle differs from independent reconstruction from retained policy paths, Encounter Envelopes and source records"
        )
    return dict(bundle)


__all__ = [
    "FORMAT",
    "ReferenceEvidenceMismatch",
    "ReferenceEvidenceVerificationError",
    "build_verified_reference_evidence_bundle",
    "validate_verified_reference_evidence_bundle",
]
