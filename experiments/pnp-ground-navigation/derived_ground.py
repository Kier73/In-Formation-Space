"""PNG-003 — proof-carrying nonlocal algebraic Ground discovery from CNF.

Two sound inference tiers (standard classical Boolean reasoning):
  * reversible consensus: (C | v) & (C | ~v) <=> C;
  * resolution: from (A | v) & (B | ~v) derive A | B, retaining sources.

Only the reversible rule deletes clauses. Newly resolved parity equations are
added as redundant *entailed* constraints, never substituted for their parents.
The independent verifier checks both kinds of evidence from the original CNF.
"""
from __future__ import annotations

from collections import defaultdict, deque
from time import perf_counter

from algebraic_ground import (compile_ground, eliminate, encode_xor, normalize,
                              parity_formula, solve as algebraic_solve)
from ground_verifier import digest_ground, digest_source


def clause_sort(clause):
    return len(clause), tuple((abs(v), v < 0) for v in clause)


def canon(clause):
    return tuple(sorted(clause, key=lambda v: (abs(v), v < 0)))


def contract_twins(clauses, n, *, max_contracts=12000):
    """Exact all-assignment-preserving simplifications with replayable steps."""
    source = set(normalize(clauses, n))
    steps = []
    passes = 0
    cutoff = False
    while True:
        passes += 1
        pairs = []
        for parent in sorted(source, key=clause_sort):
            for literal in parent:
                if literal < 0:
                    continue
                opposite = canon(set(parent) - {literal} | {-literal})
                if opposite in source:
                    child = canon(set(parent) - {literal})
                    pairs.append((literal, parent, opposite, child))
        if not pairs:
            break
        changed = 0
        for pivot, positive, negative, child in sorted(pairs,
                key=lambda x: (x[0], clause_sort(x[3]), clause_sort(x[1]))):
            if positive not in source or negative not in source:
                continue
            if len(steps) >= max_contracts:
                cutoff = True
                break
            source.remove(positive)
            source.remove(negative)
            source.add(child)
            steps.append({'pivot': pivot, 'positive': positive,
                          'negative': negative, 'child': child})
            changed += 1
        if cutoff or changed == 0:
            break
    return sorted(source, key=clause_sort), steps, {'rounds': passes,
        'contractions': len(steps), 'cutoff': cutoff}


def resolution_closure(clauses, n, *, width=2, max_attempts=100000,
                       max_added=5000):
    """Width-bounded resolution DAG; stops safely when budgets exhaust.

    All generated clauses are *entailed*, but the input is not modified here.
    This is not a general bounded-time CNF entailment algorithm.
    """
    if not 1 <= width <= 5 or max_attempts < 1 or max_added < 0:
        raise ValueError('invalid resolution budget')
    source = set(normalize(clauses, n))
    known = {c for c in source if len(c) <= width}
    by_lit = defaultdict(set)
    for c in known:
        for l in c:
            by_lit[l].add(c)
    q = deque(sorted(known, key=clause_sort))
    proofs = {}
    attempts = 0
    cutoff = False
    while q:
        left = q.popleft()
        for pivot in left:
            for right in sorted(by_lit[-pivot], key=clause_sort):
                attempts += 1
                if attempts > max_attempts:
                    cutoff = True
                    break
                mix = set(left) - {pivot} | (set(right) - {-pivot})
                if any(-v in mix for v in mix) or len(mix) > width:
                    continue
                out = canon(mix)
                if out in known:
                    continue
                if len(proofs) >= max_added:
                    cutoff = True
                    break
                proofs[out] = {'left': left, 'right': right,
                               'pivot': pivot, 'child': out}
                known.add(out)
                for literal in out:
                    by_lit[literal].add(out)
                q.append(out)
            if cutoff:
                break
        if cutoff:
            break
    return known, proofs, {'attempts': attempts,
        'new_clauses': len(proofs), 'cutoff': cutoff, 'width': width}


def minimize_proof(required_clauses, source, parents):
    """Keep only the derivation DAG needed by admitted equations."""
    source = set(source)
    emitted, processed = [], set()
    def visit(c):
        if c in source:
            return
        if c in processed:
            return
        if c not in parents:
            raise AssertionError('derived lemma lacks proof')
        entry = parents[c]
        visit(entry['left'])
        visit(entry['right'])
        emitted.append(entry)
        processed.add(c)
    for clause in sorted(set(required_clauses), key=clause_sort):
        visit(clause)
    return emitted


