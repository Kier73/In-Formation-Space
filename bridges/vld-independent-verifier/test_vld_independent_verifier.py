"""Cross-language tests for standalone Python & Node.js VLD verifiers (VIV-001)."""

from __future__ import annotations

import copy
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("vld_standalone_verifier", HERE / "vld_standalone_verifier.py")
assert SPEC is not None and SPEC.loader is not None
VER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VER)


def _build_valid_bundle() -> dict:
    pipeline_id = "viv001.sample.pipe"
    initial_input = {"seed": 42, "topic": "in-transit"}
    members = ["q0", "q1", "q2"]
    secrets = {m: f"viv-secret-{m}-0123456789abcdef" for m in members}
    mem_dg = VER.domain_digest("vld.quorum-membership.v1", {"lineage_id": "viv.lin", "member_ids": members})

    genesis_fp = VER.domain_digest("vld.pipeline-genesis.v1", {"input": initial_input, "pipeline_id": pipeline_id})
    target_fp = "a" * 64
    state_manifest = {
        "chunks": [{"byte_length": 15, "index": 0, "page_digest": "b" * 64}],
        "content_digest": "c" * 64,
        "kind": "vld.m1-manifest.v1",
        "manifest_digest": "d" * 64,
        "media_type": "application/json",
        "page_size": 4096,
        "schema_version": 1,
        "size_bytes": 15,
    }
    slot_dg = VER.domain_digest(
        "vld.stage-slot.v1",
        {
            "pipeline_id": pipeline_id,
            "stage_id": "stage.0",
            "stage_index": 0,
            "state_manifest_digest": state_manifest["manifest_digest"],
        },
    )
    prop_body = {
        "lineage_id": "viv.lin",
        "membership_digest": mem_dg,
        "operation_id": f"{pipeline_id}.stage.0",
        "predecessor_manifest_digest": VER.GENESIS_DIGEST,
        "proposer_id": "host.0",
        "schema": "vld.quorum-proposal.v1",
        "slot": 1,
        "state_manifest_digest": slot_dg,
        "term": 1,
    }
    prop_dg = VER.domain_digest("vld.quorum-proposal.v1", prop_body)
    votes = []
    for vid in ("q0", "q1"):
        msg = VER.canonical_bytes(
            {
                "domain": "vld.quorum-vote.v1",
                "lineage_id": "viv.lin",
                "proposal_digest": prop_dg,
                "slot": 1,
                "term": 1,
                "voter_id": vid,
            }
        )
        sig = hmac.new(secrets[vid].encode("utf-8"), msg, hashlib.sha256).hexdigest()
        votes.append(
            {
                "lineage_id": "viv.lin",
                "proposal_digest": prop_dg,
                "signature_hmac": sig,
                "slot": 1,
                "term": 1,
                "voter_id": vid,
            }
        )
    cert_body = {
        "membership": {"lineage_id": "viv.lin", "member_ids": members, "membership_digest": mem_dg, "quorum_size": 2},
        "proposal": {**prop_body, "proposal_digest": prop_dg},
        "schema": "vld.quorum-certificate.v1",
        "votes": votes,
    }
    cert_dg = VER.domain_digest("vld.quorum-certificate.v1", cert_body)
    q_cert = {**cert_body, "certificate_digest": cert_dg}

    rcpt_body = {
        "clock_bridge_digest": None,
        "host_id": "host.0",
        "oracle_verdict": "PASS:stage.0|VERIFIED:independent_oracle_ok",
        "pipeline_id": pipeline_id,
        "prev_continuity_digest": VER.GENESIS_DIGEST,
        "quorum_cert_digest": cert_dg,
        "scheduler_id": "sched.0",
        "schema": "vld.cross-ground-continuity-receipt.v1",
        "source_ground_fingerprint": genesis_fp,
        "source_representation": "init",
        "stage_cost": {"bytes_moved": 64.0, "compute_ops": 8.0, "latency_ms": 0.5, "verification_ops": 2.0},
        "stage_id": "stage.0",
        "stage_index": 0,
        "state_manifest": state_manifest,
        "target_ground_fingerprint": target_fp,
        "target_representation": "done",
        "temporal": {"clock": {"host.0": 1}, "epoch": 1, "scheduler_id": "sched.0"},
    }
    cont_dg = VER.domain_digest("vld.cross-ground-continuity-receipt.v1", rcpt_body)
    rcpt = {**rcpt_body, "continuity_digest": cont_dg, "quorum_certificate": q_cert}
    return {
        "initial_input": initial_input,
        "pipeline_id": pipeline_id,
        "quorum_member_ids": members,
        "quorum_member_secrets_utf8": secrets,
        "receipts": [rcpt],
    }


