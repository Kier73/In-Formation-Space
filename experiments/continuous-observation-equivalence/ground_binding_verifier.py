"""COE-004 independent consumer of proposed E-CPU computational Ground links.

Does not import producer or use its representation constructor. Source pins
and Ground/observer definitions are separately checked-out policy inputs, not
contents of the untrusted producer artifacts. Does not admit a Ground.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from independent_certificate_checker import verify_json_bytes
from mailcpu.semantic_translation import (
    ObservationContract, RepresentationRef, TranslationContract,
    canonical_value_digest,
)

SCHEMA = "in-formation-space.coe004.candidate-ground-certificate-binding/0.1"
KEYS = {
    "schema", "model_id", "ecpu_repository", "ecpu_revision", "ground_admission",
    "verification_status", "candidate_ground", "source_representation",
    "semantic_representation", "observation_contract", "translation_contract",
    "translation_digest", "certificate_file_sha256", "verified_network_sha256",
    "verified_semantic_sha256", "atomic_cells_checked",
}


class GroundLinkRejected(ValueError):
    pass


def required(ok: bool, why: str) -> None:
    if not ok:
        raise GroundLinkRejected(why)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def strict_json(raw: bytes) -> dict[str, Any]:
    required(type(raw) is bytes and 0 < len(raw) <= 8 * 1024 * 1024,
             "invalid link byte budget")

    def no_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            required(key not in out, "duplicate binding JSON key")
            out[key] = value
        return out
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicate,
                             parse_constant=lambda _: required(False, "nonfinite JSON"))
    except (ValueError, UnicodeError) as exc:
        raise GroundLinkRejected("invalid binding JSON") from exc
    required(type(payload) is dict and set(payload) == KEYS,
             "invalid or missing binding fields")
    required(raw == canonical(payload) + b"\n", "noncanonical binding JSON")
    return payload


def verify_one(model_id: str, raw_certificate: bytes, raw_binding: bytes,
               *, policy: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    required(model_id in policy["expected_network_sha256"], "unknown model source")
    claim = strict_json(raw_binding)
    required(claim["schema"] == SCHEMA, "unsupported binding schema")
    required(claim["model_id"] == model_id, "model label substitution")
    required(claim["ground_admission"] == "not-admitted", "false Ground admission claim")
    required(claim["verification_status"] == "exact-certificate-verified",
             "incorrect certificate status")
    required(profile["schema"] == "in-formation-space.coe004.computational-ground-profile/0.1"
             and profile["admission"] == "candidate-unadmitted", "unadmitted Ground profile required")
    required(profile["state_domain"] == "real-line-exact"
             and profile["arithmetic"] == "rational-parameters-ideal-real"
             and profile["input_schema"] == {"ordered": ["x"], "value_kind": "exact-real"}
             and profile["output_schema"] == {"ordered": ["y0"], "value_kind": "exact-real"},
             "unsupported candidate Ground language or arity")

    expected_network = policy["expected_network_sha256"][model_id]
    math_report = verify_json_bytes(raw_certificate, expected_network_sha256=expected_network)
    certificate = json.loads(raw_certificate)
    required(len(certificate["network"]["layers"][-1]["bias"]) == 1,
             "output width mismatches Ground profile")
    raw_digest = hashlib.sha256(raw_certificate).hexdigest()

    # Reconstruct E-CPU canonical identities from independent policy and from
    # the *already verified* certificate. Never trust refs supplied by producer.
    ground = RepresentationRef.from_payload(
        "ifs.coe004.computational-ground-profile", 1, profile)
    source = RepresentationRef.from_payload(
        "ifs.coe002.rational-relu-network", 1, certificate["network"])
    semantic = RepresentationRef.from_payload(
        "ifs.coe002.canonical-semantic-atlas", 1, certificate["semantic_atlas"])
    observer = ObservationContract.from_definition(
        "ifs.coe004.maximal-piecewise-affine-atlas", 1, profile["observer_definition"])
    mapping = RepresentationRef.from_payload(
        "ifs.coe004.certificate-backed-translation", 1,
        {"certificate_schema": certificate["schema"],
         "certificate_file_sha256": raw_digest,
         "verification_rule": "coe002.exact-all-real-activation-cell-replay/0.1"})
    context = canonical_value_digest({
        "candidate_ground": ground.to_dict(),
        "domain": "all-real-scalar-input",
        "arithmetic": "exact-rational",
        "observation": observer.to_dict(),
    })
    expected_contract = TranslationContract(
        contract_id="coe004.network-to-exact-semantic-atlas", revision=1,
        source=source, target=semantic, mapping=mapping,
        observation=observer, context_digest=context)
    try:
        received_contract = TranslationContract.from_dict(claim["translation_contract"])
    except (ValueError, TypeError, KeyError) as exc:
        raise GroundLinkRejected("invalid typed E-CPU translation contract") from exc
    required(received_contract.to_dict() == expected_contract.to_dict(),
             "source-to-semantic translation contract mismatch")
    required(claim["translation_digest"] == expected_contract.digest,
             "incorrect E-CPU translation digest")
    required(claim["candidate_ground"] == ground.to_dict(),
             "candidate Ground identity mismatch")
    required(claim["source_representation"] == source.to_dict(),
             "source representation mismatch")
    required(claim["semantic_representation"] == semantic.to_dict(),
             "semantic representation mismatch")
    required(claim["observation_contract"] == observer.to_dict(),
             "observer definition mismatch")
    required(claim["certificate_file_sha256"] == raw_digest,
             "certificate bytes not bound")
    required(claim["verified_network_sha256"] == math_report["network_sha256"],
             "certified network identity mismatch")
    required(claim["verified_semantic_sha256"] == math_report["semantic_sha256"],
             "certified semantic identity mismatch")
    required(type(claim["atomic_cells_checked"]) is int
             and claim["atomic_cells_checked"] == math_report["atomic_cells_checked"],
             "incorrect evidence coverage")
    required(claim["ecpu_repository"] == policy["ecpu_repository"]
             and claim["ecpu_revision"] == policy["ecpu_revision"],
             "E-CPU source revision substitution")
    return {
        "status": "verified-link-not-admitted",
        "model_id": model_id,
        "computational_ground_ref": ground.to_dict(),
        "semantic_ref": semantic.to_dict(),
        "translation_contract_digest": expected_contract.digest,
        "certificate_file_sha256": raw_digest,
        "semantic_sha256": math_report["semantic_sha256"],
        "cells_checked": math_report["atomic_cells_checked"],
    }


def verify_bundle(certificates: Path, bindings: Path, policy_dir: Path, ecpu_dir: Path) -> dict[str, Any]:
    policy = json.loads((policy_dir / "expected_ground_sources.json").read_text())
    profile = json.loads((policy_dir / "ground_profile.json").read_text())
    required(policy["schema"] == "in-formation-space.coe004.verifier-source-policy/0.1",
             "unsupported policy schema")
    revision = subprocess.check_output(
        ["git", "-C", str(ecpu_dir), "rev-parse", "HEAD"], text=True).strip()
    required(policy["ecpu_repository"] == "Kier73/E-CPU"
             and revision == policy["ecpu_revision"], "incorrect E-CPU checkout")
    names = sorted(policy["expected_network_sha256"])
    for directory in (certificates, bindings):
        required({f.name for f in directory.iterdir() if f.is_file()}
                 == {name + ".json" for name in names},
                 "unexpected source/certificate manifest")
    results = {}
    for name in names:
        result = verify_one(name, (certificates / (name + ".json")).read_bytes(),
                            (bindings / (name + ".json")).read_bytes(),
                            policy=policy, profile=profile)
        results[name] = result

    required(results["identity"]["semantic_ref"] == results["relu_identity"]["semantic_ref"],
             "same mathematical function did not share E-CPU semantic representation")
    required(results["rescaled_bump"]["semantic_ref"] == results["triangular_bump"]["semantic_ref"],
             "parameter rescaling changed semantic representation")
    required(results["zero"]["semantic_ref"] != results["triangular_bump"]["semantic_ref"],
             "distinct real functions incorrectly share representation")
    required(len({json.dumps(v["computational_ground_ref"], sort_keys=True)
                  for v in results.values()}) == 1, "shared Ground definition identity mismatch")
    return {"schema": "in-formation-space.coe004.independent-ground-link-report/0.1",
            "status": "all-verified-not-admitted", "ecpu_revision": revision,
            "claim_count": len(results), "claims": results,
            "authority_granted": False, "ground_admitted": False,
            "trust": "checked-in verifier-side pins, not remote authenticated authority"}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("certificates", type=Path)
    parser.add_argument("bindings", type=Path)
    parser.add_argument("--ecpu-dir", required=True, type=Path)
    parser.add_argument("--policy-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_bundle(args.certificates, args.bindings, args.policy_dir, args.ecpu_dir)
    content = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(content)
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
