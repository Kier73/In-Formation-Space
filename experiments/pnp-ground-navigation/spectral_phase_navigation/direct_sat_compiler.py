#!/usr/bin/env python3
"""SPN-008: direct CNF SAT, proof-carrying DPLL and source-checked XOR Grounds.

No solver status is verified by an author's chosen strategy or telemetry.
SAT witnesses check against original CNF. UNSAT has a complete DPLL
conflict tree or a GF(2) contradictory dependency over truth-table verified
XOR blocks. UNKNOWN is a budget refusal, not a decision.

Clauses are standard DIMACS-style sequences of signed, one-based integers.
No external solver dependency. No polynomial bound for unrestricted SAT.
"""
from __future__ import annotations

from hashlib import sha256
import json
from time import perf_counter

VERSION = 'SPN-008-direct-sat-v1'


def validate_cnf(clauses, n):
    if type(n) is not int or n < 1:
        raise ValueError('n must be a positive integer')
    if not isinstance(clauses, (list,tuple)):
        raise ValueError('CNF must be a sequence')
    for clause in clauses:
        if not isinstance(clause,(list,tuple)) or len(clause)>3:
            raise ValueError('CNF requires width at most three')
        if any(type(lit) is not int or lit==0 or abs(lit)>n for lit in clause):
            raise ValueError('invalid CNF literal')


def source_digest(clauses,n):
    validate_cnf(clauses,n)
    data=json.dumps({'n':n,'clauses':[list(c) for c in clauses]},
                    sort_keys=True,separators=(',',':'))
    return sha256(data.encode()).hexdigest()


def check_assignment(clauses, bits):
    return all(any(bits[abs(lit)-1] == int(lit>0) for lit in clause)
               for clause in clauses)


def spectral_form(clauses,n):
    """Convert exact-3-DISTINCT CNF to the SPN forbidden-bit encoding.

    None means not eligible, never an approximation or inferred SAT status.
    """
    validate_cnf(clauses,n)
    out=[]
    for clause in clauses:
        if len(clause)!=3 or len({abs(t) for t in clause})!=3:
            return None
        ordered=sorted(clause,key=lambda x:abs(x))
        out.append((tuple(abs(l)-1 for l in ordered),
                    tuple(int(l<0) for l in ordered)))
    return out


def parity_blocks(clauses,n):
    """Recognize if EVERY source clause is part of a complete XOR truth table.

    For a scope of k<=3 variables, a forbidden parity class has 2^(k-1)
    rows. Their conjunction is exactly XOR(scope)==1^forbidden_parity.
    Duplicates are collapsed, but all different patterns must match one class.
    This rejects every partial/mixed support group and all tautologies.
    """
    validate_cnf(clauses,n)
    grouped={}
    for raw_clause in clauses:
        if not raw_clause:
            return None
        # Truth-preserving source normalization: duplicate literals do not
        # change a disjunction, and a tautological clause can be omitted.
        literals=set(raw_clause)
        if any(-lit in literals for lit in literals):
            continue
        indices=[abs(l)-1 for l in literals]
        scope=tuple(sorted(indices))
        truth={abs(l)-1:int(l<0) for l in literals}
        pattern=tuple(truth[v] for v in scope)
        grouped.setdefault(scope,set()).add(pattern)
    equations=[]
    for scope,patterns in sorted(grouped.items()):
        k=len(scope)
        if len(patterns)!=1<<(k-1):
            return None
        forbidden={sum(pattern)&1 for pattern in patterns}
        if len(forbidden)!=1:
            return None
        expected={tuple((mask>>j)&1 for j in range(k))
                  for mask in range(1<<k) if (mask.bit_count()&1) in forbidden}
        if patterns!=expected:
            return None
        equations.append((sum(1<<v for v in scope), 1^next(iter(forbidden))))
    return equations



