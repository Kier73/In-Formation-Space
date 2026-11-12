"""WSP-002: compile, revise, and compare equivalent weight-space realizations."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

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
from mailcpu.stateful_transition import StatefulTransitionError, StatefulTransitionRuntime
from mailcpu.transition_space import (
    BooleanInput,
    BooleanNot,
    BooleanXor,
    CompositionalTransitionReLUNetwork,
    FiniteTransitionProgram,
    TransitionReLUNetwork,
    apply_table_intervention,
    compile_compositional_transition_program,
    compile_live_compositional_transition_program,
    compile_transition_program,
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

SEED = 20261112
LOCAL_INPUTS = (1, 0, 1, 0)
LOCAL_OUTPUTS = (0, 1, 1)
STATE_INPUT_NAMES = ("q2", "q1", "q0")
INPUT_NAMES = ("q2", "q1", "q0", "d")
OUTPUT_NAMES = ("next_q2", "next_q1", "next_q0")
COMPILERS = {
    "minterm": "mailcpu.transition_space.compile_transition_table",
    "direct_dag": "mailcpu.transition_space.compile_compositional_transition_program",
    "live_dag": "mailcpu.transition_space.compile_live_compositional_transition_program",
}


def feedback_program(*, invert_input: bool = False) -> FiniteTransitionProgram:
    """Declare q'=(q1,q0,q2 XOR q0 XOR d), optionally replacing d by NOT d."""
    q2 = BooleanInput("q2")
    q1 = BooleanInput("q1")
    q0 = BooleanInput("q0")
    d = BooleanInput("d")
    feedback_input = BooleanNot(d) if invert_input else d
    feedback = BooleanXor(BooleanXor(q2, q0), feedback_input)
    suffix = "input-inverted" if invert_input else "baseline"
    return FiniteTransitionProgram(
        f"three-bit-feedback.{suffix}.v1",
        INPUT_NAMES,
        OUTPUT_NAMES,
        (q1, q0, feedback),
    )


def independent_reference(phase: str, inputs: Sequence[int]) -> tuple[int, ...]:
    """Scalar specification kept separate from the typed AST and all compilers."""
    q2, q1, q0, d = (int(value) for value in inputs)
    if phase == "law-level-feedback-inversion":
        return (q1, q0, q2 ^ q0 ^ (1 - d))
    baseline = (q1, q0, q2 ^ q0 ^ d)
    if phase == "local-row-override" and tuple(inputs) == LOCAL_INPUTS:
        return LOCAL_OUTPUTS
    return baseline


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
    """Build a VGI Signal8 decision tree for a total finite table."""
    outputs = tuple(
        OutputSpec(name, _decision_expression(table, index))
        for index, name in enumerate(table.output_names)
    )
    addresses = tuple(f"input.{name}" for name in table.input_names)
    task = TaskSpec(table.name, addresses + ("input.zero", "input.one"), outputs)
    backend = Signal8Backend()
    interpreter = VirtualGroundInterpreter()
    observers = (1, 3, 5, 7)

    def observe(inputs: tuple[int, ...]) -> tuple[int, ...]:
        memory = {
            f"input.{name}": backend.encode_symbol(4 * bit, observer=observer)
            for name, bit, observer in zip(table.input_names, inputs, observers)
        }
        memory["input.zero"] = backend.encode_symbol(0, observer=1)
        memory["input.one"] = backend.encode_symbol(4, observer=7)
        result = interpreter.interpret(task, memory)
        observed = result.observed_outputs(backend)
        return tuple(decode_boolean_signal(observed[name]) for name in table.output_names)

    return observe


