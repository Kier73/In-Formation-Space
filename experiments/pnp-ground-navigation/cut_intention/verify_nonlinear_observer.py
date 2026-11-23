"""CIG-003 independent original-CNF receiver audit.

No import from the CIG-003 compiler. Separately replays disjoint endpoint
implications, source clause translation, connected-component decomposition,
local-model counting, column-space rank, exact nonlinear functions, policy
ranking and full certificate identity. No physical observation is admitted.
"""
from __future__ import annotations
from collections import Counter
from itertools import combinations
import hashlib
import json


class Refused(ValueError):pass


def _hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),
                            allow_nan=False).encode()).hexdigest()


def _source(source,cut):
    if (type(source) is not dict or set(source)!={'schema','base','coupling'}
        or source['schema']!='ifs.cut-intention-coupled-source.v1'):
        raise Refused('unrecognized source')
    b=source['base'];n=b.get('n');nodes=b.get('nodes');original=b.get('clauses')
    if (type(n) is not int or not 2<=n<=18720 or type(nodes) is not list or
        not 2<=len(nodes)<=40 or type(original) is not list or len(original)!=n):
        raise Refused('invalid original basis')
    if any(type(g) is not list for g in nodes):raise Refused('malformed nodes')
    ordered=[v for g in nodes for v in g]
    if any(type(v) is not int for v in ordered) or sorted(ordered)!=list(range(1,n+1)):
        raise Refused('node partition invalid')
    place={v:i for i,g in enumerate(nodes) for v in g}
    clauses=[]
    for c in original:
        if type(c) is not list or len(c)!=2 or any(type(l) is not int or not 1<=abs(l)<=n for l in c):
            raise Refused('malformed endpoint clause')
        clauses.append(tuple(sorted(c)))
    clauses=set(clauses)
    edges={}
    for c in clauses:
        if len(c)!=2 or c[0]>=0 or c[1]<=0 or abs(c[0])==c[1]:
            raise Refused('non-equivalence source')
        e=tuple(sorted((-c[0],c[1])))
        edges.setdefault(e,set()).add(c)
    pairs=sorted(edges)
    if (len(pairs)*2!=n or
        sorted(x for pair in pairs for x in pair)!=list(range(1,n+1)) or
        any(edges[(x,y)]!={(-x,y),(-y,x)} for x,y in pairs)):
        raise Refused('unproved endpoint equality')
    k=len(nodes);sizes=Counter(tuple(sorted((place[a],place[b]))) for a,b in pairs)
    widths=[sizes[a,b] for a in range(k) for b in range(a+1,k)]
    if (any(place[a]==place[b] for a,b in pairs) or
        min(widths)<1 or len(set(widths))!=1):
        raise Refused('not a uniform complete observer graph')
    if (type(cut) not in (list,tuple) or not 0<len(cut)<k or
        any(type(v) is not int for v in cut) or list(cut)!=sorted(set(cut))
        or cut[0]<0 or cut[-1]>=k):raise Refused('invalid observation cut')
    extra=source['coupling']
    if (type(extra) is not list or len(extra)>512 or
       any(type(c) is not list or len(c)>3 or
           any(type(l) is not int or l==0 or abs(l)>n for l in c) for c in extra)):
        raise Refused('invalid added original clauses')
    by_var={v:j for j,pair in enumerate(pairs) for v in pair}
    transformed=set()
    for c in extra:
        lifted={ (by_var[abs(l)]+1) * (1 if l>0 else -1) for l in c}
        if not any(-l in lifted for l in lifted):
            transformed.add(tuple(sorted(lifted,key=lambda l:(abs(l),l<0))))
    clauses=sorted(transformed,key=lambda c:(len(c),c))
    active=sorted({abs(l)-1 for c in clauses for l in c})
    if len(active)>96 or () in clauses:raise Refused('unsupported active/empty clause budget')
    renumber={v:i+1 for i,v in enumerate(active)}
    res=[tuple((1 if l>0 else -1)*renumber[abs(l)-1] for l in c) for c in clauses]
    S=set(cut)
    sides=['C' if (place[a] in S)!=(place[b] in S)
         else ('L' if place[a] in S else 'R') for a,b in pairs]
    return pairs,active,res,sides


