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
    compile_compositional_transition_program,
    compile_live_compositional_transition_program,
    compile_transition_program,
    compile_transition_table,
    two_bit_counter_program,
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


def _make_vgi_observer(table: FiniteTransitionTable):
    """Create a reusable VGI interpreter closure for repeated transition steps."""
    backend = Signal8Backend()
    interpreter = VirtualGroundInterpreter()
    task = _vgi_task(table)
    observer_coordinates = (1, 3, 5, 7)

    def observe(inputs: tuple[int, ...]) -> tuple[int, ...]:
        """Evaluate one transition using the prebuilt VGI task and Signal8 Ground."""
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
        result = interpreter.interpret(task, memory)
        observed = result.observed_outputs(backend)
        return tuple(
            decode_boolean_signal(observed[name])
            for name in table.output_names
        )

    return observe


def _verify_recurrent_rollouts(
    table: FiniteTransitionTable,
    model,
    program,
    *,
    model_name: str,
    typed_program_digest: str,
    compiler_id: str,
    horizon: int = 3,
) -> dict[str, Any]:
    """Exhaust every short control trajectory while each representation feeds back its own state."""
    if horizon < 1:
        raise ValueError("rollout horizon must be positive")
    control_pairs = tuple(itertools.product((0, 1), repeat=2))
    control_sequences = tuple(itertools.product(control_pairs, repeat=horizon))
    reference = ReferenceInterpreter(program)
    queued = QueueInterpreter(program)
    vgi_observe = _make_vgi_observer(table)
    trajectory_records: list[dict[str, Any]] = []

    systems = ("oracle", "neural", "vgi", "mailcpu_reference", "mailcpu_queue")
    for initial_state in range(4):
        initial_bits = ((initial_state >> 1) & 1, initial_state & 1)
        for controls in control_sequences:
            states = {name: initial_bits for name in systems}
            observed_outputs: list[list[int]] = []

            for advance, reset in controls:
                oracle_state = states["oracle"]
                inputs = (
                    oracle_state[0],
                    oracle_state[1],
                    advance,
                    reset,
                )
                expected = table.row_for(inputs).outputs

                reference_result = reference.run(
                    initial_registers=dict(zip(table.input_names, inputs))
                )
                queue_result = queued.run(
                    initial_registers=dict(zip(table.input_names, inputs))
                )
                if (
                    reference_result.status.value != "halted"
                    or queue_result.status.value != "halted"
                ):
                    raise AssertionError("MailCPU rollout transition did not halt")
                if canonical_result(reference_result) != canonical_result(queue_result):
                    raise AssertionError("MailCPU rollout traces diverged")

                neural_outputs = model.predict(inputs)
                vgi_outputs = vgi_observe(inputs)
                reference_outputs = tuple(
                    reference_result.state.registers[name]
                    for name in table.output_names
                )
                queue_outputs = tuple(
                    queue_result.state.registers[name]
                    for name in table.output_names
                )
                observed = {
                    "neural": neural_outputs,
                    "vgi": vgi_outputs,
                    "mailcpu_reference": reference_outputs,
                    "mailcpu_queue": queue_outputs,
                }
                if any(value != expected for value in observed.values()):
                    raise AssertionError(
                        {
                            "model": model_name,
                            "initial_state": initial_state,
                            "controls": controls,
                            "input": inputs,
                            "expected": expected,
                            "observed": observed,
                        }
                    )

                states["oracle"] = expected
                states["neural"] = neural_outputs
                states["vgi"] = vgi_outputs
                states["mailcpu_reference"] = reference_outputs
                states["mailcpu_queue"] = queue_outputs
                if any(states[name] != states["oracle"] for name in systems):
                    raise AssertionError("a recurrent state diverged after a transition")
                observed_outputs.append(list(expected))

            trajectory_records.append(
                {
                    "initial_state": list(initial_bits),
                    "controls": [list(pair) for pair in controls],
                    "outputs": observed_outputs,
                    "final_state": list(states["oracle"]),
                }
            )

    return {
        "model_name": model_name,
        "compiler_id": compiler_id,
        "typed_program_digest": typed_program_digest,
        "table_digest": table.digest,
        "model_digest": model.digest,
        "horizon": horizon,
        "initial_state_count": 4,
        "control_pair_count": len(control_pairs),
        "control_sequence_count": len(control_sequences),
        "trajectory_count": len(trajectory_records),
        "transition_step_count": len(trajectory_records) * horizon,
        "systems": list(systems),
        "all_trajectories_match": True,
        "trajectory_digest": canonical_value_digest(trajectory_records),
    }


