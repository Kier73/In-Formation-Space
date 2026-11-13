"""Coefficient-law checker and separately written scalar forward oracle.

The checker never calls the widening constructor. Binary32 values and their
exact halves embed in binary64. Each descendant must equal the original row
or its exact half, so no rounded sum can hide a small unmatched contribution.
"""
from __future__ import annotations

import math
import numpy as np

from .formation import Block, FormationError


def verify_conservation(source: Block, child: Block, certificate: dict) -> dict:
    inputs, hidden, outputs = source.validate()
    ci, width, co = child.validate()
    if (ci, co) != (inputs, outputs) or source.activation != child.activation:
        raise FormationError("interface or activation changed")
    if not hidden < width <= 2 * hidden:
        raise FormationError("unsupported width relationship")
    if certificate.get("schema") != "ifs.dyadic-neuron-widening.v1":
        raise FormationError("unsupported certificate")
    if certificate.get("rule") != "duplicate-incoming-and-conserve-outgoing-coefficients":
        raise FormationError("unsupported rule")
    if certificate.get("source_digest") != source.descriptor()["digest"]:
        raise FormationError("source identity mismatch")
    if certificate.get("generated_digest") != child.descriptor()["digest"]:
        raise FormationError("generated identity mismatch")
    parents = certificate.get("parent_index")
    if (not isinstance(parents, list) or len(parents) != width or
            any(type(p) is not int or not 0 <= p < hidden for p in parents)):
        raise FormationError("invalid parent map")
    groups = [[] for _ in range(hidden)]
    for j, parent in enumerate(parents):
        groups[parent].append(j)
        if (not np.array_equal(child.up_weight[:, j], source.up_weight[:, parent]) or
                child.up_bias[j] != source.up_bias[parent]):
            raise FormationError("incoming coefficients changed")
    if any(not 1 <= len(group) <= 2 for group in groups):
        raise FormationError("each source neuron must have one or two descendants")
    for parent, group in enumerate(groups):
        expected = source.down_weight[parent].astype(np.float64) / len(group)
        for descendant in group:
            if not np.array_equal(child.down_weight[descendant].astype(np.float64), expected):
                raise FormationError("outgoing coefficient conservation failed")
    if not np.array_equal(child.down_bias, source.down_bias):
        raise FormationError("output bias changed")
    return {"status": "passed", "incoming_neurons_checked": width,
            "outgoing_coefficients_checked": hidden * outputs,
            "coefficient_comparison": "exact-binary32-in-binary64",
            "meaning": "algebraic-function-preservation-under-shared-elementwise-activation",
            "kernel_accepted": False, "floating_point_bitwise_equivalence_claimed": False}


def scalar_oracle(block: Block, values: np.ndarray, output_indices: list[int]) -> np.ndarray:
    """Independent loop/math.fsum execution for explicitly selected output coordinates."""
    inputs, hidden, outputs = block.validate()
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != inputs or not np.isfinite(x).all():
        raise FormationError("invalid scalar oracle inputs")
    if (not output_indices or len(set(output_indices)) != len(output_indices) or
            any(type(k) is not int or not 0 <= k < outputs for k in output_indices)):
        raise FormationError("invalid oracle output selection")
    if len(x) * hidden * (inputs + len(output_indices)) > 12_000_000:
        raise FormationError("scalar oracle work budget exceeded")
    result = []
    for row in x:
        activated = []
        for j in range(hidden):
            z = math.fsum(float(row[i]) * float(block.up_weight[i, j]) for i in range(inputs))
            z += float(block.up_bias[j])
            if block.activation == "relu":
                y = max(z, 0.0)
            else:
                y = z / 2.0 * (1.0 + math.tanh((2.0 / math.pi)**0.5 * (z + 0.044715 * z*z*z)))
            activated.append(y)
        result.append([math.fsum(activated[j] * float(block.down_weight[j, k]) for j in range(hidden))
                       + float(block.down_bias[k]) for k in output_indices])
    a = np.asarray(result, dtype=np.float64)
    if not np.isfinite(a).all():
        raise FormationError("nonfinite scalar result")
    return a
