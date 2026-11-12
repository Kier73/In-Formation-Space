"""Root-signed, versioned reviewer trust manifests.

The manifest binds a reviewer trust store to a registry identity, generation,
validity window, and predecessor digest. Verification requires externally
pinned root public keys and a caller-supplied verification time. This borrows
selected rollback/freeze defenses from TUF; it is not a TUF implementation.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from authority_lineage import digest
from signed_review_receipts import (
    SignedReviewError,
    _certificate_core,
    _validate_trust_store,
    pae,
    validate_signed_review_bundle,
)

FORMAT = "in-formation.review-trust-manifest"
SCHEMA = "in-formation.review-trust-manifest/0.1"
PAYLOAD_TYPE = "application/vnd.in-formation.review-trust-manifest+json;version=0.1"
SIGNATURE_PROFILE = "DSSEv1+Ed25519"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_FIELDS = {
    "format",
    "schema",
    "registry_id",
    "generation",
    "previous_manifest_digest",
    "issued_at",
    "expires_at",
    "trust_store",
    "trust_store_digest",
    "manifest_digest",
}
_ENVELOPE_FIELDS = {"payloadType", "payload", "signatures"}
_SIGNATURE_FIELDS = {"keyid", "sig"}
_UNSET = object()


class TrustManifestError(ValueError):
    """A reviewer trust manifest is invalid, untrusted, expired, or rolled back."""


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustManifestError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise TrustManifestError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: object, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise TrustManifestError(f"{label} must be a non-empty base64 string")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise TrustManifestError(f"{label} is not valid base64") from exc
    if _b64encode(raw) != value:
        raise TrustManifestError(f"{label} is not canonical base64")
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
        raise TrustManifestError("trust manifest is not serializable JSON") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TrustManifestError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                TrustManifestError(f"non-finite JSON number is forbidden: {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustManifestError("trust manifest payload is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise TrustManifestError("trust manifest payload must be a JSON object")
    return value


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise TrustManifestError(f"{label} must use YYYY-MM-DDTHH:MM:SSZ UTC format")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise TrustManifestError(f"{label} is not a valid UTC timestamp") from exc
    return parsed


def _key_id(public_key: Ed25519PublicKey) -> str:
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("root public keys must be Ed25519PublicKey instances")
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def _public_key_map(
    trusted_root_public_keys: Mapping[str, Ed25519PublicKey],
) -> dict[str, Ed25519PublicKey]:
    if not isinstance(trusted_root_public_keys, Mapping) or not trusted_root_public_keys:
        raise TrustManifestError("at least one externally pinned root public key is required")
    result = {}
    for keyid, public_key in trusted_root_public_keys.items():
        _sha256(keyid, "root key ID")
        actual = _key_id(public_key)
        if keyid != actual:
            raise TrustManifestError("root key ID does not match its public-key fingerprint")
        if keyid in result:
            raise TrustManifestError("root key IDs must be unique")
        result[keyid] = public_key
    return result


def build_trust_manifest(
    *,
    registry_id: str,
    generation: int,
    trust_store: Mapping[str, Any],
    issued_at: str,
    expires_at: str,
    previous_manifest_digest: str | None = None,
) -> dict[str, Any]:
    """Build an immutable manifest; generation one is the chain genesis."""
    registry = _nonempty(registry_id, "registry_id")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise TrustManifestError("generation must be a positive integer")
    issued = _parse_utc(issued_at, "issued_at")
    expires = _parse_utc(expires_at, "expires_at")
    if expires <= issued:
        raise TrustManifestError("expires_at must be later than issued_at")
    if generation == 1 and previous_manifest_digest is not None:
        raise TrustManifestError("generation one must not have a predecessor digest")
    if generation > 1:
        _sha256(previous_manifest_digest, "previous_manifest_digest")
    _validate_trust_store(trust_store)
    store_digest = digest(trust_store)
    core = {
        "format": FORMAT,
        "schema": SCHEMA,
        "registry_id": registry,
        "generation": generation,
        "previous_manifest_digest": previous_manifest_digest,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "trust_store": copy.deepcopy(dict(trust_store)),
        "trust_store_digest": store_digest,
    }
    return {**core, "manifest_digest": digest(core)}


def sign_trust_manifest(
    manifest: Mapping[str, Any],
    root_private_keys: Sequence[Ed25519PrivateKey],
) -> dict[str, Any]:
    """Sign one manifest with one or more root keys using DSSE PAE."""
    _validate_manifest_document(manifest)
    if not isinstance(root_private_keys, (list, tuple)) or not root_private_keys:
        raise TrustManifestError("at least one root private key is required")
    manifest_bytes = _json_bytes(manifest)
    signatures = []
    seen = set()
    for index, private_key in enumerate(root_private_keys):
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError(f"root_private_keys[{index}] must be an Ed25519PrivateKey")
        keyid = _key_id(private_key.public_key())
        if keyid in seen:
            raise TrustManifestError("a root key cannot sign the same manifest more than once")
        signatures.append({
            "keyid": keyid,
            "sig": _b64encode(private_key.sign(pae(PAYLOAD_TYPE, manifest_bytes))),
        })
        seen.add(keyid)
    signatures.sort(key=lambda item: item["keyid"])
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": _b64encode(manifest_bytes),
        "signatures": signatures,
    }


def _validate_manifest_document(manifest: Mapping[str, Any]) -> None:
    if not isinstance(manifest, Mapping) or set(manifest) != _MANIFEST_FIELDS:
        raise TrustManifestError("manifest has missing or unrecognized fields")
    if manifest["format"] != FORMAT or manifest["schema"] != SCHEMA:
        raise TrustManifestError("unsupported trust manifest format or schema")
    _nonempty(manifest["registry_id"], "registry_id")
    generation = manifest["generation"]
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise TrustManifestError("manifest generation must be a positive integer")
    predecessor = manifest["previous_manifest_digest"]
    if generation == 1:
        if predecessor is not None:
            raise TrustManifestError("genesis manifest cannot name a predecessor")
    else:
        _sha256(predecessor, "previous_manifest_digest")
    issued = _parse_utc(manifest["issued_at"], "issued_at")
    expires = _parse_utc(manifest["expires_at"], "expires_at")
    if expires <= issued:
        raise TrustManifestError("manifest expiry must be later than issue time")
    _validate_trust_store(manifest["trust_store"])
    if manifest["trust_store_digest"] != digest(manifest["trust_store"]):
        raise TrustManifestError("trust-store digest does not match manifest contents")
    supplied = _sha256(manifest["manifest_digest"], "manifest_digest")
    core = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if digest(core) != supplied:
        raise TrustManifestError("manifest digest mismatch")


def verify_trust_manifest(
    envelope: Mapping[str, Any],
    trusted_root_public_keys: Mapping[str, Ed25519PublicKey],
    *,
    verification_time: str,
    root_threshold: int = 1,
    expected_registry_id: str | None = None,
    minimum_generation: int | None = None,
    expected_generation: int | None = None,
    expected_previous_manifest_digest: str | None | object = _UNSET,
) -> dict[str, Any]:
    """Verify a root-signed manifest against pinned keys and anti-rollback state.

    minimum_generation is caller-persisted state. For strict chain continuity,
    supply expected_generation and expected_previous_manifest_digest.
    """
    roots = _public_key_map(trusted_root_public_keys)
    if isinstance(root_threshold, bool) or not isinstance(root_threshold, int):
        raise TrustManifestError("root_threshold must be an integer")
    if root_threshold < 1 or root_threshold > len(roots):
        raise TrustManifestError("root_threshold is outside the supplied root-key set")
    when = _parse_utc(verification_time, "verification_time")
    if not isinstance(envelope, Mapping) or set(envelope) != _ENVELOPE_FIELDS:
        raise TrustManifestError("DSSE trust manifest envelope has invalid fields")
    if envelope["payloadType"] != PAYLOAD_TYPE:
        raise TrustManifestError("DSSE payloadType is not the trust manifest type")
    raw_payload = _b64decode(envelope["payload"], "DSSE manifest payload")
    manifest = _strict_json(raw_payload)
    _validate_manifest_document(manifest)

    signatures = envelope["signatures"]
    if not isinstance(signatures, list) or not signatures:
        raise TrustManifestError("manifest envelope must contain root signatures")
    valid_keyids = set()
    seen_keyids = set()
    pae_bytes = pae(envelope["payloadType"], raw_payload)
    for index, item in enumerate(signatures):
        if not isinstance(item, Mapping) or set(item) != _SIGNATURE_FIELDS:
            raise TrustManifestError(f"manifest signature {index} has invalid fields")
        keyid = _sha256(item["keyid"], f"signatures[{index}].keyid")
        if keyid in seen_keyids:
            raise TrustManifestError("duplicate root signature key IDs are forbidden")
        seen_keyids.add(keyid)
        public_key = roots.get(keyid)
        if public_key is None:
            raise TrustManifestError("manifest contains a signature from an unpinned root key")
        signature = _b64decode(item["sig"], f"signatures[{index}].sig")
        if len(signature) != 64:
            raise TrustManifestError("Ed25519 signatures must contain 64 bytes")
        try:
            public_key.verify(signature, pae_bytes)
        except InvalidSignature as exc:
            raise TrustManifestError(f"invalid root signature for key {keyid}") from exc
        valid_keyids.add(keyid)
    if len(valid_keyids) < root_threshold:
        raise TrustManifestError("manifest does not meet the pinned root signature threshold")

    if expected_registry_id is not None:
        if manifest["registry_id"] != _nonempty(expected_registry_id, "expected_registry_id"):
            raise TrustManifestError("manifest belongs to a different registry")
    if minimum_generation is not None:
        if (
            isinstance(minimum_generation, bool)
            or not isinstance(minimum_generation, int)
            or minimum_generation < 1
        ):
            raise TrustManifestError("minimum_generation must be a positive integer")
        if manifest["generation"] < minimum_generation:
            raise TrustManifestError("manifest generation is below the persisted minimum")
    if expected_generation is not None:
        if isinstance(expected_generation, bool) or not isinstance(expected_generation, int):
            raise TrustManifestError("expected_generation must be an integer")
        if manifest["generation"] != expected_generation:
            raise TrustManifestError("manifest generation does not match expected successor")
        if expected_previous_manifest_digest is _UNSET:
            raise TrustManifestError(
                "strict generation checking requires an expected predecessor digest"
            )
        if manifest["previous_manifest_digest"] != expected_previous_manifest_digest:
            raise TrustManifestError("manifest predecessor digest does not extend trusted history")
    elif expected_previous_manifest_digest is not _UNSET:
        raise TrustManifestError(
            "expected predecessor digest is only valid with expected_generation"
        )

    issued = _parse_utc(manifest["issued_at"], "issued_at")
    expires = _parse_utc(manifest["expires_at"], "expires_at")
    if when < issued:
        raise TrustManifestError("manifest is not yet valid at the supplied verification time")
    if when >= expires:
        raise TrustManifestError("manifest is expired; reject as a potential freeze condition")
    return {
        "manifest": manifest,
        "manifest_digest": manifest["manifest_digest"],
        "registry_id": manifest["registry_id"],
        "generation": manifest["generation"],
        "trust_store": copy.deepcopy(manifest["trust_store"]),
        "trust_store_digest": manifest["trust_store_digest"],
        "valid_at": verification_time,
        "root_keyids": sorted(valid_keyids),
        "root_signature_threshold": root_threshold,
    }


def verify_review_bundle_with_manifest(
    certificate: Mapping[str, Any],
    bundle: Mapping[str, Any],
    manifest_envelope: Mapping[str, Any],
    trusted_root_public_keys: Mapping[str, Ed25519PublicKey],
    *,
    verification_time: str,
    root_threshold: int = 1,
    expected_registry_id: str | None = None,
    minimum_generation: int | None = None,
    expected_generation: int | None = None,
    expected_previous_manifest_digest: str | None | object = _UNSET,
    review_artifacts: Mapping[str, bytes | str] | None = None,
) -> dict[str, Any]:
    """Verify a signed review bundle using a root-authenticated trust manifest."""
    trust = verify_trust_manifest(
        manifest_envelope,
        trusted_root_public_keys,
        verification_time=verification_time,
        root_threshold=root_threshold,
        expected_registry_id=expected_registry_id,
        minimum_generation=minimum_generation,
        expected_generation=expected_generation,
        expected_previous_manifest_digest=expected_previous_manifest_digest,
    )
    validate_signed_review_bundle(
        certificate,
        bundle,
        trust["trust_store"],
        review_artifacts=review_artifacts,
    )
    if bundle["trust_store_digest"] != trust["trust_store_digest"]:
        raise TrustManifestError("review bundle trust-store digest differs from root-signed manifest")
    return {
        "registry_id": trust["registry_id"],
        "manifest_generation": trust["generation"],
        "manifest_digest": trust["manifest_digest"],
        "root_keyids": trust["root_keyids"],
        "trust_store_digest": trust["trust_store_digest"],
        "bundle_digest": bundle["bundle_digest"],
        "review_artifacts_verified": bundle["review_artifacts_verified"],
        "verification_time": verification_time,
    }


def verify_ledger_signed_review_bundle_with_manifest(
    ledger: Mapping[str, Any],
    proposal_id: str,
    manifest_envelope: Mapping[str, Any],
    trusted_root_public_keys: Mapping[str, Ed25519PublicKey],
    *,
    verification_time: str,
    root_threshold: int = 1,
    expected_registry_id: str | None = None,
    minimum_generation: int | None = None,
    expected_generation: int | None = None,
    expected_previous_manifest_digest: str | None | object = _UNSET,
    review_artifacts: Mapping[str, bytes | str] | None = None,
) -> dict[str, Any]:
    """Verify one signed ledger event against a root-authenticated trust manifest."""
    from authority_lineage import _entries_of_type, validate_ledger

    validate_ledger(ledger)
    proposal_id = _nonempty(proposal_id, "proposal_id")
    signed_entries = [
        entry for entry in _entries_of_type(ledger, "proposal_review_signed")
        if entry["payload"]["proposal_id"] == proposal_id
    ]
    certificate_entries = [
        entry for entry in _entries_of_type(ledger, "proposal_review_certified")
        if entry["payload"]["proposal_id"] == proposal_id
    ]
    if len(signed_entries) != 1 or len(certificate_entries) != 1:
        raise TrustManifestError("proposal must have exactly one signed event and one certificate")
    certificate = certificate_entries[0]["payload"]["certificate"]
    payload = signed_entries[0]["payload"]
    trust = verify_trust_manifest(
        manifest_envelope,
        trusted_root_public_keys,
        verification_time=verification_time,
        root_threshold=root_threshold,
        expected_registry_id=expected_registry_id,
        minimum_generation=minimum_generation,
        expected_generation=expected_generation,
        expected_previous_manifest_digest=expected_previous_manifest_digest,
    )
    if payload["trust_store_digest"] != trust["trust_store_digest"]:
        raise TrustManifestError("ledger trust-store snapshot differs from root-signed manifest")
    if payload["trust_store"] != trust["trust_store"]:
        raise TrustManifestError("ledger trust-store document differs from root-signed manifest")
    validate_signed_review_bundle(
        certificate,
        payload["bundle"],
        trust["trust_store"],
        review_artifacts=review_artifacts,
    )
    return {
        "proposal_id": proposal_id,
        "registry_id": trust["registry_id"],
        "manifest_generation": trust["generation"],
        "manifest_digest": trust["manifest_digest"],
        "trust_store_digest": trust["trust_store_digest"],
        "certificate_digest": payload["certificate_digest"],
        "bundle_digest": payload["bundle_digest"],
        "review_artifacts_verified": payload["bundle"]["review_artifacts_verified"],
        "verification_time": verification_time,
    }
