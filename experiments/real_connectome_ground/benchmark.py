"""RCG-001: measure source indexing, query navigation and realization separately.

This is not a hardware-independent execution benchmark; no timing thresholds.
"""
from __future__ import annotations
import argparse
import json
import statistics
import time
from pathlib import Path
from connectome_ground import ConnectomeGround, Query, value_text


def benchmark_query(ground: ConnectomeGround, q: Query, *, repeats: int = 5) -> dict:
    if type(repeats) is not int or not (1 <= repeats <= 30):
        raise ValueError('repeats must be in 1..30')
    plan = ground.plan(q)
    receipt = ground.run(plan)
    exact_reference = ground.independent_whole_graph(q)
    assert ground.verify(plan, receipt) == exact_reference
    measures = {'navigate_ns': [], 'realize_ns': [], 'whole_reference_ns': []}
    for _ in range(repeats):
        start = time.perf_counter_ns()
        current_plan = ground.plan(q)
        measures['navigate_ns'].append(time.perf_counter_ns() - start)
        assert current_plan == plan
        start = time.perf_counter_ns()
        current_receipt = ground.run(plan)
        measures['realize_ns'].append(time.perf_counter_ns() - start)
        assert current_receipt == receipt
        start = time.perf_counter_ns()
        reference = ground.independent_whole_graph(q)
        measures['whole_reference_ns'].append(time.perf_counter_ns() - start)
        assert reference == exact_reference
    return {
        'query': q.encode(), 'ground': ground.fingerprint,
        'transfer': value_text(exact_reference),
        'selected_stage_edges': receipt['selected_edge_evaluations'],
        'whole_reference_stage_edge_visits': receipt['all_graph_edge_evaluations_reference'],
        'topology_index_probes': plan['index_probes'],
        'numerically_realized_node_labels': receipt['active_node_labels'],
        'median_ns': {key: int(statistics.median(samples)) for key, samples in measures.items()},
        'samples_ns': measures, 'repeats': repeats,
        'caveat': 'single-host Python; excludes index construction, verification and network transmission from per-query samples',
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(__file__).parent/'data'/'herm_full_edgelist.csv')
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    start = time.perf_counter_ns()
    ground = ConnectomeGround.from_csv(args.source.read_bytes())
    index_ns = time.perf_counter_ns() - start
    items = [benchmark_query(ground, q, repeats=args.repeats) for q in (
        Query('ASHL','AVAL',3),Query('ASER','AVBL',3),Query('AWCL','AIYL',2))]
    print(json.dumps({
        'source_blob': ground.source_blob, 'indexed_labels': len(ground.nodes),
        'indexed_edges': len(ground.edges), 'index_build_ns': index_ns,
        'queries': items,
        'caveat': 'whole_reference_ns measures an independent full-graph pass, not a required step on the production path',
    }, indent=2))

if __name__ == '__main__':
    main()
