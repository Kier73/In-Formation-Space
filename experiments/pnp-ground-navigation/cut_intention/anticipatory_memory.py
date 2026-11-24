"""CIG-013: source-qualified anticipatory retention for regional revisions.

Finite declared future catalog; exact separable one-table-per-region policy.
Costs are producer table cells and declared cell retention prices, not wall time.
"""
from collections import Counter, defaultdict
from functools import lru_cache
import json
from adaptive_ground import annotate
from architecture_memory import Archive, region
from composed_ground import canonical, extract
from regional_memory import identity, wire
from verify_adaptive_ground import audit
from verify_anticipatory_memory import verify_restriction

VERSION = 'ifs.cig010.adaptive.v1'


def leaves(source, n, tree):
    root = annotate(tree)
    if not audit(source, n, tree, root):
        raise ValueError('unqualified layout')
    def walk(node):
        if node['children'] is None:
            r = node['region']
            yield region(r['scope'], r['clauses']), tuple(node['boundary'])
        else:
            for c in node['children']:
                yield from walk(c)
    return list(walk(root))


def descriptor(cov, boundary):
    return dict(version=VERSION, scope=list(cov[0]), clauses=[list(c) for c in cov[1]], boundary=list(boundary))


@lru_cache(maxsize=32768)
def cold(cov, boundary):
    _, residual = extract(list(cov[1]))
    return 1 << (len(cov[0]) if residual else len(boundary))


def required(base, target, boundary):
    if base[0] != target[0] or not set(base[1]) <= set(target[1]):
        return None
    return tuple(sorted(set(boundary) | {abs(l) for c in set(target[1])-set(base[1]) for l in c}))


def options(base, current, requests, price, rich=True):
    """One retained boundary, or none. Enumerate all subsets of useful coordinates.

    A superset of the requirements permits source strengthening plus marginalization.
    A cold route remains available when a projection would cost more than fresh work.
    """
    candidates = {current} if requests else set()
    if rich:
        useful = sorted(set(v for (_, _, need) in requests for v in need))
        candidates.update(tuple(v for j, v in enumerate(useful) if i >> j & 1)
                          for i in range(1 << len(useful)))
    data = [(target, b, frozenset(need), w, cold(target, b))
            for (target, b, need), w in requests.items()]
    baseline = sum(w*fresh for _, _, _, w, fresh in data)
    best = (baseline, 0, ())
    chosen = None
    for a in sorted(candidates):
        cells = 1 << len(a)
        prepare = cold(base, a)
        future = 0
        exposed = set(a)
        for target, b, need, w, fresh in data:
            if target == base and b == a:
                work = 0
            elif need <= exposed:
                work = min(cells, fresh)
            else:
                work = fresh
            future += w*work
        rank = (prepare+price*cells+future, cells, a)
        if rank < best:
            best, chosen = rank, a
    return chosen, best[0], baseline, len(candidates)+1


class Portfolio:
    """Exact finite price objective, with incremental per-region recomputation.

    Every forecast layout is independently audited. When several base regions
    cover a target leaf, use a deterministic longest-clause match (catalog rule).
    Unmatched leaves are charged cold. Repeated forecast names are rejected.
    """
    def __init__(self, source, n, tree, price=1, rich=True):
        if type(price) is not int or price < 0:
            raise ValueError('retention price')
        self.n, self.price, self.rich = n, price, rich
        self.current = dict(leaves(source, n, tree))
        self.by_scope = defaultdict(list)
        for cov in self.current:
            self.by_scope[cov[0]].append(cov)
        for v in self.by_scope.values():
            v.sort(key=lambda c: (-len(c[1]), c[1]))
        self.groups = defaultdict(Counter)
        self.forecasts = {}
        self.results = {}
        self.unmatched = 0
        self.touched = 0

    def _scan(self, source, tree, weight):
        if type(weight) is not int or weight < 1:
            raise ValueError('forecast contract')
        grouped = defaultdict(Counter)
        unmatched = 0
        for target, b in leaves(source, self.n, tree):
            for base in self.by_scope.get(target[0], ()):
                need = required(base, target, b)
                if need is not None:
                    grouped[base][target, b, need] += weight
                    break
            else:
                unmatched += weight*cold(target, b)
        return grouped, unmatched, weight

    def add(self, name, source, tree, weight=1):
        if name in self.forecasts:
            raise ValueError('duplicate forecast')
        grouped, unmatched, weight = self._scan(source, tree, weight)
        for base, req in grouped.items():
            self.groups[base].update(req)
            self.refresh(base)
        self.unmatched += unmatched
        self.forecasts[name] = (grouped, unmatched, weight)

    def replace(self, name, source, tree, weight=1):
        old, old_cost, _ = self.forecasts[name]
        grouped, unmatched, weight = self._scan(source, tree, weight)
        for base in old.keys() | grouped.keys():
            a, b = old.get(base, Counter()), grouped.get(base, Counter())
            if a == b:
                continue
            self.groups[base].subtract(a)
            self.groups[base].update(b)
            self.groups[base] += Counter()
            self.refresh(base)
        self.unmatched += unmatched-old_cost
        self.forecasts[name] = (grouped, unmatched, weight)

    def refresh(self, base):
        self.results[base] = options(base, self.current[base], self.groups[base], self.price, self.rich)
        self.touched += 1

    def remove(self, name):
        grouped, unmatched, _ = self.forecasts.pop(name)
        for base, req in grouped.items():
            self.groups[base].subtract(req)
            self.groups[base] += Counter()
            self.refresh(base)
        self.unmatched -= unmatched

    def selection(self):
        selected = {c: r[0] for c, r in self.results.items() if r[0] is not None}
        return selected, dict(objective=self.unmatched+sum(r[1] for r in self.results.values()),
                              baseline=self.unmatched+sum(r[2] for r in self.results.values()),
                              retained_cells=sum(1 << len(b) for b in selected.values()),
                              retained_regions=len(selected), groups_refreshed=self.touched,
                              last_catalog_options=sum(r[3] for r in self.results.values()))


