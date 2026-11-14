"""RE-016 public-key custody of a legacy HMAC-verified authority history.

The migration ceremony replays RE-014/015 with legacy secrets ONE TIME.
Subsequent public verification checks Ed25519 assertions about that replay,
legacy public-byte commitments, and post-migration signatures. It does NOT
recheck RE-014 HMACs or establish the truth of scientific assumptions.
"""
from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from contextlib import closing
from typing import Any, Mapping

from credential_continuity import (
    SCHEMA as GOVERNANCE_SCHEMA, CHECKPOINT_SCHEMA, BODY_FIELDS, ROW_FIELDS,
    ROOTS, _verify, _sign, _base_context, _event_body, verify_recovery,
    verify_checkpoint, fixture as re015_fixture, enrollment as credential_enrollment,
    issue_baseline, initialize_journal, export_journal, append_journal,
    sign_governance, empty_ledger, sign_checkpoint,
)
from detection_calibration import sha, canonical

SCHEMA = 'in-formation.response-re016-public-migration/0.1'
FUTURE_SCHEMA = 'in-formation.response-re016-asymmetric-receipt/0.1'
POLICY = 'fixed-R1-W1-W2-attestation-without-HMAC-replay/0.1'
SIGNERS = ('R1', 'W1', 'W2')
FUTURE_KINDS = ('custody_confirmed', 'legacy_keys_retired', 'audit_warning')
MIGRATION_BODY = frozenset({'schema','policy','session','trust_digest','public_history_digest',
    'original_archive_digest','legacy_validation','base','governance_anchor','current_public',
    'governance_status','checkpoint_digests'})
FUTURE_BODY = frozenset({'schema','session','kind','sequence','parent','migration_digest',
    'certificate_digest','governance_anchor','claim_scope','current_key_id','note'})


class MigrationError(ValueError):
    """Invalid public attestation, migration scope, durable record, or checkpoint."""


def public_history(baseline: Mapping[str,Any]) -> dict[str,Any]:
    """Redact ONLY secret key bytes; retain all original signed artifacts intact."""
    if not isinstance(baseline,dict) or set(baseline) != {'registration','evidence','issued'}:
        raise MigrationError('legacy archive format invalid')
    registration=baseline['registration']
    if not isinstance(registration,dict) or 'keys' not in registration:
        raise MigrationError('legacy keys missing for migration preparation')
    published=copy.deepcopy(baseline)
    del published['registration']['keys']
    return published


def _trusted_public(trust: Mapping[str,Any]) -> None:
    if not isinstance(trust,dict) or trust.get('schema')!=GOVERNANCE_SCHEMA or \
        trust.get('policy')!='R-key plus both root witnesses required' or \
        not isinstance(trust.get('session'),str) or not trust['session'] or \
        not isinstance(trust.get('public'),dict) or \
        set(trust['public']) != {'R0',*ROOTS}:
        raise MigrationError('genesis must be independently pinned and complete')
    for key in trust['public'].values():
        if not isinstance(key,str) or len(key)!=64:
            raise MigrationError('trusted Ed25519 key encoding invalid')
        try:bytes.fromhex(key)
        except ValueError as exc:raise MigrationError('trusted public key malformed') from exc


