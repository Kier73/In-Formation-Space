"""PNG-002: exact CNF-to-affine observer ground with explicit accounting.

Recovers *complete* bounded-arity parity blocks from ordinary CNF, independently
re-encodes the discovered equations, applies GF(2) elimination, and either
counts decoded models, falls back to a budgeted ordinary frontier, or refuses.
This is a demonstration of established SAT/XOR techniques, not a new SAT theorem.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import product
from time import perf_counter
import json
import random

from frontier_ground import min_fill_order, solve as frontier_solve, verify_assignment


def normalize(clauses, n):
    """Canonical duplicate/tautology removal with an explicit empty-clause case."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError('n must be positive')
    result = set()
    for clause in clauses:
        c = set(clause)
        if any(not isinstance(x, int) or isinstance(x, bool) or x == 0 or abs(x) > n for x in c):
            raise ValueError('invalid literal')
        if any(-x in c for x in c):
            continue
        result.add(tuple(sorted(c, key=lambda x: (abs(x), x < 0))))
    return sorted(result, key=lambda c: (len(c), tuple((abs(x), x < 0) for x in c)))


def encode_xor(mask, rhs):
    """Canonical direct CNF encoding; only small rows are used for verification."""
    if not isinstance(mask, int) or mask <= 0 or not isinstance(rhs, int) or rhs not in (0, 1):
        raise ValueError('invalid parity equation')
    indices = [i for i in range(mask.bit_length()) if mask >> i & 1]
    return [tuple(i + 1 if not (bits >> j & 1) else -(i + 1)
                  for j, i in enumerate(indices))
            for bits in range(1 << len(indices)) if bits.bit_count() % 2 != rhs]


def compile_ground(clauses, n, max_arity=4):
    """Recognize full parity-encoding clause blocks, no heuristic implications."""
    if not 1 <= max_arity <= 5:
        raise ValueError('arity out of bounds')
    canonical = normalize(clauses, n)
    grouped = defaultdict(dict)
    for clause in canonical:
        scope = tuple(sorted(abs(x) for x in clause))
        if not 1 <= len(scope) <= max_arity:
            continue
        forbidden = sum((1 << i) for i, v in enumerate(scope) if -v in clause)
        grouped[scope][forbidden] = clause
    recovered = []
    lifted_clauses = set()
    for scope in sorted(grouped):
        patterns = grouped[scope]
        for forbidden_parity in (0, 1):
            expected = {b for b in range(1 << len(scope)) if b.bit_count() % 2 == forbidden_parity}
            if not expected.issubset(patterns):
                continue
            mask = sum(1 << (v - 1) for v in scope)
            recovered.append((mask, 1 - forbidden_parity))
            lifted_clauses.update(patterns[b] for b in expected)
    residual = [c for c in canonical if c not in lifted_clauses]
    return {
        'n': n, 'max_arity': max_arity, 'equations': recovered,
        'residual': residual, 'canonical_clause_count': len(canonical),
        'lifted_clause_count': len(lifted_clauses),
    }


def verify_compilation(clauses, n, ground):
    """Independent structural-equivalence checker, no trust in group discovery.

    Rebuilds original CNF as a set of clauses; re-encodes each claimed parity
    equation as its complete truth-table CNF and compares canonical clause sets.
    This guarantees the same satisfying assignments, not merely equisatisfiability.
    """
    try:
        if ground['n'] != n or ground['max_arity'] not in range(1, 6):
            return False
        original = set(normalize(clauses, n))
        rebuilt = set(normalize(ground['residual'], n))
        for mask, rhs in ground['equations']:
            if mask >= 1 << n or mask.bit_count() > ground['max_arity']:
                return False
            rebuilt.update(normalize(encode_xor(mask, rhs), n))
        return original == rebuilt
    except (TypeError, ValueError, KeyError, IndexError):
        return False


