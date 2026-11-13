from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mailcpu.temporal import CausalStamp, ClockDomain, TemporalContext, TemporalProfile

import direct_mtls_operation_path as direct
import mor002_overlay as mor002


def runner_env(role: str, runner: str = "runner-linux", system: str = "Linux") -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": direct.REPOSITORY,
        "GITHUB_JOB": role,
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_NUMBER": "42",
        "GITHUB_WORKFLOW_REF": f"{direct.REPOSITORY}/{direct.MOR002_WORKFLOW_PATH}@{direct.SOURCE_REF}",
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_REF": direct.SOURCE_REF,
        "GITHUB_SHA": "a" * 40,
        "RUNNER_NAME": runner,
        "RUNNER_OS": system,
        "RUNNER_ARCH": "X64",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }


class MOR002OverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_mor002_workflow_is_an_allowed_overlay_identity_and_observer_role(self) -> None:
        client = direct.host_metadata("client_host", runner_env("client_host"))
        observer = direct.host_metadata("observer_host", runner_env("observer_host", "observer-vm"))
        self.assertEqual(direct._workflow_path(client["workflow_ref"]), direct.MOR002_WORKFLOW_PATH)
        self.assertEqual(observer["role"], "observer_host")
        self.assertIn(direct.MOR002_WORKFLOW_PATH, direct.ALLOWED_WORKFLOW_PATHS)
        self.assertIn(direct.MOR002_WORKFLOW_PATH, direct.OVERLAY_WORKFLOW_PATHS)

    def test_a2_is_signed_source_local_followup_and_is_not_in_a1_envelope(self) -> None:
        identity = direct.generate_identity(
            "client_host", self.root / "client", runner_env("client_host", "client-vm")
        )
        host = identity["host"]
        context = direct._context(host)
        recorder = direct._recorder(host, context)
        attempt = f"run-{host['run_id']}-attempt-{host['run_attempt']}"
        recorder.measure(
            attempt_id=attempt,
            span_id="A1-span",
            operation_id="mor002.source.A1",
            operation=lambda: direct._local_work("a1"),
            context={"event_id": "A1", "role": "client_host"},
        )
        a1_span = recorder.spans[-1]
        context.emit_causal_stamp()
        a1_frame = context.observe().to_dict()
        envelope = direct._signed_document(
            {"path_id": f"run-{host['run_id']}-ihp002-direct-mtls"},
            identity["private_key_path"],
        )
        signed_followup = direct._write_mor002_source_followup(
            self.root / "client",
            host=host,
            context=context,
            recorder=recorder,
            attempt_id=attempt,
            predecessor_span=a1_span,
            predecessor_frame=a1_frame,
            signed_envelope=envelope,
            private_key_path=identity["private_key_path"],
        )
        core = direct._verify_signed_document(signed_followup, identity["certificate_path"])
        self.assertEqual(core["event_id"], "A2")
        self.assertFalse(core["transferred_in_handoff"])
        self.assertEqual(core["predecessor_frame"], a1_frame)
        self.assertEqual(core["predecessor_span_digest"], a1_span["span_digest"])
        self.assertEqual(core["handoff_envelope_digest"], envelope["signed_digest"])
        self.assertEqual(core["temporal_frame"]["causal"]["vector"][host["actor_id"]], 2)
        self.assertEqual(a1_frame["causal"]["vector"][host["actor_id"]], 1)
        self.assertNotIn("A2", envelope["core"])
        self.assertEqual(
            CausalStamp.from_dict(a1_frame["causal"]).relation(
                CausalStamp.from_dict(core["temporal_frame"]["causal"])
            ).value,
            "before",
        )

    def test_source_followup_is_captured_after_channel_send_but_before_ack(self) -> None:
        source = Path(direct.__file__).read_text(encoding="utf-8")
        send_at = source.index("sequence = sender_channel.send(signed_envelope)")
        a2_at = source.index("_write_mor002_source_followup(", send_at)
        ack_at = source.index("_wait_for_ack(sender_channel", send_at)
        self.assertLess(send_at, a2_at)
        self.assertLess(a2_at, ack_at)

    def test_native_sparse_vector_clock_produces_a2_b1_concurrency(self) -> None:
        a = "actor-A"
        b = "actor-B"
        a1 = CausalStamp.create(a, 1, {a: 1})
        a2 = CausalStamp.create(a, 2, {a: 2})
        b1 = CausalStamp.create(b, 2, {a: 1, b: 1})
        self.assertEqual(a1.relation(a2).value, "before")
        self.assertEqual(a1.relation(b1).value, "before")
        self.assertEqual(a2.relation(b1).value, "concurrent")

    def test_observer_c1_is_recorded_without_a_causal_clock(self) -> None:
        with patch.dict(os.environ, runner_env("observer_host"), clear=True):
            record_path = self.root / "observer.json"
            record = mor002.produce_observer(record_path)
            predicate_path = self.root / "observer.predicate.json"
            predicate = mor002.write_observer_predicate(record_path, predicate_path)
        checked = mor002._validate_event_record(record)
        self.assertIsNone(checked["temporal_frame"]["causal"])
        self.assertEqual(predicate["event_id"], "C1")
        self.assertFalse(predicate["causal_stamp_present"])
        self.assertEqual(json.loads(predicate_path.read_text())["record_sha256"], direct.file_digest(record_path))

    def test_followup_predicate_rejects_claim_that_a2_was_transferred(self) -> None:
        identity = direct.generate_identity(
            "client_host", self.root / "client", runner_env("client_host", "client-vm")
        )
        host = identity["host"]
        context = direct._context(host)
        recorder = direct._recorder(host, context)
        attempt = "run-123456789-attempt-1"
        recorder.measure(
            attempt_id=attempt, span_id="A1", operation_id="A1",
            operation=lambda: "A1", context={"event_id": "A1"},
        )
        span = recorder.spans[-1]
        context.emit_causal_stamp()
        frame = context.observe().to_dict()
        envelope = direct._signed_document(
            {"path_id": "run-123456789-ihp002-direct-mtls"},
            identity["private_key_path"],
        )
        signed = direct._write_mor002_source_followup(
            self.root / "client", host=host, context=context, recorder=recorder,
            attempt_id=attempt, predecessor_span=span, predecessor_frame=frame,
            signed_envelope=envelope, private_key_path=identity["private_key_path"],
        )
        record_path = self.root / "client" / "mor002-source-followup.json"
        altered = dict(signed)
        altered_core = dict(signed["core"])
        altered_core["transferred_in_handoff"] = True
        altered["core"] = altered_core
        altered["signed_digest"] = direct.digest_object(altered_core)
        record_path.write_text(json.dumps(altered), encoding="utf-8")
        with patch.dict(os.environ, runner_env("client_host", "client-vm"), clear=True):
            with self.assertRaisesRegex(mor002.MOR002Error, "must be A2 and remain outside"):
                mor002.write_followup_predicate(record_path, self.root / "predicate.json")

    def test_mor002_workflow_fails_closed_without_dedicated_overlay_identity(self) -> None:
        workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "mor002-tailscale-causal-reconstruction.yml"
        workflow_text = workflow_path.read_text(encoding="utf-8")
        import re

        jobs_match = re.search(r"(?ms)^jobs:\n(.*?)(?=^[^ \t]|\Z)", workflow_text)
        self.assertIsNotNone(jobs_match)
        job_names = re.findall(r"(?m)^  ([a-z_]+):$", jobs_match.group(1))
        self.assertEqual(job_names, ["tests", "client_host", "server_host", "observer_host", "verifier_host"])

        def job_block(name: str) -> str:
            match = re.search(
                rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z_]+:\n|\Z)",
                workflow_text,
            )
            self.assertIsNotNone(match)
            return match.group(1)

        action = "tailscale/github-action@064b10558093f38325e838ddea35486bdc6b1d5c"
        for role in ("client_host", "server_host"):
            block = job_block(role)
            self.assertRegex(block, r"(?m)^      id-token: write$")
            self.assertIn(f"tags: tag:mor002-mtls-ci", block)
            self.assertIn("Require the dedicated MOR-002 federation identity", block)
        self.assertNotIn(action, job_block("verifier_host"))
        self.assertIn("MOR002_TS_OAUTH_CLIENT_ID", workflow_text)
        self.assertIn("MOR002_TS_AUDIENCE", workflow_text)
        self.assertNotIn("ipify", workflow_text)
        self.assertNotIn("0.0.0.0", workflow_text)


if __name__ == "__main__":
    unittest.main()
