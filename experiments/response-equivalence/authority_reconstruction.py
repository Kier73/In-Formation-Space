"""RE-014: durable scope-bound authority transcript for RE-013 renewals.

A role-HMAC proves an enrolled *assertion* under CI fixture keys, not the truth
of IID, source fidelity, physical sensing, or hardware independence. The
independent replayer reconstructs both RE-013 evidence and append-only policy
history, never trusting a mutable 'active' field or the issuer's summary.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import tempfile
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Mapping

from active_recalibration import (evaluate, old_fixture, observer_report,
                                  registration as re013_registration, signed_plan,
                                  verify_prior, verify_revision)
from detection_calibration import canonical, sha

SCHEMA = 'in-formation.response-re014-authority/0.1'
POLICY = 're014-conditional-assumption-admission/0.1'
AUTHORITIES = ('M', 'P', 'R')
APPROVALS = {'M': 'iid_stationarity_representativeness_asserted',
             'P': 'source_reference_and_instrument_context_asserted'}
REVOKE_REASONS = ('population_shift', 'instrument_replaced',
                  'source_challenge_invalidated', 'new_conflicting_evidence')
RECEIPT_FIELDS = frozenset({'schema', 'policy', 'challenge', 'role', 'key_id',
                            'kind', 'evidence_digest', 'scope', 'body', 'mac', 'digest'})
ROW_FIELDS = frozenset({'ordinal', 'previous', 'receipt', 'chain_digest'})


class AuthorityError(ValueError):
    """A policy event, signed claim or durable audit trail is not admitted."""


def registration(*, deterministic: bool = False) -> dict[str, Any]:
    reg = re013_registration(deterministic=deterministic)
    for i, role in enumerate(AUTHORITIES):
        key = ((f'{i + 8:02x}') * 32 if deterministic else secrets.token_hex(32))
        reg['keys'][role] = key
        reg['key_ids'][role] = hashlib.sha256(bytes.fromhex(key)).hexdigest()
    return reg


def _key(reg: Mapping[str, Any], role: str) -> bytes:
    if role not in (*AUTHORITIES, 'V'):
        raise AuthorityError('role cannot participate in authority policy')
    try:
        token = reg['keys'][role]
        if not isinstance(token, str) or len(token) != 64:
            raise ValueError('invalid key encoding')
        key = bytes.fromhex(token)
        if hashlib.sha256(key).hexdigest() != reg['key_ids'][role]:
            raise ValueError('key identifier mismatch')
        return key
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise AuthorityError('authority enrollment key invalid') from exc


def evidence(reg: Mapping[str, Any], *, protocol: str = 'passive') -> dict[str, Any]:
    prior = old_fixture(reg)
    plan = signed_plan(reg, prior['old_certificate']['digest'], sha(prior['suspension']), protocol=protocol)
    return {'prior': prior, 'plan': plan,
            'A': observer_report(reg, plan, 'A'),
            'B': observer_report(reg, plan, 'B')}


def evidence_id(doc: Mapping[str, Any]) -> str:
    return sha(doc)


def claim_scope(doc: Mapping[str, Any]) -> str:
    try:
        return doc['plan']['body']['proposal']['claim_scope']
    except (KeyError, TypeError) as exc:
        raise AuthorityError('claim scope missing') from exc


def sign_event(reg: Mapping[str, Any], role: str, kind: str,
               doc: Mapping[str, Any], *, reason: str | None = None) -> dict[str, Any]:
    """Make a scoped role assertion. Signing does not prove the assertion true."""
    if kind == 'endorse' and role in APPROVALS and reason is None:
        body = {'assumption_claim': APPROVALS[role]}
    elif kind == 'issue' and role == 'V' and reason is None:
        # An issuer can produce a signature, but only the later replay can
        # establish that it was eligible to issue at this position in history.
        body = {'certificate_digest': _expected_certificate(reg, doc)['digest']}
    elif kind == 'revoke' and role == 'R' and reason in REVOKE_REASONS:
        body = {'certificate_digest': _expected_certificate(reg, doc)['digest'],
                'reason': reason}
    else:
        raise AuthorityError('role, decision or reason unauthorized')
    unsigned = {'schema': SCHEMA, 'policy': POLICY, 'challenge': reg['challenge'],
                'role': role, 'key_id': reg['key_ids'][role], 'kind': kind,
                'evidence_digest': evidence_id(doc), 'scope': claim_scope(doc),
                'body': body}
    signed = {**unsigned, 'mac': hmac.new(_key(reg, role), canonical(unsigned),
                                           hashlib.sha256).hexdigest()}
    return {**signed, 'digest': sha(signed)}


def _verify_event(rec: Any, reg: Mapping[str, Any], doc: Mapping[str, Any]) -> None:
    if not isinstance(rec, dict) or set(rec) != RECEIPT_FIELDS:
        raise AuthorityError('authority receipt fields invalid')
    role = rec['role']
    if not isinstance(role, str) or role not in (*AUTHORITIES, 'V') or rec['schema'] != SCHEMA or \
       rec['policy'] != POLICY or rec['challenge'] != reg['challenge'] or \
       rec['key_id'] != reg['key_ids'][role] or \
       rec['evidence_digest'] != evidence_id(doc) or rec['scope'] != claim_scope(doc):
        raise AuthorityError('authority receipt identity or evidence scope mismatch')
    payload = {k: v for k, v in rec.items() if k not in ('mac', 'digest')}
    expected = hmac.new(_key(reg, role), canonical(payload), hashlib.sha256).hexdigest()
    if not isinstance(rec['mac'], str) or not hmac.compare_digest(expected, rec['mac']):
        raise AuthorityError('authority role HMAC invalid')
    if rec['digest'] != sha({**payload, 'mac': rec['mac']}):
        raise AuthorityError('authority receipt digest invalid')
    kind, body = rec['kind'], rec['body']
    if kind == 'endorse' and role in APPROVALS:
        valid = body == {'assumption_claim': APPROVALS[role]}
    elif kind == 'issue' and role == 'V':
        valid = body == {'certificate_digest': _expected_certificate(reg, doc)['digest']}
    elif kind == 'revoke' and role == 'R':
        valid = isinstance(body, dict) and set(body) == {'certificate_digest', 'reason'} and \
            body['reason'] in REVOKE_REASONS and \
            body['certificate_digest'] == _expected_certificate(reg, doc)['digest']
    else:
        valid = False
    if not valid:
        raise AuthorityError('authority policy event forbidden or malformed')


def _expected_certificate(reg: Mapping[str, Any], doc: Mapping[str, Any]) -> dict[str, Any]:
    issued = evaluate(reg, doc['prior'], doc['plan'], doc['A'], doc['B'],
                      assumptions_accepted=True)
    if issued['status'] != 'conditional_revision_issued':
        raise AuthorityError('RE-013 evidence cannot issue conditional revision')
    verify_revision(reg, doc['prior'], doc['plan'], doc['A'], doc['B'], issued,
                    assumptions_accepted=True,
                    expected_protocol=doc['plan']['body']['proposal']['protocol'])
    return issued['new_certificate']


@contextmanager
def _db(filename: str | Path, *, immediate: bool = False):
    # sqlite3.Connection context manager commits/rolls back but does not close.
    conn = sqlite3.connect(str(filename), isolation_level='IMMEDIATE' if immediate else 'DEFERRED')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def create_store(filename: str | Path) -> None:
    """Durable SQLite journal. Triggers deter ordinary UPDATE/DELETE, not DB owners."""
    with _db(filename) as conn:
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('CREATE TABLE decisions(ordinal INTEGER PRIMARY KEY, previous TEXT, '
                     'receipt TEXT NOT NULL, chain_digest TEXT NOT NULL)')
        conn.execute("CREATE TRIGGER immutable_decisions_update BEFORE UPDATE ON decisions "
                     "BEGIN SELECT RAISE(ABORT, 'append-only'); END")
        conn.execute("CREATE TRIGGER immutable_decisions_delete BEFORE DELETE ON decisions "
                     "BEGIN SELECT RAISE(ABORT, 'append-only'); END")


def append(filename: str | Path, receipt: dict[str, Any],
           reg: Mapping[str, Any], doc: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the complete proposed journal in one SQLite transaction before commit."""
    _verify_event(receipt, reg, doc)
    with _db(filename, immediate=True) as conn:
        stored = conn.execute('SELECT ordinal, previous, receipt, chain_digest '
                              'FROM decisions ORDER BY ordinal').fetchall()
        entries = []
        for ordinal, prev, raw, chain in stored:
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError) as exc:
                raise AuthorityError('stored receipt is not JSON') from exc
            if raw != canonical(parsed).decode('utf-8'):
                raise AuthorityError('noncanonical stored receipt')
            entries.append({'ordinal': ordinal, 'previous': prev,
                            'receipt': parsed, 'chain_digest': chain})
        n = len(entries)
        previous = entries[-1]['chain_digest'] if entries else None
        next_hash = sha({'ordinal': n, 'previous': previous, 'receipt': receipt})
        new_entry = {'ordinal': n, 'previous': previous, 'receipt': receipt,
                     'chain_digest': next_hash}
        candidate = {'schema': SCHEMA, 'policy': POLICY,
                     'entries': entries + [new_entry],
                     'anchor': {'count': n+1, 'head': next_hash}}
        replay(candidate, reg, doc)  # Enforce causal authorization order, fail closed.
        conn.execute('INSERT INTO decisions VALUES(?,?,?,?)',
                     (n, previous, canonical(receipt).decode('utf-8'), next_hash))
        return candidate['anchor']