def _verify_xor_encoding_by_truth_table(clauses,n):
    """Verifier-side semantic XOR recognition, distinct from producer scan.

    Independently evaluate each scope's source clauses on all 2^k local
    assignments and require that their conjunction equals ONE parity
    equation. A producer-supplied list of equations is never trusted.
    """
    validate_cnf(clauses,n)
    scopes={}
    for clause in clauses:
        if not clause:
            return None
        if any(-lit in clause for lit in clause):
            continue   # tautology for all assignments
        scope=tuple(sorted({abs(lit)-1 for lit in clause}))
        scopes.setdefault(scope,[]).append(clause)
    equations=[]
    for scope,local_clauses in sorted(scopes.items()):
        allowed=[]
        for bits in range(1<<len(scope)):
            assignment={v+1:(bits>>i)&1 for i,v in enumerate(scope)}
            if all(any(assignment[abs(lit)]==int(lit>0)
                       for lit in clause) for clause in local_clauses):
                allowed.append(bits)
        if not allowed:
            return None
        allowed_parities={bits.bit_count()&1 for bits in allowed}
        if len(allowed_parities)!=1 or len(allowed)!=(1<<(len(scope)-1)):
            return None
        equations.append((sum(1<<v for v in scope),next(iter(allowed_parities))))
    return equations

def gaussian_ground(equations,n):
    """Construct satisfying XOR assignment or a contradictory row dependency."""
    pivots={}
    for index,(mask,rhs) in enumerate(equations):
        v,bit,trace=mask,rhs,1<<index
        while v:
            p=v.bit_length()-1
            if p not in pivots:
                pivots[p]=(v,bit,trace)
                break
            old,old_rhs,old_trace=pivots[p]
            v^=old;bit^=old_rhs;trace^=old_trace
        if not v and bit:
            return {'kind':'xor_unsat',
                    'conflict_indices':[j for j in range(len(equations)) if trace>>j&1]},len(pivots)
    answer=0
    for pivot,(mask,rhs,_trace) in sorted(pivots.items()):
        if ((mask&answer).bit_count()&1)!=rhs:
            answer|=1<<pivot
    return {'kind':'xor_sat','witness':[(answer>>v)&1 for v in range(n)]},len(pivots)


def _propagate(clauses, chosen, ledger):
    """Producer-only iterative source-clause unit propagation."""
    assignment=dict(chosen)
    while True:
        ledger['unit_scans']+=1
        modified=False
        for clause in clauses:
            free=[]
            sat=False
            for literal in clause:
                val=assignment.get(abs(literal))
                if val is None:
                    free.append(literal)
                elif val==int(literal>0):
                    sat=True
                    break
            if sat:
                continue
            if not free:
                return assignment,True
            if len(free)==1:
                lit=free[0]
                var=abs(lit);val=int(lit>0)
                if var in assignment and assignment[var]!=val:
                    return assignment,True
                if var not in assignment:
                    assignment[var]=val;modified=True
                    ledger['unit_inferences']+=1
        if not modified:
            return assignment,False


def _next_branch(clauses,assignment):
    activity={}
    for clause in clauses:
        if any(abs(lit) in assignment and
               assignment[abs(lit)]==int(lit>0) for lit in clause):
            continue
        for lit in clause:
            if abs(lit) not in assignment:
                activity[abs(lit)]=activity.get(abs(lit),0)+1
    return min(activity,key=lambda v:(-activity[v],v)) if activity else None


def dpll_produce(clauses,n,node_budget=1024):
    if type(node_budget) is not int or node_budget<1:
        raise ValueError('positive node_budget required')
    ledger={'nodes':0,'conflicts':0,'unit_scans':0,'unit_inferences':0,'branches':0}
    def visit(chosen):
        if ledger['nodes']>=node_budget:
            return None
        ledger['nodes']+=1
        closure,contradiction=_propagate(clauses,chosen,ledger)
        if contradiction:
            ledger['conflicts']+=1
            return {'kind':'conflict'}
        pivot=_next_branch(clauses,closure)
        if pivot is None:
            bits=[closure.get(v,0) for v in range(1,n+1)]
            if not check_assignment(clauses,bits):
                raise AssertionError('producer incorrectly marked completion')
            return {'kind':'witness','witness':bits}
        ledger['branches']+=1
        left=visit({**closure,pivot:0})
        if left and left['kind']=='witness':
            return left
        right=visit({**closure,pivot:1})
        if right and right['kind']=='witness':
            return right
        if left is not None and right is not None:
            return {'kind':'split','variable':pivot,'zero':left,'one':right}
        return None
    tree=visit({})
    return tree,ledger


