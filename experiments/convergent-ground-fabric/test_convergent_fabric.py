"""CAG-001: finite convergence, conflict, incompleteness, and tamper tests."""
from __future__ import annotations

import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import convergent_fabric as cag


class ConvergentGroundFabricTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = cag.source_bundle()
        self.blue = cag.route_bundle(self.source, "blue")
        self.amber = cag.route_bundle(self.source, "amber")

    def test_reconstruction_requires_dependencies_from_both_routes(self) -> None:
        for route, bundle in (("blue", self.blue), ("amber", self.amber)):
            receiver = cag.Replica()
            for p in bundle["packets"]:
                receiver.ingest(p, route=route)
            self.assertEqual(receiver.evaluate("final")["status"], "unknown_dependency")
        merged = cag.verify(self.source, self.blue, self.amber)
        self.assertEqual(merged["status"], "multi_route_eventual_convergence")
        self.assertEqual(merged["expected"]["value"], 44)
        self.assertEqual([x["final"]["value"] for x in merged["receivers"]], [44, 44])
        self.assertEqual(merged["receivers"][0]["distinct_packets"], 5)

    def test_every_order_and_duplicate_is_idempotent(self) -> None:
        items = cag.fixture()
        reference = cag.Replica()
        for p in items:
            reference.ingest(p, route="reference")
        expected = reference.evaluate("final")
        for arrangement in itertools.permutations(items):
            receiver = cag.Replica()
            for p in arrangement:
                self.assertTrue(receiver.ingest(p, route="r1"))
                self.assertFalse(receiver.ingest(p, route="r2"))
            self.assertEqual(receiver.evaluate("final"), expected)

    def test_grow_only_exchange_eventually_converges(self) -> None:
        left = cag.Replica()
        right = cag.Replica()
        for p in self.blue["packets"]:
            left.ingest(p, route="blue")
        for p in self.amber["packets"]:
            right.ingest(p, route="amber")
        self.assertEqual(left.evaluate("final")["status"], "unknown_dependency")
        self.assertEqual(right.evaluate("final")["status"], "unknown_dependency")
        self.assertGreater(left.reconcile_from(right, route="anti-entropy"), 0)
        self.assertGreater(right.reconcile_from(left, route="anti-entropy"), 0)
        self.assertEqual(left.evaluate("final"), right.evaluate("final"))
        self.assertEqual(left.evaluate("final")["value"], 44)
        self.assertEqual(left.reconcile_from(right, route="retry"), 0)
        self.assertEqual(right.reconcile_from(left, route="retry"), 0)

    def test_same_semantic_identity_with_different_bytes_is_a_sticky_conflict(self) -> None:
        packets = cag.fixture()
        receiver = cag.Replica()
        for p in packets:
            receiver.ingest(p, route="trusted-looking")
        wrong = cag.packet("left", "add", ["seed"], 6)
        receiver.ingest(wrong, route="fast-relay")
        self.assertEqual(receiver.evaluate("final")["status"], "conflicting_identity")
        receiver.ingest(packets[1], route="late-retry")
        self.assertEqual(receiver.evaluate("final")["status"], "conflicting_identity")
        self.assertEqual(len(receiver.variants["left"]), 2)

    def test_unobserved_dependency_remains_unknown_even_if_target_received(self) -> None:
        receiver = cag.Replica()
        receiver.ingest(cag.fixture()[-1], route="short-circuit")
        self.assertEqual(receiver.evaluate("final")["status"], "unknown_dependency")
        self.assertIsNone(receiver.evaluate("final")["result_digest"])

    def test_concurrent_branches_do_not_imply_a_total_order(self) -> None:
        left = cag.packet("left", "add", ["seed"], 4)
        right = cag.packet("right", "multiply", ["seed"], 5)
        self.assertNotIn(left["semantic_id"], right["parents"])
        self.assertNotIn(right["semantic_id"], left["parents"])
        receiver = cag.Replica()
        for p in (cag.fixture()[0], left, right):
            receiver.ingest(p, route="two-peers")
        self.assertEqual(receiver.evaluate("left")["value"], 7)
        self.assertEqual(receiver.evaluate("right")["value"], 15)
        self.assertEqual(receiver.evaluate("final")["status"], "unknown_dependency")

    def test_dependency_cycles_fail_closed(self) -> None:
        receiver = cag.Replica()
        receiver.ingest(cag.packet("a", "add", ["b"], 1), route="r1")
        receiver.ingest(cag.packet("b", "add", ["a"], 1), route="r2")
        self.assertEqual(receiver.evaluate("a")["status"], "dependency_cycle")

    def test_tampered_digest_is_not_admitted(self) -> None:
        p = cag.fixture()[1]
        bad = copy.deepcopy(p)
        bad["argument"] = -8
        with self.assertRaisesRegex(cag.ConvergenceError, "digest"):
            cag.Replica().ingest(bad, route="r1")

    def test_overflow_is_rejected_without_committing_an_effect(self) -> None:
        receiver = cag.Replica()
        receiver.ingest(cag.packet("base", "constant", [], cag.MAX_VALUE), route="r1")
        receiver.ingest(cag.packet("too_large", "multiply", ["base"], 2), route="r2")
        with self.assertRaises(cag.ConvergenceError):
            receiver.evaluate("too_large")

    def test_forged_packet_in_relay_bundle_fails_even_with_recomputed_wrapper(self) -> None:
        wrong = copy.deepcopy(self.blue)
        wrong["packets"][1] = cag.packet("right", "multiply", ["seed"], 17)
        wrong["bundle_digest"] = cag.sha({k: v for k, v in wrong.items() if k != "bundle_digest"})
        with self.assertRaisesRegex(cag.ConvergenceError, "modified source"):
            cag.verify(self.source, wrong, self.amber)

    def test_missing_or_duplicate_route_bundles_do_not_claim_convergence(self) -> None:
        with self.assertRaises(cag.ConvergenceError):
            cag.verify(self.source, self.blue, self.blue)
        dropped = copy.deepcopy(self.amber)
        dropped["packets"] = dropped["packets"][:2]
        dropped["bundle_digest"] = cag.sha({k: v for k, v in dropped.items() if k != "bundle_digest"})
        with self.assertRaisesRegex(cag.ConvergenceError, "packet count"):
            cag.verify(self.source, self.blue, dropped)

    def test_non_integer_opaque_operations_are_rejected(self) -> None:
        for value in (True, 2.5, "9", None, 10 ** 15):
            with self.subTest(value=value):
                with self.assertRaises(cag.ConvergenceError):
                    cag.validate(cag.packet("unsafe", "constant", [], value))
        with self.assertRaisesRegex(cag.ConvergenceError, "unrecognized"):
            cag.validate(cag.packet("x", "eval-python", [], 1))

    def test_roundtrip_and_source_provenance_are_digest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "source.json"
            cag.write(path, self.source)
            src = cag.read(path)
            self.assertEqual(src, self.source)
            self.assertEqual(cag.verify(src, self.blue, self.amber)["expected"]["value"], 44)
            tampered = copy.deepcopy(src)
            tampered["target"] = "left"
            with self.assertRaisesRegex(cag.ConvergenceError, "source-bundle digest"):
                cag.check_source(tampered)


if __name__ == "__main__":
    unittest.main()
