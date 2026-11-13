from __future__ import annotations

import copy
import hashlib
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

from completion_receipts import (
    CompletionReceiptError,
    create_completion_receipt,
    derive_execution_id,
    runner_key_id,
    verify_completion_receipt,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def fixture_documents():
    request_core = {
        "format": "in-formation.proof-action-request/0.1",
        "attempt_id": "proof-run:000001",
        "query_label": "establish identity",
        "plan_digest": "1" * 64,
        "proof_ground_digest": "2" * 64,
        "candidate_transition": {
            "transition_id": "transition-1",
            "source_id": "obligation-root",
            "tactic": "rfl",
            "proposed_subgoal_ids": [],
        },
    }
    request = {**request_core, "request_digest": digest(request_core)}
    result_core = {
        "format": "in-formation.proof-action-result/0.1",
        "attempt_id": request["attempt_id"],
        "request_digest": request["request_digest"],
        "return_evidence": {
            "evidence_ref": "encounter://proof-return/1",
            "encounter_id": "proof-return-1",
            "payload_digest": "3" * 64,
            "canonicalization": "canonical-json-v1",
        },
        "proof_trace": {
            "format": "vgi.lean-proof-trace/0.1",
            "transitions": [{"attempt_id": request["attempt_id"], "status": "elaborated"}],
        },
    }
    result = {**result_core, "result_digest": digest(result_core)}

    epoch_id = "proof-route-epoch-17"
    runner_id = "lean-worker-pool-a"
    execution_id = derive_execution_id(
        epoch_id, request["attempt_id"], request["request_digest"]
    )
    event_core = {
        "sequence": 8,
        "event_type": "execution_authorized",
        "epoch_id": epoch_id,
        "epoch_number": 2,
        "route": {
            "host_id": "proof-host",
            "worker_id": "proof-worker",
            "request_channel": "proof-request-2",
            "result_channel": "proof-result-2",
        },
        "route_digest": None,
        "details": {
            "owner_id": "route-owner-2",
            "owner_generation": 3,
            "attempt_id": request["attempt_id"],
            "request_digest": request["request_digest"],
            "request_sequence": 6,
            "admission_event_digest": "4" * 64,
            "execution_id": execution_id,
            "runner_id": runner_id,
        },
        "previous_event_digest": "5" * 64,
    }
    event_core["route_digest"] = digest(event_core["route"])
    event = {**event_core, "event_digest": digest(event_core)}
    return event, request, result, epoch_id, runner_id


class CompletionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.event, self.request, self.result, self.epoch_id, self.runner_id = fixture_documents()

    def make_receipt(self):
        return create_completion_receipt(
            self.event, self.request, self.result, private_key=self.private_key
        )

    def verify(self, receipt, *, event=None, request=None, result=None, key=None, runner_id=None):
        return verify_completion_receipt(
            receipt,
            event or self.event,
            request or self.request,
            result or self.result,
            trusted_runner_id=runner_id or self.runner_id,
            trusted_public_key=key or self.public_key,
        )

    def test_valid_receipt_binds_route_ticket_request_and_entire_result(self):
        receipt = self.make_receipt()
        verified = self.verify(receipt)

        self.assertEqual(verified.route_epoch_id, self.epoch_id)
        self.assertEqual(verified.execution_id, self.event["details"]["execution_id"])
        self.assertEqual(verified.attempt_id, self.request["attempt_id"])
        self.assertEqual(verified.request_digest, self.request["request_digest"])
        self.assertEqual(verified.runner_id, self.runner_id)
        self.assertEqual(verified.authorization_event_digest, self.event["event_digest"])
        self.assertEqual(verified.result_digest, self.result["result_digest"])
        self.assertEqual(verified.return_evidence_digest, digest(self.result["return_evidence"]))
        self.assertEqual(verified.proof_trace_digest, digest(self.result["proof_trace"]))

    def test_signature_is_deterministic_for_same_key_and_receipt_material(self):
        self.assertEqual(self.make_receipt(), self.make_receipt())

    def test_receipt_rejects_changed_proof_trace_even_when_new_result_is_self_consistent(self):
        receipt = self.make_receipt()
        changed = copy.deepcopy(self.result)
        changed["proof_trace"]["transitions"][0]["status"] = "rejected"
        core = {key: value for key, value in changed.items() if key != "result_digest"}
        changed["result_digest"] = digest(core)

        with self.assertRaisesRegex(CompletionReceiptError, "result_digest mismatch"):
            self.verify(receipt, result=changed)

    def test_receipt_rejects_changed_return_evidence_even_when_result_digest_is_recomputed(self):
        receipt = self.make_receipt()
        changed = copy.deepcopy(self.result)
        changed["return_evidence"]["payload_digest"] = "a" * 64
        core = {key: value for key, value in changed.items() if key != "result_digest"}
        changed["result_digest"] = digest(core)

        with self.assertRaisesRegex(CompletionReceiptError, "result_digest mismatch"):
            self.verify(receipt, result=changed)

    def test_result_must_correlate_to_exact_attempt_and_request_digest(self):
        receipt = self.make_receipt()
        changed = copy.deepcopy(self.result)
        changed["attempt_id"] = "proof-run:000002"
        core = {key: value for key, value in changed.items() if key != "result_digest"}
        changed["result_digest"] = digest(core)

        with self.assertRaisesRegex(CompletionReceiptError, "attempt ID"):
            self.verify(receipt, result=changed)

    def test_tampered_request_is_rejected_before_receipt_verification(self):
        receipt = self.make_receipt()
        changed = copy.deepcopy(self.request)
        changed["query_label"] = "different intention"

        with self.assertRaisesRegex(CompletionReceiptError, "request digest mismatch"):
            self.verify(receipt, request=changed)

    def test_receipt_signature_tampering_is_rejected(self):
        receipt = self.make_receipt()
        receipt["signature"] = ("0" if receipt["signature"][0] != "0" else "1") + receipt["signature"][1:]
        with self.assertRaisesRegex(CompletionReceiptError, "signature verification failed"):
            self.verify(receipt)

    def test_receipt_cannot_be_verified_with_an_untrusted_runner_key(self):
        receipt = self.make_receipt()
        other_key = Ed25519PrivateKey.generate().public_key()
        with self.assertRaisesRegex(CompletionReceiptError, "runner_key_id mismatch"):
            self.verify(receipt, key=other_key)

    def test_runner_identity_must_match_the_authorized_route_event(self):
        receipt = self.make_receipt()
        with self.assertRaisesRegex(CompletionReceiptError, "different runner identity"):
            self.verify(receipt, runner_id="another-runner")

    def test_authorization_event_digest_and_execution_ticket_are_checked(self):
        receipt = self.make_receipt()
        tampered = copy.deepcopy(self.event)
        tampered["details"]["execution_id"] = "urn:sha256:" + "f" * 64
        tampered_core = {key: value for key, value in tampered.items() if key != "event_digest"}
        tampered["event_digest"] = digest(tampered_core)

        with self.assertRaisesRegex(CompletionReceiptError, "ticket formula"):
            self.verify(receipt, event=tampered)

    def test_authorization_event_self_digest_is_checked(self):
        receipt = self.make_receipt()
        tampered = copy.deepcopy(self.event)
        tampered["details"]["runner_id"] = "attacker"
        with self.assertRaisesRegex(CompletionReceiptError, "event digest mismatch"):
            self.verify(receipt, event=tampered)

    def test_wrong_authorization_event_cannot_be_substituted(self):
        receipt = self.make_receipt()
        other = copy.deepcopy(self.event)
        other["sequence"] += 1
        core = {key: value for key, value in other.items() if key != "event_digest"}
        other["event_digest"] = digest(core)
        with self.assertRaisesRegex(CompletionReceiptError, "authorization_event_digest mismatch"):
            self.verify(receipt, event=other)

    def test_receipt_document_matches_json_schema(self):
        receipt = self.make_receipt()
        with open("completion-receipt.schema.json", encoding="utf-8") as stream:
            schema = json.load(stream)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(receipt)

    def test_runner_key_id_is_public_key_fingerprint(self):
        receipt = self.make_receipt()
        self.assertEqual(receipt["runner_key_id"], runner_key_id(self.public_key))
        self.assertTrue(receipt["runner_key_id"].startswith("sha256:"))

    def test_execution_id_matches_existing_route_epoch_formula(self):
        self.assertEqual(
            self.event["details"]["execution_id"],
            derive_execution_id(
                self.epoch_id,
                self.request["attempt_id"],
                self.request["request_digest"],
            ),
        )


if __name__ == "__main__":
    unittest.main()
