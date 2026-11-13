"""OPS-002: measured blocking fork/join interventions against OPS-001 predictions."""
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

from sensitivity import build_sensitivity_report, _digest, BRIDGE
from operation_path_criticality import build_operation_path_report, build_operation_path_trace
from operation_spans import OperationSpanRecorder

VARIANTS = ("control", "a", "b", "both")
LIMITS = [
    "One process with two threads sharing one monotonic clock; no distributed-host or CPU-throughput claim.",
    "Work is controlled blocking sleep. Requested delay reduction is a hypothesis about elapsed duration, not measured acceleration.",
    "Baseline runs first in each block; the four subsequent variants are shuffled. Time drift and shared-baseline correlations remain.",
    "Signed paired differences, including slowdowns, are retained. Descriptive ranges are not confidence intervals or causal identification.",
    "Predictions are constructed before intervention execution by this harness; content digests do not authenticate execution, timing, or source identity.",
    "Root elapsed time includes scheduling and instrumentation. OPS-001 predicts dependency cost only; root slack changes are reported separately.",
]


def settings(blocks, baseline_ns, reduced_ns, join_ns, seed):
    for name, value in [("blocks", blocks), ("baseline_ns", baseline_ns),
                        ("reduced_ns", reduced_ns), ("join_ns", join_ns), ("seed", seed)]:
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if blocks < 1 or not 0 <= reduced_ns < baseline_ns:
        raise ValueError("need positive blocks and reduced_ns < baseline_ns")
    return dict(blocks=blocks, baseline_ns=baseline_ns, reduced_ns=reduced_ns,
                join_ns=join_ns, seed=seed)


def delays(config, variant):
    if variant not in ("baseline",) + VARIANTS:
        raise ValueError("unknown variant")
    return {"a": config["reduced_ns"] if variant in ("a", "both") else config["baseline_ns"],
            "b": config["reduced_ns"] if variant in ("b", "both") else config["baseline_ns"],
            "join": config["join_ns"]}


def measure_trial(pool, *, attempt, segment, requested):
    """Separate recorders avoid sharing mutable recorder state across threads."""
    recorders = {name: OperationSpanRecorder(clock_actor_id="ops002-process",
                 clock_segment_id=segment) for name in ("root", "a", "b", "join")}
    gate = threading.Barrier(3, timeout=30)

    def measure(name):
        return recorders[name].measure(attempt_id=attempt, span_id=name,
            operation_id=f"ops002.{name}", operation=lambda: time.sleep(requested[name] / 1e9),
            context={"requested_sleep_ns": requested[name]})

    def worker(name):
        gate.wait()
        measure(name)

    def root():
        futures = [pool.submit(worker, name) for name in ("a", "b")]
        gate.wait()
        for future in futures:
            future.result(timeout=30)
        measure("join")

    recorders["root"].measure(attempt_id=attempt, span_id="root",
        operation_id="ops002.root", operation=root)
    if any(r.measurement_errors for r in recorders.values()):
        raise ValueError("measurement errors: no complete evidence report available")
    spans = [s for r in recorders.values() for s in r.spans]
    by_id = {s["span_id"]: s for s in spans}
    trace = build_operation_path_trace(path_id=attempt, attempt_id=attempt,
        root_span_digest=by_id["root"]["span_digest"],
        operation_span_digests=[by_id[n]["span_digest"] for n in ("a", "b", "join")],
        must_complete_before=[{"predecessor_span_digest": by_id[n]["span_digest"],
                               "successor_span_digest": by_id["join"]["span_digest"]} for n in ("a", "b")])
    trial = {"requested_sleep_ns": requested, "spans": spans, "trace": trace}
    inspect_trial(trial, requested)
    return trial


def inspect_trial(trial, requested):
    if trial["requested_sleep_ns"] != requested:
        raise ValueError("trial requested delays differ from experiment plan")
    spans, trace = trial["spans"], trial["trace"]
    report = build_operation_path_report(spans, trace=trace)
    by_id = {s["span_id"]: s for s in spans}
    if set(by_id) != {"root", "a", "b", "join"} or len(spans) != 4:
        raise ValueError("trial must contain exactly root, a, b, join")
    for name, s in by_id.items():
        if s["outcome"] != "succeeded" or s["operation_id"] != f"ops002.{name}":
            raise ValueError("unexpected operation or failed workload")
        if name != "root" and s["context"] != {"requested_sleep_ns": requested[name]}:
            raise ValueError("span delay context differs from plan")
    expected = build_operation_path_trace(path_id=trace["path_id"], attempt_id=trace["attempt_id"],
        root_span_digest=by_id["root"]["span_digest"],
        operation_span_digests=[by_id[n]["span_digest"] for n in ("a", "b", "join")],
        must_complete_before=[{"predecessor_span_digest": by_id[n]["span_digest"],
                               "successor_span_digest": by_id["join"]["span_digest"]} for n in ("a", "b")])
    if trace != expected:
        raise ValueError("trial graph differs from fixed fork/join plan")
    return report


