"""RE-016 CI-only migration with real E-CPU causal frames and public replay.

The ceremony has historical HMAC keys. Signer and public verifier jobs must NOT.
Three job-scoped Ed25519 keys are stored as short-lived CI artifacts; this is
NOT a protected hardware PKI or independent organizational custody.
"""
from __future__ import annotations

import json
import sys
from typing import Any,Mapping

from credential_continuity import _verify as verify_ed, _sign as sign_ed
from detection_calibration import sha
from public_migration import (
    SCHEMA as MIGRATION_SCHEMA, MigrationError, attest_migration, pin,
    prepare_migration, public_verify,
)

HOST_SCHEMA='in-formation.response-re016-ecpu/0.1'
ROSTER={k:0 for k in ('C','R1','W1','W2','V')}
ROLES=('R1','W1','W2')


def ctx(role:str):
    from mailcpu.temporal import TemporalContext,TemporalProfile,ClockDomain
    return TemporalContext(role,TemporalProfile(frozenset({ClockDomain.CAUSAL})),vector=dict(ROSTER))


def stamp(doc:Any, role:str):
    from mailcpu.temporal import CausalStamp
    if not isinstance(doc,dict) or doc.get('actor_id')!=role or not isinstance(doc.get('causal'),dict):
        raise MigrationError('E-CPU frame role invalid')
    result=CausalStamp.from_dict(doc['causal'])
    if result.actor_id!=role:raise MigrationError('E-CPU causal actor mismatch')
    return result


def wrap(body:dict)->dict:
    return {**body,'digest':sha(body)}


def check(doc:Any,role:str)->None:
    if not isinstance(doc,dict) or doc.get('role')!=role or doc.get('schema')!=HOST_SCHEMA or \
       doc.get('digest')!=sha({k:v for k,v in doc.items() if k!='digest'}):
        raise MigrationError('host envelope integrity or role invalid')


def ceremony_host(payload:Mapping[str,Any])->dict:
    """LEGACY-KEY-HOLDING job. Public output excludes historical secret bytes."""
    body,public=prepare_migration(payload['baseline'],payload['ledger'],
        payload['trust'],payload['checkpoints'])
    c=ctx('C');c.emit_causal_stamp()
    return wrap({'schema':HOST_SCHEMA,'role':'C','migration_body':body,
        'public_history':public,'ledger':payload['ledger'],'trust':payload['trust'],
        'checkpoints':payload['checkpoints'],'frame':c.observe().to_dict(),
        'historical_hmac_replay_performed_in_this_job':True})


def signer_host(role:str,ceremony:Mapping[str,Any],key:str)->dict:
    if role not in ROLES:raise MigrationError('unauthorized migration signer role')
    check(ceremony,'C')
    if ceremony['migration_body']['trust_digest']!=sha(ceremony['trust']) or \
       ceremony['migration_body']['public_history_digest']!=sha(ceremony['public_history']):
        raise MigrationError('ceremony public evidence changed')
    c=stamp(ceremony['frame'],'C')
    mine=ctx(role);mine.receive_causal_stamp(c);mine.emit_causal_stamp()
    frame=mine.observe().to_dict()
    signature=sign_ed(key,ceremony['migration_body'])
    binding={'role':role,'ceremony_digest':ceremony['digest'],
        'migration_body_digest':sha(ceremony['migration_body']),
        'stamp':stamp(frame,role).to_dict(),'migration_signature':signature}
    proof=sign_ed(key,binding)
    return wrap({'schema':HOST_SCHEMA,'role':role,'ceremony_digest':ceremony['digest'],
                 'frame':frame,'migration_signature':signature,
                 'signed_binding':proof,'no_legacy_keys_received':True})


