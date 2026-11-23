"""CIG-003: source-derived nonlinear observer and rank-policy Ground.

Uses CIG-001's proven endpoint equality quotient, then factors actual CNF
couplings into bounded independent components. Learns local *nonlinear* gate
ANFs from original clauses; conditional matrix ranks are computed exactly.
Intentions are source SAT, #SAT, and selected cut-rank observation policy.
The experimental policy's measurement prices are declared, not sensor evidence.
"""
from __future__ import annotations

from itertools import combinations, product
from time import perf_counter_ns

from cut_intention import GroundRefusal, analyze, digest, make_source
from coupled_ground import SCHEMA as COUPLED_SCHEMA, _cut

SCHEMA='ifs.cig003.nonlinear-observer-ground.v1'
MAX_ACTIVE=96
MAX_COMPONENT=9
MAX_CANDIDATES=4
MAX_POLICIES=2


def _accepts(clauses, bits):
    return all(any(((bits >> (abs(l)-1)) & 1) == (l>0) for l in clause) for clause in clauses)


def source_reduce(source):
    """Derive active-label CNF by replaying every original endpoint equality."""
    if type(source) is not dict or set(source)!={'schema','base','coupling'} or source['schema']!=COUPLED_SCHEMA:
        raise GroundRefusal('unqualified coupled source')
    proof=analyze(source['base'])
    extra=source['coupling'];n=source['base']['n']
    if (type(extra) is not list or len(extra)>512 or
        any(type(cl) is not list or len(cl)>3 or
            any(type(v) is not int or v==0 or abs(v)>n for v in cl) for cl in extra)):
        raise GroundRefusal('invalid source coupling or clause budget')
    by_copy={copy:i for i,pair in enumerate(proof['pairs']) for copy in pair}
    derived=set()
    for clause in extra:
        rel={ (by_copy[abs(l)]+1)*(1 if l>0 else -1) for l in clause}
        if any(-l in rel for l in rel):continue
        derived.add(tuple(sorted(rel,key=lambda x:(abs(x),x<0))))
    derived=tuple(sorted(derived,key=lambda c:(len(c),c)))
    active=tuple(sorted({abs(l)-1 for cl in derived for l in cl}))
    if len(active)>MAX_ACTIVE:
        raise GroundRefusal('active coordinate budget exceeded')
    idx={v:i+1 for i,v in enumerate(active)}
    clauses=tuple(tuple((1 if l>0 else -1)*idx[abs(l)-1] for l in cl) for cl in derived)
    return proof,active,clauses


def _components(clauses,n):
    parent=list(range(n))
    def find(v):
        while parent[v]!=v:
            parent[v]=parent[parent[v]]
            v=parent[v]
        return v
    for clause in clauses:
        vs=[abs(l)-1 for l in clause]
        for v in vs[1:]:
            a,b=find(vs[0]),find(v)
            if a!=b:parent[max(a,b)]=min(a,b)
    sets={}
    for v in range(n):sets.setdefault(find(v),[]).append(v)
    result=[]
    for values in sorted(sets.values(),key=lambda vs:vs[0]):
        if len(values)>MAX_COMPONENT:raise GroundRefusal('discovered source component exceeds exact-local budget')
        tr={v:i+1 for i,v in enumerate(values)}
        local=[tuple((1 if l>0 else -1)*tr[abs(l)-1] for l in cl)
               for cl in clauses if abs(cl[0])-1 in tr]
        result.append({'variables':values,'clauses':[list(cl) for cl in local]})
    if not result and n:raise GroundRefusal('uncovered source variables')
    return result


def _rank_vectors(rows):
    pivots={}
    for row in rows:
        while row:
            bit=row.bit_length()-1
            if bit not in pivots:
                pivots[bit]=row;break
            row ^= pivots[bit]
    return len(pivots)


def _local_rank(comp,sides,observed=None):
    """Compute exact GF(2) flattening rank, including shared crossing labels."""
    observed=observed or {}
    parts={s:[] for s in 'LRC'}
    for index,v in enumerate(comp['variables']):parts[sides[v]].append(index)
    rank=0
    for cv in range(1<<len(parts['C'])):
        cross=sum(((cv>>j)&1)<<pos for j,pos in enumerate(parts['C']))
        rows=[]
        for lv in range(1<<len(parts['L'])):
            left=cross|sum(((lv>>j)&1)<<pos for j,pos in enumerate(parts['L']))
            row=0
            for rv in range(1<<len(parts['R'])):
                bits=left|sum(((rv>>j)&1)<<pos for j,pos in enumerate(parts['R']))
                if all((bits>>i)&1==v for i,v in observed.items()) and _accepts(comp['clauses'],bits):
                    row |= 1<<rv
            rows.append(row)
        rank+=_rank_vectors(rows)
    return rank


def _local_models(comp):
    masks=[x for x in range(1<<len(comp['variables'])) if _accepts(comp['clauses'],x)]
    return masks


