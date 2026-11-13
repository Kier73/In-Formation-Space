"""Independent COE-002 artifact consumer. Imports no certificate constructor."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from independent_certificate_checker import CertificateError, verify_json_bytes

# Pinned expectations are declared in this consumer, not supplied by the
# certificate-producing job. These are test identities, not trust anchors for
# a production deployment or signatures on an external developer's work.
EXPECTED_NETWORK_DIGESTS = {
    "identity": "4cdb6f67907dd5286cd9ef7b073761fe876ec61090ed6db92dd6b676fcdad09d",
    "relu_identity": "df076e896b0b2c760a1f3fd7731f33a2377cd850458a6bb5518bc80e36fb8508",
    "zero": "ee6c630e6497be8396be01184a555c6c4287d0d56fedab76e5b0f3bc089c632f",
    "triangular_bump": "19d42b0402acac39e255920842e73a28a3e364e96211dc623f8c717ed1285571",
    "rescaled_bump": "f6c4916fa52ca096ebd7de65f0cd9eb722fd581be06591b94fe52332fd717eb1",
}


def independently_verify(directory: Path) -> dict[str, object]:
    observed = {p.name for p in directory.iterdir() if p.is_file()}
    expected_files = {f"{key}.json" for key in EXPECTED_NETWORK_DIGESTS}
    if observed != expected_files:
        raise CertificateError(f"unexpected certificate file manifest: {sorted(observed ^ expected_files)}")
    verified = {}
    for name, source in sorted(EXPECTED_NETWORK_DIGESTS.items()):
        raw = (directory / f"{name}.json").read_bytes()
        result = verify_json_bytes(raw, expected_network_sha256=source)
        result["certificate_sha256"] = hashlib.sha256(raw).hexdigest()
        verified[name] = result
    if verified["identity"]["semantic_sha256"] != verified["relu_identity"]["semantic_sha256"]:
        raise CertificateError("identity and ReLU identity must be semantically equivalent")
    if verified["triangular_bump"]["semantic_sha256"] != verified["rescaled_bump"]["semantic_sha256"]:
        raise CertificateError("positive homogeneous rescaling must retain semantics")
    if verified["zero"]["semantic_sha256"] == verified["triangular_bump"]["semantic_sha256"]:
        raise CertificateError("zero and triangular bump must differ on the real domain")
    return {
        "schema": "in-formation-space.coe002.independent-check-report/0.1",
        "status": "all_verified",
        "claims": verified,
        "claim_count": len(verified),
        "atomic_cells_checked": sum(v["atomic_cells_checked"] for v in verified.values()),
        "independence_scope": "separate Python process; standalone checker code and separate hosted CI job",
        "trust_scope": "reviewed repository fixture digests; no independent key or external signature",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = independently_verify(args.input_dir)
    contents = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(contents, encoding="utf-8")
    else:
        print(contents, end="")


if __name__ == "__main__":
    main()
