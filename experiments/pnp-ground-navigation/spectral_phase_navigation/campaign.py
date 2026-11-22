"""Reproducible SPN-002 bounded-proof campaign, standard library only."""
from __future__ import annotations
import json
from random import Random
from walsh_phase_navigation_probe import violated_count
from spectral_receipts import produce_receipt, verify_receipt


def campaign(n_values=(8, 10, 12), samples=40, budget=256, seed=20261121):
    rng = Random(seed)
    rows = []
    for n in n_values:
        m = round(4.27 * n)
        counts = {'SAT': 0, 'UNSAT': 0, 'UNKNOWN': 0}
        ground = {'SAT': 0, 'UNSAT': 0}
        visits = []
        for _ in range(samples):
            clauses = [(tuple(sorted(rng.sample(range(n), 3))),
                        tuple(rng.randrange(2) for _ in range(3))) for __ in range(m)]
            receipt = produce_receipt(clauses, n, budget=budget)
            status = verify_receipt(clauses, n, receipt)
            actual = 'SAT' if any(violated_count(clauses, x) == 0
                                  for x in range(1 << n)) else 'UNSAT'
            ground[actual] += 1
            counts[status] += 1
            if status != 'UNKNOWN':
                assert status == actual
            visits.append(receipt['producer_nodes_visited'])
        rows.append({'n': n, 'm': m, 'samples': samples, 'budget': budget,
                     'ground_truth': ground, 'certificates': counts,
                     'mean_nodes_visited': round(sum(visits) / len(visits), 2),
                     'max_nodes_visited': max(visits)})
    return rows


if __name__ == '__main__':
    print(json.dumps(campaign(), indent=2))