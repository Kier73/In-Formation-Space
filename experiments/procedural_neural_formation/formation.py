"""Construct a bounded neural block and widen it without training.

The independently checked coefficient conservation law is exact for admitted
binary32 parameters. Numerical forward comparisons are separate measurements.
This is a Net2Wider-style reimplementation, not a new widening algorithm.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np

MAX_ELEMENTS = 20_000_000
KEYS = ("up_weight", "up_bias", "down_weight", "down_bias")


class FormationError(ValueError):
    """A construction or evidence binding does not meet the supported contract."""


def digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _size(inputs: int, hidden: int, outputs: int) -> int:
    return inputs * hidden + hidden + hidden * outputs + outputs


def check_budget(inputs: int, hidden: int, outputs: int, budget: int) -> int:
    if any(type(x) is not int or x <= 0 for x in (inputs, hidden, outputs, budget)):
        raise FormationError("dimensions and budget must be positive integers")
    count = _size(inputs, hidden, outputs)
    if budget > MAX_ELEMENTS or count > budget:
        raise FormationError("parameter element budget exceeded")
    return count


@dataclass(frozen=True)
class Block:
    """An explicit affine -> elementwise activation -> affine construction."""

    up_weight: np.ndarray
    up_bias: np.ndarray
    down_weight: np.ndarray
    down_bias: np.ndarray
    activation: str = "gelu_tanh"

    def validate(self) -> tuple[int, int, int]:
        arrays = [getattr(self, key) for key in KEYS]
        if any(not isinstance(a, np.ndarray) or a.dtype != np.float32 for a in arrays):
            raise FormationError("all parameters must be binary32 arrays")
        if self.up_weight.ndim != 2 or self.down_weight.ndim != 2:
            raise FormationError("weights must be matrices")
        inputs, hidden = self.up_weight.shape
        h2, outputs = self.down_weight.shape
        check_budget(inputs, hidden, outputs, MAX_ELEMENTS)
        if h2 != hidden or self.up_bias.shape != (hidden,) or self.down_bias.shape != (outputs,):
            raise FormationError("affine dimensions do not compose")
        if self.activation not in ("relu", "gelu_tanh"):
            raise FormationError("unsupported elementwise activation")
        if any(not np.isfinite(a).all() for a in arrays):
            raise FormationError("nonfinite parameters")
        return inputs, hidden, outputs

    def descriptor(self) -> dict:
        dimensions = self.validate()
        tensors = {}
        for key in KEYS:
            a = np.ascontiguousarray(getattr(self, key), dtype="<f4")
            tensors[key] = {"shape": list(a.shape), "dtype": "F32",
                            "sha256": hashlib.sha256(a.tobytes()).hexdigest()}
        record = {"schema": "ifs.feed-forward-block.v1", "dimensions": list(dimensions),
                  "activation": self.activation, "tensors": tensors}
        return {**record, "digest": digest(record)}


def procedural_block(inputs: int, hidden: int, outputs: int, *, activation: str = "gelu_tanh",
                     seed: int = 31, max_elements: int = MAX_ELEMENTS) -> Block:
    """Materialize deterministic dyadic coefficients, with no external model input."""
    check_budget(inputs, hidden, outputs, max_elements)
    if type(seed) is not int or seed < 0:
        raise FormationError("seed must be a nonnegative integer")
    rng = np.random.Generator(np.random.PCG64(seed))
    arrays = [rng.integers(-16, 17, size=shape).astype(np.float32) / np.float32(32)
              for shape in ((inputs, hidden), (hidden,), (hidden, outputs), (outputs,))]
    block = Block(*arrays, activation)
    block.validate()
    return block


def widen(source: Block, target_width: int, *, max_elements: int = MAX_ELEMENTS) -> tuple[Block, dict]:
    """Duplicate a prefix once; split each duplicated outgoing row into two halves.

    At most doubling avoids division by non-dyadic multiplicities. Subnormal
    underflow still may lose information and is refused by the independent checker.
    """
    inputs, hidden, outputs = source.validate()
    if type(target_width) is not int or not hidden < target_width <= 2 * hidden:
        raise FormationError("target width must be greater than source and at most double")
    check_budget(inputs, target_width, outputs, max_elements)
    parents = list(range(hidden)) + list(range(target_width - hidden))
    counts = np.bincount(parents, minlength=hidden)
    child = Block(source.up_weight[:, parents].copy(), source.up_bias[parents].copy(),
                  (source.down_weight[parents] / counts[parents, None]).astype(np.float32),
                  source.down_bias.copy(), source.activation)
    certificate = {"schema": "ifs.dyadic-neuron-widening.v1", "parent_index": parents,
                   "source_digest": source.descriptor()["digest"],
                   "generated_digest": child.descriptor()["digest"],
                   "rule": "duplicate-incoming-and-conserve-outgoing-coefficients"}
    # The verifier does not invoke this constructor or derive expected child arrays.
    from .verification import verify_conservation
    verify_conservation(source, child, certificate)
    return child, certificate


def evaluate(block: Block, values: np.ndarray) -> np.ndarray:
    """Float64 NumPy evaluation of binary32 coefficients; not source-runtime inference."""
    inputs, hidden, outputs = block.validate()
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != inputs or not np.isfinite(x).all():
        raise FormationError("inputs must be a finite [probe,input] matrix")
    if x.size + len(x) * (4 * hidden + outputs) > MAX_ELEMENTS:
        raise FormationError("execution element budget exceeded")
    z = x @ block.up_weight.astype(np.float64) + block.up_bias
    if block.activation == "relu":
        h = np.maximum(z, 0)
    else:
        h = 0.5 * z * (1 + np.tanh(math.sqrt(2 / math.pi) * (z + 0.044715 * z**3)))
    result = h @ block.down_weight.astype(np.float64) + block.down_bias
    if not np.isfinite(result).all():
        raise FormationError("nonfinite numerical execution")
    return result
