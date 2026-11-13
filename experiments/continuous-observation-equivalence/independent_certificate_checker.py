"""COE-002 independent proof checker for scalar rational ReLU networks.

Standalone standard-library checker: does NOT import the certificate builder,
COE-001 atlas constructor, or their function-evaluation methods.

It checks the *supplied* interval cover rather than searching for breakpoints.
Within each cell it derives each layer's affine preactivation and rejects any
interior zero. Fixed signs certify that the proposed output law is valid there.
Continuity of affine/ReLU compositions then covers the cell endpoints.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import re
from typing import Any

SCHEMA = "in-formation-space.coe002.activation-cell-certificate/0.1"
_RAT = re.compile(r"(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class CertificateError(ValueError):
    """A claimed proof does not establish the requested function."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CertificateError(message)


def object_with(obj: object, keys: set[str], name: str) -> dict[str, Any]:
    require(type(obj) is dict and set(obj) == keys, f"invalid {name} fields")
    return obj


def rational(value: object) -> Fraction:
    require(type(value) is str and len(value) <= 128 and _RAT.fullmatch(value) is not None,
            "noncanonical rational token")
    try:
        result = Fraction(value)
    except (ZeroDivisionError, ValueError) as exc:
        raise CertificateError("invalid rational denominator") from exc
    require(str(result) == value, "rational not in reduced canonical form")
    return result


def endpoint(value: object, side: str) -> Fraction | None:
    if value == ("-inf" if side == "left" else "+inf"):
        return None
    return rational(value)


def affine_vector(value: object, *, expected_width: int | None = None) -> tuple[tuple[Fraction, Fraction], ...]:
    require(type(value) is list and 0 < len(value) <= 128, "affine vector width")
    if expected_width is not None:
        require(len(value) == expected_width, "affine vector arity mismatch")
    result = []
    for pair in value:
        require(type(pair) is list and len(pair) == 2, "affine coordinate must be pair")
        result.append((rational(pair[0]), rational(pair[1])))
    return tuple(result)


def parse_network(network: object) -> tuple[tuple[str, tuple[tuple[Fraction, ...], ...], tuple[Fraction, ...]], ...]:
    raw = object_with(network, {"layers"}, "network")
    layers = raw["layers"]
    require(type(layers) is list and 0 < len(layers) <= 64, "layer count")
    width = 1
    result = []
    for source in layers:
        current = object_with(source, {"activation", "weights", "bias"}, "layer")
        require(current["activation"] in ("relu", "linear"), "unknown activation")
        weights, bias = current["weights"], current["bias"]
        require(type(weights) is list and type(bias) is list and
                0 < len(weights) <= 128 and len(weights) == len(bias), "invalid matrix dimensions")
        matrix = []
        for row in weights:
            require(type(row) is list and len(row) == width, "nonrectangular or disconnected matrix")
            matrix.append(tuple(rational(member) for member in row))
        result.append((current["activation"], tuple(matrix), tuple(rational(b) for b in bias)))
        width = len(weights)
    return tuple(result)


def json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def hash_bytes(value: object) -> str:
    return hashlib.sha256(json_bytes(value)).hexdigest()


def sample(left: Fraction | None, right: Fraction | None) -> Fraction:
    if left is None:
        return Fraction(0) if right is None else right - 1
    return left + 1 if right is None else (left + right) / 2


def cell(value: object, expected_width: int) -> tuple[Fraction | None, Fraction | None, tuple[tuple[Fraction, Fraction], ...]]:
    raw = object_with(value, {"left", "right", "affines"}, "cell")
    return endpoint(raw["left"], "left"), endpoint(raw["right"], "right"), affine_vector(
        raw["affines"], expected_width=expected_width)


