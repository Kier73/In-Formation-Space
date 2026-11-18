"""Self-contained counterfactual experiment comparing chain-only vs genesis+spec-bound recovery (RIV-AUDIT-001)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Any, Callable, Mapping, Sequence
import unittest


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(domain: str, obj: Any) -> str:
    return hashlib.sha256(domain.encode("utf-8") + b"\x00" + _canon(obj)).hexdigest()


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    ground_fp: str
    in_rep: str
    out_rep: str
    execute_fn: Callable[[Mapping[str, Any]], tuple[dict[str, Any], str]]
    verify_fn: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None


@dataclass(frozen=True)
class CommittedSlot:
    stage_index: int
    stage_id: str
    prev_digest: str
    source_ground_fp: str
    target_ground_fp: str
    in_rep: str
    out_rep: str
    state: dict[str, Any]
    verdict: str
    continuity_digest: str


def run_pipeline(
    pipeline_id: str,
    stages: Sequence[StageSpec],
    initial_input: Mapping[str, Any],
    ledger: list[CommittedSlot],
    *,
    mode: str,  # "legacy_chain_only" | "inductive_bound"
    require_independent_verifier: bool = True,
    interrupt_after: int | None = None,
) -> tuple[dict[str, Any], dict[str, float]]:
    t0 = time.perf_counter_ns()
    if mode == "inductive_bound" and len(ledger) > len(stages):
        raise RuntimeError("High-water slot exceeds stage count.")
    if mode == "inductive_bound" and require_independent_verifier:
        if any(s.verify_fn is None for s in stages):
            raise RuntimeError("Missing mandatory independent stage verifier.")

    cur_state = dict(initial_input)
    prev_dg = "0" * 64
    prev_fp = _digest("genesis", {"input": cur_state, "pipeline_id": pipeline_id})

    for idx, slot in enumerate(ledger):
        if slot.stage_index != idx or slot.prev_digest != prev_dg:
            raise RuntimeError("Broken continuity hash chain.")
        if mode == "inductive_bound":
            exp = stages[idx]
            if (
                slot.stage_id != exp.stage_id
                or slot.source_ground_fp != prev_fp
                or slot.target_ground_fp != exp.ground_fp
                or slot.in_rep != exp.in_rep
                or slot.out_rep != exp.out_rep
            ):
                raise RuntimeError(f"Recovery identity mismatch at stage {idx}.")
            if exp.verify_fn is not None and not exp.verify_fn(cur_state, slot.state):
                raise RuntimeError(f"Recovered state failed re-verification at stage {idx}.")
        cur_state = dict(slot.state)
        prev_dg = slot.continuity_digest
        prev_fp = slot.target_ground_fp

    for idx in range(len(ledger), len(stages)):
        st_spec = stages[idx]
        nxt, verdict = st_spec.execute_fn(cur_state)
        if not verdict.startswith("PASS"):
            raise RuntimeError("Worker reported non-PASS.")
        if mode == "inductive_bound" and st_spec.verify_fn is not None:
            if not st_spec.verify_fn(cur_state, nxt):
                raise RuntimeError(f"Stage {st_spec.stage_id} rejected by independent verifier.")
            verdict = f"{verdict}|VERIFIED"
        cdg = _digest(
            "receipt",
            {
                "in_rep": st_spec.in_rep,
                "out_rep": st_spec.out_rep,
                "pipeline_id": pipeline_id,
                "prev_digest": prev_dg,
                "source_ground_fp": prev_fp,
                "stage_id": st_spec.stage_id,
                "stage_index": idx,
                "state": nxt,
                "target_ground_fp": st_spec.ground_fp,
                "verdict": verdict,
            },
        )
        ledger.append(
            CommittedSlot(
                stage_index=idx,
                stage_id=st_spec.stage_id,
                prev_digest=prev_dg,
                source_ground_fp=prev_fp,
                target_ground_fp=st_spec.ground_fp,
                in_rep=st_spec.in_rep,
                out_rep=st_spec.out_rep,
                state=dict(nxt),
                verdict=verdict,
                continuity_digest=cdg,
            )
        )
        cur_state = dict(nxt)
        prev_dg = cdg
        prev_fp = st_spec.ground_fp
        if interrupt_after is not None and idx == interrupt_after:
            break

    elapsed_ms = (time.perf_counter_ns() - t0) / 1e6
    return cur_state, {"measured_wall_ms": elapsed_ms}


class TestRecoverySoundnessExperiment(unittest.TestCase):
    def test_discriminating_input_and_spec_mutation_outcomes(self) -> None:
        stages = (
            StageSpec(
                "s0",
                "fp.add10",
                "x_in",
                "v_mid",
                lambda s: ({"v": int(s["x"]) + 10}, "PASS"),
                lambda i, o: int(o["v"]) == int(i["x"]) + 10,
            ),
            StageSpec(
                "s1",
                "fp.mul3",
                "v_mid",
                "v_out",
                lambda s: ({"v": int(s["v"]) * 3}, "PASS"),
                lambda i, o: int(o["v"]) == int(i["v"]) * 3,
            ),
        )

        # 1. Legacy chain-only exhibits silent stale-computation bug when x_0 changes 5 -> 100!
        legacy_ledger: list[CommittedSlot] = []
        run_pipeline("p.demo", stages, {"x": 5}, legacy_ledger, mode="legacy_chain_only", interrupt_after=0)
        wrong_out, _ = run_pipeline("p.demo", stages, {"x": 100}, legacy_ledger, mode="legacy_chain_only")
        self.assertEqual(wrong_out["v"], 45)  # Stale result from x=5 instead of 330!

        # 2. Inductive genesis+spec binding deterministically refuses mutated input, mutated Ground, and truncation!
        sound_ledger: list[CommittedSlot] = []
        run_pipeline("p.sound", stages, {"x": 5}, sound_ledger, mode="inductive_bound", interrupt_after=0)
        with self.assertRaisesRegex(RuntimeError, "Recovery identity mismatch"):
            run_pipeline("p.sound", stages, {"x": 100}, sound_ledger, mode="inductive_bound")

        mutated_stages = (
            StageSpec("s0", "fp.add20_mutated", "x_in", "v_mid", stages[0].execute_fn, stages[0].verify_fn),
            stages[1],
        )
        with self.assertRaisesRegex(RuntimeError, "Recovery identity mismatch"):
            run_pipeline("p.sound", mutated_stages, {"x": 5}, sound_ledger, mode="inductive_bound")

        # Valid resume with identical input & stage specs completes cleanly -> (5 + 10) * 3 = 45
        good_out, tel = run_pipeline("p.sound", stages, {"x": 5}, sound_ledger, mode="inductive_bound")
        self.assertEqual(good_out["v"], 45)
        self.assertGreaterEqual(tel["measured_wall_ms"], 0.0)

        with self.assertRaisesRegex(RuntimeError, "exceeds stage count"):
            run_pipeline("p.sound", (stages[0],), {"x": 5}, sound_ledger, mode="inductive_bound")

    def test_forged_worker_pass_rejected_by_independent_verifier(self) -> None:
        lying_stage = StageSpec(
            "s_lie",
            "fp.add10",
            "x_in",
            "v_out",
            lambda _s: ({"v": 999999}, "PASS:trust_me"),
            lambda i, o: int(o["v"]) == int(i["x"]) + 10,
        )
        ledger: list[CommittedSlot] = []
        with self.assertRaisesRegex(RuntimeError, "rejected by independent verifier"):
            run_pipeline("p.lie", (lying_stage,), {"x": 5}, ledger, mode="inductive_bound")
        self.assertEqual(len(ledger), 0)


if __name__ == "__main__":
    unittest.main()
