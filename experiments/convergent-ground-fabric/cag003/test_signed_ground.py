"""CAG-003 signed publisher contracts and receiver-independent finite tests.

Uses synthetic CAG-002 captures. Neither suite claims physical network transport.
The hosted integration separately runs real JetStream + libp2p and the E-CPU/VGI
receiver.
"""
from __future__ import annotations

import copy
import pathlib
import sys
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import signed_ground as sg
import admission as a
cag = sg.cag
c2 = sg.c2


def fixture(root: pathlib.Path) -> None:
    source = cag.source_bundle()
    blue = cag.route_bundle(source, "blue")
    amber = cag.route_bundle(source, "amber")
    jet = blue["packets"] + [blue["packets"][0]]
    peer = [amber["packets"][0], amber["packets"][0], amber["packets"][1],
            amber["packets"][2], amber["packets"][2]]
    trace = {
        "schema": c2.SCHEMA, "source_digest": source["bundle_digest"],
        "blue_digest": blue["bundle_digest"], "amber_digest": amber["bundle_digest"],
        "jetstream": {
            "server": "nats-server JetStream", "file_storage": True,
            "producer_disconnected_before_consumer": True,
            "durable_consumer_reconnected": True,
            "redelivery_after_missing_ack": True,
            "acknowledged_count": 4,
        },
        "libp2p": {
            "protocol": "/cag002/ground-packet/1.0.0",
            "listener_restarted": True, "peer_id_rotated": True,
            "lost_transport_ack_retried": True, "persisted_duplicate_seen": True,
        },
    }
    report = c2.reconstruct(source, blue, amber, trace, jet, peer)
    for name, doc in (
        ("source.json", source), ("blue-route.json", blue),
        ("amber-route.json", amber), ("transport-trace.json", trace),
        ("report.json", report),
    ):
        cag.write(root / name, doc)
    c2.record_bytes(root / "jetstream-arrivals.jsonl", jet)
    c2.record_bytes(root / "libp2p-spool.jsonl", peer)


class SignedPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        fixture(self.root)
        self.key = Ed25519PrivateKey.generate()
        self.envelope, self.trust = sg.create_intent(self.root, private=self.key)

    def verify(self, envelope=None, trust=None):
        return sg.verify_intent(
            self.root,
            self.envelope if envelope is None else envelope,
            self.trust if trust is None else trust,
        )

    def test_ed25519_signature_and_full_transcript_provenance(self):
        status = self.verify()
        self.assertEqual(status["status"], "signed_publisher_commitment_verified")
        self.assertEqual(status["input_sha256"],
                         self.envelope["statement"]["input_sha256"])
        self.assertEqual(set(status["input_sha256"]), set(sg.INPUT_FILES))

    def test_manifest_tamper_with_unchanged_signature_rejected(self):
        forged = copy.deepcopy(self.envelope)
        forged["statement"]["target"] = "left"
        with self.assertRaises(sg.SignedGroundError):
            self.verify(envelope=forged)

    def test_reforged_manifest_with_untrusted_signer_is_rejected(self):
        attacker = Ed25519PrivateKey.generate()
        forged = copy.deepcopy(self.envelope)
        forged["signature_b64"] = sg.encode(
            attacker.sign(sg.canonical(forged["statement"]))
        )
        with self.assertRaisesRegex(sg.SignedGroundError, "signature invalid"):
            self.verify(envelope=forged)

    def test_replacement_public_key_cannot_be_silent(self):
        forged = copy.deepcopy(self.trust)
        forged["public_key_b64"] = sg.encode(
            Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        )
        with self.assertRaisesRegex(sg.SignedGroundError, "fingerprint"):
            self.verify(trust=forged)

    def test_untrusted_publisher_scope_rejected(self):
        for field, value in (
            ("publisher", "anyone"), ("trust_epoch", 2),
            ("trusted_workflow_ref", "wrong/workflow.yml@refs/heads/main"),
            ("workload_contract", "execute-arbitrary-process"),
        ):
            with self.subTest(field=field):
                forged = copy.deepcopy(self.trust)
                forged[field] = value
                with self.assertRaises(sg.SignedGroundError):
                    self.verify(trust=forged)

    def test_trust_record_does_not_self_authorize_origin(self):
        self.assertIn("ephemeral", self.trust["limit"])
        self.assertEqual(self.trust["trusted_workflow_ref"], sg.WORKFLOW)
        self.assertNotIn("private_key", str(self.trust).lower())

    def test_signed_source_prevents_recomputed_wrapper_forgery(self):
        source = cag.read(self.root / "source.json")
        changed = copy.deepcopy(source)
        changed["target"] = "left"
        changed["bundle_digest"] = cag.sha(
            {k:v for k,v in changed.items() if k != "bundle_digest"})
        cag.write(self.root / "source.json", changed)
        with self.assertRaisesRegex(sg.SignedGroundError, "differs"):
            self.verify()

    def test_delivered_duplicate_history_is_exactly_bound(self):
        path = self.root / "jetstream-arrivals.jsonl"
        path.write_bytes(path.read_bytes() + path.read_bytes().splitlines()[0] + b"\n")
        with self.assertRaisesRegex(sg.SignedGroundError, "differs"):
            self.verify()

    def test_unlisted_or_missing_file_hash_refused(self):
        for mutation in ("remove", "add"):
            forged = copy.deepcopy(self.envelope)
            if mutation == "remove":
                forged["statement"]["input_sha256"].pop("report.json")
            else:
                forged["statement"]["input_sha256"]["rogue.py"] = "f" * 64
            forged["signature_b64"] = sg.encode(
                self.key.sign(sg.canonical(forged["statement"]))
            )
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                sg.SignedGroundError, "every input"
            ):
                self.verify(envelope=forged)

    def test_wrong_key_or_signature_bytes_rejected(self):
        forged = copy.deepcopy(self.envelope)
        forged["signature_b64"] = sg.encode(b"a" * 64)
        with self.assertRaisesRegex(sg.SignedGroundError, "signature invalid"):
            self.verify(envelope=forged)

    def test_input_reconstruction_requires_both_routes(self):
        value = a.compute(a.source_inputs(self.root))
        self.assertEqual(value["value"], 44)
        self.assertEqual(value["cag002_report_digest"],
                         self.envelope["statement"]["report_digest"])

    def test_signature_does_not_change_under_independent_reparse(self):
        for file in sg.INPUT_FILES:
            self.assertEqual(
                self.envelope["statement"]["input_sha256"][file],
                sg.sha((self.root / file).read_bytes()),
            )


if __name__ == "__main__":
    unittest.main()
