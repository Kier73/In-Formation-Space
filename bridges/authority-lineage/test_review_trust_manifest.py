import base64
import copy
import hashlib
import json
import unittest
from pathlib import Path

import jsonschema
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from authority_lineage import digest
from review_trust_manifest import (
    PAYLOAD_TYPE,
    TrustManifestError,
    build_trust_manifest,
    sign_trust_manifest,
    verify_ledger_signed_review_bundle_with_manifest,
    verify_review_bundle_with_manifest,
    verify_trust_manifest,
    pae,
)
from signed_review_receipts import SignedReviewError
from signed_review_ledger_demo import build_demonstration as build_signed_ledger_demo
from signed_review_receipts import build_trust_store, pae


ROOT = "agent://authority-root"
REGISTRY = "in-formation-space/reviewer-registry"
ISSUED = "2026-11-12T00:00:00Z"
EXPIRES = "2026-11-13T00:00:00Z"
VERIFY_AT = "2026-11-12T12:00:00Z"


def raw_public_key(private_key):
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def root_fixture(count=1):
    keys = [Ed25519PrivateKey.generate() for _ in range(count)]
    public = {
        hashlib.sha256(raw_public_key(key)).hexdigest(): key.public_key()
        for key in keys
    }
    return keys, public


def store_fixture():
    return build_signed_ledger_demo()["trust_store"]


def manifest_fixture(
    *,
    generation=1,
    previous=None,
    trust_store=None,
    issued_at=ISSUED,
    expires_at=EXPIRES,
):
    return build_trust_manifest(
        registry_id=REGISTRY,
        generation=generation,
        previous_manifest_digest=previous,
        trust_store=trust_store or store_fixture(),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def duplicate_key_manifest_envelope(manifest, root_key):
    core = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    raw = json.dumps(core, sort_keys=True, separators=(",", ":"))
    raw = raw[:-1] + ',"registry_id":' + json.dumps(manifest["registry_id"]) + "}"
    payload = raw.encode("utf-8")
    signature = root_key.sign(pae(PAYLOAD_TYPE, payload))
    keyid = hashlib.sha256(raw_public_key(root_key)).hexdigest()
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signatures": [{
            "keyid": keyid,
            "sig": base64.b64encode(signature).decode("ascii"),
        }],
    }


