"""RCG-003: map synthetic learned path-cost coefficients to EXISTING PNF Block.

A tiny, exact-dyadic ReLU neural realization of a learned *cost law*; it does
not change RCG-001 semantics, permissions, host admission or transport.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping

import numpy as np

from connectome_ground import ConnectomeGround, sha
from adaptive_fabric.fabric_policy import (
    SCHEMA, FEATURES, FabricRefused, HostPath, Workload,
    candidates, predict,
)
from experiments.procedural_neural_formation.formation import Block, evaluate, widen


def compiled_policy_block(ground: ConnectomeGround, model: Mapping[str, Any]):
    """Four nonnegative measured features to six synthetic route-cost outputs.

    Uses existing PNF Block representation. The hidden identity ReLU cells are
    1:1 on the declared nonnegative feature domain. Only coefficients exactly
    representable as float32 are accepted; this domain's dyadic simulator fits.
    """
    routes = tuple(p.key for p in candidates())
    if model.get('ground') != ground.fingerprint or model.get('schema') != SCHEMA + '.model.v1':
        raise FabricRefused('cannot compile a cost policy for a different source Ground')
    params = np.empty((len(FEATURES), len(routes)), dtype=np.float32)
    for j, route in enumerate(routes):
        coefficients = model['coefficients'].get(route)
        if not isinstance(coefficients, list) or len(coefficients) != len(FEATURES):
            raise FabricRefused('unavailable trained route cost coefficients')
        for i, token in enumerate(coefficients):
            try:
                rational = Fraction(token)
                coefficient = np.float32(float(rational))
            except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
                raise FabricRefused('cannot encode synthetic cost coefficient') from exc
            if not np.isfinite(coefficient) or Fraction.from_float(float(coefficient)) != rational:
                raise FabricRefused('exact synthesized neural weights require dyadic F32 representation')
            params[i, j] = coefficient
    block = Block(np.eye(4, dtype=np.float32), np.zeros(4, dtype=np.float32),
                  params, np.zeros(len(routes), dtype=np.float32), 'relu')
    definition = block.descriptor()
    manifest = {'schema': SCHEMA + '.pnf-cost-neural-ground.v1',
                'source_ground': ground.fingerprint, 'trained_cost_model': model['digest'],
                'pnf_descriptor': definition, 'feature_order': list(FEATURES),
                'output_routes': list(routes),
                'valid_domain': 'all features are nonnegative integer quantities',
                'interpretation': 'exact synthetic path-cost predictor; not a neural language model'}
    return block, {**manifest, 'digest': sha(manifest)}


def verify_compiled(ground: ConnectomeGround, model: Mapping[str, Any],
                    block: Block, manifest: dict[str, Any],
                    workload: Workload, *, queue: int = 12) -> None:
    from adaptive_fabric.fabric_policy import canonical_hash
    expected, record = compiled_policy_block(ground, model)
    if record != manifest or block.descriptor() != expected.descriptor() or \
            canonical_hash({k: v for k, v in manifest.items() if k != 'digest'}) != manifest.get('digest'):
        raise FabricRefused('PNF policy tensor or source binding has changed')
    for column, route in enumerate(candidates()):
        features = workload.feature(route, queue)
        observed = evaluate(block, np.asarray([features], dtype=np.float64))[0, column]
        exact = predict(model, ground, workload, route, queue)
        if Fraction.from_float(float(observed)) != exact:
            raise FabricRefused('PNF ReLU neural output differs from exact synthetic Ground cost')


def widen_and_verify(block: Block, workload: Workload, *, sample_route: HostPath,
                     queue: int = 9) -> dict[str, Any]:
    child, certificate = widen(block, 7)
    x = np.asarray([workload.feature(sample_route, queue)], dtype=np.float64)
    left, right = evaluate(block, x), evaluate(child, x)
    if not np.array_equal(left, right):
        raise FabricRefused('widened procedural policy does not preserve original cost law')
    return {'parent': block.descriptor()['digest'],
            'widened': child.descriptor()['digest'],
            'certificate': certificate['schema'],
            'agreement': True,
            'warning': 'widening preserves this function, it does not increase learned information'}
