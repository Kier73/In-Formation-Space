"""RE-014: cross-job journal admission/revocation using pinned real E-CPU causal stamps.

The CI HMAC enrollment is a fixture, not external identity or hardware truth.
No cross-host elapsed time or physical source guarantee is established.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Mapping

from authority_reconstruction import (
    AuthorityError, _key, append, create_store, evidence_id, export, replay, sign_event,
)
from detection_calibration import canonical, sha

HOST_SCHEMA = 'in-formation.response-re014-ecpu/0.1'
ROSTER = {'Q':0, 'R':0, 'W':0}


def _clock(actor: str):
    from mailcpu.temporal import ClockDomain, TemporalContext, TemporalProfile
    return TemporalContext(actor, TemporalProfile(frozenset({ClockDomain.CAUSAL})), vector=dict(ROSTER))


def _stamp(frame: Any, actor: str):
    from mailcpu.temporal import CausalStamp
    if not isinstance(frame, dict) or frame.get('actor_id') != actor or \
        not isinstance(frame.get('causal'), dict):
        raise AuthorityError('E-CPU frame actor or causal data invalid')
    result = CausalStamp.from_dict(frame['causal'])
    if result.actor_id != actor:
        raise AuthorityError('E-CPU causal-stamp actor mismatch')
    return result


def _wrap(role: str, transcript: Mapping[str,Any], frame: Mapping[str,Any],
          reg: Mapping[str,Any], doc: Mapping[str,Any], *, parent_digest: str | None = None) -> dict[str,Any]:
    signer = 'V' if role == 'Q' else 'R'
    body = {'schema': HOST_SCHEMA, 'role': role,
            'challenge': reg['challenge'], 'evidence_digest': evidence_id(doc),
            'transcript': transcript, 'anchor': transcript['anchor'],
            'parent_digest': parent_digest, 'frame': frame}
    mac = hmac.new(_key(reg,signer),canonical(body),hashlib.sha256).hexdigest()
    return {**body, 'mac': mac, 'digest':sha({**body,'mac':mac})}


def _verify_binding(bundle: Mapping[str,Any], reg: Mapping[str,Any],
                    doc: Mapping[str,Any]) -> CausalStamp:
    if not isinstance(bundle,dict) or set(bundle) != {
            'schema','role','challenge','evidence_digest','transcript',
            'anchor','parent_digest','frame','mac','digest'}:
        raise AuthorityError('authority-host envelope fields invalid')
    role = bundle['role']
    if role not in ('Q','R') or bundle['schema'] != HOST_SCHEMA or \
       bundle['challenge'] != reg['challenge'] or bundle['evidence_digest'] != evidence_id(doc) or \
       bundle['anchor'] != bundle['transcript'].get('anchor'):
        raise AuthorityError('authority-host envelope binding mismatch')
    unsigned={k:v for k,v in bundle.items() if k not in ('mac','digest')}
    signer='V' if role=='Q' else 'R'
    mac=hmac.new(_key(reg,signer),canonical(unsigned),hashlib.sha256).hexdigest()
    if not isinstance(bundle['mac'],str) or not hmac.compare_digest(bundle['mac'],mac):
        raise AuthorityError('authority-host signed stamp/anchor binding invalid')
    if bundle['digest'] != sha({**unsigned,'mac':bundle['mac']}):
        raise AuthorityError('authority-host digest invalid')
    return _stamp(bundle['frame'],role)


def issue_host(reg: Mapping[str,Any], doc: Mapping[str,Any],
               endorsement_m: Mapping[str,Any], endorsement_p: Mapping[str,Any],
               db_path: str|Path) -> dict[str, Any]:
    create_store(db_path)
    for receipt in (endorsement_m,endorsement_p,sign_event(reg,'V','issue',doc)):
        append(db_path,dict(receipt),reg,doc)
    transcript=export(db_path)
    if replay(transcript,reg,doc)['status'] != 'conditionally_admitted':
        raise AuthorityError('issuer cannot claim unverified admission')
    ctx=_clock('Q')
    ctx.emit_causal_stamp()
    return _wrap('Q',transcript,ctx.observe().to_dict(),reg,doc)


def revoke_host(issued: Mapping[str,Any], reg: Mapping[str,Any], doc: Mapping[str,Any],
                db_path: str|Path, *, reason: str='instrument_replaced') -> dict[str,Any]:
    from mailcpu.temporal import CausalRelation
    initial=_verify_binding(issued,reg,doc)
    if issued['role']!='Q' or export(db_path)!=issued['transcript']:
        raise AuthorityError('revocation must follow exact issued journal')
    if replay(issued['transcript'],reg,doc)['status']!='conditionally_admitted':
        raise AuthorityError('only active conditional revision may be revoked')
    append(db_path,sign_event(reg,'R','revoke',doc,reason=reason),reg,doc)
    ctx=_clock('R')
    ctx.receive_causal_stamp(initial)
    ctx.emit_causal_stamp()
    return _wrap('R',export(db_path),ctx.observe().to_dict(),reg,doc,
                 parent_digest=issued['digest'])


def verify_host(bundle: Mapping[str,Any], reg: Mapping[str,Any],
                doc: Mapping[str,Any], *, sqlite_path: str|Path|None=None,
                expected_anchor: Mapping[str,Any]|None=None,
                parent_issued: Mapping[str,Any]|None=None) -> dict[str,Any]:
    from mailcpu.temporal import CausalRelation
    stamp=_verify_binding(bundle,reg,doc)
    if sqlite_path is not None and export(sqlite_path)!=bundle['transcript']:
        raise AuthorityError('durable SQLite reconstruction differs from published journal')
    if bundle['role']=='Q' and bundle['parent_digest'] is not None:
        raise AuthorityError('initial authority host has unexpected parent')
    if bundle['role']=='R':
        if parent_issued is None:
            raise AuthorityError('revocation without preserved issuance ancestor')
        earlier=_verify_binding(parent_issued,reg,doc)
        if parent_issued['role']!='Q' or bundle['parent_digest']!=parent_issued['digest'] or \
            earlier.relation(stamp)!=CausalRelation.BEFORE or \
            bundle['transcript']['entries'][:len(parent_issued['transcript']['entries'])] != parent_issued['transcript']['entries']:
            raise AuthorityError('revocation parent or E-CPU causal continuity invalid')
    result=replay(bundle['transcript'],reg,doc,independently_anchored=expected_anchor)
    if (bundle['role']=='Q' and result['status']!='conditionally_admitted') or \
       (bundle['role']=='R' and result['status']!='revoked'):
        raise AuthorityError('authority-host claimed state incompatible with journal')
    verifier=_clock('W')
    verifier.receive_causal_stamp(stamp)
    verifier.emit_causal_stamp()
    if stamp.relation(verifier.current_causal_stamp())!=CausalRelation.BEFORE:
        raise AuthorityError('E-CPU independent verifier did not causally follow decision')
    return {'schema':HOST_SCHEMA,'authority':result,
            'causal_relation':f"{bundle['role']}_before_W",
            'cross_host_elapsed':None,'physical_assumptions_proved':False,
            'production_attestation':None}


def _read_json(path: str) -> Any:
    with open(path,encoding='utf-8') as f: return json.load(f)


def main() -> None:
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=('endorse','issue','revoke','verify'))
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--db')
    opts=parser.parse_args()
    x=_read_json(opts.input)
    if opts.operation=='endorse':
        result=sign_event(x['enrollment'],x['role'],'endorse',x['evidence'])
    elif opts.operation=='issue':
        result=issue_host(x['enrollment'],x['evidence'],x['M'],x['P'],opts.db)
    elif opts.operation=='revoke':
        result=revoke_host(x['issued'],x['enrollment'],x['evidence'],opts.db)
    else:
        result=verify_host(x['authority'],x['enrollment'],x['evidence'],
                           sqlite_path=opts.db,expected_anchor=x['expected_anchor'],
                           parent_issued=x.get('issued'))
    Path(opts.output).write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
