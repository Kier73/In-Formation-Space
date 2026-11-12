import base64
import copy
import hashlib
import json
import unittest
from pathlib import Path

import jsonschema

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from authority_lineage import (
    create_ledger,
    digest,
    issue_decision,
    propose_revision,
    resolve_proposal,
    validate_ledger,
)
from review_certificates import build_review_certificate, record_review_certificate
from signed_review_receipts import (
    SignedReviewError,
    build_signed_review_bundle,
    build_trust_store,
    record_signed_review_bundle,
    resolve_signed_reviewed_proposal,
    sign_review_vote,
    validate_signed_review_bundles_in_ledger,
)

EVENT = {"kind": "resolver", "logical_time": 77}
POLICY_DIGEST = "d" * 64


def _fixture():
    ledger = create_ledger("signed-review-ledger-tests", created_by="tests")
    ledger, initial_id = issue_decision(
        ledger,
        event_key=EVENT,
        status="AUTHORIZED",
        evidence_set_digest="a" * 64,
        policy_digest=POLICY_DIGEST,
        representative_ref="evidence://initial",
        issued_by="authority-original",
        rationale="Initial authority decision.",
    )
    ledger, proposal_id = propose_revision(
        ledger,
        event_key=EVENT,
        base_decision_ids=[initial_id],
        evidence_refs=[{"ref": "evidence://late-a", "sha256": "b" * 64}],
        reason="Late evidence requires a signed review.",
        proposed_by="agent://proposer",
    )
    bodies = {
        "review://r01": "Reviewer one inspected the cited evidence and approves.",
        "review://r02": "Reviewer two inspected the cited evidence and approves.",
    }
    votes = [
        {
            "seat": "R01",
            "reviewer_ref": "agent://reviewer-one",
            "vote": "APPROVE",
            "rationale": "Independent reviewer one approves the specific proposal.",
            "review_ref": "review://r01",
            "review_sha256": hashlib.sha256(bodies["review://r01"].encode()).hexdigest(),
        },
        {
            "seat": "R02",
            "reviewer_ref": "agent://reviewer-two",
            "vote": "APPROVE",
            "rationale": "Independent reviewer two approves the same proposal.",
            "review_ref": "review://r02",
            "review_sha256": hashlib.sha256(bodies["review://r02"].encode()).hexdigest(),
        },
    ]
    certificate = build_review_certificate(
        ledger, proposal_id, policy_name="independent_two_of_two", votes=votes
    )
    ledger = record_review_certificate(
        ledger, certificate, recorded_by="agent://review-coordinator"
    )
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
        for vote in votes
    ])
    envelopes = [
        sign_review_vote(certificate, vote, private_keys[vote["reviewer_ref"]])
        for vote in votes
    ]
    artifacts = bodies
    bundle = build_signed_review_bundle(
        certificate, envelopes, trust_store, review_artifacts=artifacts
    )
    return ledger, initial_id, proposal_id, certificate, trust_store, bundle, artifacts


def _rehash_ledger(ledger):
    previous = "0" * 64
    for entry in ledger["entries"]:
        entry["previous_digest"] = previous
        core = {
            key: entry[key]
            for key in ("sequence", "entry_type", "actor", "previous_digest", "payload")
        }
        entry["entry_digest"] = digest(core)
        previous = entry["entry_digest"]
    ledger["ledger_digest"] = digest([entry["entry_digest"] for entry in ledger["entries"]])


