"""Cryptographically review a RIV-013 bundle using signed Authority Lineage.

RIV-014 attests to a narrow proposition: two distinct trusted reviewer seats
approve the integrity/provenance bundle as internally consistent under the
declared RIV-013 contract. A root-signed, expiring trust manifest binds the
reviewer public keys. These signatures authenticate reviewer approvals, not
sensor identity, physical measurement truth, or the original source payloads.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

FORMAT = "in-formation.signed-reference-evidence-review/0.1"
REVIEW_POLICY = "independent_two_of_two"
REVIEW_EVENT_KIND = "reference-evidence-bundle-review"
_REVIEW_SEATS = ("R01", "R02")
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")


class SignedReferenceReviewError(ValueError):
    """Invalid reviewer attestation, trust manifest, or verified-bundle binding."""


class SignedReferenceReviewMismatch(SignedReferenceReviewError):
    """A signature, review certificate, bundle, or trust manifest does not agree."""


_ROOT = Path(__file__).resolve().parents[2]
for _directory in (
    _ROOT / "bridges" / "authority-lineage",
    _ROOT / "formats" / "encounter-envelope",
    _ROOT / "experiments" / "reference-calibrated-evidence",
):
    _directory_string = str(_directory)
    if _directory_string not in sys.path:
        sys.path.insert(0, _directory_string)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load required module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_AUTHORITY = _load_module(
    "riv014_authority_lineage",
    _ROOT / "bridges" / "authority-lineage" / "authority_lineage.py",
)
_CERTIFICATES = _load_module(
    "riv014_review_certificates",
    _ROOT / "bridges" / "authority-lineage" / "review_certificates.py",
)
_SIGNED = _load_module(
    "riv014_signed_review_receipts",
    _ROOT / "bridges" / "authority-lineage" / "signed_review_receipts.py",
)
_TRUST = _load_module(
    "riv014_review_trust_manifest",
    _ROOT / "bridges" / "authority-lineage" / "review_trust_manifest.py",
)
_RIV013 = _load_module(
    "riv014_riv013",
    Path(__file__).resolve().with_name("verified_reference_evidence_bundle.py"),
)

if _RIV013.FORMAT != "in-formation.reference-envelope-authority-lineage/0.1":
    raise RuntimeError("RIV-014 requires the declared RIV-013 evidence bundle contract")


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
        raise SignedReferenceReviewError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise SignedReferenceReviewError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise SignedReferenceReviewError(f"{label} must be non-empty text without NUL")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise SignedReferenceReviewError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _public_key_id(public_key: Ed25519PublicKey) -> str:
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("public key must be Ed25519PublicKey")
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def _validate_riv013_bundle(bundle: object) -> dict[str, Any]:
    try:
        return _RIV013.validate_verified_reference_evidence_bundle(bundle)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise SignedReferenceReviewError(
            f"RIV-013 evidence bundle failed reconstruction: {error}"
        ) from error


def _review_artifact_text(
    *,
    seat: str,
    principal: str,
    bundle_digest: str,
    trust_boundary_digest: str,
) -> str:
    return (
        "RIV-014 independent reviewer attestation\n"
        f"seat: {seat}\n"
        f"principal: {principal}\n"
        f"RIV-013 bundle digest: {bundle_digest}\n"
        f"trust boundary digest: {trust_boundary_digest}\n"
        "review proposition: the retained RIV-013 Encounter Envelope payloads, "
        "source-evidence digests, ObservationPath bindings, and Authority Lineage "
        "decisions are internally consistent under their declared schemas and "
        "reconstruction contracts.\n"
        "explicit exclusion: this review does not attest to physical sensor identity, "
        "physical standard truth or custody, source signature authenticity, or the "
        "truth of any measurement outside the declared content-integrity evidence.\n"
        "vote scope: approval of the RIV-013 content-integrity and provenance bundle only.\n"
    )


def build_signed_reference_evidence_review(
    *,
    verified_reference_evidence_bundle: Mapping[str, Any],
    reviewer_private_keys: Mapping[str, Ed25519PrivateKey],
    reviewer_principals: Mapping[str, str],
    root_private_keys: Sequence[Ed25519PrivateKey],
    registry_id: str,
    manifest_issued_at: str,
    manifest_expires_at: str,
    verification_time: str,
    created_by: str = "RIV-014-review-coordinator",
    recorded_by: str = "RIV-014-review-coordinator",
    proposed_by: str = "RIV-014-review-requester",
    resolved_by: str = "RIV-014-review-coordinator",
    root_threshold: int = 1,
) -> dict[str, Any]:
    """Create a signed two-reviewer approval record over one verified RIV-013 bundle.

    Private keys are caller-supplied and are never copied into the result.
    Public reviewer keys are bound into a root-signed, expiring trust manifest.
    """
    bundle = _validate_riv013_bundle(verified_reference_evidence_bundle)
    bundle_digest = bundle["bundle_digest"]
    created = _text(created_by, "created_by")
    recorded = _text(recorded_by, "recorded_by")
    proposer = _text(proposed_by, "proposed_by")
    resolver = _text(resolved_by, "resolved_by")
    registry = _text(registry_id, "registry_id")

    if not isinstance(reviewer_private_keys, Mapping) or set(reviewer_private_keys) != set(_REVIEW_SEATS):
        raise SignedReferenceReviewError(
            f"reviewer_private_keys must contain exactly {_REVIEW_SEATS}"
        )
    if not isinstance(reviewer_principals, Mapping) or set(reviewer_principals) != set(_REVIEW_SEATS):
        raise SignedReferenceReviewError(
            f"reviewer_principals must contain exactly {_REVIEW_SEATS}"
        )
    if not isinstance(root_private_keys, (list, tuple)) or not root_private_keys:
        raise SignedReferenceReviewError("at least one pinned trust-root private key is required")
    for seat in _REVIEW_SEATS:
        if not isinstance(reviewer_private_keys[seat], Ed25519PrivateKey):
            raise TypeError(f"reviewer_private_keys[{seat}] must be Ed25519PrivateKey")
    principals = {
        seat: _text(reviewer_principals[seat], f"reviewer_principals[{seat}]")
        for seat in _REVIEW_SEATS
    }
    if len(set(principals.values())) != len(principals):
        raise SignedReferenceReviewError("reviewer principals must be distinct")

    event_key = {
        "kind": REVIEW_EVENT_KIND,
        "logical_time": 0,
    }
    policy_snapshot = {
        "format": "in-formation.reference-evidence-review-policy/0.1",
        "policy_name": REVIEW_POLICY,
        "required_reviewer_seats": list(_REVIEW_SEATS),
        "required_votes": ["APPROVE", "APPROVE"],
        "proposer_excluded": True,
        "scope": "RIV-013 content-integrity and provenance consistency only",
        "excludes": [
            "physical sensor identity",
            "physical standard truth or custody",
            "source signature authenticity",
            "external transport authentication",
        ],
    }
    policy_digest = _digest(policy_snapshot)
    content_evidence_digest = _digest({
        "riv013_bundle_digest": bundle_digest,
        "authority_ledger_digest": bundle["authority_ledger_digest"],
        "policy_execution_record_digest": bundle["policy_execution_record_digest"],
        "encounter_envelope_digests": [
            item["envelope_digest"]
            for item in bundle["encounter_envelope_summaries"]
        ],
        "source_ids_by_attempt": [
            {
                "attempt_id": receipt["attempt_id"],
                "source_ids": summary["source_ids"],
            }
            for receipt, summary in zip(
                bundle["authority_receipts"],
                bundle["encounter_envelope_summaries"],
            )
        ],
    })

    ledger = _AUTHORITY.create_ledger(
        f"riv014-reference-bundle-review:{bundle_digest[:16]}",
        created_by=created,
    )
    ledger, base_decision_id = _AUTHORITY.issue_decision(
        ledger,
        event_key=event_key,
        status="AUTHORIZED",
        evidence_set_digest=content_evidence_digest,
        policy_digest=policy_digest,
        issued_by="RIV-013-content-verifier",
        rationale=(
            "RIV-013 independently reconstructed inline Encounter Envelope "
            "integrity, per-source payload digests, policy-path bindings, and "
            "Authority Lineage content. This is a machine content-integrity "
            "decision, not an authenticated physical-source claim."
        ),
        representative_ref=f"urn:sha256:{bundle_digest}",
    )
    proposal_evidence = [
        {"ref": f"urn:sha256:{bundle_digest}", "sha256": bundle_digest},
        {"ref": f"urn:sha256:{bundle['authority_ledger_digest']}", "sha256": bundle["authority_ledger_digest"]},
        {"ref": f"urn:sha256:{bundle['policy_execution_record_digest']}", "sha256": bundle["policy_execution_record_digest"]},
    ]
    ledger, proposal_id = _AUTHORITY.propose_revision(
        ledger,
        event_key=event_key,
        base_decision_ids=[base_decision_id],
        evidence_refs=proposal_evidence,
        reason=(
            "Request two independent cryptographic reviewer approvals of the "
            "RIV-013 content-integrity and provenance bundle. This review does "
            "not claim physical source or standard authentication."
        ),
        proposed_by=proposer,
    )

    trust_store = _SIGNED.build_trust_store([
        {
            "seat": seat,
            "principal": principals[seat],
            "public_key": reviewer_private_keys[seat].public_key(),
        }
        for seat in _REVIEW_SEATS
    ])
    review_artifacts: dict[str, str] = {}
    votes: list[dict[str, Any]] = []
    for seat in _REVIEW_SEATS:
        reviewer_ref = principals[seat]
        review_ref = f"urn:sha256:{bundle_digest}:review:{seat}"
        artifact = _review_artifact_text(
            seat=seat,
            principal=reviewer_ref,
            bundle_digest=bundle_digest,
            trust_boundary_digest=_digest(bundle["trust_boundary"]),
        )
        review_artifacts[review_ref] = artifact
        votes.append({
            "seat": seat,
            "reviewer_ref": reviewer_ref,
            "vote": "APPROVE",
            "rationale": (
                "The RIV-013 bundle's declared content-integrity and provenance "
                "checks reconstruct; this approval excludes physical source "
                "identity, standard truth, and source-signature authenticity."
            ),
            "review_ref": review_ref,
            "review_sha256": hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
        })

    certificate = _CERTIFICATES.build_review_certificate(
        ledger,
        proposal_id,
        policy_name=REVIEW_POLICY,
        votes=votes,
    )
    if certificate["evaluation"]["outcome"] != "ACCEPTED":
        raise AssertionError("two independent approvals did not satisfy the declared review policy")
    ledger = _CERTIFICATES.record_review_certificate(
        ledger,
        certificate,
        recorded_by=recorded,
    )

    envelopes = [
        _SIGNED.sign_review_vote(
            certificate,
            vote,
            reviewer_private_keys[vote["seat"]],
        )
        for vote in votes
    ]
    signed_bundle = _SIGNED.build_signed_review_bundle(
        certificate,
        envelopes,
        trust_store,
        review_artifacts=review_artifacts,
    )
    ledger = _SIGNED.record_signed_review_bundle(
        ledger,
        proposal_id,
        signed_bundle,
        trust_store,
        recorded_by=recorded,
        review_artifacts=review_artifacts,
    )

    manifest = _TRUST.build_trust_manifest(
        registry_id=registry,
        generation=1,
        trust_store=trust_store,
        issued_at=manifest_issued_at,
        expires_at=manifest_expires_at,
        previous_manifest_digest=None,
    )
    manifest_envelope = _TRUST.sign_trust_manifest(
        manifest,
        root_private_keys,
    )
    root_public_keys = {
        _public_key_id(private_key.public_key()): private_key.public_key()
        for private_key in root_private_keys
    }
    root_verification = _TRUST.verify_trust_manifest(
        manifest_envelope,
        root_public_keys,
        verification_time=verification_time,
        root_threshold=root_threshold,
        expected_registry_id=registry,
        minimum_generation=1,
        expected_generation=1,
        expected_previous_manifest_digest=None,
    )
    signed_verification = _TRUST.verify_ledger_signed_review_bundle_with_manifest(
        ledger,
        proposal_id,
        manifest_envelope,
        root_public_keys,
        verification_time=verification_time,
        root_threshold=root_threshold,
        expected_registry_id=registry,
        minimum_generation=1,
        expected_generation=1,
        expected_previous_manifest_digest=None,
        review_artifacts=review_artifacts,
    )
    ledger = _SIGNED.resolve_signed_reviewed_proposal(
        ledger,
        proposal_id,
        trusted_trust_store=trust_store,
        rationale=(
            "The root-signed trust manifest is valid at the supplied verification "
            "time, and the two independent reviewer signatures match the recorded "
            "certificate. The accepted proposition remains limited to RIV-013 "
            "content-integrity and provenance consistency."
        ),
        resolved_by=resolver,
        review_artifacts=review_artifacts,
    )

    signed_evidence_digest = _digest({
        "bundle_digest": bundle_digest,
        "signed_review_bundle_digest": signed_bundle["bundle_digest"],
        "review_certificate_digest": certificate["certificate_digest"],
        "trust_manifest_digest": root_verification["manifest_digest"],
        "trust_store_digest": root_verification["trust_store_digest"],
        "review_evidence_digests": [
            vote["review_sha256"] for vote in votes
        ],
    })
    ledger, final_decision_id = _AUTHORITY.issue_decision(
        ledger,
        event_key=event_key,
        status="AUTHORIZED",
        evidence_set_digest=signed_evidence_digest,
        policy_digest=certificate["policy_digest"],
        issued_by=resolver,
        rationale=(
            "Two distinct reviewer seats (R01 and R02) cryptographically approved "
            "the RIV-013 bundle under the root-authenticated reviewer trust "
            "manifest. This decision attests to reviewer approval of the bundle's "
            "declared content-integrity and provenance contract only."
        ),
        representative_ref=f"urn:sha256:{signed_bundle['bundle_digest']}",
        proposal_id=proposal_id,
    )
    _AUTHORITY.validate_ledger(ledger)
    frontier = _AUTHORITY.decision_frontier(ledger, event_key)
    if frontier["status"] != "SINGLE_DECISION" or frontier["decision_ids"] != [final_decision_id]:
        raise AssertionError("signed reviewer decision did not establish one unique authority frontier")

    core = {
        "format": FORMAT,
        "schema": FORMAT,
        "verified_reference_evidence_bundle": bundle,
        "verified_reference_evidence_bundle_digest": bundle_digest,
        "authority_review_ledger": ledger,
        "authority_review_ledger_digest": ledger["ledger_digest"],
        "review_event_key": event_key,
        "base_content_decision_id": base_decision_id,
        "review_proposal_id": proposal_id,
        "review_policy": policy_snapshot,
        "review_certificate": certificate,
        "review_artifacts": review_artifacts,
        "signed_review_bundle": signed_bundle,
        "reviewer_trust_store": trust_store,
        "root_signed_trust_manifest": manifest_envelope,
        "root_trust_manifest_digest": root_verification["manifest_digest"],
        "root_trust_registry_id": registry,
        "root_trust_manifest_generation": 1,
        "root_verification": root_verification,
        "signed_review_verification": signed_verification,
        "proposal_resolution": next(
            entry["payload"]
            for entry in ledger["entries"]
            if entry["entry_type"] == "proposal_resolved"
            and entry["payload"]["proposal_id"] == proposal_id
        ),
        "final_authority_decision_id": final_decision_id,
        "final_authority_frontier": frontier,
        "review_status": "two_independent_signed_approvals_verified",
        "attestation_scope": (
            "RIV-013 content-integrity and provenance consistency only; not "
            "physical sensor identity, physical standard truth or custody, "
            "source signature authenticity, or external transport authentication."
        ),
        "trust_boundary": [
            "Reviewer Ed25519 signatures authenticate the two review approvals relative to the root-authenticated trust manifest.",
            "The trust manifest is valid only for its declared registry, generation, root signature threshold, and verification-time interval.",
            "The private reviewer and root signing keys are caller-supplied and are not retained in this record.",
            "Reviewer signatures approve the RIV-013 bundle's declared content and provenance consistency. They do not authenticate original sensor identities, prove that source payloads came from physical sensors, or prove standard truth/custody.",
            "RIV-013's SHA-256 content checks and Authority Lineage hash chain remain integrity/reconstruction evidence, not source signatures.",
            "Trust-root public-key pins and verification time must be supplied out-of-band to validate this record; a trust manifest cannot bootstrap its own root of trust.",
            "Expiry and registry generation are enforced during validation; callers must persist minimum generation and/or expected predecessor state to prevent rollback.",
        ],
    }
    return {**core, "review_record_digest": _digest(core)}


def validate_signed_reference_evidence_review(
    record: Mapping[str, Any],
    *,
    trusted_root_public_keys: Mapping[str, Ed25519PublicKey],
    verification_time: str,
    root_threshold: int = 1,
) -> dict[str, Any]:
    """Verify RIV-014 reviewer signatures, root manifest, and final lineage decision."""
    if not isinstance(record, Mapping):
        raise TypeError("signed reference evidence review must be a mapping")
    supplied = _copy_json(record, "signed reference evidence review")
    digest = supplied.pop("review_record_digest", None)
    if not isinstance(digest, str) or not _HEX_256.fullmatch(digest) or digest != _digest(supplied):
        raise SignedReferenceReviewError("review_record_digest does not match record contents")
    if supplied.get("format") != FORMAT or supplied.get("schema") != FORMAT:
        raise SignedReferenceReviewError("unsupported signed reference review format")

    bundle = _validate_riv013_bundle(supplied["verified_reference_evidence_bundle"])
    bundle_digest = bundle["bundle_digest"]
    if bundle_digest != supplied.get("verified_reference_evidence_bundle_digest"):
        raise SignedReferenceReviewMismatch("RIV-013 bundle digest differs from review record binding")
    ledger = supplied.get("authority_review_ledger")
    if not isinstance(ledger, Mapping):
        raise SignedReferenceReviewError("authority review ledger is missing")
    _AUTHORITY.validate_ledger(ledger)
    if ledger["ledger_digest"] != supplied.get("authority_review_ledger_digest"):
        raise SignedReferenceReviewMismatch("authority review ledger digest differs from record binding")

    registry_id = _text(supplied.get("root_trust_registry_id"), "root_trust_registry_id")
    root_verification = _TRUST.verify_trust_manifest(
        supplied.get("root_signed_trust_manifest"),
        trusted_root_public_keys,
        verification_time=verification_time,
        root_threshold=root_threshold,
        expected_registry_id=registry_id,
        minimum_generation=1,
        expected_generation=1,
        expected_previous_manifest_digest=None,
    )
    if root_verification["manifest_digest"] != supplied.get("root_trust_manifest_digest"):
        raise SignedReferenceReviewMismatch("root trust manifest digest differs from record")
    if root_verification["trust_store"] != supplied.get("reviewer_trust_store"):
        raise SignedReferenceReviewMismatch("root-signed trust store differs from record trust store")

    proposal_id = _text(supplied.get("review_proposal_id"), "review_proposal_id")
    signed_verification = _TRUST.verify_ledger_signed_review_bundle_with_manifest(
        ledger,
        proposal_id,
        supplied["root_signed_trust_manifest"],
        trusted_root_public_keys,
        verification_time=verification_time,
        root_threshold=root_threshold,
        expected_registry_id=registry_id,
        minimum_generation=1,
        expected_generation=1,
        expected_previous_manifest_digest=None,
        review_artifacts=supplied["review_artifacts"],
    )
    if signed_verification != supplied.get("signed_review_verification"):
        raise SignedReferenceReviewMismatch("signed review verification summary differs from record")
    if signed_verification["bundle_digest"] != supplied["signed_review_bundle"]["bundle_digest"]:
        raise SignedReferenceReviewMismatch("signed review bundle digest differs from the ledger verification")

    if supplied["review_certificate"]["evaluation"]["outcome"] != "ACCEPTED":
        raise SignedReferenceReviewMismatch("review certificate does not meet independent approval policy")
    if supplied["review_certificate"]["policy_snapshot"]["policy_id"] != REVIEW_POLICY:
        raise SignedReferenceReviewMismatch("review certificate uses an unexpected policy")

    resolution = supplied.get("proposal_resolution")
    if not isinstance(resolution, Mapping) or resolution.get("outcome") != "ACCEPTED":
        raise SignedReferenceReviewMismatch("signed review proposal is not accepted")
    if resolution.get("signed_review_bundle_digest") != signed_verification["bundle_digest"]:
        raise SignedReferenceReviewMismatch("proposal resolution is not bound to the verified signed bundle")

    frontier = _AUTHORITY.decision_frontier(
        ledger,
        supplied["review_event_key"],
    )
    if frontier != supplied.get("final_authority_frontier"):
        raise SignedReferenceReviewMismatch("final authority frontier differs from rebuilt ledger")
    if frontier["status"] != "SINGLE_DECISION" or frontier["decision_ids"] != [supplied["final_authority_decision_id"]]:
        raise SignedReferenceReviewMismatch("final authority frontier does not contain the signed review decision")
    final_decision = frontier["decisions"][0]
    if final_decision["status"] != "AUTHORIZED":
        raise SignedReferenceReviewMismatch("final review authority decision is not AUTHORIZED")
    if final_decision["representative_ref"] != f"urn:sha256:{signed_verification['bundle_digest']}":
        raise SignedReferenceReviewMismatch("final authority decision does not identify the signed review bundle")
    if final_decision["proposal_id"] != proposal_id:
        raise SignedReferenceReviewMismatch("final authority decision does not reference the reviewed proposal")

    return {
        **dict(record),
        "external_verification": {
            "verification_time": verification_time,
            "root_signature_threshold": root_threshold,
            "root_keyids": root_verification["root_keyids"],
            "root_trust_manifest_digest": root_verification["manifest_digest"],
            "signed_review_bundle_digest": signed_verification["bundle_digest"],
            "signed_review_votes_verified": len(supplied["review_certificate"]["votes"]),
            "final_authority_decision_id": final_decision["decision_id"],
            "final_authority_decision_digest": final_decision["decision_digest"],
        },
    }


__all__ = [
    "FORMAT",
    "REVIEW_POLICY",
    "SignedReferenceReviewError",
    "SignedReferenceReviewMismatch",
    "build_signed_reference_evidence_review",
    "validate_signed_reference_evidence_review",
]