class ReviewTrustManifestTests(unittest.TestCase):
    def test_root_signed_manifest_round_trip(self):
        root_keys, pinned_roots = root_fixture()
        trust_store = store_fixture()
        manifest = manifest_fixture(trust_store=trust_store)
        envelope = sign_trust_manifest(manifest, root_keys)
        verified = verify_trust_manifest(
            envelope,
            pinned_roots,
            verification_time=VERIFY_AT,
            expected_registry_id=REGISTRY,
            minimum_generation=1,
        )
        self.assertEqual(verified["manifest_digest"], manifest["manifest_digest"])
        self.assertEqual(verified["trust_store_digest"], digest(trust_store))
        self.assertEqual(verified["generation"], 1)
        self.assertEqual(len(verified["root_keyids"]), 1)

    def test_only_out_of_band_pinned_root_key_is_accepted(self):
        root_keys, _ = root_fixture()
        _, different_roots = root_fixture()
        envelope = sign_trust_manifest(manifest_fixture(), root_keys)
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope, different_roots, verification_time=VERIFY_AT
            )

    def test_manifest_payload_tampering_invalidates_root_signature(self):
        root_keys, pinned_roots = root_fixture()
        envelope = sign_trust_manifest(manifest_fixture(), root_keys)
        altered = copy.deepcopy(envelope)
        raw = bytearray(base64.b64decode(altered["payload"]))
        raw[-2] ^= 1
        altered["payload"] = base64.b64encode(raw).decode("ascii")
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                altered, pinned_roots, verification_time=VERIFY_AT
            )

    def test_payload_type_is_bound_by_dsse_pae(self):
        root_keys, pinned_roots = root_fixture()
        envelope = sign_trust_manifest(manifest_fixture(), root_keys)
        altered = copy.deepcopy(envelope)
        altered["payloadType"] = PAYLOAD_TYPE + ";other=true"
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                altered, pinned_roots, verification_time=VERIFY_AT
            )

    def test_expired_manifest_is_rejected_at_expiry_boundary(self):
        root_keys, pinned_roots = root_fixture()
        manifest = manifest_fixture(expires_at="2026-11-12T12:00:00Z")
        envelope = sign_trust_manifest(manifest, root_keys)
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope, pinned_roots, verification_time="2026-11-12T12:00:00Z"
            )

    def test_not_yet_valid_manifest_is_rejected(self):
        root_keys, pinned_roots = root_fixture()
        manifest = manifest_fixture(issued_at="2026-11-12T12:00:01Z")
        envelope = sign_trust_manifest(manifest, root_keys)
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope, pinned_roots, verification_time=VERIFY_AT
            )

    def test_time_zone_offsets_and_noncanonical_timestamps_are_rejected(self):
        with self.assertRaises(TrustManifestError):
            manifest_fixture(issued_at="2026-11-12T00:00:00+00:00")
        with self.assertRaises(TrustManifestError):
            manifest_fixture(issued_at="2026-11-12T00:00:00.000Z")

    def test_manifest_requires_valid_trust_store_digest(self):
        root_keys, pinned_roots = root_fixture()
        manifest = manifest_fixture()
        manifest["trust_store_digest"] = "e" * 64
        core = {key: value for key, value in manifest.items() if key != "manifest_digest"}
        manifest["manifest_digest"] = digest(core)
        raw = json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        root_keyid = hashlib.sha256(raw_public_key(root_keys[0])).hexdigest()
        envelope = {
            "payloadType": PAYLOAD_TYPE,
            "payload": base64.b64encode(raw).decode("ascii"),
            "signatures": [{
                "keyid": root_keyid,
                "sig": base64.b64encode(root_keys[0].sign(pae(PAYLOAD_TYPE, raw))).decode("ascii"),
            }],
        }
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope, pinned_roots, verification_time=VERIFY_AT
            )

    def test_registry_identity_mismatch_is_rejected(self):
        root_keys, pinned_roots = root_fixture()
        envelope = sign_trust_manifest(manifest_fixture(), root_keys)
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope,
                pinned_roots,
                verification_time=VERIFY_AT,
                expected_registry_id="another-registry",
            )

    def test_generation_one_is_the_only_genesis_and_has_no_predecessor(self):
        root_keys, pinned_roots = root_fixture()
        with self.assertRaises(TrustManifestError):
            manifest_fixture(generation=1, previous="a" * 64)
        with self.assertRaises(TrustManifestError):
            manifest_fixture(generation=2, previous=None)
        envelope = sign_trust_manifest(manifest_fixture(), root_keys)
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope,
                pinned_roots,
                verification_time=VERIFY_AT,
                expected_generation=2,
                expected_previous_manifest_digest=None,
            )

    def test_strict_successor_requires_exact_generation_and_predecessor(self):
        root_keys, pinned_roots = root_fixture()
        first = manifest_fixture()
        second = manifest_fixture(
            generation=2,
            previous=first["manifest_digest"],
            issued_at="2026-11-12T13:00:00Z",
            expires_at="2026-11-14T00:00:00Z",
        )
        envelope = sign_trust_manifest(second, root_keys)
        verified = verify_trust_manifest(
            envelope,
            pinned_roots,
            verification_time="2026-11-12T14:00:00Z",
            expected_registry_id=REGISTRY,
            minimum_generation=2,
            expected_generation=2,
            expected_previous_manifest_digest=first["manifest_digest"],
        )
        self.assertEqual(verified["manifest_digest"], second["manifest_digest"])
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope,
                pinned_roots,
                verification_time="2026-11-12T14:00:00Z",
                expected_generation=3,
                expected_previous_manifest_digest=first["manifest_digest"],
            )
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope,
                pinned_roots,
                verification_time="2026-11-12T14:00:00Z",
                expected_generation=2,
                expected_previous_manifest_digest="f" * 64,
            )

    def test_minimum_generation_prevents_rollback(self):
        root_keys, pinned_roots = root_fixture()
        envelope = sign_trust_manifest(manifest_fixture(), root_keys)
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope,
                pinned_roots,
                verification_time=VERIFY_AT,
                minimum_generation=2,
            )

    def test_root_threshold_requires_distinct_pinned_signatures(self):
        root_keys, pinned_roots = root_fixture(2)
        manifest = manifest_fixture()
        one_signature = sign_trust_manifest(manifest, root_keys[:1])
        two_signatures = sign_trust_manifest(manifest, root_keys)
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                one_signature,
                pinned_roots,
                verification_time=VERIFY_AT,
                root_threshold=2,
            )
        verified = verify_trust_manifest(
            two_signatures,
            pinned_roots,
            verification_time=VERIFY_AT,
            root_threshold=2,
        )
        self.assertEqual(len(verified["root_keyids"]), 2)

    def test_duplicate_root_signatures_are_rejected(self):
        root_keys, pinned_roots = root_fixture()
        envelope = sign_trust_manifest(manifest_fixture(), root_keys)
        altered = copy.deepcopy(envelope)
        altered["signatures"].append(copy.deepcopy(altered["signatures"][0]))
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                altered, pinned_roots, verification_time=VERIFY_AT
            )

    def test_duplicate_json_keys_are_rejected_even_with_valid_root_signature(self):
        root_keys, pinned_roots = root_fixture()
        manifest = manifest_fixture()
        envelope = duplicate_key_manifest_envelope(manifest, root_keys[0])
        with self.assertRaises(TrustManifestError):
            verify_trust_manifest(
                envelope, pinned_roots, verification_time=VERIFY_AT
            )

    def test_root_signed_manifest_authenticates_review_bundle_trust_store(self):
        example = build_signed_ledger_demo()
        root_keys, pinned_roots = root_fixture()
        manifest = build_trust_manifest(
            registry_id=REGISTRY,
            generation=1,
            trust_store=example["trust_store"],
            issued_at=ISSUED,
            expires_at=EXPIRES,
        )
        envelope = sign_trust_manifest(manifest, root_keys)
        verified = verify_review_bundle_with_manifest(
            example["certificate"],
            example["signed_review_bundle"],
            envelope,
            pinned_roots,
            verification_time=VERIFY_AT,
            expected_registry_id=REGISTRY,
            review_artifacts={
                item["ref"]: item["content"] for item in example["review_artifacts"]
            },
        )
        self.assertEqual(
            verified["trust_store_digest"], example["trust_store_digest"]
        )
        self.assertTrue(verified["review_artifacts_verified"])

    def test_root_signed_manifest_verifies_ledger_anchored_bundle(self):
        example = build_signed_ledger_demo()
        root_keys, pinned_roots = root_fixture()
        manifest = build_trust_manifest(
            registry_id=REGISTRY,
            generation=1,
            trust_store=example["trust_store"],
            issued_at=ISSUED,
            expires_at=EXPIRES,
        )
        envelope = sign_trust_manifest(manifest, root_keys)
        result = verify_ledger_signed_review_bundle_with_manifest(
            example["ledger"],
            example["proposal_id"],
            envelope,
            pinned_roots,
            verification_time=VERIFY_AT,
            expected_registry_id=REGISTRY,
            review_artifacts={
                item["ref"]: item["content"] for item in example["review_artifacts"]
            },
        )
        self.assertEqual(result["manifest_digest"], manifest["manifest_digest"])
        self.assertEqual(result["bundle_digest"], example["signed_review_bundle"]["bundle_digest"])

    def test_current_manifest_rotation_removes_old_review_keys(self):
        example = build_signed_ledger_demo()
        root_keys, pinned_roots = root_fixture()
        rotated_keys = [Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()]
        rotated_store = build_trust_store([
            {
                "seat": seat,
                "principal": principal,
                "public_key": key.public_key(),
            }
            for seat, principal, key in [
                ("R01", "agent://reviewer-one-v2", rotated_keys[0]),
                ("R02", "agent://reviewer-two-v2", rotated_keys[1]),
            ]
        ])
        old_manifest = build_trust_manifest(
            registry_id=REGISTRY,
            generation=1,
            trust_store=example["trust_store"],
            issued_at=ISSUED,
            expires_at=EXPIRES,
        )
        new_manifest = build_trust_manifest(
            registry_id=REGISTRY,
            generation=2,
            previous_manifest_digest=old_manifest["manifest_digest"],
            trust_store=rotated_store,
            issued_at="2026-11-12T13:00:00Z",
            expires_at="2026-11-14T00:00:00Z",
        )
        envelope = sign_trust_manifest(new_manifest, root_keys)
        with self.assertRaises(SignedReviewError):
            verify_review_bundle_with_manifest(
                example["certificate"],
                example["signed_review_bundle"],
                envelope,
                pinned_roots,
                verification_time="2026-11-12T14:00:00Z",
                expected_registry_id=REGISTRY,
                expected_generation=2,
                expected_previous_manifest_digest=old_manifest["manifest_digest"],
            )

    def test_manifest_payload_schema(self):
        root_keys, pinned_roots = root_fixture()
        manifest = manifest_fixture()
        envelope = sign_trust_manifest(manifest, root_keys)
        raw = base64.b64decode(envelope["payload"])
        schema = json.loads(
            Path(__file__).with_name("review-trust-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(instance=json.loads(raw), schema=schema)
        successor = manifest_fixture(
            generation=2,
            previous=manifest["manifest_digest"],
            issued_at="2026-11-12T13:00:00Z",
            expires_at="2026-11-14T00:00:00Z",
        )
        jsonschema.validate(instance=successor, schema=schema)
        verify_trust_manifest(
            envelope,
            pinned_roots,
            verification_time=VERIFY_AT,
            expected_registry_id=REGISTRY,
        )


if __name__ == "__main__":
    unittest.main()
