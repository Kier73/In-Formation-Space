"""Benchmark finite Boolean compiler routes and navigate their structural costs."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from mailcpu.interpreter import QueueInterpreter, ReferenceInterpreter
from mailcpu.model import Instruction, Op, Program, canonical_result
from mailcpu.semantic_translation import (
    EffectClass,
    ObservationContract,
    ReplayClass,
    RepresentationRef,
    ResourceBound,
    TranslationContract,
    canonical_value_digest,
    compare_projected_observations,
    program_representation_ref,
)
from mailcpu.transition_space import (
    BooleanAnd,
    BooleanConstant,
    BooleanInput,
    BooleanNot,
    BooleanSelect,
    BooleanXor,
    FiniteTransitionProgram,
    apply_table_intervention,
    compile_compositional_transition_program,
    compile_live_compositional_transition_program,
    compile_transition_table,
)
from mailcpu.weight_space import decode_boolean_signal
from vgi import (
    ConditionalExpr,
    EqualityGuard,
    InputExpr,
    OutputSpec,
    Signal8Backend,
    TaskSpec,
    VirtualGroundInterpreter,
)

from navigator import navigate

COMPILERS = {
    "minterm": "mailcpu.transition_space.compile_transition_table",
    "direct_dag": "mailcpu.transition_space.compile_compositional_transition_program",
    "live_dag": "mailcpu.transition_space.compile_live_compositional_transition_program",
}
OBSERVERS = (1, 3, 5, 7)


@dataclass(frozen=True)
class Workload:
    name: str
    family: str
    program: FiniteTransitionProgram
    reference: Callable[[Sequence[int]], tuple[int, ...]]
    description: str


def _program(
    name: str,
    input_names: Sequence[str],
    output_names: Sequence[str],
    expressions: Sequence[Any],
) -> FiniteTransitionProgram:
    return FiniteTransitionProgram(
        name,
        tuple(input_names),
        tuple(output_names),
        tuple(expressions),
    )


def build_workloads() -> list[Workload]:
    """Build a varied, deterministic benchmark family with separate scalar oracles."""
    workloads: list[Workload] = []

    # Parity at increasing widths probes expression depth and repeated XOR structure.
    for width in (2, 4, 6, 8):
        names = tuple(f"x{index}" for index in range(width))
        expression: Any = BooleanInput(names[0])
        for name in names[1:]:
            expression = BooleanXor(expression, BooleanInput(name))
        program = _program(
            f"parity-{width}",
            names,
            ("parity",),
            (expression,),
        )
        workloads.append(
            Workload(
                program.name,
                "parity",
                program,
                lambda values: (sum(values) & 1,),
                f"XOR parity over {width} input bits",
            )
        )

    # Multiplexers expose a selector/data distinction absent from plain parity.
    for selector_width in (1, 2):
        selector_names = tuple(f"s{index}" for index in range(selector_width))
        data_names = tuple(f"d{index}" for index in range(2**selector_width))

        def mux_expression(level: int, start: int) -> Any:
            if level == 0:
                return BooleanInput(data_names[start])
            half = 2 ** (level - 1)
            return BooleanSelect(
                BooleanInput(selector_names[level - 1]),
                mux_expression(level - 1, start + half),
                mux_expression(level - 1, start),
            )

        expression = mux_expression(selector_width, 0)
        program = _program(
            f"multiplexer-{selector_width}-select-bits",
            selector_names + data_names,
            ("selected",),
            (expression,),
        )

        def mux_reference(values: Sequence[int], width: int = selector_width) -> tuple[int, ...]:
            selected_index = sum(int(values[index]) << index for index in range(width))
            return (int(values[width + selected_index]),)

        workloads.append(
            Workload(
                program.name,
                "multiplexer",
                program,
                mux_reference,
                f"{2**selector_width}-to-1 Boolean multiplexer",
            )
        )

    # Ripple adders use a propagate bit and a carry-select identity at each stage.
    for width in (1, 2, 3, 4):
        a_names = tuple(f"a{index}" for index in range(width))
        b_names = tuple(f"b{index}" for index in range(width))
        a = [BooleanInput(name) for name in a_names]
        b = [BooleanInput(name) for name in b_names]
        sums: list[Any] = []
        carry: Any | None = None
        for index in range(width):
            propagate = BooleanXor(a[index], b[index])
            if index == 0:
                sums.append(propagate)
                carry = BooleanAnd(a[index], b[index])
            else:
                sums.append(BooleanXor(propagate, carry))
                carry = BooleanSelect(propagate, carry, a[index])
        output_names = tuple(f"sum{index}" for index in range(width)) + ("carry",)
        program = _program(
            f"ripple-adder-{width}-bit",
            a_names + b_names,
            output_names,
            tuple(sums) + (carry,),
        )

        def adder_reference(values: Sequence[int], n: int = width) -> tuple[int, ...]:
            left = sum(int(values[index]) << index for index in range(n))
            right = sum(int(values[n + index]) << index for index in range(n))
            total = left + right
            return tuple((total >> index) & 1 for index in range(n + 1))

        workloads.append(
            Workload(
                program.name,
                "ripple-adder",
                program,
                adder_reference,
                f"Unsigned {width}-bit ripple-carry addition",
            )
        )

    # Lexicographic comparison extends the lower-bit relation only when a higher
    # bit is equal; the highest differing bit therefore determines the result.
    for width in (1, 2, 3, 4):
        a_names = tuple(f"a{index}" for index in range(width))
        b_names = tuple(f"b{index}" for index in range(width))
        a = [BooleanInput(name) for name in a_names]
        b = [BooleanInput(name) for name in b_names]
        less: Any = BooleanConstant(0)
        equal: Any = BooleanConstant(1)
        greater: Any = BooleanConstant(0)
        for index in range(width):
            equal_bit = BooleanNot(BooleanXor(a[index], b[index]))
            less = BooleanSelect(equal_bit, less, BooleanNot(a[index]))
            greater = BooleanSelect(equal_bit, greater, a[index])
            equal = BooleanAnd(equal, equal_bit)
        program = _program(
            f"unsigned-comparator-{width}-bit",
            a_names + b_names,
            ("less", "equal", "greater"),
            (less, equal, greater),
        )

        def comparator_reference(values: Sequence[int], n: int = width) -> tuple[int, ...]:
            left = sum(int(values[index]) << index for index in range(n))
            right = sum(int(values[n + index]) << index for index in range(n))
            return (int(left < right), int(left == right), int(left > right))

        workloads.append(
            Workload(
                program.name,
                "comparator",
                program,
                comparator_reference,
                f"Unsigned {width}-bit less/equal/greater comparison",
            )
        )

    # Highest-set-bit encoder with explicit validity for the all-zero input.
    priority_names = ("x0", "x1", "x2", "x3")
    x0, x1, x2, x3 = (BooleanInput(name) for name in priority_names)
    valid = BooleanSelect(x3, BooleanConstant(1), BooleanSelect(
        x2, BooleanConstant(1), BooleanSelect(x1, BooleanConstant(1), x0)
    ))
    index_high = BooleanSelect(
        x3,
        BooleanConstant(1),
        BooleanSelect(x2, BooleanConstant(1), BooleanConstant(0)),
    )
    index_low = BooleanSelect(
        x3,
        BooleanConstant(1),
        BooleanSelect(
            x2,
            BooleanConstant(0),
            BooleanSelect(x1, BooleanConstant(1), BooleanConstant(0)),
        ),
    )
    priority_program = _program(
        "priority-encoder-4",
        priority_names,
        ("valid", "index_high", "index_low"),
        (valid, index_high, index_low),
    )

    def priority_reference(values: Sequence[int]) -> tuple[int, ...]:
        asserted = [index for index, value in enumerate(values) if value]
        if not asserted:
            return (0, 0, 0)
        index = max(asserted)
        return (1, (index >> 1) & 1, index & 1)

    workloads.append(
        Workload(
            priority_program.name,
            "priority-encoder",
            priority_program,
            priority_reference,
            "Highest asserted input index plus a validity bit",
        )
    )

    # A control datapath makes the priority order observable across revisions.
    control_names = (
        "q1", "q0", "load", "shift", "reset", "data1", "data0", "serial_in"
    )
    q1, q0, load, shift, reset, data1, data0, serial_in = (
        BooleanInput(name) for name in control_names
    )
    next_q1 = BooleanSelect(
        reset,
        BooleanConstant(0),
        BooleanSelect(load, data1, BooleanSelect(shift, q0, q1)),
    )
    next_q0 = BooleanSelect(
        reset,
        BooleanConstant(0),
        BooleanSelect(load, data0, BooleanSelect(shift, serial_in, q0)),
    )
    control_program = _program(
        "state-control-reset-load-shift-hold",
        control_names,
        ("next_q1", "next_q0"),
        (next_q1, next_q0),
    )

    def control_reference(values: Sequence[int]) -> tuple[int, ...]:
        q1_value, q0_value, load_value, shift_value, reset_value, d1, d0, serial = (
            int(value) for value in values
        )
        if reset_value:
            return (0, 0)
        if load_value:
            return (d1, d0)
        if shift_value:
            return (q0_value, serial)
        return (q1_value, q0_value)

    workloads.append(
        Workload(
            control_program.name,
            "state-control",
            control_program,
            control_reference,
            "Reset > load > shift > hold priority over a two-bit register",
        )
    )
    return workloads


def _compile_decision_tree_program(table) -> Program:
    """Compile a complete table to a MailCPU binary decision tree.

    Each BRANCH tests one declared input bit. The zero subtree falls through;
    the one subtree is reached by an absolute branch target. Every leaf writes
    the table output and halts, so one input executes exactly one path of
    input-width branches plus one output block.
    """
    instructions: list[Instruction] = []

    def emit(depth: int, prefix: tuple[int, ...]) -> None:
        if depth == len(table.input_names):
            outputs = table.row_for(prefix).outputs
            for name, bit in zip(table.output_names, outputs):
                instructions.append(Instruction(Op.SET, (name, bit)))
            instructions.append(Instruction(Op.HALT))
            return

        input_name = table.input_names[depth]
        branch_position = len(instructions)
        instructions.append(Instruction(Op.BRANCH, (input_name, -1)))

        # A false input falls through to the zero child.
        emit(depth + 1, prefix + (0,))
        one_target = len(instructions)
        emit(depth + 1, prefix + (1,))

        instructions[branch_position] = Instruction(
            Op.BRANCH,
            (input_name, one_target),
        )

    emit(0, ())
    return Program(tuple(instructions))


def _decision_expression(table, output_index: int, depth: int = 0, prefix=()):
    if depth == len(table.input_names):
        row = table.row_for(prefix)
        return InputExpr("input.one" if row.outputs[output_index] else "input.zero")
    address = InputExpr(f"input.{table.input_names[depth]}")
    one = InputExpr("input.one")
    return ConditionalExpr(
        EqualityGuard(address, one, 0.02),
        _decision_expression(table, output_index, depth + 1, prefix + (1,)),
        _decision_expression(table, output_index, depth + 1, prefix + (0,)),
    )


def _vgi_observer(table):
    outputs = tuple(
        OutputSpec(name, _decision_expression(table, index))
        for index, name in enumerate(table.output_names)
    )
    addresses = tuple(f"input.{name}" for name in table.input_names)
    task = TaskSpec(table.name, addresses + ("input.zero", "input.one"), outputs)
    backend = Signal8Backend()
    interpreter = VirtualGroundInterpreter()
    compiled_program = interpreter.compile_task(task)

    def observe(inputs: tuple[int, ...]) -> tuple[int, ...]:
        memory = {
            f"input.{name}": backend.encode_symbol(
                4 * bit,
                observer=OBSERVERS[index % len(OBSERVERS)],
            )
            for index, (name, bit) in enumerate(zip(table.input_names, inputs))
        }
        memory["input.zero"] = backend.encode_symbol(0, observer=1)
        memory["input.one"] = backend.encode_symbol(4, observer=7)
        result = interpreter.execute(compiled_program, memory)
        observed = result.observed_outputs(backend)
        return tuple(decode_boolean_signal(observed[name]) for name in table.output_names)

    return observe


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def model_cost_metrics(name: str, model) -> dict[str, Any]:
    """Count storage and dense-forward work separately from nonzero sparsity."""
    architecture = tuple(model.architecture)
    dense_multiply_slots = sum(
        architecture[index] * architecture[index + 1]
        for index in range(len(architecture) - 1)
    )
    dense_bias_slots = sum(architecture[1:])
    nonzero_weight_slots = sum(
        value != 0.0
        for layer in model.weights
        for row in layer
        for value in row
    )
    nonzero_bias_slots = sum(
        value != 0.0
        for layer in model.biases
        for value in layer
    )
    dense_parameters = model.parameter_count
    active_parameters = model.active_parameter_count
    return {
        "compiler": name,
        "compiler_id": COMPILERS[name],
        "architecture": list(architecture),
        "depth": len(architecture) - 1,
        "hidden_relu_units": sum(architecture[1:-1]),
        "dense_parameter_count": dense_parameters,
        "active_parameter_count": active_parameters,
        "active_parameter_fraction": (
            active_parameters / dense_parameters if dense_parameters else 0.0
        ),
        "dense_multiply_slots": dense_multiply_slots,
        "dense_bias_slots": dense_bias_slots,
        "dense_forward_multiply_plus_add_slots": (
            2 * dense_multiply_slots + dense_bias_slots
        ),
        "nonzero_weight_slots": nonzero_weight_slots,
        "nonzero_bias_slots": nonzero_bias_slots,
        "nonzero_weight_fraction": (
            nonzero_weight_slots / dense_multiply_slots
            if dense_multiply_slots
            else 0.0
        ),
        "execution_note": (
            "Current model.forward traverses dense matrices, including zero coefficients. "
            "Nonzero counts describe sparsity potential, not measured sparse-runtime savings."
        ),
        "artifact_digest": model.digest,
    }


def _translation_context(table, executable, program, model_name, model, metrics):
    source_ref = program_representation_ref(executable)
    target_ref = RepresentationRef.from_payload(
        "mailcpu.finite-transition-relu-model",
        1,
        model.snapshot(),
    )
    mapping_ref = RepresentationRef.from_payload(
        "realization-cost-navigation.typed-program-to-relu",
        1,
        {
            "compiler": COMPILERS[model_name],
            "typed_program_digest": program.digest,
            "table_digest": table.digest,
            "architecture": list(model.architecture),
            "cost_metrics": metrics,
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
    resource_bounds = (
        ResourceBound("parameters", model.parameter_count, "scalar-parameters"),
        ResourceBound("instructions", len(executable.instructions), "instructions"),
    )
    return source_ref, target_ref, mapping_ref, observation, resource_bounds


def _verify_workload(workload: Workload) -> dict[str, Any]:
    program = workload.program
    table = program.to_table()
    models = {
        "minterm": compile_transition_table(table),
        "direct_dag": compile_compositional_transition_program(program),
        "live_dag": compile_live_compositional_transition_program(program),
    }
    executable = _compile_decision_tree_program(table)
    vgi_observe = _vgi_observer(table)
    metrics = {
        name: model_cost_metrics(name, model)
        for name, model in models.items()
    }
    route_contexts = {
        name: _translation_context(table, executable, program, name, model, metrics[name])
        for name, model in models.items()
    }

    rows: list[dict[str, Any]] = []
    observation_payload: list[dict[str, Any]] = []
    for row_index, row in enumerate(table.rows):
        inputs = tuple(row.inputs)
        expected = workload.reference(inputs)
        typed = program.evaluate(inputs)
        table_outputs = row.outputs
        if typed != expected or table_outputs != expected:
            raise AssertionError(
                {
                    "workload": workload.name,
                    "inputs": list(inputs),
                    "expected": list(expected),
                    "typed": list(typed),
                    "table": list(table_outputs),
                }
            )

        initial = dict(zip(table.input_names, inputs))
        reference = ReferenceInterpreter(executable).run(initial_registers=initial)
        queued = QueueInterpreter(executable).run(initial_registers=initial)
        if reference.status.value != "halted" or queued.status.value != "halted":
            raise AssertionError(f"MailCPU execution did not halt for {workload.name}")
        if canonical_result(reference) != canonical_result(queued):
            raise AssertionError(f"MailCPU execution backends diverged for {workload.name}")
        reference_outputs = tuple(
            reference.state.registers[name] for name in table.output_names
        )
        queue_outputs = tuple(
            queued.state.registers[name] for name in table.output_names
        )
        vgi_outputs = vgi_observe(inputs)
        if (
            reference_outputs != expected
            or queue_outputs != expected
            or vgi_outputs != expected
        ):
            raise AssertionError(
                {
                    "workload": workload.name,
                    "inputs": list(inputs),
                    "expected": list(expected),
                    "mailcpu_reference": list(reference_outputs),
                    "mailcpu_queue": list(queue_outputs),
                    "vgi": list(vgi_outputs),
                }
            )

        route_results: dict[str, Any] = {}
        for name, model in models.items():
            neural_outputs = model.predict(inputs)
            if neural_outputs != expected:
                raise AssertionError(
                    {
                        "workload": workload.name,
                        "compiler": name,
                        "inputs": list(inputs),
                        "expected": list(expected),
                        "neural": list(neural_outputs),
                    }
                )
            source_ref, target_ref, mapping_ref, observation, resource_bounds = route_contexts[name]
            contract = TranslationContract(
                contract_id=f"realization-cost-{workload.name}-{name}-{row_index}",
                revision=1,
                source=source_ref,
                target=target_ref,
                mapping=mapping_ref,
                observation=observation,
                context_digest=canonical_value_digest(
                    {
                        "program_digest": program.digest,
                        "table_digest": table.digest,
                        "inputs": initial,
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
                resource_bounds=resource_bounds,
                effect_class=EffectClass.PURE,
                replay_class=ReplayClass.DETERMINISTIC,
            )
            comparison = compare_projected_observations(
                contract,
                case_payload={
                    "program_digest": program.digest,
                    "table_digest": table.digest,
                    "input_registers": initial,
                },
                source_observation=dict(zip(table.output_names, reference_outputs)),
                target_observation=dict(zip(table.output_names, neural_outputs)),
            )
            if not comparison.equivalent:
                raise AssertionError(
                    f"semantic translation contract failed for {workload.name}/{name}/{row_index}"
                )
            route_results[name] = {
                "outputs": list(neural_outputs),
                "translation_equivalent": comparison.equivalent,
                "translation_contract_digest": comparison.contract_digest,
            }

        rows.append(
            {
                "row_index": row_index,
                "inputs": list(inputs),
                "outputs": list(expected),
                "mailcpu_reference_outputs": list(reference_outputs),
                "mailcpu_queue_outputs": list(queue_outputs),
                "vgi_outputs": list(vgi_outputs),
                "neural_routes": route_results,
            }
        )
        observation_payload.append(
            {"inputs": list(inputs), "outputs": list(expected)}
        )

    observation_digest = _canonical_digest(observation_payload)
    route_digests = {
        name: _canonical_digest(
            [
                {
                    "inputs": list(row.inputs),
                    "outputs": list(model.predict(row.inputs)),
                }
                for row in table.rows
            ]
        )
        for name, model in models.items()
    }
    if any(value != observation_digest for value in route_digests.values()):
        raise AssertionError(f"neural routes disagree on {workload.name}")

    navigation = {
        "pareto": navigate(list(metrics.values()), objective="pareto"),
        "storage_first": navigate(list(metrics.values()), objective="storage"),
        "dense_compute_first": navigate(
            list(metrics.values()),
            objective="dense_compute",
        ),
    }
    return {
        "name": workload.name,
        "family": workload.family,
        "description": workload.description,
        "input_names": list(program.input_names),
        "output_names": list(program.output_names),
        "input_width": len(program.input_names),
        "output_width": len(program.output_names),
        "complete_domain_rows": table.row_count,
        "typed_program_digest": program.digest,
        "transition_table_digest": table.digest,
        "mailcpu_reference_compiler": "experiment.binary-input-decision-tree",
        "mailcpu_reference_instruction_count": len(executable.instructions),
        "independent_observation_digest": observation_digest,
        "route_observation_digests": route_digests,
        "models": list(metrics.values()),
        "navigation": navigation,
        "verified_case_count": len(rows),
        "semantic_translation_comparison_count": len(rows) * len(models),
        "all_cross_representation_cases_verified": True,
        "case_evidence_digest": _canonical_digest(rows),
        "cases": rows,
    }


def run_experiment() -> dict[str, Any]:
    workloads = build_workloads()
    results = [_verify_workload(workload) for workload in workloads]
    total_rows = sum(item["verified_case_count"] for item in results)
    total_comparisons = sum(
        item["semantic_translation_comparison_count"] for item in results
    )
    payload = {
        "schema": "in-formation-space.realization-cost-navigation.v1",
        "experiment_id": "RCN-001",
        "status": "verified-within-complete-finite-domains",
        "source_revisions": {
            "ecpu": os.environ.get("ECPU_REVISION", "unspecified-local-checkout"),
            "vgi": os.environ.get("VGI_REVISION", "unspecified-local-checkout"),
            "ifs": os.environ.get("IFS_REVISION", "unspecified-local-checkout"),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "runtime_timing_measured": False,
        },
        "workload_families": [
            "parity",
            "multiplexer",
            "ripple-adder",
            "comparator",
            "priority-encoder",
            "state-control",
        ],
        "compiler_routes": list(COMPILERS),
        "workload_count": len(results),
        "complete_input_rows_verified": total_rows,
        "semantic_translation_comparisons": total_comparisons,
        "verified_workloads": sum(
            item["all_cross_representation_cases_verified"] for item in results
        ),
        "cost_model": {
            "dimensions": [
                "dense_parameter_count",
                "dense_multiply_slots",
                "hidden_relu_units",
                "depth",
            ],
            "dense_forward_multiply_plus_add_slots": (
                "2 * dense_multiply_slots + dense_bias_slots"
            ),
            "active_parameters": (
                "reported as sparsity diagnostics only; not treated as execution savings "
                "because the current forward path traverses dense matrices"
            ),
            "navigation": (
                "hard resource caps followed by Pareto filtering or an explicit single-axis "
                "storage / dense-compute preference; no weighted aggregate score"
            ),
            "timing": "No wall-clock compilation or inference benchmark is claimed.",
        },
        "limitations": [
            "All compiler and cross-runtime checks are exhaustive only on each workload's declared Boolean input domain.",
            "The benchmark suite tests selected hand-declared workload families, not all Boolean functions or arbitrary programs.",
            "The dense multiply and bias-add counts are structural operation counts derived from architecture shapes, not measured CPU/GPU latency.",
            "Nonzero coefficients do not reduce current dense forward work; a sparse tensor format and sparse kernel would need separate implementation and measurement.",
            "No continuous-input behavior, training/generalization, LLM weight interpretation, distributed realization, quantization, or hardware advantage is claimed.",
            "Pareto navigation exposes choices under stated dimensions; it does not establish one universally best compiler.",
        ],
        "workloads": results,
    }
    payload["result_digest"] = _canonical_digest(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional deterministic JSON evidence path")
    args = parser.parse_args()
    result = run_experiment()
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "status": result["status"],
                "workloads": result["workload_count"],
                "input_rows": result["complete_input_rows_verified"],
                "semantic_comparisons": result["semantic_translation_comparisons"],
                "result_digest": result["result_digest"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