def _parts(clauses,n):
    near=[set() for _ in range(n)]
    for c in clauses:
        ids={abs(x)-1 for x in c}
        for v in ids:near[v]|=ids-{v}
    pending=set(range(n));pieces=[]
    while pending:
        start=min(pending);pending.remove(start);queue=[start];members={start}
        while queue:
            for v in near[queue.pop()]:
                if v in pending:pending.remove(v);queue.append(v);members.add(v)
        vs=sorted(members)
        if len(vs)>9:raise Refused('component budget')
        indexed={v:i+1 for i,v in enumerate(vs)}
        rows=[[indexed[abs(l)-1]*(1 if l>0 else -1) for l in c]
              for c in clauses if c and abs(c[0])-1 in indexed]
        pieces.append({'variables':vs,'clauses':rows})
    return sorted(pieces,key=lambda item:item['variables'][0])


def _satisfies(clauses,bits):
    return all(any((bool(bits>>(abs(l)-1)&1)==(l>0)) for l in row) for row in clauses)


def _rank(comp,sides,known):
    vars=comp['variables']
    C=[j for j,v in enumerate(vars) if sides[v]=='C']
    L=[j for j,v in enumerate(vars) if sides[v]=='L']
    R=[j for j,v in enumerate(vars) if sides[v]=='R']
    result=0
    for c in range(1<<len(C)):
        cm=sum(((c>>j)&1)<<p for j,p in enumerate(C))
        cols=[]
        for rv in range(1<<len(R)):
            rm=cm|sum(((rv>>j)&1)<<p for j,p in enumerate(R))
            col=0
            for lv in range(1<<len(L)):
                bits=rm|sum(((lv>>j)&1)<<p for j,p in enumerate(L))
                if (all((bits>>i)&1 == value for i,value in known.items()) and
                    _satisfies(comp['clauses'],bits)):
                    col |= 1<<lv
            cols.append(col)
        # Column elimination with lowest active pivot, rather than the producer's rows.
        pivots={}
        for v in cols:
            while v:
                p=(v&-v).bit_length()-1
                if p not in pivots:pivots[p]=v;break
                v^=pivots[p]
        result+=len(pivots)
    return result


def _gates(pieces):
    result=[]
    for i,comp in enumerate(pieces):
        cset=[tuple(cl) for cl in comp['clauses']]
        supports={tuple(sorted({abs(l)-1 for l in row})) for row in cset if len(set(abs(l) for l in row))==3}
        used=set()
        for triple in sorted(supports):
            if len(triple)!=3 or used.intersection(triple):continue
            options=[]
            for out in triple:
                inp=tuple(j for j in triple if j!=out)
                proof=tuple(row for row in cset if out+1 in (abs(l) for l in row)
                          and all(abs(l)-1 in triple for l in row))
                if not proof:continue
                vals=[]
                for bits in range(4):
                    allowed=[]
                    for z in (0,1):
                        mask=(z<<out)|sum(((bits>>j)&1)<<v for j,v in enumerate(inp))
                        if _satisfies(proof,mask):allowed.append(z)
                    if len(allowed)!=1:break
                    vals.append(allowed[0])
                if len(vals)!=4 or not (vals[0]!=vals[1] or vals[2]!=vals[3]) or not (vals[0]!=vals[2] or vals[1]!=vals[3]):
                    continue
                f0,f1,f2,f3=vals
                co=[f0,f0^f1,f0^f2,f0^f1^f2^f3]
                if not co[3]:continue # genuinely nonlinear in the discovered two inputs
                masks=[str(sum(1<<comp['variables'][v] for j,v in enumerate(inp) if code>>j&1))
                        for code,bit in enumerate(co) if bit]
                options.append((out,inp,vals,proof,masks))
            if options:
                out,inp,vals,proof,anf=max(options,key=lambda a:a[0])
                used.update(triple)
                result.append({'component':i,'output_index':comp['variables'][out],
                    'inputs_indices':[comp['variables'][v] for v in inp],
                    'table':vals,'anf_masks':anf,'proof_clauses':[list(cl) for cl in proof],
                    'feature_basis':['original-output','nonlinear-anf'],
                    'pullback_matrix_rows':[2,2]})
    return sorted(result,key=lambda g:g['output_index'])


def _bridge(pieces,n):
    near=[set() for _ in range(n)]
    for comp in pieces:
        for row in comp['clauses']:
            nodes={comp['variables'][abs(l)-1] for l in row}
            for v in nodes:near[v].update(nodes-{v})
    def components(omitted):
        pending=set(range(n))-{omitted};ans=0
        while pending:
            ans+=1;stack=[pending.pop()]
            while stack:
                for u in near[stack.pop()]:
                    if u in pending:pending.remove(u);stack.append(u)
        return ans
    b=components(-1)
    return {v:components(v)-b for v in range(n)}


