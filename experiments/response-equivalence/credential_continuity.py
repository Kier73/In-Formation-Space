"""RE-015: separate-key rotation, durable authority replay and external anti-rollback.

Ed25519 proves a signature under a *trusted enrollment*, NOT that a role is
physically independent or its calibration assumptions are true. Two signed
checkpoint replicas make a stale authority database detectable only while at
least one checkpoint head is retained independently and presented to replay.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

from authority_reconstruction import (AuthorityError, append as append_base,
    create_store as create_base, evidence, export as export_base,
    registration as base_registration, replay as replay_base,
    sign_event as sign_base)
from detection_calibration import canonical, sha

SCHEMA = 'in-formation.response-re015-credential-continuity/0.1'
CHECKPOINT_SCHEMA = 'in-formation.response-re015-checkpoint/0.1'
ROOTS = ('W1', 'W2')
REASONS = ('instrument_replaced', 'source_challenge_invalidated', 'new_conflicting_evidence')
EVENT_FIELDS = frozenset(('schema','body','signatures','digest'))
ROW_FIELDS = frozenset(('sequence','parent','event','entry_digest'))
BODY_FIELDS = frozenset(('kind','session','evidence_digest','certificate_digest',
    'claim_scope','base_anchor','sequence','parent','current_key_id','new_public_key','reason'))
CHECKPOINT_FIELDS = frozenset(('schema','role','body','signature','digest'))


class ContinuityError(ValueError):
    """A key transition, authority recovery or externally retained head is invalid."""


def _private(seed: bytes | None = None) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(seed) if seed is not None else Ed25519PrivateKey.generate()


def _public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(serialization.Encoding.Raw,
                                         serialization.PublicFormat.Raw).hex()


def _private_hex(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption()).hex()


def enrollment(*, deterministic: bool = False) -> dict[str, Any]:
    """Synthetic trust genesis. The fixture issuer is not external PKI/attestation."""
    def create(name: str) -> Ed25519PrivateKey:
        return _private(hashlib.sha256(('RE015-fixture-'+name).encode()).digest()
                        if deterministic else None)
    secrets_by_role = {role: create(role) for role in ('R0','R1',*ROOTS)}
    private = {role: _private_hex(key) for role,key in secrets_by_role.items()}
    public = {role: _public_hex(secrets_by_role[role]) for role in ('R0',*ROOTS)}
    return {'trust': {'schema':SCHEMA, 'session': 're015-demo-session' if deterministic else secrets.token_hex(24),
                       'public':public, 'policy':'R-key plus both root witnesses required'},
            'private':private, 'replacement_public': _public_hex(secrets_by_role['R1'])}


def _sign(key_hex: str, body: Mapping[str, Any]) -> str:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex)).sign(canonical(body)).hex()


def _verify(key_hex: str, body: Mapping[str, Any], signature: Any) -> None:
    try:
        if not isinstance(signature, str) or len(signature) != 128:
            raise ValueError('invalid signature length')
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(
            bytes.fromhex(signature), canonical(body))
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ContinuityError('Ed25519 enrollment signature invalid') from exc


def issue_baseline() -> dict[str, Any]:
    """Reconstructable RE-014 issued state, not a new issued certificate."""
    reg = base_registration(deterministic=True)
    doc = evidence(reg)
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory)/'authority.sqlite3'
        create_base(db)
        for role,kind in (('M','endorse'),('P','endorse'),('V','issue')):
            append_base(db, sign_base(reg,role,kind,doc),reg,doc)
        transcript=export_base(db)
    if replay_base(transcript,reg,doc)['status'] != 'conditionally_admitted':
        raise ContinuityError('RE-014 baseline not reconstructable')
    return {'registration':reg, 'evidence':doc, 'issued':transcript}


def _base_context(baseline: Mapping[str,Any]) -> dict[str,Any]:
    if not isinstance(baseline,dict) or set(baseline) != {'registration','evidence','issued'}:
        raise ContinuityError('missing RE-014 reconstructable basis')
    try:
        result = replay_base(baseline['issued'],baseline['registration'],baseline['evidence'])
    except (AuthorityError, KeyError, TypeError, ValueError) as exc:
        raise ContinuityError('original authority evidence invalid') from exc
    if result['status'] != 'conditionally_admitted' or result['journal_anchor']['count'] != 3:
        raise ContinuityError('original authority no longer conditionally issued')
    return {'evidence_digest':result['evidence_digest'],
            'certificate_digest':result['certificate_digest'],
            'claim_scope':result['scope'],
            'base_anchor':result['journal_anchor']}


def empty_ledger() -> dict[str,Any]:
    return {'schema':SCHEMA,'rows':[],'anchor':{'count':0,'head':None}}


def _event_body(kind: str, trust: Mapping[str,Any], base: Mapping[str,Any],
                state: Mapping[str,Any], *, new_public: str|None=None,
                reason: str|None=None) -> dict[str,Any]:
    if kind == 'rotate':
        if not isinstance(new_public,str) or len(new_public)!=64 or new_public == state['current_public']:
            raise ContinuityError('rotation requires distinct new Ed25519 public key')
        try: Ed25519PublicKey.from_public_bytes(bytes.fromhex(new_public))
        except ValueError as exc: raise ContinuityError('invalid replacement key') from exc
        if reason is not None: raise ContinuityError('rotation has no revoke reason')
    elif kind == 'revoke':
        if reason not in REASONS or new_public is not None:
            raise ContinuityError('revocation reason invalid')
    else:
        raise ContinuityError('unknown governance decision')
    return {'kind':kind,'session':trust['session'], **base,
            'sequence':state['count'],'parent':state['head'],
            'current_key_id':sha({'public':state['current_public']}),
            'new_public_key':new_public,'reason':reason}


def sign_governance(body: Mapping[str,Any], signers: Mapping[str,str]) -> dict[str,Any]:
    """The production of endorsements may occur in three separate jobs."""
    if not isinstance(body,dict) or set(body)!=BODY_FIELDS or set(signers)!={'R',*ROOTS}:
        raise ContinuityError('governance signers or payload incomplete')
    sigs={role:_sign(signers[role],body) for role in ('R',*ROOTS)}
    payload={'schema':SCHEMA,'body':body,'signatures':sigs}
    return {**payload,'digest':sha(payload)}


def sign_by_role(body: Mapping[str,Any], key_hex: str) -> str:
    return _sign(key_hex,body)


def assemble_event(body: Mapping[str,Any], signatures: Mapping[str,str]) -> dict[str,Any]:
    if not isinstance(body,dict) or set(body)!=BODY_FIELDS or set(signatures)!={'R',*ROOTS}:
        raise ContinuityError('governance event incomplete')
    payload={'schema':SCHEMA,'body':dict(body),'signatures':dict(signatures)}
    return {**payload,'digest':sha(payload)}


def replay_ledger(ledger: Mapping[str,Any], trust: Mapping[str,Any],
                  baseline: Mapping[str,Any]) -> dict[str,Any]:
    """Rebuild active signer, policy, and status; never accept a stored status."""
    if not isinstance(trust,dict) or trust.get('schema')!=SCHEMA or \
       not isinstance(trust.get('session'),str) or not trust['session'] or \
       trust.get('policy') != 'R-key plus both root witnesses required' or \
       not isinstance(trust.get('public'),dict) or set(trust['public'])!={'R0',*ROOTS}:
        raise ContinuityError('trust genesis invalid')
    base=_base_context(baseline)
    if not isinstance(ledger,dict) or set(ledger) != {'schema','rows','anchor'} or \
       ledger['schema']!=SCHEMA or not isinstance(ledger['rows'],list):
        raise ContinuityError('governance ledger invalid')
    current=trust['public']['R0']; previous=None; rotated=False; revoked=False
    for index,row in enumerate(ledger['rows']):
        if not isinstance(row,dict) or set(row)!=ROW_FIELDS or \
           type(row['sequence']) is not int or row['sequence']!=index or row['parent']!=previous or \
           row['entry_digest']!=sha({'sequence':index,'parent':previous,'event':row['event']}):
            raise ContinuityError('governance journal chain broken')
        event=row['event']
        if not isinstance(event,dict) or set(event)!=EVENT_FIELDS or event['schema']!=SCHEMA or \
           event['digest']!=sha({k:v for k,v in event.items() if k!='digest'}) or \
           not isinstance(event['signatures'],dict) or set(event['signatures'])!={'R',*ROOTS}:
            raise ContinuityError('governance receipt integrity invalid')
        body=event['body']
        expected={'session':trust['session'],**base, 'sequence':index,'parent':previous,
                  'current_key_id':sha({'public':current})}
        if not isinstance(body,dict) or set(body)!=BODY_FIELDS or \
           any(body.get(k)!=v for k,v in expected.items()):
            raise ContinuityError('governance evidence, scope, session or signer epoch invalid')
        _verify(current,body,event['signatures']['R'])
        for witness in ROOTS:_verify(trust['public'][witness],body,event['signatures'][witness])
        if body['kind']=='rotate' and not rotated and not revoked:
            new=body['new_public_key']
            if not isinstance(new,str) or len(new)!=64 or new==current or body['reason'] is not None:
                raise ContinuityError('invalid key transition')
            try:Ed25519PublicKey.from_public_bytes(bytes.fromhex(new))
            except ValueError as exc:raise ContinuityError('invalid new public key') from exc
            current=new; rotated=True
        elif body['kind']=='revoke' and rotated and not revoked and \
             body['new_public_key'] is None and body['reason'] in REASONS:
            revoked=True
        else:raise ContinuityError('governance decision not authorized in current state')
        previous=row['entry_digest']
    expected_anchor={'count':len(ledger['rows']),'head':previous}
    if ledger['anchor']!=expected_anchor:
        raise ContinuityError('self-declared governance anchor invalid')
    return {'status':'revoked' if revoked else 'conditionally_admitted',
            'rotated':rotated,'governance_anchor':expected_anchor,
            'base_anchor':base['base_anchor'], 'evidence_digest':base['evidence_digest'],
            'certificate_digest':base['certificate_digest'], 'claim_scope':base['claim_scope'],
            'current_key_id':sha({'public':current}),
            'legacy_re014_hmac_verification_key_required':True,
            'issuer_process_required_for_recovery':False,
            'physical_assumptions_proved':False,'physical_signer_identity_proved':False}


@contextmanager
def _database(path: str|Path, *, immediate: bool=False):
    conn=sqlite3.connect(str(path),isolation_level='IMMEDIATE' if immediate else 'DEFERRED')
    try:
        with conn: yield conn
    finally:conn.close()


def initialize_journal(path: str|Path) -> None:
    with _database(path) as conn:
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('CREATE TABLE journal(sequence INTEGER PRIMARY KEY, parent TEXT, event TEXT NOT NULL, entry_digest TEXT NOT NULL)')
        for operation in ('UPDATE','DELETE'):
            conn.execute(f"CREATE TRIGGER no_{operation.lower()}_journal BEFORE {operation} ON journal "
                         "BEGIN SELECT RAISE(ABORT,'append-only'); END")


def export_journal(path: str|Path) -> dict[str,Any]:
    with _database(path) as conn:
        data=conn.execute('SELECT sequence,parent,event,entry_digest FROM journal ORDER BY sequence').fetchall()
    rows=[]
    for sequence,parent,raw,entry in data:
        try: event=json.loads(raw)
        except (ValueError,TypeError) as exc:raise ContinuityError('unparseable governance journal') from exc
        if raw!=canonical(event).decode():raise ContinuityError('noncanonical governance journal')
        rows.append({'sequence':sequence,'parent':parent,'event':event,'entry_digest':entry})
    return {'schema':SCHEMA,'rows':rows,'anchor':{'count':len(rows),
        'head':rows[-1]['entry_digest'] if rows else None}}


def append_journal(path: str|Path, event: Mapping[str,Any],trust: Mapping[str,Any],
                   baseline: Mapping[str,Any]) -> dict[str,Any]:
    with _database(path,immediate=True) as conn:
        data=conn.execute('SELECT sequence,parent,event,entry_digest FROM journal ORDER BY sequence').fetchall()
        rows=[]
        for sequence,parent,raw,entry in data:
            parsed=json.loads(raw)
            if raw!=canonical(parsed).decode():raise ContinuityError('noncanonical prior journal')
            rows.append({'sequence':sequence,'parent':parent,'event':parsed,'entry_digest':entry})
        seq=len(rows); parent=rows[-1]['entry_digest'] if rows else None
        new={'sequence':seq,'parent':parent,'event':event,
             'entry_digest':sha({'sequence':seq,'parent':parent,'event':event})}
        candidate={'schema':SCHEMA,'rows':rows+[new],
                   'anchor':{'count':seq+1,'head':new['entry_digest']}}
        replay_ledger(candidate,trust,baseline)
        conn.execute('INSERT INTO journal VALUES (?,?,?,?)',
                     (seq,parent,canonical(event).decode(),new['entry_digest']))
        return candidate['anchor']


def checkpoint_body(ledger: Mapping[str,Any], trust: Mapping[str,Any],
                    baseline: Mapping[str,Any]) -> dict[str,Any]:
    state=replay_ledger(ledger,trust,baseline)
    return {'schema':CHECKPOINT_SCHEMA,'session':trust['session'],
            'governance_anchor':state['governance_anchor'],'base_anchor':state['base_anchor'],
            'certificate_digest':state['certificate_digest'],
            'evidence_digest':state['evidence_digest'],'scope':state['claim_scope']}


def sign_checkpoint(role: str, body: Mapping[str,Any], key: str) -> dict[str,Any]:
    if role not in ROOTS:raise ContinuityError('unknown witness')
    record={'schema':CHECKPOINT_SCHEMA,'role':role,'body':dict(body),
            'signature':_sign(key,body)}
    return {**record,'digest':sha(record)}


def verify_checkpoint(item: Any, role: str, trust: Mapping[str,Any]) -> dict[str,Any]:
    if not isinstance(item,dict) or set(item)!=CHECKPOINT_FIELDS or \
       item['schema']!=CHECKPOINT_SCHEMA or item['role']!=role or \
       item['digest']!=sha({k:v for k,v in item.items() if k!='digest'}):
        raise ContinuityError('witness checkpoint envelope invalid')
    body=item['body']
    if not isinstance(body,dict) or body.get('schema')!=CHECKPOINT_SCHEMA or \
       body.get('session')!=trust['session']:
        raise ContinuityError('witness checkpoint scope invalid')
    _verify(trust['public'][role],body,item['signature'])
    return body


def initialize_replica(path: str|Path) -> None:
    with _database(path) as conn:
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('CREATE TABLE heads(sequence INTEGER PRIMARY KEY, receipt TEXT NOT NULL)')
        for operation in ('UPDATE','DELETE'):
            conn.execute(f"CREATE TRIGGER no_{operation.lower()}_heads BEFORE {operation} ON heads "
                         "BEGIN SELECT RAISE(ABORT,'append-only'); END")


def append_replica(path: str|Path, receipt: Mapping[str,Any],role: str,trust: Mapping[str,Any]) -> None:
    body=verify_checkpoint(receipt,role,trust)
    seq=body['governance_anchor']['count']
    if type(seq) is not int or seq<0:raise ContinuityError('checkpoint count invalid')
    with _database(path,immediate=True) as conn:
        last=conn.execute('SELECT sequence,receipt FROM heads ORDER BY sequence DESC LIMIT 1').fetchone()
        if (last is None and seq!=0) or (last is not None and seq!=last[0]+1):
            raise ContinuityError('external witness checkpoint sequence not consecutive')
        if last is not None:
            previous=json.loads(last[1])['body']
            if body['base_anchor']!=previous['base_anchor'] or \
               body['certificate_digest']!=previous['certificate_digest'] or \
               body['evidence_digest']!=previous['evidence_digest'] or body['scope']!=previous['scope']:
                raise ContinuityError('witness checkpoint history switched scope')
        conn.execute('INSERT INTO heads VALUES (?,?)',(seq,canonical(receipt).decode()))


def export_replica(path: str|Path) -> list[dict[str,Any]]:
    with _database(path) as conn:
        rows=conn.execute('SELECT sequence,receipt FROM heads ORDER BY sequence').fetchall()
    items=[]
    for idx,(sequence,raw) in enumerate(rows):
        if sequence!=idx:raise ContinuityError('external witness SQLite history gap')
        item=json.loads(raw)
        if raw!=canonical(item).decode():raise ContinuityError('noncanonical witness SQLite receipt')
        items.append(item)
    return items


def latest_replica(path: str|Path) -> dict[str,Any]:
    with _database(path) as conn:
        row=conn.execute('SELECT receipt FROM heads ORDER BY sequence DESC LIMIT 1').fetchone()
    if row is None:raise ContinuityError('external witness checkpoint missing')
    return json.loads(row[0])


def verify_recovery(ledger: Mapping[str,Any], baseline: Mapping[str,Any],
                    trust: Mapping[str,Any], checkpoints: Mapping[str,Any]) -> dict[str,Any]:
    """Verifier needs no current or historical issuer private keys."""
    if not isinstance(checkpoints,dict) or set(checkpoints)!=set(ROOTS):
        raise ContinuityError('two separately enrolled external witnesses required')
    state=replay_ledger(ledger,trust,baseline)
    expected=checkpoint_body(ledger,trust,baseline)
    for role in ROOTS:
        body=verify_checkpoint(checkpoints[role],role,trust)
        if body!=expected:raise ContinuityError('external checkpoint detects rollback or fork')
    return {**state,'recovery_status':'independent_evidence_reconstructed',
            'checkpoint_witnesses':list(ROOTS),'issuer_host_online':False,
            'root_collusion_excluded':False,'global_rollback_precluded':False}


def fixture(*, deterministic: bool=True, revoke: bool=True) -> dict[str,Any]:
    enrollment_data=enrollment(deterministic=deterministic)
    trust=enrollment_data['trust']; private=enrollment_data['private']; baseline=issue_baseline()
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        journal=Path(directory)/'governance.sqlite3'
        replica={r:Path(directory)/(r+'.sqlite3') for r in ROOTS}
        initialize_journal(journal)
        for path in replica.values():initialize_replica(path)
        def record_checkpoint():
            body=checkpoint_body(export_journal(journal),trust,baseline)
            for role,path in replica.items():
                append_replica(path,sign_checkpoint(role,body,private[role]),role,trust)
        record_checkpoint()
        initial=export_journal(journal)
        status=replay_ledger(initial,trust,baseline)
        body=_event_body('rotate',trust,_base_context(baseline),
            {'count':0,'head':None,'current_public':trust['public']['R0']},
            new_public=enrollment_data['replacement_public'])
        event=sign_governance(body,{'R':private['R0'],'W1':private['W1'],'W2':private['W2']})
        append_journal(journal,event,trust,baseline);record_checkpoint()
        rotated=export_journal(journal)
        if revoke:
            body=_event_body('revoke',trust,_base_context(baseline),
                {'count':1,'head':rotated['anchor']['head'],'current_public':enrollment_data['replacement_public']},
                reason='instrument_replaced')
            event=sign_governance(body,{'R':private['R1'],'W1':private['W1'],'W2':private['W2']})
            append_journal(journal,event,trust,baseline);record_checkpoint()
        final=export_journal(journal)
        checkpoints={role:latest_replica(path) for role,path in replica.items()}
        recovered=verify_recovery(final,baseline,trust,checkpoints)
    return {'baseline':baseline,'trust':trust,'initial':initial,'rotated':rotated,
            'final':final,'checkpoints':checkpoints,'recovered':recovered,
            'before':status['status']}


def demo() -> dict[str,Any]:
    sample=fixture()
    result=sample['recovered']
    return {'experiment':'RE-015','initial':sample['before'],
            'after_rotation':replay_ledger(sample['rotated'],sample['trust'],sample['baseline'])['status'],
            'after_revocation':result['status'],
            'history_length':result['governance_anchor']['count'],
            'witnesses':result['checkpoint_witnesses'],
            'reconstructed_without_original_issuer_process':not result['issuer_process_required_for_recovery'],
            'legacy_re014_hmac_key_still_required':result['legacy_re014_hmac_verification_key_required'],
            'compromised_old_key_can_revoke':False,
            'independent_external_witnesses_are_fixture_roles':True,
            'physical_authority_attested':False}


if __name__=='__main__':
    print(json.dumps(demo(),sort_keys=True,indent=2))