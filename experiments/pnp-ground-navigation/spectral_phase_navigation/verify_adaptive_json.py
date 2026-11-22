#!/usr/bin/env python3
"""SPN-007 stateless portable JSON checker: no producer session required.

Reads one JSON envelope from stdin: {"n":int,"clauses":[{"variables":
[v0,v1,v2],"forbidden":[b0,b1,b2]},...],"receipt":{...}}.
Outputs a single JSON conclusion to stdout; errors exit nonzero with a
machine-readable refusal on stderr. The verifier shares Python source with
producers' source CNF validation, NOT a separate implementation/language.
"""
from __future__ import annotations

import json
import sys
from adaptive_ground_compiler import verify_adaptive_receipt
from spectral_receipts import formula_digest

MAX_STDIN_BYTES=2_000_000


def check_envelope(envelope):
    if not isinstance(envelope,dict):
        raise ValueError('envelope must be a JSON object')
    n=envelope.get('n')
    rows=envelope.get('clauses')
    if not isinstance(rows,list):
        raise ValueError('clauses must be a list')
    clauses=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!= {'variables','forbidden'}:
            raise ValueError('malformed clause item')
        vs,fs=row['variables'],row['forbidden']
        if not isinstance(vs,list) or not isinstance(fs,list):
            raise ValueError('malformed clause arrays')
        clauses.append((vs,fs))
    status=verify_adaptive_receipt(clauses,n,envelope.get('receipt'))
    return {'verified':status in ('SAT','UNSAT'), 'result':status,
            'source_sha256':formula_digest(clauses,n),
            'ground_energy':envelope['receipt']['ground_energy'],
            'ground_degeneracy':envelope['receipt'].get('ground_degeneracy')}


def main():
    data=sys.stdin.buffer.read(MAX_STDIN_BYTES+1)
    if len(data)>MAX_STDIN_BYTES:
        raise ValueError('JSON envelope exceeds 2 MB input cap')
    envelope=json.loads(data)
    result=check_envelope(envelope)
    print(json.dumps(result,sort_keys=True,separators=(',',':')))


if __name__=='__main__':
    try:
        main()
    except (ValueError,TypeError,KeyError,RecursionError) as error:
        print(json.dumps({'verified':False,'error':type(error).__name__,
                          'reason':str(error)[:120]},sort_keys=True),file=sys.stderr)
        sys.exit(2)
