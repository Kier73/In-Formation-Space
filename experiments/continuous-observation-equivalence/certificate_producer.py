"""COE-002 producer: construct a portable activation-cell certificate.

The certificate checker is a separate standalone implementation, not imported
here. The producer's data are untrusted until independently checked.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from continuous_equivalence import Layer, Region, atlas, compact, fingerprint, token

SCHEMA = "in-formation-space.coe002.activation-cell-certificate/0.1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def network_description(layers: tuple[Layer, ...]) -> dict[str, object]:
    return {"layers": [{"activation": item.activation,
                        "weights": [[token(weight) for weight in row] for row in item.weights],
                        "bias": [token(bias) for bias in item.bias]}
                       for item in layers]}


def cell_description(region: Region) -> dict[str, object]:
    return {"left": token(region.left, infinite="-inf"),
            "right": token(region.right, infinite="+inf"),
            "affines": [[token(f.slope), token(f.offset)] for f in region.output]}


def produce(layers: tuple[Layer, ...], *, max_cells: int = 4096) -> dict[str, object]:
    # Retain even hidden splits canceled by the final layer. A verifier cannot
    # safely check only the compact output atlas for internal activation signs.
    cells = atlas(layers, max_regions=max_cells, retain_activation_cells=True)
    semantic = tuple(compact(list(cells)))
    network = network_description(layers)
    return {"schema": SCHEMA, "network": network,
            "network_sha256": sha256(canonical_bytes(network)).hexdigest(),
            "atomic_cells": [cell_description(r) for r in cells],
            "semantic_atlas": [cell_description(r) for r in semantic],
            "semantic_sha256": fingerprint(semantic)}
