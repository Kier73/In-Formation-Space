"""Adversarial bounds plus actual E-CPU mTLS/ReliableChannel framing tests.

These tests deliberately use synthetic bytes, NOT issuer attestations. The
post-merge workflow calls the real recipient's Sigstore proof verifier.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import threading
from unittest import TestCase, skipUnless

from mailcpu.mtls_transport import accept_mutual_tls, MutualTLSTransportError
from mailcpu.socket_transport import SocketTransport

import ecpu_proof_transit as bridge
from ecpu_proof_transit_demo import _certs


class ProofWireProtocolTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = {}
        for i, kind in enumerate(bridge.SUBJECTS):
            data = bytes([i + 30]) * (2 + 5 * i)
            if kind == "public_key":
                data += b"\n"
            path = self.root / f"{kind}.blob"
            path.write_bytes(data)
            self.paths[kind] = path

    def frames(self):
        return bridge.make_frames(self.paths)

    def test_six_subjects_roundtrip_including_zero_trust_of_transport(self):
        decoder = bridge.ProofStreamDecoder()
        frames = self.frames()
        for frame in frames:
            decoder.ingest(frame)
        self.assertTrue(decoder.finished)
        self.assertEqual(decoder.frames_seen, len(frames))
        with tempfile.TemporaryDirectory() as folder:
            received = decoder.materialize(Path(folder))
            for kind in bridge.SUBJECTS:
                self.assertEqual(received[kind].read_bytes(), self.paths[kind].read_bytes())

    def test_missing_or_extra_subject_rejected(self):
        missing = dict(self.paths)
        missing.pop(bridge.SUBJECTS[0])
        with self.assertRaisesRegex(bridge.ProofTransitError, "six"):
            bridge.make_frames(missing)
        bogus = dict(self.paths, forged=self.paths["runner"])
        with self.assertRaisesRegex(bridge.ProofTransitError, "six"):
            bridge.make_frames(bogus)

    def test_source_symlink_rejected(self):
        src = self.paths["checker"]
        link = self.root / "checker-link"
        link.symlink_to(src)
        self.paths["checker"] = link
        with self.assertRaisesRegex(bridge.ProofTransitError, "symlink"):
            bridge.make_frames(self.paths)

    def test_cannot_promote_incomplete_transfer(self):
        decoder = bridge.ProofStreamDecoder()
        for frame in self.frames()[:-1]:
            decoder.ingest(frame)
        with self.assertRaisesRegex(bridge.ProofTransitError, "incomplete"):
            decoder.materialize(self.root)

    def test_byte_tampering_rejected_even_with_same_manifest(self):
        frames = list(self.frames())
        mutated = deepcopy(frames[1])
        mutated["hex"] = "00" * (len(mutated["hex"]) // 2)
        frames[1] = mutated
        decoder = bridge.ProofStreamDecoder()
        with self.assertRaisesRegex(bridge.ProofTransitError, "digest mismatch"):
            for frame in frames:
                decoder.ingest(frame)

    def test_out_of_order_or_duplicate_chunks_rejected(self):
        frames = self.frames()
        decoder = bridge.ProofStreamDecoder()
        decoder.ingest(frames[0])
        decoder.ingest(frames[1])
        with self.assertRaisesRegex(bridge.ProofTransitError, "reordered|duplicate|substituted"):
            decoder.ingest(frames[1])

    def test_wrong_manifest_total_or_over_limit_rejected(self):
        for edit in ("total", "limit", "unknown", "chunks"):
            frames = list(deepcopy(self.frames()))
            manifest = frames[0]["manifest"]
            if edit == "total":
                manifest["total_bytes"] += 1
            elif edit == "limit":
                manifest["artifacts"]["runner"]["size"] = bridge.MAX_SUBJECT + 1
            elif edit == "unknown":
                manifest["artifacts"]["unexpected"] = manifest["artifacts"]["runner"]
            else:
                manifest["artifacts"]["runner"]["chunks"] = 10
            with self.subTest(edit=edit), self.assertRaises(bridge.ProofTransitError):
                bridge.ProofStreamDecoder().ingest(frames[0])

    def test_finish_does_not_allow_incomplete_or_extra_frames(self):
        frames = self.frames()
        decoder = bridge.ProofStreamDecoder()
        decoder.ingest(frames[0])
        with self.assertRaises(bridge.ProofTransitError):
            decoder.ingest(frames[-1])
        decoder = bridge.ProofStreamDecoder()
        for frame in frames:
            decoder.ingest(frame)
        with self.assertRaisesRegex(bridge.ProofTransitError, "post-finish"):
            decoder.ingest(frames[-1])

    def test_noncanonical_hex_or_malformed_frame_rejected(self):
        for change in ("upper", "bad", "extra"):
            frames = list(deepcopy(self.frames()))
            if change == "upper":
                frames[1]["hex"] = "AA"
            elif change == "bad":
                frames[1]["hex"] = "0G"
            else:
                frames[1]["unexpected"] = True
            decoder = bridge.ProofStreamDecoder()
            decoder.ingest(frames[0])
            with self.subTest(change=change), self.assertRaises(bridge.ProofTransitError):
                decoder.ingest(frames[1])


@skipUnless(shutil.which("openssl"), "OpenSSL CLI required for ephemeral mTLS fixture")
class LiveTransportTests(ProofWireProtocolTests):
    def test_actual_mutual_tls_reliable_channel_carries_exact_proof_bytes(self):
        certs = _certs(self.root)
        listener = SocketTransport.listen("127.0.0.1", 0)
        decoder = bridge.ProofStreamDecoder()
        errors = []
        peer = {}

        def server():
            transport = None
            try:
                transport = accept_mutual_tls(
                    listener, bridge.DESTINATION, bridge.ORIGIN,
                    bridge._ctx(certs["ca"], certs["server_cert"], certs["server_key"], server=True),
                    expected_peer_dns=bridge.ORIGIN,
                )
                peer["tls_version"] = transport.socket.version()
                channel = bridge._proof_channels(transport, serving=True)
                import time
                deadline = time.monotonic() + 15
                while not decoder.finished and time.monotonic() < deadline:
                    result = channel.receive(commit=lambda _seq, payload: decoder.ingest(payload))
                    if result is None:
                        time.sleep(.003)
                if not decoder.finished:
                    raise AssertionError("timed out receiving complete reliable proof")
                time.sleep(.07)
            except BaseException as exc:
                errors.append(exc)
            finally:
                if transport is not None:
                    transport.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        try:
            sent = bridge.send_frames(
                "127.0.0.1", listener.getsockname()[1], self.paths,
                ca=certs["ca"], cert=certs["client_cert"],
                key=certs["client_key"], budget=12,
            )
            thread.join(timeout=15)
            self.assertFalse(thread.is_alive())
            self.assertFalse(errors, repr(errors))
            self.assertTrue(decoder.finished)
            self.assertEqual(sent["frames_sent"], decoder.frames_seen)
            self.assertIn(peer["tls_version"], ("TLSv1.2", "TLSv1.3"))
            with tempfile.TemporaryDirectory() as received_folder:
                received = decoder.materialize(Path(received_folder))
                self.assertEqual(
                    {k: p.read_bytes() for k, p in received.items()},
                    {k: p.read_bytes() for k, p in self.paths.items()},
                )
        finally:
            listener.close()

    def test_mtls_rejects_wrong_expected_client_dns(self):
        certs = _certs(self.root)
        listener = SocketTransport.listen("127.0.0.1", 0)
        outcomes = []

        def server():
            try:
                accept_mutual_tls(
                    listener, bridge.DESTINATION, bridge.ORIGIN,
                    bridge._ctx(certs["ca"], certs["server_cert"], certs["server_key"], server=True),
                    expected_peer_dns="unauthorized-peer",
                )
                outcomes.append("UNEXPECTED_ACCEPT")
            except MutualTLSTransportError:
                outcomes.append("REJECTED")
        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        try:
            from mailcpu.mtls_transport import connect_mutual_tls
            client = connect_mutual_tls(
                "127.0.0.1", listener.getsockname()[1],
                bridge.ORIGIN, bridge.DESTINATION,
                bridge._ctx(certs["ca"], certs["client_cert"], certs["client_key"], server=False),
                server_hostname=bridge.DESTINATION,
            )
            client.close()
            thread.join(timeout=10)
            self.assertEqual(outcomes, ["REJECTED"])
        finally:
            listener.close()


if __name__ == "__main__":
    import unittest
    unittest.main()
