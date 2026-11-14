#!/usr/bin/env python3
"""CAG-003: issue and independently check signed, transport-agnostic Ground intents.

The trust record is provisioned separately from the signed payload. In the
hosted fixture, GitHub attests that trust record and both artifacts originate
from an approved *workflow*, not an independently authorized publisher. The
ephemeral private key never appears in persisted evidence.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cag002"))
import convergent_fabric as cag
import substrates as c2

SIGNED_SCHEMA = "in-formation.cag003-ed25519-intent/0.1"
TRUST_SCHEMA = "in-formation.cag003-receiver-trust/0.1"
MANIFEST_SCHEMA = "in-formation.cag003-publisher-commitment/0.1"
PUBLISHER = "github-actions-ephemeral-cag003-publisher"
CONTRACT = "cag003.receiver-ground-reconstruction@1"
WORKFLOW = "Kier73/In-Formation-Space/.github/workflows/cag003-signed-admission.yml@refs/heads/main"
INPUT_FILES = (
    "source.json", "blue-route.json", "amber-route.json",
    "jetstream-arrivals.jsonl", "libp2p-spool.jsonl",
    "transport-trace.json", "report.json",
)
SHA = re.compile(r"^[0-9a-f]{64}$")


class SignedGroundError(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise SignedGroundError(reason)


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode(data: str, expected: int) -> bytes:
    require(isinstance(data, str) and len(data) <= 256, "invalid base64 encoding")
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise SignedGroundError("invalid base64 data") from exc
    require(len(raw) == expected and encode(raw) == data, "invalid canonical base64 length")
    return raw


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: Mapping[str, Any]) -> bytes:
    return cag.canonical(obj)


def load(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    require(type(doc) is dict, "JSON document is not an object")
    return doc


def write(path: Path, doc: Mapping[str, Any]) -> None:
    cag.write(path, doc)


def trusted_key_id(public: bytes) -> str:
    return sha(public)


def valid_source(directory: Path) -> dict[str, Any]:
    # Independently interpret actual captured CAG-002 network histories first.
    report = c2.offline_verify(directory)
    require(report["status"] == "two_real_substrates_local_reconstruction",
            "captured Ground is not locally reconstructable")
    require(report["reference"]["value"] == 44, "fixture result is not 44")
    return report


def create_intent(directory: Path, *, private: Ed25519PrivateKey | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    report = valid_source(directory)
    key = private or Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trust = {
        "schema": TRUST_SCHEMA,
        "publisher": PUBLISHER,
        "trust_epoch": 1,
        "key_id": trusted_key_id(pub),
        "public_key_b64": encode(pub),
        "workload_contract": CONTRACT,
        "source_digest": report["source_digest"],
        "trusted_workflow_ref": WORKFLOW,
        "limit": "workflow-attested ephemeral publisher key, NOT an external independent identity",
    }
    file_hashes = {
        filename: sha((directory / filename).read_bytes())
        for filename in INPUT_FILES
    }
    statement = {
        "schema": MANIFEST_SCHEMA,
        "publisher": PUBLISHER,
        "trust_epoch": 1,
        "key_id": trust["key_id"],
        "source_digest": report["source_digest"],
        "route_digests": report["route_digests"],
        "report_digest": report["report_digest"],
        "workload_contract": CONTRACT,
        "target": "final",
        "input_sha256": file_hashes,
    }
    signature = key.sign(canonical(statement))
    envelope = {
        "schema": SIGNED_SCHEMA,
        "statement": statement,
        "algorithm": "Ed25519",
        "signature_b64": encode(signature),
    }
    return envelope, trust


def verify_intent(directory: Path, envelope: Mapping[str, Any],
                  trust: Mapping[str, Any]) -> dict[str, Any]:
    require(type(trust) is dict and set(trust) == {
        "schema", "publisher", "trust_epoch", "key_id", "public_key_b64",
        "workload_contract", "source_digest", "trusted_workflow_ref", "limit",
    }, "unexpected trust record")
    require(trust["schema"] == TRUST_SCHEMA and trust["publisher"] == PUBLISHER
            and type(trust["trust_epoch"]) is int and trust["trust_epoch"] == 1
            and trust["workload_contract"] == CONTRACT
            and trust["trusted_workflow_ref"] == WORKFLOW,
            "unadmitted publisher trust scope")
    pub = decode(trust["public_key_b64"], 32)
    require(trust["key_id"] == trusted_key_id(pub), "trust record public-key fingerprint mismatch")
    require(type(envelope) is dict and set(envelope) == {
        "schema", "statement", "algorithm", "signature_b64",
    } and envelope["schema"] == SIGNED_SCHEMA
            and envelope["algorithm"] == "Ed25519", "signed envelope fields invalid")
    statement = envelope["statement"]
    require(type(statement) is dict and set(statement) == {
        "schema", "publisher", "trust_epoch", "key_id", "source_digest",
        "route_digests", "report_digest", "workload_contract", "target", "input_sha256",
    }, "unexpected signed statement")
    require(statement["schema"] == MANIFEST_SCHEMA
            and statement["publisher"] == trust["publisher"]
            and statement["trust_epoch"] == trust["trust_epoch"]
            and statement["key_id"] == trust["key_id"]
            and statement["workload_contract"] == CONTRACT
            and statement["target"] == "final", "signed publisher scope mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(
            decode(envelope["signature_b64"], 64),
            canonical(statement),
        )
    except (ValueError, InvalidSignature) as exc:
        raise SignedGroundError("Ed25519 statement signature invalid") from exc
    received_files = statement["input_sha256"]
    require(type(received_files) is dict and set(received_files) == set(INPUT_FILES),
            "signed statement does not bind every input")
    for filename in INPUT_FILES:
        expected_hash = received_files[filename]
        require(type(expected_hash) is str and SHA.fullmatch(expected_hash) is not None,
                "invalid captured file hash")
        require(sha((directory / filename).read_bytes()) == expected_hash,
                f"transport capture differs from signed publisher commitment: {filename}")
    report = valid_source(directory)
    require(statement["source_digest"] == trust["source_digest"] == report["source_digest"]
            and statement["route_digests"] == report["route_digests"]
            and statement["report_digest"] == report["report_digest"],
            "signed source or result is different from reconstructed transport evidence")
    return {
        "status": "signed_publisher_commitment_verified",
        "publisher": PUBLISHER,
        "key_id": trust["key_id"],
        "source_digest": report["source_digest"],
        "report_digest": report["report_digest"],
        "input_sha256": received_files,
        "cryptographic_integrity": "Ed25519 signature checked against separately supplied trust record",
        "authority_limit": "bootstrap trust record requires independently checked GitHub workflow attestation",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("issue", "verify"))
    p.add_argument("--directory", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "issue":
            signed, trust = create_intent(args.directory)
            write(args.directory / "signed-intent.json", signed)
            write(args.directory / "publisher-trust.json", trust)
            print("CAG-003 signed source and captured transport digests; ephemeral key discarded")
        else:
            record = verify_intent(
                args.directory,
                load(args.directory / "signed-intent.json"),
                load(args.directory / "publisher-trust.json"),
            )
            print(json.dumps(record, sort_keys=True))
    except (SignedGroundError, cag.ConvergenceError, c2.SubstrateError, OSError,
            ValueError, KeyError, TypeError) as exc:
        p.exit(1, f"CAG-003 fail-closed identity verification: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
