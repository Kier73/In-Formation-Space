"""OPS-003: compare incomplete and resource-aware models of a shared-lock workload."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import platform
import random
import statistics
import threading
import time
import uuid
from pathlib import Path

from intervention import settings, delays, inspect_trial, compare, VARIANTS, LIMITS as BASE_LIMITS
from sensitivity import build_sensitivity_report, _digest, BRIDGE
from operation_path_criticality import build_operation_path_report, build_operation_path_trace
from operation_spans import OperationSpanRecorder

MODELS = ("fork_join", "resource_order")
RESOURCE = "ops003.shared-lock"
LIMITS = BASE_LIMITS + [
    "Branch spans measure work while holding a shared mutex; they exclude lock acquisition and waiting. Root spans include these costs.",
    "Resource order comes from a receipt chain appended under that mutex, not from sorting timestamps. Receipts are harness assertions, not authenticated lock ownership.",
    "release_pending_ns is sampled before releasing the mutex, not an observed release instant. The next acquisition and work spans must follow this marker.",
    "Both graph interpretations remain available. Root gain minus predicted path gain is a diagnostic discrepancy, not a claim that OPS-001 predicts root elapsed time.",
    "Lock acquisition order may change between trials and is reported. For two serialized work nodes, the path cost is their sum in either order; this does not generalize to arbitrary resource schedules.",
]
LEASE_FIELDS = {"schema", "resource_id", "attempt_id", "clock_actor_id", "clock_segment_id",
                "ordinal", "span_digest", "requested_ns", "acquired_ns", "release_pending_ns", "previous_digest", "receipt_digest"}


def make_trace(spans, attempt, order=()):
    by_id = {s["span_id"]: s for s in spans}
    pairs = [("a", "join"), ("b", "join")]
    if order:
        pairs.append(tuple(order))
    return build_operation_path_trace(path_id=attempt, attempt_id=attempt,
        root_span_digest=by_id["root"]["span_digest"],
        operation_span_digests=[by_id[n]["span_digest"] for n in ("a", "b", "join")],
        must_complete_before=[{"predecessor_span_digest": by_id[a]["span_digest"],
                               "successor_span_digest": by_id[b]["span_digest"]} for a, b in pairs])


def derive_resource_trace(trial):
    """Validate the ordered receipt evidence before constructing the extra edge."""
    by_id = {s["span_id"]: s for s in trial["spans"]}
    by_digest = {s["span_digest"]: s for s in trial["spans"]}
    root = by_id["root"]
    receipts = trial["resource_receipts"]
    if not isinstance(receipts, list) or len(receipts) != 2:
        raise ValueError("exactly two resource receipts are required")
    previous = None
    release = root["monotonic_start_ns"]
    order = []
    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, dict) or set(receipt) != LEASE_FIELDS:
            raise ValueError("resource receipt fields differ")
        core = {k: v for k, v in receipt.items() if k != "receipt_digest"}
        if receipt["receipt_digest"] != _digest(core):
            raise ValueError("resource receipt digest mismatch")
        if (receipt["schema"] != "in-formation.mutex-work-receipt/0.1"
                or receipt["resource_id"] != RESOURCE
                or receipt["attempt_id"] != root["attempt_id"]
                or receipt["clock_actor_id"] != root["clock_actor_id"]
                or receipt["clock_segment_id"] != root["clock_segment_id"]):
            raise ValueError("resource receipt identity differs from trial")
        if type(receipt["ordinal"]) is not int or receipt["ordinal"] != index or receipt["previous_digest"] != previous:
            raise ValueError("resource receipt chain is invalid")
        span = by_digest.get(receipt["span_digest"])
        if span is None or span["span_id"] not in ("a", "b") or span["span_id"] in order:
            raise ValueError("resource receipt must bind a distinct branch span")
        requested, acquired, pending = receipt["requested_ns"], receipt["acquired_ns"], receipt["release_pending_ns"]
        if any(type(v) is not int for v in (requested, acquired, pending)):
            raise ValueError("resource coordinates must be integer nanoseconds")
        if not (root["monotonic_start_ns"] <= requested <= acquired
                and release <= acquired <= span["monotonic_start_ns"]
                <= span["monotonic_end_ns"] <= pending <= root["monotonic_end_ns"]):
            raise ValueError("resource receipt interval or handoff is inconsistent")
        previous, release = receipt["receipt_digest"], pending
        order.append(span["span_id"])
    if release > by_id["join"]["monotonic_start_ns"]:
        raise ValueError("join must follow the final resource release marker")
    return make_trace(trial["spans"], root["attempt_id"], order), order


def inspect(trial, requested):
    fork_report = inspect_trial(trial, requested)
    expected, order = derive_resource_trace(trial)
    if _digest(trial["resource_trace"]) != _digest(expected):
        raise ValueError("resource trace differs from receipt reconstruction")
    serial_report = build_operation_path_report(trial["spans"], trace=expected)
    return {"fork_join": fork_report, "resource_order": serial_report}, order


def measure_trial(pool, *, attempt, segment, requested):
    recorders = {n: OperationSpanRecorder(clock_actor_id="ops003-process", clock_segment_id=segment)
                 for n in ("root", "a", "b", "join")}
    gate = threading.Barrier(3, timeout=30)
    lock = threading.Lock()
    receipts = []

    def measure(name):
        # Same sleep-operation identities and contexts as OPS-002.
        recorders[name].measure(attempt_id=attempt, span_id=name, operation_id=f"ops002.{name}",
            operation=lambda: time.sleep(requested[name] / 1e9), context={"requested_sleep_ns": requested[name]})

    def worker(name):
        gate.wait()
        requested_ns = time.perf_counter_ns()
        with lock:
            acquired = time.perf_counter_ns()
            measure(name)
            pending = time.perf_counter_ns()
            span = recorders[name].spans[0]
            core = {"schema": "in-formation.mutex-work-receipt/0.1", "resource_id": RESOURCE,
                    "attempt_id": attempt, "clock_actor_id": span["clock_actor_id"],
                    "clock_segment_id": segment, "ordinal": len(receipts),
                    "span_digest": span["span_digest"], "requested_ns": requested_ns, "acquired_ns": acquired,
                    "release_pending_ns": pending,
                    "previous_digest": receipts[-1]["receipt_digest"] if receipts else None}
            receipts.append({**core, "receipt_digest": _digest(core)})

    def root():
        futures = [pool.submit(worker, n) for n in ("a", "b")]
        gate.wait()
        for future in futures:
            future.result(timeout=30)
        measure("join")

    recorders["root"].measure(attempt_id=attempt, span_id="root", operation_id="ops002.root", operation=root)
    if any(r.measurement_errors for r in recorders.values()):
        raise ValueError("incomplete measurement evidence")
    spans = [s for r in recorders.values() for s in r.spans]
    trial = {"requested_sleep_ns": requested, "spans": spans,
             "trace": make_trace(spans, attempt), "resource_receipts": receipts}
    trial["resource_trace"], _ = derive_resource_trace(trial)
    inspect(trial, requested)
    return trial


def predict(baseline, config, variant):
    requested = delays(config, variant)
    reductions = {s["span_digest"]: config["baseline_ns"] - requested[s["span_id"]]
                  for s in baseline["spans"] if s["span_id"] in ("a", "b")}
    return {model: build_sensitivity_report(baseline["spans"],
                trace=baseline["trace" if model == "fork_join" else "resource_trace"], reductions=reductions)
            for model in MODELS}


def summarize(config, blocks):
    settings(**config)
    if len(blocks) != config["blocks"]:
        raise ValueError("block count differs")
    rng, attempts, rows = random.Random(config["seed"]), set(), []
    for index, block in enumerate(blocks):
        order = list(VARIANTS)
        rng.shuffle(order)
        if block["order"] != order or set(block["variants"]) != set(VARIANTS):
            raise ValueError("variant coverage or seeded order differs")
        baseline = block["baseline"]
        base_reports, base_order = inspect(baseline, delays(config, "baseline"))
        for trial in [baseline] + [block["variants"][v]["trial"] for v in order]:
            attempt = trial["trace"]["attempt_id"]
            if attempt in attempts:
                raise ValueError("duplicate trial identity")
            attempts.add(attempt)
        for variant in order:
            entry = block["variants"][variant]
            predictions = predict(baseline, config, variant)
            if _digest(entry["predictions"]) != _digest(predictions):
                raise ValueError("predictions differ from baseline and plan")
            observed, observed_order = inspect(entry["trial"], delays(config, variant))
            for model in MODELS:
                metrics = compare(base_reports[model], observed[model], predictions[model])
                rows.append({"block": index, "variant": variant, "model": model,
                    "resource_order_changed": base_order != observed_order, **metrics,
                    "root_gain_minus_predicted_path_gain_ns": metrics["observed_root_gain_ns"] - metrics["predicted_path_gain_ns"],
                    "baseline_root_slack_ns": base_reports[model]["root_slack_ns"],
                    "observed_root_slack_ns": observed[model]["root_slack_ns"]})
    metrics = [k for k in rows[0] if k.endswith("_ns")]
    summary = {model: {variant: {k: {"median": statistics.median(r[k] for r in rows if r["model"] == model and r["variant"] == variant),
                    "min": min(r[k] for r in rows if r["model"] == model and r["variant"] == variant),
                    "max": max(r[k] for r in rows if r["model"] == model and r["variant"] == variant)} for k in metrics}
                    for variant in VARIANTS} for model in MODELS}
    return {"paired_comparisons": rows, "by_model": summary}


def validate_bundle(bundle):
    core = {k: v for k, v in bundle.items() if k != "bundle_digest"}
    if bundle.get("bundle_digest") != _digest(core):
        raise ValueError("bundle digest mismatch")
    if bundle["schema"] != "in-formation.operation-path-contention/0.1" or bundle["interpretation_limits"] != LIMITS:
        raise ValueError("schema or interpretation limits differ")
    if _digest(bundle["analysis"]) != _digest(summarize(bundle["config"], bundle["blocks"])):
        raise ValueError("analysis differs from reconstruction")
    return bundle


def run_experiment(*, blocks=7, baseline_ns=80_000_000, reduced_ns=20_000_000,
                   join_ns=10_000_000, seed=20261113):
    config = settings(blocks, baseline_ns, reduced_ns, join_ns, seed)
    segment, rng, observations = str(uuid.uuid4()), random.Random(seed), []
    with ThreadPoolExecutor(max_workers=2) as pool:
        measure_trial(pool, attempt="warmup", segment=segment, requested=delays(config, "baseline"))
        for index in range(blocks):
            baseline = measure_trial(pool, attempt=f"{index}:baseline", segment=segment, requested=delays(config, "baseline"))
            order = list(VARIANTS)
            rng.shuffle(order)
            variants = {}
            for variant in order:
                predictions = predict(baseline, config, variant)
                trial = measure_trial(pool, attempt=f"{index}:{variant}", segment=segment, requested=delays(config, variant))
                variants[variant] = {"predictions": predictions, "trial": trial}
            observations.append({"baseline": baseline, "order": order, "variants": variants})
    sources = [Path(__file__), Path(__file__).with_name("sensitivity.py"), Path(__file__).with_name("intervention.py"),
               BRIDGE / "operation_spans.py", BRIDGE / "operation_path_criticality.py"]
    core = {"schema": "in-formation.operation-path-contention/0.1", "config": config,
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "clock": vars(time.get_clock_info("perf_counter"))},
            "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            "blocks": observations, "analysis": summarize(config, observations), "interpretation_limits": list(LIMITS)}
    return validate_bundle({**core, "bundle_digest": _digest(core)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--blocks", type=int, default=7)
    args = parser.parse_args()
    bundle = (validate_bundle(json.loads(args.verify.read_text(encoding="utf-8")))
              if args.verify else run_experiment(blocks=args.blocks))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(bundle["analysis"]["by_model"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
