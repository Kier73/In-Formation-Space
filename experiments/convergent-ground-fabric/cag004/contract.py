"""CAG-004: one signed mathematical intention, multiple physical host topologies.

All code is a finite typed research contract. The source public key is trusted
only after separately verifying the exact GitHub workflow attestation of the
key record. The private key stays in the publisher job.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SCHEMA = "in-formation.cag004-intent/0.1"
SIGN_SCHEMA = "in-formation.cag004-signed-intent/0.1"
TRUST_SCHEMA = "in-formation.cag004-ephemeral-trust/0.1"
INTERNAL_SCHEMA = "in-formation.cag004-internal-loci/0.1"
EXTERNAL_SCHEMA = "in-formation.cag004-receiver-locus/0.1"
AUDIT_SCHEMA = "in-formation.cag004-topology-audit/0.1"
OPERATOR = "cag004.lcg-affine-projection@1"
ISSUER = "Kier73/In-Formation-Space/.github/workflows/cag004-topology-neutral.yml@refs/heads/main"
SHN_REFERENCE = "3a81f1c386b1fc223cc0aec354c099c8c1f717a5"
ECPU_RECEIVER_REFERENCE = "3b57adcc2baaaa7e56e4bab943946f4e87e95c65"
COORDINATES = (0, 7, 1024, 10**15 + 137)
M = 65536
SHA = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")


class TopologyError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise TopologyError(reason)


def canonical(doc: Any) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(doc: Any) -> str:
    return hashlib.sha256(canonical(doc)).hexdigest()


def persist(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(doc) + b"\n")


def read(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    require(raw.endswith(b"\n") and len(raw) < 262144, "unbounded or unterminated document")
    obj = json.loads(raw)
    require(type(obj) is dict and canonical(obj) + b"\n" == raw, "noncanonical JSON document")
    return obj


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def unb64(value: Any, length: int) -> bytes:
    require(type(value) is str and len(value) < 256, "unbounded base64 field")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise TopologyError("invalid base64") from exc
    require(len(raw) == length and b64(raw) == value, "noncanonical base64 length")
    return raw


def state_at(t: int) -> int:
    """Independent O(log t) affine-composition oracle for x'=5x+1 mod 65536."""
    require(type(t) is int and 0 <= t <= 10**18, "invalid coordinate")
    a, b = 1, 0
    pa, pb = 5, 1
    while t:
        if t & 1:
            a, b = (pa * a) % M, (pa * b + pb) % M
        pa, pb = (pa * pa) % M, (pa * pb + pb) % M
        t >>= 1
    return (a * 7 + b) % M


def observed_at(t: int) -> int:
    return (3 * state_at(t) + 11) % M


def iterative_at(t: int) -> int:
    require(type(t) is int and 0 <= t <= 2048, "iterative oracle is bounded")
    x = 7
    for _ in range(t):
        x = (5 * x + 1) % M
    return (3 * x + 11) % M


def intent() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "operator": OPERATOR,
        "ecpu_shn_revision": SHN_REFERENCE,
        "law": {"modulus": M, "multiplier": 5, "increment": 1, "initial": 7,
                "projection_multiplier": 3, "projection_increment": 11},
        "jobs": [{"job_id": f"orbit-{n}", "coordinate": n} for n in COORDINATES],
        "scope": "pure observer-side finite affine projection, no external effects",
    }


