"""CIG-008: exact affine-to-Boolean interfaces, with bounded factor navigation.

An affine region emits its projected parity constraints and a constant fiber
multiplicity. The remaining overlapping Boolean factors share exact interfaces.
No global assignment enumeration; budget refusal is UNKNOWN, not UNSAT.
"""
from collections import defaultdict
from hashlib import sha256
from itertools import combinations
import json

SCHEMA = 'ifs.cig008.composed-ground.v1'


def canonical(clauses, n):
    if type(n) is not int or not 1 <= n <= 8192 or len(clauses) > 150000:
        raise ValueError('source budget')
    out = set()
    for row in clauses:
        if len(row) > 64 or any(type(l) is not int or not 1 <= abs(l) <= n for l in row):
            raise ValueError('invalid source literal')
        c = frozenset(row)
        if not any(-l in c for l in c):
            out.add(tuple(sorted(c, key=abs)))
    return sorted(out, key=lambda c: (len(c), c))


def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def extract(rows):
    """Find complete parity blocks; consume exactly their source clauses."""
    groups = defaultdict(set)
    for c in rows:
        if 1 <= len(c) <= 3:
            groups[tuple(map(abs, c))].add(c)
    equations, used = [], set()
    for scope, clauses in sorted(groups.items()):
        for rhs in (0, 1):
            expected = {tuple(-v if p >> i & 1 else v for i, v in enumerate(scope))
                        for p in range(1 << len(scope)) if p.bit_count() % 2 != rhs}
            if expected <= clauses:
                equations.append([sum(1 << (v-1) for v in scope), rhs])
                used.update(expected)
    return equations, [list(c) for c in rows if c not in used]


def project(equations, hidden):
    """Eliminate hidden columns, retaining source-equivalent reconstruction rows."""
    rows = [tuple(r) for r in equations]
    pivots = []
    work = 0
    for v in hidden:
        flag = 1 << (v-1)
        candidates = [i for i, (m, _) in enumerate(rows) if m & flag]
        work += len(rows)
        if not candidates:
            continue
        i = min(candidates, key=lambda i: (rows[i][0].bit_count(), rows[i]))
        m, b = rows.pop(i)
        pivots.append([v, m, b])
        rows = [(a ^ m, c ^ b) if a & flag else (a, c) for a, c in rows]
    return pivots, sorted(set(rows) - {(0, 0)}), work


def scope(mask):
    return tuple(i+1 for i in range(mask.bit_length()) if mask >> i & 1)


def _table(scope_, pred):
    return (scope_, tuple(int(pred(dict(zip(scope_, ((x >> j) & 1 for j in range(len(scope_)))))))
                          for x in range(1 << len(scope_))))


def count_factors(residual, projected, interface, max_width, max_cells):
    """Variable elimination over exact integer factors, with reverse witness."""
    factors = []
    cells = 0
    maximum = 0
    def add(s, pred):
        nonlocal cells, maximum
        if len(s) > max_width or cells + (1 << len(s)) > max_cells:
            raise OverflowError('factor budget')
        cells += 1 << len(s); maximum = max(maximum, len(s))
        factors.append(_table(s, pred))
    for c in residual:
        add(tuple(sorted(map(abs, c))), lambda a: any(a[abs(l)] == (l > 0) for l in c))
    for m, b in projected:
        s = scope(m)
        add(s, lambda a: sum(a.values()) % 2 == b)
    def at(f, a):
        return f[1][sum(a[v] << i for i, v in enumerate(f[0]))]
    pending = set(interface); history = []; order = []
    while pending:
        neighborhoods = {v: set() for v in pending}
        for s, _ in factors:
            for v in s:
                neighborhoods[v].update(s)
        v = min(pending, key=lambda v: (len(neighborhoods[v]), v))
        pending.remove(v); order.append(v)
        bucket = [f for f in factors if v in f[0]]
        factors = [f for f in factors if v not in f[0]]
        s = tuple(sorted(neighborhoods[v] - {v}))
        # Charge BOTH values of the eliminated variable, not only emitted rows.
        if len(s)+1 > max_width or cells + (2 << len(s)) > max_cells:
            raise OverflowError('elimination budget')
        cells += 2 << len(s); maximum = max(maximum, len(s)+1)
        vals = []
        for x in range(1 << len(s)):
            a = {u: x >> i & 1 for i, u in enumerate(s)}
            total = 0
            for bit in (0, 1):
                a[v] = bit
                product = 1
                for f in bucket:
                    product *= at(f, a)
                total += product
            vals.append(total)
        factors.append((s, tuple(vals)))
        history.append((v, bucket))
    total = 1
    for s, vals in factors:
        assert not s
        total *= vals[0]
    witness = None
    if total:
        a = {}
        for v, bucket in reversed(history):
            for b in (0, 1):
                a[v] = b
                if all(at(f, a) for f in bucket):
                    break
            else:
                raise AssertionError('witness reconstruction failed')
        witness = sum(b << (v-1) for v, b in a.items())
    return total, witness, order, cells, maximum


