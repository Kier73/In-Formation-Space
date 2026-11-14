"""RE-011: event detection calibration against a declared, synthetic injection ledger.

The ledger is a test-fixture reference, NOT externally witnessed physical truth.
Role HMACs authenticate CI-enrolled reporters, NOT independent devices.
Statistical upper limits are conditional on IID trials, unbiased known injections,
stationarity, and genuine source truth; deterministic fixtures do not prove them.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import secrets
from typing import Any, Mapping

SCHEMA = 'in-formation.response-re011/0.1'
SESSION = 're011-fault-calibration'
ROLES = ('S', 'A', 'B')
POSITIVE = 60
SHAM = 20
TOTAL = POSITIVE + SHAM
STATUSES = frozenset({'detected', 'not_detected', 'unavailable', 'refused'})
RECORD_FIELDS = frozenset({'schema', 'session', 'challenge', 'role', 'key_id',
                           'kind', 'trial', 'injected', 'status', 'event_id', 'parent'})
SEAL_FIELDS = frozenset({'schema', 'session', 'challenge', 'role', 'key_id',
                         'kind', 'count', 'head', 'positive', 'sham'})

class CalibrationError(ValueError):
    """Invalid, missing or unauthenticated calibration evidence."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def enrollment(*, deterministic: bool = False) -> dict[str, Any]:
    keys = ({r: (format(i + 1, '02x') * 32) for i, r in enumerate(ROLES)}
            if deterministic else {r: secrets.token_hex(32) for r in ROLES})
    return {'challenge': 're011-fixture-challenge' if deterministic else secrets.token_hex(24),
            'keys': keys,
            'key_ids': {r: hashlib.sha256(bytes.fromhex(keys[r])).hexdigest() for r in ROLES}}


def _key(reg: Mapping[str, Any], role: str) -> bytes:
    if role not in ROLES:
        raise CalibrationError('unrecognized role')
    try:
        key_hex = reg['keys'][role]
        key = bytes.fromhex(key_hex)
        if len(key) != 32 or reg['key_ids'][role] != hashlib.sha256(key).hexdigest():
            raise ValueError('enrollment mismatch')
        return key
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CalibrationError('role enrollment invalid') from exc


def _base(reg: Mapping[str, Any], role: str, kind: str) -> dict[str, Any]:
    return {'schema': SCHEMA, 'session': SESSION, 'challenge': reg['challenge'],
            'role': role, 'key_id': reg['key_ids'][role], 'kind': kind}


def _sign(payload: dict[str, Any], key: bytes) -> dict[str, Any]:
    body = {**payload, 'mac': hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()}
    return {**body, 'digest': sha(body)}


def _verify(record: Any, reg: Mapping[str, Any], role: str, kind: str,
            fields: frozenset[str]) -> None:
    if not isinstance(record, dict) or set(record) != fields | {'mac', 'digest'}:
        raise CalibrationError('signed fields malformed')
    if any(record.get(k) != value for k, value in _base(reg, role, kind).items()):
        raise CalibrationError('role/session/challenge mismatch')
    body = {k: v for k, v in record.items() if k not in ('mac', 'digest')}
    expected = hmac.new(_key(reg, role), canonical(body), hashlib.sha256).hexdigest()
    if not isinstance(record['mac'], str) or not hmac.compare_digest(record['mac'], expected):
        raise CalibrationError('role HMAC invalid')
    if record['digest'] != sha({**body, 'mac': record['mac']}):
        raise CalibrationError('signed digest invalid')


def event_id(reg: Mapping[str, Any], trial: int) -> str:
    return sha({'challenge': reg['challenge'], 'trial': trial, 'event': 'injection'})


