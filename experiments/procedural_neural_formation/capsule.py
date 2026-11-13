"""PNF-002: portable, non-executable binary32 model-pair capsules.

The receiver trusts externally supplied identities, never identities extracted
from the capsule itself. No pickle, executable model code or compression is used.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct

import numpy as np

from .formation import Block, FormationError, KEYS, MAX_ELEMENTS, digest
from .verification import scalar_oracle, verify_conservation

MAGIC = b"IFSPNF02"
PREFIX = struct.Struct("<8sI")
MAX_HEADER = 256 * 1024
MAX_CAPSULE = 64 * 1024 * 1024
SCHEMA = "ifs.portable-neural-pair.v1"


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FormationError("duplicate JSON key")
        result[key] = value
    return result


def _identity(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise FormationError("expected identity must be a lowercase SHA-256")
    return value


def pack_pair(source: Block, generated: Block, certificate: dict, provenance: dict,
              probes: list[list[float]]) -> tuple[bytes, dict]:
    """Export both explicit parameter realizations plus their stated relationship."""
    verify_conservation(source, generated, certificate)
    header = {"schema": SCHEMA, "source": source.descriptor(),
              "generated": generated.descriptor(), "certificate": certificate,
              "source_provenance": provenance, "generated_origin": "constructed-by-dyadic-widening",
              "probes": probes}
    raw_header = canonical(header)
    size = PREFIX.size + len(raw_header) + sum(getattr(block, key).nbytes
        for block in (source, generated) for key in KEYS)
    if len(raw_header) > MAX_HEADER or size > MAX_CAPSULE:
        raise FormationError("capsule budget exceeded")
    payload = b"".join(np.ascontiguousarray(getattr(block, key), dtype="<f4").tobytes()
                       for block in (source, generated) for key in KEYS)
    raw = PREFIX.pack(MAGIC, len(raw_header)) + raw_header + payload
    policy = {"capsule_sha256": sha(raw), "capsule_bytes": len(raw),
              "source_digest": header["source"]["digest"],
              "generated_digest": header["generated"]["digest"]}
    # Exercise the same strict decoder before exposing an export.
    unpack_pair(raw, policy)
    return raw, policy


def unpack_pair(raw: bytes, policy: dict) -> tuple[Block, Block, dict]:
    """Reconstruct only after structural/size/digest preflight against external pins."""
    if not isinstance(raw, bytes) or not PREFIX.size < len(raw) <= MAX_CAPSULE:
        raise FormationError("invalid capsule size")
    if type(policy.get("capsule_bytes")) is not int or policy["capsule_bytes"] != len(raw):
        raise FormationError("capsule byte count differs from receiver policy")
    if sha(raw) != _identity(policy.get("capsule_sha256")):
        raise FormationError("capsule identity differs from receiver policy")
    magic, header_length = PREFIX.unpack_from(raw)
    if magic != MAGIC or not 0 < header_length <= MAX_HEADER or PREFIX.size + header_length >= len(raw):
        raise FormationError("invalid capsule prefix")
    encoded = raw[PREFIX.size:PREFIX.size + header_length]
    try:
        header = json.loads(encoded, object_pairs_hook=_unique,
                            parse_constant=lambda value: (_ for _ in ()).throw(FormationError("nonfinite JSON")))
        if canonical(header) != encoded:
            raise FormationError("header is not canonical JSON")
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise FormationError("invalid capsule JSON") from exc
    fields = {"schema", "source", "generated", "certificate", "source_provenance", "generated_origin", "probes"}
    if not isinstance(header, dict) or set(header) != fields or header["schema"] != SCHEMA:
        raise FormationError("unsupported capsule fields/schema")
    if header["generated_origin"] != "constructed-by-dyadic-widening":
        raise FormationError("generated provenance must remain distinct from observation")
    if not isinstance(header["source_provenance"], dict) or header["source_provenance"].get("kind") not in (
        "procedural", "observed-selected-huggingface-payloads"):
        raise FormationError("unsupported source provenance kind")
    layouts = []
    total = 0
    for label in ("source", "generated"):
        descriptor = header[label]
        if not isinstance(descriptor, dict) or set(descriptor) != {"schema", "dimensions", "activation", "tensors", "digest"}:
            raise FormationError("invalid block descriptor")
        dims = descriptor["dimensions"]
        if not isinstance(dims, list) or len(dims) != 3 or any(type(n) is not int or n <= 0 for n in dims):
            raise FormationError("invalid model dimensions")
        i, h, o = dims
        shapes = [(i, h), (h,), (h, o), (o,)]
        count = sum(math.prod(s) for s in shapes)
        if count > MAX_ELEMENTS:
            raise FormationError("parameter element budget exceeded")
        total += 4 * count
        if descriptor["schema"] != "ifs.feed-forward-block.v1" or descriptor["activation"] not in ("relu", "gelu_tanh"):
            raise FormationError("unsupported model/activation")
        tensors = descriptor["tensors"]
        if not isinstance(tensors, dict) or set(tensors) != set(KEYS):
            raise FormationError("invalid tensor catalog")
        for key, shape in zip(KEYS, shapes):
            t = tensors[key]
            if (not isinstance(t, dict) or set(t) != {"shape", "dtype", "sha256"} or
                not isinstance(t["shape"], list) or any(type(n) is not int for n in t["shape"]) or
                t["shape"] != list(shape) or t["dtype"] != "F32"):
                raise FormationError("invalid typed tensor layout")
            _identity(t["sha256"])
        if descriptor["digest"] != _identity(policy.get(label + "_digest")):
            raise FormationError("model identity differs from receiver policy")
        if digest({k: v for k, v in descriptor.items() if k != "digest"}) != descriptor["digest"]:
            raise FormationError("model descriptor digest mismatch")
        layouts.append(shapes)
    cursor = PREFIX.size + header_length
    if cursor + total != len(raw):
        raise FormationError("truncated or trailing capsule bytes")
    # Validate small probe arrays and work before any tensor allocation.
    probes = header["probes"]
    inputs, hidden, outputs = header["source"]["dimensions"]
    if (not isinstance(probes, list) or not 1 <= len(probes) <= 4 or
        any(not isinstance(row, list) or len(row) != inputs or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in row) for row in probes)):
        raise FormationError("invalid probe inputs")
    widest = max(hidden, header["generated"]["dimensions"][1])
    if len(probes) * widest * (inputs + min(outputs, 3)) > 12_000_000:
        raise FormationError("receiver numerical work budget exceeded")
    # Hash all payload spans before materializing arrays.
    spans = []
    for label, shapes in zip(("source", "generated"), layouts):
        entries = []
        for key, shape in zip(KEYS, shapes):
            length = math.prod(shape) * 4
            span = memoryview(raw)[cursor:cursor + length]
            if sha(span) != header[label]["tensors"][key]["sha256"]:
                raise FormationError("tensor payload digest mismatch")
            entries.append((cursor, length, shape))
            cursor += length
        spans.append(entries)
    blocks = []
    for label, entries in zip(("source", "generated"), spans):
        arrays = [np.frombuffer(raw, dtype="<f4", count=length // 4, offset=start).reshape(shape).astype(np.float32, copy=True)
                  for start, length, shape in entries]
        block = Block(*arrays, header[label]["activation"])
        block.validate()
        blocks.append(block)
    return blocks[0], blocks[1], header


def verify_capsule(raw: bytes, policy: dict) -> dict:
    """Receiver reconstruction and evaluation; never calls the widening constructor."""
    source, generated, header = unpack_pair(raw, policy)
    law = verify_conservation(source, generated, header["certificate"])
    outputs = source.validate()[2]
    selected = sorted({0, outputs // 2, outputs - 1})
    probes = np.asarray(header["probes"], dtype=np.float64)
    a = scalar_oracle(source, probes, selected)
    b = scalar_oracle(generated, probes, selected)
    if not np.allclose(a, b, rtol=1e-10, atol=1e-10):
        raise FormationError("receiver differential execution failed")
    return {"schema": "ifs.neural-receiver-verification.v1", "status": "verified",
            **policy, "coefficient_law": law, "source_dimensions": list(source.validate()),
            "generated_dimensions": list(generated.validate()), "activation": generated.activation,
            "output_indices": selected, "probe_count": len(probes),
            "source_outputs": a.tolist(), "generated_outputs": b.tolist(),
            "max_absolute_error": float(np.max(np.abs(a - b))),
            "source_provenance_status": "sender-declared-and-content-bound; not independently re-observed",
            "kernel_accepted": False}
