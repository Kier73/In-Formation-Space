"""DSSE/Ed25519 signatures for authority-review vote receipts.

This module verifies signatures against a caller-supplied trust store. It does
not establish how that trust store was provisioned, nor does a key fingerprint
prove an agent's identity. Review payload bytes are signed exactly as carried;
no cross-language JSON canonicalization claim is made.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from authority_lineage import (
    _append_entry,
    _entries_of_type,
    _event_equal,
    _nonempty as _lineage_nonempty,
    _sha256 as _lineage_sha256,
    current_frontier,
    digest,
    resolve_proposal,
    validate_ledger,
)

FORMAT = "in-formation.signed-review-bundle"
SCHEMA = "in-formation.signed-review-bundle/0.1"
TRUST_STORE_FORMAT = "in-formation.review-trust-store"
TRUST_STORE_SCHEMA = "in-formation.review-trust-store/0.1"
PAYLOAD_TYPE = "application/vnd.in-formation.authority-review-vote+json;version=0.2"
SIGNED_PAYLOAD_FORMAT = "in-formation.signed-authority-review-vote"
SIGNED_PAYLOAD_SCHEMA = "in-formation.signed-authority-review-vote/0.2"
SIGNED_CONTEXT_FIELDS = {
    "format",
    "schema",
    "certificate_digest",
    "proposal_id",
    "proposal_digest",
    "event_key",
    "base_decision_ids",
    "base_decision_digests",
    "policy_digest",
}
SIGNED_PAYLOAD_FIELDS = SIGNED_CONTEXT_FIELDS | {"vote"}
SIGNATURE_PROFILE = "DSSEv1+Ed25519"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
REVIEW_SEATS = ("R00", "R01", "R02")
VOTE_FIELDS = {
    "seat",
    "reviewer_ref",
    "vote",
    "rationale",
    "review_ref",
    "review_sha256",
}
TRUST_STORE_FIELDS = {"format", "schema", "keys"}
TRUST_KEY_FIELDS = {"keyid", "principal", "seat", "public_key"}
ENVELOPE_FIELDS = {"payloadType", "payload", "signatures"}
SIGNATURE_FIELDS = {"keyid", "sig"}
BUNDLE_FIELDS = {
    "format",
    "schema",
    "signature_profile",
    "certificate_digest",
    "payload_type",
    "trust_store_digest",
    "review_artifacts_verified",
    "signed_review_votes",
    "bundle_digest",
}


class SignedReviewError(ValueError):
    """A signed review receipt, envelope, or trust store is invalid."""


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SignedReviewError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise SignedReviewError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: object, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise SignedReviewError(f"{label} must be a non-empty base64 string")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise SignedReviewError(f"{label} is not valid base64") from exc
    if _b64encode(raw) != value:
        raise SignedReviewError(f"{label} is not canonical base64")
    return raw


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SignedReviewError("review payload is not serializable JSON") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SignedReviewError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                SignedReviewError(f"non-finite JSON number is forbidden: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignedReviewError("signed review payload is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise SignedReviewError("signed review payload must be a JSON object")
    return parsed


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE pre-authentication encoding over UTF-8 payload type and raw bytes."""
    if not isinstance(payload_type, str) or not payload_type:
        raise SignedReviewError("payload_type must be a non-empty string")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    type_bytes = payload_type.encode("utf-8")
    return (
        b"DSSEv1 "
        + str(len(type_bytes)).encode("ascii")
        + b" "
        + type_bytes
        + b" "
        + str(len(payload)).encode("ascii")
        + b" "
        + payload
    )


