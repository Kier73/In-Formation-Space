"""Verify a finite-state transition table across VGI, MailCPU, and ReLU models."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

from mailcpu.interpreter import QueueInterpreter, ReferenceInterpreter
from mailcpu.model import canonical_result
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
    FiniteTransitionTable,
    apply_table_intervention,
    compile_transition_program,
    compile_transition_table,
    two_bit_counter_table,
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

ARCHITECTURES = (
    ("one-hidden-layer", (4, 16, 2)),
    ("two-hidden-layer", (4, 16, 16, 2)),
)
EDITED_INPUTS = (0, 1, 1, 1)
EDITED_OUTPUTS = (1, 0)


def _decision_expression(
    table: FiniteTransitionTable,
    output_index: int,
    depth: int = 0,
    prefix: tuple[int, ...] = (),
):
    """Lower one output column to nested VGI equality/conditional expressions."""
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


def _vgi_task(table: FiniteTransitionTable) -> TaskSpec:
    """Build the finite transition decision tree using existing VGI task nodes."""
    outputs = tuple(
        OutputSpec(
            name,
            _decision_expression(table, output_index),
        )
        for output_index, name in enumerate(table.output_names)
    )
    input_addresses = tuple(f"input.{name}" for name in table.input_names)
    return TaskSpec(
        table.name,
        input_addresses + ("input.zero", "input.one"),
        outputs,
    )


def _vgi_observe(table: FiniteTransitionTable, inputs: tuple[int, ...]) -> tuple[int, ...]:
    """Run one transition through Signal8 with distinct observer coordinates."""
    backend = Signal8Backend()
    observer_coordinates = (1, 3, 5, 7)
    memory = {
        f"input.{name}": backend.encode_symbol(
            4 * bit,
            observer=observer,
        )
        for name, bit, observer in zip(
            table.input_names,
            inputs,
            observer_coordinates,
        )
    }
    memory["input.zero"] = backend.encode_symbol(0, observer=1)
    memory["input.one"] = backend.encode_symbol(4, observer=7)
    result = VirtualGroundInterpreter().interpret(_vgi_task(table), memory)
    observed = result.observed_outputs(backend)
    return tuple(
        decode_boolean_signal(observed[name])
        for name in table.output_names
    )


def _translation_contract(
    table: FiniteTransitionTable,
    program,
    model,
    inputs: tuple[int, ...],
    *,
    phase: str,
    architecture_name: str,
    row_index: int,
) -> TranslationContract:
    """Bind one reference-program/model comparison to the exact case and table."""
    program_ref = program_representation_ref(program)
    observation = ObservationContract.from_definition(
        "mailcpu.finite-state-next-value",
        1,
        {
            "output_fields": list(table.output_names),
            "value_domain": [0, 1],
            "comparison": "canonical-json-exact",
        },
    )
    mapping = RepresentationRef.from_payload(
        "mailcpu.finite-transition-table-to-relu",
        1,
        {
            "compiler": "mailcpu.transition_space.compile_transition_table",
            "table_digest": table.digest,
            "architecture": list(model.architecture),
            "architecture_name": architecture_name,
            "minterm_count": table.row_count,
        },
    )
    initial = dict(zip(table.input_names, inputs))
    return TranslationContract(
        contract_id=f"finite-transition-{phase}-{architecture_name}-{row_index}",
        revision=1,
        source=program_ref,
        target=RepresentationRef.from_payload(
            "mailcpu.finite-transition-relu-model",
            1,
            model.snapshot(),
        ),
        mapping=mapping,
        observation=observation,
        context_digest=canonical_value_digest(
            {"table_digest": table.digest, "inputs": initial}
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
        resource_bounds=(
            ResourceBound("parameters", model.parameter_count, "scalar-parameters"),
            ResourceBound("instructions", len(program.instructions), "instructions"),
        ),
        effect_class=EffectClass.PURE,
        replay_class=ReplayClass.DETERMINISTIC,
    )


def _run_case(
    table: FiniteTransitionTable,
    model,
    program,
    inputs: tuple[int, ...],
    *,
    phase: str,
    architecture_name: str,
    row_index: int,
) -> dict[str, Any]:
    """Compare one case across the truth table, two MailCPU backends, VGI, and weights."""
    initial = dict(zip(table.input_names, inputs))
    reference = ReferenceInterpreter(program).run(initial_registers=initial)
    queued = QueueInterpreter(program).run(initial_registers=initial)
    if reference.status.value != "halted" or queued.status.value != "halted":
        raise AssertionError("MailCPU transition program did not halt")
    if canonical_result(reference) != canonical_result(queued):
        raise AssertionError("MailCPU reference and queue traces differ")

    expected = table.row_for(inputs).outputs
    reference_outputs = tuple(
        reference.state.registers[name] for name in table.output_names
    )
    queue_outputs = tuple(
        queued.state.registers[name] for name in table.output_names
    )
    vgi_outputs = _vgi_observe(table, inputs)
    neural_outputs = model.predict(inputs)
    if any(
        values != expected
        for values in (reference_outputs, queue_outputs, vgi_outputs, neural_outputs)
    ):
        raise AssertionError(
            {
                "phase": phase,
                "architecture": architecture_name,
                "inputs": inputs,
                "expected": expected,
                "reference": reference_outputs,
                "queue": queue_outputs,
                "vgi": vgi_outputs,
                "neural": neural_outputs,
            }
        )

    contract = _translation_contract(
        table,
        program,
        model,
        inputs,
        phase=phase,
        architecture_name=architecture_name,
        row_index=row_index,
    )
    comparison = compare_projected_observations(
        contract,
        case_payload={
            "table_digest": table.digest,
            "input_registers": initial,
        },
        source_observation=dict(zip(table.output_names, reference_outputs)),
        target_observation=dict(zip(table.output_names, neural_outputs)),
    )
    if not comparison.equivalent:
        raise AssertionError("semantic translation comparison failed")

    return {
        "phase": phase,
        "architecture": architecture_name,
        "row_index": row_index,
        "inputs": list(inputs),
        "expected_outputs": list(expected),
        "vgi_outputs": list(vgi_outputs),
        "mailcpu_reference_outputs": list(reference_outputs),
        "mailcpu_queue_outputs": list(queue_outputs),
        "neural_outputs": list(neural_outputs),
        "translation_equivalent": comparison.equivalent,
        "translation_contract_digest": comparison.contract_digest,
    }


def run_experiment() -> dict[str, Any]:
    """Exhaust both 16-row transition tables through two neural architectures."""
    source_table = two_bit_counter_table()
    target_table = source_table.with_output(
        EDITED_INPUTS,
        EDITED_OUTPUTS,
        name="two-bit-counter.reset-exception.v1",
    )
    architecture_results: list[dict[str, Any]] = []
    all_cases: list[dict[str, Any]] = []

    for architecture_name, architecture in ARCHITECTURES:
        model = compile_transition_table(
            source_table,
            architecture=architecture,
        )
        source_model_digest = model.digest
        source_active_parameters = model.active_parameter_count
        source_program = compile_transition_program(source_table)

        source_cases = [
            _run_case(
                source_table,
                model,
                source_program,
                row.inputs,
                phase="baseline",
                architecture_name=architecture_name,
                row_index=row_index,
            )
            for row_index, row in enumerate(source_table.rows)
        ]

        intervention = apply_table_intervention(
            model,
            source_table,
            target_table,
        )
        if intervention.changed_parameters != 1:
            raise AssertionError("the selected transition edit must change exactly one weight")
        target_program = compile_transition_program(target_table)
        target_cases = [
            _run_case(
                target_table,
                model,
                target_program,
                row.inputs,
                phase="single-row-intervention",
                architecture_name=architecture_name,
                row_index=row_index,
            )
            for row_index, row in enumerate(target_table.rows)
        ]

        for row in source_table.rows:
            expected = (
                target_table.row_for(row.inputs).outputs
                if row.inputs == EDITED_INPUTS
                else row.outputs
            )
            if model.predict(row.inputs) != expected:
                raise AssertionError("intervention altered more than its declared transition")

        architecture_results.append(
            {
                "name": architecture_name,
                "architecture": list(model.architecture),
                "parameter_count": model.parameter_count,
                "active_parameters_before": source_active_parameters,
                "active_parameters_after": model.active_parameter_count,
                "source_table_digest": source_table.digest,
                "target_table_digest": target_table.digest,
                "source_model_digest": source_model_digest,
                "target_model_digest": model.digest,
                "intervention": intervention.to_dict(),
                "mailcpu_program_instructions": {
                    "baseline": len(source_program.instructions),
                    "intervened": len(target_program.instructions),
                },
            }
        )
        all_cases.extend(source_cases)
        all_cases.extend(target_cases)

    return {
        "schema": "in-formation-space.finite-state-transition-neural-synthesis.v1",
        "status": "verified-within-complete-finite-domain",
        "transition_table": source_table.to_dict(),
        "intervention": {
            "inputs": list(EDITED_INPUTS),
            "source_outputs": list(source_table.row_for(EDITED_INPUTS).outputs),
            "target_outputs": list(EDITED_OUTPUTS),
            "meaning": (
                "For state 01 with advance=1 and reset=1, use the increment "
                "transition 10 instead of the baseline reset transition 00."
            ),
        },
        "architecture_count": len(architecture_results),
        "transition_rows": source_table.row_count,
        "phase_count": 2,
        "case_count": len(all_cases),
        "architectures": architecture_results,
        "cases": all_cases,
        "verification_scope": (
            "All 16 inputs of the complete four-bit Boolean transition domain, "
            "for the baseline table and a one-row edited table, across two exact "
            "ReLU architectures, VGI Signal8, MailCPU reference and queue interpreters, "
            "and per-case semantic translation comparisons."
        ),
        "limitations": [
            "The truth-table compiler allocates one hidden minterm per input row; width grows exponentially with input-bit count.",
            "The result is exact on the declared finite Boolean domain, not a learned or generalizing model.",
            "The intervention changes one selected output coefficient because the target table differs in one output bit on one row.",
            "No noise tolerance, quantization, training, arbitrary real-valued input behavior, or hardware speed is tested.",
        ],
    }


def main() -> None:
    """Run the experiment, fail on any mismatch, and write optional JSON evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional path for deterministic JSON evidence")
    args = parser.parse_args()
    result = run_experiment()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
