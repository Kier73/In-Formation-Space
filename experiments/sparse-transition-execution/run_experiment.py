"""Measure sparse finite-transition realization against its dense source."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
RCN_EXPERIMENT = ROOT / "experiments" / "realization-cost-navigation"
if str(RCN_EXPERIMENT) not in sys.path:
    sys.path.insert(0, str(RCN_EXPERIMENT))

# Reuse RCN-001's immutable workload family and scalar oracles.
rcn = importlib.import_module("run_experiment")

from mailcpu.semantic_translation import (  # noqa: E402
    EffectClass,
    ObservationContract,
    ReplayClass,
    RepresentationRef,
    ResourceBound,
    TranslationContract,
    canonical_value_digest,
    compare_projected_observations,
)
from mailcpu.transition_space import SparseTransitionReLUNetwork  # noqa: E402

COMPILERS = {
    "minterm": "mailcpu.transition_space.compile_transition_table",
    "direct_dag": "mailcpu.transition_space.compile_compositional_transition_program",
    "live_dag": "mailcpu.transition_space.compile_live_compositional_transition_program",
}
REPEATS = 7


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_size(snapshot: dict[str, Any]) -> int:
    return len(json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8"))


def _measure_full_domain(
    model: Any,
    input_rows: Sequence[tuple[int, ...]],
    *,
    expected_checksum: int,
    repeats: int = REPEATS,
) -> dict[str, Any]:
    """Measure repeated full-domain predict sweeps with output checksum guards."""
    warmup = sum(sum(model.predict(values)) for values in input_rows)
    if warmup != expected_checksum:
        raise AssertionError("warmup inference checksum changed")
    samples: list[int] = []
    for _ in range(repeats):
        checksum = 0
        started = time.perf_counter_ns()
        for values in input_rows:
            checksum += sum(model.predict(values))
        elapsed = time.perf_counter_ns() - started
        if checksum != expected_checksum:
            raise AssertionError("timed inference checksum changed")
        samples.append(elapsed)
    return {
        "sample_count": len(samples),
        "samples_ns": samples,
        "median_ns": int(statistics.median(samples)),
        "minimum_ns": min(samples),
        "maximum_ns": max(samples),
        "median_ns_per_input": (
            statistics.median(samples) / len(input_rows) if input_rows else 0.0
        ),
        "measured_call": (
            "predict; includes input validation, forward evaluation, and Boolean output validation"
        ),
    }


def _measure_conversion(
    dense: Any,
    *,
    repeats: int = REPEATS,
) -> tuple[SparseTransitionReLUNetwork, dict[str, Any]]:
    samples: list[int] = []
    sparse: SparseTransitionReLUNetwork | None = None
    for _ in range(repeats):
        started = time.perf_counter_ns()
        candidate = SparseTransitionReLUNetwork.from_dense(dense)
        samples.append(time.perf_counter_ns() - started)
        if sparse is None:
            sparse = candidate
        elif candidate.digest != sparse.digest:
            raise AssertionError("dense-to-sparse conversion is not stable")
    assert sparse is not None
    return sparse, {
        "sample_count": len(samples),
        "samples_ns": samples,
        "median_ns": int(statistics.median(samples)),
        "minimum_ns": min(samples),
        "maximum_ns": max(samples),
        "measured_call": (
            "SparseTransitionReLUNetwork.from_dense; excludes dense model compilation"
        ),
    }


def _translation_contract(
    workload: Any,
    table: Any,
    route_name: str,
    dense: Any,
    sparse: SparseTransitionReLUNetwork,
) -> TranslationContract:
    source_ref = RepresentationRef.from_payload(
        "mailcpu.dense-finite-transition-relu", 1, dense.snapshot()
    )
    target_ref = RepresentationRef.from_payload(
        "mailcpu.sparse-finite-transition-relu", 1, sparse.snapshot()
    )
    mapping_ref = RepresentationRef.from_payload(
        "mailcpu.dense-to-sparse-transition-execution",
        1,
        {
            "compiler": COMPILERS[route_name],
            "workload": workload.name,
            "program_digest": workload.program.digest,
            "table_digest": table.digest,
            "dense_model_digest": dense.digest,
            "sparse_model_digest": sparse.digest,
            "operation_profile": sparse.operation_profile,
        },
    )
    observation = ObservationContract.from_definition(
        "mailcpu.finite-state-next-value",
        1,
        {
            "output_fields": list(table.output_names),
            "value_domain": [0, 1],
            "comparison": "canonical-json-exact",
            "input_domain": f"{{0,1}}^{len(table.input_names)}",
        },
    )
    bounds = (
        ResourceBound(
            "dense_parameters", dense.parameter_count, "scalar-parameter-slots"
        ),
        ResourceBound(
            "sparse_parameters",
            sparse.stored_parameter_count,
            "stored-nonzero-scalar-parameters",
        ),
    )
    return TranslationContract(
        contract_id=f"sparse-execution-{workload.name}-{route_name}",
        revision=1,
        source=source_ref,
        target=target_ref,
        mapping=mapping_ref,
        observation=observation,
        context_digest=canonical_value_digest(
            {
                "program_digest": workload.program.digest,
                "table_digest": table.digest,
                "route": route_name,
            }
        ),
        precondition_digests=(
            canonical_value_digest(
                {"input_domain": f"{{0,1}}^{len(table.input_names)}"}
            ),
        ),
        invariant_digests=(
            canonical_value_digest(
                {"output_domain": f"{{0,1}}^{len(table.output_names)}"}
            ),
        ),
        resource_bounds=bounds,
        effect_class=EffectClass.PURE,
        replay_class=ReplayClass.DETERMINISTIC,
    )


def _compile_dense_models(program: Any, table: Any) -> dict[str, Any]:
    return {
        "minterm": rcn.compile_transition_table(table),
        "direct_dag": rcn.compile_compositional_transition_program(program),
        "live_dag": rcn.compile_live_compositional_transition_program(program),
    }


def verify_workload(workload: Any) -> dict[str, Any]:
    program = workload.program
    table = program.to_table()
    rows = [tuple(row.inputs) for row in table.rows]
    dense_models = _compile_dense_models(program, table)
    expected_by_row: list[tuple[int, ...]] = []

    for values in rows:
        expected = workload.reference(values)
        if (
            program.evaluate(values) != expected
            or table.row_for(values).outputs != expected
        ):
            raise AssertionError(
                f"independent source descriptions disagree for {workload.name}/{values}"
            )
        expected_by_row.append(expected)

    expected_checksum = sum(sum(output) for output in expected_by_row)
    route_results: list[dict[str, Any]] = []
    all_case_evidence: list[dict[str, Any]] = []

    for route_name, dense in dense_models.items():
        sparse, conversion_metrics = _measure_conversion(dense)
        if sparse.source_model_digest != dense.digest:
            raise AssertionError("sparse model lost its exact dense source identity")
        if sparse.architecture != dense.architecture:
            raise AssertionError("sparse conversion changed the declared architecture")

        contract = _translation_contract(
            workload, table, route_name, dense, sparse
        )
        dense_bytes = _snapshot_size(dense.snapshot())
        sparse_bytes = _snapshot_size(sparse.snapshot())
        cases: list[dict[str, Any]] = []
        contract_digests: list[str] = []

        for row_index, (values, expected) in enumerate(
            zip(rows, expected_by_row)
        ):
            dense_output = dense.predict(values)
            sparse_output = sparse.predict(values)
            if dense_output != expected or sparse_output != expected:
                raise AssertionError(
                    {
                        "workload": workload.name,
                        "route": route_name,
                        "row": list(values),
                        "expected": list(expected),
                        "dense": list(dense_output),
                        "sparse": list(sparse_output),
                    }
                )
            comparison = compare_projected_observations(
                contract,
                case_payload={
                    "program_digest": program.digest,
                    "table_digest": table.digest,
                    "input_registers": dict(zip(table.input_names, values)),
                },
                source_observation=dict(zip(table.output_names, dense_output)),
                target_observation=dict(zip(table.output_names, sparse_output)),
            )
            if not comparison.equivalent:
                raise AssertionError(
                    f"dense/sparse translation failed for "
                    f"{workload.name}/{route_name}/{row_index}"
                )
            contract_digests.append(comparison.contract_digest)
            cases.append(
                {
                    "row_index": row_index,
                    "inputs": list(values),
                    "outputs": list(expected),
                    "dense_outputs": list(dense_output),
                    "sparse_outputs": list(sparse_output),
                    "translation_equivalent": True,
                    "translation_contract_digest": comparison.contract_digest,
                }
            )

        all_case_evidence.extend(cases)
        dense_timing = _measure_full_domain(
            dense, rows, expected_checksum=expected_checksum
        )
        sparse_timing = _measure_full_domain(
            sparse, rows, expected_checksum=expected_checksum
        )
        profile = sparse.operation_profile
        route_results.append(
            {
                "compiler": route_name,
                "compiler_id": COMPILERS[route_name],
                "architecture": list(dense.architecture),
                "source_program_digest": program.digest,
                "transition_table_digest": table.digest,
                "dense_model_digest": dense.digest,
                "sparse_model_digest": sparse.digest,
                "sparse_source_kind": sparse.source_kind,
                "sparse_source_digest": sparse.source_digest,
                "dense_parameter_count": dense.parameter_count,
                "dense_active_parameter_count": dense.active_parameter_count,
                "sparse_stored_parameter_count": sparse.stored_parameter_count,
                "sparse_stored_weight_count": sparse.stored_weight_count,
                "sparse_stored_bias_count": sparse.stored_bias_count,
                "parameter_reduction_fraction": (
                    1.0 - sparse.stored_parameter_count / dense.parameter_count
                    if dense.parameter_count else 0.0
                ),
                "dense_snapshot_bytes": dense_bytes,
                "sparse_snapshot_bytes": sparse_bytes,
                "snapshot_byte_reduction_fraction": (
                    1.0 - sparse_bytes / dense_bytes if dense_bytes else 0.0
                ),
                "dense_equivalent_parameter_count": (
                    sparse.dense_equivalent_parameter_count
                ),
                "operation_profile": profile,
                "conversion_timing": conversion_metrics,
                "dense_inference_timing": dense_timing,
                "sparse_inference_timing": sparse_timing,
                "sparse_over_dense_median_time_ratio": (
                    sparse_timing["median_ns"] / dense_timing["median_ns"]
                    if dense_timing["median_ns"] else None
                ),
                "translation_comparison_count": len(cases),
                "translation_contract_digest": _canonical_digest(contract_digests),
                "case_evidence_digest": _canonical_digest(cases),
            }
        )

    return {
        "name": workload.name,
        "family": workload.family,
        "description": workload.description,
        "input_width": len(program.input_names),
        "output_width": len(program.output_names),
        "complete_domain_rows": len(rows),
        "program_digest": program.digest,
        "table_digest": table.digest,
        "routes": route_results,
        "translation_comparison_count": sum(
            route["translation_comparison_count"] for route in route_results
        ),
        "case_evidence_digest": _canonical_digest(all_case_evidence),
        "all_dense_sparse_cases_verified": True,
    }


def run_experiment() -> dict[str, Any]:
    workloads = rcn.build_workloads()
    results = [verify_workload(workload) for workload in workloads]
    total_rows = sum(item["complete_domain_rows"] for item in results)
    all_routes = [
        route for workload in results for route in workload["routes"]
    ]
    payload = {
        "schema": "in-formation-space.sparse-transition-execution.sre001.v1",
        "experiment_id": "SRE-001",
        "status": "verified-within-complete-finite-domains",
        "source_revisions": {
            "ifs": os.environ.get("IFS_REVISION", "unspecified-local-checkout"),
            "ecpu": os.environ.get("ECPU_REVISION", "unspecified-local-checkout"),
            "vgi": os.environ.get("VGI_REVISION", "unspecified-local-checkout"),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "clock": {
                "implementation": time.get_clock_info("perf_counter").implementation,
                "monotonic": time.get_clock_info("perf_counter").monotonic,
                "resolution": time.get_clock_info("perf_counter").resolution,
            },
            "timing_repeats_per_full_domain": REPEATS,
            "timing_scope": (
                "local Python predict sweeps on the GitHub Actions host; includes input "
                "validation and Boolean output validation; excludes compilation and conversion"
            ),
        },
        "workload_count": len(results),
        "complete_input_rows_verified": total_rows,
        "dense_sparse_translation_comparisons": sum(
            item["translation_comparison_count"] for item in results
        ),
        "verified_workloads": sum(
            item["all_dense_sparse_cases_verified"] for item in results
        ),
        "aggregate_structural_counts": {
            "dense_parameter_slots": sum(
                route["dense_parameter_count"] for route in all_routes
            ),
            "dense_active_parameter_slots": sum(
                route["dense_active_parameter_count"] for route in all_routes
            ),
            "sparse_stored_parameter_slots": sum(
                route["sparse_stored_parameter_count"] for route in all_routes
            ),
            "dense_snapshot_bytes": sum(
                route["dense_snapshot_bytes"] for route in all_routes
            ),
            "sparse_snapshot_bytes": sum(
                route["sparse_snapshot_bytes"] for route in all_routes
            ),
            "dense_weight_multiply_slots": sum(
                route["operation_profile"]["dense_weight_multiply_count"]
                for route in all_routes
            ),
            "sparse_weight_multiply_slots": sum(
                route["operation_profile"]["sparse_weight_multiply_count"]
                for route in all_routes
            ),
            "dense_accumulator_addition_slots": sum(
                route["operation_profile"]["dense_accumulator_addition_count"]
                for route in all_routes
            ),
            "sparse_accumulator_addition_slots": sum(
                route["operation_profile"]["sparse_accumulator_addition_count"]
                for route in all_routes
            ),
        },
        "limitations": [
            "The corpus is the 16 selected RCN-001 workloads, not all Boolean transition programs.",
            "Sparse storage omits zero weights and zero biases but retains dense activation vectors.",
            "Snapshot byte counts measure canonical JSON payload size, not Python heap use or resident process memory.",
            "Timing is local Python predict latency on one identified CI host and is descriptive, not a hardware or production benchmark.",
            "Conversion timing is separate from inference timing and excludes dense compiler construction.",
            "No packed-bit, quantized, GPU, vectorized, distributed, or hardware-specific sparse kernel is implemented.",
            "Finite-domain equivalence does not establish arbitrary continuous-domain or all-floating-point equivalence.",
        ],
        "workloads": results,
    }
    payload["result_digest"] = _canonical_digest(payload)
    return payload


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_experiment()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "status": result["status"],
                "workloads": result["workload_count"],
                "input_rows": result["complete_input_rows_verified"],
                "comparisons": result["dense_sparse_translation_comparisons"],
                "result_digest": result["result_digest"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
