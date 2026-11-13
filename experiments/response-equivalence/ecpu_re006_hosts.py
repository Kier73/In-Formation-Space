"""RE-006 real E-CPU temporal adapter, used by distinct GitHub Actions jobs.

Vector stamps prove declared message/receipt ordering within an E-CPU model;
artifacts are not physically authenticated sensors, execution, or isolation.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from mailcpu.temporal import CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile
from scoped_intervention_audit import (
    AuditError, check, close_receipt, enroll, monitor_receipt, negative_receipt,
    open_receipt, plant_receipt, verify,
)

ROSTER = {'A':0,'B':0,'M':0,'N':0}


def ctx(actor: str, *, prior: Mapping[str, Any] | None = None) -> TemporalContext:
    kwargs = {'vector':ROSTER} if prior is None else {
        'vector':CausalStamp.from_dict(prior).vector_map(),
        'lamport':CausalStamp.from_dict(prior).lamport,
    }
    return TemporalContext(actor, TemporalProfile(frozenset({ClockDomain.CAUSAL})), **kwargs)


def stamp(clock: TemporalContext) -> dict[str, Any]:
    clock.emit_causal_stamp()
    frame = clock.observe()  # A real, typed E-CPU TemporalFrame.
    if frame.causal is None:
        raise AuditError('E-CPU causal domain missing')
    return frame.causal.to_dict()


def produce_open(reg: Mapping[str, Any]) -> dict[str, Any]:
    return open_receipt(reg, stamp(ctx('A')))


def produce_monitor(reg: Mapping[str, Any], opening: dict, *, permitted: bool = True,
                    sentinel: tuple[int,int,int] = (7,7,7)) -> dict:
    clock = ctx('M')
    clock.receive_causal_stamp(CausalStamp.from_dict(opening['causal']))
    return monitor_receipt(reg, stamp(clock), opening, permitted=permitted, sentinel=sentinel)


def produce_negative(reg: Mapping[str, Any], opening: dict, *, permitted: bool = True,
                     positive_delta: int = 1) -> dict:
    clock = ctx('N')
    clock.receive_causal_stamp(CausalStamp.from_dict(opening['causal']))
    return negative_receipt(reg, stamp(clock), opening, permitted=permitted, positive_delta=positive_delta)


def produce_close(reg: Mapping[str, Any], opening: dict, monitor: dict, negative: dict,
                  *, completed: bool = True) -> dict:
    # A's actor state is explicitly *logically* resumed on a distinct CI job;
    # this does not establish continuity of a physical machine identity.
    clock = ctx('A', prior=opening['causal'])
    clock.receive_causal_stamp(CausalStamp.from_dict(monitor['causal']))
    clock.receive_causal_stamp(CausalStamp.from_dict(negative['causal']))
    return close_receipt(reg, stamp(clock), opening, monitor, negative, completed=completed)


def produce_plant(reg: Mapping[str, Any], closing: dict, *, readout: int = 2) -> dict:
    clock = ctx('B')
    clock.receive_causal_stamp(CausalStamp.from_dict(closing['causal']))
    return plant_receipt(reg, stamp(clock), closing, readout=readout)


def produce_bundle(reg: Mapping[str, Any], *, denied: bool = False,
                   drift: bool = False) -> dict[str, Any]:
    opening = produce_open(reg)
    monitor = produce_monitor(reg, opening, permitted=not denied,
                              sentinel=(7,8,7) if drift else (7,7,7))
    negative = produce_negative(reg, opening)
    closing = produce_close(reg, opening, monitor, negative)
    plant = produce_plant(reg, closing)
    return {'open':opening, 'monitor':monitor, 'negative_control':negative,
            'close':closing, 'plant':plant}


def _frame(record: dict, actor: str, expected_vector: Mapping[str, int]) -> CausalStamp:
    try:
        result = CausalStamp.from_dict(record['causal'])
    except (ValueError, TypeError, KeyError) as error:
        raise AuditError('invalid E-CPU causal stamp') from error
    if result.actor_id != actor or result.vector_map() != dict(expected_vector):
        raise AuditError('unexpected actor or causal vector progression')
    return result


def verify_host(bundle: dict, reg: dict, *, model_scope: str = 'open_world') -> dict[str, Any]:
    result = verify(bundle, reg, model_scope=model_scope)
    a0 = _frame(bundle['open'], 'A', {'A':1,'B':0,'M':0,'N':0})
    m = _frame(bundle['monitor'], 'M', {'A':1,'B':0,'M':2,'N':0})
    n = _frame(bundle['negative_control'], 'N', {'A':1,'B':0,'M':0,'N':2})
    a1 = _frame(bundle['close'], 'A', {'A':4,'B':0,'M':2,'N':2})
    b = _frame(bundle['plant'], 'B', {'A':4,'B':2,'M':2,'N':2})
    expected = {
        'A0_M0':'before', 'A0_N0':'before', 'M0_N0':'concurrent',
        'M0_A1':'before', 'N0_A1':'before', 'A1_B0':'before',
    }
    pairs = {'A0_M0':(a0,m),'A0_N0':(a0,n),'M0_N0':(m,n),
             'M0_A1':(m,a1),'N0_A1':(n,a1),'A1_B0':(a1,b)}
    for label, (first, second) in pairs.items():
        if first.relation(second).value != expected[label]:
            raise AuditError('actual E-CPU causal relation differs from contract')
    return {'schema':'in-formation.response-re006-hosted/0.1',
            'native_ecpu_temporal':True, 'causal_relations':expected,
            'identification':result, 'cross_host_elapsed':None,
            'physical_host_authentication':False,
            'physical_causation_proved':False,
            'hosted_scope':'distinct CI jobs and artifact relay, not distinct physical fault domains'}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: --enroll|--open|--monitor|--negative|--close|--plant|--verify')
    op = sys.argv[1]
    arg = {} if op == '--enroll' else json.load(sys.stdin)
    if op == '--enroll':
        answer = enroll()
    elif op == '--open':
        answer = produce_open(arg['enrollment'])
    elif op == '--monitor':
        answer = produce_monitor(arg['enrollment'],arg['open'])
    elif op == '--negative':
        answer = produce_negative(arg['enrollment'],arg['open'])
    elif op == '--close':
        answer = produce_close(arg['enrollment'],arg['open'],arg['monitor'],arg['negative_control'])
    elif op == '--plant':
        answer = produce_plant(arg['enrollment'],arg['close'])
    elif op == '--verify':
        answer = verify_host(arg['bundle'],arg['enrollment'],model_scope=arg.get('model_scope','open_world'))
    else:
        raise SystemExit('unknown role')
    print(json.dumps(answer, sort_keys=True))


if __name__ == '__main__':
    main()

