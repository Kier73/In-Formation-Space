"""CIG-008 independent source checker: no producer import.

Re-encode claimed parity relations, compare augmented row spaces, verify the
hidden-pivot certificate, and replay exact interface messages with a separate
factor representation. A Hall receipt is decision-only, never a count.
"""
from hashlib import sha256
from itertools import product
import json


def normal(source, n):
    if type(n) is not int or not 1 <= n <= 8192 or len(source) > 150000:
        raise ValueError('invalid source')
    result = set()
    for c in source:
        if len(c) > 64 or any(type(l) is not int or not 1 <= abs(l) <= n for l in c):
            raise ValueError('invalid literal')
        literals = set(c)
        if all(-l not in literals for l in literals):
            result.add(tuple(sorted(literals, key=abs)))
    return sorted(result, key=lambda x:(len(x), x))


def indices(mask, n):
    if type(mask) is not int or not 0 <= mask < 1 << n:
        raise ValueError('invalid mask')
    out = set()
    while mask:
        bit = mask & -mask; out.add(bit.bit_length()); mask -= bit
    return out


def row_space(rows):
    """Canonical RREF of augmented rows, with lowest-column pivots (sets)."""
    basis = {}
    for row in rows:
        r = set(row)
        for p in sorted(basis):
            if p in r:
                r ^= basis[p]
        if r:
            p = min(r)
            for old in basis.values():
                if p in old:
                    old ^= r
            basis[p] = r
    return {p:frozenset(v) for p,v in basis.items()}


def accepted(rows, state):
    return all(any(((state >> (abs(l)-1)) & 1) == int(l > 0) for l in c) for c in rows)


def replay(residual, projected, n, order, width, limit):
    """Replay integer sum-product using assignment tuples, not packed tables."""
    factors = []; visits = 0; peak = 0
    def add(s, func):
        nonlocal visits, peak
        if len(s)>width or visits+(1<<len(s))>limit:
            raise ValueError('checker factor budget')
        visits += 1 << len(s); peak = max(peak,len(s))
        factors.append((s, {z:int(func(dict(zip(s,z)))) for z in product((0,1),repeat=len(s))}))
    for c in residual:
        add(tuple(sorted(map(abs,c))),lambda a: any(a[abs(l)]==int(l>0) for l in c))
    for m,b in projected:
        add(tuple(sorted(indices(m,n))),lambda a: sum(a.values())%2==b)
    for v in order:
        selected = [f for f in factors if v in f[0]]
        factors = [f for f in factors if v not in f[0]]
        scope = sorted(set().union(*(set(s) for s,_ in selected)) | {v})
        if len(scope)>width or visits+(1<<len(scope))>limit:
            raise ValueError('checker elimination budget')
        visits += 1<<len(scope); peak=max(peak,len(scope))
        new = tuple(x for x in scope if x!=v); table={}
        for values in product((0,1),repeat=len(scope)):
            a=dict(zip(scope,values)); value=1
            for s, f in selected:
                value*=f[tuple(a[x] for x in s)]
            key=tuple(a[x] for x in new); table[key]=table.get(key,0)+value
        factors.append((new,table))
    total=1
    for s, table in factors:
        if s: raise ValueError('incomplete elimination')
        total*=table[()]
    return total,visits,peak


def verify(clauses, n, r, *, max_width=12, max_cells=2_000_000):
    try:
        rows=normal(clauses,n)
        if r['schema']!='ifs.cig008.composed-ground.v1' or r['n']!=n or r['source']!=sha256(json.dumps([n,rows],sort_keys=True,separators=(',',':')).encode()).hexdigest():
            return False
        if r['max_width']!=max_width or r['max_cells']!=max_cells or not 1<=max_width<=16 or not 1<=max_cells<=10_000_000:
            return False
        source=set(rows); reconstructed=set(); eq_rows=[]
        for m,b in r['equations']:
            vs=sorted(indices(m,n))
            if not 1<=len(vs)<=3 or type(b)is not int or b not in (0,1): return False
            block={tuple(v if not bit else -v for v,bit in zip(vs,bits))
                   for bits in product((0,1),repeat=len(vs)) if sum(bits)%2!=b}
            if reconstructed & block or not block<=source: return False
            reconstructed |= block
            eq_rows.append(set(vs)|({n+1} if b else set()))
        residual=normal(r['residual'],n)
        if set(residual)&reconstructed or set(residual)|reconstructed!=source: return False
        interface=sorted({abs(l) for c in residual for l in c})
        if r['interface']!=interface or sorted(r['elimination_order'])!=interface: return False
        hidden=set(range(1,n+1))-set(interface)
        augmented=[]; seen=set()
        for v,m,b in r['pivots']:
            s=indices(m,n)
            if type(v) is not int or v not in hidden or v not in s or v in seen or seen&s or type(b)is not int or b not in (0,1):return False
            seen.add(v); augmented.append(s|({n+1} if b else set()))
        # Triangular rows certify rank of hidden projection: each has one new pivot.
        # Hidden columns left unpivoted may occur in pivot rows (free coordinates).
        for m,b in r['projected']:
            s=indices(m,n)
            if s&hidden or type(b)is not int or b not in (0,1):return False
            augmented.append(s|({n+1} if b else set()))
        if row_space(eq_rows)!=row_space(augmented):return False
        if [v for v,_,_ in r['pivots']] != sorted(seen): return False
        remaining=len(eq_rows); work=0
        for v in sorted(hidden):
            work+=remaining
            remaining-=int(v in seen)
        if r['projection_row_visits']!=work:return False
        free=len(hidden)-len(seen)
        if r['free_hidden']!=free:return False
        c,visits,peak=replay(residual,r['projected'],n,r['elimination_order'],max_width,max_cells)
        if (r['interface_count'],r['count'],r['cells'],r['peak_scope'],r['status'])!=(str(c),str(c<<free),visits,peak,'SAT' if c else 'UNSAT'):return False
        if c:
            w=int(r['witness'])
            return 0<=w<1<<n and accepted(rows,w)
        return r['witness'] is None
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):
        return False


def verify_decision(clauses,n,receipt):
    """Check Hall contradiction against the FULL source or original witness."""
    from hall_ground import verify_hall
    try:
        if receipt['status']=='UNSAT' and receipt['route']=='Hall-subsource':
            return receipt['hall']['status']=='UNSAT' and verify_hall(clauses,n,receipt['hall'])
        if receipt['status']=='SAT' and receipt['route']=='Hall-affine-extension':
            w=int(receipt['witness'])
            return 0<=w<1<<n and accepted(normal(clauses,n),w)
    except (ValueError,KeyError,TypeError):
        return False
    return False
