"""Demonstrate threshold-authorized root-key rotation for reviewer trust."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from authority_lineage import digest
from review_root_rotation import (
    build_root_transition,
    sign_root_transition,
    verify_rotated_trust_manifest,
)
from review_trust_manifest import (
    build_trust_manifest,
    sign_trust_manifest,
    verify_ledger_signed_review_bundle_with_manifest,
    verify_review_bundle_with_manifest,
)
from signed_review_ledger_demo import build_demonstration as build_ledger_demo
from signed_review_receipts import (
    SignedReviewError,
    build_signed_review_bundle,
    build_trust_store,
    sign_review_vote,
)


REGISTRY = "in-formation-space/reviewer-registry"
ISSUED_1 = "2026-11-12T00:00:00Z"
EXPIRES_1 = "2026-11-13T00:00:00Z"
ISSUED_2 = "2026-11-12T13:00:00Z"
EXPIRES_2 = "2026-11-14T00:00:00Z"
VERIFY_1 = "2026-11-12T12:00:00Z"
VERIFY_2 = "2026-11-12T14:00:00Z"


def _raw_public(public_key) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _public_map(private_keys):
    return {
        hashlib.sha256(_raw_public(key.public_key())).hexdigest(): key.public_key()
        for key in private_keys
    }


def build_demonstration() -> dict[str, Any]:
    example = build_ledger_demo()
    certificate = example["certificate"]
    review_artifacts = {
        item["ref"]: item["content"] for item in example["review_artifacts"]
    }

    # The old root is the verifier's already-pinned trust anchor. Two distinct
    # new root keys form a 2-of-2 successor role for this demonstration.
    old_root = Ed25519PrivateKey.generate()
    old_root_public = _public_map([old_root])
    new_roots = [Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()]
    new_root_public = _public_map(new_roots)

    manifest_1 = build_trust_manifest(
        registry_id=REGISTRY,
        generation=1,
        trust_store=example["trust_store"],
        issued_at=ISSUED_1,
        expires_at=EXPIRES_1,
    )
    manifest_1_envelope = sign_trust_manifest(manifest_1, [old_root])
    old_bundle_verified = verify_review_bundle_with_manifest(
        certificate,
        example["signed_review_bundle"],
        manifest_1_envelope,
        old_root_public,
        verification_time=VERIFY_1,
        expected_registry_id=REGISTRY,
        minimum_generation=1,
        review_artifacts=review_artifacts,
    )
    old_ledger_verified = verify_ledger_signed_review_bundle_with_manifest(
        example["ledger"],
        example["proposal_id"],
        manifest_1_envelope,
        old_root_public,
        verification_time=VERIFY_1,
        expected_registry_id=REGISTRY,
        minimum_generation=1,
        review_artifacts=review_artifacts,
    )

    # Rotate reviewer-key material while keeping the two principal labels and
    # assigned seats stable. Only the public key fingerprints change.
    new_reviewer_private = {
        vote["reviewer_ref"]: Ed25519PrivateKey.generate()
        for vote in certificate["votes"]
    }
    new_reviewer_store = build_trust_store([
        {
            "seat": vote["seat"],
            "principal": vote["reviewer_ref"],
            "public_key": new_reviewer_private[vote["reviewer_ref"]].public_key(),
        }
        for vote in certificate["votes"]
    ])
    new_vote_envelopes = [
        sign_review_vote(
            certificate, vote, new_reviewer_private[vote["reviewer_ref"]]
        )
        for vote in certificate["votes"]
    ]
    new_review_bundle = build_signed_review_bundle(
        certificate,
        new_vote_envelopes,
        new_reviewer_store,
        review_artifacts=review_artifacts,
    )
    manifest_2 = build_trust_manifest(
        registry_id=REGISTRY,
        generation=2,
        previous_manifest_digest=manifest_1["manifest_digest"],
        trust_store=new_reviewer_store,
        issued_at=ISSUED_2,
        expires_at=EXPIRES_2,
    )
    manifest_2_envelope = sign_trust_manifest(manifest_2, new_roots)
    transition = build_root_transition(
        manifest_2,
        new_root_public,
        previous_generation=1,
        previous_manifest_digest=manifest_1["manifest_digest"],
        new_root_threshold=2,
    )
    transition_envelope = sign_root_transition(
        transition,
        [old_root],
        new_roots,
    )
    rotation = verify_rotated_trust_manifest(
        transition_envelope,
        manifest_2_envelope,
        old_root_public,
        verification_time=VERIFY_2,
        expected_registry_id=REGISTRY,
        expected_previous_generation=1,
        expected_previous_manifest_digest=manifest_1["manifest_digest"],
    )
    new_bundle_verified = verify_review_bundle_with_manifest(
        certificate,
        new_review_bundle,
        manifest_2_envelope,
        new_root_public,
        verification_time=VERIFY_2,
        expected_registry_id=REGISTRY,
        minimum_generation=2,
        expected_generation=2,
        expected_previous_manifest_digest=manifest_1["manifest_digest"],
        review_artifacts=review_artifacts,
    )
    old_bundle_rejected = False
    try:
        verify_review_bundle_with_manifest(
            certificate,
            example["signed_review_bundle"],
            manifest_2_envelope,
            new_root_public,
            verification_time=VERIFY_2,
            expected_registry_id=REGISTRY,
            minimum_generation=2,
            expected_generation=2,
            expected_previous_manifest_digest=manifest_1["manifest_digest"],
            review_artifacts=review_artifacts,
        )
    except SignedReviewError:
        old_bundle_rejected = True
    if not old_bundle_rejected:
        raise AssertionError("retired reviewer key set unexpectedly passed under generation 2")

    core = {
        "format": "in-formation.review-root-rotation-example",
        "schema": "in-formation.review-root-rotation-example/0.1",
        "registry_id": REGISTRY,
        "root_provisioning": (
            "Generation-1 root public key is the externally pinned bootstrap trust anchor. "
            "Generation-2 root keys are authorized by both old and new root signature "
            "thresholds. This artifact includes public keys only; all private keys are "
            "ephemeral and are not included."
        ),
        "private_keys_included": False,
        "generation_1": {
            "manifest": manifest_1,
            "manifest_envelope": manifest_1_envelope,
            "old_root_keyids": sorted(old_root_public),
            "review_bundle_digest": example["signed_review_bundle"]["bundle_digest"],
            "review_bundle_verified": old_bundle_verified,
            "ledger_bundle_verified": old_ledger_verified,
        },
        "root_transition": {
            "document": transition,
            "dsse_envelope": transition_envelope,
            "old_root_signature_count": len(rotation["old_root_keyids"]),
            "old_root_threshold": 1,
            "new_root_signature_count": len(rotation["new_root_keyids"]),
            "new_root_threshold": rotation["root_threshold"],
        },
        "generation_2": {
            "manifest": manifest_2,
            "manifest_envelope": manifest_2_envelope,
            "new_root_public_keys": [
                {
                    "keyid": keyid,
                    "public_key": base64.b64encode(_raw_public(key)).decode("ascii"),
                }
                for keyid, key in sorted(new_root_public.items())
            ],
            "reviewer_trust_store": new_reviewer_store,
            "new_review_bundle": new_review_bundle,
            "rotation_verified": {
                "manifest_digest": rotation["manifest_digest"],
                "transition_digest": rotation["transition_digest"],
                "new_root_keyids": rotation["new_root_keyids"],
                "root_threshold": rotation["root_threshold"],
            },
            "new_bundle_verified": new_bundle_verified,
            "old_bundle_rejected_after_reviewer_key_rotation": old_bundle_rejected,
        },
        "security_boundaries": [
            "The generation-1 root key must be pinned out of band.",
            "Both old and new root thresholds must sign the exact successor transition.",
            "The successor manifest must be signed by the new root set and match the digest named in the transition.",
            "The verifier must persist the accepted generation, manifest digest, and current root public-key set.",
            "Emergency recovery after compromise of the currently trusted root threshold remains an out-of-band recovery problem.",
            "No trusted signed-at time is added to reviewer votes; exact historical key validity at vote time is not reconstructed.",
        ],
    }
    return {**core, "example_digest": digest(core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a dual-authorized reviewer trust root rotation example."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build_demonstration()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "registry_id": result["registry_id"],
        "previous_generation": result["generation_1"]["manifest"]["generation"],
        "next_generation": result["generation_2"]["manifest"]["generation"],
        "old_root_signature_count": result["root_transition"]["old_root_signature_count"],
        "new_root_signature_count": result["root_transition"]["new_root_signature_count"],
        "new_bundle_verified": result["generation_2"]["new_bundle_verified"]["review_artifacts_verified"],
        "old_bundle_rejected_after_rotation": result["generation_2"]["old_bundle_rejected_after_reviewer_key_rotation"],
        "private_keys_included": result["private_keys_included"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
