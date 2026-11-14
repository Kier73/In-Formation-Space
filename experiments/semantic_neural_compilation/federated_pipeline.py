"""SNC-004: independent GitHub runner fixtures for federated mathematical cache.

Each role constructs its own policy from checked-in source descriptions.
Only the untrusted exported capsule passes from sender to receiving job.
No sender policy, private key, shared SQLite or trust decision is exported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from independent_certificate_checker import hash_bytes
from federated_capsule import export_from_host, receiver_run
from persistent_host import POLICY_SCHEMA, PersistentSemanticHost, canonical, sha

HERE = Path(__file__).resolve().parent


def policy_from_local_source(out: Path, example: str, alias: str) -> dict:
    examples = json.loads((HERE / "examples.json").read_text())
    semantics = examples[example]
    policy = {"schema": POLICY_SCHEMA, "models": {alias: hash_bytes(semantics)}}
    out.write_bytes(canonical(policy))
    return policy


def produce(folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    policy = folder / "producer-policy.json"
    identity = policy_from_local_source(policy, "clamp_0_1", "source_clamp")
    examples = json.loads((HERE / "examples.json").read_text())
    host = PersistentSemanticHost(folder / "producer.sqlite3", policy)
    observed = host.observe(model="source_clamp", coordinate="1/2",
                            request_id="source-seed", source=examples["clamp_0_1"])
    if observed["cache_state"] != "constructed-verified":
        raise RuntimeError("producer did not construct exact source")
    capsule = export_from_host(host, "source_clamp")
    (folder / "portable-model.json").write_bytes(capsule)
    # The exported artifact is portable; local producer policy is NOT
    # included in the artifact upload step.
    result = {
        "schema": "in-formation-space.snc004.producer-report/0.1",
        "status": "untrusted-verified-capsule-export",
        "source_semantic_sha256": identity["models"]["source_clamp"],
        "network_sha256": observed["receipt"]["generated_network_sha256"],
        "export_bytes": len(capsule), "export_sha256": sha(capsule),
        "producer_database_not_transmitted": True,
        "producer_policy_not_transmitted": True,
    }
    (folder / "producer-report.json").write_bytes(canonical(result))
    return result


def receive(folder: Path, source_file: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    policy = folder / "receiver-policy.json"
    identity = policy_from_local_source(policy, "clamp_0_1", "clamp")
    # "clamp" is a receiver-owned alias, deliberately different from
    # the exporter's local "source_clamp" alias.
    result = receiver_run(
        capsule=source_file, database=folder / "receiver.sqlite3",
        policy=policy, model="clamp", coordinate="3/4",
        request_id="import-observe",
        output=folder / "receiver-report.json",
    )
    report = result["import"]
    if report["source_semantic_sha256"] != identity["models"]["clamp"] or \
            report["model_compiler_ran_at_receiver"] is not False:
        raise RuntimeError("receiver failed to independently admit source")
    if result["observation"]["receipt"]["outputs"] != ["3/4"]:
        raise RuntimeError("receiver did not compute exact expected output")
    # This is a separate host object, not a new receiving job. It additionally
    # demonstrates idempotent local persistence before artifact handoff.
    restarted = PersistentSemanticHost(folder / "receiver.sqlite3", policy)
    again = restarted.observe(model="clamp", coordinate="3/4",
                              request_id="import-observe")
    if (again["cache_state"], again["disposition"], again["construction_ns"]) != (
        "restored-verified", "idempotent-replay", 0):
        raise RuntimeError("receiver did not durably restore imported model")
    return {
        "schema": "in-formation-space.snc004.receiver-summary/0.1",
        "status": "independent-verified-admission-and-restoration",
        "receiver_semantic_sha256": identity["models"]["clamp"],
        "import_verification_ns": report["independent_certificate_verification_ns"],
        "restoration_verification_ns": again["independent_verification_ns"],
        "source_file_bytes": source_file.stat().st_size,
        "source_file_sha256": sha(source_file.read_bytes()),
        "fresh_process_rebuild_required": False,
        "origin_signature_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="role", required=True)
    sender = sub.add_parser("producer")
    sender.add_argument("--directory", type=Path, required=True)
    receiver = sub.add_parser("receiver")
    receiver.add_argument("--directory", type=Path, required=True)
    receiver.add_argument("--capsule", type=Path, required=True)
    args = parser.parse_args()
    report = produce(args.directory) if args.role == "producer" else \
        receive(args.directory, args.capsule)
    if args.role == "receiver":
        (args.directory / "receiver-summary.json").write_bytes(canonical(report))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