def _translation_contract(
    table: FiniteTransitionTable,
    program,
    model,
    inputs: tuple[int, ...],
    *,
    phase: str,
    architecture_name: str,
    row_index: int,
    typed_program_digest: str,
    compiler_id: str = "mailcpu.transition_space.compile_transition_table",
) -> TranslationContract:
    """Bind one reference-program/model comparison to its typed source and exact case."""
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
            "compiler": compiler_id,
            "derived_table_digest": table.digest,
            "architecture": list(model.architecture),
            "architecture_name": architecture_name,
            "typed_transition_program_digest": typed_program_digest,
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
            {
                "table_digest": table.digest,
                "typed_transition_program_digest": typed_program_digest,
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
    typed_program_digest: str,
    compiler_id: str = "mailcpu.transition_space.compile_transition_table",
) -> dict[str, Any]:
    """Compare one case across typed source, table, MailCPU, VGI, and neural weights."""
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
        typed_program_digest=typed_program_digest,
        compiler_id=compiler_id,
    )
    comparison = compare_projected_observations(
        contract,
        case_payload={
            "table_digest": table.digest,
            "typed_transition_program_digest": typed_program_digest,
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
        "typed_transition_program_digest": typed_program_digest,
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
    """Derive two finite tables from typed transition programs and exhaust both."""
    source_specification = two_bit_counter_program()
    target_specification = source_specification.with_row_output(
        EDITED_INPUTS,
        EDITED_OUTPUTS,
        name="two-bit-counter.reset-exception.v1",
    )
    source_table = source_specification.to_table()
    target_table = target_specification.to_table()
    expected_target = source_table.with_output(
        EDITED_INPUTS,
        EDITED_OUTPUTS,
        name=target_specification.name,
    )
    if target_table != expected_target:
        raise AssertionError("typed row override and table row override disagree")

    architecture_results: list[dict[str, Any]] = []
    all_cases: list[dict[str, Any]] = []
    rollout_results: list[dict[str, Any]] = []

    for architecture_name, architecture in ARCHITECTURES:
        model = compile_transition_table(
            source_table,
            architecture=architecture,
        )
        source_model_digest = model.digest
        source_active_parameters = model.active_parameter_count
        source_program = compile_transition_program(source_table)
        rollout_results.append(
            _verify_recurrent_rollouts(
                source_table,
                model,
                source_program,
                model_name=f"minterm:{architecture_name}:baseline",
                typed_program_digest=source_specification.digest,
                compiler_id="mailcpu.transition_space.compile_transition_table",
            )
        )

        source_cases = [
            _run_case(
                source_table,
                model,
                source_program,
                row.inputs,
                phase="baseline",
                architecture_name=architecture_name,
                row_index=row_index,
                typed_program_digest=source_specification.digest,
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
        rollout_results.append(
            _verify_recurrent_rollouts(
                target_table,
                model,
                target_program,
                model_name=f"minterm:{architecture_name}:one-row-override",
                typed_program_digest=target_specification.digest,
                compiler_id="mailcpu.transition_space.compile_transition_table",
            )
        )
        target_cases = [
            _run_case(
                target_table,
                model,
                target_program,
                row.inputs,
                phase="single-row-intervention",
                architecture_name=architecture_name,
                row_index=row_index,
                typed_program_digest=target_specification.digest,
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

    compositional_source_model = compile_compositional_transition_program(
        source_specification
    )
    compositional_target_model = compile_compositional_transition_program(
        target_specification
    )
    compositional_source_program = compile_transition_program(source_table)
    compositional_target_program = compile_transition_program(target_table)
    rollout_results.extend(
        [
            _verify_recurrent_rollouts(
                source_table,
                compositional_source_model,
                compositional_source_program,
                model_name="direct-dag:baseline",
                typed_program_digest=source_specification.digest,
                compiler_id="mailcpu.transition_space.compile_compositional_transition_program",
            ),
            _verify_recurrent_rollouts(
                target_table,
                compositional_target_model,
                compositional_target_program,
                model_name="direct-dag:one-row-override",
                typed_program_digest=target_specification.digest,
                compiler_id="mailcpu.transition_space.compile_compositional_transition_program",
            ),
        ]
    )
    compositional_source_cases = [
        _run_case(
            source_table,
            compositional_source_model,
            compositional_source_program,
            row.inputs,
            phase="compositional-baseline",
            architecture_name="compositional-source",
            row_index=row_index,
            typed_program_digest=source_specification.digest,
            compiler_id="mailcpu.transition_space.compile_compositional_transition_program",
        )
        for row_index, row in enumerate(source_table.rows)
    ]
    compositional_target_cases = [
        _run_case(
            target_table,
            compositional_target_model,
            compositional_target_program,
            row.inputs,
            phase="compositional-row-override",
            architecture_name="compositional-override",
            row_index=row_index,
            typed_program_digest=target_specification.digest,
            compiler_id="mailcpu.transition_space.compile_compositional_transition_program",
        )
        for row_index, row in enumerate(target_table.rows)
    ]
    live_source_model = compile_live_compositional_transition_program(
        source_specification
    )
    live_target_model = compile_live_compositional_transition_program(
        target_specification
    )
    rollout_results.extend(
        [
            _verify_recurrent_rollouts(
                source_table,
                live_source_model,
                compositional_source_program,
                model_name="live-dag:baseline",
                typed_program_digest=source_specification.digest,
                compiler_id="mailcpu.transition_space.compile_live_compositional_transition_program",
            ),
            _verify_recurrent_rollouts(
                target_table,
                live_target_model,
                compositional_target_program,
                model_name="live-dag:one-row-override",
                typed_program_digest=target_specification.digest,
                compiler_id="mailcpu.transition_space.compile_live_compositional_transition_program",
            ),
        ]
    )
    live_source_cases = [
        _run_case(
            source_table,
            live_source_model,
            compositional_source_program,
            row.inputs,
            phase="live-compositional-baseline",
            architecture_name="live-compositional-source",
            row_index=row_index,
            typed_program_digest=source_specification.digest,
            compiler_id="mailcpu.transition_space.compile_live_compositional_transition_program",
        )
        for row_index, row in enumerate(source_table.rows)
    ]
    live_target_cases = [
        _run_case(
            target_table,
            live_target_model,
            compositional_target_program,
            row.inputs,
            phase="live-compositional-row-override",
            architecture_name="live-compositional-override",
            row_index=row_index,
            typed_program_digest=target_specification.digest,
            compiler_id="mailcpu.transition_space.compile_live_compositional_transition_program",
        )
        for row_index, row in enumerate(target_table.rows)
    ]

    compositional_models = [
        {
            "name": "compositional-source",
            "program_digest": source_specification.digest,
            "table_digest": source_table.digest,
            "model_digest": compositional_source_model.digest,
            "architecture": list(compositional_source_model.architecture),
            "parameter_count": compositional_source_model.parameter_count,
            "active_parameter_count": compositional_source_model.active_parameter_count,
        },
        {
            "name": "compositional-override",
            "program_digest": target_specification.digest,
            "table_digest": target_table.digest,
            "model_digest": compositional_target_model.digest,
            "architecture": list(compositional_target_model.architecture),
            "parameter_count": compositional_target_model.parameter_count,
            "active_parameter_count": compositional_target_model.active_parameter_count,
        },
        {
            "name": "live-compositional-source",
            "program_digest": source_specification.digest,
            "table_digest": source_table.digest,
            "model_digest": live_source_model.digest,
            "architecture": list(live_source_model.architecture),
            "parameter_count": live_source_model.parameter_count,
            "active_parameter_count": live_source_model.active_parameter_count,
        },
        {
            "name": "live-compositional-override",
            "program_digest": target_specification.digest,
            "table_digest": target_table.digest,
            "model_digest": live_target_model.digest,
            "architecture": list(live_target_model.architecture),
            "parameter_count": live_target_model.parameter_count,
            "active_parameter_count": live_target_model.active_parameter_count,
        },
    ]
    all_cases.extend(compositional_source_cases)
    all_cases.extend(compositional_target_cases)
    all_cases.extend(live_source_cases)
    all_cases.extend(live_target_cases)

    return {
        "schema": "in-formation-space.finite-state-transition-neural-synthesis.v5",
        "status": "verified-within-complete-finite-domain",
        "typed_transition_program": source_specification.to_dict(),
        "typed_transition_program_digest": source_specification.digest,
        "edited_typed_transition_program": target_specification.to_dict(),
        "edited_typed_transition_program_digest": target_specification.digest,
        "compiler_path": (
            "typed Boolean transition program -> enumerated finite table -> "
            "ReLU minterm network and MailCPU reference program"
        ),
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
        "compositional_model_count": len(compositional_models),
        "compositional_models": compositional_models,
        "neural_compiler_count": 3,
        "neural_compilers": [
            "truth-table-minterm",
            "direct-expression-dag",
            "live-feature-expression-dag",
        ],
        "transition_rows": source_table.row_count,
        "phase_count": 2,
        "case_count": len(all_cases),
        "architectures": architecture_results,
        "cases": all_cases,
        "recurrent_rollout_verification": {
            "horizon": 3,
            "model_phase_count": len(rollout_results),
            "trajectory_count": sum(item["trajectory_count"] for item in rollout_results),
            "transition_step_count": sum(item["transition_step_count"] for item in rollout_results),
            "all_trajectories_match": all(
                item["all_trajectories_match"] for item in rollout_results
            ),
            "per_model": rollout_results,
        },
        "verification_scope": (
            "All 16 inputs of the complete four-bit Boolean transition domain, "
            "for the baseline typed transition program and a compositional one-row "
            "override, across two truth-table minterm architectures and two direct "
            "Boolean-DAG architectures, VGI Signal8, MailCPU reference and queue "
            "interpreters, and per-case semantic comparisons."
        ),
        "limitations": [
            "The truth-table compiler allocates one hidden minterm per input row; width grows exponentially with input-bit count.",
            "The result is exact on the declared finite Boolean domain, not a learned or generalizing model.",
            "The one-row typed override changes one selected output coefficient in each minterm architecture; both DAG compilers independently recompile the edited typed expression.",
            "No noise tolerance, quantization, training, arbitrary real-valued input behavior, or hardware speed is tested.",
            "Recurrent verification covers all three-step Boolean control sequences, not unbounded trajectories."

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