def eliminate(equations, n):
    """Full Gauss-Jordan over GF(2), retaining provenance for 0=1 witness."""
    rows = [[mask, rhs, 1 << i] for i, (mask, rhs) in enumerate(equations)]
    rank, xor_steps, probe_steps = 0, 0, 0
    pivots = []
    for column in range(n):
        selected = next((j for j in range(rank, len(rows)) if rows[j][0] >> column & 1), None)
        probe_steps += len(rows) - rank
        if selected is None:
            continue
        rows[rank], rows[selected] = rows[selected], rows[rank]
        for j in range(len(rows)):
            if j != rank and (rows[j][0] >> column & 1):
                rows[j][0] ^= rows[rank][0]
                rows[j][1] ^= rows[rank][1]
                rows[j][2] ^= rows[rank][2]
                xor_steps += 1
        pivots.append(column)
        rank += 1
    contradiction = next((r[2] for r in rows if not r[0] and r[1]), None)
    if contradiction is not None:
        return {'rank': rank, 'contradiction': contradiction,
                'free': None, 'decoder': None, 'row_xors': xor_steps,
                'row_probes_upper_bound': probe_steps}
    free = [v for v in range(n) if v not in set(pivots)]
    free_index = {v: i for i, v in enumerate(free)}
    pivot_index = {p: j for j, p in enumerate(pivots)}
    decoder = []
    for v in range(n):
        if v in free_index:
            decoder.append((0, 1 << free_index[v]))
        else:
            row = rows[pivot_index[v]]
            decoder.append((row[1], sum(1 << i for f, i in free_index.items() if row[0] >> f & 1)))
    return {'rank': rank, 'contradiction': None, 'free': free, 'decoder': decoder,
            'row_xors': xor_steps, 'row_probes_upper_bound': probe_steps}


def verify_refutation(equations, contradiction, n):
    """Check that XOR of selected, source-lifted equations derives 0=1."""
    if not isinstance(contradiction, int) or contradiction <= 0 or contradiction >= 1 << len(equations):
        return False
    mask, rhs = 0, 0
    for i, (lhs, b) in enumerate(equations):
        if contradiction >> i & 1:
            mask ^= lhs
            rhs ^= b
    return mask == 0 and rhs == 1 and all(0 < lhs < 1 << n for lhs, _ in equations)


def decode(decoder, z):
    return {i + 1: const ^ ((mask & z).bit_count() % 2)
            for i, (const, mask) in enumerate(decoder)}


class BudgetExhausted(Exception):
    pass


def count_residual(residual, decoder, free_dim, budget):
    """Complete binary decision tree over free GF(2) coordinates, with pruning.

    Stops with an explicit refusal when the total search-node budget runs out.
    This method is not a polynomial bound for general mixed CNF/XOR instances.
    """
    transformed = [tuple((decoder[abs(lit) - 1][0],
                          decoder[abs(lit) - 1][1], int(lit > 0))
                         for lit in clause) for clause in residual]
    weights = Counter()
    for clause in transformed:
        for _, mask, _ in clause:
            for i in range(free_dim):
                if mask >> i & 1:
                    weights[i] += 1
    order = sorted(range(free_dim), key=lambda i: (-weights[i], i))
    ledger = {'visited_nodes': 0, 'literal_evaluations': 0,
              'pruned_false_nodes': 0, 'satisfied_suffix_nodes': 0,
              'free_variable_order': [x + 1 for x in order], 'node_budget': budget}

    def rec(depth, assigned_mask, assigned_values):
        ledger['visited_nodes'] += 1
        if ledger['visited_nodes'] > budget:
            raise BudgetExhausted
        all_true = True
        for clause in transformed:
            clause_true, unresolved = False, False
            for constant, mask, required in clause:
                ledger['literal_evaluations'] += 1
                if mask & ~assigned_mask:
                    unresolved = True
                elif constant ^ ((mask & assigned_values).bit_count() % 2) == required:
                    clause_true = True
                    break
            if not clause_true:
                if not unresolved:
                    ledger['pruned_false_nodes'] += 1
                    return 0, None
                all_true = False
        if all_true:
            ledger['satisfied_suffix_nodes'] += 1
            return 1 << (free_dim - depth), assigned_values
        if depth == free_dim:
            raise AssertionError('all literals known, but clause unresolved')
        var_bit = 1 << order[depth]
        a, wa = rec(depth + 1, assigned_mask | var_bit, assigned_values)
        b, wb = rec(depth + 1, assigned_mask | var_bit, assigned_values | var_bit)
        return a + b, wa if wa is not None else wb

    count, z = rec(0, 0, 0)
    return count, z, ledger


