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
from review_certificate_demo import build_demonstration
from signed_review_receipts import (
    PAYLOAD_TYPE,
    SignedReviewError,
    build_signed_review_bundle,
    build_trust_store,
    pae,
    sign_review_vote,
    validate_signed_review_bundle,
    verify_signed_review_vote,
)


def signed_fixture():
    example = build_demonstration()
    certificate = example["certificate"]
    private_keys = {
        "agent://reviewer-one": Ed25519PrivateKey.generate(),
        "agent://reviewer-two": Ed25519PrivateKey.generate(),
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
        sign_review_vote(certificate, vote, private_keys[vote["reviewer_ref"]])
        for vote in certificate["votes"]
    ]
    artifacts = {
        item["ref"]: item["content"] for item in example["review_artifacts"]
    }
    return certificate, trust_store, envelopes, artifacts, private_keys


class SignedReviewReceiptTests(unittest.TestCase):
    def test_dsse_pae_uses_utf8_byte_lengths_and_binds_type(self):
        self.assertEqual(pae("type", b"body"), b"DSSEv1 4 type 4 body")
        self.assertEqual(
            pae("týpe", "λ".encode("utf-8")),
            b"DSSEv1 5 t\xc3\xbdpe 2 \xce\xbb",
        )
        self.assertNotEqual(pae("type-a", b"body"), pae("type-b", b"body"))

    def test_signed_vote_round_trip(self):
        certificate, trust_store, envelopes, _, _ = signed_fixture()
        verified = verify_signed_review_vote(envelopes[0], trust_store)
        expected = certificate["votes"][0]
        self.assertEqual(verified["vote"], expected)
        self.assertEqual(verified["seat"], expected["seat"])
        self.assertEqual(verified["principal"], expected["reviewer_ref"])
        self.assertEqual(
            verified["payload_sha256"],
            hashlib.sha256(base64.b64decode(envelopes[0]["payload"])).hexdigest(),
        )

    def test_signed_bundle_covers_every_certificate_vote_and_artifact(self):
        certificate, trust_store, envelopes, artifacts, _ = signed_fixture()
        bundle = build_signed_review_bundle(
            certificate, envelopes, trust_store, review_artifacts=artifacts
        )
        self.assertEqual(len(bundle["signed_review_votes"]), 2)
        self.assertTrue(bundle["review_artifacts_verified"])
        validate_signed_review_bundle(
            certificate, bundle, trust_store, review_artifacts=artifacts
        )

    def test_portable_schemas_accept_trust_store_bundle_and_signed_payloads(self):
        certificate, trust_store, envelopes, artifacts, _ = signed_fixture()
        bundle = build_signed_review_bundle(
            certificate, envelopes, trust_store, review_artifacts=artifacts
        )
        root = Path(__file__).parent
        trust_schema = json.loads(
            (root / "review-trust-store.schema.json").read_text(encoding="utf-8")
        )
        bundle_schema = json.loads(
            (root / "signed-review-bundle.schema.json").read_text(encoding="utf-8")
        )
        payload_schema = json.loads(
            (root / "signed-authority-review-vote.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(instance=trust_store, schema=trust_schema)
        jsonschema.validate(instance=bundle, schema=bundle_schema)
        for envelope in envelopes:
            payload = json.loads(base64.b64decode(envelope["payload"]).decode("utf-8"))
            jsonschema.validate(instance=payload, schema=payload_schema)

    def test_bundle_without_artifact_bytes_makes_no_artifact_verification_claim(self):
        certificate, trust_store, envelopes, _, _ = signed_fixture()
        bundle = build_signed_review_bundle(certificate, envelopes, trust_store)
        self.assertFalse(bundle["review_artifacts_verified"])
        validate_signed_review_bundle(certificate, bundle, trust_store)

    def test_review_artifact_bytes_are_checked_when_provided(self):
        certificate, trust_store, envelopes, artifacts, _ = signed_fixture()
        altered = dict(artifacts)
        altered[next(iter(altered))] += "tampered"
        with self.assertRaises(SignedReviewError):
            build_signed_review_bundle(
                certificate, envelopes, trust_store, review_artifacts=altered
            )

    def test_payload_tampering_invalidates_signature(self):
        _, trust_store, envelopes, _, _ = signed_fixture()
        altered = copy.deepcopy(envelopes[0])
        raw = base64.b64decode(altered["payload"])
        altered["payload"] = base64.b64encode(raw + b" ").decode("ascii")
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(altered, trust_store)

    def test_payload_type_tampering_invalidates_signature(self):
        _, trust_store, envelopes, _, _ = signed_fixture()
        altered = copy.deepcopy(envelopes[0])
        altered["payloadType"] = PAYLOAD_TYPE + ";unexpected=true"
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(altered, trust_store)

    def test_proposal_context_tampering_invalidates_signature(self):
        _, trust_store, envelopes, _, _ = signed_fixture()
        altered = copy.deepcopy(envelopes[0])
        payload = json.loads(base64.b64decode(altered["payload"]).decode("utf-8"))
        payload["proposal_digest"] = "e" * 64
        altered["payload"] = base64.b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(altered, trust_store)

    def test_valid_vote_signature_cannot_be_replayed_for_another_certificate(self):
        certificate, trust_store, envelopes, _, _ = signed_fixture()
        other_certificate = copy.deepcopy(certificate)
        other_certificate["event_key"]["logical_time"] += 1
        core = {
            key: value for key, value in other_certificate.items()
            if key != "certificate_digest"
        }
        other_certificate["certificate_digest"] = digest(core)
        with self.assertRaises(SignedReviewError):
            build_signed_review_bundle(other_certificate, envelopes, trust_store)

    def test_signature_tampering_is_rejected(self):
        _, trust_store, envelopes, _, _ = signed_fixture()
        altered = copy.deepcopy(envelopes[0])
        sig = bytearray(base64.b64decode(altered["signatures"][0]["sig"]))
        sig[0] ^= 1
        altered["signatures"][0]["sig"] = base64.b64encode(sig).decode("ascii")
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(altered, trust_store)

    def test_unknown_key_is_rejected(self):
        _, trust_store, envelopes, _, _ = signed_fixture()
        altered = copy.deepcopy(envelopes[0])
        altered["signatures"][0]["keyid"] = "f" * 64
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(altered, trust_store)

    def test_trust_store_seat_assignment_is_bound_to_vote(self):
        _, trust_store, envelopes, _, _ = signed_fixture()
        altered = copy.deepcopy(trust_store)
        signer_keyid = envelopes[0]["signatures"][0]["keyid"]
        target = next(item for item in altered["keys"] if item["keyid"] == signer_keyid)
        target["seat"] = "R00" if target["seat"] != "R00" else "R01"
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(envelopes[0], altered)

    def test_trust_store_principal_assignment_is_bound_to_vote(self):
        _, trust_store, envelopes, _, _ = signed_fixture()
        altered = copy.deepcopy(trust_store)
        signer_keyid = envelopes[0]["signatures"][0]["keyid"]
        target = next(item for item in altered["keys"] if item["keyid"] == signer_keyid)
        target["principal"] = "agent://different-agent"
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(envelopes[0], altered)

    def test_trust_store_cannot_relabel_public_key_without_fingerprint_change(self):
        certificate, trust_store, envelopes, _, private_keys = signed_fixture()
        altered = copy.deepcopy(trust_store)
        target = altered["keys"][0]
        target_vote = next(
            vote for vote in certificate["votes"]
            if vote["reviewer_ref"] == target["principal"]
        )
        envelope = sign_review_vote(
            certificate, target_vote, private_keys[target["principal"]]
        )
        target["public_key"] = base64.b64encode(b"x" * 32).decode("ascii")
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(envelope, altered)

    def test_bundle_rejects_missing_receipt(self):
        certificate, trust_store, envelopes, _, _ = signed_fixture()
        with self.assertRaises(SignedReviewError):
            build_signed_review_bundle(certificate, envelopes[:1], trust_store)

    def test_bundle_rejects_duplicate_or_extra_receipt(self):
        certificate, trust_store, envelopes, _, _ = signed_fixture()
        with self.assertRaises(SignedReviewError):
            build_signed_review_bundle(
                certificate, [envelopes[0], envelopes[0]], trust_store
            )

    def test_signed_vote_must_exactly_match_certificate_vote(self):
        certificate, trust_store, envelopes, _, keys = signed_fixture()
        vote = dict(certificate["votes"][0])
        vote["rationale"] += " altered"
        envelope = sign_review_vote(certificate, vote, keys[vote["reviewer_ref"]])
        with self.assertRaises(SignedReviewError):
            build_signed_review_bundle(
                certificate, [envelope, envelopes[1]], trust_store
            )

    def test_certificate_digest_is_reconstructed(self):
        certificate, trust_store, envelopes, _, _ = signed_fixture()
        altered = copy.deepcopy(certificate)
        altered["votes"][0]["vote"] = "REJECT"
        with self.assertRaises(SignedReviewError):
            build_signed_review_bundle(altered, envelopes, trust_store)

    def test_bundle_digest_detects_mutation(self):
        certificate, trust_store, envelopes, _, _ = signed_fixture()
        bundle = build_signed_review_bundle(certificate, envelopes, trust_store)
        altered = copy.deepcopy(bundle)
        altered["signed_review_votes"][0]["reviewer_ref"] = "agent://forged"
        with self.assertRaises(SignedReviewError):
            validate_signed_review_bundle(certificate, altered, trust_store)

    def test_trust_store_change_invalidates_bundle_binding(self):
        certificate, trust_store, envelopes, _, _ = signed_fixture()
        bundle = build_signed_review_bundle(certificate, envelopes, trust_store)
        changed = copy.deepcopy(trust_store)
        changed["keys"][0]["principal"] += "-rotated"
        with self.assertRaises(SignedReviewError):
            validate_signed_review_bundle(certificate, bundle, changed)

    def test_one_key_cannot_attest_two_reviewers(self):
        example = build_demonstration()
        certificate = example["certificate"]
        key = Ed25519PrivateKey.generate()
        with self.assertRaises(SignedReviewError):
            build_trust_store([
                {"seat": "R01", "principal": "agent://one", "public_key": key.public_key()},
                {"seat": "R02", "principal": "agent://two", "public_key": key.public_key()},
            ])

    def test_json_duplicate_keys_are_rejected_after_signature_verification(self):
        certificate, trust_store, _, _, keys = signed_fixture()
        vote = certificate["votes"][0]
        from signed_review_receipts import _certificate_context, pae, _b64encode
        context_json = json.dumps(
            _certificate_context(certificate),
            sort_keys=True,
            separators=(",", ":"),
        )
        vote_without_outer = dict(vote)
        vote_json = json.dumps(vote_without_outer, sort_keys=True, separators=(",", ":"))
        duplicate_vote_json = (
            '{"seat":"R01","seat":"R01",'
            + vote_json[1:]
        )
        raw = (
            context_json[:-1] + ',"vote":' + duplicate_vote_json
        ).encode("utf-8")
        signature = keys["agent://reviewer-one"].sign(pae(PAYLOAD_TYPE, raw))
        pub = keys["agent://reviewer-one"].public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        keyid = hashlib.sha256(pub).hexdigest()
        envelope = {
            "payloadType": PAYLOAD_TYPE,
            "payload": _b64encode(raw),
            "signatures": [{"keyid": keyid, "sig": _b64encode(signature)}],
        }
        with self.assertRaises(SignedReviewError):
            verify_signed_review_vote(envelope, trust_store)


if __name__ == "__main__":
    unittest.main()
