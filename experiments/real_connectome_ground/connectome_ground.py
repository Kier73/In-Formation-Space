"""RCG-001: source-bound exact-horizon causal subcircuits of a real connectome.

A sparse, unsigned synapse-count transfer *model*, not biological firing-rate
inference. Graph import is independent of VGI/E-CPU authority; the optional
adapter reuses native E-CPU DAG for projected stage readiness.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from collections import defaultdict
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
from typing import Any

SCHEMA = 'ifs.real-connectome-ground.v1'
SOURCE_COMMIT = 'd542a44bf2662f79e0ad23342a959a181a920877'
SOURCE_BLOB = '89ffc2a2d9e1934ddc462d51032acead5e4cfc91'
SOURCE_PATH = 'c302/data/herm_full_edgelist.csv'
SOURCE_URL = 'https://github.com/openworm/c302/blob/' + SOURCE_COMMIT + '/' + SOURCE_PATH


class ConnectomeRefused(ValueError):
    """Invalid source evidence, model intention or purported observation."""


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def value_text(x: Fraction) -> str:
    return f'{x.numerator}/{x.denominator}'


@dataclass(frozen=True, order=True)
class Synapse:
    source: str
    target: str
    kind: str
    count: int

    def __post_init__(self) -> None:
        if (type(self.source) is not str or not self.source or
                type(self.target) is not str or not self.target or
                self.kind not in ('chemical', 'electrical') or
                type(self.count) is not int or not (1 <= self.count <= 10_000_000)):
            raise ConnectomeRefused('invalid typed connectome synapse record')

    def fields(self) -> list[Any]:
        return [self.source, self.target, self.kind, self.count]


@dataclass(frozen=True)
class Query:
    source: str
    target: str
    steps: int
    kind: str = 'chemical'

    def encode(self) -> dict[str, Any]:
        return dict(source=self.source, target=self.target, steps=self.steps, kind=self.kind)


class ConnectomeGround:
    """An indexed source graph, retaining original outgoing mass across queries."""

    def __init__(self, edges: tuple[Synapse, ...], *, source_blob: str, source_id: str):
        if not edges or len(set(edges)) != len(edges):
            raise ConnectomeRefused('empty or repeated connectome edges')
        if not isinstance(source_blob, str) or len(source_blob) != 40:
            raise ConnectomeRefused('missing source Git blob identity')
        if type(source_id) is not str or not source_id:
            raise ConnectomeRefused('missing source description')
        self.edges = tuple(sorted(edges))
        self.nodes = frozenset(v for e in self.edges for v in (e.source, e.target))
        self.source_blob, self.source_id = source_blob, source_id
        self.forward = {k: defaultdict(list) for k in ('chemical', 'electrical')}
        self.reverse = {k: defaultdict(list) for k in ('chemical', 'electrical')}
        self.out_strength = {k: defaultdict(int) for k in ('chemical', 'electrical')}
        for e in self.edges:
            self.forward[e.kind][e.source].append(e)
            self.reverse[e.kind][e.target].append(e)
            self.out_strength[e.kind][e.source] += e.count
        self.fingerprint = sha({'schema': SCHEMA, 'source_id': source_id,
                                'source_blob': source_blob,
                                'edges': [e.fields() for e in self.edges]})

    @classmethod
    def from_csv(cls, raw: bytes, *, require_original: bool = True) -> 'ConnectomeGround':
        if type(raw) is not bytes:
            raise ConnectomeRefused('source must be actual byte evidence')
        git_blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
        if require_original and git_blob != SOURCE_BLOB:
            raise ConnectomeRefused('upstream OpenWorm Git blob has been altered')
        try:
            s = raw.decode('utf-8')
            reader = csv.DictReader(io.StringIO(s, newline=''), skipinitialspace=True)
            if reader.fieldnames != ['Source', 'Target', 'Weight', 'Type']:
                raise ConnectomeRefused('source columns do not match version-pinned contract')
            records = []
            for row in reader:
                if any(x is None for x in row.values()) or None in row:
                    raise ConnectomeRefused('source contains malformed CSV rows')
                src, dst, weight, kind = (row[name].strip() for name in reader.fieldnames)
                if not weight.isdecimal() or weight.startswith('0'):
                    raise ConnectomeRefused('synapse count is not canonical positive integer')
                records.append(Synapse(src, dst, kind, int(weight)))
        except (UnicodeError, csv.Error) as exc:
            raise ConnectomeRefused('cannot parse source CSV') from exc
        if require_original and (len(records) != 7379 or len({a for x in records for a in (x.source, x.target)}) != 448):
            raise ConnectomeRefused('OpenWorm source topology disagrees with declared release')
        return cls(tuple(records), source_blob=git_blob,
                   source_id=(SOURCE_COMMIT + '/' + SOURCE_PATH if require_original else 'local-fixture'))

    def _admit(self, q: Query) -> None:
        if not isinstance(q, Query) or q.source not in self.nodes or q.target not in self.nodes or \
                type(q.steps) is not int or not (1 <= q.steps <= 8) or q.kind not in ('chemical', 'electrical'):
            raise ConnectomeRefused('invalid or unavailable typed connectome observation query')

    def plan(self, q: Query, *, max_probes: int = 150_000) -> dict[str, Any]:
        """Exact time-expanded cone by forward/backward reachability intersection."""
        self._admit(q)
        fw, bw = self.forward[q.kind], self.reverse[q.kind]
        forward = [set([q.source])]
        backward = [set() for _ in range(q.steps + 1)]
        backward[-1].add(q.target)
        probes = 0
        for step in range(q.steps):
            next_nodes = set()
            for node in forward[-1]:
                for e in fw.get(node, ()):
                    next_nodes.add(e.target)
                    probes += 1
                    if probes > max_probes:
                        raise ConnectomeRefused('indexed planning probe budget exceeded')
            forward.append(next_nodes)
        for step in range(q.steps - 1, -1, -1):
            previous = set()
            for node in backward[step + 1]:
                for e in bw.get(node, ()):
                    previous.add(e.source)
                    probes += 1
                    if probes > max_probes:
                        raise ConnectomeRefused('indexed planning probe budget exceeded')
            backward[step] = previous
        cone = [sorted(forward[step] & backward[step]) for step in range(q.steps + 1)]
        links = []
        for step in range(q.steps):
            allowed = set(cone[step + 1])
            for node in cone[step]:
                for e in fw.get(node, ()):
                    if e.target in allowed:
                        # Keep source out-strength from the full Ground.
                        links.append([step, e.source, e.target, e.count,
                                      self.out_strength[q.kind][e.source]])
        body = {'schema': SCHEMA + '.cone.v1', 'ground': self.fingerprint,
                'source_blob': self.source_blob, 'query': q.encode(),
                'model': 'unsigned-outgoing-synapse-count-normalized-exact-horizon',
                'layered_nodes': cone, 'layered_edges': links,
                'index_probes': probes}
        return {**body, 'digest': sha(body)}

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Demand-realize only selected stage edges; compare to reference in verify."""
        if not isinstance(plan, dict) or type(plan.get('query')) is not dict:
            raise ConnectomeRefused('malformed intention')
        try:
            q = Query(**plan['query'])
        except (TypeError, ValueError) as exc:
            raise ConnectomeRefused('invalid intention attributes') from exc
        expected = self.plan(q)
        if canonical(plan) != canonical(expected):
            raise ConnectomeRefused('untrusted plan differs from receiver-owned Ground')
        state = {q.source: Fraction(1)}
        trace = []
        for layer in range(q.steps):
            next_state = defaultdict(Fraction)
            for stage, src, dst, weight, global_out_mass in plan['layered_edges']:
                if stage == layer:
                    next_state[dst] += state.get(src, Fraction(0)) * Fraction(weight, global_out_mass)
            state = dict(next_state)
            trace.append(sha({'layer': layer + 1,
                              'retained_state': [(node, value_text(v))
                                                 for node, v in sorted(state.items())]}))
        response = state.get(q.target, Fraction(0))
        body = {'schema': SCHEMA + '.observation.v1', 'ground': self.fingerprint,
                'plan_digest': plan['digest'], 'transfer': value_text(response),
                'trace_digests': trace, 'selected_edge_evaluations': len(plan['layered_edges']),
                'active_node_labels': len({node for stage in plan['layered_nodes'] for node in stage}),
                'layered_state_slots': sum(map(len, plan['layered_nodes'])),
                'all_graph_edge_evaluations_reference': q.steps * sum(e.kind == q.kind for e in self.edges),
                'is_biological_firing_prediction': False}
        return {**body, 'digest': sha(body)}

    def independent_whole_graph(self, q: Query) -> Fraction:
        """Independent unpruned edge-streaming reference; no cone index."""
        self._admit(q)
        total = defaultdict(int)
        for e in self.edges:
            if e.kind == q.kind:
                total[e.source] += e.count
        states = {q.source: Fraction(1)}
        for _ in range(q.steps):
            future = defaultdict(Fraction)
            for e in self.edges:
                if e.kind == q.kind and e.source in states:
                    future[e.target] += states[e.source] * Fraction(e.count, total[e.source])
            states = dict(future)
        return states.get(q.target, Fraction(0))

    def verify(self, plan: dict[str, Any], receipt: dict[str, Any], *, whole_graph: bool = True) -> Fraction:
        expected = self.run(plan)
        if canonical(receipt) != canonical(expected):
            raise ConnectomeRefused('observation is not reconstructable from source Ground')
        number, denominator = map(int, receipt['transfer'].split('/'))
        outcome = Fraction(number, denominator)
        if whole_graph and outcome != self.independent_whole_graph(Query(**plan['query'])):
            raise ConnectomeRefused('independent full-connectome oracle disagrees')
        return outcome


