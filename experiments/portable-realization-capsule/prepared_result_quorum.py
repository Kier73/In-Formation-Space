"""Strict-majority aggregation for independently signed PSC validator receipts.

This module keeps validator attestations separate from E-CPU claim authority.
It admits a configured set of distinct validator identities, gathers signed
verification results, and only emits a content-bound quorum receipt when a
strict majority agrees on the exact same verification digest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from prepared_result_validation import (
    PreparedResultValidationError,
    PreparedResultValidatorEndpoint,
    _canonical,
    _digest,
    _load_ed25519_public_key,
    _public_key_fingerprint,
    validate_prepared_result_remotely,
    verify_stored_remote_validator_receipt,
)

QUORUM_CONFIG_SCHEMA = "ifs.psc.remote-validator-quorum-config.v1"
TRUST_SET_SCHEMA = "ifs.psc.remote-validator-trust-set.v1"
QUORUM_RECEIPT_SCHEMA = "ifs.psc.remote-validator-quorum-receipt.v1"
_MAX_CONFIG_BYTES = 1024 * 1024


def _exact_fields(value: Any, expected: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise PreparedResultValidationError(f"{field} fields do not match the exact schema")
    return value


@dataclass(frozen=True)
class PreparedResultValidatorQuorum:
    """A pinned set of independent validator peers with strict-majority admission."""

    quorum_id: str
    threshold: int
    endpoints: tuple[PreparedResultValidatorEndpoint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.quorum_id, str) or not self.quorum_id or self.quorum_id.strip() != self.quorum_id:
            raise PreparedResultValidationError("validator quorum ID must be non-empty trimmed text")
        if not isinstance(self.endpoints, tuple) or len(self.endpoints) < 3:
            raise PreparedResultValidationError("validator quorum requires at least three independent endpoints")
        if type(self.threshold) is not int or not (len(self.endpoints) // 2 < self.threshold <= len(self.endpoints)):
            raise PreparedResultValidationError("validator quorum threshold must be a strict majority of its endpoint set")

        peer_ids = [endpoint.validator_peer_id for endpoint in self.endpoints]
        certificate_pins = [endpoint.server_certificate_sha256 for endpoint in self.endpoints]
        key_ids = [
            _public_key_fingerprint(_load_ed25519_public_key(endpoint.attestation_public_key_path))
            for endpoint in self.endpoints
        ]
        if len(set(peer_ids)) != len(peer_ids):
            raise PreparedResultValidationError("validator quorum peer IDs must be unique")
        if len(set(certificate_pins)) != len(certificate_pins):
            raise PreparedResultValidationError("validator quorum TLS certificate pins must be unique")
        if len(set(key_ids)) != len(key_ids):
            raise PreparedResultValidationError("validator quorum Ed25519 signing keys must be unique")

        workers = {
            (
                endpoint.worker_peer_id,
                endpoint.worker_host_id,
                endpoint.worker_implementation_fingerprint,
            )
            for endpoint in self.endpoints
        }
        if len(workers) != 1:
            raise PreparedResultValidationError("all validators in one quorum must pin the same worker identity tuple")

    @property
    def expected_validator_peer_ids(self) -> tuple[str, ...]:
        return tuple(sorted(endpoint.validator_peer_id for endpoint in self.endpoints))

    def offline_trust_set(self) -> dict[str, Any]:
        validators: dict[str, Any] = {}
        for endpoint in sorted(self.endpoints, key=lambda selected: selected.validator_peer_id):
            validators[endpoint.validator_peer_id] = {
                "attestation_key_id": _public_key_fingerprint(
                    _load_ed25519_public_key(endpoint.attestation_public_key_path)
                ),
                "certificate_sha256": endpoint.server_certificate_sha256,
                "dns_identity": endpoint.server_dns_identity,
            }
        return {
            "schema": TRUST_SET_SCHEMA,
            "quorum_id": self.quorum_id,
            "threshold": self.threshold,
            "validators": validators,
        }


def load_prepared_result_validator_quorum(
    path: Path,
    *,
    worker_peer_id: str,
    worker_host_id: str,
    worker_implementation_fingerprint: str,
) -> PreparedResultValidatorQuorum:
    """Load a finite, exact validator trust configuration for one recovery worker."""
    if not isinstance(path, Path) or not path.is_file():
        raise PreparedResultValidationError("validator quorum config path must identify an existing file")
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_CONFIG_BYTES:
        raise PreparedResultValidationError("validator quorum config is empty or exceeds its finite byte bound")
    try:
        selected = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreparedResultValidationError("validator quorum config is not valid UTF-8 JSON") from exc
    config = _exact_fields(
        selected,
        {"schema", "quorum_id", "threshold", "worker", "validators"},
        "validator quorum config",
    )
    if config["schema"] != QUORUM_CONFIG_SCHEMA:
        raise PreparedResultValidationError("unsupported validator quorum config schema")
    worker = _exact_fields(
        config["worker"],
        {"peer_id", "host_id", "implementation_fingerprint"},
        "validator quorum worker identity",
    )
    if (
        worker["peer_id"] != worker_peer_id
        or worker["host_id"] != worker_host_id
        or worker["implementation_fingerprint"] != worker_implementation_fingerprint
    ):
        raise PreparedResultValidationError("validator quorum config is bound to a different worker identity")
    validators = config["validators"]
    if not isinstance(validators, list) or len(validators) < 3 or len(validators) > 31:
        raise PreparedResultValidationError("validator quorum config must contain between 3 and 31 endpoints")

    expected_endpoint_fields = {
        "validator_peer_id",
        "host",
        "port",
        "server_dns_identity",
        "server_certificate_sha256",
        "worker_certificate_path",
        "worker_private_key_path",
        "trusted_server_ca_path",
        "attestation_public_key_path",
    }
    endpoints: list[PreparedResultValidatorEndpoint] = []
    for index, item in enumerate(validators):
        selected_endpoint = _exact_fields(item, expected_endpoint_fields, f"validator endpoint {index}")
        endpoints.append(
            PreparedResultValidatorEndpoint(
                validator_peer_id=selected_endpoint["validator_peer_id"],
                host=selected_endpoint["host"],
                port=selected_endpoint["port"],
                server_dns_identity=selected_endpoint["server_dns_identity"],
                server_certificate_sha256=selected_endpoint["server_certificate_sha256"],
                worker_peer_id=worker_peer_id,
                worker_host_id=worker_host_id,
                worker_implementation_fingerprint=worker_implementation_fingerprint,
                worker_certificate_path=Path(selected_endpoint["worker_certificate_path"]),
                worker_private_key_path=Path(selected_endpoint["worker_private_key_path"]),
                trusted_server_ca_path=Path(selected_endpoint["trusted_server_ca_path"]),
                attestation_public_key_path=Path(selected_endpoint["attestation_public_key_path"]),
            )
        )
    return PreparedResultValidatorQuorum(
        quorum_id=config["quorum_id"],
        threshold=config["threshold"],
        endpoints=tuple(endpoints),
    )


def validator_quorum_config_dict(
    quorum_id: str,
    threshold: int,
    *,
    worker_peer_id: str,
    worker_host_id: str,
    worker_implementation_fingerprint: str,
    endpoints: tuple[PreparedResultValidatorEndpoint, ...],
) -> dict[str, Any]:
    """Serialize a quorum config without private signing keys."""
    quorum = PreparedResultValidatorQuorum(quorum_id, threshold, endpoints)
    worker = {
        "peer_id": worker_peer_id,
        "host_id": worker_host_id,
        "implementation_fingerprint": worker_implementation_fingerprint,
    }
    serialized_endpoints = [
        {
            "validator_peer_id": endpoint.validator_peer_id,
            "host": endpoint.host,
            "port": endpoint.port,
            "server_dns_identity": endpoint.server_dns_identity,
            "server_certificate_sha256": endpoint.server_certificate_sha256,
            "worker_certificate_path": str(endpoint.worker_certificate_path),
            "worker_private_key_path": str(endpoint.worker_private_key_path),
            "trusted_server_ca_path": str(endpoint.trusted_server_ca_path),
            "attestation_public_key_path": str(endpoint.attestation_public_key_path),
        }
        for endpoint in sorted(endpoints, key=lambda selected: selected.validator_peer_id)
    ]
    return {
        "schema": QUORUM_CONFIG_SCHEMA,
        "quorum_id": quorum.quorum_id,
        "threshold": quorum.threshold,
        "worker": worker,
        "validators": serialized_endpoints,
    }


def validate_prepared_result_with_quorum(
    quorum: PreparedResultValidatorQuorum,
    *,
    envelope: Mapping[str, Any],
    prepared_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Collect signed validator results and admit only a strict-majority exact-digest agreement."""
    if not isinstance(quorum, PreparedResultValidatorQuorum):
        raise PreparedResultValidationError("remote validation requires a typed validator quorum")
    responses: list[dict[str, Any]] = []
    failures: dict[str, str] = {}
    for endpoint in sorted(quorum.endpoints, key=lambda selected: selected.validator_peer_id):
        try:
            response = validate_prepared_result_remotely(
                endpoint,
                envelope=envelope,
                prepared_record=prepared_record,
            )
        except Exception as exc:
            failures[endpoint.validator_peer_id] = f"{type(exc).__name__}: {exc}"
            continue
        responses.append(
            {
                "validator_peer_id": endpoint.validator_peer_id,
                "response": response,
            }
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    for selected in responses:
        response = selected["response"]
        groups.setdefault(response["verification_digest"], []).append(selected)
    winning = [
        (digest, members)
        for digest, members in groups.items()
        if len(members) >= quorum.threshold
    ]
    if len(winning) != 1:
        detail = {
            "responded": len(responses),
            "required": quorum.threshold,
            "failed_validator_peer_ids": sorted(failures),
            "agreement_counts": {digest: len(members) for digest, members in groups.items()},
        }
        raise PreparedResultValidationError(
            f"no unique strict-majority validator agreement for prepared PSC result: {detail}"
        )

    verification_digest, selected_members = winning[0]
    verification = selected_members[0]["response"]["verification"]
    for member in selected_members:
        if member["response"]["verification"] != verification:
            raise PreparedResultValidationError("validator responses collide on digest but disagree on report content")
    validator_receipts = [
        member["response"]["remote_validator_receipt"]
        for member in selected_members
    ]
    validator_receipts.sort(key=lambda receipt: receipt["validator_peer_id"])
    trust_set = quorum.offline_trust_set()
    core = {
        "schema": QUORUM_RECEIPT_SCHEMA,
        "quorum_id": quorum.quorum_id,
        "threshold": quorum.threshold,
        "expected_validator_peer_ids": list(quorum.expected_validator_peer_ids),
        "validator_trust": trust_set["validators"],
        "verification_digest": verification_digest,
        "verification": verification,
        "validator_receipts": validator_receipts,
    }
    quorum_digest = _digest(core)
    receipt = {**core, "quorum_receipt_digest": quorum_digest}
    return {
        "valid": True,
        "verification": verification,
        "verification_digest": verification_digest,
        "remote_validator_receipt": receipt,
        "remote_validator_receipt_digest": quorum_digest,
        "validator_failures": failures,
    }


def verify_stored_remote_validator_quorum_receipt(
    quorum: PreparedResultValidatorQuorum,
    receipt: Mapping[str, Any],
) -> str:
    """Reverify every stored signer and the threshold against the worker's current trust configuration."""
    expected_fields = {
        "schema",
        "quorum_id",
        "threshold",
        "expected_validator_peer_ids",
        "validator_trust",
        "verification_digest",
        "verification",
        "validator_receipts",
        "quorum_receipt_digest",
    }
    selected = _exact_fields(receipt, expected_fields, "stored validator quorum receipt")
    core = {key: value for key, value in selected.items() if key != "quorum_receipt_digest"}
    quorum_digest = selected["quorum_receipt_digest"]
    if not isinstance(quorum_digest, str) or _digest(core) != quorum_digest:
        raise PreparedResultValidationError("stored validator quorum receipt digest mismatch")

    trust_set = quorum.offline_trust_set()
    if (
        selected["schema"] != QUORUM_RECEIPT_SCHEMA
        or selected["quorum_id"] != quorum.quorum_id
        or selected["threshold"] != quorum.threshold
        or selected["expected_validator_peer_ids"] != list(quorum.expected_validator_peer_ids)
        or selected["validator_trust"] != trust_set["validators"]
    ):
        raise PreparedResultValidationError("stored validator quorum receipt differs from the current pinned trust set")
    verification = selected["verification"]
    verification_digest = selected["verification_digest"]
    if (
        not isinstance(verification, Mapping)
        or not isinstance(verification_digest, str)
        or _digest({
            key: value for key, value in verification.items()
            if key != "verification_digest"
        }) != verification_digest
        or verification.get("verification_digest") != verification_digest
    ):
        raise PreparedResultValidationError("stored validator quorum verification digest is invalid")

    receipts = selected["validator_receipts"]
    if not isinstance(receipts, list) or len(receipts) < quorum.threshold:
        raise PreparedResultValidationError("stored validator quorum receipt has fewer signatures than required")
    endpoint_by_peer = {endpoint.validator_peer_id: endpoint for endpoint in quorum.endpoints}
    peer_ids = [item.get("validator_peer_id") if isinstance(item, Mapping) else None for item in receipts]
    if (
        peer_ids != sorted(peer_ids)
        or len(peer_ids) != len(set(peer_ids))
        or any(peer_id not in endpoint_by_peer for peer_id in peer_ids)
    ):
        raise PreparedResultValidationError("stored validator quorum receipt signer set is not unique and canonical")
    for item in receipts:
        peer_id = item["validator_peer_id"]
        verify_stored_remote_validator_receipt(endpoint_by_peer[peer_id], item)
        if (
            item.get("validation_digest") != verification_digest
            or item.get("validation") != verification
        ):
            raise PreparedResultValidationError("stored validator signature does not endorse the quorum verification result")
    return quorum_digest