def verify_certificate(certificate: object, *, expected_network_sha256: str | None = None,
                       max_cells: int = 4096, max_scalar_ops: int = 3_000_000) -> dict[str, object]:
    """Verify a supplied all-real activation cover, not a constructor's assertion.

    Binding to an independently known network identity requires the optional
    expected_network_sha256; the certificate's own hash is not authentication.
    """
    proof = object_with(certificate, {"schema", "network", "network_sha256",
                                      "atomic_cells", "semantic_atlas", "semantic_sha256"}, "certificate")
    require(proof["schema"] == SCHEMA, "unsupported certificate schema")
    network = parse_network(proof["network"])
    net_hash = hash_bytes(proof["network"])
    require(type(proof["network_sha256"]) is str and _HEX.fullmatch(proof["network_sha256"]) is not None
            and net_hash == proof["network_sha256"], "network digest mismatch")
    if expected_network_sha256 is not None:
        require(type(expected_network_sha256) is str and net_hash == expected_network_sha256,
                "independent expected network identity mismatch")
    cells = proof["atomic_cells"]
    require(type(max_cells) is int and 0 < max_cells <= 100000 and
            type(max_scalar_ops) is int and max_scalar_ops > 0, "invalid verifier budget")
    require(type(cells) is list and 0 < len(cells) <= max_cells, "certificate cell budget or empty cover")
    scalar_ops = len(cells) * sum(len(weights) * len(weights[0]) for _, weights, _ in network)
    require(scalar_ops <= max_scalar_ops, "scalar work budget exceeded")
    out_width = len(network[-1][1])
    parsed = [cell(record, out_width) for record in cells]
    require(parsed[0][0] is None and parsed[-1][1] is None, "cover must span full real line")
    for index, (left, right, declared) in enumerate(parsed):
        require(left is None or right is None or left < right, "empty or inverted interval")
        if index:
            prior_right = parsed[index - 1][1]
            require(prior_right is not None and left is not None and prior_right == left,
                    "missing, overlapping or unbounded interior cell")
        witness = sample(left, right)
        active: tuple[tuple[Fraction, Fraction], ...] = ((Fraction(1), Fraction(0)),)
        for activation, weights, bias in network:
            pre = tuple((sum((w * affine[0] for w, affine in zip(row, active)), Fraction(0)),
                         b + sum((w * affine[1] for w, affine in zip(row, active)), Fraction(0)))
                        for row, b in zip(weights, bias))
            if activation == "linear":
                active = pre
                continue
            next_active = []
            for slope, offset in pre:
                if slope:
                    root = -offset / slope
                    require(not ((left is None or left < root) and (right is None or root < right)),
                            "undisclosed ReLU sign transition inside cell")
                next_active.append((slope, offset) if slope * witness + offset > 0 else
                                   (Fraction(0), Fraction(0)))
            active = tuple(next_active)
        require(active == declared, f"incorrect affine law in cell {index}")
        if index:
            previous = parsed[index - 1][2]
            join = left
            require(all(a * join + b == c * join + d for (a, b), (c, d) in zip(previous, active)),
                    "discontinuous adjacent output expressions")

    # Reduce the verified cover to the unique maximal affine output partition.
    merged = []
    for left, right, outputs in parsed:
        if merged and merged[-1][1] == left and merged[-1][2] == outputs:
            merged[-1] = (merged[-1][0], right, outputs)
        else:
            merged.append((left, right, outputs))
    normalized = [{"left": "-inf" if left is None else str(left),
                   "right": "+inf" if right is None else str(right),
                   "affines": [[str(slope), str(offset)] for slope, offset in outputs]}
                  for left, right, outputs in merged]
    require(type(proof["semantic_atlas"]) is list and proof["semantic_atlas"] == normalized,
            "incorrect or noncanonical semantic atlas")
    # COE-001 canonical atlas digest uses same serialization, independently reconstructed.
    require(type(proof["semantic_sha256"]) is str and _HEX.fullmatch(proof["semantic_sha256"]) is not None
            and hash_bytes(normalized) == proof["semantic_sha256"], "semantic atlas digest mismatch")
    return {"status": "verified", "network_sha256": net_hash,
            "semantic_sha256": hash_bytes(normalized),
            "atomic_cells_checked": len(parsed), "semantic_regions": len(merged),
            "input_domain": "all-real-scalar-input", "arithmetic": "exact-rational"}


def verify_json_bytes(raw: bytes, **kwargs: object) -> dict[str, object]:
    """Reject JSON duplicate keys and noncanonical JSON file encodings."""
    require(type(raw) is bytes and 0 < len(raw) <= 8 * 1024 * 1024, "invalid certificate bytes")
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for k, value in pairs:
            require(k not in result, "duplicate JSON object key")
            result[k] = value
        return result
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                             parse_constant=lambda _: require(False, "nonfinite JSON value"))
    except (ValueError, UnicodeError) as exc:
        raise CertificateError("invalid JSON certificate bytes") from exc
    require(json_bytes(decoded) + b"\n" == raw, "certificate file not canonical JSON plus one LF")
    return verify_certificate(decoded, **kwargs)
