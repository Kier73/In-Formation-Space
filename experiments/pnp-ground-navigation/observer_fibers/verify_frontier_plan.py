"""OFG-003 fresh-process verification of a source-bound JSON plan on stdin.

Input: {"intention":{"n":...,"clauses":...,"requested_vars":...,"offers":...},
        "plan":{...}}
A trusted consumer must separately bind the supplied intention to its actual source.
"""
import json
import sys
from frontier_observation_planner import Intention, verify_plan


def run(payload):
    q=payload['intention']
    intention=Intention(q['n'],tuple(tuple(c) for c in q['clauses']),
                        tuple(q['requested_vars']),tuple(tuple(x) for x in q['offers']))
    assert verify_plan(intention,payload['plan'])
    return {'verified':True,'source_identity':payload['plan']['source_identity'],
            'separator':payload['plan']['geometry']['separator'],
            'selected_observation':payload['plan']['selected_policy']['observe']}


if __name__ == '__main__':
    try:
        print(json.dumps(run(json.load(sys.stdin)),sort_keys=True))
    except (KeyError,TypeError,ValueError,AssertionError) as err:
        print(json.dumps({'verified':False,'error':str(err)}),file=sys.stderr)
        sys.exit(1)
