"""TPP-007 physical-context renewal with retrospective evidence-gated admission.

Uses original pinned NOAA bytes. Spectral predecessor remains disconfirmed.
A proposal made after 2026-11-18 is evaluated only on 2026-11-19.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCHEMA = 'ifs.tpp007-sgn001.context-renewal.v1'
SOURCE_SCHEMA = 'in-formation-space.tpp007.seven-day-residual-continuity.v1'
SGN_SCHEMA = 'ifs.tpp007-sgn001.chronological-qualification.v1'
SGN_SHA = '000108a8a6a52346ad6e658ed07695fd917281137040187f56da8e676749eabf'
DIGESTS = {
    'water_level': '8a31edbda35209261cbba2cc1fa8d7e3955449fda2d928ac31287028bc74f79d',
    'predictions': '7bb2a2a473aac47a268991816aa7e23f06a12daaa7dbf7922bb60d514ad413f8',
}
DAYS = tuple(f'2026-11-{n}' for n in range(13, 20))
POLICY = {
    'adaptive_threshold_multiplier': 2,
    'min_improvement_percent': 15,
    'samples_per_day': 240,
    'method': 'lagged-median-residual-on-context-change',
    'version': '1.0',
}


def canonical(value):
    """Canonical JSON identity (not an actor or measurement signature)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf8')


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _milli(value):
    """Exact source decimal metres to integral millimetres; never round."""
    if not isinstance(value, str):
        raise ValueError('decimal source must be string')
    try:
        decimal = Decimal(value)
        scaled = decimal * 1000
    except InvalidOperation as exc:
        raise ValueError('invalid source decimal') from exc
    if not decimal.is_finite() or scaled != scaled.to_integral_value():
        raise ValueError('precision beyond source contract')
    return int(scaled)


def read_sources(archive):
    """Verify immutable NOAA responses, source context and all 1680 timestamps."""
    if (not isinstance(archive, dict) or archive.get('schema') != SOURCE_SCHEMA
            or archive.get('acquisition') != 'real-public-two-batched-requests'
            or archive.get('actual_request_attempts') != 2
            or archive.get('assessment', {}).get('status') != 'complete'
            or archive['assessment'].get('source_sha256') !=
                [DIGESTS['water_level'], DIGESTS['predictions']]):
        raise ValueError('archival source/assessment refused')
    original = {}
    times = [
        (datetime(2026, 11, 13, tzinfo=timezone.utc) +
         timedelta(minutes=6 * i)).strftime('%Y-%m-%d %H:%M')
        for i in range(1680)
    ]
    for entry in archive.get('documents', []):
        product = entry.get('product')
        if product not in DIGESTS or product in original:
            raise ValueError('unrecognized or duplicate source product')
        if (entry.get('status') != 'received' or
            entry.get('scope') != 'public-provider-read-only-no-instrument-attestation'
            or entry.get('start_utc_day') != '20261113'
            or entry.get('end_utc_day') != '20261119'):
            raise ValueError('source time/scope refused')
        parsed = urlparse(entry.get('source', ''))
        query = parse_qs(parsed.query)
        if (parsed.scheme, parsed.hostname, parsed.path) != (
                'https', 'api.tidesandcurrents.noaa.gov', '/api/prod/datagetter'):
            raise ValueError('unknown source host')
        for key, expected in (
            ('station', '9414290'), ('product', product), ('datum', 'MLLW'),
            ('units', 'metric'), ('time_zone', 'gmt'), ('format', 'json'),
            ('begin_date', '20261113'), ('end_date', '20261119'),
        ):
            if query.get(key) != [expected]:
                raise ValueError('source reference differs')
        raw = base64.b64decode(entry['raw_body_base64'], validate=True)
        if (sha256(raw).hexdigest() != DIGESTS[product] or
                entry.get('raw_sha256') != DIGESTS[product] or
                entry.get('raw_bytes') != len(raw)):
            raise ValueError('source bytes not pinned')
        data = json.loads(raw)
        if product == 'water_level' and str(data.get('metadata', {}).get('id')) != '9414290':
            raise ValueError('wrong physical station')
        rows = data.get('data' if product == 'water_level' else 'predictions')
        if not isinstance(rows, list):
            raise ValueError('missing source rows')
        readings = {}
        for row in rows:
            key = row['t']
            if not isinstance(key, str) or key in readings:
                raise ValueError('duplicate/invalid timestamp')
            if (product == 'water_level' and
                    (row.get('q') not in ('p', 'v') or not isinstance(row.get('f'), str))):
                raise ValueError('unqualified provider quality')
            readings[key] = _milli(row.get('v'))
        if set(readings) != set(times):
            raise ValueError('incomplete six-minute chronology')
        original[product] = [readings[t] for t in times]
    if set(original) != set(DIGESTS):
        raise ValueError('missing observation product')
    return [x - y for x, y in zip(original['water_level'], original['predictions'])]


