"""RE-006: scoped exclusion audit, not an assertion of physical causation.

Independent role-HMAC receipts, instrument positive/negative controls and a
causally bracketed intervention can support a CLOSED-FINITE-FIXTURE conclusion.
They cannot prove that an arbitrary external influence was absent. All states,
measurements and processes are synthetic; enrolled keys are shared CI secrets.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Mapping

SCHEMA = 'in-formation.response-re006/0.1'
SESSION = 're006-scoped-intervention-audit'
ACTORS = ('A', 'M', 'N')
CANDIDATES = ('common_cause_alias', 'common_cause_marker', 'event_causal')
PREDICTIONS = {'event_causal': 1, 'common_cause_marker': 2, 'common_cause_alias': 2}
KIND_ROLE = {'open': 'A', 'monitor': 'M', 'negative_control': 'N', 'close': 'A', 'plant': 'B'}
PAYLOAD_FIELDS = {
    'open': {'command', 'target_event', 'declared_controls'},
    'monitor': {'start_digest', 'status', 'event', 'sentinel', 'sampling_scope'},
    'negative_control': {'start_digest', 'status', 'sham_delta', 'positive_delta'},
    'close': {'start_digest', 'monitor_digest', 'negative_digest', 'status'},
    'plant': {'close_digest', 'readout'},
}
FIELDS = {'schema', 'session', 'challenge', 'role', 'kind', 'payload', 'causal', 'key_id', 'mac', 'digest'}


class AuditError(ValueError):
    """Malformed, altered or falsely authorized evidence."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def sha(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def enroll(*, deterministic: bool = False) -> dict[str, Any]:
    """CI fixture enrollment, NOT physical identity attestation.

    A deterministic enrollment is public test material; never use it to argue
    security. Hosted execution generates fresh, ephemeral role keys.
    """
    keys = {role: ((role.encode().hex() * 64)[:64] if deterministic else secrets.token_hex(32))
            for role in ACTORS}
    return {'challenge': 're006-deterministic-challenge' if deterministic else secrets.token_hex(24),
            'keys': keys,
            'key_ids': {r: hashlib.sha256(bytes.fromhex(keys[r])).hexdigest() for r in ACTORS}}


def _key(enrollment: Mapping[str, Any], role: str) -> bytes:
    if role not in ACTORS:
        raise AuditError('role is not enrolled for signing')
    try:
        value = enrollment['keys'][role]
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError('invalid key length')
        key = bytes.fromhex(value)
        if hashlib.sha256(key).hexdigest() != enrollment['key_ids'][role]:
            raise ValueError('key identity mismatch')
        return key
    except (ValueError, KeyError, TypeError) as error:
        raise AuditError('missing or incorrect enrolled key') from error


def record(kind: str, payload: dict[str, Any], stamp: Mapping[str, Any],
           enrollment: Mapping[str, Any]) -> dict[str, Any]:
    if kind not in KIND_ROLE or set(payload) != PAYLOAD_FIELDS[kind]:
        raise AuditError('invalid record kind or payload')
    role = KIND_ROLE[kind]
    row = {'schema': SCHEMA, 'session': SESSION, 'challenge': enrollment['challenge'],
           'role': role, 'kind': kind, 'payload': payload,
           'causal': dict(stamp), 'key_id': enrollment['key_ids'].get(role),
           'mac': None}
    if role in ACTORS:
        row['mac'] = hmac.new(_key(enrollment, role), canonical(row | {'mac': None}),
                              hashlib.sha256).hexdigest()
    row['digest'] = sha(row)
    return row


