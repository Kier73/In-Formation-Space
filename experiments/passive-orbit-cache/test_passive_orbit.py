"""PON-001: passive-host, immutable-address and temporary lease contracts."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import threading
import time
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from passive_orbit import (
    ROOT_PIN, SCHEMA, HERE, Route, PassiveRejected, checked_manifest,
    checked_packet, canonical, digest, listen, navigate,
)

PUBLIC = HERE / "public"


@contextmanager
def temporary_host(root: Path, ttl: float = 3.0):
    host = listen(root, ttl_seconds=ttl)
    worker = threading.Thread(target=host.serve_forever, daemon=True)
    worker.start()
    try:
        yield Route("temp", "http://127.0.0.1:" + str(host.server_port) + "/", "temporary")
    finally:
        host.shutdown()
        host.server_close()
        worker.join(timeout=3)


def subset(root: Path, names: list[str], *, root_manifest: bool = True):
    root.mkdir(parents=True, exist_ok=True)
    (root / "objects").mkdir(exist_ok=True)
    manifest = json.loads((PUBLIC / "manifest.json").read_bytes())
    if root_manifest:
        (root / "manifest.json").write_bytes((PUBLIC / "manifest.json").read_bytes())
    for obj in manifest["objects"]:
        if obj["semantic_id"] in names:
            filename = obj["object_sha256"] + ".json"
            shutil.copyfile(PUBLIC / "objects" / filename, root / "objects" / filename)


class PON001Tests(unittest.TestCase):
    def test_public_fixture_bytes_and_immutable_addresses(self):
        raw = (PUBLIC / "manifest.json").read_bytes()
        self.assertEqual(digest(raw), ROOT_PIN)
        manifest = checked_manifest(raw, ROOT_PIN)
        self.assertEqual(len(manifest["objects"]), 5)
        for ref in manifest["objects"]:
            blob = (PUBLIC / "objects" / (ref["object_sha256"] + ".json")).read_bytes()
            checked_packet(blob, identity=ref["semantic_id"], address=ref["object_sha256"])

    def test_two_passive_hosts_supply_complementary_dependencies(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            subset(root / "left", ["seed", "left", "merge"])
            subset(root / "right", ["right", "final"])
            with temporary_host(root / "left") as l, temporary_host(root / "right") as r:
                answer = navigate([Route("left", l.base_url, "temporary"),
                                   Route("right", r.base_url, "temporary")])
            self.assertEqual(answer["status"], "locally_reconstructed_pure_result")
            self.assertEqual(answer["value"], 44)
            self.assertEqual(answer["verified_object_count"], 5)
            self.assertEqual(answer["source_by_semantic_id"]["seed"], "left")
            self.assertEqual(answer["source_by_semantic_id"]["final"], "right")
            self.assertFalse(answer["passive_host_executed_operations"])
            self.assertFalse(answer["external_execution_authorized"])

    def test_expired_temporary_host_falls_back_to_other_holder(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            subset(root / "soon", ["seed", "left", "right", "merge", "final"])
            subset(root / "later", ["seed", "left", "right", "merge", "final"])
            with temporary_host(root / "soon", ttl=0.05) as expiring, \
                 temporary_host(root / "later", ttl=3.0) as durable:
                time.sleep(0.09)
                result = navigate([Route("soon", expiring.base_url, "temporary"),
                                   Route("later", durable.base_url, "temporary")])
            self.assertEqual(result["value"], 44)
            self.assertEqual(result["source_by_semantic_id"]["root"], "later")
            self.assertTrue(any(row["route"] == "soon" and row["status"] == "http_410"
                                for row in result["attempts"]))

    def test_altered_passive_bytes_never_bypass_receiver_owned_digest(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            subset(root / "corrupt", ["seed", "left", "right", "merge", "final"])
            subset(root / "valid", ["seed", "left", "right", "merge", "final"])
            man = json.loads((PUBLIC / "manifest.json").read_bytes())
            key = man["objects"][0]["object_sha256"]
            path = root / "corrupt" / "objects" / (key + ".json")
            bad = json.loads(path.read_bytes())
            bad["argument"] = 999
            path.write_bytes(canonical(bad))
            with temporary_host(root / "corrupt") as faulty, \
                 temporary_host(root / "valid") as good:
                result = navigate([Route("tampered", faulty.base_url, "temporary"),
                                   Route("good", good.base_url, "temporary")])
            self.assertEqual(result["value"], 44)
            self.assertEqual(result["source_by_semantic_id"]["seed"], "good")
            self.assertTrue(any(row["status"] == "rejected_integrity_or_semantics"
                                for row in result["attempts"]))

    def test_missing_node_preserved_as_unresolved(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            subset(root, ["seed", "left", "merge", "final"])
            with temporary_host(root) as host:
                result = navigate([host])
            self.assertEqual(result["status"], "unresolved")
            self.assertIsNone(result["value"])
            self.assertEqual(result["missing"], ["right"])
            self.assertEqual(result["evaluation_status"], "unknown_dependency")
            self.assertFalse(result["local_arithmetic_performed"])

    def test_missing_all_roots_does_not_infer_any_function(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            subset(root, ["seed", "right"], root_manifest=False)
            with temporary_host(root) as host:
                r = navigate([host])
            self.assertEqual(r["status"], "root_unavailable_or_unverified")
            self.assertIsNone(r["target"])
            self.assertFalse(r["local_arithmetic_performed"])

    def test_untrusted_manifest_rejected_even_if_all_objects_correct(self):
        root = json.loads((PUBLIC / "manifest.json").read_bytes())
        root["target"] = "seed"
        altered = canonical(root)
        self.assertNotEqual(digest(altered), ROOT_PIN)
        with self.assertRaisesRegex(PassiveRejected, "manifest digest"):
            checked_manifest(altered, ROOT_PIN)
        root["target"] = "final"
        root["objects"].append(dict(root["objects"][0]))
        with self.assertRaisesRegex(PassiveRejected, "duplicate"):
            checked_manifest(canonical(root), digest(canonical(root)))

    def test_packet_rehashed_semantic_substitution_rejected(self):
        root = json.loads((PUBLIC / "manifest.json").read_bytes())
        ptr = root["objects"][0]
        blob = (PUBLIC / "objects" / (ptr["object_sha256"] + ".json")).read_bytes()
        obj = json.loads(blob)
        obj["argument"] = 45
        from convergent_fabric import sha as cag_sha
        obj["digest"] = cag_sha({k: v for k, v in obj.items() if k != "digest"})
        tampered = canonical(obj)
        with self.assertRaisesRegex(PassiveRejected, "content address"):
            checked_packet(tampered, identity="seed", address=ptr["object_sha256"])
        with self.assertRaisesRegex(PassiveRejected, "semantic identity"):
            checked_packet(blob, identity="right", address=ptr["object_sha256"])

    def test_public_origin_must_be_exact_owned_repo_at_immutable_revision(self):
        ref = "a" * 40
        valid = "https://raw.githubusercontent.com/Kier73/In-Formation-Space/" \
                + ref + "/experiments/passive-orbit-cache/public/"
        self.assertEqual(Route("raw", valid, "public").kind, "public")
        for url in (
            valid.replace(ref, "main"),
            valid.replace("Kier73", "Attacker"),
            valid.replace("raw.githubusercontent.com", "evil.example"),
            valid.replace("https:", "http:"),
            valid + "?x=1",
            "http://127.0.0.1:8091/",
            "https://raw.githubusercontent.com@evil.example/Kier73/In-Formation-Space/"
            + ref + "/experiments/passive-orbit-cache/public/",
        ):
            with self.subTest(url=url), self.assertRaises(PassiveRejected):
                Route("outside", url, "public")

    def test_temporary_holder_read_only_and_finite_ttl(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            subset(root, ["seed"])
            with temporary_host(root) as route:
                with self.assertRaises(HTTPError) as err:
                    urlopen(Request(route.base_url + "manifest.json",
                                    data=b"unauthorized write", method="POST"), timeout=3)
                self.assertEqual(err.exception.code, 405)
            with self.assertRaises(PassiveRejected):
                listen(root, ttl_seconds=0)
            with self.assertRaises(PassiveRejected):
                listen(root, ttl_seconds=3600)

    def test_redirects_are_not_followed(self):
        # No host can redirect the receiver toward arbitrary off-route URLs.
        from passive_orbit import Fetcher, NoRedirect
        import urllib.request
        class Redirecting(urllib.request.BaseHandler):
            def http_open(self, req):
                raise PassiveRejected("passive host redirect prohibited")
        self.assertIsInstance(Fetcher()._opener.handlers[
            next(i for i, x in enumerate(Fetcher()._opener.handlers)
                 if isinstance(x, NoRedirect))], NoRedirect)

    def test_large_manifest_rejected(self):
        original = json.loads((PUBLIC / "manifest.json").read_bytes())
        original["objects"] = [dict(original["objects"][0])] * 33
        data = canonical(original)
        with self.assertRaisesRegex(PassiveRejected, "object count"):
            checked_manifest(data, digest(data))


if __name__ == "__main__":
    unittest.main()
