from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from mailcpu.journal import EventJournal

from proof_action_execution import ProofAttentionSession
from proof_attention_trajectory import (
    ProofAttentionTrajectoryError,
    export_proof_attention_trajectory,
    restore_proof_attention_trajectory,
)
from test_proof_action_execution import (
    add_result,
    add_result_payload,
    execute_to_return,
    ground,
    make_session,
    trace,
)
from vgi.proof import ProofGroundAdapter, VerifiedKernelReceipt


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def paths(root: Path, prefix: str):
    return (
        root / f"{prefix}.mtrj",
        root / f"{prefix}.mtrj.idx",
        root / f"{prefix}.manifest.json",
    )


def independently_project_journal(session):
    journal = EventJournal()
    for attempt in session.to_dict()["attempts"]:
        for event in attempt["events"]:
            journal.append(event["stage"], {
                "attempt_id": event["attempt_id"],
                "attempt_event_sequence": event["sequence"],
                "actor": event["actor"],
                "evidence_ref": event["evidence_ref"],
                "details": event["details"],
                "previous_event_digest": event["previous_event_digest"],
                "attempt_event_digest": event["event_digest"],
            })
    assert journal.verify()
    return journal.records()[-1].digest if journal.records() else "0" * 64


class ProofAttentionTrajectoryTests(unittest.TestCase):
    def test_active_session_roundtrips_through_sparse_ecpu_trajectory(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        proof_ground = ground(payload)
        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "active")
            manifest = export_proof_attention_trajectory(
                session, proof_ground, data, index, manifest_path, stride=64
            )
            restored = restore_proof_attention_trajectory(
                manifest_path, data, index, proof_ground
            )

        self.assertEqual(manifest["trajectory"]["event_count"], 4)
        self.assertEqual(manifest["trajectory"]["stride"], 64)
        self.assertEqual(
            manifest["trajectory"]["journal_head_digest"],
            independently_project_journal(session),
        )
        self.assertEqual(restored.to_dict(), session.to_dict())
        self.assertEqual(restored.status, "active")
        self.assertEqual(restored.active_attempt.status, "returned")

    def test_interpreted_session_restores_and_continues_from_updated_proof_ground(self):
        session, payload, _ = make_session()
        first = session.begin_next()
        execute_to_return(first)
        updated_payload = add_result_payload(payload, first, result_status="elaborated")
        updated_ground = ground(updated_payload)
        session.interpret_result(
            updated_ground,
            actor="proof-trace-adapter",
            interpretation_ref=f"interpretation://{first.attempt_id}",
        )

        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "interpreted")
            export_proof_attention_trajectory(
                session, updated_ground, data, index, manifest_path, stride=1
            )
            restored = restore_proof_attention_trajectory(
                manifest_path, data, index, updated_ground
            )
            self.assertEqual(restored.to_dict(), session.to_dict())
            next_attempt = restored.begin_next()

        self.assertEqual(next_attempt.action["tactic"], "simp")
        self.assertEqual(restored.attempts[0].status, "continued")

    def test_completed_session_restores_only_with_kernel_receipt_in_current_ground(self):
        session, payload, _ = make_session()
        first = session.begin_next()
        execute_to_return(first)
        completed_ground = add_result(payload, first, include_receipt=True)
        session.interpret_result(
            completed_ground,
            actor="proof-trace-adapter",
            interpretation_ref=f"interpretation://{first.attempt_id}",
        )
        self.assertIsNone(session.begin_next())
        self.assertEqual(session.status, "complete")

        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "complete")
            export_proof_attention_trajectory(
                session, completed_ground, data, index, manifest_path
            )
            restored = restore_proof_attention_trajectory(
                manifest_path, data, index, completed_ground
            )

        self.assertEqual(restored.to_dict(), session.to_dict())
        self.assertEqual(restored.status, "complete")

    def test_empty_exhausted_session_roundtrips_without_trajectory_frames(self):
        session, payload, _ = make_session(transitions=[])
        self.assertIsNone(session.begin_next())
        self.assertEqual(session.status, "exhausted")
        proof_ground = ground(payload)

        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "empty")
            manifest = export_proof_attention_trajectory(
                session, proof_ground, data, index, manifest_path, stride=8
            )
            restored = restore_proof_attention_trajectory(
                manifest_path, data, index, proof_ground
            )

        self.assertEqual(manifest["trajectory"]["event_count"], 0)
        self.assertEqual(manifest["trajectory"]["receipt_head"], "0" * 64)
        self.assertEqual(manifest["trajectory"]["journal_head_digest"], "0" * 64)
        self.assertEqual(restored.to_dict(), session.to_dict())
        self.assertEqual(restored.status, "exhausted")

    def test_binary_frame_tampering_is_rejected(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        proof_ground = ground(payload)
        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "tamper-frame")
            export_proof_attention_trajectory(
                session, proof_ground, data, index, manifest_path
            )
            raw = bytearray(data.read_bytes())
            raw[-1] ^= 1
            data.write_bytes(raw)
            with self.assertRaisesRegex(
                ProofAttentionTrajectoryError, "receipt or frame verification"
            ):
                restore_proof_attention_trajectory(
                    manifest_path, data, index, proof_ground
                )

    def test_manifest_tampering_is_rejected_before_frame_restore(self):
        session, payload, _ = make_session()
        session.begin_next()
        proof_ground = ground(payload)
        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "tamper-manifest")
            export_proof_attention_trajectory(
                session, proof_ground, data, index, manifest_path
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["trajectory"]["event_count"] += 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ProofAttentionTrajectoryError, "manifest digest mismatch"
            ):
                restore_proof_attention_trajectory(
                    manifest_path, data, index, proof_ground
                )

    def test_rehashed_manifest_cannot_override_independent_event_journal_projection(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        proof_ground = ground(payload)
        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "tamper-journal")
            export_proof_attention_trajectory(
                session, proof_ground, data, index, manifest_path
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["trajectory"]["journal_head_digest"] = "f" * 64
            core = {key: value for key, value in manifest.items() if key != "manifest_digest"}
            manifest["manifest_digest"] = digest(core)
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ProofAttentionTrajectoryError, "EventJournal projection head"
            ):
                restore_proof_attention_trajectory(
                    manifest_path, data, index, proof_ground
                )

    def test_restore_rejects_a_different_current_proof_frontier(self):
        session, payload, _ = make_session()
        session.begin_next()
        original_ground = ground(payload)
        changed_payload = copy.deepcopy(payload)
        changed_payload["transitions"].append({
            "source": "root",
            "tactic": "rfl",
            "subgoals": [],
            "attempt_status": "candidate",
            "evidence_ref": "candidate:rfl",
        })
        changed_ground = ground(changed_payload)

        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "different-ground")
            export_proof_attention_trajectory(
                session, original_ground, data, index, manifest_path
            )
            with self.assertRaisesRegex(
                ProofAttentionTrajectoryError, "does not match supplied ProofGround"
            ):
                restore_proof_attention_trajectory(
                    manifest_path, data, index, changed_ground
                )

    def test_event_stream_is_an_ordered_projection_of_attempt_history(self):
        session, payload, _ = make_session()
        first = session.begin_next()
        execute_to_return(first)
        updated_payload = add_result_payload(payload, first, result_status="timeout")
        updated_ground = ground(updated_payload)
        session.interpret_result(
            updated_ground,
            actor="proof-trace-adapter",
            interpretation_ref=f"interpretation://{first.attempt_id}",
        )
        second = session.begin_next()
        execute_to_return(second)

        with tempfile.TemporaryDirectory() as directory:
            data, index, manifest_path = paths(Path(directory), "order")
            export_proof_attention_trajectory(
                session, updated_ground, data, index, manifest_path, stride=2
            )
            restored = restore_proof_attention_trajectory(
                manifest_path, data, index, updated_ground
            )

        self.assertEqual(restored.to_dict(), session.to_dict())
        self.assertEqual(
            [event["stage"] for attempt in restored.attempts for event in attempt.events],
            [
                "planned", "dispatched", "admitted", "returned", "interpreted",
                "continued", "planned", "dispatched", "admitted", "returned",
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