def _public_replay(ledger: Mapping[str,Any], trust: Mapping[str,Any], base: Mapping[str,Any]) -> dict[str,Any]:
    """Strict RE-015 governance replayer with NO legacy keys or HMAC checks."""
    _trusted_public(trust)
    if not isinstance(base,dict) or set(base) != {'evidence_digest','certificate_digest',
            'claim_scope','base_anchor'} or not isinstance(ledger,dict) or \
       set(ledger) != {'schema','rows','anchor'} or ledger['schema']!=GOVERNANCE_SCHEMA or \
       not isinstance(ledger['rows'],list):
        raise MigrationError('public replay basis or ledger invalid')
    current=trust['public']['R0']
    prev=None;rotated=False;revoked=False
    for seq,row in enumerate(ledger['rows']):
        if not isinstance(row,dict) or set(row)!=ROW_FIELDS or \
            type(row['sequence']) is not int or row['sequence']!=seq or \
            row['parent']!=prev or row['entry_digest']!=sha({'sequence':seq,'parent':prev,'event':row['event']}):
            raise MigrationError('public governance journal chain malformed')
        ev=row['event']
        if not isinstance(ev,dict) or set(ev)!={'schema','body','signatures','digest'} or \
            ev['schema']!=GOVERNANCE_SCHEMA or \
            ev['digest']!=sha({k:v for k,v in ev.items() if k!='digest'}) or \
            not isinstance(ev['signatures'],dict) or set(ev['signatures']) != {'R',*ROOTS}:
            raise MigrationError('public governance event malformed')
        body=ev['body']
        expected={'session':trust['session'],**base,'sequence':seq,'parent':prev,
                  'current_key_id':sha({'public':current})}
        if not isinstance(body,dict) or set(body)!=BODY_FIELDS or \
            any(body.get(k)!=v for k,v in expected.items()):
            raise MigrationError('governance scope, parent or signer epoch mismatch')
        _verify(current,body,ev['signatures']['R'])
        for r in ROOTS:_verify(trust['public'][r],body,ev['signatures'][r])
        if body['kind']=='rotate' and not rotated and not revoked:
            newer=body['new_public_key']
            if not isinstance(newer,str) or len(newer)!=64 or newer==current or body['reason'] is not None:
                raise MigrationError('incorrect key transition')
            try:bytes.fromhex(newer)
            except ValueError as exc:raise MigrationError('new public key malformed') from exc
            current=newer;rotated=True
        elif body['kind']=='revoke' and rotated and not revoked and \
            body['new_public_key'] is None and body['reason'] in \
            ('instrument_replaced','source_challenge_invalidated','new_conflicting_evidence'):
            revoked=True
        else:
            raise MigrationError('governance transition is unauthorized')
        prev=row['entry_digest']
    anchor={'count':len(ledger['rows']),'head':prev}
    if ledger['anchor']!=anchor or not rotated or not revoked:
        raise MigrationError('migration only handles fully revoked, rotated history')
    return {'governance_anchor':anchor,'current_public':current,'status':'revoked'}


def _expected_checkpoints(ledger:Mapping[str,Any],trust:Mapping[str,Any],
                          base:Mapping[str,Any],checkpoints:Mapping[str,Any]) -> None:
    if not isinstance(checkpoints,dict) or set(checkpoints)!=set(ROOTS):
        raise MigrationError('both external checkpoint witnesses required')
    expected={'schema':CHECKPOINT_SCHEMA,'session':trust['session'],
              'governance_anchor':ledger['anchor'],'base_anchor':base['base_anchor'],
              'certificate_digest':base['certificate_digest'],
              'evidence_digest':base['evidence_digest'],'scope':base['claim_scope']}
    for role in ROOTS:
        if verify_checkpoint(checkpoints[role],role,trust)!=expected:
            raise MigrationError('mismatched signed witness checkpoint')


def prepare_migration(baseline: Mapping[str,Any], ledger:Mapping[str,Any],
                      trust:Mapping[str,Any],checkpoints:Mapping[str,Any]) -> tuple[dict,dict]:
    """SECRET-HOLDING CEREMONY ONLY: actually replay original HMAC evidence."""
    recovered=verify_recovery(ledger,baseline,trust,checkpoints)
    if recovered['status']!='revoked' or recovered['governance_anchor']['count']!=2:
        raise MigrationError('legacy replay is not a revoked two-decision transcript')
    base=_base_context(baseline)
    original=public_history(baseline)
    public_replay=_public_replay(ledger,trust,base)
    if public_replay['governance_anchor']!=recovered['governance_anchor'] or \
       public_replay['current_public']!=ledger['rows'][0]['event']['body']['new_public_key']:
        raise MigrationError('public replay and historical replay disagree')
    body={'schema':SCHEMA,'policy':POLICY,'session':trust['session'],'trust_digest':sha(trust),
          'public_history_digest':sha(original),'original_archive_digest':sha(baseline),
          'legacy_validation':'legacy_hmac_replayed_during_ceremony',
          'base':base,'governance_anchor':recovered['governance_anchor'],
          'current_public':public_replay['current_public'],
          'governance_status':'revoked',
          'checkpoint_digests':{r:checkpoints[r]['digest'] for r in ROOTS}}
    return body,original


def attest_migration(body:Mapping[str,Any],private:Mapping[str,str]) -> dict[str,Any]:
    if not isinstance(body,dict) or set(body)!=MIGRATION_BODY or set(private)!=set(SIGNERS):
        raise MigrationError('migration attestations incomplete')
    payload={'schema':SCHEMA,'body':dict(body),
             'signatures':{r:_sign(private[r],body) for r in SIGNERS}}
    return {**payload,'digest':sha(payload)}


