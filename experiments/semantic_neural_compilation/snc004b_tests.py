"""SNC-004B: framed E-CPU capsule delivery and independent host-authority tests."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from independent_certificate_checker import hash_bytes
from federated_capsule import export_from_host
from federated_auditor import audit
from persistent_host import PersistentSemanticHost, POLICY_SCHEMA, canonical, HostRejected
from snc004b_identity import make_identity, inspect_peer, make_endpoint, inspect_endpoint
from snc004b_live import (
    CapsuleDecoder, WireRejected, addressing, certificate_sha256,
    make_frames, verdict, SCHEMA,
)

EXAMPLES = json.loads((Path(__file__).parent / "examples.json").read_text())
NONCE = "1" * 32


def fixture(root: Path):
    source = EXAMPLES["clamp_0_1"]
    p = root / "producer.json"
    q = root / "receiver.json"
    p.write_bytes(canonical({"schema": POLICY_SCHEMA,
                             "models": {"source_clamp": hash_bytes(source)}}))
    q.write_bytes(canonical({"schema": POLICY_SCHEMA,
                             "models": {"clamp": hash_bytes(source)}}))
    producer = PersistentSemanticHost(root / "producer.sqlite3", p)
    producer.observe(model="source_clamp", coordinate="1/2",
                     request_id="seed1", source=source)
    recipient = PersistentSemanticHost(root / "recipient.sqlite3", q)
    return producer, recipient, export_from_host(producer, "source_clamp"), q


class SNC004bContract(unittest.TestCase):
    def test_canonical_chunked_capsule_and_finite_frame_commit(self):
        with TemporaryDirectory() as raw:
            _, host, capsule, _ = fixture(Path(raw))
            frames = make_frames(capsule, model="clamp", coordinate="3/4",
                                 request_id="observed1", nonce=NONCE)
            self.assertEqual(frames[0]["manifest"]["schema"], SCHEMA)
            dec = CapsuleDecoder()
            for frame in frames:
                dec.ingest(frame)
            self.assertTrue(dec.complete)
            self.assertEqual(dec.body, capsule)
            self.assertEqual(dec.frames, len(frames))
            accepted = verdict(host, body=dec.body, manifest=dec.manifest)
            self.assertTrue(accepted["accepted"])
            self.assertEqual(accepted["result"]["observation"]["receipt"]["outputs"],
                             ["3/4"])
            self.assertFalse(accepted["result"]["import"]["external_execution_authorized"])
            report = audit(
                body=capsule,
                receiver_report=canonical(accepted["result"]),
                expected_source=EXAMPLES["clamp_0_1"],
                expected_model="clamp", expected_coordinate="3/4",
                expected_request_id="observed1",
            )
            self.assertEqual(report["status"],
                             "independent-full-domain-and-observation-reconstruction")

    def test_duplicate_final_and_missing_final_never_admit(self):
        with TemporaryDirectory() as raw:
            _, host, capsule, _ = fixture(Path(raw))
            frames = make_frames(capsule, model="clamp", coordinate="3/4",
                                 request_id="r1", nonce=NONCE)
            dec = CapsuleDecoder()
            for frame in frames[:-1]:
                dec.ingest(frame)
            self.assertFalse(dec.complete)
            self.assertEqual(host.count("clamp"), (0, 0))
            with self.assertRaises(WireRejected):
                dec.ingest({"phase": "finish", "manifest_sha256": "f" * 64})
            dec.ingest(frames[-1])
            with self.assertRaises(WireRejected):
                dec.ingest(frames[-1])

    def test_reordered_or_corrupted_chunk_fails_closed(self):
        raw = b'{"x":"test"}\n'
        frames = make_frames(raw, model="clamp", coordinate="1",
                             request_id="test", nonce=NONCE)
        dec = CapsuleDecoder()
        dec.ingest(frames[0])
        with self.assertRaises(WireRejected):
            dec.ingest({"phase": "chunk", "index": 1, "hex": frames[1]["hex"]})
        dec = CapsuleDecoder()
        dec.ingest(frames[0])
        bad = deepcopy(frames[1])
        bad["hex"] = "00" * (len(bad["hex"]) // 2)
        with self.assertRaisesRegex(WireRejected, "integrity"):
            dec.ingest(bad)

    def test_wrong_session_nonce_manifest_and_unbounded_body_refused(self):
        frames = make_frames(b"ok", model="clamp", coordinate="1",
                             request_id="a", nonce=NONCE)
        for field, bad in (
            ("nonce", "bad"), ("schema", "other"),
            ("byte_length", 999_999), ("sha256", "x" * 64),
            ("chunks", 200), ("model", "../host")
        ):
            with self.subTest(field=field):
                f = deepcopy(frames[0])
                f["manifest"][field] = bad
                with self.assertRaises((WireRejected, ValueError)):
                    CapsuleDecoder().ingest(f)

    def test_semantic_denial_is_an_application_response_not_proof_admission(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            _, host, capsule, policy = fixture(root)
            policy.write_bytes(canonical({
                "schema": POLICY_SCHEMA,
                "models": {"clamp": hash_bytes(EXAMPLES["identity"])},
            }))
            manifest = make_frames(capsule, model="clamp", coordinate="3/4",
                                   request_id="failure", nonce=NONCE)[0]["manifest"]
            response = verdict(host, body=capsule, manifest=manifest)
            self.assertFalse(response["accepted"])
            self.assertEqual(response["nonce"], NONCE)
            self.assertEqual(host.count("clamp"), (0, 0))

    def test_rehashed_neural_weights_denied_even_over_authenticated_channel(self):
        with TemporaryDirectory() as raw:
            _, host, capsule, _ = fixture(Path(raw))
            altered = json.loads(capsule)
            network = altered["snc001_capsule"]["generated_certificate"]["network"]
            network["layers"][1]["weights"][0][0] = "99"
            altered["snc001_capsule"]["generated_certificate"]["network_sha256"] = hash_bytes(network)
            altered["generated_network_sha256"] = hash_bytes(network)
            body = canonical(altered)
            manifest = make_frames(body, model="clamp", coordinate="3/4",
                                   request_id="attacker", nonce=NONCE)[0]["manifest"]
            response = verdict(host, body=body, manifest=manifest)
            self.assertFalse(response["accepted"])
            self.assertEqual(host.count("clamp"), (0, 0))

    def test_receiver_owned_alias_cannot_be_selected_by_producer_policy(self):
        with TemporaryDirectory() as raw:
            _, host, capsule, _ = fixture(Path(raw))
            manifest = make_frames(capsule, model="source_clamp",
                                   coordinate="3/4", request_id="bad", nonce=NONCE)[0]["manifest"]
            result = verdict(host, body=capsule, manifest=manifest)
            self.assertFalse(result["accepted"])

    def test_source_pins_require_unique_canonical_keys(self):
        for bad in ("", "bad token", "a" * 65, "x/../y"):
            with self.subTest(bad=bad), self.assertRaises(WireRejected):
                make_frames(b"abc", model="clamp",
                            coordinate="1", request_id=bad, nonce=NONCE)
        with self.assertRaises(WireRejected):
            make_frames(b"abc", model="clamp", coordinate="1",
                        request_id="good", nonce="000")

    def test_overlay_address_has_no_public_wildcard_or_loopback_fallback(self):
        self.assertEqual(addressing("100.64.1.2", overlay=True), "100.64.1.2")
        self.assertEqual(addressing("127.0.0.1", overlay=False), "127.0.0.1")
        for addr in ("0.0.0.0", "127.0.0.1", "8.8.8.8",
                     "::1", "100.128.0.1", "example.com"):
            with self.subTest(addr=addr), self.assertRaises(WireRejected):
                addressing(addr, overlay=True)
        for addr in ("0.0.0.0", "100.64.1.2", "8.8.8.8"):
            with self.subTest(addr=addr), self.assertRaises(WireRejected):
                addressing(addr, overlay=False)

    def test_multi_chunk_assembly_and_partial_tail(self):
        body = b"a" * 20_001
        frames = make_frames(body, model="clamp",
                             coordinate="1/4", request_id="multi", nonce=NONCE)
        self.assertEqual(len(frames), 5)
        dec = CapsuleDecoder()
        for frame in frames[:2]:
            dec.ingest(frame)
        with self.assertRaises(WireRejected):
            dec.ingest(frames[-1])
        dec = CapsuleDecoder()
        for frame in frames:
            dec.ingest(frame)
        self.assertTrue(dec.complete)
        self.assertEqual(dec.body, body)

    def test_application_commit_duplicate_request_matches_durable_receipt(self):
        with TemporaryDirectory() as raw:
            _, host, capsule, _ = fixture(Path(raw))
            man = make_frames(capsule, model="clamp", coordinate="1/2",
                              request_id="same", nonce=NONCE)[0]["manifest"]
            first = verdict(host, body=capsule, manifest=man)
            second = verdict(host, body=capsule, manifest=man)
            self.assertTrue(first["accepted"])
            self.assertTrue(second["accepted"])
            self.assertEqual(second["result"]["observation"]["disposition"],
                             "idempotent-replay")
            self.assertEqual(
                first["result"]["observation"]["receipt_sha256"],
                second["result"]["observation"]["receipt_sha256"])
            self.assertEqual(host.count("clamp"), (1, 1))


    def test_bootstrap_exact_run_peer_identity_and_overlay_endpoint(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.dict(os.environ, {
                "GITHUB_RUN_ID": "424242",
                "GITHUB_RUN_ATTEMPT": "3",
            }):
                make_identity(directory=root, role="server")
                record = root / "server-bootstrap.json"
                cert = root / "server-cert.pem"
                self.assertEqual(
                    inspect_peer(cert=cert, record=record, expected_role="server")["role"],
                    "server")
                make_endpoint(directory=root, ip="100.64.5.6")
                self.assertEqual(inspect_endpoint(directory=root), "100.64.5.6")
                with self.assertRaises(HostRejected):
                    inspect_peer(cert=cert, record=record, expected_role="client")
                saved = record.read_bytes()
                forged = json.loads(saved)
                forged["run_attempt"] = "4"
                record.write_bytes(canonical(forged))
                with self.assertRaisesRegex(HostRejected, "wrong run"):
                    inspect_peer(cert=cert, record=record, expected_role="server")
                record.write_bytes(saved)
                endpoint = root / "server-endpoint.json"
                original = endpoint.read_bytes()
                injected = json.loads(original)
                injected["server_ipv4"] = "127.0.0.1"
                endpoint.write_bytes(canonical(injected))
                with self.assertRaises(WireRejected):
                    inspect_endpoint(directory=root)
                endpoint.write_bytes(original)
                with self.assertRaises(WireRejected):
                    make_endpoint(directory=root, ip="8.8.8.8")



if __name__ == "__main__":
    unittest.main()