def assemble(ceremony:Mapping[str,Any], signers:Mapping[str,Mapping[str,Any]])->dict:
    from mailcpu.temporal import CausalRelation
    check(ceremony,'C')
    if not isinstance(signers,dict) or set(signers)!=set(ROLES):
        raise MigrationError('independent signed migration jobs missing')
    t=ceremony['trust'];b=ceremony['migration_body']
    parent=stamp(ceremony['frame'],'C')
    vectors={}
    for role in ROLES:
        doc=signers[role];check(doc,role)
        if doc.get('no_legacy_keys_received') is not True or doc.get('ceremony_digest')!=ceremony['digest']:
            raise MigrationError('signer scope and handoff invalid')
        st=stamp(doc['frame'],role)
        if parent.relation(st)!=CausalRelation.BEFORE:
            raise MigrationError('signer must causally follow migration ceremony')
        key=b['current_public'] if role=='R1' else t['public'][role]
        verify_ed(key,b,doc['migration_signature'])
        binding={'role':role,'ceremony_digest':ceremony['digest'],
                 'migration_body_digest':sha(b),'stamp':st.to_dict(),
                 'migration_signature':doc['migration_signature']}
        verify_ed(key,binding,doc['signed_binding'])
        vectors[role]=st
    for i,first in enumerate(ROLES):
        for second in ROLES[i+1:]:
            if vectors[first].relation(vectors[second])!=CausalRelation.CONCURRENT:
                raise MigrationError('unjustified signer causal ordering')
    body={'schema':MIGRATION_SCHEMA,'body':b,
          'signatures':{r:signers[r]['migration_signature'] for r in ROLES}}
    migration={**body,'digest':sha(body)}
    return {'migration':migration,'retained_pin':pin(t,migration,ceremony['ledger']),
            'verified_causal_relation':'C_before_each_signer; signers_pairwise_concurrent'}


def public_verifier_host(ceremony:Mapping[str,Any],signers:Mapping[str,Mapping[str,Any]],
                         retained_pin:Mapping[str,Any])->dict:
    joined=assemble(ceremony,signers)
    result=public_verify(joined['migration'],ceremony['public_history'],
            ceremony['ledger'],ceremony['trust'],ceremony['checkpoints'],retained_pin)
    v=ctx('V')
    for role in ROLES:v.receive_causal_stamp(stamp(signers[role]['frame'],role))
    v.emit_causal_stamp()
    return wrap({'schema':HOST_SCHEMA,'role':'V','migration':joined['migration'],
         'result':result,'frame':v.observe().to_dict(),
         'public_history_digest':sha(ceremony['public_history']),
         'retained_pin':retained_pin,
         'causal_relation':joined['verified_causal_relation'],
         'legacy_key_material_used':False})


def independent_replay(ceremony:Mapping[str,Any], signers:Mapping[str,Mapping[str,Any]],
                       retained_pin:Mapping[str,Any], received:Mapping[str,Any])->dict:
    check(received,'V')
    fresh=public_verifier_host(ceremony,signers,retained_pin)
    if fresh['result']!=received['result'] or fresh['migration']!=received['migration'] or \
       fresh['public_history_digest']!=received['public_history_digest'] or \
       fresh['retained_pin']!=received['retained_pin']:
        raise MigrationError('independent post-migration public replay differs')
    return {'status':'independently_replayed_public_attestation',
            'historic_hmac_reverified':False,'legacy_secret_received':False,
            'certificate_status':fresh['result']['status']}


def demo()->dict:
    from public_migration import hosted_material
    material=hosted_material(deterministic=True)
    c=ceremony_host(material['ceremony'])
    signed={r:signer_host(r,c,material['signer_keys'][r]) for r in ROLES}
    pkg=assemble(c,signed)
    result=public_verifier_host(c,signed,pkg['retained_pin'])
    return independent_replay(c,signed,pkg['retained_pin'],result)


def main():
    if len(sys.argv)!=2 or sys.argv[1] not in ('--ceremony','--R1','--W1','--W2','--assemble','--verify','--replay','--demo'):
        raise SystemExit('usage: ecpu_re016_hosts.py --ceremony|--R1|--W1|--W2|--assemble|--verify|--replay|--demo')
    op=sys.argv[1]
    request=json.load(sys.stdin) if op!='--demo' else None
    if op=='--ceremony':out=ceremony_host(request['ceremony'])
    elif op in ('--R1','--W1','--W2'):out=signer_host(op[2:],request['ceremony'],request['private_key'])
    elif op=='--assemble':out=assemble(request['ceremony'],request['signers'])
    elif op=='--verify':out=public_verifier_host(request['ceremony'],request['signers'],request['pin'])
    elif op=='--replay':out=independent_replay(request['ceremony'],request['signers'],request['pin'],request['received'])
    else:out=demo()
    print(json.dumps(out,indent=2,sort_keys=True))

if __name__=='__main__':main()