def public_verify(migration:Mapping[str,Any],pub:Mapping[str,Any],
                 ledger:Mapping[str,Any],trust:Mapping[str,Any],
                 checkpoints:Mapping[str,Any], pinned:Mapping[str,Any]) -> dict[str,Any]:
    """NO HMAC SECRETS: validate signatures, bytes and prior-replay attestation.

    The returned historical evidence level is *attested prior verification*,
    NEVER independent old-HMAC verification. A pin is externally supplied.
    """
    _trusted_public(trust)
    if not isinstance(migration,dict) or set(migration)!= {'schema','body','signatures','digest'} or \
       migration['schema']!=SCHEMA or migration['digest']!=sha({k:v for k,v in migration.items() if k!='digest'}) or \
       not isinstance(migration['signatures'],dict) or set(migration['signatures'])!=set(SIGNERS):
        raise MigrationError('migration attestation envelope invalid')
    body=migration['body']
    if not isinstance(body,dict) or set(body)!=MIGRATION_BODY or \
        body['schema']!=SCHEMA or body['policy']!=POLICY or \
        body['session']!=trust['session'] or body['trust_digest']!=sha(trust) or \
        body['legacy_validation']!='legacy_hmac_replayed_during_ceremony' or \
        body['governance_status']!='revoked' or body['public_history_digest']!=sha(pub):
        raise MigrationError('legacy report or public projection commitment mismatch')
    if not isinstance(pub,dict) or set(pub)!={'registration','evidence','issued'} or \
       not isinstance(pub['registration'],dict) or 'keys' in pub['registration'] or \
       not isinstance(pub['registration'].get('key_ids'),dict):
        raise MigrationError('public archive must contain no legacy secrets')
    base=body['base']
    if not isinstance(base,dict) or set(base)!= {'evidence_digest','certificate_digest','claim_scope','base_anchor'} or \
       base['evidence_digest']!=sha(pub['evidence']) or \
       not isinstance(pub.get('issued'),dict) or pub['issued'].get('anchor')!=base['base_anchor']:
        raise MigrationError('published legacy evidence and anchor disagree')
    state=_public_replay(ledger,trust,base)
    if state['governance_anchor']!=body['governance_anchor'] or \
        state['current_public']!=body['current_public'] or state['status']!='revoked':
        raise MigrationError('public governance replay mismatch')
    _expected_checkpoints(ledger,trust,base,checkpoints)
    if body['checkpoint_digests']!={r:checkpoints[r]['digest'] for r in ROOTS}:
        raise MigrationError('externally held checkpoint commitments mismatch')
    # The pin is OUTSIDE the authority+archive and cannot be substituted by them.
    expected_pin={'trust_digest':sha(trust),'migration_digest':migration['digest'],
                  'governance_anchor':ledger['anchor']}
    if pinned!=expected_pin:
        raise MigrationError('externally retained pin detects stale or foreign history')
    for role in SIGNERS:
        key=state['current_public'] if role=='R1' else trust['public'][role]
        _verify(key,body,migration['signatures'][role])
    return {'status':'revoked','historical_validation_mode':'attested_prior_legacy_replay',
            'historical_hmac_reexecuted':False,'legacy_secret_required_for_public_verifier':False,
            'public_projection_authenticated_by_attestation':True,
            'certificate_digest':base['certificate_digest'],'claim_scope':base['claim_scope'],
            'migration_digest':migration['digest'], 'governance_anchor':ledger['anchor'],
            'physical_assumptions_verified':False,'trust_genesis_externally_proved':False,
            'global_rollback_precluded':False}


def pin(trust:Mapping[str,Any],migration:Mapping[str,Any],ledger:Mapping[str,Any])->dict[str,Any]:
    """Only externally distributed pins have anti-rollback value."""
    return {'trust_digest':sha(trust),'migration_digest':migration['digest'],
            'governance_anchor':ledger['anchor']}


