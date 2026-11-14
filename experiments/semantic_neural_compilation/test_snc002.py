"""SNC-002: adversarial source-only neural transfer and independent receiver tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

from independent_certificate_checker import CertificateError, hash_bytes
from compiler import compile_semantics
from semantic_transit import (
    CHUNK, MAX_DOCUMENT, Decoder, TransitRejected, SCHEMA,
    canonical, digest, make_frames, verify_received, tls_context,
    SENDER, RECEIVER,
)
from run_semantic_transit import test_certificates as fixture_certificates
from mailcpu.mtls_transport import (
    MutualTLSTransportError, accept_mutual_tls, connect_mutual_tls,
)
from mailcpu.socket_transport import SocketTransport

EXAMPLES = json.loads((Path(__file__).parent / "examples.json").read_text())


def payload(name: str = "triangular_bump") -> bytes:
    return canonical({
        "schema": SCHEMA, "kind": "semantic",
        "semantic_atlas": EXAMPLES[name],
    })


def parameters(name: str = "triangular_bump") -> bytes:
    return canonical({
        "schema": SCHEMA, "kind": "parameters",
        "generated_certificate":
            compile_semantics(EXAMPLES[name])["generated_certificate"],
    })


class SNC002WireTests(unittest.TestCase):
    def test_source_only_contains_no_neural_weights_or_proof(self):
        data = json.loads(payload())
        self.assertEqual(set(data), {"schema", "kind", "semantic_atlas"})
        self.assertNotIn(b'"weights"', payload())
        self.assertNotIn(b'"generated_certificate"', payload())

    def test_whole_reliable_wire_roundtrip_both_modes(self):
        for mode, raw in (("semantic", payload()), ("parameters", parameters())):
            with self.subTest(mode=mode):
                frames = make_frames(raw, mode=mode)
                receiver = Decoder()
                for frame in frames:
                    receiver.ingest(frame)
                self.assertTrue(receiver.completed)
                self.assertEqual(receiver.document, raw)
                self.assertEqual(receiver.manifest["kind"], mode)
                self.assertEqual(receiver.frames_seen, len(frames))
                verdict = verify_received(
                    receiver.document, kind=mode,
                    expected_semantic_sha256=hash_bytes(EXAMPLES["triangular_bump"]))
                self.assertEqual(
                    verdict["status"], "exact-all-real-semantic-equivalence-verified")

    def test_rehashed_different_semantics_rejected_by_receiver_policy(self):
        altered = json.loads(payload())
        altered["semantic_atlas"][1]["affines"][0][0] = "2"
        altered["semantic_atlas"][1]["affines"][0][1] = "0"
        # Change the following segment to maintain continuity.
        altered["semantic_atlas"][2]["affines"][0] = ["-2", "2"]
        altered["semantic_atlas"][3]["affines"][0] = ["0", "0"]
        changed = canonical(altered)
        with self.assertRaises((CertificateError, TransitRejected, ValueError)):
            verify_received(
                changed, kind="semantic",
                expected_semantic_sha256=hash_bytes(EXAMPLES["triangular_bump"]))

    def test_modified_parameter_certificate_rejected_even_if_rehashed(self):
        from independent_certificate_checker import hash_bytes
        data = json.loads(parameters())
        net = data["generated_certificate"]["network"]
        net["layers"][1]["weights"][0][1] = "99"
        data["generated_certificate"]["network_sha256"] = hash_bytes(net)
        with self.assertRaises((CertificateError, TransitRejected)):
            verify_received(
                canonical(data), kind="parameters",
                expected_semantic_sha256=hash_bytes(EXAMPLES["triangular_bump"]))

    def test_no_acceptance_on_missing_or_duplicate_final_frames(self):
        frames = make_frames(payload(), mode="semantic")
        receiver = Decoder()
        for frame in frames[:-1]:
            receiver.ingest(frame)
        self.assertFalse(receiver.completed)
        self.assertEqual(receiver.document, payload())
        with self.assertRaisesRegex(TransitRejected, "chunk|finish|wrong"):
            receiver.ingest({"phase": "finish", "manifest_sha256": "0" * 64})
        receiver.ingest(frames[-1])
        with self.assertRaisesRegex(TransitRejected, "post-finish"):
            receiver.ingest(frames[-1])

    def test_corrupt_or_reordered_chunks_refused(self):
        frames = list(make_frames(payload(), mode="semantic"))
        receiver = Decoder()
        receiver.ingest(frames[0])
        mutated = deepcopy(frames[1])
        mutated["hex"] = "00" * (len(mutated["hex"]) // 2)
        with self.assertRaisesRegex(TransitRejected, "digest"):
            receiver.ingest(mutated)
        receiver = Decoder()
        receiver.ingest(frames[0])
        with self.assertRaisesRegex(TransitRejected, "out-of-order"):
            receiver.ingest({"phase": "chunk", "index": 2, "hex": frames[1]["hex"]})

    def test_malformed_or_oversized_manifest_is_rejected(self):
        frames = make_frames(payload(), mode="semantic")
        for field, changed in (("byte_length", MAX_DOCUMENT + 1),
                               ("chunks", 0), ("schema", "wrong"),
                               ("kind", "unknown"), ("sha256", "bad")):
            with self.subTest(field=field):
                first = deepcopy(frames[0])
                first["manifest"][field] = changed
                with self.assertRaises(TransitRejected):
                    Decoder().ingest(first)

    def test_noncanonical_payload_and_kind_substitution_are_rejected(self):
        with self.assertRaises(TransitRejected):
            make_frames(payload(), mode="parameters")
        with self.assertRaises((CertificateError, TransitRejected)):
            make_frames(b'{"schema":"x", "kind":"semantic"}\n', mode="semantic")
        with self.assertRaises((CertificateError, TransitRejected)):
            verify_received(
                canonical({"schema": SCHEMA, "kind": "semantic", "semantic_atlas": []}),
                kind="semantic", expected_semantic_sha256="0" * 64)

    def test_multi_chunk_partial_transfer_cannot_finish(self):
        source = canonical({"schema": SCHEMA, "kind": "semantic",
                            "semantic_atlas": EXAMPLES["triangular_bump"],
                            "padding": "x" * (CHUNK * 2)})
        # This is protocol-visible but NOT a semantically valid payload.
        # Framing must support independent assembly without promoting it.
        with self.assertRaises(TransitRejected):
            make_frames(source, mode="semantic")
        source = payload()
        frames = make_frames(source, mode="semantic")
        dec = Decoder()
        dec.ingest(frames[0])
        with self.assertRaises(TransitRejected):
            dec.ingest(frames[-1])

    def test_receiver_requires_source_identity(self):
        with self.assertRaises(TransitRejected):
            verify_received(payload(), kind="semantic", expected_semantic_sha256="")
        with self.assertRaises(CertificateError):
            verify_received(payload(), kind="semantic", expected_semantic_sha256="0" * 64)


@unittest.skipUnless(shutil.which("openssl"), "openssl CLI required for local mTLS fixture")
class SNC002TLSIdentityTests(unittest.TestCase):
    def test_wrong_peer_identity_rejected_even_with_valid_ca(self):
        with tempfile.TemporaryDirectory(prefix="snc002-identity-") as tmp:
            files = fixture_certificates(Path(tmp))
            listener = SocketTransport.listen("127.0.0.1", 0)
            outcomes: list[str] = []
            def receiver():
                try:
                    socket = accept_mutual_tls(
                        listener, RECEIVER, SENDER,
                        tls_context(
                            files["ca"], files["server_cert"],
                            files["server_key"], server=True),
                        expected_peer_dns="wrong-sender",
                    )
                    socket.close()
                    outcomes.append("ACCEPTED")
                except MutualTLSTransportError:
                    outcomes.append("REJECTED")
            thread = threading.Thread(target=receiver, daemon=True)
            thread.start()
            try:
                transport = connect_mutual_tls(
                    "127.0.0.1", listener.getsockname()[1],
                    SENDER, RECEIVER,
                    tls_context(files["ca"], files["client_cert"],
                                files["client_key"], server=False),
                    server_hostname=RECEIVER, timeout=8,
                )
                transport.close()
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
                self.assertEqual(outcomes, ["REJECTED"])
            finally:
                listener.close()


if __name__ == "__main__":
    unittest.main()