class TestVLDIndependentVerifier(unittest.TestCase):
    def test_python_and_nodejs_cross_language_agreement_and_tamper_refusal(self) -> None:
        bundle = _build_valid_bundle()
        sec_bytes = {k: v.encode("utf-8") for k, v in bundle["quorum_member_secrets_utf8"].items()}
        py_res = VER.verify_continuity_chain(
            bundle["receipts"],
            pipeline_id=bundle["pipeline_id"],
            initial_input=bundle["initial_input"],
            quorum_member_ids=bundle["quorum_member_ids"],
            quorum_member_secrets=sec_bytes,
            require_verified_tag=True,
        )
        self.assertEqual(py_res["status"], "VERIFIED")

        # Tampered initial_input must fail
        with self.assertRaises(VER.VerificationError):
            VER.verify_continuity_chain(
                bundle["receipts"],
                pipeline_id=bundle["pipeline_id"],
                initial_input={"seed": 999, "topic": "in-transit"},
                quorum_member_ids=bundle["quorum_member_ids"],
                quorum_member_secrets=sec_bytes,
            )

        # Forged worker PASS without |VERIFIED: tag must fail
        unverified = copy.deepcopy(bundle["receipts"])
        unverified[0]["oracle_verdict"] = "PASS:self_asserted_only"
        with self.assertRaises(VER.VerificationError):
            VER.verify_continuity_chain(
                unverified,
                pipeline_id=bundle["pipeline_id"],
                initial_input=bundle["initial_input"],
                require_verified_tag=True,
            )

        # If Node.js is installed, verify exact cross-language digest agreement!
        node_bin = shutil.which("node")
        if node_bin is not None:
            import tempfile

            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
                json.dump(bundle, tf)
                tmp_name = tf.name
            try:
                proc = subprocess.run(
                    [node_bin, str(HERE / "vld_standalone_verifier.mjs"), tmp_name],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                node_res = json.loads(proc.stdout)
                self.assertEqual(node_res["status"], "VERIFIED_NODEJS")
                self.assertEqual(node_res["final_continuity_digest"], py_res["final_continuity_digest"])
            finally:
                Path(tmp_name).unlink(missing_ok=True)

            # Negative controls on Node.js verifier: replayed votes from different proposal/slot, tampered certificate_digest & missing secret
            replayed = copy.deepcopy(bundle)
            fake_prop = "f" * 64
            for v in replayed["receipts"][0]["quorum_certificate"]["votes"]:
                v["proposal_digest"] = fake_prop
                v["slot"] = 999
                v["term"] = 999
                msg = VER.canonical_bytes(
                    {
                        "domain": "vld.quorum-vote.v1",
                        "lineage_id": v["lineage_id"],
                        "proposal_digest": fake_prop,
                        "slot": 999,
                        "term": 999,
                        "voter_id": v["voter_id"],
                    }
                )
                v["signature_hmac"] = hmac.new(replayed["quorum_member_secrets_utf8"][v["voter_id"]].encode("utf-8"), msg, hashlib.sha256).hexdigest()

            missing_sec = copy.deepcopy(bundle)
            del missing_sec["quorum_member_secrets_utf8"]["q0"]

            bad_stage_spec = copy.deepcopy(bundle)
            bad_stage_spec["expected_stages"] = [
                {
                    "ground_fingerprint": "0" * 64,
                    "input_representation": "init",
                    "output_representation": "done",
                    "stage_id": "stage.0",
                }
            ]

            for bad_bundle in (replayed, missing_sec, bad_stage_spec):
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
                    json.dump(bad_bundle, tf)
                    bad_path = tf.name
                try:
                    bad_proc = subprocess.run(
                        [node_bin, str(HERE / "vld_standalone_verifier.mjs"), bad_path],
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(bad_proc.returncode, 0)
                finally:
                    Path(bad_path).unlink(missing_ok=True)

    def test_1d_snc_capsule_verifier_rejects_shadowed_and_non_relu_capsules(self) -> None:
        shadow_atlas = [
            {"left": "-inf", "right": "+inf", "affines": [["0", "0"]]},
            {"left": "0", "right": "+inf", "affines": [["999", "999"]]},
        ]
        forged_body = {
            "network": {
                "hidden_activation": "tanh",
                "hidden_bias": ["0"],
                "hidden_weight": [["0", "9999"]],
                "output_bias": ["0"],
                "output_weight": [["0"]],
            },
            "schema": "vld.snc-relu-capsule.v1",
            "source_atlas": shadow_atlas,
            "source_atlas_digest": VER.domain_digest("vld.semantic-atlas.v1", shadow_atlas),
        }
        forged_cap = {**forged_body, "capsule_digest": VER.domain_digest("vld.snc-relu-capsule.v1", forged_body)}
        with self.assertRaises(VER.VerificationError):
            VER.verify_snc_1d_capsule(forged_cap)


if __name__ == "__main__":
    unittest.main()