def future_body(migration:Mapping[str,Any],prior_rows:list[dict],kind:str,note:str)->dict:
    if kind not in FUTURE_KINDS or not isinstance(note,str) or not 0<len(note)<=120 or \
       not isinstance(prior_rows,list):raise MigrationError('unsupported future decision')
    mb=migration['body']
    return {'schema':FUTURE_SCHEMA,'session':mb['session'],'kind':kind,
            'sequence':len(prior_rows),'parent': prior_rows[-1]['digest'] if prior_rows else migration['digest'],
            'migration_digest':migration['digest'],'certificate_digest':mb['base']['certificate_digest'],
            'governance_anchor':mb['governance_anchor'],'claim_scope':mb['base']['claim_scope'],
            'current_key_id':sha({'public':mb['current_public']}),'note':note}


def sign_future(body:Mapping[str,Any],private:Mapping[str,str])->dict:
    if not isinstance(body,dict) or set(body)!=FUTURE_BODY or set(private)!=set(SIGNERS):
        raise MigrationError('future receipt signers or fields incomplete')
    item={'schema':FUTURE_SCHEMA,'body':dict(body),
          'signatures':{r:_sign(private[r],body) for r in SIGNERS}}
    return {**item,'digest':sha(item)}


def replay_future(rows:Any, migration:Mapping[str,Any],trust:Mapping[str,Any]) -> dict:
    if not isinstance(rows,list):raise MigrationError('future public archive missing')
    retired=False;last=migration['digest']
    for i,entry in enumerate(rows):
        if not isinstance(entry,dict) or set(entry)!= {'schema','body','signatures','digest'} or \
           entry['schema']!=FUTURE_SCHEMA or entry['digest']!=sha({k:v for k,v in entry.items() if k!='digest'}) or \
           not isinstance(entry['signatures'],dict) or set(entry['signatures'])!=set(SIGNERS):
            raise MigrationError('future public receipt malformed')
        body=entry['body'];expected=future_body(migration,rows[:i],body.get('kind'),body.get('note'))
        if body!=expected or body['sequence']!=i or body['parent']!=last:
            raise MigrationError('future chain or scope invalid')
        if body['kind']=='legacy_keys_retired':
            if retired:raise MigrationError('legacy-key retirement cannot repeat')
            retired=True
        for role in SIGNERS:
            public=migration['body']['current_public'] if role=='R1' else trust['public'][role]
            _verify(public,body,entry['signatures'][role])
        last=entry['digest']
    return {'status':'revoked','receipt_count':len(rows),'head':last,
            'retirement_attested':retired,'historical_hmac_reexecuted':False,
            'no_renewal_admitted_by_receipts':True}


def create_future_archive(path:str|Path)->None:
    with closing(sqlite3.connect(str(path))) as db, db:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE future_receipts(seq INTEGER PRIMARY KEY, document TEXT NOT NULL)')
        for op in ('UPDATE','DELETE'):
            db.execute(f'CREATE TRIGGER no_{op.lower()}_future BEFORE {op} ON future_receipts '
                       "BEGIN SELECT RAISE(ABORT,'append-only'); END")


def export_future_archive(path:str|Path)->list[dict]:
    with closing(sqlite3.connect(str(path))) as db, db:
        data=db.execute('SELECT seq,document FROM future_receipts ORDER BY seq').fetchall()
    entries=[]
    for seq,raw in data:
        if type(seq) is not int or seq!=len(entries):raise MigrationError('SQLite public receipt gap')
        try:item=json.loads(raw)
        except (ValueError,TypeError) as exc:raise MigrationError('invalid serialized future receipt') from exc
        if raw!=canonical(item).decode():raise MigrationError('noncanonical persisted public receipt')
        entries.append(item)
    return entries


def append_future_archive(path:str|Path,entry:Mapping[str,Any],migration:Mapping[str,Any],
                          trust:Mapping[str,Any])->dict:
    with closing(sqlite3.connect(str(path),isolation_level='IMMEDIATE')) as db, db:
        raw=db.execute('SELECT seq,document FROM future_receipts ORDER BY seq').fetchall()
        old=[]
        for seq,item in raw:
            if seq!=len(old):raise MigrationError('existing future archive gap')
            parsed=json.loads(item)
            if item!=canonical(parsed).decode():raise MigrationError('noncanonical future archive')
            old.append(parsed)
        proposed=old+[dict(entry)]
        checked=replay_future(proposed,migration,trust)
        db.execute('INSERT INTO future_receipts VALUES (?,?)',(len(old),canonical(entry).decode()))
        return checked


def future_pin(migration:Mapping[str,Any],rows:list[dict],trust:Mapping[str,Any])->dict:
    result=replay_future(rows,migration,trust)
    return {'migration_digest':migration['digest'],'trust_digest':sha(trust),
            'receipt_count':result['receipt_count'],'head':result['head']}