def verify(source,cert):
    try:
        if type(cert) is not dict or cert.get('schema')!='ifs.cig003.nonlinear-observer-ground.v1':
            raise Refused('unknown certificate')
        pairs,active,clauses,all_sides=_source(source,cert['cut'])
        n=len(active);pieces=_parts(clauses,n)
        side=[all_sides[v] for v in active]
        counted=1;models=[]
        items=[]
        for comp in pieces:
            approved=[m for m in range(1<<len(comp['variables'])) if _satisfies(comp['clauses'],m)]
            models.append(approved)
            counted*=len(approved)
            items.append({**comp,'solutions':str(len(approved)),
                          'cut_rank':str(_rank(comp,side,{}))})
        inactive=sum(s=='C' for s in all_sides)-sum(s=='C' for s in side)
        full_rank=1<<inactive
        for comp in pieces:full_rank*=_rank(comp,side,{})
        witness=None
        if counted:
            selected={}
            for comp,possibilities in zip(pieces,models):
                m=possibilities[0]
                selected.update({active[v]:(m>>i)&1 for i,v in enumerate(comp['variables'])})
            witness=[0]*source['base']['n']
            for j,(x,y) in enumerate(pairs):
                witness[x-1]=witness[y-1]=selected.get(j,0)
            if not all(any(witness[abs(l)-1]==int(l>0) for l in row)
                       for row in source['base']['clauses']+source['coupling']):
                raise Refused('witness fails original clauses')
        gates=_gates(pieces)
        scores=_bridge(pieces,n)
        candidate_gates=sorted((g for g in gates if scores[g['output_index']]>0),
                     key=lambda g:(-scores[g['output_index']],
                         side[g['output_index']]!='C',g['output_index']))[:4]
        candidates=[g['output_index'] for g in candidate_gates]
        policy=cert.get('observation_policy',{})
        c=policy.get('cost_contract',{})
        price1=c.get('native_output');price2=c.get('derived_anf')
        if any(type(v) is not int or not 0<=v<=100 for v in (price1,price2)):
            raise Refused('invalid declared measurement prices')
        alternatives=[]
        limit=cert.get('limits',{}).get('max_observations')
        if type(limit) is not int or not 0<=limit<=2:raise Refused('invalid policy depth')
        for r in range(min(limit,len(candidates))+1):
            for subset in combinations(candidates,r):
                outcome=[]
                for bits in range(1<<r):
                    constraints={v:(bits>>j)&1 for j,v in enumerate(subset)}
                    total=1<<inactive
                    for comp in pieces:
                        fixed={j:constraints[v] for j,v in enumerate(comp['variables']) if v in constraints}
                        total*=_rank(comp,side,fixed)
                    outcome.append(str(total))
                worst=max(map(int,outcome))
                width=(worst-1).bit_length() if worst else 0
                cost=min(price1,price2)*r
                alternatives.append({'observe_indices':list(subset),
                    'methods':{str(v):('derived-anf' if price2<=price1 else 'native-output') for v in subset},
                    'outcome_ranks':outcome,'worst_rank':str(worst),
                    'worst_rank_bits':width,'measurement_cost':cost,
                    'total_declared_cost':width+cost})
        selected=min(alternatives,key=lambda a:(a['total_declared_cost'],len(a['observe_indices']),a['observe_indices']))
        expected_policy={'candidate_indices':candidates,
            'bridge_scores':{str(v):scores[v] for v in candidates},
            'selected':selected,'alternatives':alternatives,
            'cost_contract':{'native_output':price1,'derived_anf':price2,
                'units':'declared measurement-bit-equivalent price + ceil(log2 worst conditional rank)',
                'no_actual_measurement':True}}
        expected={'schema':'ifs.cig003.nonlinear-observer-ground.v1',
            'source_sha256':_hash(source),'cut':list(cert['cut']),
            'active_labels':active,'reduced_clauses':[list(c) for c in clauses],
            'components':items,'gates':gates,'nonlinear_gate_count':len(gates),
            'result':{'status':'SAT' if counted else 'UNSAT',
                'count':str(counted<<(len(pairs)-len(active))),
                'rank':str(full_rank) if counted else '0',
                'witness':witness,'inactive_crossing_labels':inactive},
            'observation_policy':expected_policy,
            'limits':{'max_observations':limit},
            'ledger':{'enumerated_component_states':sum(1<<len(c['variables']) for c in pieces),
                'global_active_state_count':str(1<<len(active)),
                'candidate_gates':len(gates),
                'policy_branches':sum(len(a['outcome_ranks']) for a in alternatives)}}
        if expected!=cert:raise Refused('certificate does not match source-replayed evidence')
        return True
    except (KeyError,IndexError,TypeError,OverflowError,AttributeError) as e:
        raise Refused('malformed source or certificate') from e