def _anf(table, inputs):
    coeff=list(table)
    for bit in range(len(inputs)):
        for pos in range(1<<len(inputs)):
            if pos&(1<<bit):coeff[pos]^=coeff[pos^(1<<bit)]
    return [str(sum(1<<inputs[j] for j in range(len(inputs)) if mask>>j&1))
            for mask,c in enumerate(coeff) if c]


def _discover_gates(comps):
    """Prove disjoint arity-two nonlinear functions from original local CNF."""
    found=[]
    for comp_idx,comp in enumerate(comps):
        triples=sorted({tuple(sorted({abs(l)-1 for l in cl})) for cl in comp['clauses']
                        if len({abs(l) for l in cl})==3})
        used=set()
        for triple in triples:
            if len(triple)!=3 or any(v in used for v in triple):continue
            candidate=[]
            for out in triple:
                inputs=tuple(v for v in triple if v!=out)
                selected=tuple(cl for cl in comp['clauses']
                    if out+1 in [abs(l) for l in cl] and
                    {abs(l)-1 for l in cl}.issubset(set(triple)))
                if not selected:continue
                table=[]
                for value in range(4):
                    possible=[]
                    for b in (0,1):
                        bits=sum(((value>>j)&1)<<v for j,v in enumerate(inputs))|(b<<out)
                        if _accepts(selected,bits):possible.append(b)
                    if len(possible)!=1:break
                    table.append(possible[0])
                if len(table)!=4:continue
                if not all(any(table[x]!=table[x^(1<<i)] for x in range(4)) for i in range(2)):
                    continue
                anf=_anf(table,inputs)
                if max((int(m).bit_count() for m in anf),default=0)<2:continue
                candidate.append((out,inputs,table,selected,anf))
            if candidate:
                out,inputs,table,selected,anf=max(candidate,key=lambda a:a[0])
                used.update(triple)
                found.append({'component':comp_idx,'output_index':comp['variables'][out],
                    'inputs_indices':[comp['variables'][v] for v in inputs],
                    'table':table,'anf_masks':[
                        str(sum(1<<comp['variables'][p] for p in range(len(comp['variables']))
                                if int(m)>>p&1)) for m in anf],
                    'proof_clauses':[list(c) for c in selected],
                    'feature_basis':['original-output','nonlinear-anf'],
                    'pullback_matrix_rows':[2,2]})
    return sorted(found,key=lambda g:g['output_index'])


def _bridge_scores(comps,n):
    graph={v:set() for v in range(n)}
    for comp in comps:
        for cl in comp['clauses']:
            scope=[comp['variables'][abs(x)-1] for x in cl]
            for v in scope:graph[v].update(set(scope)-{v})
    def count(removed):
        todo=set(graph)-set(removed);total=0
        while todo:
            total+=1;stack=[todo.pop()]
            while stack:
                v=stack.pop()
                for nxt in graph[v]:
                    if nxt in todo:todo.remove(nxt);stack.append(nxt)
        return total
    baseline=count(())
    return {v:count((v,))-baseline for v in range(n)}


def _conditional_rank(comps,sides,inactive_cross,observations):
    value=1<<inactive_cross
    for comp in comps:
        fixed={i:observations[v] for i,v in enumerate(comp['variables']) if v in observations}
        value*=_local_rank(comp,sides,fixed)
        if not value:break
    return value


def _choose_policy(comps,sides,inactive_cross,gates,n,max_observations,native_price,anf_price):
    scores=_bridge_scores(comps,n)
    candidates=sorted((g for g in gates if scores[g['output_index']]>0),
                      key=lambda g:(-scores[g['output_index']],
                         sides[g['output_index']]!='C',g['output_index']))[:MAX_CANDIDATES]
    candidates=[g['output_index'] for g in candidates]
    alternatives=[]
    for size in range(min(max_observations,len(candidates))+1):
        for subset in combinations(candidates,size):
            outcomes=[]
            for state in range(1<<size):
                obs={v:(state>>j)&1 for j,v in enumerate(subset)}
                outcomes.append(str(_conditional_rank(comps,sides,inactive_cross,obs)))
            worst=max(map(int,outcomes),default=0)
            bits=(worst-1).bit_length() if worst else 0
            cost=min(native_price,anf_price)*len(subset)
            methods={str(v):('derived-anf' if anf_price<=native_price else 'native-output')
                     for v in subset}
            alternatives.append({'observe_indices':list(subset),'methods':methods,
                'outcome_ranks':outcomes,'worst_rank':str(worst),
                'worst_rank_bits':bits,'measurement_cost':cost,
                'total_declared_cost':bits+cost})
    chosen=min(alternatives,key=lambda a:(a['total_declared_cost'],
        len(a['observe_indices']),a['observe_indices']))
    return {'candidate_indices':candidates,'bridge_scores':{str(v):scores[v] for v in candidates},
            'selected':chosen,'alternatives':alternatives,
            'cost_contract':{'native_output':native_price,'derived_anf':anf_price,
                'units':'declared measurement-bit-equivalent price + ceil(log2 worst conditional rank)',
                'no_actual_measurement':True}}


