#!/usr/bin/env python3
"""SPN-009 DIMACS CLI: goal-sensitive, source-checked SAT and #SAT.

  python language_choice_cli.py source.cnf --goal decision --out receipt.json
  python language_choice_cli.py source.cnf --goal count --out count.json
  python language_choice_cli.py source.cnf --verify receipt.json

UNKNOWN has exit code 0 but is not a decision. The source CNF must accompany
any checked receipt. No external solver or dependency is required.
"""
import argparse
import json
from pathlib import Path

from direct_sat_cli import parse_dimacs
from language_choice_sat import compile_language,verify_language_receipt


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source',type=Path)
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument('--out',type=Path)
    mode.add_argument('--verify',type=Path)
    ap.add_argument('--goal',choices=('decision','count'),default='decision')
    ap.add_argument('--node-budget',type=int,default=512)
    ap.add_argument('--rank-cap',type=int,default=3)
    ap.add_argument('--spectral-state-cap',type=int,default=512)
    ap.add_argument('--frontier-cell-cap',type=int,default=200000)
    ap.add_argument('--without-sfi',action='store_true')
    a=ap.parse_args(argv)
    clauses,n=parse_dimacs(a.source.read_text(encoding='utf-8'))
    if a.verify:
        receipt=json.loads(a.verify.read_text(encoding='utf-8'))
        result=verify_language_receipt(clauses,n,receipt,
                                      frontier_cell_cap=a.frontier_cell_cap)
        print(json.dumps({'verified':result,'goal':receipt['goal']}))
    else:
        receipt=compile_language(clauses,n,goal=a.goal,
                        node_budget=a.node_budget,rank_cap=a.rank_cap,
                        spectral_state_cap=a.spectral_state_cap,
                        frontier_cell_cap=a.frontier_cell_cap,
                        allow_sfi=not a.without_sfi)
        if a.out:
            a.out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'result':receipt['result'],'goal':a.goal,
                          'language':receipt['language'],
                          'receipt':str(a.out) if a.out else 'not_written'}))
    return 0

if __name__=='__main__':raise SystemExit(main())
