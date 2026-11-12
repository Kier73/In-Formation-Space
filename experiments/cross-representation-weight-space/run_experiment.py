"""Run the finite XOR→AND cross-representation weight-space experiment.

Requires the E-CPU and Virtual-Ground-Interpreter packages to be importable.
The runner fails closed on any mismatch and writes deterministic JSON evidence.
"""

from __future__ import annotations

import argparse
import json
from itertools import product
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
from mailcpu.weight_space import (
    ARCHITECTURE,
    DEEP_ARCHITECTURE,
    boolean_gate_program,
    compile_boolean_gate,
    decode_boolean_signal,
    edit_boolean_gate,
    evaluate_boolean_gate,
    encode_boolean_signal,
)
from vgi import (
    AddExpr,
    ConditionalExpr,
    EqualityGuard,
    InputExpr,
    OutputSpec,
    Signal8Backend,
    TaskSpec,
    VirtualGroundInterpreter,
)


def _vgi_task(gate: str) -> TaskSpec:
    a, b = InputExpr("input.a"), InputExpr("input.b")
    if gate == "xor":
        return TaskSpec(
            "boolean-xor",
            ("input.a", "input.b"),
            (OutputSpec("result", AddExpr(a, b)),),
        )
    zero, one = InputExpr("input.zero"), InputExpr("input.one")
    return TaskSpec(
        "boolean-and",
        ("input.a", "input.b", "input.zero", "input.one"),
        (
            OutputSpec(
                "result",
                ConditionalExpr(
                    EqualityGuard(a, one, 0.02),
                    ConditionalExpr(
                        EqualityGuard(b, one, 0.02),
                        one,
                        zero,
                    ),
                    zero,
                ),
            ),
        ),
    )


def _vgi_observation(gate: str, left: int, right: int) -> int:
    backend = Signal8Backend()
    memory = {
        "input.a": backend.encode_symbol(
            encode_boolean_signal(left),
            observer=1,
        ),
        "input.b": backend.encode_symbol(
            encode_boolean_signal(right),
            observer=3,
        ),
    }
    if gate == "and":
        memory["input.zero"] = backend.encode_symbol(0, observer=5)
        memory["input.one"] = backend.encode_symbol(4, observer=7)
    result = VirtualGroundInterpreter().interpret(_vgi_task(gate), memory)
    signal_symbol = result.observed_outputs(backend)["result"]
    return decode_boolean_signal(signal_symbol)


def _translation_contract(
    gate: str,
    program,
    model,
    left: int,
    right: int,
) -> TranslationContract:
    observation = ObservationContract.from_definition(
        "mailcpu.boolean-result",
        1,
        {
            "projection": "single-result-register",
            "field": "result",
            "domain": [0, 1],
            "comparison": "canonical-json-exact",
        },
    )
    mapping = RepresentationRef.from_payload(
        "mailcpu.boolean-weight-compiler",
        1,
        {
            "compiler": "mailcpu.weight_space.compile_boolean_gate",
            "gate": gate,
            "architecture": list(model.architecture),
            "activation": "relu-hidden-linear-output",
        },
    )
    return TranslationContract(
        contract_id=f"mailcpu.boolean-{gate}-program-to-weights",
        revision=1,
        source=program_representation_ref(program),
        target=RepresentationRef.from_payload(
            "mailcpu.relu-network",
            1,
            model.snapshot(),
        ),
        mapping=mapping,
        observation=observation,
        context_digest=canonical_value_digest(
            {"initial_registers": {"a": left, "b": right}}
        ),
        precondition_digests=(
            canonical_value_digest({"input_domain": "{0,1}^2"}),
        ),
        invariant_digests=(
            canonical_value_digest({"output_domain": "{0,1}"}),
        ),
        resource_bounds=(
            ResourceBound("parameters", model.parameter_count, "scalar-parameters"),
            ResourceBound("steps", 10, "instructions"),
        ),
        effect_class=EffectClass.PURE,
        replay_class=ReplayClass.DETERMINISTIC,
    )


