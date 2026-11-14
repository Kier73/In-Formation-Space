"""PON-002: independent off-route reconstruction of dual public-provider evidence.

Checks signed short-lived *test* grants, receiver-owned root digest, both
providers' exact reported observations, and recomputes CAG-001 mathematics
directly from the separately pinned repository fixture.

The grants demonstrate cryptographic verification but their ephemeral public
keys are carried *inside their reports*. Without separately pinned keys or
authenticated GitHub artifact provenance they do not authenticate an issuer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from convergent_fabric import Replica
from passive_orbit import ROOT_PIN, HERE, checked_manifest, checked_packet, canonical, digest
from pon002_orbit import check_grant, REPORT_SCHEMA


class AuditRejected(ValueError):
    pass


def ensure(ok: bool, reason: str) -> None:
    if not ok:
        raise AuditRejected(reason)


def read_report(raw: bytes, expected_operator: str, expected_commit: str) -> dict:
    ensure(type(raw) is bytes and 0 < len(raw) <= 50_000, "report size bound")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditRejected("unparseable report") from exc
    ensure(type(doc) is dict and canonical(doc) + b"\n" == raw and set(doc) == {
        "schema", "provider", "public_git_commit", "issuer_public_key_hex",
        "capability", "receiver_min_epoch", "observed_at_unix", "orbit",
    }, "unexpected or noncanonical provider report")
    ensure(doc["schema"] == "in-formation.pon002-provider-report/0.1" and
           doc["provider"] == expected_operator and
           doc["public_git_commit"] == expected_commit,
           "report belongs to wrong public provider or source revision")
    try:
        pub = bytes.fromhex(doc["issuer_public_key_hex"])
    except (TypeError, ValueError) as exc:
        raise AuditRejected("invalid ephemeral public key") from exc
    ensure(type(doc["issuer_public_key_hex"]) is str and
           len(doc["issuer_public_key_hex"]) == 64 and
           pub.hex() == doc["issuer_public_key_hex"],
           "noncanonical ephemeral issuer key")
    try:
        check_grant(
            grant=doc["capability"], pinned_key=pub,
            root_pin=ROOT_PIN,
            minimum_epoch=doc["receiver_min_epoch"],
            now=doc["observed_at_unix"])
    except (ValueError, TypeError, KeyError) as exc:
        raise AuditRejected("invalid signed ephemeral grant") from exc
    orbit = doc["orbit"]
    ensure(type(orbit) is dict and orbit.get("schema") == REPORT_SCHEMA and
           orbit.get("status") == "verified_reconstruction" and
           orbit.get("evaluation_status") == "locally_reconstructed_pure_result" and
           orbit.get("target") == "final" and
           orbit.get("value") == 44 and
           orbit.get("public_git_commit") == expected_commit and
           orbit.get("root_sha256") == ROOT_PIN and
           orbit.get("issuer_public_key_sha256") == digest(pub) and
           orbit.get("grant_epoch") == doc["capability"]["epoch"],
           "report does not match admitted mathematical source")
    ensure(orbit.get("delivery_operators") == [
        {"github": "GitHub", "jsdelivr": "jsDelivr"}[expected_operator]
    ] and orbit.get("provider_source_origins") == [
        "github.com/Kier73/In-Formation-Space"
    ], "reported delivery independence/source origin mismatch")
    ensure(orbit.get("passive_hosts_executed_arithmetic") is False and
           orbit.get("external_effects_authorized") is False and
           orbit.get("externally_authenticated_issuer") is False,
           "unsubstantiated remote execution or issuer claim")
    events = orbit.get("events")
    delivery = orbit.get("delivery_by_object")
    ensure(type(events) is list and type(delivery) is dict and
           len(events) == 6 and len(delivery) == 6,
           "provider did not report every root and dependency object")
    expected_names = {"root", "seed", "left", "right", "merge", "final"}
    ensure(set(delivery) == expected_names and
           {e.get("object") for e in events} == expected_names and
           all(e.get("provider") == expected_operator and
               e.get("operator") == orbit["delivery_operators"][0] and
               e.get("status") == "verified" and
               e.get("source_origin") == orbit["provider_source_origins"][0] and
               type(e.get("elapsed_ns_local")) is int and
               e["elapsed_ns_local"] >= 0
               for e in events) and
           all(s.get("provider") == expected_operator and
               s.get("operator") == orbit["delivery_operators"][0]
               for s in delivery.values()),
           "reported object receipts are not from the expected HTTPS operator")
    ensure(orbit.get("verified_objects") == 5 and
           orbit.get("total_manifest_objects") == 5 and
           orbit.get("missing") == [] and
           orbit.get("reachable_closure_ids") == sorted(expected_names - {"root"}),
           "incomplete or reordered dependency set")
    core = {k: v for k, v in orbit.items() if k != "evidence_digest"}
    ensure(orbit.get("evidence_digest") == digest(canonical(core)),
           "evidence receipt hash mismatch")
    return orbit


def independent_reference(public: Path) -> dict:
    manifest_raw = (public / "manifest.json").read_bytes()
    manifest = checked_manifest(manifest_raw, ROOT_PIN)
    replica = Replica()
    for ref in manifest["objects"]:
        raw = (public / "objects" / (ref["object_sha256"] + ".json")).read_bytes()
        packet = checked_packet(raw, identity=ref["semantic_id"],
                                address=ref["object_sha256"])
        replica.ingest(packet, route="independent-checked-in-reference")
    result = replica.evaluate(manifest["target"])
    ensure(result["status"] == "locally_reconstructed_pure_result" and
           result["value"] == 44, "auditor independent source incomplete")
    return result


def audit(raw_github: bytes, raw_jsdelivr: bytes, *, commit: str,
          public: Path = HERE / "public") -> dict:
    ensure(type(commit) is str and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit)
           is not None, "auditor requires full Git commit")
    github = read_report(raw_github, "github", commit)
    cdn = read_report(raw_jsdelivr, "jsdelivr", commit)
    reference = independent_reference(public)
    for name, orbit in (("github", github), ("jsdelivr", cdn)):
        ensure(orbit["result_digest"] == reference["result_digest"] and
               orbit["lineage"] == reference["lineage"] and
               orbit["value"] == reference["value"],
               f"{name} reported result differs from independent reconstruction")
    return {
        "schema": "in-formation.pon002-third-party-audit/0.1",
        "status": "two-public-delivery-operators-converged-on-receiver-verified-orbit",
        "source_git_commit": commit,
        "source_root_sha256": ROOT_PIN,
        "verified_result": 44,
        "reference_result_digest": reference["result_digest"],
        "github_evidence_sha256": digest(raw_github),
        "jsdelivr_evidence_sha256": digest(raw_jsdelivr),
        "distinct_delivery_operators": ["GitHub", "jsDelivr"],
        "distinct_source_origins": 1,
        "common_source_dependency": "both public providers obtain data from GitHub repository",
        "each_provider_reported_full_https_retrieval": True,
        "ephemeral_root_grants_verified_as_signed": True,
        "independent_publisher_signature_authenticated": False,
        "real_provider_storage_independence_proven": False,
        "host_physical_independence_attested": False,
        "actual_in_transit_router_computation": False,
        "observer_locally_realized_arithmetic": True,
        "external_execution_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-report", type=Path, required=True)
    parser.add_argument("--jsdelivr-report", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        args.github_report.read_bytes(), args.jsdelivr_report.read_bytes(),
        commit=args.commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
