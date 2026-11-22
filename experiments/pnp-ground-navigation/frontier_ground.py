"""PNG-001: exact #SAT via an observer-interface (frontier) ground.

This is ordinary variable elimination over nonnegative-integer factors, not
an algorithm for unrestricted polynomial-time SAT. The induced factor scopes
are the measured cost of the representation.
"""
from dataclasses import dataclass
from itertools import combinations
from time import perf_counter
import json
import random
import sys


@dataclass(frozen=True)
class Factor:
    scope: tuple[int, ...]
    values: tuple[int, ...]

    def at(self, assignment):
        pos = sum((int(bool(assignment[v])) << i) for i, v in enumerate(self.scope))
        return self.values[pos]


def clause_factor(clause):
    scope = tuple(sorted({abs(x) for x in clause}))
    if not scope or any(v == 0 for v in scope):
        raise ValueError('clauses must have nonzero variable IDs')
    values = tuple(int(any(bool(mask & (1 << scope.index(abs(lit)))) == (lit > 0)
                          for lit in clause)) for mask in range(1 << len(scope)))
    return Factor(scope, values)


def verify_assignment(clauses, witness):
    return all(any((bool(witness[abs(lit)]) == (lit > 0)) for lit in clause)
               for clause in clauses)


def min_fill_order(clauses, n):
    graph = {v: set() for v in range(1, n + 1)}
    for clause in clauses:
        scope = {abs(l) for l in clause}
        for a in scope:
            graph[a].update(scope - {a})
    order = []
    while graph:
        def cost(v):
            ns = graph[v]
            fill = sum(b not in graph[a] for a, b in combinations(sorted(ns), 2))
            return fill, len(ns), v
        pivot = min(graph, key=cost)
        neighbors = sorted(graph[pivot])
        for a, b in combinations(neighbors, 2):
            graph[a].add(b)
            graph[b].add(a)
        for a in neighbors:
            graph[a].discard(pivot)
        del graph[pivot]
        order.append(pivot)
    return order


def solve(clauses, n):
    """Return exact count, original-variable witness, and fully billed cost ledger."""
    if n < 1:
        raise ValueError('n must be positive')
    clauses = [tuple(c) for c in clauses]
    if any(not c or any(abs(x) > n or x == 0 for x in c) for c in clauses):
        raise ValueError('invalid literal or empty clause')
    factors = [clause_factor(c) for c in clauses]
    order = min_fill_order(clauses, n)
    history = []
    ledger = {'n': n, 'clauses': len(clauses), 'max_scope': 0,
              'factor_lookups': 0, 'projected_entries': 0,
              'initial_table_entries': sum(len(f.values) for f in factors),
              'elimination_order': order}
    start = perf_counter()
    for pivot in order:
        bucket = [f for f in factors if pivot in f.scope]
        factors = [f for f in factors if pivot not in f.scope]
        scope = tuple(sorted({v for f in bucket for v in f.scope} - {pivot}))
        ledger['max_scope'] = max(ledger['max_scope'], len(scope))
        ledger['projected_entries'] += 1 << len(scope)
        values = []
        for mask in range(1 << len(scope)):
            a = {v: bool(mask & (1 << i)) for i, v in enumerate(scope)}
            total = 0
            for bit in (False, True):
                a[pivot] = bit
                product = 1
                for factor in bucket:
                    ledger['factor_lookups'] += 1
                    product *= factor.at(a)
                    if product == 0:
                        break
                total += product
            values.append(total)
        factors.append(Factor(scope, tuple(values)))
        history.append((pivot, bucket))
    count = 1
    for f in factors:
        count *= f.values[0]
    witness = None
    if count:
        a = {}
        for pivot, bucket in reversed(history):
            for bit in (False, True):
                a[pivot] = bit
                if all(f.at(a) > 0 for f in bucket):
                    break
            else:
                raise AssertionError('invalid reconstruction')
        witness = {v: int(a[v]) for v in range(1, n + 1)}
        assert verify_assignment(clauses, witness)
    ledger['elapsed_ms'] = round((perf_counter() - start) * 1000, 3)
    return count, witness, ledger


def brute_count(clauses, n):
    count = 0
    for bits in range(1 << n):
        assignment = {v: (bits >> (v - 1)) & 1 for v in range(1, n + 1)}
        count += verify_assignment(clauses, assignment)
    return count


def chain(n, contradictory=False):
    clauses = [(1,)]
    for i in range(1, n):
        clauses.extend([(-i, i + 1), (i, -(i + 1))])
    if contradictory:
        clauses.append((-n,))
    return clauses


def random_3cnf(n, count, seed):
    rng = random.Random(seed)
    clauses = []
    for _ in range(count):
        vs = rng.sample(range(1, n + 1), 3)
        clauses.append(tuple(v if rng.getrandbits(1) else -v for v in vs))
    return clauses


def campaign():
    cases = [('chain-96-sat', chain(96), 96),
             ('chain-96-unsat', chain(96, True), 96),
             ('random-12', random_3cnf(12, 48, 73), 12),
             ('random-16', random_3cnf(16, 64, 73), 16),
             ('xor-contradiction', [(1, 2), (1, -2), (-1, 2), (-1, -2)], 2)]
    results = []
    for name, clauses, n in cases:
        result, witness, ledger = solve(clauses, n)
        if n <= 16:
            assert result == brute_count(clauses, n)
        results.append({'case': name, 'solutions': result,
                        'witness_verified': witness is not None and verify_assignment(clauses, witness),
                        **ledger})
    return results


if __name__ == '__main__':
    print(json.dumps(campaign(), indent=2))