def compile_ground(clauses, n, *, max_width=12, max_cells=2_000_000):
    if type(max_width) is not int or not 1 <= max_width <= 16 or type(max_cells) is not int or not 1 <= max_cells <= 10_000_000:
        raise ValueError('invalid finite budgets')
    rows = canonical(clauses, n)
    eqs, residual = extract(rows)
    interface = sorted({abs(l) for c in residual for l in c})
    hidden = sorted(set(range(1, n+1)) - set(interface))
    pivots, projected, work = project(eqs, hidden)
    try:
        c, witness, order, cells, width = count_factors(residual, projected, interface, max_width, max_cells)
    except OverflowError:
        return {'status': 'UNKNOWN', 'reason': 'bounded factor budget', 'source': digest([n, rows])}
    if witness is not None:
        for v, m, b in reversed(pivots):
            witness |= (b ^ ((m & witness).bit_count() & 1)) << (v-1)
        assert all(any(bool(witness & (1 << (abs(l)-1))) == (l > 0) for l in c) for c in rows)
    result = {'schema': SCHEMA, 'source': digest([n, rows]), 'n': n,
              'equations': eqs, 'residual': residual, 'interface': interface,
              'pivots': pivots, 'projected': [list(r) for r in projected],
              'free_hidden': len(hidden)-len(pivots), 'elimination_order': order,
              'max_width': max_width, 'max_cells': max_cells, 'cells': cells,
              'peak_scope': width, 'projection_row_visits': work,
              'interface_count': str(c), 'count': str(c << (len(hidden)-len(pivots))),
              'status': 'SAT' if c else 'UNSAT', 'witness': str(witness) if c else None}
    return result


def decide_with_hall(clauses, n):
    """Decision-only interface to the actual CIG-007 Hall implementation.

    A residual Hall refutation also refutes the entire source. A matching
    witness is admissible only if it extends through every affine relation.
    No matching result is ever interpreted as a nonzero model count.
    """
    from hall_ground import compile_hall
    rows = canonical(clauses, n)
    eqs, residual = extract(rows)
    interface = {abs(l) for c in residual for l in c}
    pivots, projected, _ = project(eqs, sorted(set(range(1,n+1))-interface))
    receipt = compile_hall(residual,n)
    if receipt['status']=='UNSAT':
        return {'status':'UNSAT','route':'Hall-subsource','hall':receipt}
    if receipt['status']=='SAT':
        state=int(receipt['witness'])
        if all((m&state).bit_count()%2==b for m,b in projected):
            for v,m,b in reversed(pivots):
                state |= (b ^ ((m&state).bit_count()&1))<<(v-1)
            if all(any(bool(state&(1<<(abs(l)-1)))==(l>0) for l in c) for c in rows):
                return {'status':'SAT','route':'Hall-affine-extension','witness':str(state)}
    return {'status':'UNKNOWN','reason':'matching did not resolve full source'}
