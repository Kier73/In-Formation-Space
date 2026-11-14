"""RE-012: real E-CPU typed causal stamps and synthetic scoped certificates.

GitHub jobs exercise a pinned E-CPU temporal module; all detection reports,
keys, sensor identities, and source injections are CI-generated fixtures.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from mailcpu.temporal import CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile
from applicability_monitor import (
    ApplicabilityError, SCHEMA, assess, calibration, create_certificate,
    observer, plan, sign, verify_signed,
)
from detection_calibration import sha

HOST_SCHEMA='in-formation.response-re012-ecpu/0.1'
ROSTER={'S':0,'A':0,'B':0}


def context(role: str) -> TemporalContext:
    return TemporalContext(role, TemporalProfile(frozenset({ClockDomain.CAUSAL})),vector=dict(ROSTER))


def _envelope(body: Mapping[str,Any]) -> dict[str,Any]:
    return {**body,'digest':sha(body)}


def _check(doc: Any,role: str) -> None:
    if (not isinstance(doc,dict) or doc.get('schema')!=HOST_SCHEMA or
            doc.get('role')!=role or 'digest' not in doc or
            doc['digest']!=sha({k:v for k,v in doc.items() if k!='digest'})):
        raise ApplicabilityError('host envelope invalid')


def _stamp(doc: Mapping[str,Any],role: str) -> CausalStamp:
    frame=doc.get('frame')
    if (not isinstance(frame,dict) or frame.get('actor_id')!=role or
            not isinstance(frame.get('causal'),dict)):
        raise ApplicabilityError('typed E-CPU causal frame invalid')
    stamp=CausalStamp.from_dict(frame['causal'])
    if stamp.actor_id!=role:
        raise ApplicabilityError('causal stamp actor mismatch')
    return stamp


def source_host(reg: Mapping[str,Any], *, mode: str='baseline') -> dict[str,Any]:
    source,baseline_a,baseline_b=calibration(reg)
    cert=create_certificate(reg,source,baseline_a,baseline_b)
    monitoring=plan(reg,mode=mode)
    ctx=context('S')
    stamp=ctx.emit_causal_stamp()
    binding=sign(reg,'S','temporal_binding',{'source_seal':source['seal']['digest'],
        'certificate_digest':cert['digest'],'monitor_plan':monitoring['digest'],
        'stamp':stamp.to_dict()})
    return _envelope({'schema':HOST_SCHEMA,'role':'S','challenge':reg['challenge'],
          'calibration':{'source':source,'A':baseline_a,'B':baseline_b},
          'certificate':cert,'plan':monitoring,
          'binding':binding,'frame':ctx.observe().to_dict()})


def observer_host(source: Mapping[str,Any],reg: Mapping[str,Any],role: str,
                  *,sensor:str|None=None,firmware:str|None=None,
                  miss_slots:tuple[int,...]=(),late_slots:tuple[int,...]=()) -> dict[str,Any]:
    if role not in ('A','B'):
        raise ApplicabilityError('unknown host observer')
    _check(source,'S')
    if source['challenge']!=reg['challenge']:
        raise ApplicabilityError('observer challenge mismatch')
    s=_stamp(source,'S')
    ctx=context(role)
    ctx.receive_causal_stamp(s)
    receipt=observer(reg,source['plan'],role,sensor=sensor,firmware=firmware,
                     miss_slots=miss_slots,late_slots=late_slots,
                     defer_source_mac_to_verifier='S' not in reg.get('keys',{}))
    stamp=ctx.emit_causal_stamp()
    binding=sign(reg,role,'temporal_binding',{'source_seal':source['calibration']['source']['seal']['digest'],
        'certificate_digest':source['certificate']['digest'],
        'monitor_plan':source['plan']['digest'],
        'report_digest':receipt['digest'],'stamp':stamp.to_dict()})
    return _envelope({'schema':HOST_SCHEMA,'role':role,'challenge':reg['challenge'],
        'report':receipt,'binding':binding,'frame':ctx.observe().to_dict()})


def verify(source: Mapping[str,Any],a: Mapping[str,Any],b: Mapping[str,Any],
           reg: Mapping[str,Any],*,assumptions_accepted:bool=False) -> dict[str,Any]:
    for role,doc in (('S',source),('A',a),('B',b)):
        _check(doc,role)
        if doc['challenge']!=reg['challenge']:
            raise ApplicabilityError('host challenge mismatch')
    seals=source['calibration'];s=_stamp(source,'S');ca=_stamp(a,'A');cb=_stamp(b,'B')
    for role,doc,st in (('S',source,s),('A',a,ca),('B',b,cb)):
        receipt=verify_signed(doc['binding'],reg,role,'temporal_binding')
        expected={'source_seal':seals['source']['seal']['digest'],
                  'certificate_digest':source['certificate']['digest'],
                  'monitor_plan':source['plan']['digest'],'stamp':st.to_dict()}
        if role!='S':expected['report_digest']=doc['report']['digest']
        if receipt!=expected:
            raise ApplicabilityError('temporal stamp / claim binding mismatched')
    if (s.relation(ca)!=CausalRelation.BEFORE or s.relation(cb)!=CausalRelation.BEFORE or
            ca.relation(cb)!=CausalRelation.CONCURRENT):
        raise ApplicabilityError('E-CPU causal precedence invalid')
    result=assess(source['certificate'],reg,seals['source'],seals['A'],seals['B'],
          source['plan'],a['report'],b['report'],assumptions_accepted=assumptions_accepted)
    return {'schema':HOST_SCHEMA,'causal_relations':{'S_before_A':'before',
            'S_before_B':'before','A_concurrent_B':'concurrent'},
            'applicability':result,'cross_host_elapsed':None,
            'physical_sensor_identity_verified':False,
            'hosted_physical_detection_guarantee':None}


def demonstration() -> dict[str,Any]:
    from detection_calibration import enrollment
    reg=enrollment(deterministic=True)
    s=source_host(reg)
    return verify(s,observer_host(s,reg,'A'),observer_host(s,reg,'B'),reg)


def main() -> None:
    mode=sys.argv[1] if len(sys.argv)==2 else '--demo'
    if mode=='--demo': result=demonstration()
    elif mode=='--source':
        inp=json.load(sys.stdin);result=source_host(inp['enrollment'],mode=inp.get('mode','baseline'))
    elif mode in ('--A','--B'):
        inp=json.load(sys.stdin)
        result=observer_host(inp['source'],inp['enrollment'],mode[2:])
    elif mode=='--verify':
        inp=json.load(sys.stdin)
        result=verify(inp['source'],inp['A'],inp['B'],inp['enrollment'],
                      assumptions_accepted=inp.get('assumptions_accepted',False))
    else:raise SystemExit('usage: ecpu_re012_hosts.py [--demo|--source|--A|--B|--verify]')
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__=='__main__':main()
