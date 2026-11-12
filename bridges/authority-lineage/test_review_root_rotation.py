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
from review_root_rotation import (
    PAYLOAD_TYPE,
    RootRotationError,
    build_root_transition,
    sign_root_transition,
    verify_root_transition,
    verify_rotated_trust_manifest,
)
from review_trust_manifest import build_trust_manifest, sign_trust_manifest
from signed_review_ledger_demo import build_demonstration as build_ledger_demo


REGISTRY = "in-formation-space/reviewer-registry"
ISSUED_1 = "2026-11-12T00:00:00Z"
EXPIRES_1 = "2026-11-13T00:00:00Z"
ISSUED_2 = "2026-11-12T13:00:00Z"
EXPIRES_2 = "2026-11-14T00:00:00Z"
VERIFY_2 = "2026-11-12T14:00:00Z"


def raw_public(private_key):
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def key_map(private_keys):
    return {
        hashlib.sha256(raw_public(key)).hexdigest(): key.public_key()
        for key in private_keys
    }


def build_fixture(old_count=1, new_count=1, new_threshold=1):
    example = build_ledger_demo()
    old_keys = [Ed25519PrivateKey.generate() for _ in range(old_count)]
    new_keys = [Ed25519PrivateKey.generate() for _ in range(new_count)]
    old_public = key_map(old_keys)
    new_public = key_map(new_keys)
    manifest_1 = build_trust_manifest(
        registry_id=REGISTRY,
        generation=1,
        trust_store=example["trust_store"],
        issued_at=ISSUED_1,
        expires_at=EXPIRES_1,
    )
    manifest_2 = build_trust_manifest(
        registry_id=REGISTRY,
        generation=2,
        previous_manifest_digest=manifest_1["manifest_digest"],
        trust_store=example["trust_store"],
        issued_at=ISSUED_2,
        expires_at=EXPIRES_2,
    )
    transition = build_root_transition(
        manifest_2,
        new_public,
        previous_generation=1,
        previous_manifest_digest=manifest_1["manifest_digest"],
        new_root_threshold=new_threshold,
    )
    transition_envelope = sign_root_transition(transition, old_keys, new_keys)
    manifest_envelope = sign_trust_manifest(manifest_2, new_keys)
    return {
        "example": example,
        "old_keys": old_keys,
        "new_keys": new_keys,
        "old_public": old_public,
        "new_public": new_public,
        "manifest_1": manifest_1,
        "manifest_2": manifest_2,
        "transition": transition,
        "transition_envelope": transition_envelope,
        "manifest_envelope": manifest_envelope,
    }


