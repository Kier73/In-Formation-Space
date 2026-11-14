"""SNC-001 independently checked semantic-to-neural capsule receiver.

This module never imports compiler.py, certificate_producer.py or the COE atlas
constructor. It checks the untrusted producer output with the independently
implemented COE-002 activation-cell proof checker.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys

COE = Path(__file__).resolve().parents[1] / "continuous-observation-equivalence"
sys.path.insert(0, str(COE))
from independent_certificate_checker import (  # noqa: E402
    CertificateError, hash_bytes, json_bytes, parse_network,
    require, verify_json_bytes,
)

SCHEMA = "in-formation-space.snc001.semantic-to-neural/0.1"


def strict_json(raw: bytes) -> object:
    require(type(raw) is bytes and 0 < len(raw) <= 8 * 1024 * 1024,
            "invalid capsule size")
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in pairs:
            require(key not in out, "duplicate capsule JSON key")
            out[key] = value
        return out
    try:
        decoded = json.loads(
            raw.decode("utf-8"), object_pairs_hook=unique,
            parse_constant=lambda _: require(False, "nonfinite JSON"),
        )
    except (ValueError, UnicodeError) as exc:
        raise CertificateError("invalid capsule JSON") from exc
    require(raw == json_bytes(decoded) + b"\n", "noncanonical capsule JSON")
    return decoded


def verify_capsule(
    raw: bytes, *,
    expected_source_sha256: str | None = None,
    expected_network_sha256: str | None = None,
    max_cells: int = 4096,
    max_scalar_ops: int = 3_000_000,
) -> dict[str, object]:
    cap = strict_json(raw)
    require(type(cap) is dict and set(cap) == {
        "schema", "source_semantic_atlas", "source_semantic_sha256",
        "generated_certificate",
    }, "unexpected capsule fields")
    require(cap["schema"] == SCHEMA, "unexpected capsule schema")
    source, source_sha = cap["source_semantic_atlas"], cap["source_semantic_sha256"]
    require(type(source) is list and 0 < len(source) <= 64,
            "source region count exceeded")
    require(type(source_sha) is str and hash_bytes(source) == source_sha,
            "source semantic digest mismatch")
    if expected_source_sha256 is not None:
        require(source_sha == expected_source_sha256,
                "source does not match verifier-owned semantic pin")

    cert = cap["generated_certificate"]
    require(type(cert) is dict, "missing generated neural certificate")
    # The legacy COE-002 checker is independent of the generating compiler.
    report = verify_json_bytes(
        json_bytes(cert) + b"\n",
        expected_network_sha256=expected_network_sha256,
        max_cells=max_cells, max_scalar_ops=max_scalar_ops,
    )
    require(cert["semantic_atlas"] == source and
            report["semantic_sha256"] == source_sha,
            "generated neural function differs from source meaning")
    model = parse_network(cert["network"])
    require(len(model) == 2 and model[0][0] == "relu" and model[1][0] == "linear",
            "expected two-layer constructive ReLU realization")
    require(len(model[0][1]) == len(source) + 1,
            "unexpected constructive hidden-layer width")
    require(len(model[1][1]) == len(source[0]["affines"]),
            "unexpected neural output width")

    return {
        "status": "exact-all-real-semantic-equivalence-verified",
        "source_semantic_sha256": source_sha,
        "generated_network_sha256": report["network_sha256"],
        "semantic_regions": report["semantic_regions"],
        "atomic_cells_checked": report["atomic_cells_checked"],
        "hidden_neurons": len(model[0][1]),
        "output_channels": len(model[1][1]),
        "scope": "scalar-real-input/rational-parameters/ideal-arithmetic",
        "authority_granted": False,
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capsule", type=Path)
    parser.add_argument("--expected-source-sha256", default=None)
    parser.add_argument("--expected-network-sha256", default=None)
    args = parser.parse_args()
    result = verify_capsule(
        args.capsule.read_bytes(),
        expected_source_sha256=args.expected_source_sha256,
        expected_network_sha256=args.expected_network_sha256,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
