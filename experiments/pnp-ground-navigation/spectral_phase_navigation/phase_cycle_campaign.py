#!/usr/bin/env python3
"""Reproducible SPN-003 comparison: same instances, exact bounded receipts."""
import json
from random import Random

from phase_cycle_bounds import produce_cycle_receipt, triangle_bound
from spectral_receipts import produce_receipt
from walsh_phase_navigation_probe import spectral_coefficients, violated_count
from test_phase_cycle_bounds import frustrated_blocks


def run_campaign(seed=73176, budget=256):
    rng = Random(seed)
    rows = []
    for n, m, samples in [(8, 34, 30), (10, 43, 30), (12, 51, 30)]:
        totals = {'n': n, 'm': m, 'samples': samples,
                  'sat': 0, 'unsat': 0, 'unknown': 0,
                  'legacy_nodes': 0, 'cycle_nodes': 0,
                  'cycle_nodes_less': 0, 'cycle_nodes_equal': 0,
                  'cycle_nodes_more': 0, 'improved_unsat': 0,
                  'cycle_positive_leaves': 0,
                  'root_phase_correction_positive': 0}
        for _ in range(samples):
            clauses = []
            for _j in range(m):
                vs = tuple(sorted(rng.sample(range(n), 3)))
                forbidden = tuple(rng.randrange(2) for _k in range(3))
                clauses.append((vs, forbidden))
            c = spectral_coefficients(clauses)
            legacy_lower = c[0] - sum(abs(a) for s, a in c.items() if s)
            phase_lower, _ = triangle_bound(c)
            totals['root_phase_correction_positive'] += int(phase_lower > legacy_lower)
            old = produce_receipt(clauses, n, budget=budget)
            new = produce_cycle_receipt(clauses, n, budget=budget)
            sat = any(violated_count(clauses, x) == 0 for x in range(1 << n))
            expected = 'SAT' if sat else 'UNSAT'
            assert old['result'] == new['result'] == expected
            totals[expected.lower()] += 1
            old_nodes, new_nodes = old['producer_nodes_visited'], new['producer_nodes_visited']
            totals['legacy_nodes'] += old_nodes
            totals['cycle_nodes'] += new_nodes
            totals['cycle_positive_leaves'] += new['producer_cycle_bound_leaves']
            totals['cycle_nodes_less'] += int(new_nodes < old_nodes)
            totals['cycle_nodes_equal'] += int(new_nodes == old_nodes)
            totals['cycle_nodes_more'] += int(new_nodes > old_nodes)
            totals['improved_unsat'] += int(not sat and new_nodes < old_nodes)
        rows.append(totals)
    family = []
    for blocks in (1, 2, 4, 8, 12, 16, 32):
        clauses, n = frustrated_blocks(blocks)
        old = produce_receipt(clauses, n, budget=budget)
        new = produce_cycle_receipt(clauses, n, budget=budget)
        assert new['result'] == 'UNSAT' and new['producer_nodes_visited'] == 1
        assert len(new['proof']['triangles']) == blocks
        family.append({'blocks': blocks, 'n': n, 'clauses': len(clauses),
                       'legacy_result': old['result'], 'legacy_nodes': old['producer_nodes_visited'],
                       'phase_result': new['result'], 'phase_nodes': new['producer_nodes_visited'],
                       'phase_bound': new['proof']['bound'],
                       'triangles': len(new['proof']['triangles']),
                       'receipt_bytes': len(json.dumps(new, sort_keys=True, separators=(',', ':'))),
                       })
    return {'seed': seed, 'budget': budget,
            'random_3sat': rows, 'disjoint_frustrated_blocks': family}


if __name__ == '__main__':
    print(json.dumps(run_campaign(), indent=2))