"""SNC-004: untrusted capsule federation, authority, replay and audit tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from independent_certificate_checker import hash_bytes
from federated_capsule import (
    FORMAT, HostRejected, export_from_host, import_on_host, receiver_run,
)
from federated_auditor import AuditRejected, audit
from persistent_host import (
    POLICY_SCHEMA, PersistentSemanticHost, canonical, sha,
)
from compiler import compile_semantics

EXAMPLES = json.loads((Path(__file__).parent / "examples.json").read_text())


def pin(root: Path, name: str, semantic: list) -> Path:
    policy = root / (name + "-policy.json")
    policy.write_bytes(canonical({
        "schema": POLICY_SCHEMA,
        "models": {name: hash_bytes(semantic)},
    }))
    return policy


def fixtures(root: Path):
    source = EXAMPLES["clamp_0_1"]
    sender_policy = pin(root, "source_clamp", source)
    receiver_policy = pin(root, "clamp", source)
    sender = PersistentSemanticHost(root / "sender.sqlite3", sender_policy)
    sender.observe(model="source_clamp", coordinate="1/2",
                   request_id="source", source=source)
    body = export_from_host(sender, "source_clamp")
    receiver = PersistentSemanticHost(root / "receiver.sqlite3", receiver_policy)
    return sender, receiver, body, receiver_policy


class FederatedHostTests(unittest.TestCase):
    def test_independent_receiver_uses_no_constructor_and_reuses_after_restart(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            _, dest, raw, policy = fixtures(root)
            with patch("compiler.compile_semantics",
                       side_effect=AssertionError("compiler invoked during import")):
                accepted = import_on_host(dest, "clamp", raw)
                verified = dest.observe(model="clamp", coordinate="3/4",
                                        request_id="first")
            self.assertEqual(accepted["disposition"], "imported-independently-verified")
            self.assertFalse(accepted["model_compiler_ran_at_receiver"])
            self.assertFalse(accepted["external_execution_authorized"])
            self.assertEqual(verified["cache_state"], "restored-verified")
            self.assertEqual(verified["receipt"]["outputs"], ["3/4"])
            later = dest.observe(model="clamp", coordinate="1/2",
                                 request_id="second")
            self.assertEqual(later["cache_state"], "memory-reused")
            self.assertEqual(later["independent_verification_ns"], 0)
            restarted = PersistentSemanticHost(root / "receiver.sqlite3", policy)
            replay = restarted.observe(model="clamp", coordinate="3/4",
                                       request_id="first")
            self.assertEqual(replay["cache_state"], "restored-verified")
            self.assertEqual(replay["disposition"], "idempotent-replay")
            self.assertEqual(dest.count("clamp"), (1, 2))

    def test_import_replay_is_idempotent(self):
        with TemporaryDirectory() as root:
            _, dest, raw, _ = fixtures(Path(root))
            a = import_on_host(dest, "clamp", raw)
            b = import_on_host(dest, "clamp", raw)
            self.assertEqual(a["disposition"], "imported-independently-verified")
            self.assertEqual(b["disposition"], "idempotent-existing-verified")
            self.assertEqual(dest.count("clamp"), (1, 0))

    def test_unknown_or_different_receiver_pin_denied(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            _, dest, raw, policy = fixtures(root)
            with self.assertRaisesRegex(HostRejected, "absent/revoked"):
                import_on_host(dest, "sender_authority", raw)
            policy.write_bytes(canonical({
                "schema": POLICY_SCHEMA,
                "models": {"clamp": hash_bytes(EXAMPLES["identity"])},
            }))
            with self.assertRaisesRegex(HostRejected, "receiver-owned"):
                import_on_host(dest, "clamp", raw)
            self.assertEqual(dest.count("clamp"), (0, 0))

    def test_canonical_and_schema_substitution_denied(self):
        with TemporaryDirectory() as root:
            _, dest, raw, _ = fixtures(Path(root))
            for bad in (raw[:-1], raw.replace(b'"schema":', b'"schema":"x","schema":', 1),
                        raw.replace(b'"generated_network_sha256":',
                                    b'"unexpected":true,"generated_network_sha256":', 1)):
                with self.subTest(bad=bad[:60]), self.assertRaises(HostRejected):
                    import_on_host(dest, "clamp", bad)
            self.assertEqual(dest.count("clamp"), (0, 0))

    def test_outer_identity_forgery_denied(self):
        with TemporaryDirectory() as root:
            _, dest, raw, _ = fixtures(Path(root))
            bad = json.loads(raw)
            bad["generated_network_sha256"] = "0" * 64
            with self.assertRaises(HostRejected):
                import_on_host(dest, "clamp", canonical(bad))
            bad = json.loads(raw)
            bad["source_semantic_sha256"] = hash_bytes(EXAMPLES["identity"])
            with self.assertRaisesRegex(HostRejected, "receiver-owned"):
                import_on_host(dest, "clamp", canonical(bad))
            self.assertEqual(dest.count("clamp"), (0, 0))

    def test_rehashed_parameter_substitution_denied(self):
        with TemporaryDirectory() as root:
            _, dest, raw, _ = fixtures(Path(root))
            fake = json.loads(raw)
            net = fake["snc001_capsule"]["generated_certificate"]["network"]
            net["layers"][1]["weights"][0][0] = "17"
            fake["snc001_capsule"]["generated_certificate"]["network_sha256"] = hash_bytes(net)
            fake["generated_network_sha256"] = hash_bytes(net)
            with self.assertRaisesRegex(HostRejected, "certificate"):
                import_on_host(dest, "clamp", canonical(fake))
            self.assertEqual(dest.count("clamp"), (0, 0))

    def test_existing_corrupt_cache_is_not_silently_overwritten(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            _, dest, raw, _ = fixtures(root)
            import_on_host(dest, "clamp", raw)
            with sqlite3.connect(root / "receiver.sqlite3") as db:
                db.execute("UPDATE realizations SET capsule=?", (b"broken",))
            with self.assertRaises(HostRejected):
                import_on_host(dest, "clamp", raw)
            self.assertEqual(dest.count("clamp"), (1, 0))

    def test_policy_revocation_blocks_imported_and_warm_realizations(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            _, dest, raw, policy = fixtures(root)
            import_on_host(dest, "clamp", raw)
            dest.observe(model="clamp", coordinate="0", request_id="before")
            policy.write_bytes(canonical({
                "schema": POLICY_SCHEMA,
                "models": {"another": hash_bytes(EXAMPLES["identity"])},
            }))
            with self.assertRaisesRegex(HostRejected, "absent/revoked"):
                dest.observe(model="clamp", coordinate="1", request_id="after")
            with self.assertRaisesRegex(HostRejected, "absent/revoked"):
                import_on_host(dest, "clamp", raw)

    def test_concurrent_receiver_imports_admit_one_realization(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            _, dest, raw, policy = fixtures(root)
            def transfer(_):
                independently_opened = PersistentSemanticHost(
                    root / "receiver.sqlite3", policy)
                return import_on_host(independently_opened, "clamp", raw)["disposition"]
            with ThreadPoolExecutor(max_workers=2) as pool:
                states = list(pool.map(transfer, range(2)))
            self.assertEqual(sorted(states), [
                "idempotent-existing-verified", "imported-independently-verified",
            ])
            self.assertEqual(dest.count("clamp"), (1, 0))

    def test_receiver_receipt_and_third_host_auditor(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            _, dest, raw, policy = fixtures(root)
            export_file = root / "transfer.json"
            export_file.write_bytes(raw)
            report_path = root / "report.json"
            report = receiver_run(
                capsule=export_file, database=dest.database, policy=policy,
                model="clamp", coordinate="3/4",
                request_id="import-observe", output=report_path,
            )
            checked = audit(
                body=raw, receiver_report=report_path.read_bytes(),
                expected_source=EXAMPLES["clamp_0_1"],
                expected_model="clamp", expected_coordinate="3/4",
                expected_request_id="import-observe",
            )
            self.assertEqual(checked["status"],
                             "independent-full-domain-and-observation-reconstruction")
            self.assertEqual(checked["independent_outputs"], ["3/4"])
            forged = deepcopy(report)
            forged["observation"]["receipt"]["outputs"] = ["99"]
            forged["observation"]["receipt_sha256"] = sha(
                canonical(forged["observation"]["receipt"]))
            with self.assertRaises(AuditRejected):
                audit(body=raw, receiver_report=canonical(forged),
                      expected_source=EXAMPLES["clamp_0_1"],
                      expected_model="clamp", expected_coordinate="3/4",
                      expected_request_id="import-observe")

    def test_source_aliases_do_not_become_receiver_policy(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            sender, receiver, raw, _ = fixtures(root)
            self.assertNotIn(b"source_clamp", raw)
            self.assertNotIn(b"policy", raw)
            self.assertEqual(json.loads(raw)["schema"], FORMAT)
            self.assertEqual(import_on_host(receiver, "clamp", raw)["model"], "clamp")
            self.assertEqual(sender.count("source_clamp"), (1, 1))

    def test_sender_cannot_export_unverified_or_corrupt_cache(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            policy = pin(root, "source_clamp", EXAMPLES["clamp_0_1"])
            host = PersistentSemanticHost(root / "new.sqlite3", policy)
            with self.assertRaisesRegex(HostRejected, "no verified"):
                export_from_host(host, "source_clamp")
            host.observe(model="source_clamp", coordinate="0",
                         request_id="first", source=EXAMPLES["clamp_0_1"])
            with sqlite3.connect(root / "new.sqlite3") as db:
                db.execute("UPDATE realizations SET capsule=?", (b"bad",))
            with self.assertRaises(HostRejected):
                export_from_host(host, "source_clamp")


if __name__ == "__main__":
    unittest.main()
