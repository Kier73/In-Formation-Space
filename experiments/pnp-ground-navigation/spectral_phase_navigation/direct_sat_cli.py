#!/usr/bin/env python3
"""Direct SAT DIMACS CLI. Exit 0 for a verified result, including UNKNOWN.

Run:
  python direct_sat_cli.py case.cnf --node-budget 512 --out receipt.json
  python direct_sat_cli.py case.cnf --verify receipt.json

The input formula accompanies the proof. Source-order digest binds them.
Only clauses of width <=3 are accepted in this SPN-008 research stage.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from direct_sat_compiler import produce_direct_sat, verify_direct_sat


def parse_dimacs(text):
    """Parse strict, multiline DIMACS CNF; comments may appear between clauses."""
    n=m=None
    clauses=[]; pending=[]
    for line_no,line in enumerate(text.splitlines(),1):
        stripped=line.strip()
        if not stripped or stripped.startswith('c'):continue
        if stripped.startswith('p'):
            parts=stripped.split()
            if n is not None or pending or clauses or len(parts)!=4 or parts[:2]!=['p','cnf']:
                raise ValueError(f'malformed or repeated header on line {line_no}')
            try:n=int(parts[2]);m=int(parts[3])
            except ValueError as exc:raise ValueError(f'invalid header line {line_no}') from exc
            if n<1 or m<0:raise ValueError('invalid DIMACS declared size')
            continue
        if n is None:raise ValueError('missing DIMACS header')
        for part in stripped.split():
            try:lit=int(part)
            except ValueError as exc:raise ValueError(f'invalid literal line {line_no}') from exc
            if lit==0:
                clauses.append(tuple(pending));pending=[]
                if len(clauses)>m:raise ValueError('more clauses than declared')
            elif abs(lit)>n:
                raise ValueError(f'variable outside declared range on line {line_no}')
            else:
                pending.append(lit)
                if len(pending)>3:raise ValueError('only width <=3 supported')
    if n is None or pending or len(clauses)!=m:
        raise ValueError('missing header, unterminated clause, or clause count mismatch')
    return clauses,n


def main(argv=None):
    parser=argparse.ArgumentParser(description='SPN-008 direct SAT with checkable proof or explicit UNKNOWN')
    parser.add_argument('cnf',type=Path,help='DIMACS CNF source, width at most 3')
    parser.add_argument('--node-budget',type=int,default=1024)
    parser.add_argument('--spectral-budget',type=int,default=0)
    parser.add_argument('--out',type=Path,help='write full source-bound JSON receipt')
    parser.add_argument('--verify',type=Path,help='verify existing receipt instead of producing one')
    args=parser.parse_args(argv)
    clauses,n=parse_dimacs(args.cnf.read_text(encoding='utf-8'))
    if args.verify:
        receipt=json.loads(args.verify.read_text(encoding='utf-8'))
    else:
        receipt=produce_direct_sat(clauses,n,args.node_budget,args.spectral_budget)
        if args.out:
            args.out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    status=verify_direct_sat(clauses,n,receipt)
    print(json.dumps({'verified_status':status,'n':n,'clauses':len(clauses),
                      'source_sha256':receipt['source_sha256'],
                      'proof_kind':receipt['proof']['kind']},sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
