"""Reuse VGI's actual typed operator navigation as an independent COG algebra engine.

No fake substitution when vgi is missing: dedicated CI job installs the pinned
VGI package and explicitly requires these imports before running native tests.
"""
from __future__ import annotations
from capability_atlas import Affine, compile_regions


def vgi_check(map_: Affine, probes: tuple[tuple[int,int], ...]) -> dict:
    from vgi.typed_operator_navigation import (
        DenseMap, FiniteSpace, OperatorChain, TypedVector,
        homogeneous_affine_map, project_homogeneous_vector, fulfill,
        OperatorDemand, verify_receipt,
    )
    from vgi.affine import ModularAffineMap

    p = map_.p
    # Use the existing VGI ModularAffineMap + homogeneous embedding. The 3rd
    # coordinate stays 1, and every operator is a closed typed map of the same frame.
    source = ModularAffineMap(p, map_.mat, map_.bias)
    typed = homogeneous_affine_map('COG002.target', 'COG002.Fp2.plus.constant', source)
    plan = compile_regions(map_)
    factors = []
    for index, step in enumerate(reversed(plan.steps)):
        op = ModularAffineMap(p, step.transform.mat, step.transform.bias)
        factors.append(homogeneous_affine_map(f'COG002.region.{index}',
                                              'COG002.Fp2.plus.constant', op))
    chain = OperatorChain(tuple(factors))
    tests = 0
    for x in probes:
        initial = TypedVector(typed.domain, (x[0],x[1],1))
        target = project_homogeneous_vector(typed.apply(initial))
        composed = project_homogeneous_vector(chain.apply(initial))
        expected = map_.apply(x)
        if target != expected or composed != expected:
            raise ValueError('VGI typed atlas disagrees with independent algebraic Ground')
        receipt = fulfill(chain,OperatorDemand('vector',vector=initial))
        if not verify_receipt(chain,OperatorDemand('vector',vector=initial),receipt):
            raise ValueError('VGI native receipt failed semantic reconstruction')
        tests += 1
    return {'p':p,'probes':tests,'native_vgi_chain':chain.fingerprint,
            'typed_operator_count':len(plan.steps),'combined_dense_materialized':False}