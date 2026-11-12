from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mailcpu.transport import InMemoryTransport

from proof_action_continuity import (
    ProofActionContinuityError,
    export_proof_action_continuity_bundle,
    restore_proof_action_continuity_bundle,
)
from proof_attention_trajectory import export_proof_attention_trajectory
from test_proof_action_reliable_channel import make_endpoints


def write_trajectory(session, proof_ground, directory: Path, name: str):
    data_path = directory / f"{name}.mtrj"
    index_path = directory / f"{name}.mtrj.idx"
    manifest_path = directory / f"{name}.manifest.json"
    manifest = export_proof_attention_trajectory(
        session,
        proof_ground,
        data_path,
        index_path,
        manifest_path,
        stride=2,
    )
    return manifest, manifest_path, data_path, index_path


def restore_bundle(bundle, proof_ground, paths):
    _manifest, manifest_path, data_path, index_path = paths
    return restore_proof_action_continuity_bundle(
        bundle,
        proof_ground,
        restore_transport=InMemoryTransport.from_snapshot,
        trajectory_manifest_path=manifest_path,
        trajectory_data_path=data_path,
        trajectory_index_path=index_path,
    )


class ProofActionContinuityTests(unittest.TestCase):
    def test_bundle_restores_pending_dispatch_against_the_exact_trajectory_cut(self):
        _session, _trace, proof_ground, _transport, host, worker = make_endpoints()
        dispatched = host.dispatch_next()

        with tempfile.TemporaryDirectory() as temporary:
            paths = write_trajectory(
                host.session, proof_ground, Path(temporary), "dispatched"
            )
            manifest = paths[0]
            bundle = export_proof_action_continuity_bundle(host, worker, manifest)

            transport2, host2, worker2, history = restore_bundle(
                bundle, proof_ground, paths
            )
            self.assertIsInstance(transport2, InMemoryTransport)
            self.assertEqual(
                history.to_dict()["session_digest"],
                host2.session.to_dict()["session_digest"],
            )
            self.assertEqual(
                bundle["trajectory_binding"]["manifest_digest"],
                manifest["manifest_digest"],
            )

            received = worker2.receive_request()
            self.assertIsNotNone(received)
            self.assertEqual(received.request_sequence, dispatched.request_sequence)
            self.assertEqual(received.request, dispatched.request)
            self.assertTrue(host2.observe_request_admission())
            self.assertEqual(host2.active_attempt.status, "admitted")
            # The history view remains the immutable snapshot at export time.
            self.assertEqual(history.active_attempt.status, "dispatched")

    def test_bundle_restores_after_result_return_with_session_and_history_aligned(self):
        from proof_action_protocol import make_proof_action_result
        from test_proof_action_execution import add_result_payload
        from test_proof_action_protocol import return_evidence
        from test_proof_action_reliable_channel import deliver_request_and_admit

        _session, source_trace, proof_ground, _transport, host, worker = make_endpoints()
        _dispatch, received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        worker.send_result(make_proof_action_result(
            received.request,
            return_evidence=return_evidence(attempt),
            proof_trace=add_result_payload(source_trace, attempt),
        ))

        with tempfile.TemporaryDirectory() as temporary:
            paths = write_trajectory(
                host.session, proof_ground, Path(temporary), "returned"
            )
            bundle = export_proof_action_continuity_bundle(host, worker, paths[0])
            _transport2, host2, worker2, history = restore_bundle(
                bundle, proof_ground, paths
            )
            imported = host2.receive_result()
            self.assertIsNotNone(imported)
            self.assertEqual(host2.session.attempts[0].status, "interpreted")
            self.assertEqual(history.attempts[0].status, "admitted")
            self.assertEqual(worker2.process_result_acknowledgements(), (1,))
            self.assertEqual(worker2.pending_result_sequences, ())

    def test_export_rejects_a_trajectory_from_a_different_session(self):
        _session_a, _trace_a, pg_a, _transport_a, host_a, worker_a = make_endpoints()
        _session_b, _trace_b, pg_b, _transport_b, host_b, worker_b = make_endpoints()
        from proof_action_execution import ProofAttentionSession

        host_a.dispatch_next()
        other_roots = tuple(host_b.session.plan["active_root_obligation_ids"])
        host_b.session = ProofAttentionSession(
            pg_b,
            other_roots,
            attempt_id_prefix="different-proof-run",
            query_label="investigate a distinct root intention",
        )
        host_b.dispatch_next()

        with tempfile.TemporaryDirectory() as temporary:
            manifest_b = write_trajectory(
                host_b.session, pg_b, Path(temporary), "other-session"
            )[0]
            with self.assertRaisesRegex(
                ProofActionContinuityError,
                "does not describe the host's exact session snapshot",
            ):
                export_proof_action_continuity_bundle(host_a, worker_a, manifest_b)

    def test_restore_rejects_a_different_persisted_trajectory_manifest(self):
        _session_a, _trace_a, pg_a, _transport_a, host_a, worker_a = make_endpoints()
        _session_b, _trace_b, pg_b, _transport_b, host_b, worker_b = make_endpoints()
        host_a.dispatch_next()
        host_b.dispatch_next()

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            paths_a = write_trajectory(host_a.session, pg_a, directory, "session-a")
            paths_b = write_trajectory(host_b.session, pg_b, directory, "session-b")
            bundle = export_proof_action_continuity_bundle(host_a, worker_a, paths_a[0])

            with self.assertRaisesRegex(
                ProofActionContinuityError,
                "does not match the continuity bundle binding",
            ):
                restore_proof_action_continuity_bundle(
                    bundle,
                    pg_a,
                    restore_transport=InMemoryTransport.from_snapshot,
                    trajectory_manifest_path=paths_b[1],
                    trajectory_data_path=paths_b[2],
                    trajectory_index_path=paths_b[3],
                )

    def test_restore_rejects_modified_append_only_trajectory_bytes(self):
        _session, _trace, proof_ground, _transport, host, worker = make_endpoints()
        host.dispatch_next()

        with tempfile.TemporaryDirectory() as temporary:
            paths = write_trajectory(
                host.session, proof_ground, Path(temporary), "tampered"
            )
            bundle = export_proof_action_continuity_bundle(host, worker, paths[0])
            data_path = paths[2]
            raw = bytearray(data_path.read_bytes())
            raw[-1] ^= 0x01
            data_path.write_bytes(raw)

            with self.assertRaises(ProofActionContinuityError):
                restore_bundle(bundle, proof_ground, paths)


if __name__ == "__main__":
    unittest.main(verbosity=2)