def export(filename: str | Path) -> dict[str, Any]:
    with _db(filename) as conn:
        data = conn.execute('SELECT ordinal, previous, receipt, chain_digest '
                            'FROM decisions ORDER BY ordinal').fetchall()
    entries = []
    for seq, previous, raw, chain in data:
        try:
            receipt = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise AuthorityError('stored receipt is not JSON') from exc
        if raw != canonical(receipt).decode('utf-8'):
            raise AuthorityError('noncanonical stored receipt')
        entries.append({'ordinal': seq, 'previous': previous,
                        'receipt': receipt, 'chain_digest': chain})
    return {'schema': SCHEMA, 'policy': POLICY, 'entries': entries,
            'anchor': {'count': len(entries),
                       'head': entries[-1]['chain_digest'] if entries else None}}


def replay(transcript: Mapping[str, Any], reg: Mapping[str, Any],
           doc: Mapping[str, Any], *, independently_anchored: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read-only replay: never trusts stored status, approval counts or issuer summary."""
    if not isinstance(transcript, dict) or set(transcript) != {'schema', 'policy', 'entries', 'anchor'} or \
        transcript['schema'] != SCHEMA or transcript['policy'] != POLICY or \
        not isinstance(transcript['entries'], list):
        raise AuthorityError('authority transcript envelope invalid')
    evidence_result = evaluate(reg, doc['prior'], doc['plan'], doc['A'], doc['B'])
    if evidence_result['status'] != 'renewal_not_admitted':
        raise AuthorityError('RE-013 default must refuse unsupported assumptions')
    if evidence_result['reasons'] != ['statistical_and_physical_assumptions_unestablished']:
        raise AuthorityError('renewal evidence is not sufficient for conditional admission')
    verify_prior(reg, doc['prior'])
    approvals: set[str] = set()
    issued = revoked = False
    previous = None
    entries = transcript['entries']
    for index, item in enumerate(entries):
        if not isinstance(item, dict) or set(item) != ROW_FIELDS or \
            type(item['ordinal']) is not int or item['ordinal'] != index or \
            item['previous'] != previous or \
            item['chain_digest'] != sha({'ordinal': index, 'previous': previous,
                                         'receipt': item['receipt']}):
            raise AuthorityError('authority chain continuity or sequence invalid')
        rec = item['receipt']
        _verify_event(rec, reg, doc)
        kind, role = rec['kind'], rec['role']
        if kind == 'endorse':
            if role in approvals or issued or revoked:
                raise AuthorityError('replayed, late or duplicated policy endorsement')
            approvals.add(role)
        elif kind == 'issue':
            if issued or revoked or approvals != set(APPROVALS):
                raise AuthorityError('conditional issuance lacks prerequisite independent claims')
            issued = True
        elif kind == 'revoke':
            if not issued or revoked:
                raise AuthorityError('revocation needs one active issued revision')
            revoked = True
        else:
            raise AuthorityError('undeclared authority decision')
        previous = item['chain_digest']
    anchor = {'count': len(entries), 'head': previous}
    if transcript['anchor'] != anchor:
        raise AuthorityError('self-declared journal anchor invalid')
    if independently_anchored is not None and independently_anchored != anchor:
        raise AuthorityError('independent journal anchor detects rollback or fork')
    cert = _expected_certificate(reg, doc) if issued else None
    return {'schema': SCHEMA, 'policy': POLICY, 'status': (
                'revoked' if revoked else 'conditionally_admitted' if issued else 'pending_authority'),
            'evidence_digest': evidence_id(doc), 'scope': claim_scope(doc),
            'approvals': sorted(approvals),
            'certificate_digest': cert['digest'] if cert else None,
            'journal_anchor': anchor,
            'history': [e['receipt']['kind'] + ':' + e['receipt']['role'] for e in entries],
            'physical_source_truth_established': False,
            'physical_sensor_identity_established': False,
            'iid_assumption_proved': False,
            'adversarial_guarantee': None,
            'external_attestation_present': False}


def demo() -> dict[str, Any]:
    reg = registration(deterministic=True)
    doc = evidence(reg)
    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / 're014.sqlite3'
        create_store(db)
        before = replay(export(db), reg, doc)
        for role, kind in (('M', 'endorse'), ('P', 'endorse'), ('V', 'issue')):
            append(db, sign_event(reg, role, kind, doc), reg, doc)
        active_transcript = export(db)
        active = replay(active_transcript, reg, doc,
                        independently_anchored=active_transcript['anchor'])
        append(db, sign_event(reg, 'R', 'revoke', doc,
                              reason='instrument_replaced'), reg, doc)
        revoked = replay(export(db), reg, doc)
        return {'experiment': 'RE-014',
                'before': before['status'], 'after_approvals': active['status'],
                'after_revocation': revoked['status'], 'scope': active['scope'],
                'approval_roles': active['approvals'],
                'history': revoked['history'],
                'certificate_digest': active['certificate_digest'],
                'fresh_authority_approval_proves_physical_truth': False,
                'rollback_requires_external_anchor': True}


if __name__ == '__main__':
    print(json.dumps(demo(), indent=2, sort_keys=True))
