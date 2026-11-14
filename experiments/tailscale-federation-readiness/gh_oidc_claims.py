#!/usr/bin/env python3
"""IHP-009: validate a short-lived GitHub OIDC JWT, publish only bounded claims.

The JWT and GitHub's bearer credential stay in memory on the issuing runner.
The off-host verifier authenticates the attested claim record, not the discarded JWT.
Neither step establishes Tailscale federation or E-CPU socket reachability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

REPOSITORY = "Kier73/In-Formation-Space"
ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URL = ISSUER + "/.well-known/jwks"
AUDIENCE = "in-formation-space/ihp009-oidc-claim-observation"
WORKFLOW_PATH = ".github/workflows/ihp009-oidc-claims-evidence.yml"
WORKFLOW_REF = f"{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main"
SOURCE_REF = "refs/heads/main"
CLAIMS_SCHEMA = "in-formation.ihp009-oidc-claims/0.1"
CLAIMS_PREDICATE_SCHEMA = "in-formation.ihp009-oidc-claims-predicate/0.1"
REPORT_SCHEMA = "in-formation.ihp009-oidc-claims-report/0.1"
REPORT_PREDICATE_SCHEMA = "in-formation.ihp009-oidc-claims-report-predicate/0.1"
CLAIMS_PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/ihp009-oidc-claims/v1"
CLAIMS = (
    "iss", "sub", "aud", "repository", "repository_id", "repository_owner",
    "repository_owner_id", "ref", "workflow_ref", "workflow_sha",
    "run_id", "run_attempt", "event_name",
)


class OIDCClaimError(ValueError):
    """Evidence is absent, inconsistent or fails its pinned policy."""


def require(condition: bool, why: str) -> None:
    if not condition:
        raise OIDCClaimError(why)


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(obj, dict), "JSON evidence must be an object")
    return obj


def environment(env: Mapping[str, str], role: str) -> dict[str, str]:
    require(role in ("claims_host", "verifier_host"), "unexpected workflow role")
    expected = {
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REF": SOURCE_REF,
        "GITHUB_WORKFLOW_REF": WORKFLOW_REF,
        "GITHUB_JOB": role,
    }
    for name, value in expected.items():
        require(env.get(name) == value, f"unexpected workflow context: {name}")
    require(env.get("GITHUB_EVENT_NAME") in ("push", "workflow_dispatch"),
            "claims may be observed only on a protected main push or manual dispatch")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "RUNNER_NAME"):
        require(bool(env.get(key)), f"missing workflow context: {key}")
    require(re.fullmatch(r"[0-9]+", env["GITHUB_RUN_ID"]) is not None, "invalid run ID")
    require(re.fullmatch(r"[0-9]+", env["GITHUB_RUN_ATTEMPT"]) is not None, "invalid run attempt")
    require(re.fullmatch(r"[0-9a-f]{40}", env["GITHUB_SHA"]) is not None, "invalid source SHA")
    return {
        "repository": REPOSITORY,
        "ref": SOURCE_REF,
        "workflow_ref": WORKFLOW_REF,
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": env["GITHUB_RUN_ATTEMPT"],
        "job": role,
        "runner_name": env["RUNNER_NAME"],
        "git_sha": env["GITHUB_SHA"],
    }


def expected_immutable_subject(env: Mapping[str, str]) -> str:
    repo_id = env.get("GITHUB_REPOSITORY_ID", "")
    owner_id = env.get("GITHUB_REPOSITORY_OWNER_ID", "")
    require(repo_id.isdecimal() and owner_id.isdecimal(), "GitHub immutable repository IDs missing")
    return f"repo:Kier73@{owner_id}/In-Formation-Space@{repo_id}:ref:refs/heads/main"


def build_record(payload: Mapping[str, Any], header: Mapping[str, Any],
                 env: Mapping[str, str]) -> dict[str, Any]:
    ctx = environment(env, "claims_host")
    require(header.get("alg") == "RS256" and isinstance(header.get("kid"), str)
            and 1 <= len(header["kid"]) <= 256, "unsupported JWT header")
    expected_claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "repository": REPOSITORY,
        "ref": SOURCE_REF,
        "workflow_ref": WORKFLOW_REF,
        "run_id": ctx["run_id"],
        "run_attempt": ctx["run_attempt"],
        "event_name": env["GITHUB_EVENT_NAME"],
        "repository_id": env.get("GITHUB_REPOSITORY_ID"),
        "repository_owner_id": env.get("GITHUB_REPOSITORY_OWNER_ID"),
    }
    for key, expected in expected_claims.items():
        require(isinstance(expected, str) and expected and payload.get(key) == expected,
                f"verified JWT claim does not match current runner: {key}")
    require(isinstance(payload.get("sub"), str) and 1 <= len(payload["sub"]) <= 1024,
            "invalid OIDC subject")
    selected = {key: payload[key] for key in CLAIMS if key in payload}
    require(all(isinstance(value, str) and len(value) <= 2048 for value in selected.values()),
            "selected OIDC claims must be bounded strings")
    expected_sub = expected_immutable_subject(env)
    actual_default = payload["sub"] == expected_sub
    core = {
        "schema": CLAIMS_SCHEMA,
        "status": ("observed_default_immutable_subject" if actual_default
                   else "observed_nondefault_subject_requires_review"),
        "context": ctx,
        "claims": selected,
        "expected_default_immutable_subject": expected_sub,
        "oidc_signature": {
            "signature_verified_in_issuing_job": True,
            "algorithm": "RS256",
            "key_id": header["kid"],
            "jwks_url": JWKS_URL,
            "raw_jwt_retained": False,
        },
        "limitations": [
            "The JWT signature was validated against GitHub's public JWK in the issuing job; the JWT itself is not retained.",
            "The separate verifier authenticates the claims file and workflow provenance, not the discarded original JWT signature.",
            "The audience is a dedicated IHP-009 diagnostic value, not a Tailscale federated-identity audience.",
            "A validated GitHub OIDC claim does not establish Tailscale federation, peer connectivity, mTLS, or E-CPU operation.",
        ],
    }
    return {**core, "record_digest": digest(core)}


def validate_record(record: Mapping[str, Any], *, env: Mapping[str, str],
                    expected_job: str = "claims_host") -> None:
    ctx = environment(env, "verifier_host")
    require(record.get("schema") == CLAIMS_SCHEMA, "unknown claim-record schema")
    require(set(record) == {
        "schema", "status", "context", "claims", "expected_default_immutable_subject",
        "oidc_signature", "limitations", "record_digest",
    }, "invalid claim-record fields")
    core = {k: v for k, v in record.items() if k != "record_digest"}
    require(record.get("record_digest") == digest(core), "claim record digest mismatch")
    source = record["context"]
    require(isinstance(source, dict) and set(source) == set(ctx), "claim host context invalid")
    for key in ("repository", "ref", "workflow_ref", "run_id", "run_attempt", "git_sha"):
        require(source.get(key) == ctx[key], f"cross-host claim context differs: {key}")
    require(source["job"] == expected_job and source["runner_name"] != ctx["runner_name"],
            "claim producer and verifier must be different hosted jobs")
    claims = record["claims"]
    require(isinstance(claims, dict) and set(claims).issubset(CLAIMS)
            and set(("iss","sub","aud","repository","repository_id","repository_owner_id",
                     "ref","workflow_ref","run_id","run_attempt","event_name")).issubset(claims),
            "claims missing or unexpected")
    signature = record.get("oidc_signature")
    require(isinstance(signature, dict)
            and signature.get("signature_verified_in_issuing_job") is True
            and signature.get("raw_jwt_retained") is False
            and signature.get("algorithm") == "RS256"
            and signature.get("jwks_url") == JWKS_URL
            and isinstance(signature.get("key_id"), str), "missing issuer-side JWT signature check")
    expected = {
        "iss": ISSUER, "aud": AUDIENCE, "repository": REPOSITORY, "ref": SOURCE_REF,
        "workflow_ref": WORKFLOW_REF, "run_id": ctx["run_id"],
        "run_attempt": ctx["run_attempt"], "event_name": env["GITHUB_EVENT_NAME"],
    }
    for name, value in expected.items():
        require(claims.get(name) == value, f"claim verifier policy mismatch: {name}")
    subject = record.get("expected_default_immutable_subject")
    require(isinstance(subject, str) and subject.endswith(":ref:refs/heads/main"),
            "missing expected default subject")
    expected_status = ("observed_default_immutable_subject" if claims["sub"] == subject
                       else "observed_nondefault_subject_requires_review")
    require(record.get("status") == expected_status, "subject classification mismatch")
    require(isinstance(record.get("limitations"), list) and len(record["limitations"]) == 4,
            "claim limitations missing")


def request_and_validate_token(env: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    import jwt
    token_url = env.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    bearer = env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    require(token_url.startswith("https://") and bearer, "GitHub OIDC request context missing")
    url = token_url + ("&" if "?" in token_url else "?") + urllib.parse.urlencode({"audience": AUDIENCE})
    req = urllib.request.Request(url, headers={"Authorization": f"bearer {bearer}"})
    with urllib.request.urlopen(req, timeout=15) as response:
        document = json.loads(response.read(32768).decode("utf-8"))
    require(isinstance(document, dict) and isinstance(document.get("value"), str),
            "GitHub OIDC endpoint returned no JWT")
    raw_token = document["value"]
    header = jwt.get_unverified_header(raw_token)
    require(header.get("alg") == "RS256", "unexpected GitHub JWT signature algorithm")
    jwks = jwt.PyJWKClient(JWKS_URL, timeout=15)
    public_key = jwks.get_signing_key_from_jwt(raw_token).key
    decoded = jwt.decode(raw_token, public_key, algorithms=["RS256"], audience=AUDIENCE,
                         issuer=ISSUER, options={"require": ["sub", "aud", "iss", "iat", "exp"]})
    return decoded, header


def build_claims_predicate(record_path: Path) -> dict[str, Any]:
    record = read_json(record_path)
    return {
        "schema": CLAIMS_PREDICATE_SCHEMA,
        "record_sha256": file_digest(record_path),
        "record_digest": record["record_digest"],
        "run_id": record["context"]["run_id"],
        "run_attempt": record["context"]["run_attempt"],
        "status": record["status"],
    }


def verify_record_attestation(record_path: Path, expected_predicate: Mapping[str, Any],
                              *, gh: str = "gh") -> dict[str, Any]:
    command = [
        gh, "attestation", "verify", str(record_path),
        "--repo", REPOSITORY,
        "--predicate-type", CLAIMS_PREDICATE_TYPE,
        "--signer-workflow", f"{REPOSITORY}/{WORKFLOW_PATH}",
        "--source-ref", SOURCE_REF,
        "--deny-self-hosted-runners",
        "--format", "json",
    ]
    run = subprocess.run(command, capture_output=True, text=True, check=True)
    data = json.loads(run.stdout)
    require(isinstance(data, list), "GitHub attestation verification returned no list")
    matches = []
    for item in data:
        verification = item.get("verificationResult", {}) if isinstance(item, dict) else {}
        statement = verification.get("statement", {}) if isinstance(verification, dict) else {}
        subjects = statement.get("subject", []) if isinstance(statement, dict) else []
        if not any(isinstance(s, dict) and isinstance(s.get("digest"), dict)
                   and s["digest"].get("sha256") == file_digest(record_path) for s in subjects):
            continue
        require(statement.get("predicateType") == CLAIMS_PREDICATE_TYPE,
                "verified attestation predicate type differs")
        require(statement.get("predicate") == dict(expected_predicate),
                "verified predicate does not match the downloaded record")
        signature = verification.get("signature", {})
        require(isinstance(signature, dict) and isinstance(signature.get("certificate"), dict),
                "GitHub attestation has no signing certificate")
        matches.append(True)
    require(bool(matches), "no verified GitHub attestation matches the exact record bytes")
    return {
        "verified": True,
        "record_sha256": file_digest(record_path),
        "signer_workflow": f"{REPOSITORY}/{WORKFLOW_PATH}",
        "source_ref": SOURCE_REF,
        "self_hosted_runners_denied": True,
    }


def build_report(record: Mapping[str, Any], record_sha256: str,
                 attestation: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    validate_record(record, env=env)
    require(attestation.get("verified") is True and attestation.get("record_sha256") == record_sha256,
            "downloaded record was not verified by GitHub attestation")
    ctx = environment(env, "verifier_host")
    core = {
        "schema": REPORT_SCHEMA,
        "status": "independently_attested_github_oidc_claims",
        "claim_record_sha256": record_sha256,
        "claim_record_digest": record["record_digest"],
        "subject": record["claims"]["sub"],
        "subject_classification": record["status"],
        "claims": record["claims"],
        "claim_host": record["context"],
        "verifier_host": ctx,
        "claim_attestation": dict(attestation),
        "limitations": [
            "Independent job verified GitHub-attested record bytes; the original short-lived JWT was not transferred or reverified.",
            "Observed issuer and subject values assist a tailnet admin, but the IHP-009 workflow_ref and diagnostic audience are not IHP-006 or MOR-002 identity values.",
            "There is no evidence here of a Tailscale join, E-CPU mTLS delivery or multi-host semantic handoff.",
        ],
    }
    return {**core, "report_digest": digest(core)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    cmd = parser.add_subparsers(dest="command", required=True)
    observe = cmd.add_parser("observe")
    observe.add_argument("--output-dir", type=Path, required=True)
    verify = cmd.add_parser("verify")
    verify.add_argument("--record", type=Path, required=True)
    verify.add_argument("--predicate", type=Path, required=True)
    verify.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "observe":
            claims, header = request_and_validate_token(os.environ)
            record = build_record(claims, header, os.environ)
            path = args.output_dir / "claims.json"
            write_json(path, record)
            write_json(args.output_dir / "claims.predicate.json", build_claims_predicate(path))
            print(f"IHP-009 recorded signature-checked GitHub OIDC claims: {record['status']}; no token retained")
        else:
            record = read_json(args.record)
            expected = build_claims_predicate(args.record)
            require(read_json(args.predicate) == expected, "local claim attestation predicate mismatch")
            attestation = verify_record_attestation(args.record, expected)
            report = build_report(record, file_digest(args.record), attestation, os.environ)
            path = args.output_dir / "report.json"
            write_json(path, report)
            write_json(args.output_dir / "report.predicate.json", {
                "schema": REPORT_PREDICATE_SCHEMA,
                "report_sha256": file_digest(path),
                "report_digest": report["report_digest"],
                "run_id": report["verifier_host"]["run_id"],
                "run_attempt": report["verifier_host"]["run_attempt"],
                "status": report["status"],
            })
            print(f"IHP-009 independently attested claim record: {report['status']}; no JWT transferred")
    except Exception as error:
        # Never print a JWT, request bearer, full urllib exception, or token endpoint output.
        print(f"IHP-009 failed closed ({type(error).__name__}); no successful claim report", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
