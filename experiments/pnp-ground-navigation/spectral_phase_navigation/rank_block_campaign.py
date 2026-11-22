#!/usr/bin/env python3
"""SPN-004 seeded rank-budget comparison against SPN-002 and SPN-003."""
import json
from random import Random

from spectral_receipts import produce_receipt
from phase_cycle_bounds import produce_cycle_receipt
from rank_block_bounds import produce_rank_receipt
from test_rank_block_bounds import fano_blocks
from walsh_phase_navigation_probe import violated_count


def run_campaign(seed=73176, budget=256):
    rng = Random(seed)
    random_cases = []
    for n, m, samples in ((8, 34, 30), (10, 43, 30), (12, 51, 30)):
        row = {'n': n, 'm': m, 'samples': samples,
               'sat': 0, 'unsat': 0, 'unknown': 0,
               'legacy_nodes': 0, 'cycle_nodes': 0, 'rank3_nodes': 0,
               'rank3_better_than_cycle': 0,
               'rank3_worse_than_cycle': 0, 'rank3_bound_leaves': 0}
        for _ in range(samples):
            clauses = []
            for _j in range(m):
                vs = tuple(sorted(rng.sample(range(n), 3)))
                forbidden = tuple(rng.randrange(2) for _k in range(3))
                clauses.append((vs, forbidden))
            legacy = produce_receipt(clauses, n, budget=budget)
            cycle = produce_cycle_receipt(clauses, n, budget=budget)
            rank = produce_rank_receipt(clauses, n, budget=budget, rank_cap=3)
            answer = 'SAT' if any(violated_count(clauses, x) == 0 for x in range(1 << n)) else 'UNSAT'
            assert legacy['result'] == cycle['result'] == rank['result'] == answer
            assert rank['producer_nodes_visited'] <= cycle['producer_nodes_visited']
            row[answer.lower()] += 1
            row['legacy_nodes'] += legacy['producer_nodes_visited']
            row['cycle_nodes'] += cycle['producer_nodes_visited']
            row['rank3_nodes'] += rank['producer_nodes_visited']
            row['rank3_better_than_cycle'] += int(rank['producer_nodes_visited'] < cycle['producer_nodes_visited'])
            row['rank3_worse_than_cycle'] += int(rank['producer_nodes_visited'] > cycle['producer_nodes_visited'])
            row['rank3_bound_leaves'] += rank['producer_bound_leaves']
        random_cases.append(row)

    structured = []
    for count in (1, 2, 4, 8, 16, 32):
        clauses, n = fano_blocks(count)
        cycle = produce_cycle_receipt(clauses, n, budget=budget)
        rank = produce_rank_receipt(clauses, n, budget=budget, rank_cap=3)
        assert rank['result'] == 'UNSAT' and rank['producer_nodes_visited'] == 1
        structured.append({'blocks': count, 'n': n, 'm': len(clauses),
                           'cycle_result': cycle['result'],
                           'cycle_nodes': cycle['producer_nodes_visited'],
                           'rank_result': rank['result'],
                           'rank_nodes': rank['producer_nodes_visited'],
                           'rank_ground_bound': rank['proof']['bound'],
                           'rank_block_count': len(rank['proof']['blocks']),
                           'rank_receipt_bytes': len(json.dumps(rank, sort_keys=True,
                                                              separators=(',', ':')))})
    return {'seed': seed, 'budget': budget, 'random_3sat': random_cases,
            'structured_fano_rank3_blocks': structured}


if __name__ == '__main__':
    print(json.dumps(run_campaign(), indent=2))