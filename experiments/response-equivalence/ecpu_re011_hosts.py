"""RE-011 cross-job causal reconstruction using actual pinned E-CPU TemporalContext.

The GitHub jobs are distinct processes, not attested physical sensor hardware.
Role-scoped CI HMAC keys authenticate claims under fixture enrollment only.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from mailcpu.temporal import CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile
from detection_calibration import (
    CalibrationError, SCHEMA, _base, _key, _sign, _verify, enrollment,
    produce_source, produce_observer, reconstruct, sha,
)

HOST_SCHEMA = 'in-formation.response-re011-ecpu/0.1'
BIND_FIELDS = frozenset({'schema','session','challenge','role','key_id','kind',
                         'source_seal','report_seal','stamp'})
ROSTER = {'S':0,'A':0,'B':0}


def context(actor: str) -> TemporalContext:
    return TemporalContext(actor, TemporalProfile(frozenset({ClockDomain.CAUSAL})),
                           vector=dict(ROSTER))


def _wrap(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, 'digest':sha(body)}


def _check(doc: Any, role: str) -> None:
    if not isinstance(doc, dict) or doc.get('schema') != HOST_SCHEMA or doc.get('role') != role or \
       doc.get('digest') != sha({k:v for k,v in doc.items() if k!='digest'}):
        raise CalibrationError('invalid host envelope')


def _stamp(doc: Mapping[str, Any], actor: str) -> CausalStamp:
    frame=doc.get('frame')
    if not isinstance(frame,dict) or frame.get('actor_id') != actor or not isinstance(frame.get('causal'),dict):
        raise CalibrationError('invalid E-CPU frame actor')
    stamp=CausalStamp.from_dict(frame['causal'])
    if stamp.actor_id != actor:
        raise CalibrationError('E-CPU frame causal actor mismatch')
    return stamp


def _binding(reg: Mapping[str,Any], role: str, source_seal: str,
             report_seal: str, stamp: CausalStamp) -> dict[str, Any]:
    return _sign({**_base(reg,role,'binding'), 'source_seal':source_seal,
                  'report_seal':report_seal, 'stamp':stamp.to_dict()},_key(reg,role))


def source_host(reg: Mapping[str, Any]) -> dict[str, Any]:
    source=produce_source(reg)
    ctx=context('S')
    stamp=ctx.emit_causal_stamp()
    return _wrap({'schema':HOST_SCHEMA,'role':'S','challenge':reg['challenge'],
                  'source':source,'frame':ctx.observe().to_dict(),
                  'binding':_binding(reg,'S',source['seal']['digest'],
                                     source['seal']['digest'],stamp)})


def observer_host(source_doc: Mapping[str,Any], reg: Mapping[str,Any], role: str,
                  regime: str='common_mode_dropouts') -> dict[str,Any]:
    _check(source_doc,'S')
    if source_doc['challenge']!=reg['challenge']:
        raise CalibrationError('source challenge mismatch')
    stamp=_stamp(source_doc,'S')
    ctx=context(role)
    ctx.receive_causal_stamp(stamp)
    own=produce_observer(source_doc['source'],reg,role,regime)
    out_stamp=ctx.emit_causal_stamp()
    return _wrap({'schema':HOST_SCHEMA,'role':role,'challenge':reg['challenge'],
                  'log':own,'frame':ctx.observe().to_dict(),
                  'binding':_binding(reg,role,source_doc['source']['seal']['digest'],
                                     own['seal']['digest'],out_stamp)})


def verify(source_doc: Mapping[str,Any], a_doc: Mapping[str,Any], b_doc: Mapping[str,Any],
           reg: Mapping[str,Any]) -> dict[str,Any]:
    for role,doc in (('S',source_doc),('A',a_doc),('B',b_doc)):
        _check(doc,role)
        if doc['challenge']!=reg['challenge']:
            raise CalibrationError('host challenge mismatch')
    s=_stamp(source_doc,'S')
    a=_stamp(a_doc,'A')
    b=_stamp(b_doc,'B')
    source_log=source_doc['source']; source_seal=source_log['seal']['digest']
    for role, doc, stamp, report_seal in (
          ('S',source_doc,s,source_seal),
          ('A',a_doc,a,a_doc['log']['seal']['digest']),
          ('B',b_doc,b,b_doc['log']['seal']['digest'])):
        _verify(doc['binding'],reg,role,'binding',BIND_FIELDS)
        if (doc['binding']['source_seal']!=source_seal or
            doc['binding']['report_seal']!=report_seal or
            doc['binding']['stamp']!=stamp.to_dict()):
            raise CalibrationError('signed stamp or sealed-log binding mismatch')
    if (s.relation(a)!=CausalRelation.BEFORE or
        s.relation(b)!=CausalRelation.BEFORE or
        a.relation(b)!=CausalRelation.CONCURRENT):
        raise CalibrationError('E-CPU causal handoff/concurrency invalid')
    result=reconstruct(source_log,a_doc['log'],b_doc['log'],reg)
    if result['counts']['joint_non_detection'] != 12:
        raise CalibrationError('hosted common-mode fixture unexpected count')
    return {'schema':HOST_SCHEMA,
            'causal_relations':{'S_before_A':'before','S_before_B':'before',
                                'A_concurrent_B':'concurrent'},
            'calibration':result,
            'cross_host_elapsed':None,
            'trusted_physical_source':False,
            'physical_detection_guarantee':None}


def demonstration()->dict[str,Any]:
    reg=enrollment(deterministic=True)
    source=source_host(reg)
    return verify(source,observer_host(source,reg,'A'),observer_host(source,reg,'B'),reg)


def main()->None:
    role=sys.argv[1] if len(sys.argv)==2 else '--demo'
    if role=='--demo':
        data=demonstration()
    elif role=='--source':
        args=json.load(sys.stdin)
        data=source_host(args['enrollment'])
    elif role in ('--A','--B'):
        args=json.load(sys.stdin)
        data=observer_host(args['source'],args['enrollment'],role[2:])
    elif role=='--verify':
        args=json.load(sys.stdin)
        data=verify(args['source'],args['A'],args['B'],args['enrollment'])
    else:
        raise SystemExit('usage: ecpu_re011_hosts.py [--demo|--source|--A|--B|--verify]')
    print(json.dumps(data,sort_keys=True,indent=2))

if __name__=='__main__':main()