def choose_nonredundant(equations, candidates, n, limit=100):
    """Use only rank-increasing, or first refuting, derived XOR equations."""
    if limit < 0:
        raise ValueError('negative lemma budget')
    if limit == 0:
        return [], 0
    selected = []
    rank_checks = 0
    active = list(equations)
    current = eliminate(active, n)
    for eq in sorted(candidates, key=lambda e: (e[0].bit_count(), e[0], e[1])):
        rank_checks += 1
        after = eliminate(active + [eq], n)
        if after['rank'] > current['rank'] or (current['contradiction'] is None and
                                              after['contradiction'] is not None):
            active.append(eq)
            selected.append(eq)
            current = after
            if len(selected) >= limit or current['contradiction'] is not None:
                break
    return selected, rank_checks


def compile_proven_ground(clauses, n, *, max_arity=4, max_contracts=12000,
                          resolution_width=2, max_resolution_attempts=100000,
                          max_resolution_added=5000, max_learned=100):
    t0 = perf_counter()
    original = normalize(clauses, n)
    terminal, contractions, cstats = contract_twins(
        original, n, max_contracts=max_contracts)
    base = compile_ground(terminal, n, max_arity=max_arity)
    known, proof_db, rstats = resolution_closure(terminal, n,
        width=resolution_width, max_attempts=max_resolution_attempts,
        max_added=max_resolution_added)
    if () in known:
        # Explicit source resolution proof of UNSAT (not merely failed search).
        empty_proof = minimize_proof([()], terminal, proof_db)
    else:
        empty_proof = []
    closure_ground = compile_ground(known, n, max_arity=max_arity)
    candidates = set(map(tuple, closure_ground['equations'])) - set(map(tuple, base['equations']))
    selected, rank_checks = choose_nonredundant(base['equations'], candidates, n,
                                                 limit=max_learned)
    required = [clause for mask, rhs in selected for clause in encode_xor(mask, rhs)]
    required.extend([()] if empty_proof else [])
    proof = minimize_proof(required, terminal, proof_db)
    rows = list(base['equations']) + selected
    augmented = normalize(base['residual'] + parity_formula(n, rows) +
                          ([()] if empty_proof else []), n)
    # Already-proven clauses are added as redundant lemmas, not substituted
    # for constraints that may further constrain free coordinates.
    result, ground = algebraic_solve(augmented, n, max_arity=max_arity)
    record = {'format': 'PNG-003-resolution-ground-v1', 'n': n,
        'original_clauses': original, 'terminal_clauses': terminal,
        'base_equations': base['equations'], 'base_residual': base['residual'],
        'learned_equations': selected, 'contract_steps': contractions,
        'resolution_steps': proof, 'resolution_empty': bool(empty_proof),
        'ground': ground, 'result': result,
        'source_sha256': digest_source(original, n),
        'augmented_sha256': digest_source(augmented, n),
        'ground_sha256': digest_ground(ground),
        'compilation_ledger': {'source_clauses':len(original),
            'terminal_clauses':len(terminal), 'base_equations':len(base['equations']),
            'learned_equations':len(selected), 'candidate_equations':len(candidates),
            'rank_checks':rank_checks, 'proof_steps':len(proof),
            'contraction':cstats, 'resolution':rstats,
            'elapsed_ms':round((perf_counter()-t0)*1000,3)}}
    return record


def split_guard(clauses, *, guard_id):
    """Two logically equivalent guarded copies; free guard when F is true."""
    return [tuple(clause) + (guard_id,) for clause in clauses] + [
            tuple(clause) + (-guard_id,) for clause in clauses]


def implication_equalities(nodes):
    """Non-twin 2-CNF gadgets that imply x_i == x_(i+1), fixing auxiliaries.

    For every i, (x_i OR g_i) & (NOT g_i OR NOT x_(i+1)) &
    (NOT x_i OR x_(i+1)).  No two parent clauses have identical context.
    """
    clauses = []
    for i in range(1, nodes):
        g = nodes + i
        clauses.extend([(i, g), (-g, -(i+1)), (-i, i+1)])
    return clauses, nodes * 2 - 1
