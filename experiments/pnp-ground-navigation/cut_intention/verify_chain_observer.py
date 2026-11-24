"""CIG-004 receiver: independent original-CNF, ANF and Krylov-span audit.

Never imports the CIG-004 producer or its polynomial/linear algebra helpers.
It reuses CIG-003's independent original-CNF endpoint proof only.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
from verify_nonlinear_observer import _source as qualified_cnf_source

SCHEMA='ifs.cig004.chain-observer-ground.v1'

class Reject(ValueError):pass


def _hash(doc):
    return hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _true(clauses,state):
    for clause in clauses:
        if not any(((state>>(abs(l)-1))&1)==(1 if l>0 else 0) for l in clause):
            return False
    return True


def _truth_anf(inputs,table):
    """Recover ANF coefficients by parity over subcubes (not Mobius update)."""
    coefficients=[]
    for mask in range(4):
        coeff=0
        for subset in range(4):
            if subset&~mask==0:coeff ^= table[subset]
        if coeff:
            coefficients.append(sum(1<<inputs[j] for j in range(2) if mask & (1<<j)))
    return tuple(sorted(coefficients))


def _times(left,right):
    counts={}
    if len(left)*len(right)>16384:raise Reject('independent multiplication work exceeded')
    for x in left:
        for y in right:
            key=x|y  # Boolean idempotence, NOT free-polynomial multiplication
            counts[key]=1-counts.get(key,0)
    ans=tuple(sorted(k for k,v in counts.items() if v))
    if len(ans)>1024:raise Reject('independent term budget exceeded')
    return ans


def _substitute(poly,operator):
    terms=set()
    for mask in poly:
        product=(0,)
        for v in range(len(operator)):
            if mask & (1<<v):product=_times(product,operator[v])
        terms.symmetric_difference_update(product)
        if len(terms)>1024:raise Reject('independent substitution exceeds term budget')
    return tuple(sorted(terms))


def _value(poly,state):
    parity=0
    for monomial in poly:
        if (state & monomial)==monomial:parity^=1
    return parity


def _linear_expression(basis,wanted):
    """Return coefficient mask of wanted, or None if outside source span."""
    pivots={}
    for index,poly in enumerate(basis):
        remainder=set(poly);coeff=1<<index
        for pivot in sorted(pivots,reverse=True):
            if pivot in remainder:
                row,code=pivots[pivot];remainder.symmetric_difference_update(row);coeff ^= code
        if not remainder:raise Reject('feature basis contains a dependency')
        pivots[max(remainder)]=(remainder,coeff)
    remainder=set(wanted);coeff=0
    for pivot in sorted(pivots,reverse=True):
        if pivot in remainder:
            row,code=pivots[pivot];remainder.symmetric_difference_update(row);coeff^=code
    return coeff if not remainder else None


def _independent_orbit(target,operator,limit=20):
    orbit=[];poly=(1<<target,)
    for _ in range(limit+1):
        # An old polynomial repeated in the span terminates the Krylov orbit.
        try:
            present=_linear_expression(orbit,poly) if orbit else None
        except Reject as exc:
            raise Reject('invalid independent orbit') from exc
        if present is not None:return orbit
        if len(orbit)>=limit:raise Reject('Krylov orbit budget exceeded')
        orbit.append(poly)
        poly=_substitute(poly,operator)
    raise Reject('Krylov orbit not closed')


def _matrix_apply(rows,vector):
    res=0
    for i,row in enumerate(rows):
        if (row & vector).bit_count() & 1:res|=1<<i
    return res


def _matrix_mul(left,right):
    ans=[]
    for row in left:
        dest=0
        for i,bitrow in enumerate(right):
            if row & (1<<i):dest^=bitrow
        ans.append(dest)
    return tuple(ans)


def _matrix_navigate(matrix,initial,steps):
    result=tuple(1<<i for i in range(len(matrix)))
    power=tuple(matrix);count=0
    while steps:
        if steps%2:
            result=_matrix_mul(power,result);count+=1
        steps//=2
        if steps:
            power=_matrix_mul(power,power);count+=1
    return _matrix_apply(result,initial),count


def verify(source,certificate):
    try:
        if not isinstance(certificate,dict) or certificate.get('schema')!=SCHEMA:
            raise Reject('unrecognized CIG-004 certificate')
        if certificate['source_digest']!=_hash(source):raise Reject('source identity invalid')
        pairs,active,clauses,_=qualified_cnf_source(source,certificate['cut'])
        n=len(active)
        if not 1<=n<=24 or len(pairs)<n:raise Reject('source outside receiver budget')
        if certificate['active_labels']!=active or certificate['clauses']!=[list(c) for c in clauses]:
            raise Reject('noncanonical or changed original clauses')
        if certificate['orientation']!='maximum-variable local output; proof-checked chosen rewrite':
            raise Reject('undisclosed interpretation orientation')
        families=defaultdict(list)
        for c in clauses:
            support=tuple(sorted({abs(l)-1 for l in c}))
            if len(support)!=3:raise Reject('unsupported or missing source clause')
            families[support].append(tuple(c))
        gates=[]
        for support,proof in sorted(families.items(),key=lambda pair:max(pair[0])):
            output=max(support);inputs=support[:2]
            truth=[]
            for two_bits in range(4):
                options=[]
                for bit in (0,1):
                    assignment=sum(((two_bits>>i)&1)<<x for i,x in enumerate(inputs))|(bit<<output)
                    if _true(proof,assignment):options.append(bit)
                if len(options)!=1:raise Reject('source clauses not a total function')
                truth.append(options[0])
            gates.append({'output':output,'inputs':list(inputs),'table':truth,
                          'anf_masks':list(_truth_anf(inputs,truth)),
                          'source_clauses':[list(c) for c in sorted(proof)]})
        if not gates or len(gates)>12 or certificate['gates']!=gates:
            raise Reject('unproven or misoriented source functions')
        outputs={g['output'] for g in gates}
        if len(outputs)!=len(gates) or not any(outputs.intersection(g['inputs']) for g in gates):
            raise Reject('source lacks a multi-step chain')
        if any(any(v>=g['output'] for v in g['inputs']) for g in gates):
            raise Reject('source is not a forward gate DAG')
        registers=[i for i in range(n) if i not in outputs]
        if certificate['registers']!=registers:raise Reject('source free-bit accounting forged')
        operator=[(1<<i,) for i in range(n)]
        for g in gates:operator[g['output']]=tuple(g['anf_masks'])
        if certificate['operator_rows']!=[list(x) for x in operator]:
            raise Reject('nonlinear transition is not source-derived')
        target=max(outputs)
        if certificate['observer']!=target:raise Reject('observer differs from intended chain endpoint')
        info=certificate['features']
        basis=tuple(tuple(row) for row in info['basis'])
        if not basis or len(basis)>20 or info['dimension']!=len(basis):
            raise Reject('invalid feature dimension')
        if any(not isinstance(x,int) or x<0 or x >= 1<<n for row in basis for x in row):
            raise Reject('ANF monomial outside source domain')
        if any(len(row)>1024 or tuple(sorted(set(row)))!=row for row in basis):
            raise Reject('noncanonical ANF feature')
        orbit=_independent_orbit(target,operator)
        if len(basis)!=len(orbit):raise Reject('feature span not minimal')
        for feature in basis:
            if _linear_expression(orbit,feature) is None:
                raise Reject('extraneous feature outside minimum Krylov span')
        for feature in orbit:
            if _linear_expression(basis,feature) is None:
                raise Reject('feature basis omits an exact future observation')
        matrix=[]
        for feature in basis:
            code=_linear_expression(basis,_substitute(feature,operator))
            if code is None:raise Reject('feature space is not pullback closed')
            matrix.append(code)
        read=_linear_expression(basis,(1<<target,))
        if (info['matrix_rows']!=matrix or info['read_mask']!=read or
            info['closure_pullbacks']!=len(basis)):
            raise Reject('invalid exact feature dynamics or observation decoder')
        fa=certificate['future_alignment']
        future=(1<<target,);h=0
        while h<=len(gates)+1:
            nxt=_substitute(future,operator)
            if nxt==future:break
            future=nxt;h+=1
        if h>len(gates)+1:raise Reject('future polynomial does not stabilize')
        if (fa['stabilization_steps']!=h or fa['exact_for_steps_at_least']!=h or
            fa['anf_masks']!=list(future) or fa['symbolic_pullbacks']!=h+1 or
            fa['dimension']!=(1 if future else 0)):
            raise Reject('future-aligned observer incorrectly constructed')
        nav=certificate['navigation']
        if type(nav['initial']) is not str or type(nav['steps']) is not str:
            raise Reject('navigation coordinates malformed')
        initial=int(nav['initial']);steps=int(nav['steps'])
        if not 0<=initial<1<<n or steps<0 or steps.bit_length()>4096:
            raise Reject('navigation source or horizon invalid')
        source_features=sum(_value(f,initial)<<i for i,f in enumerate(basis))
        result,products=_matrix_navigate(matrix,source_features,steps)
        observed=(result & read).bit_count()&1
        future_value=_value(future,initial)
        if (nav['initial_features']!=str(source_features) or
            nav['result_features']!=str(result) or nav['observed']!=observed or
            nav['matrix_products']!=products or fa['observed']!=future_value):
            raise Reject('false nonlinear navigation result')
        if steps>=h and observed!=future_value:raise Reject('eventual source observation wrong')
        exact_count=1<<(len(registers)+len(pairs)-n)
        result_claim=certificate['source_result']
        if result_claim['count']!=str(exact_count) or result_claim['status']!='SAT':
            raise Reject('source SAT/#SAT count mismatched')
        witness=result_claim['witness']
        if (type(witness) is not list or len(witness)!=source['base']['n'] or
            any(type(bit) is not int or bit not in (0,1) for bit in witness)):
            raise Reject('malformed original-CNF witness')
        if not _true(source['base']['clauses']+source['coupling'],sum(v<<i for i,v in enumerate(witness))):
            raise Reject('witness violates original source')
        # Verify source semantics in full on the small admitted fixture domain;
        # the local functional proofs above remain the generic certificate.
        if n<=12:
            models=0
            for state in range(1<<n):
                source_truth=_true(clauses,state)
                update=sum(_value(row,state)<<i for i,row in enumerate(operator))
                if source_truth!=(update==state):raise Reject('source fixed-point contract false')
                models+=int(source_truth)
                if steps<=len(gates)+1:
                    direct=state
                    for _ in range(steps):
                        direct=sum(_value(row,direct)<<i for i,row in enumerate(operator))
                    projected=sum(_value(f,state)<<i for i,f in enumerate(basis))
                    calc,_=_matrix_navigate(matrix,projected,steps)
                    if ((calc&read).bit_count()&1)!=((direct>>target)&1):
                        raise Reject('finite-time observer composition mismatch')
            if models!=1<<len(registers):raise Reject('source fixed-point count false')
        if certificate['ledger']!={'source_clause_count':len(source['base']['clauses'])+len(source['coupling']),
                    'active_variables':n,'original_endpoint_variables':source['base']['n'],
                    'original_sat_models':str(exact_count),'source_cube_size':str(1<<n),
                    'nonlinear_operator_row_count':len(operator),
                    'closure_pullbacks':len(basis),'matrix_products':products,
                    'future_alignment_pullbacks':h+1}:
            raise Reject('source construction work ledger changed')
        return True
    except Reject:raise
    except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError,RecursionError) as exc:
        raise Reject('invalid source-derived feature certificate') from exc
