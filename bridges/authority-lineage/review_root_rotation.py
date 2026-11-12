"""Dual-authorized root-key rotation for reviewer trust manifests.

A root transition is an explicit DSSE document signed by thresholds from both
the currently trusted root-key set and the proposed successor root-key set.
The caller must retain the previously accepted generation and manifest digest.
This borrows the old-and-new root threshold continuity pattern from TUF; it is
not a TUF implementation.
"""
from __future__ import annotations

import base64
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

from authority_lineage import digest
from review_trust_manifest import (
    PAYLOAD_TYPE as TRUST_MANIFEST_PAYLOAD_TYPE,
    TrustManifestError,
    _key_id,
    _parse_utc,
    _validate_manifest_document,
    verify_trust_manifest,
    pae,
)

FORMAT = "in-formation.review-root-transition"
SCHEMA = "in-formation.review-root-transition/0.1"
PAYLOAD_TYPE = "application/vnd.in-formation.review-root-transition+json;version=0.1"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_TRANSITION_FIELDS = {
    "format",
    "schema",
    "registry_id",
    "previous_generation",
    "previous_manifest_digest",
    "next_generation",
    "next_manifest_digest",
    "new_root_role",
    "transition_digest",
}
_ROOT_ROLE_FIELDS = {"keys", "threshold"}
_ROOT_KEY_FIELDS = {"keyid", "public_key"}
_ENVELOPE_FIELDS = {"payloadType", "payload", "signatures"}
_SIGNATURE_FIELDS = {"keyid", "sig"}


