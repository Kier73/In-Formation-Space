"""PON-002: signed capability, causal navigation and corrupt/outage route tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import time
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from passive_orbit import (
    ROOT_PIN, HERE, PassiveRejected, canonical, digest, checked_manifest
)
from pon002_orbit import (
    Provider, providers_for_commit, grant_root, check_grant, public_key_bytes,
    reconstruct, GITHUB_BASE, JSDELIVR_BASE, CAP_SCHEMA,
)

PUBLIC = HERE / "public"
COMMIT = "b" * 40
DOCS = json.loads((PUBLIC / "manifest.json").read_text())
REFS = {r["semantic_id"]: r["object_sha256"] for r in DOCS["objects"]}


class MemoryFetcher:
    def __init__(self, by_route: dict):
        self.by_route = by_route
        self.calls = []

    def read(self, route, path, *, limit):
        self.calls.append((route.name, path))
        value = self.by_route.get(route.name, {}).get(path)
        if value is None:
            return None, "http_404", 90_000
        if value == b"!unreachable!":
            return None, "unavailable", 90_000
        if len(value) > limit:
            raise PassiveRejected("remote response exceeds byte budget")
        return value, "retrieved", 90_000


def objects():
    out = {"manifest.json": (PUBLIC / "manifest.json").read_bytes()}
    for ref in DOCS["objects"]:
        name = "objects/" + ref["object_sha256"] + ".json"
        out[name] = (PUBLIC / name).read_bytes()
    return out


def capability(root_pin=ROOT_PIN, *, epoch=4, now=2_000_000_000):
    signer = Ed25519PrivateKey.generate()
    pub = public_key_bytes(signer)
    grant = grant_root(signer=signer, manifest_sha=root_pin,
                       epoch=epoch, valid_from=now - 20,
                       valid_until=now + 200)
    return signer, pub, grant, now


def run_with(mapping, *, preference=("github", "jsdelivr")):
    signer, pub, grant, now = capability()
    fetch = MemoryFetcher(mapping)
    result = reconstruct(routes=providers_for_commit(COMMIT, preference=preference),
                         grant=grant, pinned_key=pub, now=now,
                         minimum_epoch=4, fetcher=fetch)
    return result, fetch


class PON002Tests(unittest.TestCase):
    def test_signed_complete_orbit_is_route_independent(self):
        records = objects()
        a, _ = run_with({"github": records})
        b, _ = run_with({"jsdelivr": records}, preference=("jsdelivr", "github"))
        self.assertEqual(a["status"], "verified_reconstruction")
        self.assertEqual(b["status"], "verified_reconstruction")
        self.assertEqual((a["value"], b["value"]), (44, 44))
        self.assertEqual(a["result_digest"], b["result_digest"])
        self.assertEqual(a["verified_objects"], 5)
        self.assertFalse(a["passive_hosts_executed_arithmetic"])
        self.assertFalse(a["externally_authenticated_issuer"])
        self.assertEqual(a["provider_source_origins"], b["provider_source_origins"])

    def test_two_delivery_operators_complement_missing_dependencies(self):
        all_objs = objects()
        github = {k: v for k, v in all_objs.items() if
                  k == "manifest.json" or REFS["seed"] in k or REFS["left"] in k}
        cdn = {k: v for k, v in all_objs.items() if
               k == "manifest.json" or k not in github}
        result, io = run_with({"github": github, "jsdelivr": cdn})
        self.assertEqual(result["value"], 44)
        used = {r["provider"] for r in result["delivery_by_object"].values()}
        self.assertEqual(used, {"github", "jsdelivr"})
        self.assertTrue(any(e["status"] == "http_404" for e in result["events"]))
        self.assertLessEqual(len(io.calls), 54)

    def test_corrupt_rehashed_packet_does_not_replace_pinned_data(self):
        full = objects()
        damaged = dict(full)
        identity = REFS["final"]
        path = "objects/" + identity + ".json"
        forged = json.loads(full[path])
        forged["argument"] = 500
        from convergent_fabric import sha
        forged["digest"] = sha({k: v for k, v in forged.items() if k != "digest"})
        damaged[path] = canonical(forged)
        result, _ = run_with({"jsdelivr": damaged, "github": full},
                             preference=("jsdelivr", "github"))
        self.assertEqual(result["value"], 44)
        self.assertEqual(result["delivery_by_object"]["final"]["provider"], "github")
        self.assertTrue(any(x["status"] == "rejected_integrity_or_semantics"
                            for x in result["events"]))

    def test_signed_root_remains_unresolved_if_both_sources_miss_dependency(self):
        all_obj = objects()
        missing = "objects/" + REFS["seed"] + ".json"
        incomplete = {k: v for k, v in all_obj.items() if k != missing}
        result, _ = run_with({"github": incomplete, "jsdelivr": incomplete})
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["evaluation_status"], "unknown_dependency")
        self.assertIn("seed", result["missing"])
        self.assertIsNone(result["value"])

    def test_causal_navigation_skips_unrelated_manifest_objects(self):
        man = deepcopy(DOCS)
        man["objects"].append({
            "semantic_id": "unneeded", "object_sha256": "f" * 64
        })
        raw = canonical(man)
        new_root = digest(raw)
        signer, pub, grant, now = capability(root_pin=new_root)
        data = objects()
        data["manifest.json"] = raw
        fetch = MemoryFetcher({"github": data})
        result = reconstruct(
            routes=providers_for_commit(COMMIT), grant=grant,
            pinned_key=pub, root_pin=new_root,
            minimum_epoch=4, now=now, fetcher=fetch)
        self.assertEqual(result["value"], 44)
        self.assertEqual(result["verified_objects"], 5)
        self.assertEqual(result["total_manifest_objects"], 6)
        self.assertNotIn(("github", "objects/" + "f" * 64 + ".json"), fetch.calls)
        self.assertNotIn("unneeded", result["delivery_by_object"])

    def test_receiver_key_pin_and_signature_alterations_fail_closed(self):
        signer, pub, grant, now = capability()
        wrong = public_key_bytes(Ed25519PrivateKey.generate())
        with self.assertRaises(PassiveRejected):
            check_grant(grant=grant, pinned_key=wrong, root_pin=ROOT_PIN,
                        minimum_epoch=4, now=now)
        modified = deepcopy(grant)
        modified["epoch"] = 5
        with self.assertRaisesRegex(PassiveRejected, "signature"):
            check_grant(grant=modified, pinned_key=pub, root_pin=ROOT_PIN,
                        minimum_epoch=4, now=now)
        modified = deepcopy(grant)
        modified["scope"] = "write-effects"
        with self.assertRaises(PassiveRejected):
            check_grant(grant=modified, pinned_key=pub, root_pin=ROOT_PIN,
                        minimum_epoch=4, now=now)

    def test_receiver_epoch_and_expiry_fail_without_network_requests(self):
        signer, pub, grant, now = capability()
        io = MemoryFetcher({"github": objects()})
        for candidate in [now - 30, now + 201]:
            with self.subTest(now=candidate), self.assertRaises(PassiveRejected):
                reconstruct(routes=providers_for_commit(COMMIT), grant=grant,
                            pinned_key=pub, minimum_epoch=4,
                            now=candidate, fetcher=io)
        with self.assertRaisesRegex(PassiveRejected, "rolled-back"):
            reconstruct(routes=providers_for_commit(COMMIT), grant=grant,
                        pinned_key=pub, minimum_epoch=5, now=now, fetcher=io)
        self.assertEqual(io.calls, [])

    def test_public_provider_urls_pin_full_commit_with_path_separator(self):
        routes = providers_for_commit(COMMIT)
        self.assertEqual(routes[0].base_url,
            "https://raw.githubusercontent.com/Kier73/In-Formation-Space/"
            + COMMIT + "/experiments/passive-orbit-cache/public/")
        self.assertEqual(routes[1].base_url,
            "https://cdn.jsdelivr.net/gh/Kier73/In-Formation-Space@"
            + COMMIT + "/experiments/passive-orbit-cache/public/")
        self.assertTrue(routes[0].base_url.endswith(COMMIT +
            "/experiments/passive-orbit-cache/public/"))

    def test_noncanonical_duplicate_or_mutable_public_routes_fail(self):
        urls = [
            GITHUB_BASE + "main/experiments/passive-orbit-cache/public/",
            "https://cdn.jsdelivr.net/gh/Kier73/In-Formation-Space@main/experiments/passive-orbit-cache/public/",
            "https://cdn.jsdelivr.net/gh/Kier73/In-Formation-Space@"+COMMIT+"/other/",
            "https://cdn.jsdelivr.net@evil.invalid/gh/Kier73/In-Formation-Space@"+COMMIT+"/experiments/passive-orbit-cache/public/",
            "http://cdn.jsdelivr.net/gh/Kier73/In-Formation-Space@"+COMMIT+"/experiments/passive-orbit-cache/public/",
        ]
        for bad in urls:
            with self.subTest(bad=bad), self.assertRaises(PassiveRejected):
                Provider("bad", bad, "jsdelivr", COMMIT)
        with self.assertRaises(PassiveRejected):
            providers_for_commit("main")
        with self.assertRaises(PassiveRejected):
            providers_for_commit(COMMIT, preference=("github", "github"))
        signer, pub, grant, now = capability()
        with self.assertRaises(PassiveRejected):
            reconstruct(routes=providers_for_commit(COMMIT) +
                        [Provider("duplicate", GITHUB_BASE + "c" * 40 +
                                  "/experiments/passive-orbit-cache/public/", "github", "c"*40)],
                        grant=grant, pinned_key=pub,
                        minimum_epoch=4, now=now, fetcher=MemoryFetcher({}))

    def test_missing_both_roots_and_unavailable_provider_preserve_unknown(self):
        result, fetch = run_with({"github": {"manifest.json": b"!unreachable!"},
                                  "jsdelivr": {}})
        self.assertEqual(result["status"], "unresolved")
        self.assertIn("root", result["missing"])
        self.assertFalse(result["passive_hosts_executed_arithmetic"])
        self.assertEqual(len(fetch.calls), 2)

    def test_signature_cannot_be_replayed_into_other_root_or_scope(self):
        signer, pub, grant, now = capability()
        for root in ("e" * 64, "0" * 64):
            with self.assertRaisesRegex(PassiveRejected, "receiver-owned"):
                check_grant(grant=grant, pinned_key=pub, root_pin=root,
                            minimum_epoch=4, now=now)
        expired = grant_root(signer=signer, manifest_sha=ROOT_PIN,
                             epoch=5, valid_from=now-20, valid_until=now+100)
        with self.assertRaises(PassiveRejected):
            check_grant(grant=expired, pinned_key=pub, root_pin=ROOT_PIN,
                        minimum_epoch=6, now=now)

    def test_reference_result_computes_only_after_all_predecessors_verified(self):
        data = objects()
        tampered = dict(data)
        file = "objects/" + REFS["right"] + ".json"
        tampered[file] = b"bad"
        unresolved, _ = run_with({"github": tampered, "jsdelivr": {}})
        resolved, _ = run_with({"github": tampered, "jsdelivr": data})
        self.assertEqual(unresolved["status"], "unresolved")
        self.assertIsNone(unresolved["result_digest"])
        self.assertEqual(resolved["value"], 44)
        self.assertEqual(resolved["status"], "verified_reconstruction")


if __name__ == "__main__":
    unittest.main()
