"""RE-015 hosted recovery using genuine pinned E-CPU temporal stamps.

Distinct hosted jobs are NOT attested physical authorities. The test sends
fixture signing secrets via CI artifacts; don't reuse this as production PKI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any,Mapping

from credential_continuity import (
    ContinuityError, _base_context, _event_body, _verify, append_journal,
    append_replica, checkpoint_body, empty_ledger, export_journal,
    initialize_journal, initialize_replica, latest_replica, export_replica, replay_ledger,
    sign_checkpoint, sign_governance, verify_recovery, verify_checkpoint,
)
from detection_calibration import sha

HOST_SCHEMA='in-formation.response-re015-ecpu/0.1'
ROSTER={a:0 for a in ('Q','R','W1','W2','V')}


def _context(actor:str):
    from mailcpu.temporal import TemporalContext,TemporalProfile,ClockDomain
    return TemporalContext(actor,TemporalProfile(frozenset({ClockDomain.CAUSAL})),vector=dict(ROSTER))


def _stamp(frame:Any,actor:str):
    from mailcpu.temporal import CausalStamp
    if not isinstance(frame,dict) or frame.get('actor_id')!=actor or \
        not isinstance(frame.get('causal'),dict):
        raise ContinuityError('E-CPU frame actor invalid')
    out=CausalStamp.from_dict(frame['causal'])
    if out.actor_id!=actor:raise ContinuityError('E-CPU causal actor mismatch')
    return out


def _wrap(role:str,ledger:Mapping[str,Any],frame:Mapping[str,Any],
          key_hex:str, *, parent:str|None=None)->dict[str,Any]:
    from credential_continuity import sign_by_role
    body={'schema':HOST_SCHEMA,'role':role,'ledger':ledger,'frame':frame,
          'parent':parent,'ledger_anchor':ledger['anchor']}
    signed={**body,'binding_signature':sign_by_role({'role':role,'anchor':ledger['anchor'],
        'stamp':_stamp(frame,role).to_dict(),'parent':parent},key_hex)}
    return {**signed,'digest':sha(signed)}


def _check_bundle(doc:Any, trust:Mapping[str,Any], baseline:Mapping[str,Any],
                  role:str)->Any:
    if not isinstance(doc,dict) or set(doc)!={'schema','role','ledger','frame','parent',
            'ledger_anchor','binding_signature','digest'} or \
       doc['schema']!=HOST_SCHEMA or doc['role']!=role or doc['ledger_anchor']!=doc['ledger'].get('anchor') or \
       doc['digest']!=sha({k:v for k,v in doc.items() if k!='digest'}):
        raise ContinuityError('host bundle integrity/role invalid')
    replay_ledger(doc['ledger'],trust,baseline)
    actor_stamp=_stamp(doc['frame'],role)
    if role=='Q':public=trust['public']['R0']
    elif role=='R':public=doc['ledger']['rows'][0]['event']['body']['new_public_key']
    else:raise ContinuityError('host role unauthorized')
    _verify(public,{'role':role,'anchor':doc['ledger_anchor'],
        'stamp':actor_stamp.to_dict(),'parent':doc['parent']},doc['binding_signature'])
    return actor_stamp


def rotate_host(baseline:Mapping[str,Any],trust:Mapping[str,Any],private:Mapping[str,str],
                journal_path:str|Path, *, replacement_public:str|None=None)->dict[str,Any]:
    initialize_journal(journal_path)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    new=replacement_public or Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private['R1'])).public_key().public_bytes(
        serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
    body=_event_body('rotate',trust,_base_context(baseline),
        {'count':0,'head':None,'current_public':trust['public']['R0']},new_public=new)
    event=sign_governance(body,{'R':private['R0'],**{k:private[k] for k in ('W1','W2')}})
    append_journal(journal_path,event,trust,baseline)
    ctx=_context('Q');ctx.emit_causal_stamp()
    return _wrap('Q',export_journal(journal_path),ctx.observe().to_dict(),private['R0'])


def revoke_host(previous:Mapping[str,Any],baseline:Mapping[str,Any],
                trust:Mapping[str,Any],private:Mapping[str,str],journal_path:str|Path)->dict[str,Any]:
    prior=_check_bundle(previous,trust,baseline,'Q')
    if export_journal(journal_path)!=previous['ledger'] or previous['parent'] is not None:
        raise ContinuityError('revocation received stale or foreign persisted journal')
    rotated=previous['ledger'];key=rotated['rows'][0]['event']['body']['new_public_key']
    body=_event_body('revoke',trust,_base_context(baseline),
        {'count':1,'head':rotated['anchor']['head'],'current_public':key},
        reason='instrument_replaced')
    event=sign_governance(body,{'R':private['R1'],**{k:private[k] for k in ('W1','W2')}})
    append_journal(journal_path,event,trust,baseline)
    ctx=_context('R');ctx.receive_causal_stamp(prior);ctx.emit_causal_stamp()
    return _wrap('R',export_journal(journal_path),ctx.observe().to_dict(),
                 private['R1'],parent=previous['digest'])


def witness_host(role:str,rotated:Mapping[str,Any],revoked:Mapping[str,Any],
                 baseline:Mapping[str,Any],trust:Mapping[str,Any],private_key:str,
                 replica_path:str|Path)->dict[str,Any]:
    if role not in ('W1','W2'):raise ContinuityError('witness role invalid')
    original=_check_bundle(rotated,trust,baseline,'Q')
    last=_check_bundle(revoked,trust,baseline,'R')
    from mailcpu.temporal import CausalRelation
    if original.relation(last)!=CausalRelation.BEFORE or revoked['parent']!=rotated['digest']:
        raise ContinuityError('witness cannot accept causal discontinuity')
    initialize_replica(replica_path)
    signed=[]
    for doc in (empty_ledger(),rotated['ledger'],revoked['ledger']):
        item=sign_checkpoint(role,checkpoint_body(doc,trust,baseline),private_key)
        append_replica(replica_path,item,role,trust)
        signed.append(item)
    ctx=_context(role);ctx.receive_causal_stamp(last);ctx.emit_causal_stamp()
    result={'schema':HOST_SCHEMA,'role':role,'heads':signed,'latest':latest_replica(replica_path),
            'frame':ctx.observe().to_dict(),'parent':revoked['digest']}
    return {**result,'digest':sha(result)}


def verify_host(rotated:Mapping[str,Any],revoked:Mapping[str,Any],
                witnesses:Mapping[str,Any],baseline:Mapping[str,Any],
                trust:Mapping[str,Any], *, journal_path:str|Path|None=None,
                witness_sqlite:Mapping[str,str|Path]|None=None)->dict[str,Any]:
    from mailcpu.temporal import CausalRelation
    q=_check_bundle(rotated,trust,baseline,'Q');r=_check_bundle(revoked,trust,baseline,'R')
    if q.relation(r)!=CausalRelation.BEFORE or revoked['parent']!=rotated['digest']:
        raise ContinuityError('revocation not causally linked to rotation')
    if revoked['ledger']['rows'][:len(rotated['ledger']['rows'])]!=rotated['ledger']['rows']:
        raise ContinuityError('revocation lost earlier authenticated record')
    if journal_path is not None and export_journal(journal_path)!=revoked['ledger']:
        raise ContinuityError('SQLite governance journal changed or rolled back')
    if set(witnesses)!={'W1','W2'}:raise ContinuityError('independent witness pair absent')
    stamps={};latest={}
    for role in ('W1','W2'):
        record=witnesses[role]
        if not isinstance(record,dict) or set(record)!={'schema','role','heads','latest','frame','parent','digest'} or \
           record['schema']!=HOST_SCHEMA or record['role']!=role or \
           record['parent']!=revoked['digest'] or \
           record['digest']!=sha({k:v for k,v in record.items() if k!='digest'}):
            raise ContinuityError('external witness host envelope invalid')
        stamps[role]=_stamp(record['frame'],role)
        if r.relation(stamps[role])!=CausalRelation.BEFORE:
            raise ContinuityError('external witness not causally after revocation')
        if not isinstance(record['heads'],list) or len(record['heads'])!=3:
            raise ContinuityError('missing witness archival checkpoint history')
        for i,(receipt,ledger) in enumerate(zip(record['heads'],
                                                (empty_ledger(),rotated['ledger'],revoked['ledger']))):
            expected=checkpoint_body(ledger,trust,baseline)
            if verify_checkpoint(receipt,role,trust)!=expected:
                raise ContinuityError('independent witness archived inconsistent head')
        if record['latest']!=record['heads'][-1]:
            raise ContinuityError('witness latest head differs from archive')
        latest[role]=record['latest']
        if witness_sqlite is not None and (role not in witness_sqlite or
              export_replica(witness_sqlite[role])!=record['heads']):
            raise ContinuityError('external witness SQLite database differs from signed archive')
    if stamps['W1'].relation(stamps['W2'])!=CausalRelation.CONCURRENT:
        raise ContinuityError('witness host causal independence assertion invalid')
    recovered=verify_recovery(revoked['ledger'],baseline,trust,latest)
    verifier=_context('V');verifier.receive_causal_stamp(stamps['W1']);verifier.receive_causal_stamp(stamps['W2']);verifier.emit_causal_stamp()
    return {'schema':HOST_SCHEMA,'reconstructed':recovered,
            'causal_relations':{'Q_before_R':'before','R_before_W1':'before','R_before_W2':'before',
                'W1_concurrent_W2':'concurrent'},
            'verifier_causally_after_witnesses':True,
            'root_private_keys_required_for_verifier':False,
            'legacy_re014_hmac_keys_required':True,
            'external_hardware_identity_attested':False,'physical_clock_elapsed':None}


def main():
    if len(sys.argv)!=3 or sys.argv[1] not in ('--rotate','--revoke','--W1','--W2','--verify'):
        raise SystemExit('usage: ecpu_re015_hosts.py --rotate|--revoke|--W1|--W2|--verify request.json')
    op=sys.argv[1]; data=json.loads(Path(sys.argv[2]).read_text())
    if op=='--rotate':out=rotate_host(data['baseline'],data['trust'],data['private'],data['db'],
        replacement_public=data.get('replacement_public'))
    elif op=='--revoke':out=revoke_host(data['rotated'],data['baseline'],data['trust'],data['private'],data['db'])
    elif op in ('--W1','--W2'):
        out=witness_host(op[2:],data['rotated'],data['revoked'],data['baseline'],
                         data['trust'],data['private'],data['db'])
    else:out=verify_host(data['rotated'],data['revoked'],data['witnesses'],
                         data['baseline'],data['trust'],journal_path=data.get('db'),
                         witness_sqlite=data.get('witness_sqlite'))
    print(json.dumps(out,sort_keys=True,indent=2))

if __name__=='__main__':main()