def verify_future_pin(rows:list[dict],migration:Mapping[str,Any],trust:Mapping[str,Any],
                      retained:Mapping[str,Any])->dict:
    """A trusted external latest head is REQUIRED for a rollback claim."""
    report=replay_future(rows,migration,trust)
    if retained!=future_pin(migration,rows,trust):
        raise MigrationError('independently retained future checkpoint detects rollback')
    return report


def hosted_material(*, deterministic:bool=False)->dict:
    """One-time CI genesis with separately scoped signing keys for later jobs.

    Keys distributed in CI artifacts are NOT protected independent identities.
    Neither Ed25519 signatures nor CI process boundaries establish hardware trust.
    """
    import tempfile
    data=credential_enrollment(deterministic=deterministic)
    trust=data['trust'];priv=data['private'];base=issue_baseline()
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'governance.sqlite3'
        initialize_journal(path)
        key=trust['public']['R0']
        rotate=_event_body('rotate',trust,_base_context(base),
            {'count':0,'head':None,'current_public':key},new_public=data['replacement_public'])
        append_journal(path,sign_governance(rotate,{'R':priv['R0'],'W1':priv['W1'],'W2':priv['W2']}),trust,base)
        rotated=export_journal(path)
        revoke=_event_body('revoke',trust,_base_context(base),
            {'count':1,'head':rotated['anchor']['head'],'current_public':data['replacement_public']},
            reason='instrument_replaced')
        append_journal(path,sign_governance(revoke,{'R':priv['R1'],'W1':priv['W1'],'W2':priv['W2']}),trust,base)
        ledger=export_journal(path)
        context={'schema':CHECKPOINT_SCHEMA,'session':trust['session'],
                 'governance_anchor':ledger['anchor'],'base_anchor':_base_context(base)['base_anchor'],
                 'certificate_digest':_base_context(base)['certificate_digest'],
                 'evidence_digest':_base_context(base)['evidence_digest'],
                 'scope':_base_context(base)['claim_scope']}
        checkpoints={r:sign_checkpoint(r,context,priv[r]) for r in ROOTS}
        verify_recovery(ledger,base,trust,checkpoints)
    return {'ceremony':{'baseline':base,'ledger':ledger,'trust':trust,'checkpoints':checkpoints},
            'signer_keys':{r:priv[r] for r in SIGNERS}}


def fixture()->dict:
    old=re015_fixture()
    # The fixture contains no private key bytes after the handoff.
    ceremony,public=prepare_migration(old['baseline'],old['final'],old['trust'],old['checkpoints'])
    enrolled=__import__('credential_continuity').enrollment(deterministic=True)
    private={role:enrolled['private'][role] for role in SIGNERS}
    migration=attest_migration(ceremony,private)
    checkpoint=pin(old['trust'],migration,old['final'])
    return {'public':public,'trust':old['trust'],'ledger':old['final'],
            'checkpoints':old['checkpoints'],'migration':migration,'pin':checkpoint,
            'private':private,'legacy_reference':old['baseline']}


def demo()->dict:
    import tempfile
    sample=fixture()
    initial=public_verify(sample['migration'],sample['public'],sample['ledger'],
                          sample['trust'],sample['checkpoints'],sample['pin'])
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'public.sqlite3';create_future_archive(path)
        retired=sign_future(future_body(sample['migration'],[],'legacy_keys_retired','legacy custody closed'),sample['private'])
        append_future_archive(path,retired,sample['migration'],sample['trust'])
        ack=sign_future(future_body(sample['migration'],[retired],'custody_confirmed','public evidence retained'),sample['private'])
        result=append_future_archive(path,ack,sample['migration'],sample['trust'])
    return {'experiment':'RE-016','historical_status':initial['status'],
            'historical_validation_mode':initial['historical_validation_mode'],
            'old_hmac_replayed_by_public_verifier':initial['historical_hmac_reexecuted'],
            'legacy_secrets_needed_for_public_verifier':initial['legacy_secret_required_for_public_verifier'],
            'future_receipts':result['receipt_count'],'retirement_attested':result['retirement_attested'],
            'physical_assumptions_verified':initial['physical_assumptions_verified']}

if __name__=='__main__':print(json.dumps(demo(),indent=2,sort_keys=True))