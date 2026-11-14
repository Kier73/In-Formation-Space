"""PON-002: reconstruct both provider evidence sets independently and detect forgeries."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from passive_orbit import ROOT_PIN, canonical, digest
from pon002_orbit import providers_for_commit, grant_root, public_key_bytes, reconstruct
from pon002_audit import AuditRejected, audit

from test_pon002_orbit import COMMIT, MemoryFetcher, objects

TIME = 2_000_000_000


def report_for(provider: str) -> bytes:
    signer = Ed25519PrivateKey.generate()
    key = public_key_bytes(signer)
    grant = grant_root(signer=signer, manifest_sha=ROOT_PIN,
                       epoch=3, valid_from=TIME-50, valid_until=TIME+500)
    routes = [r for r in providers_for_commit(COMMIT) if r.kind == provider]
    result = reconstruct(routes=routes, grant=grant, pinned_key=key,
                         minimum_epoch=3, now=TIME,
                         fetcher=MemoryFetcher({provider: objects()}))
    return canonical({
        "schema": "in-formation.pon002-provider-report/0.1",
        "provider": provider, "public_git_commit": COMMIT,
        "issuer_public_key_hex": key.hex(), "capability": grant,
        "receiver_min_epoch": 3, "observed_at_unix": TIME,
        "orbit": result,
    }) + b"\n"


class AuditTests(unittest.TestCase):
    def test_independent_signed_provider_audit_converges(self):
        result = audit(report_for("github"), report_for("jsdelivr"), commit=COMMIT)
        self.assertEqual(result["verified_result"], 44)
        self.assertEqual(result["distinct_source_origins"], 1)
        self.assertFalse(result["real_provider_storage_independence_proven"])
        self.assertFalse(result["independent_publisher_signature_authenticated"])
        self.assertFalse(result["actual_in_transit_router_computation"])

    def test_relabelled_provider_cannot_pass_delivery_audit(self):
        github = report_for("github")
        cdn = json.loads(report_for("jsdelivr"))
        cdn["provider"] = "github"
        with self.assertRaises(AuditRejected):
            audit(github, canonical(cdn)+b"\n", commit=COMMIT)

    def test_forged_result_and_recomputed_report_digest_rejected(self):
        github = report_for("github")
        cdn = json.loads(report_for("jsdelivr"))
        cdn["orbit"]["value"] = 999
        core = {k: v for k, v in cdn["orbit"].items() if k != "evidence_digest"}
        cdn["orbit"]["evidence_digest"] = digest(canonical(core))
        with self.assertRaises(AuditRejected):
            audit(github, canonical(cdn)+b"\n", commit=COMMIT)

    def test_modified_signature_and_replayed_source_revision_rejected(self):
        github = report_for("github")
        cdn = json.loads(report_for("jsdelivr"))
        cdn["capability"]["valid_until"] += 1
        with self.assertRaisesRegex(AuditRejected, "grant"):
            audit(github, canonical(cdn)+b"\n", commit=COMMIT)
        with self.assertRaises(AuditRejected):
            audit(github, report_for("jsdelivr"), commit="c"*40)

    def test_noncanonical_report_and_duplicate_identity_refused(self):
        github = report_for("github")
        cdn = report_for("jsdelivr")
        with self.assertRaises(AuditRejected):
            audit(github+b"\n", cdn, commit=COMMIT)
        bad = json.loads(cdn)
        bad["orbit"]["delivery_by_object"]["final"]["provider"] = "github"
        bad["orbit"]["evidence_digest"] = digest(canonical(
            {k: v for k, v in bad["orbit"].items() if k != "evidence_digest"}))
        with self.assertRaises(AuditRejected):
            audit(github, canonical(bad)+b"\n", commit=COMMIT)


if __name__ == "__main__":
    unittest.main()
