"""TCN-006: reproducible computational-witness receipt and independent short checks.

An SHA-256 digest protects accidental changes; it is not an external signature.
A successful receipt asserts consistency with the given symbolic circuit only.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from cocycle import ExactOperator
from moving_frame import MovingFrameGround, dense_reference


def _canonical(record):
    return json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _signed_step(value):
    if type(value) is not str or not value.isascii() or not value.isdigit() or len(value) > 350 or (len(value)>1 and value[0]=='0'):
        raise ValueError('canonical bounded nonnegative decimal step string required')
    return int(value)


def replay(program):
    if not isinstance(program, dict) or set(program) != {'p','source','events','coordinates','max_work'}:
        raise ValueError('complete program required')
    p, source, events = program['p'], program['source'], program['events']
    if type(p) is not int or not 3 <= p <= 1021 or type(source) is not int:
        raise ValueError('bounded prime field and source required')
    if type(events) is not list or len(events)>1000:
        raise ValueError('bounded event sequence required')
    state=MovingFrameGround.start(p,source)
    small=True
    direct_events=[]
    direct_steps=0
    for ev in events:
        if not isinstance(ev,dict) or 'kind' not in ev:
            raise ValueError('event kind required')
        kind=ev['kind']
        if kind=='cubic':
            if set(ev)!={'kind','coefficient'} or type(ev['coefficient']) is not int:
                raise ValueError('canonical cubic event required')
            state=state.after_cubic(ev['coefficient'])
            direct_events.append({'kind':'cubic','c':ev['coefficient']})
        elif kind=='harmonic':
            if set(ev)!={'kind','strength_hex'} or type(ev['strength_hex']) is not str:
                raise ValueError('canonical harmonic event required')
            strength=float.fromhex(ev['strength_hex'])
            if not math.isfinite(strength) or strength.hex()!=ev['strength_hex']:
                raise ValueError('finite canonical float required')
            state=state.after_harmonic(strength)
            direct_events.append({'kind':'harmonic','strength':strength})
        elif kind=='schedule':
            if set(ev)!={'kind','pattern','steps_decimal'} or type(ev['pattern']) is not list:
                raise ValueError('canonical schedule required')
            n=_signed_step(ev['steps_decimal'])
            state=state.after_schedule(tuple(ev['pattern']),n)
            direct_steps += n
            if direct_steps > 80:
                small=False
                direct_events=[]
            if small:
                for i in range(n):
                    direct_events.append({'kind':'transfer','a':ev['pattern'][i%len(ev['pattern'])]})
        elif kind=='clifford':
            if set(ev)!={'kind','matrix','quadrant'} or type(ev['matrix']) is not list or type(ev['quadrant']) is not int:
                raise ValueError('canonical Clifford event required')
            op=ExactOperator(p,tuple(tuple(row) for row in ev['matrix']),ev['quadrant'])
            state=state.after_clifford(op)
            # The current dense oracle uses this same kernel for generic
            # Clifford operators; do not call that an independent check.
            small=False
            direct_events=[]
        else:
            raise ValueError('unknown event kind')
    coords=program['coordinates']
    if type(coords) is not list:
        raise ValueError('coordinate list required')
    decision=state.admission(coords, program['max_work'])
    return state,decision,direct_events if small else None


def make_receipt(program):
    state,decision,direct=replay(program)
    admitted=decision['status']=='admitted'
    predictions=([[float(z.real).hex(),float(z.imag).hex()]
                  for y in program['coordinates']
                  for z in [state.amplitude(y, max_work=program['max_work'])]]
                 if admitted else [])
    dense_discrepancy=None
    if admitted and direct is not None:
        reference=dense_reference(state.p,state.source,direct)
        expected=[complex(float.fromhex(x[0]),float.fromhex(x[1])) for x in predictions]
        dense_discrepancy=max(abs(v-reference[y]) for y,v in zip(program['coordinates'],expected))
    out={'schema':'ifs.moving-frame-ground.v1','program':program,
         'state':state.record(),'admission':decision,'predictions':predictions,
         'independent_short_dense_max_error':dense_discrepancy,
         'scope':'symbolic known operator reconstruction, no independent physical observation or cryptographic signature'}
    out['sha256']=hashlib.sha256(_canonical(out)).hexdigest()
    return out


def verify_receipt(record):
    try:
        if not isinstance(record,dict) or set(record)!={
                'schema','program','state','admission','predictions','independent_short_dense_max_error','scope','sha256'}:
            return False
        if record['schema']!='ifs.moving-frame-ground.v1':
            return False
        payload={k:v for k,v in record.items() if k!='sha256'}
        if hashlib.sha256(_canonical(payload)).hexdigest()!=record['sha256']:
            return False
        regenerated=make_receipt(record['program'])
        if regenerated['state']!=record['state'] or regenerated['admission']!=record['admission'] or regenerated['predictions']!=record['predictions']:
            return False
        # Compare short independent direct FFT test without relying on hash alone.
        if regenerated['independent_short_dense_max_error'] != record['independent_short_dense_max_error']:
            return False
        if regenerated['independent_short_dense_max_error'] is not None and regenerated['independent_short_dense_max_error']>1e-8:
            return False
        return regenerated==record
    except (ValueError,TypeError,KeyError,OverflowError,ArithmeticError,AttributeError,IndexError,RecursionError):
        return False