def frontier_estimate(clauses, n):
    """Estimate the explicit factor size without materializing any factor."""
    if () in clauses:
        return {'width': 0, 'projected_entries': 0, 'initial_entries': 1}
    order = min_fill_order(clauses, n)
    graph = {v: set() for v in range(1, n + 1)}
    from itertools import combinations
    for clause in clauses:
        scope = {abs(l) for l in clause}
        for a in scope:
            graph[a].update(scope - {a})
    width, projected = 0, 0
    for v in order:
        neighbors = sorted(graph[v])
        width = max(width, len(neighbors))
        projected += 1 << len(neighbors)
        for a, b in combinations(neighbors, 2):
            graph[a].add(b)
            graph[b].add(a)
        for a in neighbors:
            graph[a].discard(v)
        del graph[v]
    return {'width': width, 'projected_entries': projected,
            'initial_entries': sum(1 << len(c) for c in clauses)}


def solve(clauses, n, *, max_arity=4, free_budget=20,
          node_budget=1_000_000, frontier_entry_budget=200_000):
    """Exact count/witness or explicit undecided, with verifiable certificates.

    No compactness guarantee on arbitrary CNF; estimate alone is not proof of
    complexity. Pure XOR gives polynomial elimination and rank-based #SAT.
    """
    clauses = [tuple(c) for c in clauses]
    start = perf_counter()
    ground = compile_ground(clauses, n, max_arity)
    if not verify_compilation(clauses, n, ground):
        raise AssertionError('source-to-ground equivalence failed')
    elimination = eliminate(ground['equations'], n)
    ledger = {
        'source_clauses': len(clauses), 'canonical_clauses': ground['canonical_clause_count'],
        'lifted_clauses': ground['lifted_clause_count'],
        'recovered_equations': len(ground['equations']),
        'residual_clauses': len(ground['residual']),
        'rank': elimination['rank'], 'free_dimension': n - elimination['rank'],
        'gf2_row_xors': elimination['row_xors'],
        'gf2_row_probes_upper_bound': elimination['row_probes_upper_bound'],
        'compilation_equivalence_verified': True,
        'original_model_count_preserved': True,
    }
    contradiction = elimination['contradiction']
    if contradiction is not None:
        if not verify_refutation(ground['equations'], contradiction, n):
            raise AssertionError('bad contradiction witness')
        result = {'status': 'unsat', 'count': 0, 'witness': None, 'method': 'gf2-refutation',
                  'refutation_equation_indices': [i for i in range(len(ground['equations'])) if contradiction >> i & 1],
                  'ledger': ledger}
    elif () in ground['residual']:
        result = {'status': 'unsat', 'count': 0, 'witness': None, 'method': 'empty-clause',
                  'ledger': ledger}
    elif not ground['residual']:
        decoder = elimination['decoder']
        witness = decode(decoder, 0)
        count = 1 << len(elimination['free'])
        if not verify_assignment(clauses, witness):
            raise AssertionError('bad XOR witness')
        result = {'status': 'sat', 'count': count, 'witness': witness,
                  'method': 'affine-rank', 'ledger': ledger}
    elif n - elimination['rank'] <= free_budget:
        try:
            count, z, search_cost = count_residual(ground['residual'], elimination['decoder'],
                                                   n - elimination['rank'], node_budget)
            ledger['residual_search'] = search_cost
            witness = None if z is None else decode(elimination['decoder'], z)
            if witness is not None and not verify_assignment(clauses, witness):
                raise AssertionError('bad decoded witness')
            result = {'status': 'sat' if count else 'unsat', 'count': count,
                      'witness': witness, 'method': 'affine-reduced-search', 'ledger': ledger}
        except BudgetExhausted:
            ledger['residual_search'] = {'node_budget': node_budget, 'exhausted': True}
            result = {'status': 'undetermined', 'count': None, 'witness': None,
                      'method': 'budget-refusal', 'ledger': ledger}
    else:
        estimate = frontier_estimate(ground['residual'], n)
        ledger['ordinary_frontier_estimate'] = estimate
        if (ground['equations'] or
                estimate['projected_entries'] > frontier_entry_budget or
                estimate['initial_entries'] > frontier_entry_budget):
            # The ordinary frontier would count the *residual alone*, and
            # cannot be safely combined with recovered XORs. Do not run it.
            result = {'status': 'undetermined', 'count': None, 'witness': None,
                      'method': 'unsupported-hybrid-refusal' if ground['equations']
                      else 'budget-refusal', 'ledger': ledger}
        else:
            count, witness, stats = frontier_solve(ground['residual'], n)
            ledger['ordinary_frontier_execution'] = stats
            result = {'status': 'sat' if count else 'unsat', 'count': count,
                      'witness': witness, 'method': 'ordinary-frontier', 'ledger': ledger}
    result['ledger']['elapsed_ms'] = round((perf_counter() - start) * 1000, 3)
    return result, ground


