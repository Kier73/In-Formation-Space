"""SNC-004: third-host reconstruction without using the sender's compiler.

The auditor trusts its own checked-in semantic source and the independent
COE-002 certificate checker. GitHub artifact delivery is evidence transport,
not a cryptographic signature of the model's real-world origin.
"""
from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path

from independent_certificate_checker import (
    CertificateError, hash_bytes, parse_network, rational,
)
from verifier import strict_json, verify_capsule

EXPORT_SCHEMA = "in-formation-space.snc004.untrusted-model-capsule/0.1"
IMPORT_SCHEMA = "in-formation-space.snc004.receiver-import/0.1"
REPORT_SCHEMA = "in-formation-space.snc004.receiver-report/0.1"
RECEIPT_SCHEMA = "in-formation-space.snc003.observation-receipt/0.1"


class AuditRejected(ValueError):
    pass


def check(condition: bool, why: str) -> None:
    if not condition:
        raise AuditRejected(why)


def canonical(data: object) -> bytes:
    return json.dumps(data, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"


def sha(raw: bytes) -> str:
    from hashlib import sha256
    return sha256(raw).hexdigest()


def independent_direct_network_value(network: object,
                                     x: Fraction) -> list[str]:
    """Standalone rational network interpretation; imports no SNC compiler."""
    layers = parse_network(network)
    values: tuple[Fraction, ...] = (x,)
    for activation, weights, biases in layers:
        values = tuple(
            sum((weight * coordinate for weight, coordinate in zip(row, values)),
                bias)
            for row, bias in zip(weights, biases)
        )
        if activation == "relu":
            values = tuple(max(Fraction(0), value) for value in values)
    return [str(value) for value in values]


def audit(*, body: bytes, receiver_report: bytes, expected_source: object,
          expected_model: str, expected_coordinate: str,
          expected_request_id: str) -> dict[str, object]:
    expected = hash_bytes(expected_source)
    try:
        export = strict_json(body)
        report = strict_json(receiver_report)
    except CertificateError as exc:
        raise AuditRejected("noncanonical audit evidence") from exc
    check(type(export) is dict and set(export) == {
        "schema", "source_semantic_sha256", "generated_network_sha256",
        "snc001_capsule",
    } and export["schema"] == EXPORT_SCHEMA,
          "invalid exported proof schema")
    check(export["source_semantic_sha256"] == expected,
          "export is not the independently expected source meaning")
    inner = export["snc001_capsule"]
    check(type(inner) is dict, "missing inner proof")
    try:
        certificate_report = verify_capsule(canonical(inner),
                                            expected_source_sha256=expected)
    except CertificateError as exc:
        raise AuditRejected("invalid exported certificate") from exc
    check(export["generated_network_sha256"] ==
          certificate_report["generated_network_sha256"],
          "declared generated network identity mismatch")
    check(inner["source_semantic_atlas"] == expected_source,
          "source atlas differs from independently checked-in source")

    check(type(report) is dict and set(report) == {
        "schema", "model", "import", "observation",
        "origin_document_sha256", "authority_scope",
    } and report["schema"] == REPORT_SCHEMA and
          report["model"] == expected_model and
          report["origin_document_sha256"] == sha(body),
          "receiving host report has wrong source or scope")
    imported = report["import"]
    check(type(imported) is dict and imported.get("schema") == IMPORT_SCHEMA and
          imported.get("status") == "admitted-to-local-mathematical-cache" and
          imported.get("source_semantic_sha256") == expected and
          imported.get("generated_network_sha256") ==
          certificate_report["generated_network_sha256"] and
          imported.get("import_document_sha256") == sha(body) and
          imported.get("model_compiler_ran_at_receiver") is False and
          imported.get("external_execution_authorized") is False,
          "receiving host did not independently admit exact meaning")
    observation = report["observation"]
    check(type(observation) is dict and
          observation.get("status") == "verified-exact-mathematical-observation" and
          observation.get("construction_ns") == 0 and
          observation.get("cache_state") == "restored-verified" and
          observation.get("external_execution_authorized") is False,
          "incorrect cached observation status")
    receipt = observation["receipt"]
    check(type(receipt) is dict and set(receipt) == {
        "schema", "request_id", "model", "semantic_sha256",
        "generated_network_sha256", "coordinate", "outputs", "arithmetic",
    } and receipt["schema"] == RECEIPT_SCHEMA and
          receipt["model"] == expected_model and
          receipt["request_id"] == expected_request_id and
          receipt["coordinate"] == expected_coordinate and
          receipt["semantic_sha256"] == expected and
          receipt["generated_network_sha256"] ==
          certificate_report["generated_network_sha256"] and
          receipt["arithmetic"] == "exact-rational-reference-evaluation",
          "observation identity is not grounded in expected source")
    check(observation["receipt_sha256"] == sha(canonical(receipt)),
          "receipt digest did not match exact bytes")
    check(receipt["outputs"] ==
          independent_direct_network_value(
              inner["generated_certificate"]["network"],
              rational(expected_coordinate)),
          "independently reconstructed mathematical output disagrees")

    return {
        "schema": "in-formation-space.snc004.third-host-audit/0.1",
        "status": "independent-full-domain-and-observation-reconstruction",
        "semantic_sha256": expected,
        "network_sha256": certificate_report["generated_network_sha256"],
        "input_coordinate": expected_coordinate,
        "independent_outputs": receipt["outputs"],
        "export_sha256": sha(body),
        "receipt_sha256": observation["receipt_sha256"],
        "mathematical_scope": "scalar-input exact rational affine/ReLU; all real inputs",
        "cross_host_network_transport_verified": False,
        "external_origin_authenticated": False,
        "ground_admitted": False,
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--receiver-report", type=Path, required=True)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--example-name", default="clamp_0_1")
    parser.add_argument("--model", default="clamp")
    parser.add_argument("--coordinate", default="3/4")
    parser.add_argument("--request-id", default="import-observe")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    examples = json.loads(args.examples.read_text())
    report = audit(
        body=args.capsule.read_bytes(),
        receiver_report=args.receiver_report.read_bytes(),
        expected_source=examples[args.example_name],
        expected_model=args.model,
        expected_coordinate=args.coordinate,
        expected_request_id=args.request_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
