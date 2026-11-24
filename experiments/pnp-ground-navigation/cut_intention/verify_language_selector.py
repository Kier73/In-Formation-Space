"""Independent CIG-006 receiver: original endpoint clauses, every orientation,
ANF source semantics, minimal invariant space, exact temporal readouts, and
uniform finite-class ambiguity. Never imports the CIG-006 producer.
"""
from __future__ import annotations
from itertools import product
from verify_nonlinear_observer import _source as original_source
from verify_chain_observer import (_hash,_true,_truth_anf,_substitute,
    _linear_expression,_value,_matrix_mul)
from verify_joint_intention import _independent_joint_orbit

SCHEMA='ifs.cig006.source-selected-temporal-language.v1'

class Reject(ValueError):pass


def _group_orientations(clauses):
    groups={}
    for c in clauses:
        if len(c)!=3 or len(set(abs(x) for x in c))!=3:raise Reject('not a complete ternary relation family')
        groups.setdefault(tuple(sorted(abs(x)-1 for x in c)),[]).append(tuple(c))
    candidates=[]
    for scope,source_rows in sorted(groups.items()):
        alternatives=[]
        for output in scope:
            inputs=tuple(x for x in scope if x!=output)
            values=[]
            for i in range(4):
                admitted=[]
                for b in (0,1):
                    state=(b<<output)|sum(((i>>j)&1)<<pos for j,pos in enumerate(inputs))
                    if _true(source_rows,state):admitted.append(b)
                if len(admitted)!=1:break
                values.append(admitted[0])
            if len(values)==4:
                alternatives.append({'output':output,'inputs':list(inputs),'table':values,
                  'anf_masks':list(_truth_anf(inputs,values)),
                  'source_clauses':[list(c) for c in sorted(source_rows)]})
        if not alternatives:raise Reject('source does not prove a total relation')
        candidates.append(sorted(alternatives,key=lambda g:g['output']))
    return candidates


def _independent_power(matrix,t):
    n=len(matrix);acc=tuple(1<<j for j in range(n));power=tuple(matrix);count=0
    while t:
        if t%2:
            acc=_matrix_mul(power,acc);count+=1
        t//=2
        if t:
            power=_matrix_mul(power,power);count+=1
    return acc,count


def _polynomial_xor(polys):
    terms=set()
    for poly in polys:terms.symmetric_difference_update(poly)
    return tuple(sorted(terms))


def _expected_future(basis,masks,matrix,time):
    power,work=_independent_power(matrix,time)
    results=[]
    for read in masks:
        coefficients=0
        for index,row in enumerate(power):
            if (read>>index)&1:coefficients ^= row
        polys=(basis[j] for j in range(len(basis)) if (coefficients>>j)&1)
        results.append(_polynomial_xor(polys))
    return results,work


def _audit_snapshot(futures,n,reported):
    union=0
    for p in futures:
        for m in p:union|=m
    support=[i for i in range(n) if union&(1<<i)]
    lookup=[]
    for pos in range(1<<len(support)):
        state=sum(((pos>>j)&1)<<v for j,v in enumerate(support))
        lookup.append(sum(_value(p,state)<<k for k,p in enumerate(futures)))
    image=sorted(set(lookup));encoded={v:i for i,v in enumerate(image)}
    bit_count=(len(image)-1).bit_length()
    encoder=[]
    for bit in range(bit_count):
        table=[(encoded[x]>>bit)&1 for x in lookup]
        poly=[]
        # Independent direct parity over submasks, rather than producer's
        # fast Möbius table transform.
        for mask in range(1<<len(support)):
            subset=mask;parity=0
            while True:
                parity ^= table[subset]
                if subset==0:break
                subset=(subset-1)&mask
            if parity:poly.append(sum(1<<support[j] for j in range(len(support)) if mask&(1<<j)))
        encoder.append(poly)
    independent=[]
    for poly in futures:
        if _linear_expression(independent,poly) is None:independent.append(poly)
    expected={'support':support,'linear_rank':len(independent),
             'image_size':len(image),'minimum_binary_bits':bit_count,
             'decoder':image,'encoder_anf':encoder,
             'source_support_assignments':len(lookup)}
    if expected!=reported:raise Reject('nonlinear snapshot quotient or polynomial code forged')
    for coordinate,output in enumerate(lookup):
        state=sum(((coordinate>>j)&1)<<v for j,v in enumerate(support))
        code=sum(_value(tuple(p),state)<<i for i,p in enumerate(encoder))
        if not 0<=code<len(image) or image[code]!=output:
            raise Reject('source code fails its nonlinear decoder')
    return expected


