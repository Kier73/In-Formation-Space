"""RCG-001 exact path-mass attribution for query-selected real connectome circuits.

These are algebraic mediators under the declared unsigned count transfer law,
not real physiological causal interventions or spikes.
"""
from __future__ import annotations
from collections import defaultdict
from fractions import Fraction
from typing import Any
from connectome_ground import ConnectomeGround, ConnectomeRefused, Query, sha, value_text


def attribute(ground: ConnectomeGround, plan: dict[str, Any], receipt: dict[str, Any],
              *, top_n: int = 6) -> dict[str, Any]:
    if type(top_n) is not int or not (1 <= top_n <= 30):
        raise ConnectomeRefused('attribution top_n must be in 1..30')
    total = ground.verify(plan, receipt, whole_graph=True)
    q = Query(**plan['query'])
    edges = [[] for _ in range(q.steps)]
    for stage, src, dst, count, outgoing in plan['layered_edges']:
        edges[stage].append((src, dst, Fraction(count, outgoing)))
    forward = [{q.source: Fraction(1)}]
    for layer in edges:
        nxt = defaultdict(Fraction)
        for src, dst, weight in layer:
            nxt[dst] += forward[-1].get(src, Fraction(0)) * weight
        forward.append(dict(nxt))
    backward = [{} for _ in range(q.steps + 1)]
    backward[-1] = {q.target: Fraction(1)}
    for i in reversed(range(q.steps)):
        prev = defaultdict(Fraction)
        for src, dst, weight in edges[i]:
            prev[src] += backward[i + 1].get(dst, Fraction(0)) * weight
        backward[i] = dict(prev)
    if forward[-1].get(q.target, Fraction(0)) != total or backward[0].get(q.source, Fraction(0)) != total:
        raise ConnectomeRefused('forward/backward exact path-mass reconstruction disagrees')
    mediators = []
    for i in range(1, q.steps):
        parts = [(node, forward[i].get(node, Fraction(0)) * backward[i].get(node, Fraction(0)))
                 for node in plan['layered_nodes'][i]]
        if sum((mass for _, mass in parts), Fraction(0)) != total:
            raise ConnectomeRefused('stage attribution fails conservation')
        parts.sort(key=lambda item: (-item[1], item[0]))
        shown = parts[:top_n]
        omitted = sum((mass for _, mass in parts[top_n:]), Fraction(0))
        mediators.append({
            'stage': i, 'total_paths_mass': value_text(total),
            'ranked_node_count': len(parts),
            'most_contributing': [
                {'node': node, 'mass': value_text(mass),
                 'fraction': value_text(mass / total) if total else '0/1'}
                for node, mass in shown],
            'omitted_mass': value_text(omitted)})
    body = {'schema': 'ifs.real-connectome-ground.attribution.v1',
            'ground': ground.fingerprint, 'plan_digest': plan['digest'],
            'observation_digest': receipt['digest'], 'total': value_text(total),
            'stages': mediators,
            'interpretation': 'exact structural transfer fraction, not biological firing or causal intervention'}
    return {**body, 'digest': sha(body)}
