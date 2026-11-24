"""Fresh interpreter receiving only original source and issued certificate on stdin."""
import json,sys
from verify_chain_observer import verify,Reject

try:
    wire=json.load(sys.stdin)
    if set(wire)!={'source','certificate'} or not verify(wire['source'],wire['certificate']):
        raise Reject('invalid source or certificate')
except (Reject,ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:
    print('REFUSED:',str(exc),file=sys.stderr)
    sys.exit(2)
print('verified: original-CNF nonlinear observer Ground')