def native_ecpu_stage_dag(ground: ConnectomeGround, plan: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    """Reuse native E-CPU dependency DAG; not a host authorization claim."""
    from mailcpu.computation_dag import ComputationNode, NavigableComputationDAG
    ground.verify(plan, receipt, whole_graph=True)
    n = plan['query']['steps']
    nodes = [ComputationNode(
        f'layer.{i}', 1, 'connectome.exact_transfer', '/computational-ground/connectome',
        ground.fingerprint, (f'layer.{i-1}',) if i else (),
        {'layer': i, 'plan': plan['digest'], 'source_blob': ground.source_blob})
        for i in range(n)]
    dag = NavigableComputationDAG(nodes)
    for i in range(n):
        if [node.node_id for node in dag.ready_nodes()] != [f'layer.{i}']:
            raise ConnectomeRefused('native E-CPU DAG did not preserve causal readiness')
        dag.commit(f'layer.{i}', {'trace_digest': receipt['trace_digests'][i]})
    if not dag.is_complete:
        raise ConnectomeRefused('native causal DAG not completely committed')
    restored = NavigableComputationDAG.from_snapshot(dag.snapshot())
    if not restored.is_complete or restored.digest != dag.digest:
        raise ConnectomeRefused('native E-CPU DAG recovered a different dependency state')
    return {'dag_digest': dag.digest, 'nodes': n, 'recovered_complete': restored.is_complete}


def demonstrate(path: Path) -> list[dict[str, Any]]:
    ground = ConnectomeGround.from_csv(path.read_bytes())
    result = []
    for q in (Query('ASHL', 'AVAL', 3), Query('ASER', 'AVBL', 3),
              Query('AWCL', 'AIYL', 2), Query('ASHL', 'AVAR', 3)):
        plan = ground.plan(q)
        receipt = ground.run(plan)
        ground.verify(plan, receipt)
        result.append({'query': q.encode(), 'transfer': receipt['transfer'],
                       'selected_nodes': receipt['active_node_labels'],
                       'selected_stage_edges': receipt['selected_edge_evaluations'],
                       'full_reference_edges': receipt['all_graph_edge_evaluations_reference'],
                       'topology_index_probes': plan['index_probes'],
                       'ground_digest': ground.fingerprint})
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(__file__).parent / 'data' / 'herm_full_edgelist.csv')
    args = parser.parse_args()
    print(json.dumps(demonstrate(args.source), indent=2))
