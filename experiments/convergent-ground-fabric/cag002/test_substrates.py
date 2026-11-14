"""CAG-002: offline verifier and trace tamper negatives."""
from __future__ import annotations

import copy
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import substrates as s

cag = s.cag


def fixture():
    source, blue, amber = s.route_packets()
    jet = blue["packets"] + [blue["packets"][0]]
    peer = [amber["packets"][0], amber["packets"][0], amber["packets"][1],
            amber["packets"][2], amber["packets"][2]]
    trace = {
        "schema": s.SCHEMA,
        "source_digest": source["bundle_digest"],
        "blue_digest": blue["bundle_digest"],
        "amber_digest": amber["bundle_digest"],
        "jetstream": {
            "server": "nats-server JetStream", "file_storage": True,
            "producer_disconnected_before_consumer": True,
            "durable_consumer_reconnected": True,
            "redelivery_after_missing_ack": True,
            "acknowledged_count": 4,
        },
        "libp2p": {
            "protocol": "/cag002/ground-packet/1.0.0",
            "listener_restarted": True,
            "peer_id_rotated": True,
            "lost_transport_ack_retried": True,
            "persisted_duplicate_seen": True,
        },
    }
    return source, blue, amber, trace, jet, peer


class DualSubstrateVerifierTests(unittest.TestCase):
    def test_exact_semantics_across_two_transport_orders(self):
        result = s.reconstruct(*fixture())
        self.assertEqual(result["status"], "two_real_substrates_local_reconstruction")
        self.assertEqual(result["reference"]["value"], 44)
        self.assertEqual(len(result["cases"]), 2)
        self.assertEqual(
            [x["status_after_route"] for x in result["cases"]],
            [["unknown_dependency", "locally_reconstructed_pure_result"]] * 2)
        self.assertEqual({x["unique_packet_count"] for x in result["cases"]}, {5})

    def test_missing_route_does_not_establish_result(self):
        source, blue, amber, trace, jet, peer = fixture()
        with self.assertRaisesRegex(s.SubstrateError, "route delivery incomplete"):
            s.reconstruct(source, blue, amber, trace, jet, peer[:2])

    def test_corrupt_content_rejected_even_when_wrapped(self):
        source, blue, amber, trace, jet, peer = fixture()
        forged = cag.packet("left", "add", ["seed"], 8)
        peer[2] = forged
        with self.assertRaisesRegex(s.SubstrateError, "absent from authorized source projection"):
            s.reconstruct(source, blue, amber, trace, jet, peer)

    def test_delivery_ack_is_not_sufficient_for_result(self):
        source, blue, amber, trace, jet, peer = fixture()
        trace["jetstream"]["redelivery_after_missing_ack"] = False
        with self.assertRaisesRegex(s.SubstrateError, "durability/redelivery"):
            s.reconstruct(source, blue, amber, trace, jet, peer)

    def test_libp2p_restart_is_observable_but_not_authority(self):
        source, blue, amber, trace, jet, peer = fixture()
        trace["libp2p"]["peer_id_rotated"] = False
        with self.assertRaisesRegex(s.SubstrateError, "reconnect/ACK-loss"):
            s.reconstruct(source, blue, amber, trace, jet, peer)

    def test_route_digest_mismatch_and_extra_packet_rejected(self):
        source, blue, amber, trace, jet, peer = fixture()
        bad = copy.deepcopy(trace)
        bad["blue_digest"] = "f" * 64
        with self.assertRaisesRegex(s.SubstrateError, "wrong route digest"):
            s.reconstruct(source, blue, amber, bad, jet, peer)
        jet.append(cag.packet("malicious", "constant", [], 100))
        with self.assertRaisesRegex(s.SubstrateError, "absent from authorized source"):
            s.reconstruct(source, blue, amber, trace, jet, peer)

    def test_packet_duplicate_is_idempotent_to_semantic_result(self):
        source, blue, amber, trace, jet, peer = fixture()
        a = s.reconstruct(source, blue, amber, trace, jet, peer)
        jet.extend(jet[:2])
        peer.extend(peer[:1])
        b = s.reconstruct(source, blue, amber, trace, jet, peer)
        self.assertEqual(a["reference"], b["reference"])
        self.assertEqual([x["final"] for x in a["cases"]],
                         [x["final"] for x in b["cases"]])

    def test_exact_route_capture_hash_changes_under_duplicate_replay(self):
        source, blue, amber, trace, jet, peer = fixture()
        first = s.reconstruct(source, blue, amber, trace, jet, peer)
        self.assertEqual(set(first["captured_route_files_sha256"]), {"jetstream", "libp2p"})
        jet.append(jet[0])
        second = s.reconstruct(source, blue, amber, trace, jet, peer)
        self.assertNotEqual(first["captured_route_files_sha256"]["jetstream"],
                            second["captured_route_files_sha256"]["jetstream"])
        self.assertEqual(first["reference"], second["reference"])

    def test_noncanonical_route_capture_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "arrivals.jsonl"
            path.write_bytes(b' { "schema": "fake" }\\n')
            with self.assertRaisesRegex(s.SubstrateError, "canonical JSONL"):
                s.read_jsonl(path)

    def test_offline_verifier_rejects_altered_report(self):
        source, blue, amber, trace, jet, peer = fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            for name, obj in (
                ("source.json", source), ("blue-route.json", blue),
                ("amber-route.json", amber), ("transport-trace.json", trace)):
                cag.write(root / name, obj)
            s.record_bytes(root / "jetstream-arrivals.jsonl", jet)
            s.record_bytes(root / "libp2p-spool.jsonl", peer)
            report = s.reconstruct(source, blue, amber, trace, jet, peer)
            cag.write(root / "report.json", report)
            self.assertEqual(s.offline_verify(root), report)
            report["reference"]["value"] = 81
            cag.write(root / "report.json", report)
            with self.assertRaisesRegex(s.SubstrateError, "different report"):
                s.offline_verify(root)


if __name__ == "__main__":
    unittest.main()