def twice_median(values):
    """Exact median in twice the original integer unit, including half units."""
    if not values:
        raise ValueError('missing observation')
    values = sorted(values)
    n = len(values)
    return 2 * values[n//2] if n % 2 else values[n//2 - 1] + values[n//2]


def day(series, i):
    if len(series) != 1680:
        raise ValueError('incomplete observation week')
    return series[i*240:(i+1)*240]


def prepare(series, policy=POLICY):
    """Propose day-19 Ground using only days 13–18, never day-19 observations."""
    if policy != POLICY:
        raise ValueError('changed context policy')
    calibration = [twice_median(day(series, i)) for i in range(5)]
    shifts = [abs(y - x) for x, y in zip(calibration, calibration[1:])]
    threshold = twice_median(shifts)  # exactly 2*median of first four day changes
    previous, proposed = calibration[-1], twice_median(day(series, 5))
    shift = abs(proposed - previous)
    return {
        'status': 'provisional_not_admitted',
        'prior_observed_day': DAYS[4],
        'renewal_observed_day': DAYS[5],
        'proposed_target_day': DAYS[6],
        'previous_offset_twice_millimetres': previous,
        'candidate_offset_twice_millimetres': proposed,
        'measured_shift_twice_millimetres': shift,
        'calibration_window_utc_days': [DAYS[0], DAYS[4]],
        'calibration_adjacent_shifts_twice_millimetres': shifts,
        'calibrated_threshold_twice_millimetres': threshold,
        'renewal_triggered': shift > threshold,
        'available_through_utc': DAYS[5] + 'T23:54:00Z',
        'not': 'no_target_observations_or_future_authority',
    }


def score(series, proposal):
    """Independently score the fixed proposal after day-19 completion."""
    if proposal != prepare(series):
        raise ValueError('proposal differs from earlier-only observation')
    if not proposal['renewal_triggered']:
        return {'status': 'renewal_not_triggered', 'target_day': DAYS[6],
                'scope': 'no newly qualified physical Ground'}
    future = day(series, 6)
    error = lambda offset: sum(abs(2*x - offset) for x in future)
    original, stale = error(0), error(proposal['previous_offset_twice_millimetres'])
    renewed = error(proposal['candidate_offset_twice_millimetres'])
    better = (100*renewed <= (100-POLICY['min_improvement_percent'])*original
              and renewed < stale)
    return {
        'status': 'historically_corrob_for_target_only' if better
                  else 'refused_after_target_observation',
        'target_day': DAYS[6],
        'scored_samples': len(future),
        'error_units': 'sum_of_absolute_half_millimetres',
        'uncorrected_error': original,
        'stale_context_error': stale,
        'renewed_candidate_error': renewed,
        'scope': 'retrospective single-day physical observation; no future authorization',
    }


def build_receipt(archive, spectral):
    """Bind rejected SGN predecessor and renewed temporal candidate to evidence."""
    if (not isinstance(spectral, dict) or digest(spectral) != SGN_SHA
            or spectral.get('schema') != SGN_SCHEMA
            or spectral.get('physical_evidence') != DIGESTS
            or spectral.get('splits') != {'train':[1,720], 'validation':[721,1200],
                                         'final_test':[1201,1680]}):
        raise ValueError('SGN predecessor not pinned')
    for name in ('noaa_residual', 'water_level'):
        lane = spectral.get('lanes', {}).get(name, {})
        if (lane.get('effective_admission') != 'refused_after_independent_test'
                or lane.get('held_out_test', {}).get('status') != 'failed_out_of_sample'):
            raise ValueError('predecessor was not independently refused')
    series = read_sources(archive)
    proposal = prepare(series)
    payload = {
        'schema': SCHEMA,
        'source': {
            'station':'9414290', 'datum':'MLLW', 'units':'metric',
            'retrieval':'retrospective', 'provider_quality':'preliminary',
            'source_sha256':DIGESTS,
        },
        'policy': POLICY,
        'predecessor': {
            'kind':'spectral', 'status':'refused_after_independent_test',
            'report_sha256':SGN_SHA,
            'not':'independent_receipt_checksum_is_not_source_authentication',
        },
        'pretarget': proposal,
        'posttarget': score(series, proposal),
        'authority': {
            'state':'retrospective_witness_only',
            'executable_next_unobserved_day':False,
            'requires':'receiver-owned-source-admission-and-new-out-of-sample-evidence',
        },
    }
    return {'payload':payload, 'sha256':digest(payload)}


def verify_receipt(receipt, archive, spectral):
    """Refuse recomputed/self-consistent but source-inconsistent receipts."""
    if (not isinstance(receipt, dict) or set(receipt) != {'payload','sha256'}
            or receipt['sha256'] != digest(receipt['payload'])):
        raise ValueError('receipt envelope or digest refused')
    if canonical(receipt) != canonical(build_receipt(archive, spectral)):
        raise ValueError('receiver source reconstruction differs from proposed receipt')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--spectral-report', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    receipt = build_receipt(json.loads(args.archive.read_text(encoding='utf8')),
                            json.loads(args.spectral_report.read_text(encoding='utf8')))
    serialized = json.dumps(receipt, sort_keys=True, indent=2) + '\n'
    if args.output:
        args.output.write_text(serialized, encoding='utf8')
    print(serialized)


if __name__ == '__main__':
    main()