def issue(private: Ed25519PrivateKey | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    key = private if private is not None else Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    statement = intent()
    trust = {
        "schema": TRUST_SCHEMA, "issuer_workflow": ISSUER, "epoch": 1,
        "key_id": hashlib.sha256(public).hexdigest(),
        "public_key_b64": b64(public),
        "intent_digest": digest(statement),
        "limit": "GitHub-main-workflow-scoped ephemeral public key, not independent publisher authority",
    }
    signed = {
        "schema": SIGN_SCHEMA, "key_id": trust["key_id"], "statement": statement,
        "signature_b64": b64(key.sign(canonical(statement))),
    }
    return signed, trust


def verify_intent(signed: Mapping[str, Any], trust: Mapping[str, Any]) -> dict[str, Any]:
    require(type(trust) is dict and set(trust) == {
        "schema", "issuer_workflow", "epoch", "key_id", "public_key_b64", "intent_digest", "limit"},
        "unexpected publisher trust record")
    require(trust["schema"] == TRUST_SCHEMA and trust["issuer_workflow"] == ISSUER
            and type(trust["epoch"]) is int and trust["epoch"] == 1
            and trust["limit"] == "GitHub-main-workflow-scoped ephemeral public key, not independent publisher authority",
            "unadmitted source authority/epoch")
    public = unb64(trust["public_key_b64"], 32)
    require(trust["key_id"] == hashlib.sha256(public).hexdigest(), "public key fingerprint mismatch")
    require(type(signed) is dict and set(signed) == {
        "schema", "key_id", "statement", "signature_b64"}
        and signed["schema"] == SIGN_SCHEMA and signed["key_id"] == trust["key_id"],
        "signed statement fields invalid")
    statement = signed["statement"]
    require(type(statement) is dict and statement == intent()
            and digest(statement) == trust["intent_digest"],
            "source intention differs from independently declared exact contract")
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(
            unb64(signed["signature_b64"], 64), canonical(statement))
    except InvalidSignature as exc:
        raise TopologyError("publisher Ed25519 signature invalid") from exc
    return statement


def semantic_result(job: Mapping[str, Any], value: int, statement: Mapping[str, Any]) -> str:
    return digest({"operator": OPERATOR, "source_digest": digest(statement),
                   "job_id": job["job_id"], "coordinate": job["coordinate"],
                   "observed_value": value})


def packet(job: Mapping[str, Any], phase: str, value: int | None,
           trace: list[str]) -> dict[str, Any]:
    return {"schema": "mailcpu.self-hosted-port-packet.v1",
            "job_id": job["job_id"], "coordinate": job["coordinate"],
            "phase": phase, "value": value, "trace": trace}


def internal_receipts(job: Mapping[str, Any]) -> tuple[list[str], int]:
    """Independently recreate SHN-001's two bounded unsigned content digests."""
    value = state_at(job["coordinate"])
    request = packet(job, "request", None, [])
    nav_receipt = digest({"host": "navigator", "input_digest": digest(request),
                          "value": value, "operation": "lcg_navigate.v1"})
    navigated = packet(job, "navigated", value, [nav_receipt])
    projected = observed_at(job["coordinate"])
    project_receipt = digest({"host": "projector", "input_digest": digest(navigated),
                              "value": projected, "operation": "affine_projection.v1"})
    final = packet(job, "projected", projected, [nav_receipt, project_receipt])
    return [nav_receipt, project_receipt], sum(len(canonical(p)) for p in
                                               (request, navigated, final))


def seal_report(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "report_digest": digest(body)}


def validate_report(report: Mapping[str, Any], schema: str,
                    statement: Mapping[str, Any]) -> None:
    require(type(report) is dict and report.get("schema") == schema,
            "wrong topology report schema")
    body = {k: v for k, v in report.items() if k != "report_digest"}
    require(report.get("report_digest") == digest(body), "topology report digest mismatch")
    require(report.get("source_digest") == digest(statement),
            "topology report refers to a different signed intention")


def verify(internal: Mapping[str, Any], receiver: Mapping[str, Any],
           signed: Mapping[str, Any], trust: Mapping[str, Any]) -> dict[str, Any]:
    statement = verify_intent(signed, trust)
    validate_report(internal, INTERNAL_SCHEMA, statement)
    validate_report(receiver, EXTERNAL_SCHEMA, statement)
    require(internal.get("shn_revision") == SHN_REFERENCE and
            receiver.get("ecpu_revision") == ECPU_RECEIVER_REFERENCE,
            "host implementation revisions do not match pinned roles")
    internal_rows = internal.get("observations")
    receiver_rows = receiver.get("observations")
    require(type(internal_rows) is list and len(internal_rows) == 2 * len(COORDINATES)
            and type(receiver_rows) is list and len(receiver_rows) == len(COORDINATES),
            "incomplete or extra observer topology")
    attestations = []
    for job in statement["jobs"]:
        coordinate = job["coordinate"]
        expected = observed_at(coordinate)
        if coordinate <= 2048:
            require(expected == iterative_at(coordinate), "independent iterative oracle disagrees")
        expected_semantic = semantic_result(job, expected, statement)
        expected_receipts, expected_bytes = internal_receipts(job)
        for ports in (1, 2):
            hits = [r for r in internal_rows if type(r) is dict
                    and r.get("job_id") == job["job_id"] and r.get("physical_boundary_ports") == ports]
            require(len(hits) == 1, "missing or duplicate interior topology observation")
            obs = hits[0]
            require(set(obs) == {
                "schema", "job_id", "requested_coordinate", "observed_value",
                "physical_boundary_ports", "logical_observer_hosts",
                "internal_virtual_interfaces", "internal_link_count",
                "interpreter_quanta", "internal_payload_bytes", "external_payload_bytes",
                "materialized_orbit_intermediate_states", "navigation_algorithm",
                "observer_receipts", "journal_verified",
                "independent_physical_execution_claimed", "hardware_port_emulation_verified",
                "semantic_result_digest", "restored_phases", "local_elapsed_ns",
            }, "unexpected internal resource fields")
            require(obs["requested_coordinate"] == coordinate
                    and type(obs["observed_value"]) is int and obs["observed_value"] == expected
                    and obs["semantic_result_digest"] == expected_semantic
                    and obs["observer_receipts"] == expected_receipts
                    and obs["internal_payload_bytes"] == expected_bytes
                    and obs["interpreter_quanta"] == 3
                    and obs["logical_observer_hosts"] == 3
                    and obs["internal_virtual_interfaces"] == 6
                    and obs["internal_link_count"] == 3
                    and obs["external_payload_bytes"] == 0
                    and obs["materialized_orbit_intermediate_states"] == 0
                    and obs["navigation_algorithm"] == "mailcpu.law_certifier.lcg_navigate"
                    and obs["journal_verified"] is True
                    and obs["independent_physical_execution_claimed"] is False
                    and obs["hardware_port_emulation_verified"] is False
                    and obs["restored_phases"] == ["navigator", "projector", "dispatcher", "done"]
                    and type(obs["local_elapsed_ns"]) is int and obs["local_elapsed_ns"] >= 0,
                    "internal observation or resource account changed")
        matches = [r for r in receiver_rows if type(r) is dict and r.get("job_id") == job["job_id"]]
        require(len(matches) == 1, "missing or duplicated external receiver observation")
        ext = matches[0]
        require(set(ext) == {
            "job_id", "coordinate", "observed_value", "semantic_result_digest",
            "workload_digest", "operator_contract_digest", "hypervisor_allow",
            "hypervisor_replayed", "hypervisor_denied", "handler_invocations",
            "receiver_journal_verified", "receiver_local_elapsed_ns",
        }, "unexpected receiver resource/authority fields")
        require(ext["coordinate"] == coordinate and ext["observed_value"] == expected
                and ext["semantic_result_digest"] == expected_semantic
                and type(ext["workload_digest"]) is str and SHA.fullmatch(ext["workload_digest"]) is not None
                and type(ext["operator_contract_digest"]) is str
                and SHA.fullmatch(ext["operator_contract_digest"]) is not None
                and ext["hypervisor_allow"] is True and ext["hypervisor_replayed"] is True
                and ext["hypervisor_denied"] is True and ext["handler_invocations"] == 1
                and ext["receiver_journal_verified"] is True
                and type(ext["receiver_local_elapsed_ns"]) is int and ext["receiver_local_elapsed_ns"] >= 0,
                "receiver mathematical observation or local authorization claim failed")
        attestations.append({"job_id": job["job_id"], "coordinate": coordinate,
                             "observed_value": expected,
                             "semantic_result_digest": expected_semantic,
                             "topologies": ["internal-one-port", "internal-two-port", "separate-receiver"]})
    require(internal.get("execution_domain") == "one E-CPU interpreter, internal OwnedNetworkFabric"
            and receiver.get("execution_domain") == "independent GitHub-hosted E-CPU Hypervisor receiver"
            and receiver.get("external_link_claim") == "GitHub Actions artifact transfer, physical byte rate not measured",
            "physical execution domains misrepresented")
    body = {
        "schema": AUDIT_SCHEMA,
        "status": "same_semantics_distinct_topology_accounting",
        "source_digest": digest(statement),
        "internal_report_digest": internal["report_digest"],
        "receiver_report_digest": receiver["report_digest"],
        "results": attestations,
        "falsifiable_boundaries": [
            "Three internal hosts share ONE interpreter and crash domain; they do not provide three processors.",
            "The one/two external ports are declared capacity budgets, unused by SHN-001; no silicon port timing measured.",
            "The remote receiver is a separate GitHub workflow job connected through artifact transfer, not a separate WAN/provider.",
            "The public key is a GitHub-workflow-attested ephemeral identity, not an independent publisher authorization.",
            "The verifier recomputes pure math and checks attested report claims; it does not witness hypervisor execution directly.",
            "Wall-clock and local elapsed durations from different jobs cannot be subtracted as synchronized times.",
            "Only this bounded affine recurrence can use O(log t) navigation; no arbitrary state-space shortcut is implied.",
        ],
    }
    return seal_report(body)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("issue", "verify"))
    p.add_argument("--directory", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "issue":
            signed, trust = issue()
            persist(args.directory / "signed-intent.json", signed)
            persist(args.directory / "issuer-trust.json", trust)
            result = {"status": "signed_intent_created",
                      "source_digest": digest(signed["statement"])}
        else:
            signed = read(args.directory / "signed-intent.json")
            trust = read(args.directory / "issuer-trust.json")
            report = verify(read(args.directory / "internal-report.json"),
                            read(args.directory / "receiver-report.json"), signed, trust)
            persist(args.directory / "auditor-report.json", report)
            result = {"status": report["status"], "digest": report["report_digest"]}
        print(json.dumps(result, sort_keys=True))
    except (TopologyError, OSError, ValueError, KeyError, TypeError) as exc:
        p.exit(1, f"CAG-004 refused: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
