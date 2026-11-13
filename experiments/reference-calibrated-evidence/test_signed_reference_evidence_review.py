from __future__ import annotations

import base64
import copy
import hashlib
import json
import unittest
from pathlib import Path

import jsonschema
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from test_verified_reference_evidence_bundle import make_path_and_envelope
from verified_reference_evidence_bundle import build_verified_reference_evidence_bundle
from signed_reference_evidence_review import (
    SignedReferenceReviewError,
    SignedReferenceReviewMismatch,
    build_signed_reference_evidence_review,
    validate_signed_reference_evidence_review,
)

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / "signed-reference-evidence-review.schema.json").read_text(encoding="utf-8"))
REGISTRY = "Kier73/reference-evidence-reviewers"
ISSUED_AT = "2026-01-01T00:00:00Z"
EXPIRES_AT = "2027-01-01T00:00:00Z"
VERIFICATION_TIME = "2026-11-12T12:00:00Z"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def public_key_id(key):
    raw = key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def test_fixture():
    from test_verified_reference_evidence_bundle import build_policy
    policy = build_policy()
    execution, envelope = make_path_and_envelope(policy, signal="A")
    return build_verified_reference_evidence_bundle(
        policy_execution_record=execution,
        encounter_envelopes=(envelope,),
        authority_ledger_id="riv014-source-authority-ledger",
        ledger_created_by="RIV-014-test-fixture",
    )


def make_record(
    *,
    reviewer_keys=None,
    principals=None,
    root_keys=None,
    issued_at=ISSUED_AT,
    expires_at=EXPIRES_AT,
    verification_time=VERIFICATION_TIME,
):
    reviewer_keys = reviewer_keys or {
        "R01": Ed25519PrivateKey.generate(),
        "R02": Ed25519PrivateKey.generate(),
    }
    principals = principals or {"R01": "reviewer-alpha", "R02": "reviewer-beta"}
    root_keys = root_keys or [Ed25519PrivateKey.generate()]
    bundle = test_fixture()
    record = build_signed_reference_evidence_review(
        verified_reference_evidence_bundle=bundle,
        reviewer_private_keys=reviewer_keys,
        reviewer_principals=principals,
        root_private_keys=root_keys,
        registry_id=REGISTRY,
        manifest_issued_at=issued_at,
        manifest_expires_at=expires_at,
        verification_time=verification_time,
    )
    pinned = {
        public_key_id(key.public_key()): key.public_key()
        for key in root_keys
    }
    return record, pinned, reviewer_keys, root_keys


class SignedReferenceEvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.record, self.pinned_roots, self.reviewer_keys, self.root_keys = make_record()

    def test_two_independent_reviewers_and_root_manifest_attest_to_bundle_scope(self):
        result = validate_signed_reference_evidence_review(
            self.record,
            trusted_root_public_keys=self.pinned_roots,
            verification_time=VERIFICATION_TIME,
        )
        self.assertEqual(
            self.record["review_status"],
            "two_independent_signed_approvals_verified",
        )
        self.assertEqual(
            self.record["review_certificate"]["policy_snapshot"]["policy_id"],
            "independent_two_of_two",
        )
        self.assertEqual(
            self.record["review_certificate"]["evaluation"]["outcome"],
            "ACCEPTED",
        )
        self.assertEqual(
            [vote["seat"] for vote in self.record["review_certificate"]["votes"]],
            ["R01", "R02"],
        )
        self.assertEqual(
            self.record["proposal_resolution"]["outcome"],
            "ACCEPTED",
        )
        self.assertEqual(
            result["external_verification"]["signed_review_votes_verified"],
            2,
        )
        self.assertEqual(
            self.record["final_authority_frontier"]["status"],
            "SINGLE_DECISION",
        )
        self.assertEqual(
            self.record["final_authority_frontier"]["decisions"][0]["status"],
            "AUTHORIZED",
        )

    def test_attestation_scope_explicitly_excludes_physical_source_authentication(self):
        scope = self.record["attestation_scope"].lower()
        self.assertIn("not physical sensor identity", scope)
        self.assertIn("physical standard truth", scope)
        self.assertIn("source signature authenticity", scope)
        self.assertIn("reviewer approvals", self.record["trust_boundary"][0].lower())

    def test_review_and_root_private_keys_are_not_retained(self):
        encoded = json.dumps(self.record, sort_keys=True)
        for key in list(self.reviewer_keys.values()) + list(self.root_keys):
            raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
            self.assertNotIn(base64.b64encode(raw).decode("ascii"), encoded)
            self.assertNotIn(raw.hex(), encoded)

    def test_distinct_reviewer_principals_are_required(self):
        keys = {
            "R01": Ed25519PrivateKey.generate(),
            "R02": Ed25519PrivateKey.generate(),
        }
        with self.assertRaises(SignedReferenceReviewError):
            build_signed_reference_evidence_review(
                verified_reference_evidence_bundle=test_fixture(),
                reviewer_private_keys=keys,
                reviewer_principals={"R01": "same-reviewer", "R02": "same-reviewer"},
                root_private_keys=[Ed25519PrivateKey.generate()],
                registry_id=REGISTRY,
                manifest_issued_at=ISSUED_AT,
                manifest_expires_at=EXPIRES_AT,
                verification_time=VERIFICATION_TIME,
            )

    def test_missing_or_extra_reviewer_seat_is_rejected(self):
        with self.assertRaises(SignedReferenceReviewError):
            build_signed_reference_evidence_review(
                verified_reference_evidence_bundle=test_fixture(),
                reviewer_private_keys={"R01": Ed25519PrivateKey.generate()},
                reviewer_principals={"R01": "reviewer-alpha"},
                root_private_keys=[Ed25519PrivateKey.generate()],
                registry_id=REGISTRY,
                manifest_issued_at=ISSUED_AT,
                manifest_expires_at=EXPIRES_AT,
                verification_time=VERIFICATION_TIME,
            )

    def test_root_key_pin_mismatch_is_rejected(self):
        with self.assertRaises(Exception):
            validate_signed_reference_evidence_review(
                self.record,
                trusted_root_public_keys={
                    public_key_id(Ed25519PrivateKey.generate().public_key()):
                    Ed25519PrivateKey.generate().public_key()
                },
                verification_time=VERIFICATION_TIME,
            )

    def test_expired_manifest_is_rejected(self):
        with self.assertRaises(Exception):
            validate_signed_reference_evidence_review(
                self.record,
                trusted_root_public_keys=self.pinned_roots,
                verification_time="2027-01-01T00:00:00Z",
            )

    def test_not_yet_valid_manifest_is_rejected(self):
        with self.assertRaises(Exception):
            validate_signed_reference_evidence_review(
                self.record,
                trusted_root_public_keys=self.pinned_roots,
                verification_time="2025-12-31T23:59:59Z",
            )

    def test_tampered_reviewer_signature_is_rejected_even_after_record_digest_recalculation(self):
        changed = copy.deepcopy(self.record)
        envelope = changed["signed_review_bundle"]["signed_review_votes"][0]["envelope"]
        signature = envelope["signatures"][0]["sig"]
        envelope["signatures"][0]["sig"] = (
            ("A" if signature[0] != "A" else "B") + signature[1:]
        )
        core = {key: value for key, value in changed.items() if key != "review_record_digest"}
        changed["review_record_digest"] = sha(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ))
        with self.assertRaises(Exception):
            validate_signed_reference_evidence_review(
                changed,
                trusted_root_public_keys=self.pinned_roots,
                verification_time=VERIFICATION_TIME,
            )

    def test_altered_review_artifact_is_rejected(self):
        changed = copy.deepcopy(self.record)
        first = next(iter(changed["review_artifacts"]))
        changed["review_artifacts"][first] += "\ntampered"
        core = {key: value for key, value in changed.items() if key != "review_record_digest"}
        changed["review_record_digest"] = sha(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ))
        with self.assertRaises(Exception):
            validate_signed_reference_evidence_review(
                changed,
                trusted_root_public_keys=self.pinned_roots,
                verification_time=VERIFICATION_TIME,
            )

    def test_signed_review_record_and_schema_validate(self):
        self.assertIsInstance(validate_signed_reference_evidence_review(
            self.record,
            trusted_root_public_keys=self.pinned_roots,
            verification_time=VERIFICATION_TIME,
        ), dict)
        jsonschema.Draft202012Validator.check_schema(SCHEMA)
        jsonschema.validate(self.record, SCHEMA)

    def test_recomputed_trust_manifest_with_altered_store_is_not_accepted_by_old_roots(self):
        changed = copy.deepcopy(self.record)
        changed["root_signed_trust_manifest"]["payload"] = base64.b64encode(
            json.dumps(
                {"format": "forged"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).decode()
        core = {key: value for key, value in changed.items() if key != "review_record_digest"}
        changed["review_record_digest"] = sha(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ))
        with self.assertRaises(Exception):
            validate_signed_reference_evidence_review(
                changed,
                trusted_root_public_keys=self.pinned_roots,
                verification_time=VERIFICATION_TIME,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
