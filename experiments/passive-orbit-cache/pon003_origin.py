"""PON-003: independently signed, immutable origin publication contracts.

The two publishers prepare *separate physical bundles* from known canonical
PON-001 source bytes. Neither issuer key nor published receipt grants CPU
execution authority. Ed25519 public keys require receiver-side pins backed by
independent provenance for real deployments; self-issued keys alone are not
proof of separate organizations or physical machines.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from passive_orbit import (
    HERE, ROOT_PIN, HASH, canonical, checked_manifest, checked_packet,
    digest, PassiveRejected, require
)

SCHEMA = "in-formation.pon003.origin-publication/0.1"
ROOT_NAME = "manifest.json"
MODES = {"r2", "ipfs"}
NAMES = {"r2": "bucket-origin", "ipfs": "block-origin"}
CID_PATTERN = re.compile(r"bafkrei[a-z2-7]{52}\Z")
MAX_AGE_S = 3600
MAX_OBJECTS = 16


def raw_cid(address: str) -> str:
    """CIDv1, raw codec 0x55, sha2-256 0x12, 32-byte digest, base32 lower."""
    require(type(address) is str and HASH.fullmatch(address) is not None,
            "raw CID requires a canonical sha256")
    raw = b"\x01\x55\x12\x20" + bytes.fromhex(address)
    return "b" + base64.b32encode(raw).decode("ascii").lower().rstrip("=")


def check_raw_cid(cid: str, address: str) -> None:
    require(type(cid) is str and CID_PATTERN.fullmatch(cid) is not None
            and cid == raw_cid(address), "unexpected raw CID vs pinned sha256")


def publisher_source() -> dict[str, bytes]:
    """Finite, known benign fixture. Never fetch unauthenticated programs."""
    public = HERE / "public"
    root = (public / ROOT_NAME).read_bytes()
    manifest = checked_manifest(root, ROOT_PIN)
    require(len(manifest["objects"]) <= MAX_OBJECTS, "unbounded source")
    objects = {ROOT_NAME: root}
    for ref in manifest["objects"]:
        path = "objects/" + ref["object_sha256"] + ".json"
        raw = (public / path).read_bytes()
        checked_packet(raw, identity=ref["semantic_id"],
                       address=ref["object_sha256"])
        objects[path] = raw
    return objects


def inventory(objects: dict[str, bytes]) -> list[dict]:
    """Each object binds a semantic ID, raw SHA-256 and IPFS raw block CID."""
    manifest = checked_manifest(objects[ROOT_NAME], ROOT_PIN)
    entries = [{"semantic_id": "root", "path": ROOT_NAME,
                "sha256": ROOT_PIN, "raw_cid": raw_cid(ROOT_PIN)}]
    for item in manifest["objects"]:
        sid, addr = item["semantic_id"], item["object_sha256"]
        path = "objects/" + addr + ".json"
        require(path in objects and digest(objects[path]) == addr,
                "publication inventory missing exact byte object")
        entries.append({"semantic_id": sid, "path": path,
                        "sha256": addr, "raw_cid": raw_cid(addr)})
    return entries


def pubkey(private: Ed25519PrivateKey) -> bytes:
    return private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def sign_publication(*, signer: Ed25519PrivateKey, kind: str, objects: dict,
                     epoch: int, now: int) -> dict:
    require(kind in MODES and type(epoch) is int and epoch >= 1 and
            type(now) is int and now > 0, "invalid publication authority parameters")
    core = {
        "schema": SCHEMA, "origin_id": NAMES[kind], "kind": kind,
        "root_sha256": ROOT_PIN,
        "public_key_sha256": digest(pubkey(signer)),
        "epoch": epoch, "issued_at": now,
        "valid_until": now + MAX_AGE_S,
        "scope": "immutable/read-only/pure-cag001",
        "object_inventory": inventory(objects),
    }
    return {**core, "signature_hex": signer.sign(canonical(core)).hex()}


def verify_publication(*, receipt: object, trusted_public_key: bytes,
                       expected_kind: str, root_pin: str, floor: int,
                       now: int) -> dict:
    """Never read a provider-chosen key, URL, root, or policy as authority."""
    require(type(receipt) is dict and set(receipt) == {
        "schema", "origin_id", "kind", "root_sha256", "public_key_sha256",
        "epoch", "issued_at", "valid_until", "scope",
        "object_inventory", "signature_hex",
    }, "publication receipt contract mismatch")
    require(expected_kind in MODES and type(trusted_public_key) is bytes and
            len(trusted_public_key) == 32 and
            type(root_pin) is str and HASH.fullmatch(root_pin) is not None and
            type(floor) is int and floor >= 1 and
            type(now) is int and now > 0,
            "receiver public key, root, policy epoch and trusted time required")
    require(receipt["schema"] == SCHEMA and
            receipt["origin_id"] == NAMES[expected_kind] and
            receipt["kind"] == expected_kind and
            receipt["root_sha256"] == root_pin and
            receipt["public_key_sha256"] == digest(trusted_public_key) and
            receipt["scope"] == "immutable/read-only/pure-cag001",
            "receiver-pinned origin policy conflict")
    require(type(receipt["epoch"]) is int and receipt["epoch"] >= floor and
            type(receipt["issued_at"]) is int and
            type(receipt["valid_until"]) is int and
            receipt["issued_at"] <= now <= receipt["valid_until"] and
            0 < receipt["valid_until"] - receipt["issued_at"] <= MAX_AGE_S,
            "publication expired, future-dated, or below receiver epoch floor")
    signed = receipt["signature_hex"]
    require(type(signed) is str and
            re.fullmatch(r"[0-9a-f]{128}", signed) is not None,
            "noncanonical Ed25519 signature")
    payload = {k: v for k, v in receipt.items() if k != "signature_hex"}
    try:
        Ed25519PublicKey.from_public_bytes(trusted_public_key).verify(
            bytes.fromhex(signed), canonical(payload))
    except (InvalidSignature, ValueError) as exc:
        raise PassiveRejected("publication signature verification failed") from exc
    entries = receipt["object_inventory"]
    require(type(entries) is list and 1 <= len(entries) <= MAX_OBJECTS + 1,
            "bounded inventory required")
    labels = set()
    paths = set()
    for e in entries:
        require(type(e) is dict and set(e) == {
            "semantic_id", "path", "sha256", "raw_cid"
        }, "unknown inventory fields")
        sid, path, addr = e["semantic_id"], e["path"], e["sha256"]
        require(type(sid) is str and
                re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", sid) is not None
                and sid not in labels and
                type(path) is str and
                (path == ROOT_NAME if sid == "root"
                 else path == "objects/" + addr + ".json")
                and path not in paths and
                type(addr) is str and HASH.fullmatch(addr) is not None,
                "invalid inventory identity, path or duplicate")
        labels.add(sid)
        paths.add(path)
        check_raw_cid(e["raw_cid"], addr)
    require("root" in labels and entries[0]["semantic_id"] == "root" and
            entries[0]["sha256"] == root_pin and
            len(labels) >= 2, "signed inventory is not rooted")
    return {e["semantic_id"]: e for e in entries}


def produce(*, kind: str, output: Path, epoch: int, now: int) -> dict:
    require(kind in MODES, "unknown origin mode")
    source = publisher_source()
    signer = Ed25519PrivateKey.generate()
    receipt = sign_publication(signer=signer, kind=kind,
                               objects=source, epoch=epoch, now=now)
    output.mkdir(parents=True, exist_ok=True)
    (output / "receipt.json").write_bytes(canonical(receipt))
    (output / "public-key.hex").write_text(pubkey(signer).hex() + "\n",
                                            encoding="ascii")
    for path, content in source.items():
        target = (output / path) if kind == "r2" else (
            output / "blocks" / raw_cid(digest(content)))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=sorted(MODES))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epoch", type=int, default=1)
    args = parser.parse_args()
    receipt = produce(kind=args.kind, output=args.output,
                      epoch=args.epoch, now=int(time.time()))
    print(json.dumps({
        "origin_id": receipt["origin_id"],
        "kind": receipt["kind"],
        "root_sha256": receipt["root_sha256"],
        "published_objects": len(receipt["object_inventory"]),
        "signed_publication_sha256": digest(canonical(receipt)),
        "ephemeral_private_key_exported": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