def seal(reg: Mapping[str, Any], role: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return _sign({**_base(reg, role, 'seal'), 'count': TOTAL,
                  'positive': POSITIVE, 'sham': SHAM,
                  'head': records[-1]['digest']}, _key(reg, role))


def produce_source(reg: Mapping[str, Any]) -> dict[str, Any]:
    """Synthetic source explicitly declares positives and sham challenges."""
    records = []
    parent = None
    for trial in range(TOTAL):
        injected = trial < POSITIVE
        record = _sign({**_base(reg, 'S', 'trial'), 'trial': trial,
                        'injected': injected, 'status': 'commanded',
                        'event_id': event_id(reg, trial) if injected else None,
                        'parent': parent}, _key(reg, 'S'))
        records.append(record)
        parent = record['digest']
    return {'records': records, 'seal': seal(reg, 'S', records)}


def fault_indices(role: str, regime: str) -> frozenset[int]:
    """Exact deterministic test patterns, not sampled population probabilities."""
    if role not in ('A', 'B') or regime not in (
            'complementary_dropouts', 'common_mode_dropouts', 'colluding_silence'):
        raise CalibrationError('undeclared role or fault regime')
    if regime == 'colluding_silence':
        return frozenset(range(POSITIVE))
    if regime == 'common_mode_dropouts' or role == 'A':
        return frozenset(range(0, POSITIVE, 5))
    return frozenset(range(1, POSITIVE, 5))


def produce_observer(source: Mapping[str, Any], reg: Mapping[str, Any],
                     role: str, regime: str = 'complementary_dropouts',
                     *, unavailable: frozenset[int] = frozenset(),
                     false_positives: frozenset[int] = frozenset()) -> dict[str, Any]:
    """Each synthetic role independently emits reports from the declared schedule.

    It has access to injected labels because this is a *simulation*. No hardware
    isolation or observer blindness is claimed.
    """
    if role not in ('A', 'B'):
        raise CalibrationError('only observers may report detection')
    if any(type(x) is not int or x < 0 or x >= TOTAL for x in (unavailable | false_positives)):
        raise CalibrationError('fault index outside trial range')
    # The source seal is validated by independent verifier; role has only scoped key.
    if not isinstance(source, dict) or 'records' not in source or len(source['records']) != TOTAL:
        raise CalibrationError('source schedule unavailable')
    misses = fault_indices(role, regime)
    records = []
    parent = None
    for trial, challenge in enumerate(source['records']):
        injection = challenge['injected']
        if trial in unavailable:
            status = 'unavailable'
        else:
            status = ('not_detected' if trial in misses else 'detected') if injection else (
                'detected' if trial in false_positives else 'not_detected')
        fingerprint = challenge['event_id'] if status == 'detected' and injection else (
            sha({'challenge': reg['challenge'], 'trial': trial, 'event': 'false_positive'})
            if status == 'detected' else None)
        record = _sign({**_base(reg, role, 'trial'), 'trial': trial,
                        'injected': None, 'status': status, 'event_id': fingerprint,
                        'parent': parent}, _key(reg, role))
        records.append(record)
        parent = record['digest']
    return {'records': records, 'seal': seal(reg, role, records)}


def verify_log(log: Mapping[str, Any], reg: Mapping[str, Any], role: str) -> list[dict[str, Any]]:
    if not isinstance(log, dict) or set(log) != {'records', 'seal'}:
        raise CalibrationError('archive log or seal missing')
    records = log['records']
    if not isinstance(records, list) or len(records) != TOTAL:
        raise CalibrationError('archive incomplete or duplicated')
    parent = None
    for trial, record in enumerate(records):
        _verify(record, reg, role, 'trial', RECORD_FIELDS)
        if type(record['trial']) is not int or record['trial'] != trial or record['parent'] != parent:
            raise CalibrationError('trial index/parent chain invalid')
        if role == 'S':
            expected_injected = trial < POSITIVE
            if record['injected'] is not expected_injected or record['status'] != 'commanded':
                raise CalibrationError('source injection declaration invalid')
            if record['event_id'] != (event_id(reg, trial) if expected_injected else None):
                raise CalibrationError('source event identity invalid')
        else:
            if record['injected'] is not None or record['status'] not in STATUSES:
                raise CalibrationError('observer status invalid')
            if (record['status'] == 'detected') != (isinstance(record['event_id'], str) and len(record['event_id']) == 64):
                raise CalibrationError('observer detection identity invalid')
        parent = record['digest']
    _verify(log['seal'], reg, role, 'seal', SEAL_FIELDS)
    s = log['seal']
    if (type(s['count']) is not int or s['count'] != TOTAL or s['positive'] != POSITIVE
            or s['sham'] != SHAM or s['head'] != parent):
        raise CalibrationError('seal scope or terminal digest invalid')
    return records


def upper_binomial_miss(k: int, n: int, alpha: float = 0.05) -> float:
    """Numerically invert Binomial CDF(k;n,p)=alpha for one-sided upper limit.

    Only meaningful as a statistical confidence statement for genuine IID
    Bernoulli trials under stable, unbiased sampling. NOT a bound on adversaries.
    """
    if type(k) is not int or type(n) is not int or n < 1 or k < 0 or k > n or \
       not isinstance(alpha, float) or not 0 < alpha < 1:
        raise ValueError('invalid binomial parameters')
    if k == n:
        return 1.0
    def cdf(p: float) -> float:
        return math.fsum(math.comb(n, j) * (p ** j) * ((1 - p) ** (n-j))
                         for j in range(k + 1))
    lo, hi = 0.0, 1.0
    for _ in range(65):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def reconstruct(source: Mapping[str, Any], a: Mapping[str, Any], b: Mapping[str, Any],
                reg: Mapping[str, Any], *, iid_assumed: bool = False) -> dict[str, Any]:
    """Reconstruct reported calibration, not physical or adversarial guarantees."""
    if type(iid_assumed) is not bool:
        raise CalibrationError('statistical assumption flag must be Boolean')
    s = verify_log(source, reg, 'S')
    ar = verify_log(a, reg, 'A')
    br = verify_log(b, reg, 'B')
    counts = {'injected': POSITIVE, 'sham': SHAM,
              'A_non_detection': 0, 'B_non_detection': 0, 'joint_non_detection': 0,
              'A_unavailable': 0, 'B_unavailable': 0,
              'A_sham_false_positive': 0, 'B_sham_false_positive': 0}
    undetected = []
    for i in range(TOTAL):
        injected = s[i]['injected']
        for role, record in (('A', ar[i]), ('B', br[i])):
            if record['status'] == 'detected' and record['event_id'] != (
                    s[i]['event_id'] if injected else
                    sha({'challenge': reg['challenge'], 'trial': i, 'event': 'false_positive'})):
                raise CalibrationError('event identity disagreement')
            if record['status'] == 'unavailable':
                counts[f'{role}_unavailable'] += 1
            if not injected and record['status'] == 'detected':
                counts[f'{role}_sham_false_positive'] += 1
            if injected and record['status'] != 'detected':
                counts[f'{role}_non_detection'] += 1
        if injected and ar[i]['status'] != 'detected' and br[i]['status'] != 'detected':
            counts['joint_non_detection'] += 1
            undetected.append(i)
    result = {'schema': SCHEMA, 'counts': counts, 'joint_non_detection_trials': undetected,
              'reported_individual_non_detection': {
                  'A': [counts['A_non_detection'], POSITIVE],
                  'B': [counts['B_non_detection'], POSITIVE]},
              'reported_joint_non_detection': [counts['joint_non_detection'], POSITIVE],
              'iid_binomial_bounds_assumed': iid_assumed,
              'conditional_95pct_one_sided_upper_miss': None,
              'independence_between_observers_verified': False,
              'physical_injections_verified': False,
              'physical_instrument_identity_verified': False,
              'adversarial_miss_bound': None,
              'source_truthfulness_verified': False,
              'scope': 'synthetic CI-enrolled 60 commanded positives and 20 sham trials'}
    if iid_assumed:
        result['conditional_95pct_one_sided_upper_miss'] = {
            name: round(upper_binomial_miss(counts[f'{name}_non_detection'], POSITIVE), 9)
            for name in ('A', 'B')}
        result['conditional_95pct_one_sided_upper_miss']['joint'] = round(
            upper_binomial_miss(counts['joint_non_detection'], POSITIVE), 9)
        result['iid_assumptions'] = ('independent and identically distributed trials',
            'stationary detection conditions', 'truthful instrumented injection ledger',
            'unbiased trial selection', 'unchanged conditions in future trials')
    return result


def fixture(regime: str = 'complementary_dropouts', *, iid_assumed: bool = False):
    reg = enrollment(deterministic=True)
    s = produce_source(reg)
    a = produce_observer(s, reg, 'A', regime)
    b = produce_observer(s, reg, 'B', regime)
    return {'source': s, 'A': a, 'B': b}, reg, reconstruct(s, a, b, reg,
                                                         iid_assumed=iid_assumed)


def demonstration() -> dict[str, Any]:
    entries = {}
    for regime in ('complementary_dropouts', 'common_mode_dropouts', 'colluding_silence'):
        _, _, result = fixture(regime, iid_assumed=True)
        entries[regime] = {'counts': result['counts'],
                           'conditional_95pct_one_sided_upper_miss': result['conditional_95pct_one_sided_upper_miss'],
                           'independence_between_observers_verified': False,
                           'physical_injections_verified': False,
                           'adversarial_miss_bound': None}
    return {'experiment': 'RE-011', 'model': 'deterministic fault-injection fixture',
            'statistical_interpretation': 'conditional IID-only numerical binomial inversion; fixture is not an IID sample',
            'regimes': entries}

if __name__ == '__main__':
    print(json.dumps(demonstration(), sort_keys=True, indent=2))