def _run_case(gate: str, model, left: int, right: int) -> dict[str, Any]:
    program = boolean_gate_program(gate)
    initial = {"a": left, "b": right}
    reference = ReferenceInterpreter(program).run(initial_registers=initial)
    queued = QueueInterpreter(program).run(initial_registers=initial)
    expected = evaluate_boolean_gate(gate, left, right)
    neural = model.predict(left, right)
    signal = _vgi_observation(gate, left, right)

    if reference.status.value != "halted" or queued.status.value != "halted":
        raise AssertionError("MailCPU did not halt within its execution bound")
    reference_value = reference.state.registers["result"]
    queue_value = queued.state.registers["result"]
    if canonical_result(reference) != canonical_result(queued):
        raise AssertionError("MailCPU reference and queue traces differ")

    contract = _translation_contract(gate, program, model, left, right)
    comparison = compare_projected_observations(
        contract,
        case_payload={
            "program": program_representation_ref(program).to_dict(),
            "initial_registers": initial,
        },
        source_observation={"result": reference_value},
        target_observation={"result": neural},
    )

    observed = {
        "input": [left, right],
        "expected": expected,
        "vgi_signal8": signal,
        "mailcpu_reference": reference_value,
        "mailcpu_queue": queue_value,
        "neural_weights": neural,
        "translation_equivalent": comparison.equivalent,
        "translation_contract_digest": comparison.contract_digest,
    }
    if any(
        value != expected
        for value in (signal, reference_value, queue_value, neural)
    ) or not comparison.equivalent:
        raise AssertionError(f"cross-representation mismatch: {observed}")
    return observed


def run_experiment() -> dict[str, Any]:
    architecture_specs = (
        ("two-hidden-layer", ARCHITECTURE),
        ("three-hidden-layer", DEEP_ARCHITECTURE),
    )
    architecture_results: list[dict[str, Any]] = []
    all_cases: list[dict[str, Any]] = []

    for architecture_name, architecture in architecture_specs:
        model = compile_boolean_gate("xor", architecture=architecture)
        if model.parameter_count != 10_000:
            raise AssertionError(
                f"{architecture_name} declared {model.parameter_count} parameters"
            )
        initial_digest = model.digest
        xor_cases = [
            _run_case("xor", model, left, right)
            for left, right in product((0, 1), repeat=2)
        ]

        intervention = edit_boolean_gate(model, "and")
        if intervention.changed_parameters != 2:
            raise AssertionError("XOR-to-AND must change exactly two parameters")
        and_cases = [
            _run_case("and", model, left, right)
            for left, right in product((0, 1), repeat=2)
        ]

        final_layer = len(architecture) - 2
        coordinates = {
            (item.layer_index, item.output_index, item.input_index)
            for item in intervention.coordinates
        }
        if coordinates != {(final_layer, 0, 0), (final_layer, 0, 1)}:
            raise AssertionError("the intervention did not target the final two coefficients")

        architecture_results.append(
            {
                "name": architecture_name,
                "architecture": list(model.architecture),
                "parameter_count": model.parameter_count,
                "active_parameters": {
                    "xor": 9,
                    "and": model.active_parameter_count,
                },
                "initial_xor_model_digest": initial_digest,
                "final_and_model_digest": model.digest,
                "intervention": intervention.to_dict(),
            }
        )
        all_cases.extend(
            {"architecture": architecture_name, "gate": "xor", **case}
            for case in xor_cases
        )
        all_cases.extend(
            {"architecture": architecture_name, "gate": "and", **case}
            for case in and_cases
        )

    return {
        "schema": "in-formation-space.cross-representation-weight-space.v1",
        "status": "verified-within-declared-finite-domain",
        "domain": [[0, 0], [0, 1], [1, 0], [1, 1]],
        "architectures": architecture_results,
        "architecture_count": len(architecture_results),
        "parameter_count_per_architecture": 10_000,
        "case_count": len(all_cases),
        "cases": all_cases,
        "verification_scope": (
            "Exact equality on all four binary input pairs for XOR and AND, across two distinct "
            "10,000-parameter ReLU architectures, the VGI Signal8 realization, and the MailCPU "
            "reference and queue interpreters. Per-case semantic checks compare MailCPU "
            "reference outputs to neural outputs for each architecture."
        ),
        "limitations": [
            "Both neural architectures are hand-constructed for this finite Boolean example, not general neural synthesis.",
            "Each 10,000 parameter count includes zero-valued weights and biases.",
            "Both networks are sparse in active values despite their dense declared architectures.",
            "No training, generalization, robustness outside binary inputs, or hardware performance is tested.",
        ],
    }

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional JSON evidence output path")
    args = parser.parse_args()
    result = run_experiment()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
