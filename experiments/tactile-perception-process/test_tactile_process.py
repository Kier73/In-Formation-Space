"""Reproducible finite probes, independent replay and adversarial fixtures."""
from fractions import Fraction as Q
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import socket
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tactile_process import (ROUTES, action_wire, decode_action, distinguish,
                             emit_report, observe, demonstration, canonical)
from independent_check import verify

DRIVE = ("drive", Q(1, 2))
IDLE = ("idle", Q(0))


class TactileProcessTests(unittest.TestCase):
    def test_transducer_equivalence_not_raw_equality(self):
        actions = [DRIVE, IDLE, ("drive", Q(1, 4))]
        a = emit_report("electrical", actions)
        b = emit_report("hydraulic", actions, "json")
        self.assertEqual(observe(a, "position"), observe(b, "position"))
        self.assertEqual(observe(a, "energy"), observe(b, "energy"))
        self.assertNotEqual([e["raw_sensor"] for e in a["events"]],
                            [e["raw_sensor"] for e in b["events"]])
        self.assertTrue(verify(a)["verified"])
        self.assertTrue(verify(b)["verified"])

    def test_wire_interpretation_and_real_loopback_bytes(self):
        for encoding in ("text", "json"):
            wire = action_wire(*DRIVE, encoding)
            self.assertEqual(decode_action(wire, encoding), DRIVE)
            client, server = socket.socketpair()
            with client, server:
                client.sendall(len(wire).to_bytes(2, "big") + wire)
                header = server.recv(2)
                size = int.from_bytes(header, "big")
                received = bytearray()
                while len(received) < size:
                    received.extend(server.recv(size - len(received)))
                self.assertEqual(decode_action(bytes(received), encoding), DRIVE)
        for malformed in (b"drive:2/1", b"drive:01/2", b"idle:1/2", b"drive:1/0"):
            with self.assertRaises(ValueError):
                decode_action(malformed, "text")
        with self.assertRaises(ValueError):
            decode_action(b'{"d":2,"kind":"drive","n":1,"n":0}', "json")

    def test_independent_energy_reconstruction(self):
        for route in ROUTES:
            for encoding in ("text", "json"):
                evidence = emit_report(route, [DRIVE, DRIVE, IDLE, IDLE], encoding)
                state = verify(evidence)
                self.assertEqual(state["events"], 4)
                for event in evidence["events"]:
                    e = Q(event["energy_in_j"])
                    rhs = Q(event["mechanical_work_j"]) + Q(event["heat_j"]) + Q(event["storage_delta_j"])
                    self.assertEqual(e, rhs)

    def test_hidden_storage_requires_continuation(self):
        one = emit_report("inertial", [DRIVE])
        ideal = emit_report("electrical", [DRIVE])
        self.assertEqual(observe(one, "position"), observe(ideal, "position"))
        probe = distinguish("electrical", "inertial", "position")
        self.assertEqual(probe["status"], "distinguished")
        self.assertEqual(probe["sequence"], ["drive:1/2", "idle:0/1"])
        self.assertEqual(probe["left"], ["1/2", "1/2"])
        self.assertEqual(probe["right"], ["1/2", "3/4"])
        self.assertEqual(distinguish("electrical", "inertial", "energy")["sequence"], ["drive:1/2"])

    def test_relative_observer_contract(self):
        self.assertEqual(distinguish("electrical", "resistive", "position")["status"],
                         "undetermined-within-supplied-horizon")
        self.assertEqual(distinguish("electrical", "resistive", "energy")["sequence"], ["drive:1/2"])
        self.assertEqual(distinguish("electrical", "hydraulic", "position")["status"],
                         "undetermined-within-supplied-horizon")
        self.assertEqual(distinguish("electrical", "hydraulic", "energy")["status"],
                         "undetermined-within-supplied-horizon")

    def test_independent_shortest_probe_oracle(self):
        alphabet = (DRIVE, IDLE)
        for left, right, prop in (("electrical", "inertial", "position"),
                                   ("electrical", "resistive", "energy"),
                                   ("electrical", "hydraulic", "position")):
            actual = distinguish(left, right, prop, max_depth=3)
            witnesses = []
            for length in (1, 2, 3):
                for seq in product(alphabet, repeat=length):
                    if observe(emit_report(left, seq), prop) != observe(emit_report(right, seq), prop):
                        witnesses.append(seq)
            if witnesses:
                self.assertEqual(len(actual["sequence"]), min(map(len, witnesses)))
            else:
                self.assertEqual(actual["status"], "undetermined-within-supplied-horizon")

    def test_resealed_tamper_refused(self):
        original = emit_report("electrical", [DRIVE, IDLE])
        self.assertTrue(verify(original)["verified"])
        for field, forged in (("observed_position_m", "99/1"),
                              ("raw_sensor", "99/1"),
                              ("heat_j", "1/1"),
                              ("state_stored_j", "2/1")):
            report = json.loads(json.dumps(original))
            report["events"][0][field] = forged
            for idx, event in enumerate(report["events"]):
                event["parent_digest"] = report["events"][idx - 1]["digest"] if idx else "0" * 64
                event["digest"] = sha256(canonical({k: v for k, v in event.items() if k != "digest"})).hexdigest()
            report["head_digest"] = report["events"][-1]["digest"]
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify(report)

    def test_missing_or_modified_evidence_refused(self):
        report = emit_report("hydraulic", [DRIVE], "json")
        report["events"][0].pop("input_hex")
        with self.assertRaises(ValueError):
            verify(report)
        report = emit_report("hydraulic", [DRIVE])
        report["events"][0]["digest"] = "0" * 64
        with self.assertRaises(ValueError):
            verify(report)

    def test_deterministic_record(self):
        output = demonstration()
        expected_path = Path(__file__).with_name("results.json")
        with expected_path.open(encoding="utf-8") as handle:
            self.assertEqual(output, json.load(handle))


if __name__ == "__main__":
    unittest.main()
