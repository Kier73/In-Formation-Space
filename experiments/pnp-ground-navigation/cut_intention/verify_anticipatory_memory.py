"""Independent checker for a source-strengthened regional conditional count.

The old message must be receiver-admitted; this function is not an admission API.
"""
from itertools import product
from verify_composed_ground import normal
from regional_memory import identity


def verify_restriction(n, old_desc, old, new_desc, new):
    try:
        scope = old_desc['scope']
        if scope != new_desc['scope'] or scope != sorted(set(scope)) or len(scope) > 10:
            return False
        if any(type(v) is not int or not 1 <= v <= n for v in scope):
            return False
        a, b = old_desc['boundary'], new_desc['boundary']
        if a != sorted(set(a)) or b != sorted(set(b)) or not set(b) <= set(a) <= set(scope):
            return False
        original = set(normal(old_desc['clauses'], n))
        revised = set(normal(new_desc['clauses'], n))
        if not original <= revised or any(abs(l) not in scope for c in revised for l in c):
            return False
        added = revised - original
        if any(abs(l) not in a for c in added for l in c):
            return False
        for desc, msg in ((old_desc, old), (new_desc, new)):
            if set(msg) != {'key', 'boundary', 'counts'} or msg['key'] != identity(desc) or msg['boundary'] != desc['boundary']:
                return False
            if len(msg['counts']) != 2**len(desc['boundary']):
                return False
            if any(type(v) is not str or not v.isascii() or not v.isdecimal() or str(int(v)) != v for v in msg['counts']):
                return False
        expected = {x: 0 for x in product((0, 1), repeat=len(b))}
        for bits in product((0, 1), repeat=len(a)):
            values = dict(zip(a, bits))
            if all(any(values[abs(l)] == int(l > 0) for l in row) for row in added):
                i = sum(v * 2**j for j, v in enumerate(bits))
                expected[tuple(values[v] for v in b)] += int(old['counts'][i])
        return all(new['counts'][sum(v * 2**j for j, v in enumerate(x))] == str(c)
                   for x, c in expected.items())
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError):
        return False
