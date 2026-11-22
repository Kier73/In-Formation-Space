#!/usr/bin/env python3
"""Source-only JSON verification entrypoint for GRC-001 continuity receipts."""
import json
import sys
from ground_revision_continuity import verify_revision


def main(argv):
    if len(argv)!=2:
        raise SystemExit('usage: verify_ground_revision_json.py RECORD.json')
    with open(argv[1],encoding='utf-8') as stream:
        obj=json.load(stream)
    if set(obj)!={'n','old_clauses','new_clauses','receipt'}:
        raise ValueError('unexpected revision envelope keys')
    out=verify_revision(obj['old_clauses'],obj['new_clauses'],obj['n'],obj['receipt'])
    print(json.dumps({'result':out,'accepted':out!='UNKNOWN'}))

if __name__=='__main__':main(sys.argv)