def _translation_contract(table, executable, model, *, phase, model_name, row_index, typed_digest):
    source = program_representation_ref(executable)
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
        "wsp-002.typed-law-to-relu",
        1,
        {
            "compiler": COMPILERS[model_name],
            "derived_table_digest": table.digest,
            "architecture": list(model.architecture),
            "model_name": model_name,
            "typed_transition_program_digest": typed_digest,
        },
    )
    inputs = tuple(table.rows[row_index].inputs)
    return TranslationContract(
        contract_id=f"wsp-002-{phase}-{model_name}-{row_index}",
        revision=1,
        source=source,
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
                "typed_transition_program_digest": typed_digest,
                "inputs": dict(zip(table.input_names, inputs)),
            }
        ),
        precondition_digests=(
            canonical_value_digest({"input_domain": "{0,1}^4"}),
        ),
        invariant_digests=(
            canonical_value_digest({"output_domain": "{0,1}^3"}),
        ),
        resource_bounds=(
            ResourceBound("parameters", model.parameter_count, "scalar-parameters"),
            ResourceBound("instructions", len(executable.instructions), "instructions"),
        ),
        effect_class=EffectClass.PURE,
        replay_class=ReplayClass.DETERMINISTIC,
    )


def verify_case(table, typed_program, executable, vgi_observe, model, inputs, *, phase, model_name, row_index):
    """Compare independent scalar, typed AST, MailCPU, VGI, and neural observations."""
    expected = independent_reference(phase, inputs)
    typed = typed_program.evaluate(inputs)
    table_value = table.row_for(inputs).outputs
    initial = dict(zip(table.input_names, inputs))
    reference = ReferenceInterpreter(executable).run(initial_registers=initial)
    queued = QueueInterpreter(executable).run(initial_registers=initial)
    if reference.status.value != "halted" or queued.status.value != "halted":
        raise AssertionError("MailCPU transition program did not halt")
    if canonical_result(reference) != canonical_result(queued):
        raise AssertionError("MailCPU reference and queue executions diverged")
    ref_outputs = tuple(reference.state.registers[name] for name in table.output_names)
    queue_outputs = tuple(queued.state.registers[name] for name in table.output_names)
    vgi_outputs = vgi_observe(inputs)
    neural_outputs = model.predict(inputs)
    observed = (typed, table_value, ref_outputs, queue_outputs, vgi_outputs, neural_outputs)
    if any(value != expected for value in observed):
        raise AssertionError(
            {
                "phase": phase,
                "model": model_name,
                "inputs": list(inputs),
                "independent_expected": list(expected),
                "typed": list(typed),
                "table": list(table_value),
                "mailcpu_reference": list(ref_outputs),
                "mailcpu_queue": list(queue_outputs),
                "vgi": list(vgi_outputs),
                "neural": list(neural_outputs),
            }
        )

    contract = _translation_contract(
        table,
        executable,
        model,
        phase=phase,
        model_name=model_name,
        row_index=row_index,
        typed_digest=typed_program.digest,
    )
    comparison = compare_projected_observations(
        contract,
        case_payload={
            "table_digest": table.digest,
            "typed_transition_program_digest": typed_program.digest,
            "input_registers": initial,
        },
        source_observation=dict(zip(table.output_names, ref_outputs)),
        target_observation=dict(zip(table.output_names, neural_outputs)),
    )
    if not comparison.equivalent:
        raise AssertionError("translation contract rejected a matching case")
    return {
        "phase": phase,
        "compiler": model_name,
        "row_index": row_index,
        "inputs": list(inputs),
        "outputs": list(expected),
        "translation_equivalent": comparison.equivalent,
        "translation_contract_digest": comparison.contract_digest,
    }


def compile_all(program: FiniteTransitionProgram) -> dict[str, Any]:
    table = program.to_table()
    return {
        "table": table,
        "models": {
            "minterm": compile_transition_table(table),
            "direct_dag": compile_compositional_transition_program(program),
            "live_dag": compile_live_compositional_transition_program(program),
        },
    }


