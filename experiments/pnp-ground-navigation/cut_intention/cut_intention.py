"""CIG-001: source-derived, intention-specific exact Grounds of one CNF.

A graph has one independent bit per edge-label; its endpoint copies are forced
identical by *original* two-clause equivalences. No graph annotation is trusted
as an axiom: the source compiler re-derives the complete equality graph from
CNF, and a separate verifier independently reconstructs it.

Intents: SAT witness, exact #SAT, and exact coefficient-flattening cut rank.
Only this syntactically recognized source family is admitted. Complexity of
symbolic answers is not the cost of materializing the full relation tensor.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from time import perf_counter_ns

SCHEMA = 'ifs.cut-intention-source.v1'
GROUND_SCHEMA = 'ifs.cut-intention-ground.v1'
INTENTS = ('SAT', '#SAT', 'CUT_RANK')


class GroundRefusal(ValueError):
    """Source or observation contract does not satisfy the proved language."""


def digest(x):
    data = json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def make_source(k, label_bits=1):
    """Return a plain source CNF and its node-observer partition.

    The node partition declares *which observer sees which source variable*.
    It does not supply an equality proof or a privileged SAT answer.
    """
    if type(k) is not int or not 2 <= k <= 40 or type(label_bits) is not int or not 1 <= label_bits <= 12:
        raise ValueError('bounded integer graph size and label bits required')
    nodes = [[] for _ in range(k)]
    clauses = []
    var = 0
    for a in range(k):
        for b in range(a + 1, k):
            for _ in range(label_bits):
                x, y = var + 1, var + 2
                var += 2
                nodes[a].append(x)
                nodes[b].append(y)
                clauses.extend([[-x, y], [x, -y]])
    return {'schema': SCHEMA, 'n': var, 'clauses': clauses, 'nodes': nodes}


def source_accepts(source, bits):
    """Evaluate *the supplied original CNF*, independent of Grounds."""
    if len(bits) != source['n'] or any(b not in (0, 1) for b in bits):
        return False
    return all(any(bits[abs(lit) - 1] == (1 if lit > 0 else 0)
                   for lit in clause) for clause in source['clauses'])


def analyze(source):
    """Syntactically prove exactly one disjoint equality per source var pair."""
    if (type(source) is not dict or set(source) != {'schema','n','clauses','nodes'}
            or source.get('schema') != SCHEMA or type(source['n']) is not int
            or not 2 <= source['n'] <= 40 * 39 * 12):
        raise GroundRefusal('malformed source')
    n, groups = source['n'], source['nodes']
    if (not isinstance(groups, list) or not 2 <= len(groups) <= 40 or
            any(not isinstance(g, list) for g in groups) or
            any(type(v) is not int for g in groups for v in g) or
            sorted(v for g in groups for v in g) != list(range(1, n+1))):
        raise GroundRefusal('node observers must partition source variables')
    node_of = {v: i for i, group in enumerate(groups) for v in group}
    clauses = source['clauses']
    if not isinstance(clauses, list) or len(clauses) != n:
        raise GroundRefusal('expected two binary clauses per equality pair')
    directions = defaultdict(set)
    for clause in clauses:
        if (not isinstance(clause, list) or len(clause) != 2 or
                any(type(v) is not int or not 1 <= abs(v) <= n for v in clause) or
                clause[0] * clause[1] >= 0 or abs(clause[0]) == abs(clause[1])):
            raise GroundRefusal('non-equivalence or malformed source clause')
        neg = next(abs(v) for v in clause if v < 0)
        pos = next(v for v in clause if v > 0)
        pair = (min(neg, pos), max(neg, pos))
        direction = (neg, pos)
        if direction in directions[pair]:
            raise GroundRefusal('duplicate directed clause')
        directions[pair].add(direction)
    pairs = sorted(directions)
    if len(pairs) * 2 != n:
        raise GroundRefusal('missing equality edge')
    if any(ds != {(a,b),(b,a)} for (a,b),ds in directions.items()):
        raise GroundRefusal('unpaired equivalence clause')
    count = Counter(v for pair in pairs for v in pair)
    if count != Counter({v: 1 for v in range(1, n + 1)}):
        raise GroundRefusal('equality pairs share or omit variables')
    edge_hist = Counter()
    for a,b in pairs:
        if node_of[a] == node_of[b]:
            raise GroundRefusal('equality pair must cross distinct node observers')
        edge_hist[tuple(sorted((node_of[a], node_of[b])))] += 1
    k = len(groups)
    values = [edge_hist.get((a,b),0) for a in range(k) for b in range(a+1,k)]
    if not values or min(values) < 1 or len(set(values)) != 1:
        raise GroundRefusal('source is not a complete, uniformly labeled graph')
    return {'k':k, 'label_bits':values[0], 'pairs':pairs,
            'node_of':node_of, 'source_digest':digest(source)}


def cut_geometry(k, selected):
    """Exact integer hub coefficients are twice the Euclidean coordinates."""
    S = set(selected)
    twice = []
    for a in range(k):
        suffix = range(a+1,k)
        twice.append(sum(b not in S for b in suffix) if a in S
                     else -sum(b in S for b in suffix))
    crossing = len(S)*(k-len(S))
    assert sum(abs(x) for x in twice) == crossing
    # k*sum((2v)^2)>=crossing^2 is exact Cauchy-Schwarz.
    assert k*sum(x*x for x in twice) >= crossing*crossing
    return {'hub_twice':twice,'hub_norm_sq_numerator':sum(x*x for x in twice),
            'hub_norm_sq_denominator':4,'hub_l1_twice':crossing,
            'geometric_cauchy_checked':True}


def compile_ground(source, intention, cut=None):
    start = perf_counter_ns()
    if intention not in INTENTS:
        raise GroundRefusal('unknown observer intention')
    proof = analyze(source)
    k, l = proof['k'], proof['label_bits']
    if intention == 'CUT_RANK':
        if (not isinstance(cut, (tuple,list)) or any(type(v) is not int for v in cut)
                or sorted(set(cut)) != list(cut) or not 0 < len(cut) < k
                or cut[0] < 0 or cut[-1] >= k):
            raise GroundRefusal('a nontrivial canonical node cut is required')
        cross_edges = len(cut)*(k-len(cut))
        exponent = l * cross_edges
        result = {'rank':str(1 << exponent), 'log2_rank':exponent,
                  'flattening_row_bits':sum(len(source['nodes'][i]) for i in cut),
                  'flattening_col_bits':sum(len(source['nodes'][i]) for i in range(k) if i not in cut),
                  'matrix_entry_log2':source['n']}
        geometry = cut_geometry(k,cut)
    else:
        if cut is not None:
            raise GroundRefusal('a node cut is only defined for CUT_RANK')
        cross_edges = 0
        geometry = None
        if intention == 'SAT':
            result = {'status':'SAT', 'witness':[0]*source['n']}
            if not source_accepts(source,result['witness']):
                raise GroundRefusal('constructed witness rejected by original clauses')
        else:
            result = {'status':'SAT','count':str(1 << len(proof['pairs'])),
                      'free_label_bits':len(proof['pairs'])}
    ground = {'schema':GROUND_SCHEMA, 'source_digest':proof['source_digest'],
              'intention':intention,'cut':list(cut) if cut is not None else None,
              'proof':{'variable_equalities':[list(pair) for pair in proof['pairs']],
                       'node_count':k,'label_bits_per_edge':l,
                       'crossing_edges':cross_edges},
              'result':result,'geometry':geometry}
    return ground, {'construct_ns':perf_counter_ns()-start,
                    'source_variables':source['n'], 'source_clauses':len(source['clauses']),
                    'symbolic_certificate_bytes':len(json.dumps(ground,separators=(',', ':')).encode()),
                    'input_digest':proof['source_digest']}


def min_balanced_hub_norm_sq_numerator(k):
    """Exact O(k^2)-state suffix DP for min 4||v_S||²; no 2^k enumeration."""
    if type(k) is not int or not 2 <= k <= 512:
        raise ValueError('k outside exact DP envelope')
    state = {0:0}
    for t in range(k):
        new = {}
        for r, cost in state.items():
            for bit in (0,1):
                newr = r+bit
                nxt = cost + (bit*t-r)**2
                if newr not in new or nxt < new[newr]:
                    new[newr] = nxt
        state = new
    lo = (k+2)//3  # ceil(k/3)
    hi = (2*k)//3
    return min(state[s] for s in range(lo,hi+1))