def _verify_conflict_tree(clauses,n,tree):
    """Different implication computation from producer. Check every split and leaf.

    Only a contradiction derivable from original clauses by unit closure
    qualifies as a leaf. A split must cover BOTH values of a fresh variable.
    """
    def closure(chosen):
        known=dict(chosen)
        while True:
            changed=[]
            for clause in clauses:
                satisfied=False
                possibilities=[]
                for lit in clause:
                    v=abs(lit)
                    if v not in known:
                        possibilities.append((v,int(lit>0)))
                    elif known[v]==int(lit>0):
                        satisfied=True;break
                if satisfied:
                    continue
                if not possibilities:
                    return known,True
                if len(possibilities)==1:
                    changed.append(possibilities[0])
            if not changed:
                return known,False
            for v,b in changed:
                if v in known and known[v]!=b:
                    return known,True
                known[v]=b
    seen=0
    def visit(node,chosen):
        nonlocal seen
        seen+=1
        if not isinstance(node,dict):
            raise ValueError('malformed proof node')
        inferred,contradiction=closure(chosen)
        kind=node.get('kind')
        if kind=='conflict':
            if not contradiction or set(node)!={'kind'}:
                raise ValueError('false conflict leaf')
            return
        if contradiction:
            raise ValueError('non-conflict node after contradiction')
        if kind!='split':
            raise ValueError('UNSAT tree requires complete split or conflict')
        v=node.get('variable')
        if (type(v) is not int or not 1<=v<=n or v in inferred or
                set(node)!={'kind','variable','zero','one'}):
            raise ValueError('invalid split variable or missing child')
        visit(node['zero'],{**inferred,v:0})
        visit(node['one'],{**inferred,v:1})
    visit(tree,{})
    return seen


def verify_direct_sat(clauses,n,receipt):
    """Admit only direct CNF witnesses, exhaustive conflicts, or XOR dependencies.

    An SPN nested proof is separately checked against the independently
    converted original CNF before admitting its decision.
    """
    if (not isinstance(receipt,dict) or receipt.get('version')!=VERSION or
            receipt.get('source_sha256')!=source_digest(clauses,n)):
        raise ValueError('wrong source or version')
    result=receipt.get('result');proof=receipt.get('proof')
    if result not in ('SAT','UNSAT','UNKNOWN') or not isinstance(proof,dict):
        raise ValueError('invalid result or proof')
    kind=proof.get('kind')
    if kind in ('xor_sat','xor_unsat'):
        equations=_verify_xor_encoding_by_truth_table(clauses,n)
        if equations is None:
            raise ValueError('source does not semantically encode complete XOR blocks')
        if kind=='xor_sat':
            bits=proof.get('witness')
            if (result!='SAT' or not isinstance(bits,list) or len(bits)!=n or
                    any(type(b) is not int or b not in (0,1) for b in bits) or
                    not check_assignment(clauses,bits) or
                    any((mask & sum(b<<i for i,b in enumerate(bits))).bit_count()%2!=rhs
                        for mask,rhs in equations)):
                raise ValueError('forged XOR SAT witness')
        else:
            indices=proof.get('conflict_indices')
            if (result!='UNSAT' or not isinstance(indices,list) or
                    not indices or len(set(indices))!=len(indices) or
                    any(type(j) is not int or not 0<=j<len(equations) for j in indices)):
                raise ValueError('invalid contradictory dependency')
            mask=rhs=0
            for j in indices:
                mask ^= equations[j][0];rhs ^= equations[j][1]
            if mask!=0 or rhs!=1:
                raise ValueError('parity dependency does not prove contradiction')
    elif kind=='witness':
        bits=proof.get('witness')
        if (result!='SAT' or not isinstance(bits,list) or len(bits)!=n or
                any(type(b) is not int or b not in (0,1) for b in bits) or
                not check_assignment(clauses,bits)):
            raise ValueError('invalid direct SAT witness')
    elif kind in ('conflict','split'):
        if result!='UNSAT':
            raise ValueError('unsat tree mismatch')
        _verify_conflict_tree(clauses,n,proof)
    elif kind=='spectral_fallback':
        if result=='UNKNOWN':
            raise ValueError('invalid fallback result')
        spectral=spectral_form(clauses,n)
        if spectral is None:
            raise ValueError('formula not spectral eligible')
        from adaptive_ground_compiler import verify_adaptive_receipt
        if verify_adaptive_receipt(spectral,n,proof.get('receipt'))!=result:
            raise ValueError('nested spectral decision mismatch')
    elif kind=='unknown':
        if result!='UNKNOWN' or proof.get('reason')!='budget_exhausted':
            raise ValueError('invalid refusal')
    else:
        raise ValueError('unrecognized certificate')
    return result