def observation_digest(model) -> str:
    payload = [
        {"inputs": list(inputs), "outputs": list(model.predict(inputs))}
        for inputs in itertools.product((0, 1), repeat=4)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def model_info(name: str, model) -> dict[str, Any]:
    return {
        "compiler": name,
        "compiler_id": COMPILERS[name],
        "architecture": list(model.architecture),
        "dense_parameter_count": model.parameter_count,
        "active_parameter_count": model.active_parameter_count,
        "active_fraction": (
            model.active_parameter_count / model.parameter_count
            if model.parameter_count
            else 0.0
        ),
        "artifact_digest": model.digest,
        "finite_domain_observation_digest": observation_digest(model),
    }


def _clone_with_tensors(model, weights, biases):
    if isinstance(model, TransitionReLUNetwork):
        return TransitionReLUNetwork(
            weights,
            biases,
            table_digest=model.table_digest,
            input_names=model.input_names,
            output_names=model.output_names,
            architecture=model.architecture,
        )
    if isinstance(model, CompositionalTransitionReLUNetwork):
        return CompositionalTransitionReLUNetwork(
            weights,
            biases,
            program_digest=model.program_digest,
            input_names=model._input_names,
            output_names=model._output_names,
            architecture=model.architecture,
        )
    raise TypeError(f"unsupported network type: {type(model).__name__}")


def transform_hidden_layer(model, permutation: Sequence[int], scales: Mapping[int, float], *, inverse=False):
    """Apply a hidden permutation and positive ReLU rescaling, or its exact inverse."""
    weights = [[list(row) for row in layer] for layer in model.weights]
    biases = [list(layer) for layer in model.biases]
    layer = 0
    width = model.architecture[layer + 1]
    permutation = tuple(permutation)
    if sorted(permutation) != list(range(width)):
        raise ValueError("permutation must be a bijection over hidden-unit coordinates")
    normalized_scales = {int(index): float(scale) for index, scale in scales.items()}
    if any(index < 0 or index >= width or not scale > 0 for index, scale in normalized_scales.items()):
        raise ValueError("scale coordinates must be valid and scales strictly positive")

    if inverse:
        for index, scale in normalized_scales.items():
            weights[layer][index] = [value / scale for value in weights[layer][index]]
            biases[layer][index] /= scale
            for row in weights[layer + 1]:
                row[index] *= scale
        inverse_permutation = tuple(permutation.index(old_index) for old_index in range(width))
        weights[layer] = [weights[layer][inverse_permutation[index]] for index in range(width)]
        biases[layer] = [biases[layer][inverse_permutation[index]] for index in range(width)]
        weights[layer + 1] = [
            [row[inverse_permutation[index]] for index in range(width)]
            for row in weights[layer + 1]
        ]
    else:
        weights[layer] = [weights[layer][old_index] for old_index in permutation]
        biases[layer] = [biases[layer][old_index] for old_index in permutation]
        weights[layer + 1] = [
            [row[old_index] for old_index in permutation]
            for row in weights[layer + 1]
        ]
        for index, scale in normalized_scales.items():
            weights[layer][index] = [value * scale for value in weights[layer][index]]
            biases[layer][index] *= scale
            for row in weights[layer + 1]:
                row[index] /= scale
    return _clone_with_tensors(model, weights, biases)


def permute_without_compensation(model, permutation: Sequence[int]):
    """Negative control: move hidden units but leave downstream columns unchanged."""
    weights = [[list(row) for row in layer] for layer in model.weights]
    biases = [list(layer) for layer in model.biases]
    weights[0] = [weights[0][old_index] for old_index in permutation]
    biases[0] = [biases[0][old_index] for old_index in permutation]
    return _clone_with_tensors(model, weights, biases)


def verify_weight_equivalence(models: Mapping[str, Any]) -> dict[str, Any]:
    """Generate distinct but equivalent parameterizations and a broken symmetry control."""
    finite_digests = {name: observation_digest(model) for name, model in models.items()}
    if len(set(finite_digests.values())) != 1:
        raise AssertionError("compiler routes do not share one finite-domain function")
    baseline = models["minterm"]
    width = baseline.architecture[1]
    rng = random.Random(SEED)
    variants = []
    seen = {baseline.digest}
    attempts = 0
    while len(variants) < 20 and attempts < 500:
        attempts += 1
        permutation = list(range(width))
        rng.shuffle(permutation)
        if permutation == list(range(width)):
            continue
        scales = {rng.randrange(width): float(2 ** rng.randint(1, 3))}
        candidate = transform_hidden_layer(baseline, permutation, scales)
        if candidate.digest in seen:
            continue
        if any(
            candidate.predict(inputs) != baseline.predict(inputs)
            for inputs in itertools.product((0, 1), repeat=4)
        ):
            raise AssertionError("valid ReLU symmetry changed finite-domain behavior")
        restored = transform_hidden_layer(candidate, permutation, scales, inverse=True)
        if restored.digest != baseline.digest:
            raise AssertionError("inverse symmetry did not restore the source artifact")
        seen.add(candidate.digest)
        variants.append(
            {
                "artifact_digest": candidate.digest,
                "finite_domain_observation_digest": observation_digest(candidate),
                "permutation": permutation,
                "positive_scales": {str(key): value for key, value in scales.items()},
                "inverse_restores_source_digest": True,
            }
        )
    if len(variants) != 20:
        raise AssertionError("could not construct 20 distinct symmetry-related parameterizations")

    negative = None
    for left in range(width):
        for right in range(left + 1, width):
            permutation = list(range(width))
            permutation[left], permutation[right] = permutation[right], permutation[left]
            candidate = permute_without_compensation(baseline, permutation)
            counterexamples = [
                inputs
                for inputs in itertools.product((0, 1), repeat=4)
                if candidate.predict(inputs) != baseline.predict(inputs)
            ]
            if counterexamples:
                witness = counterexamples[0]
                negative = {
                    "permutation": permutation,
                    "artifact_digest": candidate.digest,
                    "counterexample": list(witness),
                    "source_output": list(baseline.predict(witness)),
                    "altered_output": list(candidate.predict(witness)),
                    "detected": True,
                }
                break
        if negative is not None:
            break
    if negative is None:
        raise AssertionError("uncompensated permutation negative control was not detected")

    route_controls = {}
    for name, model in models.items():
        route_width = model.architecture[1]
        transformed = transform_hidden_layer(
            model,
            tuple(reversed(range(route_width))),
            {0: 2.0},
        )
        if any(
            transformed.predict(inputs) != model.predict(inputs)
            for inputs in itertools.product((0, 1), repeat=4)
        ):
            raise AssertionError(f"symmetry failed on compiler route {name}")
        route_controls[name] = {
            "source_artifact_digest": model.digest,
            "transformed_artifact_digest": transformed.digest,
            "same_finite_domain_observations": True,
        }

    return {
        "relation": "observer-relative functional equivalence on the complete {0,1}^4 domain",
        "source_models": {
            name: {
                "artifact_digest": model.digest,
                "finite_domain_observation_digest": finite_digests[name],
                "architecture": list(model.architecture),
            }
            for name, model in models.items()
        },
        "distinct_minterm_variants": variants,
        "variant_count": len(variants),
        "cross_route_symmetry_controls": route_controls,
        "uncompensated_permutation_negative_control": negative,
    }


def verify_rollouts(program: FiniteTransitionProgram, models: Mapping[str, Any]) -> dict[str, Any]:
    """Exhaust all 8 starting states and 256 length-eight input sequences."""
    trajectories = 0
    transitions = 0
    for initial in itertools.product((0, 1), repeat=3):
        for sequence in itertools.product((0, 1), repeat=8):
            state = tuple(initial)
            for d in sequence:
                inputs = state + (d,)
                expected = independent_reference("baseline", inputs)
                typed = program.evaluate(inputs)
                outputs = {name: model.predict(inputs) for name, model in models.items()}
                if typed != expected or any(value != expected for value in outputs.values()):
                    raise AssertionError(
                        {
                            "initial_state": list(initial),
                            "input_sequence": list(sequence),
                            "state": list(state),
                            "input": d,
                            "expected": list(expected),
                            "typed": list(typed),
                            "models": {name: list(value) for name, value in outputs.items()},
                        }
                    )
                state = expected
                transitions += 1
            trajectories += 1
    return {
        "initial_state_count": 8,
        "input_sequences_per_state": 256,
        "sequence_length": 8,
        "trajectory_count": trajectories,
        "transition_count": transitions,
        "all_models_match_independent_reference": True,
    }


def verify_stateful_revision(source: FiniteTransitionProgram, target: FiniteTransitionProgram) -> dict[str, Any]:
    """Revise a live runtime at an unchanged tick, then verify replay and tamper rejection."""
    runtime = StatefulTransitionRuntime(
        source,
        initial_state=(1, 0, 1),
        state_input_names=STATE_INPUT_NAMES,
    )
    prefix = (0, 1, 1)
    for d in prefix:
        runtime.step({"d": d})
    state_before = runtime.state
    tick_before = runtime.tick
    revision_event = runtime.revise(target)
    if runtime.state != state_before or runtime.tick != tick_before or runtime.revision != 1:
        raise AssertionError("revision changed live state/time or failed to advance revision")

    suffix = (1, 0, 1)
    suffix_outputs = []
    for d in suffix:
        inputs = runtime.state + (d,)
        expected = independent_reference("law-level-feedback-inversion", inputs)
        step = runtime.step({"d": d})
        if step.state != expected:
            raise AssertionError("revised runtime did not apply the new feedback law")
        suffix_outputs.append(list(step.state))

    snapshot = runtime.snapshot()
    restored = StatefulTransitionRuntime.from_snapshot(snapshot)
    if (
        restored.state != runtime.state
        or restored.tick != runtime.tick
        or restored.revision != runtime.revision
        or restored.chain_head_digest != runtime.chain_head_digest
    ):
        raise AssertionError("snapshot restore did not reconstruct revision history")
    tampered = json.loads(json.dumps(snapshot))
    tampered["events"][0]["event_digest"] = "0" * 64
    try:
        StatefulTransitionRuntime.from_snapshot(tampered)
    except StatefulTransitionError:
        tamper_rejected = True
    else:
        raise AssertionError("tampered stateful event history was accepted")
    return {
        "prefix_inputs": list(prefix),
        "revision_tick": tick_before,
        "revision_event_digest": revision_event["event_digest"],
        "state_preserved_at_revision": list(state_before),
        "tick_preserved_at_revision": tick_before,
        "revision_after_install": runtime.revision,
        "suffix_inputs": list(suffix),
        "suffix_states": suffix_outputs,
        "snapshot_restored_equal": True,
        "tampered_event_rejected": tamper_rejected,
        "final_tick": runtime.tick,
        "final_state": list(runtime.state),
        "event_count": runtime.event_count,
        "chain_head_digest": runtime.chain_head_digest,
    }


def verify_phase(phase: str, compiled: dict[str, Any], typed_program: FiniteTransitionProgram):
    table = compiled["table"]
    models = compiled["models"]
    executable = compile_transition_program(table)
    vgi = _vgi_observer(table)
    patterns = list(itertools.product((0, 1), repeat=4))
    cases = []
    for model_name, model in models.items():
        for row_index, inputs in enumerate(patterns):
            cases.append(
                verify_case(
                    table,
                    typed_program,
                    executable,
                    vgi,
                    model,
                    inputs,
                    phase=phase,
                    model_name=model_name,
                    row_index=row_index,
                )
            )
    observation_digests = {observation_digest(model) for model in models.values()}
    if len(observation_digests) != 1:
        raise AssertionError(f"compiler routes disagree in phase {phase}")
    return {
        "phase": phase,
        "typed_program_digest": typed_program.digest,
        "table_digest": table.digest,
        "independent_observation_digest": next(iter(observation_digests)),
        "models": [model_info(name, model) for name, model in models.items()],
        "case_count": len(cases),
        "cases": cases,
        "all_cases_verified": True,
    }


def run_experiment() -> dict[str, Any]:
    baseline_program = feedback_program()
    local_program = baseline_program.with_row_output(
        LOCAL_INPUTS,
        LOCAL_OUTPUTS,
        name="three-bit-feedback.local-exception.v1",
    )
    law_program = feedback_program(invert_input=True)

    baseline = compile_all(baseline_program)
    local = compile_all(local_program)
    local_minterm = compile_transition_table(baseline["table"])
    local_intervention = apply_table_intervention(
        local_minterm,
        baseline["table"],
        local["table"],
    )
    if local_intervention.changed_parameters != 1:
        raise AssertionError("one-row override should change one minterm output weight")
    local["models"]["minterm"] = local_minterm

    law_level = compile_all(law_program)
    baseline_result = verify_phase("baseline", baseline, baseline_program)
    local_result = verify_phase("local-row-override", local, local_program)
    law_result = verify_phase("law-level-feedback-inversion", law_level, law_program)

    equivalence = verify_weight_equivalence(baseline["models"])
    rollouts = verify_rollouts(baseline_program, baseline["models"])
    stateful = verify_stateful_revision(baseline_program, law_program)
    return {
        "schema": "in-formation-space.verified-weight-space-realization.wsp002.v1",
        "status": "verified-within-complete-finite-domain",
        "experiment_id": "WSP-002",
        "source_revisions": {
            "ecpu": os.environ.get("ECPU_REVISION", "unspecified-local-checkout"),
            "vgi": os.environ.get("VGI_REVISION", "unspecified-local-checkout"),
            "ifs": os.environ.get("IFS_REVISION", "unspecified-local-checkout"),
        },
        "ground": {
            "name": "three-bit-input-driven-feedback-register",
            "input_names": list(INPUT_NAMES),
            "output_names": list(OUTPUT_NAMES),
            "domain": "{0,1}^4",
            "domain_size": 16,
            "law": [
                "next_q2 = q1",
                "next_q1 = q0",
                "next_q0 = q2 XOR q0 XOR d",
            ],
            "local_override": {
                "inputs": list(LOCAL_INPUTS),
                "source_outputs": list(baseline["table"].row_for(LOCAL_INPUTS).outputs),
                "target_outputs": list(LOCAL_OUTPUTS),
                "changed_output_bits": 1,
                "weight_intervention": local_intervention.to_dict(),
            },
            "law_level_edit": {
                "source": "next_q0 = q2 XOR q0 XOR d",
                "target": "next_q0 = q2 XOR q0 XOR NOT d",
                "affected_rows": 16,
                "changed_output_bits": 16,
            },
        },
        "compiler_routes": [
            "truth-table-minterm",
            "direct-expression-dag",
            "liveness-compacted-expression-dag",
        ],
        "phases": [baseline_result, local_result, law_result],
        "phase_case_count": sum(
            phase["case_count"] for phase in (baseline_result, local_result, law_result)
        ),
        "weight_equivalence": equivalence,
        "recurrent_trajectory_verification": rollouts,
        "stateful_revision_verification": stateful,
        "parameter_accounting": {
            "separates_dense_slots_from_nonzero_active_parameters": True,
            "reports_architecture_and_active_fraction_per_model": True,
        },
        "verification_scope": (
            "Exhaustive exact verification over all 16 Boolean transition inputs for three compiler routes, "
            "cross-checked against an independent scalar law, the typed source, MailCPU reference and queue "
            "interpreters, and VGI Signal8. Recurrent checks cover every length-eight input sequence from every "
            "three-bit initial state. ReLU symmetry checks establish observer-relative equivalence only on {0,1}^4."
        ),
        "limitations": [
            "No claim is made outside the declared four-bit Boolean input domain.",
            "The finite-domain observation digest is not a proof of equivalence on arbitrary real inputs.",
            "Positive scaling and permutation cover selected constructive ReLU symmetries, not all equivalent networks.",
            "Stateful revision and replay are local deterministic runtime checks, not distributed atomicity or durable cross-host guarantees.",
            "No training, general LLM weight decompilation, quantization, continuous-domain verification, or hardware advantage is claimed.",
        ],
    }


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
                "phase_case_count": result["phase_case_count"],
                "symmetry_variants": result["weight_equivalence"]["variant_count"],
                "trajectories": result["recurrent_trajectory_verification"]["trajectory_count"],
                "transitions": result["recurrent_trajectory_verification"]["transition_count"],
                "stateful_replay": result["stateful_revision_verification"]["snapshot_restored_equal"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