def check(row: dict[str, Any], kind: str, enrollment: Mapping[str, Any]) -> None:
    if not isinstance(row, dict) or set(row) != FIELDS or kind not in KIND_ROLE:
        raise AuditError('missing or unexpected receipt fields')
    role = KIND_ROLE[kind]
    if (row['schema'] != SCHEMA or row['session'] != SESSION
            or row['challenge'] != enrollment['challenge'] or row['role'] != role
            or row['kind'] != kind or not isinstance(row['payload'], dict)
            or set(row['payload']) != PAYLOAD_FIELDS[kind]):
        raise AuditError('receipt identity or payload contract mismatch')
    if not isinstance(row['causal'], dict) or not isinstance(row['digest'], str) or sha({k:v for k,v in row.items() if k != 'digest'}) != row['digest']:
        raise AuditError('receipt digest mismatch')
    if role in ACTORS:
        if row['key_id'] != enrollment['key_ids'][role] or not isinstance(row['mac'], str):
            raise AuditError('receipt enrollment mismatch')
        unsigned = {k:v for k,v in row.items() if k != 'digest'}
        unsigned['mac'] = None
        expected = hmac.new(_key(enrollment, role), canonical(unsigned), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(row['mac'], expected):
            raise AuditError('receipt MAC authentication failed')
    elif row['key_id'] is not None or row['mac'] is not None:
        raise AuditError('plant record must not impersonate an enrolled authority')


def open_receipt(enrollment: Mapping[str, Any], stamp: Mapping[str, Any]) -> dict[str, Any]:
    return record('open', {'command': 'apply', 'target_event': 0,
                           'declared_controls': ['environment', 'sentinel', 'sham', 'instrument_positive']},
                  stamp, enrollment)


def monitor_receipt(enrollment: Mapping[str, Any], stamp: Mapping[str, Any], opening: Mapping[str, Any],
                    *, permitted: bool = True, event: int = 0, sentinel: tuple[int,int,int] = (7,7,7),
                    sampling_scope: str = 'three_samples') -> dict[str, Any]:
    # A denial conveys no sampled values; the reported coverage is then null.
    return record('monitor', {'start_digest': opening['digest'],
                              'status': 'observed' if permitted else 'refused',
                              'event': event if permitted else None,
                              'sentinel': list(sentinel) if permitted else None,
                              'sampling_scope': sampling_scope if permitted else None},
                  stamp, enrollment)


def negative_receipt(enrollment: Mapping[str, Any], stamp: Mapping[str, Any], opening: Mapping[str, Any],
                     *, permitted: bool = True, sham_delta: int = 0, positive_delta: int = 1) -> dict[str, Any]:
    return record('negative_control', {'start_digest': opening['digest'],
                'status': 'observed' if permitted else 'refused',
                'sham_delta': sham_delta if permitted else None,
                'positive_delta': positive_delta if permitted else None}, stamp, enrollment)


def close_receipt(enrollment: Mapping[str, Any], stamp: Mapping[str, Any],
                  opening: Mapping[str, Any], monitor: Mapping[str, Any],
                  negative: Mapping[str, Any], *, completed: bool = True) -> dict[str, Any]:
    return record('close', {'start_digest': opening['digest'],
            'monitor_digest': monitor['digest'], 'negative_digest': negative['digest'],
            'status': 'completed' if completed else 'not_completed'}, stamp, enrollment)


def plant_receipt(enrollment: Mapping[str, Any], stamp: Mapping[str, Any],
                  closing: Mapping[str, Any], *, readout: int = 2) -> dict[str, Any]:
    return record('plant', {'close_digest': closing['digest'], 'readout': readout}, stamp, enrollment)


def verify(bundle: Mapping[str, Any], enrollment: Mapping[str, Any],
           *, model_scope: str = 'open_world') -> dict[str, Any]:
    """Authenticate complete receipts; admit a *conditional* exclusion only.

    `declared_closed_world` is a verifier-supplied MODEL ASSUMPTION, not
    something a finite sample or HMAC can establish. This scope is deliberately
    explicit rather than letting producers smuggle a success flag.
    """
    if model_scope not in ('open_world', 'declared_closed_world'):
        raise AuditError('unknown verifier model scope')
    expected = ('open','monitor','negative_control','close','plant')
    if not isinstance(bundle, dict) or set(bundle) != set(expected):
        raise AuditError('incomplete receipt bundle')
    for kind in expected:
        check(bundle[kind], kind, enrollment)
    opening, monitor, negative, closing, plant = (bundle[k] for k in expected)
    p = opening['payload']
    if p != {'command': 'apply', 'target_event': 0,
             'declared_controls': ['environment','sentinel','sham','instrument_positive']}:
        raise AuditError('unexpected intervention schedule or control plan')
    if (monitor['payload']['start_digest'] != opening['digest']
            or negative['payload']['start_digest'] != opening['digest']
            or closing['payload']['start_digest'] != opening['digest']
            or closing['payload']['monitor_digest'] != monitor['digest']
            or closing['payload']['negative_digest'] != negative['digest']
            or plant['payload']['close_digest'] != closing['digest']):
        raise AuditError('receipt chain or intervention window disconnected')
    m, n, c, b = monitor['payload'], negative['payload'], closing['payload'], plant['payload']
    if m['status'] not in ('observed', 'refused') or n['status'] not in ('observed', 'refused') or c['status'] not in ('completed', 'not_completed'):
        raise AuditError('invalid authority status')
    if m['status'] == 'refused' and any(m[k] is not None for k in ('event','sentinel','sampling_scope')):
        raise AuditError('denied monitor cannot report values')
    if n['status'] == 'refused' and (n['sham_delta'] is not None or n['positive_delta'] is not None):
        raise AuditError('denied controls cannot report values')
    for val in (m['event'], n['sham_delta'], n['positive_delta'], b['readout']):
        if val is not None and type(val) is not int:
            raise AuditError('inexact or malformed observation')
    if m['sentinel'] is not None and (not isinstance(m['sentinel'], list) or len(m['sentinel']) != 3 or any(type(x) is not int for x in m['sentinel'])):
        raise AuditError('invalid sentinel series')
    if type(b['readout']) is not int:
        raise AuditError('missing plant readout')
    if m['status'] == 'observed' and (m['event'] is None or m['sentinel'] is None or m['sampling_scope'] not in ('three_samples', 'incomplete')):
        raise AuditError('invalid observed environmental channel')
    if n['status'] == 'observed' and (n['sham_delta'] is None or n['positive_delta'] is None):
        raise AuditError('observed controls missing values')
    samples_pass = (m['status'] == 'observed' and m['sampling_scope'] == 'three_samples'
                    and m['event'] == 0 and m['sentinel'] == [7,7,7])
    controls_pass = (n['status'] == 'observed' and n['sham_delta'] == 0 and n['positive_delta'] == 1)
    receipts_pass = c['status'] == 'completed'
    audit_ok = samples_pass and controls_pass and receipts_pass
    conditional = audit_ok and model_scope == 'declared_closed_world'
    # The passive episodes in RE-005 are nondiscriminating and retain all three.
    # The controlled episode has Y=2; it narrows the set only conditionally.
    survivors = sorted(name for name in CANDIDATES
                       if not conditional or PREDICTIONS[name] == b['readout'])
    if not survivors:
        raise AuditError('no candidate explains the admitted controlled outcome')
    status = ('controls_passed_under_declared_sampling' if audit_ok else
              'not_admitted_missing_or_failed_controls')
    return {'schema': SCHEMA, 'audit_status': status,
            'conditional_exclusion_admitted': conditional,
            'model_scope': model_scope, 'survivors': survivors,
            'monitor_status': m['status'], 'negative_control_status': n['status'],
            'sampling_scope': m['sampling_scope'],
            'unobserved_channels_excluded': False,
            'physical_causation_proved': False,
            'source_identity': 'role-HMAC under shared test-enrollment authority',
            'external_clock_alignment': None,
            'reason': ('conditional finite-model reconstruction; completeness and sensor fidelity are assumptions'
                       if conditional else 'no justified closed-world exclusion from these receipts alone')}


def fixture_stamp(actor: str, step: int = 1) -> dict[str, Any]:
    # Deterministic stand-in for local unit tests only, not E-CPU temporal proof.
    return {'actor_id': actor, 'lamport': step, 'vector': {role: step if role == actor else 0 for role in ('A','B','M','N')}}


def fixture(*, model_scope: str = 'open_world', monitor_kwargs=None, negative_kwargs=None,
            completed: bool = True, readout: int = 2) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    reg = enroll(deterministic=True)
    a = open_receipt(reg, fixture_stamp('A'))
    m = monitor_receipt(reg, fixture_stamp('M'), a, **(monitor_kwargs or {}))
    n = negative_receipt(reg, fixture_stamp('N'), a, **(negative_kwargs or {}))
    z = close_receipt(reg, fixture_stamp('A',2), a, m, n, completed=completed)
    b = plant_receipt(reg, fixture_stamp('B'), z, readout=readout)
    bundle = {'open':a, 'monitor':m, 'negative_control':n, 'close':z, 'plant':b}
    return bundle, reg, verify(bundle, reg, model_scope=model_scope)


def demonstration() -> dict[str, Any]:
    _, _, open_result = fixture()
    _, _, closed_result = fixture(model_scope='declared_closed_world')
    _, _, denied_result = fixture(model_scope='declared_closed_world', monitor_kwargs={'permitted':False})
    _, _, drift_result = fixture(model_scope='declared_closed_world', monitor_kwargs={'sentinel':(7,8,7)})
    return {'experiment':'RE-006','open_world':open_result,'declared_closed_world':closed_result,
            'refused_monitor':denied_result, 'interference_detected':drift_result,
            'scope':'synthetic mathematical fixture; no physical exclusion certificate'}


if __name__ == '__main__':
    print(json.dumps(demonstration(), indent=2, sort_keys=True))