def restrict(old_desc, old, new_desc):
    a, b = old_desc['boundary'], new_desc['boundary']
    added = set(map(tuple, new_desc['clauses']))-set(map(tuple, old_desc['clauses']))
    positions = {v: i for i, v in enumerate(a)}
    tests = [[(1 << positions[abs(l)], l > 0) for l in c] for c in added]
    out = [0]*(1 << len(b))
    for x, count in enumerate(old['counts']):
        if all(any(bool(x & m) == sign for m, sign in c) for c in tests):
            y = sum(((x >> positions[v]) & 1) << j for j, v in enumerate(b))
            out[y] += int(count)
    return dict(key=identity(new_desc), boundary=b, counts=list(map(str, out)))


class Retained:
    """Session-local qualified seed tables. Query-derived messages stay transient."""
    def __init__(self, portfolio):
        self.n = portfolio.n
        self._entries = defaultdict(list)
        self.stats = Counter()
        self.bytes = 0
        self._seed = Archive()
        for cov, b in portfolio.selection()[0].items():
            d = descriptor(cov, b)
            msg = self._seed.obtain(d, None, self.stats)
            pair = (wire(d), wire(msg))
            self._entries[cov[0]].append(pair)
            self.bytes += sum(map(len, pair))

    def session(self):
        return RevisionArchive(self)


class RevisionArchive(Archive):
    def __init__(self, retained):
        super().__init__()
        if type(retained) is not Retained:
            raise ValueError('receiver-owned admitted retention required')
        self.n, self._retained = retained.n, retained

    def obtain(self, desc, children, stats):
        if children is not None or identity(desc) in self._proofs:
            return super().obtain(desc, children, stats)
        target = region(desc['scope'], desc['clauses'])
        b = tuple(desc['boundary'])
        best = None
        for raw_desc, raw_msg in self._retained._entries.get(target[0], ()):
            old_desc = json.loads(raw_desc)
            base = region(old_desc['scope'], old_desc['clauses'])
            need = required(base, target, b)
            a = tuple(old_desc['boundary'])
            if need is None or not set(need) <= set(a):
                continue
            cost = 0 if base == target and a == b else 1 << len(a)
            if cost <= cold(target, b) and (best is None or cost < best[0]):
                best = (cost, old_desc, json.loads(raw_msg))
        if best is None:
            return super().obtain(desc, children, stats)
        cost, old_desc, old = best
        if self._retained._seed._proofs.get(old['key']) != wire(old):
            raise ValueError('unadmitted retained table')
        msg = restrict(old_desc, old, desc) if cost else dict(old, key=identity(desc))
        if not verify_restriction(self.n, old_desc, old, desc, msg):
            raise ValueError('independent source restriction check failed')
        key = msg['key']
        self._proofs[key] = wire(msg)
        self._coverage[key] = target
        self._functions[target][b] = wire(msg)
        stats['anticipatory_reuse'] += 1
        stats['restriction_cells'] += cost
        stats['restriction_check_cells'] += len(old['counts'])
        return json.loads(self._proofs[key])