def predict(baseline, config, variant):
    requested = delays(config, variant)
    reductions = {s["span_digest"]: config["baseline_ns"] - requested[s["span_id"]]
                  for s in baseline["spans"] if s["span_id"] in ("a", "b")}
    # If a requested reduction exceeds its measured baseline duration, fail;
    # never clip it silently or infer a reduction from the later observation.
    return build_sensitivity_report(baseline["spans"], trace=baseline["trace"], reductions=reductions)


def compare(baseline_report, observed_report, prediction):
    predicted = prediction["counterfactual_benefit_ns"]
    path_gain = baseline_report["known_dependency_path_ns"] - observed_report["known_dependency_path_ns"]
    root_gain = baseline_report["root_elapsed_ns"] - observed_report["root_elapsed_ns"]
    slack_gain = baseline_report["root_slack_ns"] - observed_report["root_slack_ns"]
    return {"predicted_path_gain_ns": predicted, "observed_path_gain_ns": path_gain,
            "observed_root_gain_ns": root_gain, "observed_slack_gain_ns": slack_gain,
            "path_prediction_error_ns": path_gain - predicted}


def summarize(config, blocks):
    settings(**config)
    if len(blocks) != config["blocks"]:
        raise ValueError("block count differs from plan")
    rows = []
    rng = random.Random(config["seed"])
    attempts = set()
    for index, block in enumerate(blocks):
        order = list(VARIANTS)
        rng.shuffle(order)
        if block["order"] != order or set(block["variants"]) != set(VARIANTS):
            raise ValueError("variant order or coverage differs from seeded plan")
        baseline = block["baseline"]
        base_report = inspect_trial(baseline, delays(config, "baseline"))
        for trial in [baseline] + [block["variants"][v]["trial"] for v in order]:
            attempt = trial["trace"]["attempt_id"]
            if attempt in attempts:
                raise ValueError("duplicate trial attempt identity")
            attempts.add(attempt)
        for variant in order:
            entry = block["variants"][variant]
            prediction = predict(baseline, config, variant)
            if _digest(prediction) != _digest(entry["prediction"]):
                raise ValueError("prediction differs from baseline and planned intervention")
            observed = inspect_trial(entry["trial"], delays(config, variant))
            rows.append({"block": index, "variant": variant, **compare(base_report, observed, prediction)})
    metrics = [k for k in rows[0] if k not in ("block", "variant")]
    summary = {}
    for variant in VARIANTS:
        samples = [r for r in rows if r["variant"] == variant]
        summary[variant] = {k: {"median": statistics.median(r[k] for r in samples),
                               "min": min(r[k] for r in samples), "max": max(r[k] for r in samples)} for k in metrics}
    return {"paired_comparisons": rows, "by_variant": summary}


def validate_bundle(bundle):
    core = {k: v for k, v in bundle.items() if k != "bundle_digest"}
    if bundle.get("bundle_digest") != _digest(core):
        raise ValueError("bundle digest mismatch")
    if bundle["schema"] != "in-formation.operation-path-intervention/0.1" or bundle["interpretation_limits"] != LIMITS:
        raise ValueError("unsupported schema or altered interpretation limits")
    if _digest(bundle["analysis"]) != _digest(summarize(bundle["config"], bundle["blocks"])):
        raise ValueError("analysis differs from retained evidence")
    return bundle


def run_experiment(*, blocks=7, baseline_ns=80_000_000, reduced_ns=20_000_000,
                   join_ns=10_000_000, seed=20261113):
    config = settings(blocks, baseline_ns, reduced_ns, join_ns, seed)
    segment = str(uuid.uuid4())
    rng = random.Random(seed)
    observations = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        # One unretained warm-up trial initializes both workers.
        measure_trial(pool, attempt="warmup", segment=segment, requested=delays(config, "baseline"))
        for index in range(blocks):
            baseline = measure_trial(pool, attempt=f"{index}:baseline", segment=segment, requested=delays(config, "baseline"))
            order = list(VARIANTS)
            rng.shuffle(order)
            variants = {}
            for variant in order:
                prediction = predict(baseline, config, variant)
                trial = measure_trial(pool, attempt=f"{index}:{variant}", segment=segment, requested=delays(config, variant))
                variants[variant] = {"prediction": prediction, "trial": trial}
            observations.append({"baseline": baseline, "order": order, "variants": variants})
    sources = [Path(__file__), Path(__file__).with_name("sensitivity.py"),
               BRIDGE / "operation_spans.py", BRIDGE / "operation_path_criticality.py"]
    core = {"schema": "in-formation.operation-path-intervention/0.1", "config": config,
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "clock": vars(time.get_clock_info("perf_counter"))},
            "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            "blocks": observations, "analysis": summarize(config, observations),
            "interpretation_limits": list(LIMITS)}
    return validate_bundle({**core, "bundle_digest": _digest(core)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path, help="reconstruct a retained bundle without running sleeps")
    parser.add_argument("--blocks", type=int, default=7)
    args = parser.parse_args()
    if args.verify:
        bundle = validate_bundle(json.loads(args.verify.read_text(encoding="utf-8")))
    else:
        bundle = run_experiment(blocks=args.blocks)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(bundle["analysis"]["by_variant"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
