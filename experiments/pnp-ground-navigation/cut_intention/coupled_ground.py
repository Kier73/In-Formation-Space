"""CIG-002: source-bound bounded coupling over CIG-001's exact edge-label CNF.

The additional clauses are ORIGINAL-CNF clauses over endpoint copies.
The compiler proves every base equality from original clauses and translates
these added clauses into a smaller source-equivalent residual formula.
It can construct an exact SAT/#SAT/CUT_RANK Ground with a charged finite
active-label evaluation. No universal fast SAT or unrestricted rank claim.
"""
from __future__ import annotations

from math import gcd
from time import perf_counter_ns

from cut_intention import GroundRefusal, analyze, digest, make_source

SCHEMA = 'ifs.cut-intention-coupled-source.v1'
CERT_SCHEMA = 'ifs.cut-intention-coupled-ground.v1'
MAX_ACTIVE = 14
MAX_ADDED_CLAUSES = 128


def _check(source):
    if type(source) is not dict or set(source) != {'schema', 'base', 'coupling'} or source.get('schema') != SCHEMA:
        raise GroundRefusal('malformed coupled source')
    proof = analyze(source['base'])
    n = source['base']['n']
    extra = source['coupling']
    if type(extra) is not list or len(extra) > MAX_ADDED_CLAUSES:
        raise GroundRefusal('invalid residual-clause budget')
    for clause in extra:
        if type(clause) is not list or len(clause) > 3 or any(type(v) is not int or not 1 <= abs(v) <= n for v in clause):
            raise GroundRefusal('coupling must be source-valid bounded CNF')
    pairs = proof['pairs']
    variable_to_label = {v: i for i, pair in enumerate(pairs) for v in pair}
    normalized = []
    for clause in extra:
        lifted = set((variable_to_label[abs(x)] + 1) * (1 if x > 0 else -1) for x in clause)
        if any(-x in lifted for x in lifted):
            continue  # tautology after equality quotient; exact source equivalence
        normalized.append(tuple(sorted(lifted, key=lambda x: (abs(x), x < 0))))
    normalized = tuple(sorted(set(normalized), key=lambda c: (len(c),c)))
    active = tuple(sorted({abs(x)-1 for clause in normalized for x in clause}))
    if len(active) > MAX_ACTIVE:
        raise GroundRefusal('bounded active-label Ground refusal')
    renumber = {v:i+1 for i,v in enumerate(active)}
    reduced = tuple(tuple((1 if x>0 else -1)*renumber[abs(x)-1] for x in clause)
                    for clause in normalized)
    return proof, active, reduced


def _accepts(clauses, bits):
    return all(any(bool((bits >> (abs(l)-1)) & 1) == (l>0) for l in clause) for clause in clauses)


def _unpack(source, label_bits, pairs):
    result=[0]*source['base']['n']
    for i,(a,b) in enumerate(pairs):
        result[a-1] = result[b-1] = (label_bits >> i)&1
    return result


def source_accepts(source, witness):
    n=source['base']['n']
    if (type(witness) is not list or len(witness)!=n or
            any(type(x) is not int or x not in (0,1) for x in witness)):
        return False
    return all(any(witness[abs(l)-1] == int(l>0) for l in clause)
               for clause in source['base']['clauses']+source['coupling'])


def _cut(proof, cut):
    k=proof['k']
    if (type(cut) not in (tuple, list) or not cut or len(cut)==k or
            any(type(x) is not int for x in cut) or list(cut)!=sorted(set(cut)) or
            cut[0]<0 or cut[-1]>=k):
        raise GroundRefusal('canonical nontrivial observer cut required')
    S=set(cut)
    side=[]
    for a,b in proof['pairs']:
        first,second=proof['node_of'][a] in S,proof['node_of'][b] in S
        side.append('C' if first != second else ('L' if first else 'R'))
    return tuple(side)


def _rank(rows):
    """Exact characteristic-two row-space elimination; rows as bitvectors."""
    pivots={}
    for x in rows:
        while x:
            p=x.bit_length()-1
            if p not in pivots:
                pivots[p]=x
                break
            x ^= pivots[p]
    return len(pivots)


