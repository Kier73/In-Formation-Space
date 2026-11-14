from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gh_oidc_claims as oidc


def env(role: str, runner: str) -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": oidc.REPOSITORY,
        "GITHUB_REPOSITORY_ID": "1454466415",
        "GITHUB_REPOSITORY_OWNER_ID": "29310272",
        "GITHUB_REF": oidc.SOURCE_REF,
        "GITHUB_WORKFLOW_REF": oidc.WORKFLOW_REF,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_JOB": role,
        "GITHUB_RUN_ID": "43551555555",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "RUNNER_NAME": runner,
    }


def payload() -> dict[str, str]:
    source = env("claims_host", "oidc-source")
    return {
        "iss": oidc.ISSUER,
        "aud": oidc.AUDIENCE,
        "sub": oidc.expected_immutable_subject(source),
        "repository": oidc.REPOSITORY,
        "repository_id": source["GITHUB_REPOSITORY_ID"],
        "repository_owner": "Kier73",
        "repository_owner_id": source["GITHUB_REPOSITORY_OWNER_ID"],
        "ref": oidc.SOURCE_REF,
        "workflow_ref": oidc.WORKFLOW_REF,
        "workflow_sha": source["GITHUB_SHA"],
        "run_id": source["GITHUB_RUN_ID"],
        "run_attempt": source["GITHUB_RUN_ATTEMPT"],
        "event_name": "push",
    }


class OIDCClaimsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_env = env("claims_host", "oidc-source")
        self.verifier_env = env("verifier_host", "oidc-independent-verifier")
        self.header = {"alg": "RS256", "kid": "github-public-kid"}
        self.raw_claims = payload()
        self.record = oidc.build_record(self.raw_claims, self.header, self.source_env)

    def test_immutable_subject_and_no_token_retention(self) -> None:
        self.assertEqual(self.record["status"], "observed_default_immutable_subject")
        self.assertEqual(self.record["claims"]["sub"],
                         "repo:Kier73@29310272/In-Formation-Space@1454466415:ref:refs/heads/main")
        self.assertTrue(self.record["oidc_signature"]["signature_verified_in_issuing_job"])
        self.assertFalse(self.record["oidc_signature"]["raw_jwt_retained"])
        self.assertEqual(self.record["oidc_signature"]["algorithm"], "RS256")
        oidc.validate_record(self.record, env=self.verifier_env)

    def test_unrecognized_subject_is_retained_and_requires_review(self) -> None:
        altered = copy.deepcopy(self.raw_claims)
        altered["sub"] = "custom:repository-scoped-workload"
        record = oidc.build_record(altered, self.header, self.source_env)
        self.assertEqual(record["status"], "observed_nondefault_subject_requires_review")
        oidc.validate_record(record, env=self.verifier_env)

    def test_extra_private_values_are_not_exported(self) -> None:
        altered = copy.deepcopy(self.raw_claims)
        altered.update({"raw_token": "SENSITIVE_TEST_VALUE", "unrecognized": "PRIVATE_TEST_VALUE"})
        source = oidc.build_record(altered, self.header, self.source_env)
        self.assertNotIn("SENSITIVE_TEST_VALUE", json.dumps(source))
        self.assertNotIn("PRIVATE_TEST_VALUE", json.dumps(source))
        self.assertEqual(set(source["claims"]), set(oidc.CLAIMS))

    def test_mismatched_issuer_and_audience_fail_closed(self) -> None:
        for field, bad in (("iss", "https://untrusted.example"), ("aud", "other-audience")):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.raw_claims)
                changed[field] = bad
                with self.assertRaisesRegex(oidc.OIDCClaimError, field):
                    oidc.build_record(changed, self.header, self.source_env)

    def test_cross_run_and_repo_identity_rejected(self) -> None:
        for field, bad in (("repository_id", "999"), ("repository_owner_id", "777"),
                           ("workflow_ref", "other"), ("run_id", "3"), ("ref", "refs/heads/other")):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.raw_claims)
                changed[field] = bad
                with self.assertRaisesRegex(oidc.OIDCClaimError, field):
                    oidc.build_record(changed, self.header, self.source_env)

    def test_unexpected_algorithm_or_missing_key_id_is_rejected(self) -> None:
        for header in ({"alg": "none", "kid": "x"}, {"alg": "RS256"}):
            with self.subTest(header=header):
                with self.assertRaises(oidc.OIDCClaimError):
                    oidc.build_record(self.raw_claims, header, self.source_env)

    def test_claim_record_digest_tampering_is_rejected(self) -> None:
        bad = copy.deepcopy(self.record)
        bad["claims"]["sub"] = "forged"
        with self.assertRaisesRegex(oidc.OIDCClaimError, "digest mismatch"):
            oidc.validate_record(bad, env=self.verifier_env)

    def test_verifier_rejects_other_run_or_same_runner(self) -> None:
        wrong = copy.deepcopy(self.verifier_env)
        wrong["GITHUB_RUN_ID"] = "4444444"
        with self.assertRaisesRegex(oidc.OIDCClaimError, "run_id"):
            oidc.validate_record(self.record, env=wrong)
        wrong = copy.deepcopy(self.verifier_env)
        wrong["RUNNER_NAME"] = "oidc-source"
        with self.assertRaisesRegex(oidc.OIDCClaimError, "different hosted jobs"):
            oidc.validate_record(self.record, env=wrong)

    def test_main_only_workflow_identity_is_required(self) -> None:
        wrong = copy.deepcopy(self.source_env)
        wrong["GITHUB_REF"] = "refs/heads/develop"
        with self.assertRaisesRegex(oidc.OIDCClaimError, "GITHUB_REF"):
            oidc.build_record(self.raw_claims, self.header, wrong)

    def test_predicate_is_bound_to_exact_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "claims.json"
            oidc.write_json(file, self.record)
            predicate = oidc.build_claims_predicate(file)
            self.assertEqual(predicate["record_sha256"], hashlib.sha256(file.read_bytes()).hexdigest())
            self.assertEqual(predicate["record_digest"], self.record["record_digest"])
            file.write_bytes(file.read_bytes() + b" ")
            self.assertNotEqual(predicate["record_sha256"], oidc.file_digest(file))

    def test_attestation_requires_exact_subject_and_predicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "claims.json"
            oidc.write_json(file, self.record)
            expected = oidc.build_claims_predicate(file)
            statement = {
                "verificationResult": {
                    "statement": {
                        "subject": [{"digest": {"sha256": oidc.file_digest(file)}}],
                        "predicateType": oidc.CLAIMS_PREDICATE_TYPE,
                        "predicate": expected,
                    },
                    "signature": {"certificate": {"rawBytes": "fixture"}},
                },
            }
            process = type("Process", (), {"stdout": json.dumps([statement])})()
            with patch.object(oidc.subprocess, "run", return_value=process) as spy:
                verified = oidc.verify_record_attestation(file, expected)
            self.assertTrue(verified["verified"])
            args = spy.call_args.args[0]
            self.assertIn("--deny-self-hosted-runners", args)
            self.assertIn("--signer-workflow", args)
            self.assertIn("--source-ref", args)
            statement["verificationResult"]["statement"]["predicate"]["record_digest"] = "f" * 64
            process = type("Process", (), {"stdout": json.dumps([statement])})()
            with patch.object(oidc.subprocess, "run", return_value=process):
                with self.assertRaisesRegex(oidc.OIDCClaimError, "predicate"):
                    oidc.verify_record_attestation(file, expected)

    def test_independent_report_requires_attested_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "claims.json"
            oidc.write_json(file, self.record)
            sha = oidc.file_digest(file)
            with self.assertRaisesRegex(oidc.OIDCClaimError, "not verified"):
                oidc.build_report(self.record, sha, {"verified": False}, self.verifier_env)
            a = {"verified": True, "record_sha256": sha, "signer_workflow": oidc.WORKFLOW_REF}
            report = oidc.build_report(self.record, sha, a, self.verifier_env)
            self.assertEqual(report["status"], "independently_attested_github_oidc_claims")
            self.assertNotIn("jwt", report)
            self.assertEqual(report["claim_host"]["job"], "claims_host")
            self.assertEqual(report["verifier_host"]["job"], "verifier_host")


if __name__ == "__main__":
    unittest.main()
