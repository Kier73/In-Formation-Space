"""Demonstrate DSSE/Ed25519 review receipts with ephemeral demo-only keys."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from authority_lineage import digest
from review_certificate_demo import build_demonstration as build_certificate_demo
from signed_review_receipts import (
    PAYLOAD_TYPE,
    build_signed_review_bundle,
    build_trust_store,
    sign_review_vote,
    validate_signed_review_bundle,
)


def build_demonstration() -> dict[str, Any]:
    example = build_certificate_demo()
    certificate = example["certificate"]
    private_keys = {
        vote["reviewer_ref"]: Ed25519PrivateKey.generate()
        for vote in certificate["votes"]
    }
    trust_store = build_trust_store([
        {
            "seat": vote["seat"],
            "principal": vote["reviewer_ref"],
            "public_key": private_keys[vote["reviewer_ref"]].public_key(),
        }
        for vote in certificate["votes"]
    ])
    envelopes = [
        sign_review_vote(vote, private_keys[vote["reviewer_ref"]])
        for vote in certificate["votes"]
    ]
    review_artifacts = {
        item["ref"]: item["content"] for item in example["review_artifacts"]
    }
    bundle = build_signed_review_bundle(
        certificate,
        envelopes,
        trust_store,
        review_artifacts=review_artifacts,
    )
    validate_signed_review_bundle(
        certificate,
        bundle,
        trust_store,
        review_artifacts=review_artifacts,
    )
    core = {
        "format": "in-formation.signed-review-receipt-example",
        "schema": "in-formation.signed-review-receipt-example/0.1",
        "key_provisioning": (
            "Ephemeral Ed25519 keys generated inside this demonstration only. "
            "They prove possession within this run; they do not establish persistent "
            "or externally authenticated agent identities."
        ),
        "private_keys_included": False,
        "payload_type": PAYLOAD_TYPE,
        "certificate": certificate,
        "review_artifacts": example["review_artifacts"],
        "trust_store": trust_store,
        "trust_store_digest": digest(trust_store),
        "signed_review_bundle": bundle,
        "verification": {
            "signature_count": len(bundle["signed_review_votes"]),
            "all_certificate_votes_signed": (
                len(bundle["signed_review_votes"]) == len(certificate["votes"])
            ),
            "review_artifacts_verified": bundle["review_artifacts_verified"],
            "certificate_digest_matches": (
                bundle["certificate_digest"] == certificate["certificate_digest"]
            ),
            "trust_store_digest_matches": (
                bundle["trust_store_digest"] == digest(trust_store)
            ),
            "bundle_digest": bundle["bundle_digest"],
            "status": "VERIFIED_WITH_EPHEMERAL_DEMO_TRUST_STORE",
        },
        "interpretation": (
            "Ed25519 signatures bind each exact vote payload and DSSE payload type. "
            "Verification succeeds against the included demo trust store. The trust "
            "store is not itself authenticated; a deployment must pin or provision it "
            "through an independent trusted channel."
        ),
    }
    return {**core, "example_digest": digest(core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a signed authority-review receipt example."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    example = build_demonstration()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(example, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(example["verification"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