def compile_ground(source, intention, cut=None):
    start=perf_counter_ns()
    if intention not in ('SAT','#SAT','CUT_RANK'):
        raise GroundRefusal('unsupported intention')
    proof,active,reduced=_check(source)
    if intention=='CUT_RANK':
        sides=_cut(proof,cut)
        cross_total=sides.count('C')
        active_side=[sides[j] for j in active]
        C=[i for i,s in enumerate(active_side) if s=='C']
        L=[i for i,s in enumerate(active_side) if s=='L']
        R=[i for i,s in enumerate(active_side) if s=='R']
        work=0
        rows_examined=0
        factor=0
        # Each fixed crossing assignment defines one independent matrix block.
        for cross in range(1<<len(C)):
            fixed=sum(((cross>>i)&1)<<pos for i,pos in enumerate(C))
            matrix=[]
            for left in range(1<<len(L)):
                fixed_left=fixed|sum(((left>>i)&1)<<pos for i,pos in enumerate(L))
                row=0
                for right in range(1<<len(R)):
                    assignment=fixed_left|sum(((right>>i)&1)<<pos for i,pos in enumerate(R))
                    if _accepts(reduced,assignment): row|=1<<right
                    work+=1
                matrix.append(row)
                rows_examined+=1
            factor+=_rank(matrix)
        rank=factor << (cross_total-len(C))
        baseline=1<<cross_total
        common=gcd(rank,baseline)
        result={'rank':str(rank),'baseline_rank':str(baseline),
                'rank_ratio':[rank//common,baseline//common],
                'active_block_rank_sum':factor,
                'unrestricted_cross_labels':cross_total-len(C),
                'crossing_labels':cross_total}
        metadata={'active_side_labels':{'L':len(L),'R':len(R),'C':len(C)},
                  'evaluated_reduced_assignments':work,
                  'matrix_rows_visited':rows_examined,
                  'enumeration_cost_bound':1<<len(active)}
    else:
        if cut is not None:
            raise GroundRefusal('SAT and #SAT have no cut parameter')
        status='UNSAT'
        count=0
        first=None
        examined=0
        for mask in range(1<<len(active)):
            examined+=1
            if _accepts(reduced,mask):
                status='SAT';count+=1
                if first is None: first=mask
                if intention=='SAT': break
        m=len(proof['pairs'])
        witness=None
        if first is not None:
            label_assignment=sum(((first>>i)&1)<<v for i,v in enumerate(active))
            witness=_unpack(source,label_assignment,proof['pairs'])
            if not source_accepts(source,witness):
                raise GroundRefusal('source rejected a generated witness')
        if intention=='SAT':
            result={'status':status,'witness':witness}
        else:
            result={'status':status,'count':str(count << (m-len(active))),
                    'free_unconstrained_labels':m-len(active), 'witness':witness}
        metadata={'active_side_labels':None,'evaluated_reduced_assignments':examined,
                  'matrix_rows_visited':0,'enumeration_cost_bound':1<<len(active)}
    cert={'schema':CERT_SCHEMA,'source_digest':digest(source),'base_digest':proof['source_digest'],
          'intention':intention,'cut':list(cut) if cut is not None else None,
          'label_pairs':[list(pair) for pair in proof['pairs']],
          'active_labels':list(active),'reduced_cnf':[list(c) for c in reduced],
          'result':result,'work':metadata}
    return cert,{'construct_ns':perf_counter_ns()-start,
                 'original_variables':source['base']['n'],
                 'original_clauses':len(source['base']['clauses'])+len(source['coupling']),
                 'active_label_count':len(active)}


def make_one_clause_source(k, ell, kind, cut=None):
    """Deterministic fixtures: add ONE actual clause using original copy variables."""
    base=make_source(k,ell)
    proof=analyze(base)
    S=tuple(range(k//2)) if cut is None else tuple(cut)
    sides=_cut(proof,S)
    bins={c:[proof['pairs'][i][0] for i,s in enumerate(sides) if s==c] for c in ('L','R','C')}
    if kind=='none': clause=[]
    elif kind=='cross-cross': clause=[*bins['C'][:2]]
    elif kind=='left-right': clause=[bins['L'][0],bins['R'][0]]
    elif kind=='left-cross': clause=[bins['L'][0],bins['C'][0]]
    elif kind=='right-cross': clause=[bins['R'][0],bins['C'][0]]
    else: raise ValueError('unknown fixture')
    if kind!='none' and len(clause)!=2:
        raise ValueError('fixture needs two labels from respective sides')
    return {'schema':SCHEMA,'base':base,'coupling':[clause] if clause else []},S
