"""PON-003: independent third-runner audit of origin claims and failure evidence.

Checks publication signatures against two pinned exact public keys, separately
interprets the canonical source DAG, and audits *reported* read and failure
states. It cannot infer the physical location of an origin or prove a network
partition from a post-hoc JSON report alone. On main, the workflow also
verifies GitHub attestations of both origin tarballs and this report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "convergent-ground-fabric"))
from convergent_fabric import Replica

from passive_orbit import ROOT_PIN, canonical, checked_manifest, checked_packet, digest
from pon003_origin import verify_publication, publisher_source

SCHEMA = "in-formation.pon003.third-observer-audit/0.1"


class AuditRejected(ValueError):
    pass


def check(valid: bool, explanation: str) -> None:
    if not valid:
        raise AuditRejected(explanation)


def reference() -> dict:
    items = publisher_source()
    manifest = checked_manifest(items["manifest.json"], ROOT_PIN)
    replica = Replica()
    for entry in manifest["objects"]:
        path = "objects/" + entry["object_sha256"] + ".json"
        packet = checked_packet(items[path], identity=entry["semantic_id"],
                                address=entry["object_sha256"])
        replica.ingest(packet, route="third-party-source")
    expected = replica.evaluate(manifest["target"])
    check(expected["status"] == "locally_reconstructed_pure_result" and
          expected["value"] == 44, "independent source arithmetic unresolved")
    return expected


def audit(report: dict, *, r2_receipt: dict, ipfs_receipt: dict,
          r2_pub: bytes, ipfs_pub: bytes, now: int) -> dict:
    check(type(report) is dict and report.get("schema") ==
          "in-formation.pon003.local-killed-origin-evidence/0.1" and
          report.get("status") ==
          "two-separately-published-origin-contracts-with-kill-recovery",
          "incorrect origin-failure experiment")
    check(r2_pub != ipfs_pub and
          report.get("distinct_signing_keys") is True and
          report.get("source_root_sha256") == ROOT_PIN and
          report.get("r2_receipt_sha256") == digest(canonical(r2_receipt)) and
          report.get("ipfs_receipt_sha256") == digest(canonical(ipfs_receipt)),
          "different signing keys, root and exact receipt digests required")
    for kind, doc, key in (("r2", r2_receipt, r2_pub),
                           ("ipfs", ipfs_receipt, ipfs_pub)):
        try:
            verify_publication(
                receipt=doc, trusted_public_key=key,
                expected_kind=kind, root_pin=ROOT_PIN, floor=1, now=now,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise AuditRejected("invalid " + kind + " publication claim") from exc

    expected = reference()
    phases = ("baseline", "tampered_origin", "bucket_origin_killed")
    for name in phases:
        observed = report.get(name)
        check(type(observed) is dict and observed.get("schema") ==
              "in-formation.pon003.surviving-origin-navigation/0.1" and
              observed.get("status") == "verified_reconstruction" and
              observed.get("root_sha256") == ROOT_PIN and
              observed.get("value") == expected["value"] and
              observed.get("result_digest") == expected["result_digest"] and
              observed.get("lineage") == expected["lineage"] and
              observed.get("verified_object_count") == 5 and
              observed.get("missing") == [] and
              observed.get("source_issuer_independently_authenticated") is False and
              observed.get("physical_origin_independence_attested") is False and
              observed.get("external_effects_authorized") is False and
              observed.get("passive_origins_executed_code") is False,
              "phase did not match exact mathematical source or provenance bounds")
        core = {k: v for k, v in observed.items() if k != "evidence_sha256"}
        check(observed.get("evidence_sha256") == digest(canonical(core)),
              "phase evidence hash was modified")
        check(observed.get("receipt_sha256_by_origin") == {
            "r2": digest(canonical(r2_receipt)),
            "ipfs": digest(canonical(ipfs_receipt)),
        }, "phase not bound to both publications")
        check(type(observed.get("events")) is list and
              len(observed["events"]) >= 6, "reported byte acquisitions absent")
        check(set(observed.get("selected_origins", {})) ==
              {"root", "seed", "left", "right", "merge", "final"},
              "incomplete observed causal closure")

    check(set(report["baseline"]["selected_origins"].values()) == {"r2"},
          "baseline did not serve from bucket origin")
    check(report["tampered_origin"]["selected_origins"].get("root") == "ipfs" and
          any(e.get("origin") == "r2" and
              e.get("status") == "rejected_integrity_or_semantics"
              for e in report["tampered_origin"]["events"]),
          "tampered origin was not refused in favor of correct content")
    check(set(report["bucket_origin_killed"]["selected_origins"].values()) ==
          {"ipfs"} and
          any(e.get("origin") == "r2" and e.get("status") == "unavailable"
              for e in report["bucket_origin_killed"]["events"]),
          "loss of one origin was not reflected in surviving route")
    both = report.get("both_origins_killed")
    check(type(both) is dict and both.get("status") == "unresolved" and
          both.get("value") is None and both.get("missing") == ["root"] and
          not both.get("selected_origins") and
          {e.get("origin") for e in both.get("events", [])} ==
          {"r2", "ipfs"} and
          all(e.get("status") == "unavailable" for e in both["events"]),
          "total disappearance was mislabeled as a locally available result")
    check(report.get("real_process_kill") is True and
          report.get("physical_origin_machine_count") == 1 and
          report.get("public_origin_success_verified") is False and
          report.get("independent_storage_admins_attested") is False and
          report.get("shared_artifact_backend") == "GitHub Actions" and
          report.get("passive_hosts_executed_computation") is False,
          "origin independence or execution overclaimed")
    return {
        "schema": SCHEMA,
        "status": "signed-dual-origin-local-kill-and-independent-reconstruction",
        "expected_pure_value": expected["value"],
        "result_digest": expected["result_digest"],
        "source_root_sha256": ROOT_PIN,
        "publisher_keys_distinct": True,
        "publisher_signature_validity_rechecked": True,
        "content_integrity_on_surviving_route_reported": True,
        "single_origin_loss_reported": True,
        "both_origin_loss_reported_as_unresolved": True,
        "independent_storage_operators_verified_live": False,
        "third_host_direct_packet_capture": False,
        "local_origin_server_processes": 2,
        "public_ipfs_pin_verified": False,
        "public_r2_object_verified": False,
        "external_execution_authorized": False,
        "report_sha256": digest(canonical(report)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r2-dir", type=Path, required=True)
    parser.add_argument("--ipfs-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    check(canonical(json.loads(raw)) + b"\n" == raw,
          "reported origin experiment is not canonical")
    report = json.loads(raw)
    docs = {k: json.loads((folder / "receipt.json").read_bytes())
            for k, folder in (("r2", args.r2_dir), ("ipfs", args.ipfs_dir))}
    pins = {k: bytes.fromhex((folder / "public-key.hex").read_text().strip())
            for k, folder in (("r2", args.r2_dir), ("ipfs", args.ipfs_dir))}
    result = audit(
        report, r2_receipt=docs["r2"], ipfs_receipt=docs["ipfs"],
        r2_pub=pins["r2"], ipfs_pub=pins["ipfs"], now=int(time.time()),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