class SignedReviewLedgerTests(unittest.TestCase):
    def test_signed_bundle_is_appended_and_resolution_cites_both_receipts(self):
        ledger, _, proposal_id, certificate, trust_store, bundle, artifacts = _fixture()
        ledger = record_signed_review_bundle(
            ledger,
            proposal_id,
            bundle,
            trust_store,
            recorded_by="agent://receipt-recorder",
            review_artifacts=artifacts,
        )
        signed_entry = next(
            item for item in ledger["entries"]
            if item["entry_type"] == "proposal_review_signed"
        )
        schema_path = Path(__file__).with_name("authority-lineage.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(instance=ledger, schema=schema)
        self.assertEqual(signed_entry["payload"]["bundle_digest"], bundle["bundle_digest"])
        self.assertEqual(signed_entry["payload"]["trust_store_digest"], digest(trust_store))
        ledger = resolve_signed_reviewed_proposal(
            ledger,
            proposal_id,
            trusted_trust_store=trust_store,
            rationale="Two independently signed approvals authorize this review.",
            resolved_by="agent://review-coordinator",
            review_artifacts=artifacts,
        )
        resolution = next(
            item["payload"] for item in ledger["entries"]
            if item["entry_type"] == "proposal_resolved"
        )
        self.assertEqual(resolution["outcome"], "ACCEPTED")
        self.assertEqual(
            resolution["review_certificate_digest"], certificate["certificate_digest"]
        )
        self.assertEqual(
            resolution["signed_review_bundle_digest"], bundle["bundle_digest"]
        )
        types = [item["entry_type"] for item in ledger["entries"]]
        self.assertLess(types.index("proposal_review_certified"), types.index("proposal_review_signed"))
        self.assertLess(types.index("proposal_review_signed"), types.index("proposal_resolved"))
        validate_ledger(ledger)
        validate_signed_review_bundles_in_ledger(
            ledger,
            trusted_store_digests={proposal_id: digest(trust_store)},
            review_artifacts_by_proposal={proposal_id: artifacts},
        )
        ledger, revised_id = issue_decision(
            ledger,
            event_key=EVENT,
            status="CONFLICT",
            evidence_set_digest="c" * 64,
            policy_digest=POLICY_DIGEST,
            issued_by="authority-after-review",
            rationale="A signed, accepted proposal authorizes a new decision.",
            proposal_id=proposal_id,
        )
        self.assertEqual(revised_id, "decision-000002")
        validate_ledger(ledger)

    def test_unsigned_resolution_cannot_bypass_recorded_signed_bundle(self):
        ledger, _, proposal_id, _, trust_store, bundle, artifacts = _fixture()
        ledger = record_signed_review_bundle(
            ledger, proposal_id, bundle, trust_store,
            recorded_by="agent://recorder", review_artifacts=artifacts
        )
        with self.assertRaises(ValueError):
            resolve_proposal(
                ledger,
                proposal_id,
                outcome="ACCEPTED",
                rationale="Attempt to bypass signed receipt.",
                resolved_by="manual-reviewer",
            )

    def test_resolution_must_reference_exact_signed_bundle_digest(self):
        ledger, _, proposal_id, _, trust_store, bundle, artifacts = _fixture()
        ledger = record_signed_review_bundle(
            ledger, proposal_id, bundle, trust_store,
            recorded_by="agent://recorder", review_artifacts=artifacts
        )
        with self.assertRaises(ValueError):
            resolve_proposal(
                ledger,
                proposal_id,
                outcome="ACCEPTED",
                rationale="Attempt to reference another bundle.",
                resolved_by="manual-reviewer",
                signed_review_bundle_digest="f" * 64,
            )

    def test_wrong_external_trust_store_is_rejected_at_resolution(self):
        ledger, _, proposal_id, _, trust_store, bundle, artifacts = _fixture()
        ledger = record_signed_review_bundle(
            ledger, proposal_id, bundle, trust_store,
            recorded_by="agent://recorder", review_artifacts=artifacts
        )
        altered = copy.deepcopy(trust_store)
        altered["keys"][0]["principal"] += "-not-pinned"
        with self.assertRaises(SignedReviewError):
            resolve_signed_reviewed_proposal(
                ledger,
                proposal_id,
                trusted_trust_store=altered,
                rationale="Use an untrusted key mapping.",
                resolved_by="agent://review-coordinator",
            )

    def test_out_of_band_trust_store_digest_pin_is_enforced(self):
        ledger, _, proposal_id, _, trust_store, bundle, artifacts = _fixture()
        ledger = record_signed_review_bundle(
            ledger, proposal_id, bundle, trust_store,
            recorded_by="agent://recorder", review_artifacts=artifacts
        )
        validate_signed_review_bundles_in_ledger(
            ledger, trusted_store_digests={proposal_id: digest(trust_store)}
        )
        with self.assertRaises(SignedReviewError):
            validate_signed_review_bundles_in_ledger(
                ledger, trusted_store_digests={proposal_id: "f" * 64}
            )
        with self.assertRaises(SignedReviewError):
            validate_signed_review_bundles_in_ledger(
                ledger, trusted_store_digests={}
            )

    def test_core_ledger_validator_rejects_rehashed_invalid_signature(self):
        ledger, _, proposal_id, _, trust_store, bundle, artifacts = _fixture()
        ledger = record_signed_review_bundle(
            ledger, proposal_id, bundle, trust_store,
            recorded_by="agent://recorder", review_artifacts=artifacts
        )
        altered = copy.deepcopy(ledger)
        signed_entry = next(
            item for item in altered["entries"]
            if item["entry_type"] == "proposal_review_signed"
        )
        envelope = signed_entry["payload"]["bundle"]["signed_review_votes"][0]["envelope"]
        sig = bytearray(base64.b64decode(envelope["signatures"][0]["sig"]))
        sig[0] ^= 1
        envelope["signatures"][0]["sig"] = base64.b64encode(sig).decode("ascii")
        bundle_core = {
            key: value for key, value in signed_entry["payload"]["bundle"].items()
            if key != "bundle_digest"
        }
        new_digest = digest(bundle_core)
        signed_entry["payload"]["bundle"]["bundle_digest"] = new_digest
        signed_entry["payload"]["bundle_digest"] = new_digest
        _rehash_ledger(altered)
        with self.assertRaises(SignedReviewError):
            validate_ledger(altered)

    def test_signed_review_bundle_is_single_append_only_entry(self):
        ledger, _, proposal_id, _, trust_store, bundle, artifacts = _fixture()
        ledger = record_signed_review_bundle(
            ledger, proposal_id, bundle, trust_store,
            recorded_by="agent://recorder", review_artifacts=artifacts
        )
        with self.assertRaises(SignedReviewError):
            record_signed_review_bundle(
                ledger, proposal_id, bundle, trust_store,
                recorded_by="agent://another-recorder", review_artifacts=artifacts
            )

    def test_signed_bundle_cannot_be_recorded_after_resolution(self):
        ledger, _, proposal_id, _, trust_store, bundle, artifacts = _fixture()
        ledger = resolve_proposal(
            ledger,
            proposal_id,
            outcome="ACCEPTED",
            rationale="Manually resolved before a signed bundle was recorded.",
            resolved_by="manual-reviewer",
        )
        with self.assertRaises(SignedReviewError):
            record_signed_review_bundle(
                ledger, proposal_id, bundle, trust_store,
                recorded_by="agent://recorder", review_artifacts=artifacts
            )

    def test_stale_signed_review_is_retained_but_cannot_authorize_new_decision(self):
        ledger, initial_id, proposal_id, _, trust_store, bundle, artifacts = _fixture()
        ledger, competitor_id = propose_revision(
            ledger,
            event_key=EVENT,
            base_decision_ids=[initial_id],
            evidence_refs=[{"ref": "evidence://competing", "sha256": "e" * 64}],
            reason="Competing review proposal.",
            proposed_by="agent://competitor",
        )
        ledger = record_signed_review_bundle(
            ledger, proposal_id, bundle, trust_store,
            recorded_by="agent://recorder", review_artifacts=artifacts
        )
        ledger = resolve_proposal(
            ledger,
            competitor_id,
            outcome="ACCEPTED",
            rationale="The competing proposal resolves first.",
            resolved_by="independent-chair",
        )
        ledger, _ = issue_decision(
            ledger,
            event_key=EVENT,
            status="CONFLICT",
            evidence_set_digest="9" * 64,
            policy_digest=POLICY_DIGEST,
            issued_by="independent-chair",
            rationale="Competing branch supersedes the old decision.",
            proposal_id=competitor_id,
        )
        ledger = resolve_signed_reviewed_proposal(
            ledger,
            proposal_id,
            trusted_trust_store=trust_store,
            rationale="Signed review is preserved, but its cited base is stale.",
            resolved_by="agent://review-coordinator",
            review_artifacts=artifacts,
        )
        resolution = next(
            item["payload"] for item in ledger["entries"]
            if item["entry_type"] == "proposal_resolved"
            and item["payload"]["proposal_id"] == proposal_id
        )
        self.assertEqual(resolution["outcome"], "STALE")
        self.assertEqual(resolution["signed_review_bundle_digest"], bundle["bundle_digest"])
        validate_ledger(ledger)


if __name__ == "__main__":
    unittest.main()