def verify(source,certificate,*,intention=None):
    try:
        if type(certificate)is not dict or certificate.get('schema')!=SCHEMA:
            raise Reject('unrecognized temporal selector Ground')
        if certificate['source_digest']!=_hash(source):raise Reject('original source identity changed')
        intent=certificate['intent']
        if intention is not None and intent!=intention:
            raise Reject('recipient-intended temporal request or budget was altered')
        if type(intent) is not dict or set(intent)!={'targets','steps','initial','max_candidates','max_features'}:
            raise Reject('incomplete intention')
        selected=intent['targets'];steps=int(intent['steps']);initial=intent['initial']
        limit=intent['max_candidates'];features=intent['max_features']
        if (type(intent['steps'])is not str or intent['steps']!=str(steps) or
            steps<0 or steps.bit_length()>4096 or
            type(limit)is not int or not 1<=limit<=64 or
            type(features)is not int or not 1<=features<=24):
            raise Reject('unqualified finite policy')
        pairs,active,clauses,_=original_source(source,certificate['cut'])
        n=len(active)
        if (not 2<=n<=12 or type(selected)is not list or not selected or
            len(set(selected))!=len(selected) or any(type(x)is not int or not 0<=x<n for x in selected)
            or type(initial)is not int or not 0<=initial<(1<<n)):
            raise Reject('source or intention outside exact admissible domain')
        active_models=sum(_true(clauses,state) for state in range(1<<n))
        expected_witness=None
        if active_models:
            first=next(x for x in range(1<<n) if _true(clauses,x))
            assignment={v:(first>>i)&1 for i,v in enumerate(active)}
            expected_witness=[0]*source['base']['n']
            for i,(a,b) in enumerate(pairs):
                expected_witness[a-1]=expected_witness[b-1]=assignment.get(i,0)
        expected_model={'active_labels':active,'clauses':[list(x) for x in clauses],
                        'active_fixed_points':active_models,
                        'original_model_count':str(active_models<<(len(pairs)-n)),
                        'original_source_witness':expected_witness}
        if expected_witness is not None:
            for row in source['base']['clauses']+source['coupling']:
                if not any(expected_witness[abs(l)-1]==int(l>0) for l in row):
                    raise Reject('source-selected original witness fails unlifted CNF')
        if certificate['source_model']!=expected_model:
            raise Reject('source clause or model count differs from original')
        groups=_group_orientations(clauses)
        product_size=1
        for group in groups:product_size*=len(group)
        if product_size>limit:raise Reject('candidate search not source-complete')
        all_gates=[list(g) for g in product(*groups)]
        chosen_gates=[g for g in all_gates if len({row['output'] for row in g})==len(g)]
        cls={'name':'complete-triple-relation-functional-orientations',
             'group_count':len(groups),'cartesian_options':product_size,
             'conflict_free_count':len(chosen_gates),'complete_qualification':None}
        if len(chosen_gates)!=len(certificate['candidates']):raise Reject('candidate omissions')
        expected=[];admitted=[];total_pullbacks=0;total_products=0
        for idx,(gates,reported) in enumerate(zip(chosen_gates,certificate['candidates'])):
            if reported.get('orientation')!=[g['output'] for g in gates] or reported.get('gates')!=gates:
                raise Reject('source-proved candidate orientation changed')
            operator=[(1<<i,) for i in range(n)]
            for g in gates:operator[g['output']]=tuple(g['anf_masks'])
            # Fixed-point equivalence is checked on the entire active cube,
            # independent of the producer's syntactic orientation argument.
            for x in range(1<<n):
                fixed=all(_value(operator[i],x)==(x>>i)&1 for i in range(n))
                if fixed!=_true(clauses,x):raise Reject('candidate is not source fixed-point equivalent')
            # Source-independent orbit closure and linear containment proof.
            try:
                minimal=_independent_joint_orbit(tuple(selected),operator,max_features=features)
                basis=tuple(tuple(row) for row in reported['feature_basis'])
                if len(basis)!=len(minimal) or len({tuple(b) for b in basis})!=len(basis):
                    raise Reject('candidate feature rank changed')
                for p in minimal:
                    if _linear_expression(basis,p) is None:raise Reject('missing minimal future feature')
                for p in basis:
                    if _linear_expression(minimal,p) is None:raise Reject('spurious future feature')
                matrix=tuple(_linear_expression(basis,_substitute(p,operator)) for p in basis)
                masks=tuple(_linear_expression(basis,(1<<v,)) for v in selected)
                if None in matrix or None in masks:raise Reject('source observer representation not closed')
                if (reported['operator_rows']!=[list(row) for row in operator] or
                    reported['feature_basis']!=[list(p) for p in basis] or
                    reported['feature_matrix_rows']!=list(matrix) or
                    reported['feature_read_masks']!=list(masks) or
                    reported['feature_dimension']!=len(basis) or
                    reported['construction_pullbacks']!=len(basis)):
                    raise Reject('candidate exact Koopman certificate altered')
                futures,products=_expected_future(basis,masks,matrix,steps)
                _audit_snapshot(futures,n,reported['snapshot'])
                if (reported['future_anf']!=[list(p) for p in futures] or
                    reported['conditional_observation']!=[_value(p,initial) for p in futures] or
                    reported['matrix_products']!=products or reported['status']!='ADMITTED'):
                    raise Reject('source future readout or its cost changed')
                admitted.append((idx,reported))
                total_pullbacks+=len(basis);total_products+=products
            except (ValueError,TypeError,IndexError) as error:
                if isinstance(error,Reject):raise
                if reported.get('status')!='BUDGET_REFUSAL':
                    raise Reject('candidate improperly admitted despite feature refusal') from error
                if reported.get('reason') not in ('shared feature budget exceeded',
                     'feature limit exceeded','observer requires more exact future features'):
                    raise Reject('unsupported refusal reason')
                if reported!={'orientation':[g['output'] for g in gates], 'gates':gates,
                    'status':'BUDGET_REFUSAL', 'reason':reported['reason']}:
                    raise Reject('refused candidate carries forged data')
        complete=len(admitted)==len(chosen_gates)
        cls['complete_qualification']=complete
        if certificate['candidate_class']!=cls:raise Reject('candidate inventory changed')
        if admitted:
            pick=min(admitted,key=lambda item:(item[1]['snapshot']['minimum_binary_bits'],
                 item[1]['feature_dimension'],
                 sum(len(p) for p in item[1]['feature_basis']),item[1]['orientation']))[0]
            futures=[]
            for _,r in admitted:
                if r['future_anf'] not in futures:futures.append(r['future_anf'])
            status=('UNKNOWN_INCOMPLETE_CANDIDATE_PROOFS' if not complete else
                    'CONSENSUS_IN_DISCOVERED_CLASS' if len(futures)==1 else
                    'INTERPRETATION_AMBIGUOUS')
        else:pick=None;status='UNKNOWN_NO_ADMITTED_LANGUAGE'
        if certificate['chosen_candidate_index']!=pick or certificate['consensus_status']!=status:
            raise Reject('candidate choice or evidential status changed')
        witness=None
        if status=='INTERPRETATION_AMBIGUOUS':
            base=admitted[0][1]['future_anf']
            other=next(c['future_anf'] for _,c in admitted if c['future_anf']!=base)
            for x in range(1<<n):
                u=[_value(tuple(p),x) for p in base]
                v=[_value(tuple(p),x) for p in other]
                if u!=v:
                    witness={'initial':x,'first':u,'second':v};break
            if witness is None:raise Reject('distinct ANFs lack predicted disagreement')
        if certificate['disagreement_witness']!=witness:raise Reject('ambiguous source witness forged')
        ledger={'candidate_grounds_considered':len(chosen_gates),
                'admitted_grounds':len(admitted),
                'candidate_feature_pullbacks':total_pullbacks,
                'candidate_matrix_products':total_products,
                'source_active_assignment_checks':1<<n,
                'snapshot_support_checks':sum(c.get('snapshot',{}).get('source_support_assignments',0) for c in certificate['candidates'])}
        if certificate['ledger']!=ledger:
            raise Reject('full construction ledger altered')
        if certificate['evidence_scope']!='finite source-derived orientation class; off-fixedpoint dynamics conditional':
            raise Reject('interpretation scope changed')
        return True
    except (KeyError,TypeError,IndexError,OverflowError,AssertionError) as error:
        raise Reject('unverifiable source selection') from error