def produce_direct_sat(clauses,n,node_budget=1024,spectral_budget=0):
    """Goal-specific compiler: complete XOR -> DPLL -> optional SPN fallback.

    ``spectral_budget=0`` disables the optionally expensive spectral fallback.
    Ledger is measured, but never used as a proof of correctness.
    """
    validate_cnf(clauses,n)
    if type(spectral_budget) is not int or spectral_budget<0:
        raise ValueError('invalid spectral budget')
    started=perf_counter()
    attempts=[]
    t=perf_counter();equations=parity_blocks(clauses,n)
    attempts.append({'method':'complete_xor_recognition','status':'recognized' if equations is not None else 'refused',
                     'elapsed_ms':round((perf_counter()-t)*1000,3)})
    if equations is not None:
        t=perf_counter();proof,rank=gaussian_ground(equations,n)
        result='SAT' if proof['kind']=='xor_sat' else 'UNSAT'
        attempts.append({'method':'gf2_equation_solving','status':result,
                         'equations':len(equations),'rank_before_conflict':rank,
                         'elapsed_ms':round((perf_counter()-t)*1000,3)})
    else:
        t=perf_counter();proof,ledger=dpll_produce(clauses,n,node_budget)
        result='UNKNOWN' if proof is None else ('SAT' if proof['kind']=='witness' else 'UNSAT')
        attempts.append({'method':'source_dpll','status':result,**ledger,
                         'elapsed_ms':round((perf_counter()-t)*1000,3)})
        if result=='UNKNOWN' and spectral_budget:
            spectral=spectral_form(clauses,n)
            if spectral is not None:
                from adaptive_ground_compiler import produce_adaptive_receipt
                t=perf_counter()
                nested=produce_adaptive_receipt(spectral,n,goal='decision',rank_cap=3,
                                                node_budget=spectral_budget)
                attempts.append({'method':'spectral_fallback','status':nested['result'],
                                 'elapsed_ms':round((perf_counter()-t)*1000,3)})
                if nested['result']!='UNKNOWN':
                    proof={'kind':'spectral_fallback','receipt':nested}
                    result=nested['result']
        if result=='UNKNOWN':
            proof={'kind':'unknown','reason':'budget_exhausted'}
    receipt={'version':VERSION,'source_sha256':source_digest(clauses,n),
             'result':result,'proof':proof,
             'producer_ledger':{'attempts':attempts}}
    t=perf_counter()
    verify_direct_sat(clauses,n,receipt)
    receipt['producer_ledger']['verification_ms']=round((perf_counter()-t)*1000,3)
    receipt['producer_ledger']['total_ms']=round((perf_counter()-started)*1000,3)
    return receipt


if __name__=='__main__':
    # A direct 3-SAT contradiction, not a computational-complexity proof.
    formula=[(1,2,3),(1,-2,-3),(-1,2,-3),(-1,-2,3),
             (1,2,-3),(1,-2,3),(-1,2,3),(-1,-2,-3)]
    print(json.dumps(produce_direct_sat(formula,3),indent=2))