class ReviewRootRotationTests(unittest.TestCase):
    def test_successor_requires_both_old_and_new_root_authorization(self):
        fx = build_fixture()
        result = verify_rotated_trust_manifest(
            fx["transition_envelope"],
            fx["manifest_envelope"],
            fx["old_public"],
            verification_time=VERIFY_2,
            expected_registry_id=REGISTRY,
            expected_previous_generation=1,
            expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
        )
        self.assertEqual(result["generation"], 2)
        self.assertEqual(result["manifest_digest"], fx["manifest_2"]["manifest_digest"])
        self.assertEqual(result["new_root_keyids"], sorted(fx["new_public"]))
        self.assertEqual(
            result["trust_store_digest"], fx["manifest_2"]["trust_store_digest"]
        )

    def test_missing_old_root_signature_is_rejected(self):
        fx = build_fixture()
        old_ids = set(fx["old_public"])
        altered = copy.deepcopy(fx["transition_envelope"])
        altered["signatures"] = [
            item for item in altered["signatures"] if item["keyid"] not in old_ids
        ]
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                altered,
                fx["old_public"],
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_missing_new_root_signature_is_rejected(self):
        fx = build_fixture(new_count=2, new_threshold=2)
        new_ids = set(fx["new_public"])
        altered = copy.deepcopy(fx["transition_envelope"])
        altered["signatures"] = [
            item for item in altered["signatures"]
            if item["keyid"] != sorted(new_ids)[-1]
        ]
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                altered,
                fx["old_public"],
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_old_root_threshold_is_enforced(self):
        fx = build_fixture(old_count=2)
        only_one_old = [fx["old_keys"][0]]
        altered = sign_root_transition(
            fx["transition"], only_one_old, fx["new_keys"]
        )
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                altered,
                fx["old_public"],
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
                old_root_threshold=2,
            )

    def test_new_root_threshold_is_enforced_by_transition_and_manifest(self):
        fx = build_fixture(new_count=2, new_threshold=2)
        with self.assertRaises(RootRotationError):
            verify_rotated_trust_manifest(
                fx["transition_envelope"],
                fx["manifest_envelope"],
                fx["old_public"],
                verification_time=VERIFY_2,
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_successor_manifest_must_be_signed_by_the_new_root_set(self):
        fx = build_fixture()
        wrongly_signed = sign_trust_manifest(fx["manifest_2"], fx["old_keys"])
        with self.assertRaises(Exception):
            verify_rotated_trust_manifest(
                fx["transition_envelope"],
                wrongly_signed,
                fx["old_public"],
                verification_time=VERIFY_2,
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_wrong_pinned_old_root_is_rejected(self):
        fx = build_fixture()
        wrong_private = Ed25519PrivateKey.generate()
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                fx["transition_envelope"],
                key_map([wrong_private]),
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_wrong_registry_is_rejected(self):
        fx = build_fixture()
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                fx["transition_envelope"],
                fx["old_public"],
                expected_registry_id="another-registry",
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_previous_generation_and_digest_are_pinned(self):
        fx = build_fixture()
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                fx["transition_envelope"],
                fx["old_public"],
                expected_registry_id=REGISTRY,
                expected_previous_generation=2,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                fx["transition_envelope"],
                fx["old_public"],
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest="f" * 64,
            )

    def test_successor_manifest_digest_is_bound_by_transition(self):
        fx = build_fixture()
        other_manifest = build_trust_manifest(
            registry_id=REGISTRY,
            generation=2,
            previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            trust_store=fx["example"]["trust_store"],
            issued_at=ISSUED_2,
            expires_at="2026-11-15T00:00:00Z",
        )
        other_envelope = sign_trust_manifest(other_manifest, fx["new_keys"])
        with self.assertRaises(RootRotationError):
            verify_rotated_trust_manifest(
                fx["transition_envelope"],
                other_envelope,
                fx["old_public"],
                verification_time=VERIFY_2,
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_root_transition_payload_tampering_invalidates_both_thresholds(self):
        fx = build_fixture()
        altered = copy.deepcopy(fx["transition_envelope"])
        payload = bytearray(base64.b64decode(altered["payload"]))
        payload[-2] ^= 1
        altered["payload"] = base64.b64encode(payload).decode("ascii")
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                altered,
                fx["old_public"],
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_duplicate_signature_keyids_are_rejected(self):
        fx = build_fixture()
        altered = copy.deepcopy(fx["transition_envelope"])
        altered["signatures"].append(copy.deepcopy(altered["signatures"][0]))
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                altered,
                fx["old_public"],
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_unknown_signature_key_is_rejected(self):
        fx = build_fixture()
        unknown = Ed25519PrivateKey.generate()
        signature = unknown.sign(
            __import__("review_trust_manifest").pae(
                PAYLOAD_TYPE,
                base64.b64decode(fx["transition_envelope"]["payload"]),
            )
        )
        altered = copy.deepcopy(fx["transition_envelope"])
        altered["signatures"].append({
            "keyid": hashlib.sha256(raw_public(unknown)).hexdigest(),
            "sig": base64.b64encode(signature).decode("ascii"),
        })
        altered["signatures"].sort(key=lambda item: item["keyid"])
        with self.assertRaises(RootRotationError):
            verify_root_transition(
                altered,
                fx["old_public"],
                expected_registry_id=REGISTRY,
                expected_previous_generation=1,
                expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_one_overlapping_root_key_can_count_in_both_roles(self):
        shared = Ed25519PrivateKey.generate()
        shared_map = key_map([shared])
        fx = build_fixture()
        example = fx["example"]
        manifest_1 = fx["manifest_1"]
        manifest_2 = build_trust_manifest(
            registry_id=REGISTRY,
            generation=2,
            previous_manifest_digest=manifest_1["manifest_digest"],
            trust_store=example["trust_store"],
            issued_at=ISSUED_2,
            expires_at=EXPIRES_2,
        )
        transition = build_root_transition(
            manifest_2,
            shared_map,
            previous_generation=1,
            previous_manifest_digest=manifest_1["manifest_digest"],
        )
        envelope = sign_root_transition(transition, [shared], [shared])
        result = verify_root_transition(
            envelope,
            shared_map,
            expected_registry_id=REGISTRY,
            expected_previous_generation=1,
            expected_previous_manifest_digest=manifest_1["manifest_digest"],
        )
        self.assertEqual(result["old_root_keyids"], result["new_root_keyids"])

    def test_transition_schema_accepts_signed_transition_document(self):
        fx = build_fixture()
        schema = json.loads(
            Path(__file__).with_name("review-root-transition.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(instance=fx["transition"], schema=schema)
        self.assertEqual(
            fx["transition"]["next_generation"],
            fx["transition"]["previous_generation"] + 1,
        )

    def test_transition_cannot_skip_a_generation_at_construction(self):
        fx = build_fixture()
        with self.assertRaises(RootRotationError):
            build_root_transition(
                fx["manifest_2"],
                fx["new_public"],
                previous_generation=0,
                previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
            )

    def test_chain_continues_from_new_root_set(self):
        fx = build_fixture()
        next_result = verify_rotated_trust_manifest(
            fx["transition_envelope"],
            fx["manifest_envelope"],
            fx["old_public"],
            verification_time=VERIFY_2,
            expected_registry_id=REGISTRY,
            expected_previous_generation=1,
            expected_previous_manifest_digest=fx["manifest_1"]["manifest_digest"],
        )
        root_3 = [Ed25519PrivateKey.generate()]
        manifest_3 = build_trust_manifest(
            registry_id=REGISTRY,
            generation=3,
            previous_manifest_digest=next_result["manifest_digest"],
            trust_store=fx["example"]["trust_store"],
            issued_at="2026-11-12T15:00:00Z",
            expires_at="2026-11-16T00:00:00Z",
        )
        transition_3 = build_root_transition(
            manifest_3,
            key_map(root_3),
            previous_generation=2,
            previous_manifest_digest=next_result["manifest_digest"],
        )
        envelope_3 = sign_root_transition(
            transition_3, fx["new_keys"], root_3
        )
        manifest_envelope_3 = sign_trust_manifest(manifest_3, root_3)
        result_3 = verify_rotated_trust_manifest(
            envelope_3,
            manifest_envelope_3,
            fx["new_public"],
            verification_time="2026-11-12T16:00:00Z",
            expected_registry_id=REGISTRY,
            expected_previous_generation=2,
            expected_previous_manifest_digest=next_result["manifest_digest"],
        )
        self.assertEqual(result_3["generation"], 3)


if __name__ == "__main__":
    unittest.main()
