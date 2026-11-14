"""SNC-003 independent, durable and adversarial semantic hosting contract tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from independent_certificate_checker import hash_bytes
from persistent_host import (
    HostRejected, PersistentSemanticHost, POLICY_SCHEMA, canonical, sha,
)
from persistent_wire import (
    REQUEST_SCHEMA, RESPONSE_SCHEMA, handle, validate_request,
)

EXAMPLES = json.loads((Path(__file__).parent / "examples.json").read_text())


def fixture(folder: Path, models: dict[str, str] | None = None
            ) -> tuple[PersistentSemanticHost, Path, Path]:
    policy = folder / "policy.json"
    db = folder / "host.sqlite3"
    policy.write_bytes(canonical({
        "schema": POLICY_SCHEMA,
        "models": models or {"clamp": hash_bytes(EXAMPLES["clamp_0_1"])},
    }))
    return PersistentSemanticHost(db, policy), db, policy


def make_request(model: str, x: str, rid: str, source=None) -> dict:
    raw = {
        "schema": REQUEST_SCHEMA,
        "kind": "observe" if source is None else "seed",
        "model": model, "coordinate": x, "request_id": rid,
    }
    if source is not None:
        raw["semantic_atlas"] = source
    return raw


class PersistentHostTests(unittest.TestCase):
    def test_construct_reuse_restore_and_idempotency(self):
        with TemporaryDirectory() as root:
            host, db, policy = fixture(Path(root))
            cold = host.observe(
                model="clamp", coordinate="1/2", request_id="first",
                source=deepcopy(EXAMPLES["clamp_0_1"]),
            )
            self.assertEqual(cold["cache_state"], "constructed-verified")
            self.assertEqual(cold["receipt"]["outputs"], ["1/2"])
            self.assertGreater(cold["construction_ns"], 0)
            warm = host.observe(
                model="clamp", coordinate="3/4", request_id="second")
            self.assertEqual(warm["cache_state"], "memory-reused")
            self.assertEqual(warm["construction_ns"], 0)
            self.assertEqual(warm["independent_verification_ns"], 0)
            fresh = PersistentSemanticHost(db, policy)
            restored = fresh.observe(
                model="clamp", coordinate="3/4", request_id="third")
            self.assertEqual(restored["cache_state"], "restored-verified")
            self.assertEqual(restored["construction_ns"], 0)
            self.assertGreater(restored["independent_verification_ns"], 0)
            self.assertEqual(restored["receipt"]["outputs"], ["3/4"])
            replay = fresh.observe(
                model="clamp", coordinate="3/4", request_id="third")
            self.assertEqual(replay["disposition"], "idempotent-replay")
            self.assertEqual(replay["receipt_sha256"], restored["receipt_sha256"])
            self.assertEqual(host.count("clamp"), (1, 3))

    def test_cold_source_is_required_and_reference_carries_no_weights(self):
        with TemporaryDirectory() as root:
            host, _, _ = fixture(Path(root))
            with self.assertRaisesRegex(HostRejected, "no admitted"):
                host.observe(model="clamp", coordinate="0", request_id="u")
            req = make_request("clamp", "1/2", "u")
            self.assertNotIn("semantic_atlas", req)
            self.assertNotIn("weights", json.dumps(req))
            result = handle(host, req)
            self.assertEqual(result["schema"], RESPONSE_SCHEMA)
            self.assertFalse(result["accepted"])
            self.assertEqual(host.count("clamp"), (0, 0))

    def test_all_five_source_models(self):
        with TemporaryDirectory() as root:
            models = {name: hash_bytes(value) for name, value in EXAMPLES.items()}
            host, _, _ = fixture(Path(root), models)
            for i, (name, source) in enumerate(EXAMPLES.items()):
                received = host.observe(
                    model=name, coordinate="1/4",
                    request_id=f"example{i}", source=source)
                self.assertEqual(received["status"],
                                 "verified-exact-mathematical-observation")
                self.assertEqual(received["cache_state"], "constructed-verified")
                self.assertEqual(received["receipt"]["semantic_sha256"], models[name])
                self.assertEqual(host.count(name), (1, 1))

    def test_receiver_owned_pin_refuses_source_substitution(self):
        with TemporaryDirectory() as root:
            host, _, _ = fixture(Path(root))
            with self.assertRaisesRegex(HostRejected, "receiver-owned"):
                host.observe(
                    model="clamp", coordinate="0", request_id="forge",
                    source=EXAMPLES["identity"])
            self.assertEqual(host.count("clamp"), (0, 0))

    def test_byte_corruption_blocks_restoration_not_reconstruction(self):
        with TemporaryDirectory() as root:
            host, db, policy = fixture(Path(root))
            host.observe(model="clamp", coordinate="0", request_id="one",
                         source=EXAMPLES["clamp_0_1"])
            with sqlite3.connect(db) as sql:
                sql.execute("UPDATE realizations SET capsule=?", (b"corrupt\n",))
            fresh = PersistentSemanticHost(db, policy)
            with self.assertRaisesRegex(HostRejected, "corrupt"):
                fresh.observe(model="clamp", coordinate="1", request_id="two")
            self.assertEqual(host.count("clamp"), (1, 1))

    def test_rehashed_weight_tampering_is_rejected(self):
        with TemporaryDirectory() as root:
            host, db, policy = fixture(Path(root))
            host.observe(model="clamp", coordinate="0", request_id="one",
                         source=EXAMPLES["clamp_0_1"])
            with sqlite3.connect(db) as sql:
                saved = sql.execute("SELECT capsule FROM realizations").fetchone()[0]
                cap = json.loads(saved)
                net = cap["generated_certificate"]["network"]
                net["layers"][1]["weights"][0][0] = "27"
                from independent_certificate_checker import hash_bytes
                cap["generated_certificate"]["network_sha256"] = hash_bytes(net)
                replaced = canonical(cap)
                sql.execute(
                    "UPDATE realizations SET capsule=?,capsule_sha=?,network_sha=?",
                    (replaced, sha(replaced), hash_bytes(net)),
                )
            fresh = PersistentSemanticHost(db, policy)
            with self.assertRaisesRegex(HostRejected, "certificate verification"):
                fresh.observe(model="clamp", coordinate="1", request_id="two")
            self.assertEqual(host.count("clamp"), (1, 1))

    def test_policy_revocation_invalidates_memory_and_disk(self):
        with TemporaryDirectory() as root:
            host, db, policy = fixture(Path(root))
            host.observe(model="clamp", coordinate="0", request_id="one",
                         source=EXAMPLES["clamp_0_1"])
            policy.write_bytes(canonical({
                "schema": POLICY_SCHEMA,
                "models": {"unrelated": hash_bytes(EXAMPLES["identity"])},
            }))
            with self.assertRaisesRegex(HostRejected, "absent/revoked"):
                host.observe(model="clamp", coordinate="1", request_id="two")
            with self.assertRaisesRegex(HostRejected, "absent/revoked"):
                PersistentSemanticHost(db, policy).observe(
                    model="clamp", coordinate="1", request_id="three")

    def test_policy_rebinding_never_serves_old_realization(self):
        with TemporaryDirectory() as root:
            host, db, policy = fixture(Path(root))
            host.observe(model="clamp", coordinate="0", request_id="old",
                         source=EXAMPLES["clamp_0_1"])
            policy.write_bytes(canonical({
                "schema": POLICY_SCHEMA,
                "models": {"clamp": hash_bytes(EXAMPLES["identity"])},
            }))
            with self.assertRaisesRegex(HostRejected, "no admitted"):
                host.observe(model="clamp", coordinate="0", request_id="new")
            replaced = host.observe(model="clamp", coordinate="0",
                                    request_id="replacement",
                                    source=EXAMPLES["identity"])
            self.assertEqual(replaced["cache_state"], "constructed-verified")
            self.assertEqual(host.count("clamp"), (1, 1))
            with self.assertRaisesRegex(HostRejected, "conflicting request"):
                host.observe(model="clamp", coordinate="0", request_id="old")

    def test_retry_same_id_different_coordinate_is_conflict(self):
        with TemporaryDirectory() as root:
            host, _, _ = fixture(Path(root))
            host.observe(model="clamp", coordinate="0", request_id="same",
                         source=EXAMPLES["clamp_0_1"])
            with self.assertRaisesRegex(HostRejected, "conflicting request"):
                host.observe(model="clamp", coordinate="1", request_id="same")
            self.assertEqual(host.count("clamp"), (1, 1))

    def test_tampered_observation_even_with_updated_sha_refused(self):
        with TemporaryDirectory() as root:
            host, db, policy = fixture(Path(root))
            host.observe(model="clamp", coordinate="1/2", request_id="first",
                         source=EXAMPLES["clamp_0_1"])
            with sqlite3.connect(db) as sql:
                receipt = json.loads(sql.execute(
                    "SELECT receipt FROM observations").fetchone()[0])
                receipt["outputs"] = ["999"]
                new = canonical(receipt)
                sql.execute("UPDATE observations SET receipt=?,receipt_sha=?",
                            (new, sha(new)))
            with self.assertRaisesRegex(HostRejected, "tampered"):
                PersistentSemanticHost(db, policy).observe(
                    model="clamp", coordinate="1/2", request_id="first")

    def test_concurrent_seeds_one_committed_realization(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            host, db, policy = fixture(root)
            source = EXAMPLES["clamp_0_1"]
            def seed(i):
                return PersistentSemanticHost(db, policy).observe(
                    model="clamp", coordinate="1/2",
                    request_id=f"race{i}", source=source)
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(seed, range(2)))
            self.assertEqual(host.count("clamp"), (1, 2))
            self.assertEqual(
                sorted(r["cache_state"] for r in results),
                ["constructed-verified", "restored-verified"])

    def test_strict_request_format_and_no_client_authority(self):
        with TemporaryDirectory() as root:
            host, _, _ = fixture(Path(root))
            source = EXAMPLES["clamp_0_1"]
            ok = handle(host, make_request("clamp", "0", "valid", source))
            self.assertTrue(ok["accepted"])
            for corruption in (
                {"schema": REQUEST_SCHEMA, "kind": "observe", "model": "clamp",
                 "coordinate": "0", "request_id": "bad", "authority": True},
                {"schema": REQUEST_SCHEMA, "kind": "seed", "model": "clamp",
                 "coordinate": "0", "request_id": "bad"},
                {"schema": REQUEST_SCHEMA, "kind": "observe", "model": "clamp",
                 "coordinate": "2/4", "request_id": "bad"},
            ):
                with self.subTest(corruption=corruption):
                    reply = handle(host, corruption)
                    self.assertFalse(reply["accepted"])
            self.assertEqual(host.count("clamp"), (1, 1))


if __name__ == "__main__":
    unittest.main()
