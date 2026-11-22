"""PNG-002 reproducible campaign; optional portable source-bound receipts."""
import argparse
import json
import platform
import random
from pathlib import Path
from time import perf_counter

from algebraic_ground import (
    frontier_estimate, parity_formula, planted_dense,
    random_cubic_tseitin, solve,
)
from frontier_ground import chain, random_3cnf, solve as frontier_solve
from ground_verifier import check, digest_ground, digest_source

HERE = Path(__file__).resolve().parent


def campaign(*, receipts=False):
    pure, _, _ = planted_dense(96, 8, 22)
    mixed, _, _ = planted_dense(96, 8, 22, True)
    tseitin, tn, _ = random_cubic_tseitin(80, 7301)
    sparse = [(1, i, i + 1) for i in range(2, 25)]
    cases = [
        ('dense-96-pure-parity', pure, 96, {}),
        ('dense-96-mixed-parity-cnf', mixed, 96, {}),
        ('tseitin-120-global-unsat', tseitin, tn, {}),
        ('chain-96-structured', chain(96), 96, {}),
        ('incomplete-parity-8', parity_formula(8, [(0b1111, 1)])[:-1], 8, {}),
        ('ordinary-random-16', random_3cnf(16, 64, 73), 16, {}),
        ('narrow-fallback-25', sparse, 25, {'free_budget': 4}),
        ('random-35-budget-refusal', random_3cnf(35, 140, 73), 35,
         {'free_budget': 4, 'frontier_entry_budget': 100}),
    ]
    if receipts:
        (HERE / 'receipts').mkdir(exist_ok=True)
    out = []
    for name, clauses, n, kwargs in cases:
        result, ground = solve(clauses, n, **kwargs)
        verification_start = perf_counter()
        independent = check(clauses, n, ground, result)
        independent_ms = round((perf_counter()-verification_start)*1000, 3)
        baseline_estimate = frontier_estimate(clauses, n)
        baseline = {'min_fill_estimate': baseline_estimate, 'execution': 'not_run'}
        # Never materialize factors for a baseline predicted to exceed budget.
        if (baseline_estimate['projected_entries'] <= 200_000 and
                baseline_estimate['initial_entries'] <= 200_000):
            count, witness, ledger = frontier_solve(clauses, n)
            baseline = {'min_fill_estimate': baseline_estimate,
                        'execution': 'completed', 'count': count,
                        'factor_lookups': ledger['factor_lookups'],
                        'elapsed_ms': ledger['elapsed_ms']}
            if result['status'] != 'undetermined' and count != result['count']:
                raise AssertionError('original frontier disagrees with exact ground')
        entry = {
            'case': name, 'n': n, 'clauses': len(clauses),
            'status': result['status'], 'method': result['method'],
            'solutions': result['count'],
            'independent_verification_ms': independent_ms,
            'independent_verifier': independent,
            'ground_cost': result['ledger'], 'original_cnf_baseline': baseline,
        }
        out.append(entry)
        if receipts:
            payload = {
                'format': 'PNG-002-source-bound-ground-receipt-v1',
                'n': n, 'clauses': clauses, 'ground': ground, 'result': result,
                'source_sha256': digest_source(clauses, n),
                'ground_sha256': digest_ground(ground),
            }
            (HERE / 'receipts' / (name + '.json')).write_text(
                json.dumps(payload, indent=2) + '\n', encoding='utf8')
    return {'research_id': 'PNG-002',
            'environment': {'python': platform.python_version(),
                            'platform': platform.platform(),
                            'description': 'single-process standard-library synthetic tests'},
            'cases': out}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-results', action='store_true')
    parser.add_argument('--write-receipts', action='store_true')
    args = parser.parse_args()
    report = campaign(receipts=args.write_receipts)
    output = json.dumps(report, indent=2) + '\n'
    if args.write_results:
        (HERE / 'PNG-002-results.json').write_text(output, encoding='utf8')
    print(output)