def parity_formula(n, eqs):
    return [c for mask, rhs in eqs for c in encode_xor(mask, rhs)]


def planted_dense(n=96, remaining=8, seed=22, mixed=False):
    """Generated dense 4-XOR equations from a planted assignment, rank targeted."""
    rng = random.Random(seed)
    planted = rng.getrandbits(n)
    eqs, used = [], set()
    while len(eqs) < n - remaining:
        vs = tuple(sorted(rng.sample(range(n), 4)))
        if vs in used:
            continue
        mask = sum(1 << v for v in vs)
        rhs = (mask & planted).bit_count() & 1
        trial = eliminate(eqs + [(mask, rhs)], n)
        if trial['rank'] == len(eqs) + 1:
            used.add(vs)
            eqs.append((mask, rhs))
    clauses = parity_formula(n, eqs)
    if mixed:
        # Add non-affine constraints satisfied by the planted assignment.
        extra_scopes = ([(0, 11, 25), (17, 36, 51), (29, 54, 78)] if n >= 79
                        else [(0, n//3, n-1), (1, n//2, n-2), (2, n//4, n-3)])
        for vs in extra_scopes:
            clauses.append(tuple((v + 1) if planted >> v & 1 else -(v + 1) for v in vs))
    return clauses, planted, eqs


def random_cubic_tseitin(vertices=80, seed=7301):
    """A 3-regular graph via three edge-disjoint perfect matchings.

    Odd vertex-charge parity is an exact global XOR contradiction. No clause
    group on one vertex is contradictory on its own.
    """
    if vertices < 6 or vertices % 2:
        raise ValueError('vertices must be even >= 6')
    rng = random.Random(seed)
    for attempt in range(500):
        edges = set()
        matchings = []
        for _ in range(3):
            for tries in range(1000):
                p = list(range(vertices))
                rng.shuffle(p)
                cand = {tuple(sorted((p[i], p[i+1]))) for i in range(0, vertices, 2)}
                if edges.isdisjoint(cand):
                    matchings.append(sorted(cand))
                    edges |= cand
                    break
            else:
                break
        if len(matchings) != 3:
            continue
        graph = {v:set() for v in range(vertices)}
        for a,b in edges:
            graph[a].add(b);graph[b].add(a)
        seen={0};stack=[0]
        while stack:
            v=stack.pop()
            for w in graph[v]-seen:
                seen.add(w);stack.append(w)
        if len(seen)==vertices:
            break
    else:
        raise RuntimeError('could not generate connected graph')
    edge_ids = {edge:i+1 for i, edge in enumerate(sorted(edges))}
    eqs = []
    for v in range(vertices):
        mask = sum(1 << (edge_ids[edge]-1) for edge in edge_ids if v in edge)
        eqs.append((mask, int(v==0)))
    return parity_formula(len(edge_ids), eqs), len(edge_ids), eqs


def campaign():
    cases = []
    a, planted, _ = planted_dense(96, 8, 22, False)
    cases.append(('dense-96-pure-xor', a, 96))
    b, planted, _ = planted_dense(96, 8, 22, True)
    cases.append(('dense-96-xor-plus-cnf', b, 96))
    t, n, _ = random_cubic_tseitin(80, 7301)
    cases.append(('tseitin-120-vars-odd-charge', t, n))
    cases.extend([('chain-96', [tuple((1,))] + [c for v in range(1,96) for c in [(-v,v+1),(v,-(v+1))]], 96),
                  ('random-16-no-xor', __import__('frontier_ground').random_3cnf(16, 64, 73), 16),
                  ('incomplete-parity', parity_formula(8, [(0b1111,1)])[:-1], 8)])
    out = []
    for name, clauses, n in cases:
        result, ground = solve(clauses, n)
        out.append({'case': name, 'n': n, 'source_clauses': len(clauses),
                    'status': result['status'], 'method': result['method'],
                    'count': result['count'],
                    'witness_verified': (result['witness'] is not None and
                                         verify_assignment(clauses, result['witness'])),
                    'refutation_verified': (result.get('refutation_equation_indices') is not None and
                        verify_refutation(ground['equations'], sum(1<<i for i in result.get('refutation_equation_indices',[])), n)),
                    'ledger': result['ledger']})
    return out


if __name__ == '__main__':
    print(json.dumps(campaign(), indent=2))
