"""SNC-004: portable, untrusted neural certificate and receiver-owned admission.

A sending host exports only materialized certificate bytes. A different host
may independently verify and install those bytes if *its own* semantic policy
admits their exact mathematical meaning. The sender cannot grant authority.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

from compiler import AtlasRejected
from independent_certificate_checker import CertificateError
from persistent_host import (
    COMPILER_ID, HostRejected, PersistentSemanticHost, canonical, exact_object,
    require, sha,
)
from verifier import strict_json

FORMAT = "in-formation-space.snc004.untrusted-model-capsule/0.1"
MAX_BYTES = 256_000


def _capsule_bytes(doc: object) -> bytes:
    require(type(doc) is dict, "missing inner SNC-001 capsule")
    result = canonical(doc)
    require(0 < len(result) <= MAX_BYTES, "certificate byte budget")
    return result


def export_from_host(host: PersistentSemanticHost, model: str) -> bytes:
    """Export only a receiver-side verified persisted realization, no policy.

    Exporter authorization controls who may export locally; importers MUST
    ignore that decision and independently check their own source pins.
    """
    expected, local_policy_sha = host._policy(model)
    with host._connect() as con:
        row = con.execute(
            "SELECT network_sha, capsule_sha, capsule FROM realizations "
            "WHERE model=? AND semantic_sha=? AND compiler_id=?",
            (model, expected, COMPILER_ID),
        ).fetchone()
    require(row is not None, "no verified realization is stored for export")
    checked = host._hydrate(row[2], expected, row[0], row[1], local_policy_sha)
    inner = strict_json(row[2])
    wire = {
        "schema": FORMAT,
        "source_semantic_sha256": checked.semantic_sha256,
        "generated_network_sha256": checked.network_sha256,
        "snc001_capsule": inner,
    }
    body = canonical(wire)
    require(len(body) <= MAX_BYTES, "export byte budget")
    return body


def import_on_host(host: PersistentSemanticHost, model: str, body: bytes
                   ) -> dict[str, object]:
    """Reconstruct exact real semantics independently before durably admitting.

    Idempotent repeated imports must not rewrite an existing realization.
    A conflicting realization under the same (model, semantics, compiler)
    address fails closed, even if its mathematical outputs might coincide.
    """
    require(type(body) is bytes and 0 < len(body) <= MAX_BYTES,
            "unbounded federation payload")
    try:
        value = strict_json(body)
    except CertificateError as exc:
        raise HostRejected("noncanonical federation document") from exc
    exact_object(value, {"schema", "source_semantic_sha256",
                         "generated_network_sha256", "snc001_capsule"},
                 "federated capsule")
    require(value["schema"] == FORMAT, "unsupported federation schema")
    expected, policy_sha = host._policy(model)
    require(value["source_semantic_sha256"] == expected,
            "federated meaning contradicts receiver-owned source policy")
    inner = _capsule_bytes(value["snc001_capsule"])
    declared_network = value["generated_network_sha256"]
    require(type(declared_network) is str and len(declared_network) == 64,
            "invalid generated network identity")
    started = time.perf_counter_ns()
    # This repeats the complete COE-002 mathematical certificate check at B.
    imported = host._hydrate(
        inner, expected, declared_network, sha(inner), policy_sha)
    verification_ns = time.perf_counter_ns() - started

    with host._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        prior = con.execute(
            "SELECT network_sha, capsule_sha, capsule FROM realizations "
            "WHERE model=? AND semantic_sha=? AND compiler_id=?",
            (model, expected, COMPILER_ID),
        ).fetchone()
        if prior is not None:
            # Do not silently overwrite a damaged or alternate identity.
            host._hydrate(prior[2], expected, prior[0], prior[1], policy_sha)
            require(prior[0] == imported.network_sha256 and
                    prior[1] == sha(inner) and prior[2] == inner,
                    "conflicting existing semantic realization")
            disposition = "idempotent-existing-verified"
        else:
            con.execute(
                "INSERT INTO realizations "
                "(model, semantic_sha, compiler_id, network_sha, capsule_sha, capsule) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (model, expected, COMPILER_ID,
                 imported.network_sha256, sha(inner), inner),
            )
            disposition = "imported-independently-verified"
    # Never retain a prior memo with different policy or realization bytes.
    host._memo.pop(model, None)
    return {
        "schema": "in-formation-space.snc004.receiver-import/0.1",
        "status": "admitted-to-local-mathematical-cache",
        "disposition": disposition,
        "model": model,
        "source_semantic_sha256": expected,
        "generated_network_sha256": imported.network_sha256,
        "import_document_sha256": sha(body),
        "independent_certificate_verification_ns": verification_ns,
        "model_compiler_ran_at_receiver": False,
        "external_execution_authorized": False,
        "origin_authenticated_by_capsule": False,
    }


def receiver_run(
    *, capsule: Path, database: Path, policy: Path, model: str,
    coordinate: str, request_id: str, output: Path,
) -> dict[str, object]:
    host = PersistentSemanticHost(database, policy)
    body = capsule.read_bytes()
    imported = import_on_host(host, model, body)
    observed = host.observe(model=model, coordinate=coordinate,
                            request_id=request_id)
    require(observed["construction_ns"] == 0 and
            observed["cache_state"] == "restored-verified",
            "import was not independently restored without compilation")
    result = {
        "schema": "in-formation-space.snc004.receiver-report/0.1",
        "model": model, "import": imported, "observation": observed,
        "origin_document_sha256": sha(body),
        "authority_scope": "receiver-local exact mathematical cache only",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical(result))
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    exporter = sub.add_parser("export")
    exporter.add_argument("--database", type=Path, required=True)
    exporter.add_argument("--policy", type=Path, required=True)
    exporter.add_argument("--model", required=True)
    exporter.add_argument("--output", type=Path, required=True)
    receiver = sub.add_parser("receive")
    receiver.add_argument("--capsule", type=Path, required=True)
    receiver.add_argument("--database", type=Path, required=True)
    receiver.add_argument("--policy", type=Path, required=True)
    receiver.add_argument("--model", required=True)
    receiver.add_argument("--coordinate", required=True)
    receiver.add_argument("--request-id", required=True)
    receiver.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "export":
        host = PersistentSemanticHost(args.database, args.policy)
        raw = export_from_host(host, args.model)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
        print(json.dumps({"status": "untrusted-export",
                          "document_sha256": sha(raw), "bytes": len(raw)}))
    else:
        print(json.dumps(receiver_run(
            capsule=args.capsule, database=args.database, policy=args.policy,
            model=args.model, coordinate=args.coordinate,
            request_id=args.request_id, output=args.output),
            indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
