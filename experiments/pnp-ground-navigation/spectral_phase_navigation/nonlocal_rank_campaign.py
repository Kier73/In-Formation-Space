#!/usr/bin/env python3
"""SPN-005: seeded comparisons and cost ledger; numbers are local measurements."""
from __future__ import annotations

from json import dumps
from random import Random
from time import perf_counter

from nonlocal_rank_grounds import (parity_cycle_cnf, produce_nonlocal_receipt,
                                   verify_nonlocal_receipt)
from rank_block_bounds import produce_rank_receipt
from walsh_phase_navigation_probe import violated_count


def campaign(seed=73176, random_budget=256, structured_budget=64):
    rng = Random(seed)
    random_cases = []
    for n, m in ((8, 34), (10, 43), (12, 51)):
        row = {'n': n, 'm': m, 'samples': 30, 'sat': 0, 'unsat': 0,
               'rank4_nodes': 0, 'rank5_nodes': 0,
               'rank5_better': 0, 'rank5_worse': 0,
               'producer_rank4_ms': 0.0, 'producer_rank5_ms': 0.0,
               'discovery_pairs': 0, 'discovery_minima': 0,
               'discovery_parity_states': 0, 'producer_truncated_nodes': 0,
               'rank5_receipt_bytes': 0}
        for _ in range(30):
            clauses = [(tuple(sorted(rng.sample(range(n), 3))),
                        tuple(rng.randrange(2) for _ in range(3)))
                       for _ in range(m)]
            answer = ('SAT' if any(violated_count(clauses, x) == 0
                                   for x in range(1 << n)) else 'UNSAT')
            started = perf_counter()
            original = produce_rank_receipt(clauses, n, budget=random_budget)
            row['producer_rank4_ms'] += (perf_counter() - started) * 1000
            started = perf_counter()
            new = produce_nonlocal_receipt(clauses, n, budget=random_budget)
            row['producer_rank5_ms'] += (perf_counter() - started) * 1000
            assert original['result'] == new['result'] == answer
            assert verify_nonlocal_receipt(clauses, n, new) == answer
            row[answer.lower()] += 1
            row['rank4_nodes'] += original['producer_nodes_visited']
            row['rank5_nodes'] += new['producer_nodes_visited']
            row['rank5_better'] += int(new['producer_nodes_visited'] < original['producer_nodes_visited'])
            row['rank5_worse'] += int(new['producer_nodes_visited'] > original['producer_nodes_visited'])
            cost = new['producer_discovery']
            row['discovery_pairs'] += cost['pairs_examined']
            row['discovery_minima'] += cost['block_minima_evaluated']
            row['discovery_parity_states'] += cost['block_parity_states_evaluated']
            row['producer_truncated_nodes'] += cost['truncated_nodes']
            row['rank5_receipt_bytes'] += len(dumps(new, sort_keys=True, separators=(',',':')))
        row['producer_rank4_ms'] = round(row['producer_rank4_ms'], 3)
        row['producer_rank5_ms'] = round(row['producer_rank5_ms'], 3)
        random_cases.append(row)
    structured = []
    for blocks in (1, 2, 4, 8, 16, 24):
        clauses, n = parity_cycle_cnf(blocks)
        started = perf_counter()
        old = produce_rank_receipt(clauses, n, budget=structured_budget)
        old_ms = round((perf_counter() - started) * 1000, 3)
        started = perf_counter()
        new = produce_nonlocal_receipt(clauses, n, budget=structured_budget)
        new_ms = round((perf_counter() - started) * 1000, 3)
        assert new['result'] == 'UNSAT' and new['producer_nodes_visited'] == 1
        assert new['proof']['bound'] == [blocks, 1]
        structured.append({'blocks':blocks, 'n':n, 'm':len(clauses),
                           'local_status':old['result'],
                           'local_nodes':old['producer_nodes_visited'],
                           'nonlocal_status':new['result'],
                           'nonlocal_nodes':new['producer_nodes_visited'],
                           'nonlocal_bound':new['proof']['bound'],
                           'nonlocal_proof_blocks':len(new['proof']['blocks']),
                           'discovery_pairs':new['producer_discovery']['pairs_examined'],
                           'discovery_parity_states':new['producer_discovery']['block_parity_states_evaluated'],
                           'local_ms':old_ms, 'nonlocal_ms':new_ms,
                           'nonlocal_receipt_bytes':len(dumps(new, sort_keys=True, separators=(',',':')))})
    return {'seed':seed,'random_budget':random_budget,
            'structured_budget':structured_budget,
            'random_3sat':random_cases,
            'strided_frustrated_parity_cycles':structured,
            'measurement_note':'One local Python run; times are illustrative, not stable cross-hardware benchmarks.'}


if __name__ == '__main__':
    print(dumps(campaign(), indent=2))
