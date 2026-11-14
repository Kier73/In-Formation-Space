"""Fresh-process, forced-stop recovery benchmark for PNF-004."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from mailcpu.structural_memory import StructuralMemoryRegistry, StructuralMemoryRefused
from .ground_model import GroundModelHost, affine_at, candidates, canonical, sha, task


def cases():
    result = []
    for a in (1, 5, 13, 21):
        for c in (1, 7):
            for x0 in (3, 11):
                trace = [x0]
                for _ in range(15):
                    trace.append((a * trace[-1] + c) % 97)
                result.append({"id": f"a{a}-c{c}-x{x0}", "trace": trace, "modulus": 97,
                               "expected": affine_at(a, c, 97, x0, 10**12),
                               "expected_family": "int" if a == 1 else "lcg"})
    return result


def benchmark(host):
    outcomes = []
    started = time.perf_counter_ns()
    for sequence, case in enumerate(cases(), 1):
        laws, _ = candidates(case["trace"][:8], case["modulus"])
        registry = StructuralMemoryRegistry()
        attempts = 0
        for law in laws:
            attempts += 1
            try:
                registry.propose("baseline", law, dict(enumerate(case["trace"])))
                break
            except StructuralMemoryRefused:
                pass
        outcome = task(host, case["trace"], case["modulus"], case["id"], sequence)
        if (outcome["status"] != "admitted" or outcome["navigation_value"] != case["expected"]
                or outcome["family"] != case["expected_family"]):
            raise ValueError("functional Ground task failed")
        outcome.update({"id": case["id"], "baseline_candidate_attempts": attempts,
                        "ranked_candidate_attempts": 1})
        outcomes.append(outcome)
    return {"cases": outcomes, "case_count": len(outcomes), "successful_ground_tasks": len(outcomes),
            "baseline_candidate_attempts": sum(c["baseline_candidate_attempts"] for c in outcomes),
            "ranked_candidate_attempts": len(outcomes), "native_handler_calls": host.calls,
            "elapsed_ns_local_including_baseline": time.perf_counter_ns() - started,
            "model_digest": host.model_digest, "manifest_digest": host.manifest.manifest_digest,
            "execution_ground_digest": sha(canonical(host.ground.to_dict())),
            "parameter_spec_digest": host.references[0].spec_digest,
            "parameter_coordinates": [r.coordinate for r in host.references],
            "model_description_bytes": host.manifest.size_bytes,
            "persisted_dense_weight_payload_bytes": 0,
            "inference_engine": host.engine, "operator_contract_digest": host.spec.digest,
            "inference_after_restart": "fresh inference; no cross-process exactly-once claim"}


def worker(root, phase, policy_path, ready):
    policy = json.loads(policy_path.read_text()) if phase == "restore" else None
    host = GroundModelHost(root, restored_policy=policy,
                          engine="dense-reference" if phase == "create" else "addressed-scalar")
    outcome = benchmark(host)
    result = {"pid": os.getpid(), "phase": phase, "benchmark": outcome}
    if phase == "create":
        result["policy"] = host.save()
        result["persisted_storage"] = {
            "checkpoint_file_bytes": (root / "system.json").stat().st_size,
            "page_backing_file_bytes": sum(p.stat().st_size for p in (root / "pages").rglob("*") if p.is_file()),
            "model_description_bytes": host.manifest.size_bytes,
            "includes": "checkpoint includes laws, observations, receipts, read cache and execution ledger",
        }
    # Publish a complete result before the supervisor terminates this process.
    staging = ready.with_suffix(".tmp")
    with staging.open("wb") as stream:
        stream.write(canonical(result))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, ready)
    if phase == "create":
        # Deliberate test barrier: supervisor kills after a durable checkpoint.
        sys.stdin.read()


def run_process_benchmark():
    with tempfile.TemporaryDirectory(prefix="pnf004-restart-") as directory:
        root = Path(directory)
        before = root / "before.json"
        policy_path = root / "receiver-policy.json"
        command = [sys.executable, "-m", "experiments.ground_model_addressability.run_benchmark",
                   "--root", str(root), "--worker", "create", "--ready", str(before)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 90
            while not before.exists():
                if process.poll() is not None:
                    raise RuntimeError("initial host failed: " + process.communicate()[1].decode(errors="replace"))
                if time.monotonic() > deadline:
                    raise TimeoutError("initial host did not publish checkpoint")
                time.sleep(.01)
            first = json.loads(before.read_bytes())
            if first["pid"] != process.pid or process.poll() is not None:
                raise ValueError("initial receiver was not alive at the forced-stop barrier")
            process.kill()
            process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
        policy_path.write_bytes(canonical(first["policy"]))
        after = root / "after.json"
        completed = subprocess.run([sys.executable, "-m", "experiments.ground_model_addressability.run_benchmark",
            "--root", str(root), "--worker", "restore", "--policy", str(policy_path), "--ready", str(after)],
            capture_output=True, timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if completed.returncode:
            raise RuntimeError("restored host failed: " + completed.stderr.decode(errors="replace"))
        second = json.loads(after.read_bytes())
        a, b = first["benchmark"], second["benchmark"]
        stable = ("cases", "model_digest", "manifest_digest", "parameter_spec_digest", "parameter_coordinates")
        if any(a[k] != b[k] for k in stable):
            raise ValueError("model, task Grounds or outputs changed after reconstruction")
        if first["pid"] == second["pid"] or a["execution_ground_digest"] == b["execution_ground_digest"]:
            raise ValueError("fresh process/execution Ground was not established")
        return {"schema": "ifs.pnf004.functional-benchmark.v1", "status": "passed",
                "before": first, "after": second, "forced_stop_after_checkpoint": True,
                "stable_fields": list(stable), "separate_processes": True, "same_physical_host": True,
                "network_transfer_performed": False, "dense_model_training_performed": False,
                "model_kind": "hand-designed addressable 2->2 ReLU->1 neural ranker",
                "generalization_claimed": False, "speedup_claimed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("create", "restore"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.root, args.worker, args.policy, args.ready)
    else:
        result = run_process_benchmark()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        b = result["after"]["benchmark"]
        print(json.dumps({"status": result["status"], "tasks": b["case_count"],
                          "baseline_candidate_attempts": b["baseline_candidate_attempts"],
                          "ranked_candidate_attempts": b["ranked_candidate_attempts"],
                          "description_bytes": b["model_description_bytes"],
                          "parameter_coordinates": b["parameter_coordinates"],
                          "forced_stop_reconstruction": True}))


if __name__ == "__main__":
    main()
