from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest

from runner_crash_semantics import (
    RunnerSemanticsError,
    SQLiteIdempotentEffectSink,
    SQLitePureResultRunner,
    nontransactional_recovery_outcomes,
)


class SimulatedProcessCrash(RuntimeError):
    pass


class RunnerCrashSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_pure_result_replays_after_commit_before_response(self):
        runner = SQLitePureResultRunner(self.root / "pure.sqlite")
        calls = []

        def compute(request):
            calls.append(request)
            return {"goal": request["goal"], "status": "finished"}

        def crash_after_commit():
            raise SimulatedProcessCrash("runner died after commit, before response")

        with self.assertRaises(SimulatedProcessCrash):
            runner.execute_once(
                "ticket-1", {"goal": "A -> A"},
                compute=compute, after_commit=crash_after_commit,
            )

        replay = runner.execute_once(
            "ticket-1", {"goal": "A -> A"}, compute=compute
        )
        self.assertEqual(replay, {"goal": "A -> A", "status": "finished"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(runner.result_count(), 1)

    def test_crash_before_pure_result_commit_may_repeat_computation(self):
        runner = SQLitePureResultRunner(self.root / "pure-before-commit.sqlite")
        calls = []

        def fail_once(request):
            calls.append(request)
            if len(calls) == 1:
                raise SimulatedProcessCrash("runner died before result commit")
            return {"status": "finished"}

        with self.assertRaises(SimulatedProcessCrash):
            runner.execute_once("ticket-2", {"goal": "B"}, compute=fail_once)

        self.assertEqual(runner.result_count(), 0)
        self.assertEqual(
            runner.execute_once("ticket-2", {"goal": "B"}, compute=fail_once),
            {"status": "finished"},
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(runner.result_count(), 1)

    def test_pure_runner_rejects_execution_id_reuse_with_different_request(self):
        runner = SQLitePureResultRunner(self.root / "pure-conflict.sqlite")
        runner.execute_once("ticket-3", {"goal": "C"}, compute=lambda _: {"ok": True})
        with self.assertRaisesRegex(RunnerSemanticsError, "different request digest"):
            runner.execute_once("ticket-3", {"goal": "D"}, compute=lambda _: {"ok": True})

    def test_concurrent_pure_retries_compute_and_publish_once(self):
        database = self.root / "pure-concurrent.sqlite"
        runners = [SQLitePureResultRunner(database), SQLitePureResultRunner(database)]
        lock = threading.Lock()
        calls = []
        barrier = threading.Barrier(2)

        def compute(request):
            with lock:
                calls.append(request)
            return {"result": request["n"] * 2}

        def invoke(runner):
            barrier.wait()
            return runner.execute_once("ticket-4", {"n": 21}, compute=compute)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, runners))

        self.assertEqual(results, [{"result": 42}, {"result": 42}])
        self.assertEqual(len(calls), 1)
        self.assertEqual(runners[0].result_count(), 1)

    def test_effect_and_idempotency_receipt_survive_lost_response(self):
        sink = SQLiteIdempotentEffectSink(self.root / "effects.sqlite")
        command = {"operation": "publish", "artifact": "sha256:abc"}

        def crash_after_provider_commit():
            raise SimulatedProcessCrash("provider committed, response was lost")

        with self.assertRaises(SimulatedProcessCrash):
            sink.apply_once("ticket-5", command, after_commit=crash_after_provider_commit)

        receipt = sink.apply_once("ticket-5", command)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(sink.effect_count(), 1)
        self.assertEqual(sink.receipt_for("ticket-5"), receipt)

    def test_effect_provider_rejects_conflicting_command_under_same_ticket(self):
        sink = SQLiteIdempotentEffectSink(self.root / "effects-conflict.sqlite")
        sink.apply_once("ticket-6", {"write": "first"})
        with self.assertRaisesRegex(RunnerSemanticsError, "different command digest"):
            sink.apply_once("ticket-6", {"write": "second"})
        self.assertEqual(sink.effect_count(), 1)

    def test_concurrent_effect_retries_create_one_effect(self):
        database = self.root / "effects-concurrent.sqlite"
        sinks = [SQLiteIdempotentEffectSink(database), SQLiteIdempotentEffectSink(database)]
        barrier = threading.Barrier(2)

        def invoke(sink):
            barrier.wait()
            return sink.apply_once("ticket-7", {"write": "one"})

        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(invoke, sinks))

        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(sinks[0].effect_count(), 1)

    def test_nontransactional_started_state_is_ambiguous(self):
        # Both worlds have exactly the same durable runner record: "started".
        # The missing fact is whether the independent effect committed first.
        crash_before_effect = nontransactional_recovery_outcomes(
            effect_already_happened=False
        )
        crash_after_effect = nontransactional_recovery_outcomes(
            effect_already_happened=True
        )

        self.assertEqual(crash_before_effect, {"retry_started": 1, "skip_started": 0})
        self.assertEqual(crash_after_effect, {"retry_started": 2, "skip_started": 1})
        self.assertNotEqual(
            crash_before_effect["retry_started"],
            crash_after_effect["retry_started"],
        )
        self.assertNotEqual(
            crash_before_effect["skip_started"],
            crash_after_effect["skip_started"],
        )


if __name__ == "__main__":
    unittest.main()