def _normalize_vote(vote: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(vote, Mapping) or set(vote) != VOTE_FIELDS:
        raise SignedReviewError("review vote has missing or unrecognized fields")
    normalized = {
        "seat": _nonempty(vote.get("seat"), "vote.seat"),
        "reviewer_ref": _nonempty(vote.get("reviewer_ref"), "vote.reviewer_ref"),
        "vote": _nonempty(vote.get("vote"), "vote.vote"),
        "rationale": _nonempty(vote.get("rationale"), "vote.rationale"),
        "review_ref": _nonempty(vote.get("review_ref"), "vote.review_ref"),
        "review_sha256": _sha256(vote.get("review_sha256"), "vote.review_sha256"),
    }
    if normalized["seat"] not in REVIEW_SEATS:
        raise SignedReviewError("review vote names an unknown seat")
    if normalized["vote"] not in {"APPROVE", "REJECT", "ABSTAIN"}:
        raise SignedReviewError("review vote must be APPROVE, REJECT, or ABSTAIN")
    return normalized


def _raw_public_key(public_key: Ed25519PublicKey) -> bytes:
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("public_key must be an Ed25519PublicKey")
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def build_trust_store(
    keys: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a trust-store document from provisioned Ed25519 public keys.

    The returned structure is not self-authenticating. Its digest is useful for
    pinning a trust-store version; callers must obtain the store through a
    trusted configuration or governance channel.
    """
    if not isinstance(keys, (list, tuple)) or not keys:
        raise SignedReviewError("trust store requires at least one trusted key")
    normalized = []
    seats: set[str] = set()
    principals: set[str] = set()
    keyids: set[str] = set()
    for index, item in enumerate(keys):
        if not isinstance(item, Mapping) or set(item) != {"seat", "principal", "public_key"}:
            raise SignedReviewError(f"trust key {index} has invalid fields")
        seat = _nonempty(item.get("seat"), f"keys[{index}].seat")
        principal = _nonempty(item.get("principal"), f"keys[{index}].principal")
        if seat not in REVIEW_SEATS:
            raise SignedReviewError(f"trust key {index} uses an unknown seat")
        public_key = item.get("public_key")
        raw = _raw_public_key(public_key)
        keyid = hashlib.sha256(raw).hexdigest()
        if seat in seats or principal in principals or keyid in keyids:
            raise SignedReviewError("trust store seats, principals, and key IDs must be unique")
        normalized.append({
            "keyid": keyid,
            "principal": principal,
            "seat": seat,
            "public_key": _b64encode(raw),
        })
        seats.add(seat)
        principals.add(principal)
        keyids.add(keyid)
    return {
        "format": TRUST_STORE_FORMAT,
        "schema": TRUST_STORE_SCHEMA,
        "keys": sorted(normalized, key=lambda item: item["keyid"]),
    }


def _validate_trust_store(
    trust_store: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    if not isinstance(trust_store, Mapping) or set(trust_store) != TRUST_STORE_FIELDS:
        raise SignedReviewError("trust store has missing or unrecognized fields")
    if trust_store["format"] != TRUST_STORE_FORMAT or trust_store["schema"] != TRUST_STORE_SCHEMA:
        raise SignedReviewError("unsupported review trust-store format or schema")
    keys = trust_store["keys"]
    if not isinstance(keys, list) or not keys:
        raise SignedReviewError("trust store must contain at least one public key")
    by_keyid: dict[str, dict[str, Any]] = {}
    seats: set[str] = set()
    principals: set[str] = set()
    previous_keyid = ""
    for index, item in enumerate(keys):
        if not isinstance(item, Mapping) or set(item) != TRUST_KEY_FIELDS:
            raise SignedReviewError(f"trust store key {index} has invalid fields")
        keyid = _sha256(item.get("keyid"), f"trust_store.keys[{index}].keyid")
        principal = _nonempty(item.get("principal"), f"trust_store.keys[{index}].principal")
        seat = _nonempty(item.get("seat"), f"trust_store.keys[{index}].seat")
        if seat not in REVIEW_SEATS:
            raise SignedReviewError(f"trust store key {index} uses an unknown seat")
        if keyid in by_keyid or seat in seats or principal in principals:
            raise SignedReviewError("trust store keys, seats, and principals must be unique")
        if previous_keyid and keyid <= previous_keyid:
            raise SignedReviewError("trust store keys must be sorted by keyid")
        raw = _b64decode(item.get("public_key"), f"trust_store.keys[{index}].public_key")
        if len(raw) != 32:
            raise SignedReviewError("Ed25519 public keys must contain exactly 32 bytes")
        expected_keyid = hashlib.sha256(raw).hexdigest()
        if keyid != expected_keyid:
            raise SignedReviewError("trust-store keyid is not the public-key fingerprint")
        try:
            public_key = Ed25519PublicKey.from_public_bytes(raw)
        except ValueError as exc:
            raise SignedReviewError("invalid Ed25519 public key") from exc
        by_keyid[keyid] = {
            "keyid": keyid,
            "principal": principal,
            "seat": seat,
            "public_key": public_key,
        }
        seats.add(seat)
        principals.add(principal)
        previous_keyid = keyid
    return by_keyid


def _certificate_context(certificate: Mapping[str, Any]) -> dict[str, Any]:
    _certificate_core(certificate)
    context = {
        "format": SIGNED_PAYLOAD_FORMAT,
        "schema": SIGNED_PAYLOAD_SCHEMA,
        "certificate_digest": certificate["certificate_digest"],
        "proposal_id": certificate["proposal_id"],
        "proposal_digest": certificate["proposal_digest"],
        "event_key": copy.deepcopy(certificate["event_key"]),
        "base_decision_ids": list(certificate["base_decision_ids"]),
        "base_decision_digests": copy.deepcopy(certificate["base_decision_digests"]),
        "policy_digest": certificate["policy_digest"],
    }
    _sha256(context["certificate_digest"], "certificate_digest")
    _sha256(context["proposal_digest"], "proposal_digest")
    _sha256(context["policy_digest"], "policy_digest")
    return context


def sign_review_vote(
    certificate: Mapping[str, Any],
    vote: Mapping[str, Any],
    private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    """Sign one vote together with its exact proposal and decision context."""
    normalized = _normalize_vote(vote)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519PrivateKey")
    raw_public = _raw_public_key(private_key.public_key())
    keyid = hashlib.sha256(raw_public).hexdigest()
    payload_object = {
        **_certificate_context(certificate),
        "vote": normalized,
    }
    payload = _json_bytes(payload_object)
    signature = private_key.sign(pae(PAYLOAD_TYPE, payload))
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": _b64encode(payload),
        "signatures": [{"keyid": keyid, "sig": _b64encode(signature)}],
    }


def verify_signed_review_vote(
    envelope: Mapping[str, Any],
    trust_store: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify DSSE PAE signature and bind signed seat/principal to trusted key."""
    if not isinstance(envelope, Mapping) or set(envelope) != ENVELOPE_FIELDS:
        raise SignedReviewError("DSSE envelope has missing or unrecognized fields")
    if envelope["payloadType"] != PAYLOAD_TYPE:
        raise SignedReviewError("DSSE payloadType is not the authority-review vote type")
    raw_payload = _b64decode(envelope["payload"], "DSSE payload")
    signatures = envelope["signatures"]
    if not isinstance(signatures, list) or len(signatures) != 1:
        raise SignedReviewError("each review vote envelope must contain exactly one signature")
    signature_record = signatures[0]
    if not isinstance(signature_record, Mapping) or set(signature_record) != SIGNATURE_FIELDS:
        raise SignedReviewError("DSSE signature record has invalid fields")
    keyid = _sha256(signature_record.get("keyid"), "DSSE signature keyid")
    signature = _b64decode(signature_record.get("sig"), "DSSE signature")
    if len(signature) != 64:
        raise SignedReviewError("Ed25519 signatures must contain exactly 64 bytes")

    trusted_keys = _validate_trust_store(trust_store)
    trusted = trusted_keys.get(keyid)
    if trusted is None:
        raise SignedReviewError("DSSE keyid is not present in the supplied trust store")
    try:
        trusted["public_key"].verify(
            signature,
            pae(envelope["payloadType"], raw_payload),
        )
    except InvalidSignature as exc:
        raise SignedReviewError("DSSE Ed25519 signature verification failed") from exc

    signed_payload = _strict_json(raw_payload)
    if set(signed_payload) != SIGNED_PAYLOAD_FIELDS:
        raise SignedReviewError("signed payload has missing or unrecognized fields")
    if (
        signed_payload["format"] != SIGNED_PAYLOAD_FORMAT
        or signed_payload["schema"] != SIGNED_PAYLOAD_SCHEMA
    ):
        raise SignedReviewError("unsupported signed review payload format or schema")
    context = {key: signed_payload[key] for key in SIGNED_CONTEXT_FIELDS}
    _sha256(context["certificate_digest"], "signed payload certificate_digest")
    _sha256(context["proposal_digest"], "signed payload proposal_digest")
    _sha256(context["policy_digest"], "signed payload policy_digest")
    if not isinstance(context["base_decision_ids"], list) or not context["base_decision_ids"]:
        raise SignedReviewError("signed payload must retain base decision IDs")
    if not isinstance(context["base_decision_digests"], Mapping):
        raise SignedReviewError("signed payload base decision digests must be an object")
    if set(context["base_decision_ids"]) != set(context["base_decision_digests"]):
        raise SignedReviewError("signed payload base decision digests do not cover its bases")
    for decision_id, decision_digest in context["base_decision_digests"].items():
        _nonempty(decision_id, "base decision ID")
        _sha256(decision_digest, "base decision digest")
    if (
        not isinstance(context["event_key"], Mapping)
        or set(context["event_key"]) != {"kind", "logical_time"}
        or not isinstance(context["event_key"]["kind"], str)
        or not context["event_key"]["kind"].strip()
        or isinstance(context["event_key"]["logical_time"], bool)
        or not isinstance(context["event_key"]["logical_time"], int)
        or context["event_key"]["logical_time"] < 0
    ):
        raise SignedReviewError("signed payload event key is invalid")

    vote = _normalize_vote(signed_payload["vote"])
    if vote["seat"] != trusted["seat"]:
        raise SignedReviewError("signed vote seat differs from the trusted key's assigned seat")
    if vote["reviewer_ref"] != trusted["principal"]:
        raise SignedReviewError("signed vote reviewer_ref differs from the trusted principal")
    return {
        "vote": vote,
        "context": context,
        "keyid": keyid,
        "principal": trusted["principal"],
        "seat": trusted["seat"],
        "payload_sha256": hashlib.sha256(raw_payload).hexdigest(),
    }


def _certificate_core(certificate: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(certificate, Mapping):
        raise TypeError("certificate must be a mapping")
    if certificate.get("format") != "in-formation.authority-review-certificate":
        raise SignedReviewError("unsupported authority review certificate format")
    if certificate.get("schema") != "in-formation.authority-review-certificate/0.1":
        raise SignedReviewError("unsupported authority review certificate schema")
    supplied = _sha256(certificate.get("certificate_digest"), "certificate_digest")
    core = {key: value for key, value in certificate.items() if key != "certificate_digest"}
    if digest(core) != supplied:
        raise SignedReviewError("authority review certificate digest mismatch")
    votes = certificate.get("votes")
    if not isinstance(votes, list):
        raise SignedReviewError("authority review certificate votes must be a list")
    return core


def _check_review_artifacts(
    votes: Sequence[Mapping[str, Any]],
    review_artifacts: Mapping[str, bytes | str] | None,
) -> bool:
    if review_artifacts is None:
        return False
    if not isinstance(review_artifacts, Mapping):
        raise TypeError("review_artifacts must map artifact references to bytes or text")
    expected_refs = {vote["review_ref"] for vote in votes}
    if set(review_artifacts) != expected_refs:
        raise SignedReviewError("review artifact set does not exactly cover the signed vote references")
    for vote in votes:
        value = review_artifacts[vote["review_ref"]]
        raw = value.encode("utf-8") if isinstance(value, str) else value
        if not isinstance(raw, bytes):
            raise TypeError("review artifact values must be bytes or strings")
        if hashlib.sha256(raw).hexdigest() != vote["review_sha256"]:
            raise SignedReviewError(
                f"review artifact digest does not match signed receipt: {vote['review_ref']}"
            )
    return True


def build_signed_review_bundle(
    certificate: Mapping[str, Any],
    envelopes: Sequence[Mapping[str, Any]],
    trust_store: Mapping[str, Any],
    *,
    review_artifacts: Mapping[str, bytes | str] | None = None,
) -> dict[str, Any]:
    """Verify every signed vote and bind its bundle to a review certificate."""
    certificate_core = _certificate_core(certificate)
    trust_keys = _validate_trust_store(trust_store)
    if not isinstance(envelopes, (list, tuple)):
        raise TypeError("envelopes must be a sequence")
    cert_votes = certificate["votes"]
    expected_context = _certificate_context(certificate)
    if not cert_votes:
        raise SignedReviewError("cannot build a signed bundle with no review votes")
    if len(envelopes) != len(cert_votes):
        raise SignedReviewError("signed envelope count must equal certificate vote count")
    remaining = {
        (vote["seat"], vote["reviewer_ref"]): vote
        for vote in cert_votes
    }
    signed = []
    seen_keyids: set[str] = set()
    for envelope in envelopes:
        verified = verify_signed_review_vote(envelope, trust_store)
        vote = verified["vote"]
        identity = (vote["seat"], vote["reviewer_ref"])
        expected_vote = remaining.pop(identity, None)
        if expected_vote is None or vote != expected_vote:
            raise SignedReviewError("signed vote does not exactly match a certificate review receipt")
        if verified["context"] != expected_context:
            raise SignedReviewError("signed vote is bound to a different proposal or authority context")
        if verified["keyid"] in seen_keyids:
            raise SignedReviewError("one trusted key cannot sign multiple reviewer seats")
        seen_keyids.add(verified["keyid"])
        signed.append({
            "seat": verified["seat"],
            "reviewer_ref": verified["principal"],
            "keyid": verified["keyid"],
            "envelope": copy.deepcopy(dict(envelope)),
        })
    if remaining:
        raise SignedReviewError("signed bundle omits one or more certificate review receipts")
    signed.sort(key=lambda item: REVIEW_SEATS.index(item["seat"]))
    artifacts_verified = _check_review_artifacts(cert_votes, review_artifacts)
    core = {
        "format": FORMAT,
        "schema": SCHEMA,
        "signature_profile": SIGNATURE_PROFILE,
        "certificate_digest": certificate["certificate_digest"],
        "payload_type": PAYLOAD_TYPE,
        "trust_store_digest": digest(trust_store),
        "review_artifacts_verified": artifacts_verified,
        "signed_review_votes": signed,
    }
    return {**core, "bundle_digest": digest(core)}


def validate_signed_review_bundle(
    certificate: Mapping[str, Any],
    bundle: Mapping[str, Any],
    trust_store: Mapping[str, Any],
    *,
    review_artifacts: Mapping[str, bytes | str] | None = None,
) -> None:
    """Reverify the envelope signatures, certificate correspondence, and bundle."""
    if not isinstance(bundle, Mapping) or set(bundle) != BUNDLE_FIELDS:
        raise SignedReviewError("signed review bundle has missing or unrecognized fields")
    supplied_digest = _sha256(bundle.get("bundle_digest"), "bundle_digest")
    core = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    if digest(core) != supplied_digest:
        raise SignedReviewError("signed review bundle digest mismatch")
    if bundle["format"] != FORMAT or bundle["schema"] != SCHEMA:
        raise SignedReviewError("unsupported signed review bundle format or schema")
    if bundle["signature_profile"] != SIGNATURE_PROFILE:
        raise SignedReviewError("unsupported signed review signature profile")
    if bundle["payload_type"] != PAYLOAD_TYPE:
        raise SignedReviewError("signed review bundle payload type mismatch")
    if bundle["trust_store_digest"] != digest(trust_store):
        raise SignedReviewError("signed review bundle was produced against a different trust store")
    rebuilt = build_signed_review_bundle(
        certificate,
        [item["envelope"] for item in bundle["signed_review_votes"]],
        trust_store,
        review_artifacts=review_artifacts,
    )
    if review_artifacts is None:
        # The flag records that the producer checked the referenced bytes when
        # assembling the bundle. Without those bytes, this verifier can
        # re-check signatures but cannot independently repeat that check.
        rebuilt["review_artifacts_verified"] = bundle["review_artifacts_verified"]
        rebuilt_core = {
            key: value for key, value in rebuilt.items()
            if key != "bundle_digest"
        }
        rebuilt["bundle_digest"] = digest(rebuilt_core)
    if rebuilt != dict(bundle):
        raise SignedReviewError("signed review bundle differs from verified reconstruction")


def _proposal_certificate_entry(
    ledger: Mapping[str, Any],
    proposal_id: str,
) -> dict[str, Any]:
    entries = [
        entry for entry in _entries_of_type(ledger, "proposal_review_certified")
        if entry["payload"]["proposal_id"] == proposal_id
    ]
    if len(entries) != 1:
        raise SignedReviewError("proposal must have exactly one recorded review certificate")
    return entries[0]


def _proposal_signed_entries(
    ledger: Mapping[str, Any],
    proposal_id: str,
) -> list[dict[str, Any]]:
    return [
        entry for entry in _entries_of_type(ledger, "proposal_review_signed")
        if entry["payload"]["proposal_id"] == proposal_id
    ]


def record_signed_review_bundle(
    ledger: Mapping[str, Any],
    proposal_id: str,
    bundle: Mapping[str, Any],
    trust_store: Mapping[str, Any],
    *,
    recorded_by: str,
    review_artifacts: Mapping[str, bytes | str] | None = None,
) -> dict[str, Any]:
    """Append a complete signed-review bundle and its public trust-store snapshot."""
    validate_ledger(ledger)
    proposal_id = _lineage_nonempty(proposal_id, "proposal_id")
    proposal_entries = [
        entry for entry in _entries_of_type(ledger, "revision_proposed")
        if entry["payload"]["proposal_id"] == proposal_id
    ]
    if len(proposal_entries) != 1:
        raise SignedReviewError("proposal must exist exactly once")
    certificate_entry = _proposal_certificate_entry(ledger, proposal_id)
    proposal = proposal_entries[0]["payload"]
    if any(
        entry["payload"]["proposal_id"] == proposal_id
        for entry in _entries_of_type(ledger, "proposal_resolved")
    ):
        raise SignedReviewError("cannot record signed receipts after proposal resolution")
    if _proposal_signed_entries(ledger, proposal_id):
        raise SignedReviewError("proposal already has an immutable signed review bundle")
    frontier = current_frontier(ledger, proposal["event_key"])["decision_ids"]
    if frontier != proposal["base_decision_ids"]:
        raise SignedReviewError("cannot record signed receipts against a stale proposal frontier")

    certificate = certificate_entry["payload"]["certificate"]
    validate_signed_review_bundle(
        certificate,
        bundle,
        trust_store,
        review_artifacts=review_artifacts,
    )
    if bundle["certificate_digest"] != certificate_entry["payload"]["certificate_digest"]:
        raise SignedReviewError("signed bundle certificate digest differs from ledger certificate")
    trust_digest = digest(trust_store)
    if bundle["trust_store_digest"] != trust_digest:
        raise SignedReviewError("signed bundle trust-store digest differs from supplied trust store")

    payload = {
        "proposal_id": proposal_id,
        "event_key": copy.deepcopy(proposal["event_key"]),
        "certificate_digest": certificate_entry["payload"]["certificate_digest"],
        "bundle_digest": bundle["bundle_digest"],
        "trust_store_digest": trust_digest,
        "bundle": copy.deepcopy(dict(bundle)),
        "trust_store": copy.deepcopy(dict(trust_store)),
    }
    updated = _append_entry(
        ledger,
        "proposal_review_signed",
        _lineage_nonempty(recorded_by, "recorded_by"),
        payload,
    )
    validate_signed_review_bundles_in_ledger(
        updated,
        trusted_store_digests={proposal_id: trust_digest},
        review_artifacts_by_proposal=(
            {proposal_id: review_artifacts} if review_artifacts is not None else None
        ),
        validate_core=False,
    )
    return updated


def validate_signed_review_bundles_in_ledger(
    ledger: Mapping[str, Any],
    *,
    trusted_store_digests: Mapping[str, str] | None = None,
    review_artifacts_by_proposal: Mapping[str, Mapping[str, bytes | str]] | None = None,
    validate_core: bool = True,
) -> None:
    """Reverify every ledger-anchored bundle against its embedded public-key snapshot.

    Supplying trusted_store_digests pins one or more proposal trust stores to an
    out-of-band digest. Without that parameter, this function verifies
    possession of the embedded public keys but does not authenticate who
    provisioned those keys.
    """
    if validate_core:
        validate_ledger(
            ledger,
            validate_embedded_certificates=False,
            validate_embedded_signatures=False,
        )
    if trusted_store_digests is not None and not isinstance(trusted_store_digests, Mapping):
        raise TypeError("trusted_store_digests must map proposal IDs to pinned digests")
    for entry in _entries_of_type(ledger, "proposal_review_signed"):
        payload = entry["payload"]
        proposal_id = _lineage_nonempty(payload.get("proposal_id"), "proposal_id")
        certificate_entry = _proposal_certificate_entry(ledger, proposal_id)
        certificate = certificate_entry["payload"]["certificate"]
        if payload["certificate_digest"] != certificate_entry["payload"]["certificate_digest"]:
            raise SignedReviewError("signed ledger event certificate digest mismatch")
        trust_store = payload["trust_store"]
        actual_trust_digest = digest(trust_store)
        if payload["trust_store_digest"] != actual_trust_digest:
            raise SignedReviewError("signed ledger event trust-store digest mismatch")
        if trusted_store_digests is not None:
            expected_trust_digest = trusted_store_digests.get(proposal_id)
            if expected_trust_digest is None:
                raise SignedReviewError(
                    f"no out-of-band trust-store pin supplied for proposal {proposal_id}"
                )
            _lineage_sha256(expected_trust_digest, "trusted trust-store digest")
            if actual_trust_digest != expected_trust_digest:
                raise SignedReviewError("embedded trust store differs from out-of-band trust pin")
        review_artifacts = (
            review_artifacts_by_proposal.get(proposal_id)
            if review_artifacts_by_proposal is not None
            else None
        )
        validate_signed_review_bundle(
            certificate,
            payload["bundle"],
            trust_store,
            review_artifacts=review_artifacts,
        )


def resolve_signed_reviewed_proposal(
    ledger: Mapping[str, Any],
    proposal_id: str,
    *,
    trusted_trust_store: Mapping[str, Any],
    rationale: str,
    resolved_by: str,
    review_artifacts: Mapping[str, bytes | str] | None = None,
) -> dict[str, Any]:
    """Resolve a signed proposal only when its recorded trust store is supplied by caller."""
    validate_ledger(ledger)
    proposal_id = _lineage_nonempty(proposal_id, "proposal_id")
    certificate_entry = _proposal_certificate_entry(ledger, proposal_id)
    signed_entries = _proposal_signed_entries(ledger, proposal_id)
    if len(signed_entries) != 1:
        raise SignedReviewError("proposal must have exactly one ledger-anchored signed bundle")
    record = signed_entries[0]["payload"]
    if digest(trusted_trust_store) != record["trust_store_digest"]:
        raise SignedReviewError("caller-supplied trusted store does not match the recorded trust-store pin")
    validate_signed_review_bundle(
        certificate_entry["payload"]["certificate"],
        record["bundle"],
        trusted_trust_store,
        review_artifacts=review_artifacts,
    )
    certificate = certificate_entry["payload"]["certificate"]
    proposal_entries = [
        entry for entry in _entries_of_type(ledger, "revision_proposed")
        if entry["payload"]["proposal_id"] == proposal_id
    ]
    if len(proposal_entries) != 1:
        raise SignedReviewError("proposal must exist exactly once")
    proposal = proposal_entries[0]["payload"]
    frontier = current_frontier(ledger, proposal["event_key"])["decision_ids"]
    outcome = (
        "STALE"
        if frontier != proposal["base_decision_ids"]
        else certificate["evaluation"]["outcome"]
    )
    return resolve_proposal(
        ledger,
        proposal_id,
        outcome=outcome,
        rationale=rationale,
        resolved_by=resolved_by,
        signed_review_bundle_digest=record["bundle_digest"],
    )