class RootRotationError(ValueError):
    """A root transition is malformed, incorrectly authorized, or forked."""


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RootRotationError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise RootRotationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: object, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise RootRotationError(f"{label} must be a non-empty base64 string")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise RootRotationError(f"{label} is not valid base64") from exc
    if _b64encode(raw) != value:
        raise RootRotationError(f"{label} is not canonical base64")
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
        raise RootRotationError("root transition is not serializable JSON") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RootRotationError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                RootRotationError(f"non-finite JSON number is forbidden: {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootRotationError("root transition payload is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise RootRotationError("root transition payload must be a JSON object")
    return value


def _root_key_map(
    keys: Mapping[str, Ed25519PublicKey],
    *,
    label: str,
) -> dict[str, Ed25519PublicKey]:
    if not isinstance(keys, Mapping) or not keys:
        raise RootRotationError(f"{label} must contain at least one Ed25519 public key")
    result = {}
    for keyid, public_key in keys.items():
        _sha256(keyid, f"{label} keyid")
        try:
            actual = _key_id(public_key)
        except (TypeError, ValueError) as exc:
            raise RootRotationError(f"{label} values must be Ed25519 public keys") from exc
        if keyid != actual:
            raise RootRotationError(f"{label} keyid does not match its public-key fingerprint")
        if keyid in result:
            raise RootRotationError(f"{label} contains duplicate key IDs")
        result[keyid] = public_key
    return result


def _private_key_id(private_key: Ed25519PrivateKey) -> str:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("root signing keys must be Ed25519PrivateKey instances")
    return _key_id(private_key.public_key())


def _root_role_document(
    new_root_public_keys: Mapping[str, Ed25519PublicKey],
    threshold: int,
) -> dict[str, Any]:
    keys = _root_key_map(new_root_public_keys, label="new root role")
    if isinstance(threshold, bool) or not isinstance(threshold, int):
        raise RootRotationError("new root threshold must be an integer")
    if threshold < 1 or threshold > len(keys):
        raise RootRotationError("new root threshold is outside the new root-key set")
    entries = []
    for keyid, public_key in sorted(keys.items()):
        raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        entries.append({"keyid": keyid, "public_key": _b64encode(raw)})
    return {"keys": entries, "threshold": threshold}


def _validate_transition_document(transition: Mapping[str, Any]) -> dict[str, Ed25519PublicKey]:
    if not isinstance(transition, Mapping) or set(transition) != _TRANSITION_FIELDS:
        raise RootRotationError("root transition has missing or unrecognized fields")
    if transition["format"] != FORMAT or transition["schema"] != SCHEMA:
        raise RootRotationError("unsupported root transition format or schema")
    _nonempty(transition["registry_id"], "registry_id")
    previous_generation = transition["previous_generation"]
    next_generation = transition["next_generation"]
    for value, label in (
        (previous_generation, "previous_generation"),
        (next_generation, "next_generation"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RootRotationError(f"{label} must be a positive integer")
    if next_generation != previous_generation + 1:
        raise RootRotationError("root transition generation must be the exact successor")
    _sha256(transition["previous_manifest_digest"], "previous_manifest_digest")
    _sha256(transition["next_manifest_digest"], "next_manifest_digest")
    role = transition["new_root_role"]
    if not isinstance(role, Mapping) or set(role) != _ROOT_ROLE_FIELDS:
        raise RootRotationError("new_root_role has invalid fields")
    keys = role["keys"]
    threshold = role["threshold"]
    if not isinstance(keys, list) or not keys:
        raise RootRotationError("new_root_role requires public keys")
    if isinstance(threshold, bool) or not isinstance(threshold, int):
        raise RootRotationError("new_root_role threshold must be an integer")
    if threshold < 1 or threshold > len(keys):
        raise RootRotationError("new_root_role threshold is invalid")
    public_keys: dict[str, Ed25519PublicKey] = {}
    previous_keyid = ""
    for index, item in enumerate(keys):
        if not isinstance(item, Mapping) or set(item) != _ROOT_KEY_FIELDS:
            raise RootRotationError(f"new_root_role.keys[{index}] has invalid fields")
        keyid = _sha256(item["keyid"], f"new_root_role.keys[{index}].keyid")
        if previous_keyid and keyid <= previous_keyid:
            raise RootRotationError("new_root_role public keys must be sorted by keyid")
        raw = _b64decode(item["public_key"], f"new_root_role.keys[{index}].public_key")
        if len(raw) != 32:
            raise RootRotationError("Ed25519 root public keys must contain 32 bytes")
        if hashlib.sha256(raw).hexdigest() != keyid:
            raise RootRotationError("new root keyid is not its public-key fingerprint")
        try:
            public_key = Ed25519PublicKey.from_public_bytes(raw)
        except ValueError as exc:
            raise RootRotationError("invalid Ed25519 public key") from exc
        if keyid in public_keys:
            raise RootRotationError("new root role contains duplicate key IDs")
        public_keys[keyid] = public_key
        previous_keyid = keyid
    supplied = _sha256(transition["transition_digest"], "transition_digest")
    core = {key: value for key, value in transition.items() if key != "transition_digest"}
    if digest(core) != supplied:
        raise RootRotationError("root transition digest mismatch")
    return public_keys


def build_root_transition(
    next_manifest: Mapping[str, Any],
    new_root_public_keys: Mapping[str, Ed25519PublicKey],
    *,
    previous_generation: int,
    previous_manifest_digest: str,
    new_root_threshold: int = 1,
) -> dict[str, Any]:
    """Build the exact successor transition and delegate to its new root set."""
    try:
        _validate_manifest_document(next_manifest)
    except (TrustManifestError, KeyError, TypeError) as exc:
        raise RootRotationError("successor trust manifest is invalid") from exc
    if (
        isinstance(previous_generation, bool)
        or not isinstance(previous_generation, int)
        or previous_generation < 1
    ):
        raise RootRotationError("previous_generation must be a positive integer")
    previous_digest = _sha256(previous_manifest_digest, "previous_manifest_digest")
    if next_manifest["generation"] != previous_generation + 1:
        raise RootRotationError("successor manifest is not the exact next generation")
    if next_manifest["previous_manifest_digest"] != previous_digest:
        raise RootRotationError("successor manifest does not extend the supplied predecessor")
    role = _root_role_document(new_root_public_keys, new_root_threshold)
    core = {
        "format": FORMAT,
        "schema": SCHEMA,
        "registry_id": next_manifest["registry_id"],
        "previous_generation": previous_generation,
        "previous_manifest_digest": previous_digest,
        "next_generation": next_manifest["generation"],
        "next_manifest_digest": next_manifest["manifest_digest"],
        "new_root_role": role,
    }
    return {**core, "transition_digest": digest(core)}


def sign_root_transition(
    transition: Mapping[str, Any],
    old_root_private_keys: Sequence[Ed25519PrivateKey],
    new_root_private_keys: Sequence[Ed25519PrivateKey],
) -> dict[str, Any]:
    """Sign the transition with both old and proposed new root-key sets."""
    _validate_transition_document(transition)
    if not isinstance(old_root_private_keys, (list, tuple)) or not old_root_private_keys:
        raise RootRotationError("old root signatures are required")
    if not isinstance(new_root_private_keys, (list, tuple)) or not new_root_private_keys:
        raise RootRotationError("new root signatures are required")
    payload = _json_bytes(transition)
    pae_bytes = pae(PAYLOAD_TYPE, payload)
    signatures_by_keyid: dict[str, str] = {}
    for group_name, private_keys in (
        ("old root", old_root_private_keys),
        ("new root", new_root_private_keys),
    ):
        for index, private_key in enumerate(private_keys):
            try:
                keyid = _private_key_id(private_key)
            except (TypeError, ValueError) as exc:
                raise RootRotationError(f"{group_name} signing key {index} is invalid") from exc
            if keyid in signatures_by_keyid:
                continue
            signatures_by_keyid[keyid] = _b64encode(private_key.sign(pae_bytes))
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": _b64encode(payload),
        "signatures": [
            {"keyid": keyid, "sig": signature}
            for keyid, signature in sorted(signatures_by_keyid.items())
        ],
    }


def verify_root_transition(
    envelope: Mapping[str, Any],
    old_trusted_root_public_keys: Mapping[str, Ed25519PublicKey],
    *,
    expected_registry_id: str,
    expected_previous_generation: int,
    expected_previous_manifest_digest: str,
    old_root_threshold: int = 1,
) -> dict[str, Any]:
    """Verify old-root and new-root thresholds plus the exact predecessor."""
    old_roots = _root_key_map(old_trusted_root_public_keys, label="trusted old root")
    if isinstance(old_root_threshold, bool) or not isinstance(old_root_threshold, int):
        raise RootRotationError("old_root_threshold must be an integer")
    if old_root_threshold < 1 or old_root_threshold > len(old_roots):
        raise RootRotationError("old_root_threshold is outside the trusted old root set")
    if isinstance(envelope, Mapping) is False or set(envelope) != _ENVELOPE_FIELDS:
        raise RootRotationError("root transition DSSE envelope has invalid fields")
    if envelope["payloadType"] != PAYLOAD_TYPE:
        raise RootRotationError("DSSE payload type is not the root transition type")
    raw_payload = _b64decode(envelope["payload"], "root transition payload")
    transition = _strict_json(raw_payload)
    new_roots = _validate_transition_document(transition)
    if transition["registry_id"] != _nonempty(expected_registry_id, "expected_registry_id"):
        raise RootRotationError("root transition belongs to a different registry")
    if transition["previous_generation"] != expected_previous_generation:
        raise RootRotationError("root transition does not extend the accepted generation")
    if transition["previous_manifest_digest"] != _sha256(
        expected_previous_manifest_digest, "expected_previous_manifest_digest"
    ):
        raise RootRotationError("root transition does not extend the accepted manifest digest")

    signatures = envelope["signatures"]
    if not isinstance(signatures, list) or not signatures:
        raise RootRotationError("root transition must contain signatures")
    seen = set()
    old_signers = set()
    new_signers = set()
    pae_bytes = pae(PAYLOAD_TYPE, raw_payload)
    for index, item in enumerate(signatures):
        if not isinstance(item, Mapping) or set(item) != _SIGNATURE_FIELDS:
            raise RootRotationError(f"root transition signature {index} has invalid fields")
        keyid = _sha256(item["keyid"], f"signatures[{index}].keyid")
        if keyid in seen:
            raise RootRotationError("duplicate root transition signature key IDs")
        seen.add(keyid)
        old_key = old_roots.get(keyid)
        new_key = new_roots.get(keyid)
        public_key = old_key or new_key
        if public_key is None:
            raise RootRotationError("root transition contains a signature from an undeclared key")
        signature = _b64decode(item["sig"], f"signatures[{index}].sig")
        if len(signature) != 64:
            raise RootRotationError("Ed25519 root signatures must contain 64 bytes")
        try:
            public_key.verify(signature, pae_bytes)
        except InvalidSignature as exc:
            raise RootRotationError(f"invalid root transition signature for {keyid}") from exc
        if old_key is not None:
            old_signers.add(keyid)
        if new_key is not None:
            new_signers.add(keyid)

    new_threshold = transition["new_root_role"]["threshold"]
    if len(old_signers) < old_root_threshold:
        raise RootRotationError("root transition does not meet the previous root threshold")
    if len(new_signers) < new_threshold:
        raise RootRotationError("root transition does not meet the successor root threshold")
    return {
        "transition": transition,
        "transition_digest": transition["transition_digest"],
        "registry_id": transition["registry_id"],
        "previous_generation": transition["previous_generation"],
        "previous_manifest_digest": transition["previous_manifest_digest"],
        "next_generation": transition["next_generation"],
        "next_manifest_digest": transition["next_manifest_digest"],
        "old_root_keyids": sorted(old_signers),
        "new_root_keyids": sorted(new_signers),
        "old_root_threshold": old_root_threshold,
        "new_root_threshold": new_threshold,
        "new_root_public_keys": new_roots,
    }


def verify_rotated_trust_manifest(
    transition_envelope: Mapping[str, Any],
    successor_manifest_envelope: Mapping[str, Any],
    old_trusted_root_public_keys: Mapping[str, Ed25519PublicKey],
    *,
    verification_time: str,
    expected_registry_id: str,
    expected_previous_generation: int,
    expected_previous_manifest_digest: str,
    old_root_threshold: int = 1,
) -> dict[str, Any]:
    """Verify dual-authorized root migration and the successor trust manifest."""
    transition = verify_root_transition(
        transition_envelope,
        old_trusted_root_public_keys,
        expected_registry_id=expected_registry_id,
        expected_previous_generation=expected_previous_generation,
        expected_previous_manifest_digest=expected_previous_manifest_digest,
        old_root_threshold=old_root_threshold,
    )
    successor = verify_trust_manifest(
        successor_manifest_envelope,
        transition["new_root_public_keys"],
        verification_time=verification_time,
        root_threshold=transition["new_root_threshold"],
        expected_registry_id=expected_registry_id,
        minimum_generation=transition["next_generation"],
        expected_generation=transition["next_generation"],
        expected_previous_manifest_digest=expected_previous_manifest_digest,
    )
    if successor["manifest_digest"] != transition["next_manifest_digest"]:
        raise RootRotationError("successor manifest digest differs from dual-signed root transition")
    return {
        "registry_id": expected_registry_id,
        "previous_generation": transition["previous_generation"],
        "previous_manifest_digest": transition["previous_manifest_digest"],
        "generation": successor["generation"],
        "manifest_digest": successor["manifest_digest"],
        "transition_digest": transition["transition_digest"],
        "old_root_keyids": transition["old_root_keyids"],
        "new_root_keyids": transition["new_root_keyids"],
        "root_threshold": transition["new_root_threshold"],
        "trust_store_digest": successor["trust_store_digest"],
        "trust_store": successor["trust_store"],
        "valid_at": successor["valid_at"],
    }
