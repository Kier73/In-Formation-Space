"""Emit deterministic COE-001 evidence, with no external network/model."""
from __future__ import annotations
import json
from test_continuous_equivalence import (
    identity, relu_identity, zero, bump, equivalent_rescaled_bump)
from continuous_equivalence import compare, evaluate, q


def main() -> None:
    reparam = compare(identity(), relu_identity())
    homogeneity = compare(bump(), equivalent_rescaled_bump())
    counterexample = compare(zero(), bump())
    if [reparam["status"], homogeneity["status"], counterexample["status"]] != ["equivalent", "equivalent", "different"]:
        raise RuntimeError("discriminating outcomes changed")
    report = {
        "schema": "in-formation-space.continuous-observation-equivalence/0.1",
        "arithmetic": "exact-rational-symbolic-ideal-real",
        "input_domain": "entire-real-line",
        "observation": "ordered-output-vector",
        "identity_vs_relu": reparam,
        "rescaled_bump": homogeneity,
        "binary_agreement_but_continuous_disagreement": {
            "at_0_equal": evaluate(zero(), q(0)) == evaluate(bump(), q(0)),
            "at_1_equal": evaluate(zero(), q(1)) == evaluate(bump(), q(1)),
            "comparison": counterexample,
        },
        "limitations": [
            "one scalar input; dense feed-forward affine/ReLU layers only",
            "rational parameters under ideal exact real arithmetic, not float hardware execution",
            "complete only when finite symbolic region budget is sufficient",
            "algorithmic verifier and tests, not independent proof assistant checking",
        ],
    }
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
