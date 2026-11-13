"""COE-004: bind a checked ReLU certificate to actual E-CPU identity types.

This constructs *candidate* computational Ground and translation descriptors.
It does not register, admit, execute, or authorize a Ground in E-CPU.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from mailcpu.semantic_translation import (
    ObservationContract,
    RepresentationRef,
    TranslationContract,
    canonical_value_digest,
)
from independent_certificate_checker import verify_json_bytes

BINDING_SCHEMA = "in-formation-space.coe004.candidate-ground-certificate-binding/0.1"
GROUND_TYPE = "ifs.coe004.computational-ground-profile"
NETWORK_TYPE = "ifs.coe002.rational-relu-network"
SEMANTIC_TYPE = "ifs.coe002.canonical-semantic-atlas"
MAPPING_TYPE = "ifs.coe004.certificate-backed-translation"
OBSERVATION_TYPE = "ifs.coe004.maximal-piecewise-affine-atlas"
CONTRACT_ID = "coe004.network-to-exact-semantic-atlas"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_policy(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = json.loads((directory / "expected_ground_sources.json").read_text(encoding="utf-8"))
    profile = json.loads((directory / "ground_profile.json").read_text(encoding="utf-8"))
    if (policy["schema"] != "in-formation-space.coe004.verifier-source-policy/0.1"
            or policy["ground_profile_file"] != "ground_profile.json"
            or profile["schema"] != "in-formation-space.coe004.computational-ground-profile/0.1"
            or profile["admission"] != "candidate-unadmitted"):
        raise ValueError("unsupported or admitted source policy")
    return policy, profile


def require_pinned_ecpu(policy: dict[str, Any], ecpu_dir: Path) -> str:
    """Verify actual checked-out dependency commit, not a claimed revision."""
    commit = subprocess.check_output(
        ["git", "-C", str(ecpu_dir), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != policy["ecpu_revision"] or policy["ecpu_repository"] != "Kier73/E-CPU":
        raise ValueError("E-CPU checkout differs from verifier's exact source pin")
    return commit


def construct_binding(model_id: str, raw: bytes, *, policy: dict[str, Any],
                      profile: dict[str, Any]) -> dict[str, Any]:
    expected = policy["expected_network_sha256"].get(model_id)
    if expected is None:
        raise ValueError("unknown model ID in source policy")
    verified = verify_json_bytes(raw, expected_network_sha256=expected)
    certificate = json.loads(raw)
    if len(certificate["network"]["layers"][-1]["bias"]) != len(
            profile["output_schema"]["ordered"]):
        raise ValueError("Ground output arity disagrees with certificate")
    if profile["input_schema"]["ordered"] != ["x"]:
        raise ValueError("only scalar-input Ground profile is supported")
    source = RepresentationRef.from_payload(NETWORK_TYPE, 1, certificate["network"])
    target = RepresentationRef.from_payload(SEMANTIC_TYPE, 1, certificate["semantic_atlas"])
    ground = RepresentationRef.from_payload(GROUND_TYPE, 1, profile)
    observation = ObservationContract.from_definition(
        OBSERVATION_TYPE, 1, profile["observer_definition"])
    certificate_digest = digest_bytes(raw)
    mapping = RepresentationRef.from_payload(MAPPING_TYPE, 1, {
        "certificate_schema": certificate["schema"],
        "certificate_file_sha256": certificate_digest,
        "verification_rule": "coe002.exact-all-real-activation-cell-replay/0.1",
    })
    context_digest = canonical_value_digest({
        "candidate_ground": ground.to_dict(),
        "domain": "all-real-scalar-input",
        "arithmetic": "exact-rational",
        "observation": observation.to_dict(),
    })
    contract = TranslationContract(
        contract_id=CONTRACT_ID, revision=1, source=source, target=target,
        mapping=mapping, observation=observation, context_digest=context_digest)
    return {
        "schema": BINDING_SCHEMA,
        "model_id": model_id,
        "ecpu_repository": policy["ecpu_repository"],
        "ecpu_revision": policy["ecpu_revision"],
        "ground_admission": "not-admitted",
        "verification_status": "exact-certificate-verified",
        "candidate_ground": ground.to_dict(),
        "source_representation": source.to_dict(),
        "semantic_representation": target.to_dict(),
        "observation_contract": observation.to_dict(),
        "translation_contract": contract.to_dict(),
        "translation_digest": contract.digest,
        "certificate_file_sha256": certificate_digest,
        "verified_network_sha256": verified["network_sha256"],
        "verified_semantic_sha256": verified["semantic_sha256"],
        "atomic_cells_checked": verified["atomic_cells_checked"],
    }


def produce(directory: Path, output: Path, *, policy_directory: Path, ecpu_directory: Path) -> None:
    policy, profile = read_policy(policy_directory)
    require_pinned_ecpu(policy, ecpu_directory)
    output.mkdir(parents=True, exist_ok=True)
    names = sorted(policy["expected_network_sha256"])
    observed = {p.name for p in directory.iterdir() if p.is_file()}
    if observed != {name + ".json" for name in names}:
        raise ValueError("producer certificate manifest does not match independently pinned policy")
    for name in names:
        raw = (directory / (name + ".json")).read_bytes()
        link = construct_binding(name, raw, policy=policy, profile=profile)
        (output / (name + ".json")).write_bytes(canonical(link) + b"\n")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("certificates", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--policy-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--ecpu-dir", required=True, type=Path)
    args = parser.parse_args()
    produce(args.certificates, args.output, policy_directory=args.policy_dir,
            ecpu_directory=args.ecpu_dir)
    print("COE-004 candidate Ground bindings emitted; no Ground admitted.")


if __name__ == "__main__":
    main()
