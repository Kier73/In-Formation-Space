"""Produce USM-003 evidence by operating an actual E-CPU model-facing receiver.

Runs on a separate hosted VM from the independent source/trace verifier.
Requires the pinned E-CPU checkout on PYTHONPATH; verifier has no such need.
"""

from __future__ import annotations

import json
from pathlib import Path

from examples.model_ground_os import GroundPolicyModel, _digest, sample_stream, train_example_model
from examples.model_system_calls import run_model_system
from mailcpu.structural_memory import StructuralMemoryRegistry


def produce() -> dict[str, object]:
    context = {"tenant": "use-system", "purpose": "observed-computation"}
    host = StructuralMemoryRegistry(admission_policy=lambda proposal: (
        proposal.spec.domain == "model-operated-observed-orbit"
        and proposal.spec.context == context
    ))
    trained, _ = train_example_model()
    cases: list[dict[str, object]] = []
    for policy, model in (("high-request", GroundPolicyModel(bias=30.0)),
                          ("trained", trained)):
        for kind, seed in (("affine", 201), ("nonlinear", 207)):
            source_id = f"usm003-{policy}-{kind}"
            session_id = f"session-{policy}-{kind}"
            coordinate = 10**12 + 137
            episode = run_model_system(
                model, host, source_id, sample_stream(kind, seed),
                coordinate=coordinate, session_id=session_id, context=context,
            )
            cases.append({
                "case": {"stream_id": source_id, "session_id": session_id,
                         "kind": kind, "seed": seed,
                         "coordinate": coordinate, "policy": policy},
                "episode": episode,
            })
    # A guaranteed high-confidence request checks actual E-CPU realization
    # while the independently trained model's decisions remain unconstrained.
    high_affine = next(x for x in cases if x["case"]["stream_id"] == "usm003-high-request-affine")
    high_nonlin = next(x for x in cases if x["case"]["stream_id"] == "usm003-high-request-nonlinear")
    assert high_affine["episode"]["status"] == "complete"
    assert high_nonlin["episode"]["status"] == "refused"
    core = {"schema": "in-formation-space.usm003.bundle.v1", "cases": cases}
    return {**core, "bundle_digest": _digest(core)}


def main() -> None:
    output = Path("usm003-source-bundle.json")
    output.write_text(json.dumps(produce(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"retained model-operated E-CPU evidence: {output}")


if __name__ == "__main__":
    main()
