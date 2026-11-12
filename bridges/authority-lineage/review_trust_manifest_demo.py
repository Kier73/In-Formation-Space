"""Demonstrate root-signed reviewer trust manifests and reviewer-key rotation."""
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
from signed_review_ledger_demo import build_demonstration as build_ledger_demo
from signed_review_receipts import (
    build_signed_review_bundle,
    build_trust_store,
    sign_review_vote,
)
from review_trust_manifest import (
    build_trust_manifest,
    sign_trust_manifest,
    verify_ledger_signed_review_bundle_with_manifest,
    verify_review_bundle_with_manifest,
    verify_trust_manifest,
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


def build_demonstration() -> dict[str, Any]:
    example = build_ledger_demo()
    certificate = example["certificate"]
    review_artifacts = {
        item["ref"]: item["content"] for item in example["review_artifacts"]
    }
    root_private = Ed25519PrivateKey.generate()
    root_public = root_private.public_key()
    root_keyid = hashlib.sha256(_raw_public(root_public)).hexdigest()
    pinned_root_public_keys = {root_keyid: root_public}

    manifest_1 = build_trust_manifest(
        registry_id=REGISTRY,
        generation=1,
        trust_store=example["trust_store"],
        issued_at=ISSUED_1,
        expires_at=EXPIRES_1,
    )
    envelope_1 = sign_trust_manifest(manifest_1, [root_private])
    old_bundle_verification = verify_review_bundle_with_manifest(
        certificate,
        example["signed_review_bundle"],
        envelope_1,
        pinned_root_public_keys,
        verification_time=VERIFY_1,
        expected_registry_id=REGISTRY,
        minimum_generation=1,
        review_artifacts=review_artifacts,
    )
    ledger_verification = verify_ledger_signed_review_bundle_with_manifest(
        example["ledger"],
        example["proposal_id"],
        envelope_1,
        pinned_root_public_keys,
        verification_time=VERIFY_1,
        expected_registry_id=REGISTRY,
        minimum_generation=1,
        review_artifacts=review_artifacts,
    )

    # Rotate reviewer key material while retaining stable principal labels and
    # seats. The old bundle is no longer valid under the new trust manifest.
    new_private_keys = {
        vote["reviewer_ref"]: Ed25519PrivateKey.generate()
        for vote in certificate["votes"]
    }
    new_trust_store = build_trust_store([
        {
            "seat": vote["seat"],
            "principal": vote["reviewer_ref"],
            "public_key": new_private_keys[vote["reviewer_ref"]].public_key(),
        }
        for vote in certificate["votes"]
    ])
    new_envelopes = [
        sign_review_vote(
            certificate, vote, new_private_keys[vote["reviewer_ref"]]
        )
        for vote in certificate["votes"]
    ]
    new_bundle = build_signed_review_bundle(
        certificate,
        new_envelopes,
        new_trust_store,
        review_artifacts=review_artifacts,
    )
    manifest_2 = build_trust_manifest(
        registry_id=REGISTRY,
        generation=2,
        previous_manifest_digest=manifest_1["manifest_digest"],
        trust_store=new_trust_store,
        issued_at=ISSUED_2,
        expires_at=EXPIRES_2,
    )
    envelope_2 = sign_trust_manifest(manifest_2, [root_private])
    generation_2 = verify_trust_manifest(
        envelope_2,
        pinned_root_public_keys,
        verification_time=VERIFY_2,
        expected_registry_id=REGISTRY,
        minimum_generation=2,
        expected_generation=2,
        expected_previous_manifest_digest=manifest_1["manifest_digest"],
    )
    new_bundle_verification = verify_review_bundle_with_manifest(
        certificate,
        new_bundle,
        envelope_2,
        pinned_root_public_keys,
        verification_time=VERIFY_2,
        expected_registry_id=REGISTRY,
        minimum_generation=2,
        expected_generation=2,
        expected_previous_manifest_digest=manifest_1["manifest_digest"],
        review_artifacts=review_artifacts,
    )
    old_bundle_rejected_after_rotation = False
    try:
        verify_review_bundle_with_manifest(
            certificate,
            example["signed_review_bundle"],
            envelope_2,
            pinned_root_public_keys,
            verification_time=VERIFY_2,
            expected_registry_id=REGISTRY,
            minimum_generation=2,
            expected_generation=2,
            expected_previous_manifest_digest=manifest_1["manifest_digest"],
            review_artifacts=review_artifacts,
        )
    except Exception as exc:
        from signed_review_receipts import SignedReviewError
        if not isinstance(exc, SignedReviewError):
            raise
        old_bundle_rejected_after_rotation = True
    if not old_bundle_rejected_after_rotation:
        raise AssertionError("old reviewer key set unexpectedly verified after rotation")

    core = {
        "format": "in-formation.review-trust-manifest-example",
        "schema": "in-formation.review-trust-manifest-example/0.1",
        "root_key_provisioning": (
            "The root key is ephemeral for this demonstration. Its public key is included "
            "as a verification input, not as an authenticated root of trust. Production "
            "verifiers must pin root public keys out of band."
        ),
        "private_keys_included": False,
        "registry_id": REGISTRY,
        "pinned_root_keyid": root_keyid,
        "pinned_root_public_key": {
            "algorithm": "Ed25519",
            "raw_base64": base64.b64encode(_raw_public(root_public)).decode("ascii"),
        },
        "generation_1": {
            "manifest": manifest_1,
            "dsse_envelope": envelope_1,
            "review_bundle": example["signed_review_bundle"],
            "review_verification": old_bundle_verification,
            "ledger_verification": ledger_verification,
        },
        "generation_2": {
            "manifest": manifest_2,
            "dsse_envelope": envelope_2,
            "trust_store": new_trust_store,
            "review_bundle": new_bundle,
            "manifest_verification": {
                "manifest_digest": generation_2["manifest_digest"],
                "generation": generation_2["generation"],
                "predecessor": manifest_2["previous_manifest_digest"],
                "root_keyids": generation_2["root_keyids"],
            },
            "new_bundle_verification": new_bundle_verification,
            "old_bundle_rejected_after_rotation": old_bundle_rejected_after_rotation,
        },
        "limitations": [
            "The root public key must be pinned independently; an included public key does not authenticate itself.",
            "This is a narrow signed trust manifest, not a complete TUF implementation.",
            "Root-key rotation is out-of-band in this version; the same pinned root signs both generations.",
            "No signed-at timestamp is present in vote receipts, so this does not establish whether a reviewer key was valid at the exact signing time.",
            "Private keys are generated ephemerally and are never written to the output artifact.",
        ],
    }
    return {**core, "example_digest": digest(core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate root-signed reviewer trust metadata with a key rotation."
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
        "generation_1": result["generation_1"]["manifest"]["manifest_digest"],
        "generation_2": result["generation_2"]["manifest"]["manifest_digest"],
        "root_key_pinned": True,
        "generation_2_verified": result["generation_2"]["manifest_verification"]["generation"] == 2,
        "new_bundle_verified": result["generation_2"]["new_bundle_verification"]["review_artifacts_verified"],
        "old_bundle_rejected_after_rotation": result["generation_2"]["old_bundle_rejected_after_rotation"],
        "private_keys_included": result["private_keys_included"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
