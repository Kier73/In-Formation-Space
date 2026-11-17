"""PGT-005: exact IOS-001/002/003 contracts, pinned to one source Ground root.

A finite candidate language is NOT evidence that an unknown source belongs
there. Probe intents request only a directly measured coordinate; extrapolated
original intentions stay provisional until the target is independently read.
"""
from __future__ import annotations
import re
from typing import Any
from decision_experiment import H,fingerprint
from mailcpu.intention_sufficiency import (FiniteState, FiniteGround,
    MeasurementCapability,plan_sufficiency,verify_sufficiency_plan)
from mailcpu.observer_orbit import ObserverContract
from mailcpu.semantic_translation import RepresentationRef,ObservationContract,canonical_value_digest

LANGUAGE_SHA=fingerprint(H.tolist())


def require_root(source_root:str)->str:
    if type(source_root) is not str or re.fullmatch(r'[0-9a-f]{64}',source_root) is None:
        raise ValueError('source root must be the exact externally pinned SHA-256')
    return source_root


def authority_for(root:str)->str:
    return canonical_value_digest({'policy':'pgt005-receiver-installed-pure-reads','epoch':1,
                                    'pinned_source_root':require_root(root)})


def context_for(root:str)->str:
    return canonical_value_digest({'experiment':'pgt005','revision':1,
                                   'source_root':require_root(root)})


def subject_for(root:str)->RepresentationRef:
    return RepresentationRef.from_payload('pgt005.synthetic-source',1,
        {'domain':'eight-boolean-projections','source_root':require_root(root)})


def ground_ref()->RepresentationRef:
    return RepresentationRef.from_payload('pgt005.provisional-language',1,
        {'hypotheses_sha256':LANGUAGE_SHA,'count':int(len(H))})


def feature_name(q:int)->str:
    if type(q) is not int or not 0 <= q < 8:
        raise ValueError('unsupported observation coordinate')
    return f'q{q}'


def contract_at(q:int,root:str)->ObserverContract:
    fid=feature_name(q)
    proj=ObservationContract.from_definition(fid,1,{'project':'source-bit','coordinate':q})
    return ObserverContract('provider-b',1,subject_for(root),ground_ref(),proj,context_for(root))


def model_at(q:int,root:str)->FiniteGround:
    fid=feature_name(q)
    target=ObservationContract.from_definition(f'intention.{fid}',1,{'requested-bit':q})
    public=ObservationContract.from_definition('pgt005.initial-unknown',1,{'public':0})
    states=tuple(FiniteState.create(f'state_{i:03d}', 0, int(H[i,q]),
                                    {fid:int(H[i,q])}) for i in range(len(H)))
    return FiniteGround(ground_ref().content_digest, public.projection_digest,
                        target.projection_digest,context_for(root),states)


def probe_contract(q:int,root:str,cost:int=1):
    """Replan under native IOS-001, never treat model output as authorization."""
    if type(cost) is not int or not 0<=cost<100:
        raise ValueError('invalid symbolic cost')
    fid=feature_name(q)
    model=model_at(q,root)
    contract=contract_at(q,root)
    offers=(MeasurementCapability(fid,contract.digest,contract.observer_id,cost),)
    authority=authority_for(root)
    plan=plan_sufficiency(model,0,offers,authority)
    verify_sufficiency_plan(plan,model,0,offers,authority)
    if plan['status'] != 'MEASURE' or plan['selected_features'] != [fid]:
        raise ValueError('one-coordinate native observation must require exactly its own feature')
    return model,offers,plan,{fid:contract}


def exact_target_status(target:int,observed:dict[int,int],root:str)->dict[str,Any]:
    """Conditionally navigate the original intention under observed q fibers.

    READY here is mathematical *within* the candidate language, not source
    Ground admission. Empty fibers are marked OUT_OF_FAMILY, never accepted.
    """
    feature_name(target);require_root(root)
    for q,v in observed.items():
        feature_name(q)
        if type(v) is not int or v not in (0,1):
            raise ValueError('invalid witnessed projection')
    surviving=[i for i in range(len(H)) if all(int(H[i,q])==v for q,v in observed.items())]
    if not surviving:
        return {'status':'OUT_OF_FAMILY','candidate':None,'remaining':0,
                'claim':'observed source contradicts the candidate language'}
    rows=tuple(FiniteState.create(f'state_{i:03d}',0,int(H[i,target]),{})
               for i in surviving)
    public=ObservationContract.from_definition('pgt005.initial-unknown',1,{'public':0})
    intent=ObservationContract.from_definition(f'original-intention.q{target}',1,{'coordinate':target})
    ground=FiniteGround(ground_ref().content_digest,public.projection_digest,
                        intent.projection_digest,context_for(root),rows)
    auth=authority_for(root)
    plan=plan_sufficiency(ground,0,(),auth)
    verify_sufficiency_plan(plan,ground,0,(),auth)
    return {'status':plan['status'],'candidate':plan['ready_result'],
            'remaining':len(surviving),'plan_digest':plan['plan_digest'],
            'claim':'conditional finite-language result; not admitted source Ground'}
