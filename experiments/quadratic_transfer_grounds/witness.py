"""Reconstructable TCN-004 computational witness; SHA-256 is NOT identity/trust."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from branch import StructuredState, gate_phases


def _digest(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,
                                    separators=(',',':'),allow_nan=False).encode()).hexdigest()


def state_record(state):
    if not isinstance(state, StructuredState):
        raise TypeError('StructuredState required')
    return {'p':state.p,'kind':state.kind,'curvature':state.a,
            'terms':[[b,float(v.real).hex(),float(v.imag).hex()]
                     for b,v in sorted(state.terms)],
            'error_l2_ideal':float(state.error_l2_ideal).hex(),
            'steps_decimal':str(state.steps_logged)}


def restore_state(data):
    if not isinstance(data,dict) or set(data)!={
        'p','kind','curvature','terms','error_l2_ideal','steps_decimal'}:
        raise ValueError('unexpected state fields')
    if (type(data['steps_decimal']) is not str or not data['steps_decimal'].isascii()
            or not data['steps_decimal'].isdigit() or len(data['steps_decimal'])>1000):
        raise ValueError('invalid procedural step coordinate')
    terms=[]
    for term in data['terms']:
        if not isinstance(term,list) or len(term)!=3 or type(term[0]) is not int:
            raise ValueError('invalid term')
        value=complex(float.fromhex(term[1]),float.fromhex(term[2]))
        terms.append((term[0],value))
    result=StructuredState(data['p'],data['kind'],data['curvature'],tuple(terms),
                           float.fromhex(data['error_l2_ideal']),int(data['steps_decimal']))
    if state_record(result)!=data:
        raise ValueError('noncanonical state encoding')
    return result


def harmonic_receipt(state, strength, *, order=12, rank=7, budget=0.01):
    output,decision=state.after_harmonic(strength,taylor_order=order,
                                         max_terms=rank,absolute_error_budget=budget)
    record={'schema':'ifs.tcn004-computational-witness.v1',
            'input':state_record(state),
            'operation':{'kind':'harmonic','strength':float(strength).hex(),
                         'order':order,'rank':rank,'budget':float(budget).hex()},
            'decision':decision,
            'output':state_record(output) if output is not None else None,
            'authority':'declared computational premise, not externally witnessed'}
    record['sha256']=_digest(record)
    return record


def recheck_harmonic_receipt(record):
    """Check integrity, reconstruct both vectors, and independently check
    every output coordinate against the declared *dense* diagonal action.

    This proves only the numerical witness obligation for provided synthetic
    inputs, conditional on the gate definition. It is not signed evidence,
    source authentication, or a proof of claims about the outside world.
    """
    try:
        if not isinstance(record,dict) or set(record)!={
            'schema','input','operation','decision','output','authority','sha256'}:
            return False
        if record['schema']!='ifs.tcn004-computational-witness.v1' or record['sha256']!=_digest({
            k:v for k,v in record.items() if k!='sha256'}):
            return False
        if record['authority']!='declared computational premise, not externally witnessed':
            return False
        inp=restore_state(record['input'])
        op=record['operation']
        if not isinstance(op,dict) or set(op)!={'kind','strength','order','rank','budget'} or op['kind']!='harmonic':
            return False
        g=float.fromhex(op['strength'])
        budget=float.fromhex(op['budget'])
        proposal,decision=inp.after_harmonic(g,taylor_order=op['order'],
                                              max_terms=op['rank'],absolute_error_budget=budget)
        if decision!=record['decision']:
            return False
        if proposal is None:
            return record['output'] is None
        actual=restore_state(record['output'])
        if (actual.p!=proposal.p or actual.kind!=proposal.kind or actual.a!=proposal.a
                or actual.steps_logged!=proposal.steps_logged or actual.error_l2_ideal!=proposal.error_l2_ideal
                or len(actual.terms)!=len(proposal.terms)):
            return False
        if any((b!=c or abs(v-w)>1e-11) for (b,v),(c,w) in zip(sorted(actual.terms),sorted(proposal.terms))):
            return False
        # independent physical-coordinate parity; not relying solely on digest
        truth=gate_phases(inp.p,'harmonic',g)*inp.dense()
        err=float(np.linalg.norm(actual.dense()-truth))
        return (math.isfinite(err) and err<=decision['l2_truncation_plus_taylor_bound']+1e-9)
    except (ValueError,TypeError,KeyError,OverflowError,ArithmeticError,AttributeError):
        return False
