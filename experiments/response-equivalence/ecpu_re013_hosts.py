"""RE-013 independent-job envelope over genuine pinned E-CPU TemporalContext.

The underlying evidence is deterministic synthetic data, and the CI keys are
not physically attested. Host processes do not need others' signing secrets.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from mailcpu.temporal import CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile
from active_recalibration import (
    RenewalError, evaluate, observer_report, signed_plan, verify_prior,
)
from applicability_monitor import sign, verify_signed
from detection_calibration import sha

SCHEMA = 'in-formation.response-re013-ecpu/0.1'
ROSTER = {'S': 0, 'A': 0, 'B': 0}


def context(role: str) -> TemporalContext:
    return TemporalContext(role, TemporalProfile(frozenset({ClockDomain.CAUSAL})), vector=dict(ROSTER))


def _envelope(doc: Mapping[str,Any]) -> dict[str,Any]:
    return {**doc,'digest':sha(doc)}


def _check(doc: Any, role: str) -> None:
    if not isinstance(doc,dict) or doc.get('schema') != SCHEMA or doc.get('role') != role or \
        doc.get('digest') != sha({k:v for k,v in doc.items() if k!='digest'}):
        raise RenewalError('host envelope invalid')


def _stamp(doc: Mapping[str,Any], role: str) -> CausalStamp:
    frame = doc.get('frame')
    if not isinstance(frame,dict) or frame.get('actor_id') != role or \
            not isinstance(frame.get('causal'),dict):
        raise RenewalError('real E-CPU frame invalid')
    result = CausalStamp.from_dict(frame['causal'])
    if result.actor_id != role:
        raise RenewalError('real E-CPU causal actor mismatch')
    return result


def source_host(reg: Mapping[str,Any], prior: Mapping[str,Any],
                *, protocol: str='passive') -> dict[str,Any]:
    # Only source certificate digest + suspension fingerprint is read here;
    # full signed predecessor evidence is independently verified by V.
    plan = signed_plan(reg, prior['old_certificate']['digest'], sha(prior['suspension']), protocol=protocol)
    clock = context('S')
    stamp = clock.emit_causal_stamp()
    binding = sign(reg,'S','re013_temporal_binding',{
        'plan_digest':plan['digest'], 'prior_digest':prior['old_certificate']['digest'],
        'stamp':stamp.to_dict()})
    return _envelope({'schema':SCHEMA,'role':'S','challenge':reg['challenge'],
                      'plan':plan, 'frame':clock.observe().to_dict(), 'binding':binding})


def observer_host(source: Mapping[str,Any], reg: Mapping[str,Any], role: str,
                  *, sensor: str|None=None) -> dict[str,Any]:
    if role not in ('A','B'):
        raise RenewalError('unknown observer host')
    _check(source,'S')
    if source['challenge'] != reg['challenge']:
        raise RenewalError('different source challenge')
    source_stamp = _stamp(source,'S')
    clock = context(role)
    clock.receive_causal_stamp(source_stamp)
    report = observer_report(reg,source['plan'],role,sensor=sensor,
                             defer_source_mac_to_verifier='S' not in reg.get('keys',{}))
    stamped = clock.emit_causal_stamp()
    binding = sign(reg,role,'re013_temporal_binding',{
        'plan_digest':source['plan']['digest'],
        'report_seal':report['seal']['digest'],
        'stamp':stamped.to_dict()})
    return _envelope({'schema':SCHEMA,'role':role,'challenge':reg['challenge'],
                      'report':report,'frame':clock.observe().to_dict(), 'binding':binding})


def verify(source: Mapping[str,Any], a: Mapping[str,Any], b: Mapping[str,Any],
           prior: Mapping[str,Any], reg: Mapping[str,Any],
           *, assumptions_accepted: bool=False) -> dict[str,Any]:
    for role,doc in (('S',source),('A',a),('B',b)):
        _check(doc,role)
        if doc['challenge'] != reg['challenge']:
            raise RenewalError('host challenge mismatch')
    stamps={r:_stamp(x,r) for r,x in (('S',source),('A',a),('B',b))}
    for role, doc in (('S',source),('A',a),('B',b)):
        binding = verify_signed(doc['binding'],reg,role,'re013_temporal_binding')
        expected = {'plan_digest':source['plan']['digest'],
                    'stamp':stamps[role].to_dict()}
        if role == 'S':
            expected['prior_digest'] = prior['old_certificate']['digest']
        else:
            expected['report_seal'] = doc['report']['seal']['digest']
        if binding != expected:
            raise RenewalError('signed E-CPU causal/evidence binding invalid')
    if (stamps['S'].relation(stamps['A']) != CausalRelation.BEFORE or
        stamps['S'].relation(stamps['B']) != CausalRelation.BEFORE or
        stamps['A'].relation(stamps['B']) != CausalRelation.CONCURRENT):
        raise RenewalError('E-CPU causal handoff or concurrency invalid')
    current = evaluate(reg,prior,source['plan'],a['report'],b['report'],
                       assumptions_accepted=assumptions_accepted)
    return {'schema':SCHEMA, 'causal_relations':{
               'S_before_A':'before','S_before_B':'before','A_concurrent_B':'concurrent'},
            'renewal':current, 'cross_host_elapsed':None,
            'hardware_sensor_attested':False,'physical_detection_guarantee':None}


def demonstration() -> dict[str,Any]:
    from active_recalibration import registration, old_fixture
    reg = registration(deterministic=True)
    old = old_fixture(reg)
    src = source_host(reg,old)
    return verify(src,observer_host(src,reg,'A'),observer_host(src,reg,'B'),old,reg,
                  assumptions_accepted=True)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv)==2 else '--demo'
    if mode == '--demo':
        output = demonstration()
    elif mode == '--source':
        inp=json.load(sys.stdin)
        output=source_host(inp['enrollment'],inp['prior'],protocol=inp.get('protocol','passive'))
    elif mode in ('--A','--B'):
        inp=json.load(sys.stdin)
        output=observer_host(inp['source'],inp['enrollment'],mode[2:])
    elif mode == '--verify':
        inp=json.load(sys.stdin)
        output=verify(inp['source'],inp['A'],inp['B'],inp['prior'],inp['enrollment'],
                      assumptions_accepted=inp.get('assumptions_accepted',False))
    else:
        raise SystemExit('usage: ecpu_re013_hosts.py [--demo|--source|--A|--B|--verify]')
    print(json.dumps(output,indent=2,sort_keys=True))


if __name__=='__main__':
    main()