def make_gated_source(groups=8,k=12,ell=1):
    """Ordinary source CNF; gates are encoded, never annotated for the compiler."""
    if type(groups) is not int or not 2<=groups<=8:
        raise ValueError('fixture groups bound')
    base=make_source(k,ell);proof=analyze(base);cut=tuple(range(k//2))
    classes=_cut(proof,cut)
    bins={c:[i for i,s in enumerate(classes) if s==c] for c in 'LRC'}
    if (len(bins['C'])<groups or len(bins['L'])<groups or len(bins['R'])<groups):
        raise ValueError('fixture cut lacks sufficient independent edge-label positions')
    # Disjoint AND gates, half fed by left-private input labels, half right-private.
    left_count=(groups+1)//2
    pairs=[(bins['L'][2*i],bins['L'][2*i+1]) for i in range(left_count)]
    pairs += [(bins['R'][2*i],bins['R'][2*i+1]) for i in range(groups-left_count)]
    outputs=bins['C'][:groups]
    coupling=[]
    for out,(a,b) in zip(outputs,pairs):
        x,y,z=(proof['pairs'][j][0] for j in (a,b,out))
        coupling.extend([[-z,x],[-z,y],[z,-x,-y]])
    # One real edge between source-derived nonlinear outputs from separate hosts.
    coupling.append([proof['pairs'][outputs[0]][0],proof['pairs'][outputs[left_count]][0]])
    return {'schema':COUPLED_SCHEMA,'base':base,'coupling':coupling},cut


def compile_ground(source,cut,*,max_observations=2,native_price=2,anf_price=0):
    start=perf_counter_ns()
    if (type(max_observations) is not int or not 0<=max_observations<=MAX_POLICIES or
        any(type(q) is not int or not 0<=q<=100 for q in (native_price,anf_price))):
        raise GroundRefusal('invalid observation policy budget')
    proof,active,clauses=source_reduce(source)
    if () in clauses:
        raise GroundRefusal('empty clause: use existing direct contradiction verifier')
    sides_all=_cut(proof,cut)
    sides=tuple(sides_all[v] for v in active)
    comps=_components(clauses,len(active))
    if () in clauses:
        model_count=0;witness=None
    else:
        masks=[_local_models(c) for c in comps]
        model_count=1
        for a in masks:model_count*=len(a)
        witness=None
        if model_count:
            bits=0
            for comp,models in zip(comps,masks):
                z=models[0]
                bits|=sum(((z>>j)&1)<<v for j,v in enumerate(comp['variables']))
            values={active[j]:(bits>>j)&1 for j in range(len(active))}
            witness=[values.get(j,0) for j in range(len(proof['pairs'])) for _ in range(2)]
            # Pair order is not necessarily variable order: rebuild from labels.
            original=[0]*source['base']['n']
            for j,(a,b) in enumerate(proof['pairs']):
                original[a-1]=original[b-1]=values.get(j,0)
            witness=original
            if not all(any(witness[abs(l)-1]==int(l>0) for l in c)
                       for c in source['base']['clauses']+source['coupling']):
                raise GroundRefusal('generated witness rejected by original source')
    total_count=model_count<<(len(proof['pairs'])-len(active))
    inactive_cross=sum(s=='C' for s in sides_all)-sum(s=='C' for s in sides)
    rank=_conditional_rank(comps,sides,inactive_cross,{}) if model_count else 0
    gates=_discover_gates(comps)
    policy=_choose_policy(comps,sides,inactive_cross,gates,len(active),
                          max_observations,native_price,anf_price)
    certificate={'schema':SCHEMA,'source_sha256':digest(source),
        'cut':list(cut),'active_labels':list(active),
        'reduced_clauses':[list(c) for c in clauses],
        'components':[{**c,'solutions':str(len(_local_models(c))),
                        'cut_rank':str(_local_rank(c,sides))} for c in comps],
        'gates':gates,'nonlinear_gate_count':len(gates),
        'result':{'status':'SAT' if model_count else 'UNSAT',
                  'count':str(total_count),'rank':str(rank),'witness':witness,
                  'inactive_crossing_labels':inactive_cross},
        'observation_policy':policy,
        'limits':{'max_observations':max_observations},
        'ledger':{'enumerated_component_states':sum(1<<len(c['variables']) for c in comps),
                  'global_active_state_count':str(1<<len(active)),
                  'candidate_gates':len(gates),
                  'policy_branches':sum(len(a['outcome_ranks']) for a in policy['alternatives'])}}
    return certificate,{'elapsed_ns':perf_counter_ns()-start}
