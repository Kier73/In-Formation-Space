"""RE-013: active, scope-aware renewal of a suspended synthetic detection claim.

Synthetic fixture only. A valid role MAC proves which enrolled fixture role
reported an observation, not physical sensor provenance, source truthfulness,
stationarity or an adversarial detection bound. In particular, active probes
calibrate their intervention protocol, never the original passive protocol.
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import secrets
from typing import Any, Mapping

from applicability_monitor import (
    ApplicabilityError, calibration, create_certificate, plan as monitor_plan,
    observer as monitor_observer, assess, sign, verify_signed,
)
from detection_calibration import canonical, enrollment, sha, upper_binomial_miss

SCHEMA = 'in-formation.response-re013/0.1'
TARGET_EDGE_WEIGHT = '2/3'
MAX_JOINT_NONDETECTION = 0.15
SENSOR_IDS = {'A': 'fixture-A@1', 'B': 'fixture-B@1'}
FIRMWARE_IDS = {'A': 'detector-1', 'B': 'detector-1'}
BATCH_SIZE = 8
SHAM_SIZE = 10
SHAM_BATCHES = 2
ACTIONS = {
    'ordinary_passive': ('ordinary', 'passive', BATCH_SIZE, 8, 0),
    'edge_passive': ('edge', 'passive', BATCH_SIZE, 12, 0),
    'ordinary_stimulated': ('ordinary', 'stimulated', BATCH_SIZE, 7, 2),
    'edge_stimulated': ('edge', 'stimulated', BATCH_SIZE, 7, 3),
    'sham': ('sham', 'control', SHAM_SIZE, 4, 0),
}
CLAIM_FIELDS = frozenset({'schema', 'challenge', 'kind', 'role', 'body', 'key_id'})


class RenewalError(ApplicabilityError):
    """A plan, original certificate, executed receipt or renewal is invalid."""


def registration(*, deterministic: bool = False) -> dict[str, Any]:
    reg = enrollment(deterministic=deterministic)
    key = 'fa' * 32 if deterministic else secrets.token_hex(32)
    reg['keys']['V'] = key
    reg['key_ids']['V'] = hashlib.sha256(bytes.fromhex(key)).hexdigest()
    return reg


def old_fixture(reg: Mapping[str, Any]) -> dict[str, Any]:
    """Preissued synthetic certificate and evidence demonstrating a population shift."""
    source, a0, b0 = calibration(reg)
    certificate = create_certificate(reg, source, a0, b0)
    monitoring = monitor_plan(reg, mode='shifted')
    a = monitor_observer(reg, monitoring, 'A')
    b = monitor_observer(reg, monitoring, 'B')
    finding = assess(certificate, reg, source, a0, b0, monitoring, a, b,
                     assumptions_accepted=True)
    if finding['status'] != 'suspended' or 'event_population_shift' not in finding['reasons']:
        raise RenewalError('fixture must demonstrate actual suspension')
    return {'old_certificate': certificate,
            'baseline': {'S': source, 'A': a0, 'B': b0},
            'monitor_plan': monitoring, 'monitor_A': a, 'monitor_B': b,
            'suspension': finding}


def verify_prior(reg: Mapping[str, Any], prior: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(prior, dict) or set(prior) != {
        'old_certificate', 'baseline', 'monitor_plan', 'monitor_A', 'monitor_B', 'suspension'
    } or not isinstance(prior['baseline'], dict) or set(prior['baseline']) != {'S', 'A', 'B'}:
        raise RenewalError('prior evidence envelope incomplete')
    source, a, b = (prior['baseline'][r] for r in ('S', 'A', 'B'))
    finding = assess(prior['old_certificate'], reg, source, a, b,
                     prior['monitor_plan'], prior['monitor_A'], prior['monitor_B'],
                     assumptions_accepted=True)
    if finding != prior['suspension'] or finding['status'] != 'suspended' or \
            'event_population_shift' not in finding['reasons']:
        raise RenewalError('old certificate suspension not independently reconstructed')
    return finding


def strata_upper(n: int, misses: int = 0) -> float:
    return upper_binomial_miss(misses, n, 0.025)


def bound(n_ordinary: int, n_edge: int, misses_o: int = 0, misses_e: int = 0) -> float:
    """Hypothetical Bonferroni simultaneous upper miss bound, NOT a real guarantee."""
    if n_ordinary < 1 or n_edge < 1:
        raise RenewalError('both strata need fresh positive evidence')
    return (strata_upper(n_ordinary, misses_o) +
            2 * strata_upper(n_edge, misses_e)) / 3


def choose_plan(protocol: str = 'passive', *, max_batches: int = 8) -> dict[str, Any]:
    """Enumerate a finite, exact integer action menu for a CONDITIONAL target.

    Minimize observation cost, then intervention cost and sample count, under
    zero hypothetical misses; failures can invalidate this advance plan.
    Paths have different protocol scopes and are not interchangeable.
    """
    if protocol not in ('passive', 'stimulated') or type(max_batches) is not int or not 1 <= max_batches <= 16:
        raise RenewalError('unknown calibration protocol or invalid search budget')
    candidates = []
    ordinary = f'ordinary_{protocol}'
    edge = f'edge_{protocol}'
    for o, e in itertools.product(range(1, max_batches + 1), repeat=2):
        if bound(o * BATCH_SIZE, e * BATCH_SIZE) >= MAX_JOINT_NONDETECTION:
            continue
        actions = [ordinary] * o + [edge] * e + ['sham'] * SHAM_BATCHES
        observation_cost = sum(ACTIONS[x][3] for x in actions)
        intervention_cost = sum(ACTIONS[x][4] for x in actions)
        candidates.append((observation_cost, intervention_cost, o + e,
                           o, e, actions))
    if not candidates:
        raise RenewalError('no valid conditional policy within search budget')
    obs, intervention, _, o, e, actions = min(candidates)
    return {'protocol': protocol, 'actions': actions,
            'predicted_positive_counts': {'ordinary': o * BATCH_SIZE, 'edge': e * BATCH_SIZE},
            'predicted_sham_count': SHAM_BATCHES * SHAM_SIZE,
            'predicted_zero_miss_upper': round(bound(o * BATCH_SIZE, e * BATCH_SIZE), 12),
            'observation_cost': obs, 'intervention_cost': intervention,
            'status': 'planned_only',
            'claim_scope': f'fixture-{protocol}-stratified-detection',
            'cost_model': 'fixed synthetic per-batch accounting, not measured elapsed time'}


def _preview_source(rec: Any, reg: Mapping[str, Any]) -> dict[str, Any]:
    """Untrusted source preview for scoped A/B signers without source key."""
    if not isinstance(rec, dict) or set(rec) != CLAIM_FIELDS | {'mac', 'digest'} or \
            rec['schema'] != 'in-formation.response-re012/0.1' or rec['kind'] != 'renewal_plan' or \
            rec['role'] != 'S' or rec['challenge'] != reg['challenge'] or \
            rec['key_id'] != reg['key_ids']['S'] or \
            not isinstance(rec['body'], dict) or \
            not isinstance(rec['mac'], str) or len(rec['mac']) != 64 or \
            rec['digest'] != sha({k:v for k,v in rec.items() if k != 'digest'}):
        raise RenewalError('untrusted source plan envelope malformed')
    return rec['body']


def signed_plan(reg: Mapping[str, Any], prior_certificate_digest: str,
                invalidation_digest: str, *, protocol: str = 'passive') -> dict[str, Any]:
    for value in (prior_certificate_digest, invalidation_digest):
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise RenewalError('prior certificate/invalidation commitment missing')
    proposal = choose_plan(protocol)
    return sign(reg, 'S', 'renewal_plan',
                {'schema': SCHEMA, 'prior_digest': prior_certificate_digest,
                 'invalidation_digest': invalidation_digest, 'proposal': proposal,
                 'target_edge_weight': TARGET_EDGE_WEIGHT, 'revision': 2})


def _expected_event(plan_digest: str, batch: int, index: int, action: str) -> str:
    return sha({'plan':plan_digest, 'batch':batch, 'index':index, 'action':action})


def _state_after(state: int, action: str) -> int:
    return state + int(ACTIONS[action][1] == 'stimulated')


def observer_report(reg: Mapping[str, Any], p: Mapping[str, Any], role: str,
                    *, missing: tuple[tuple[int,int], ...] = (),
                    unavailable: tuple[tuple[int,int], ...] = (),
                    false_positive: tuple[tuple[int,int], ...] = (),
                    sensor: str | None = None,
                    defer_source_mac_to_verifier: bool = False) -> dict[str, Any]:
    """Return signed synthetic reports, including intervention state annotations."""
    if role not in ('A', 'B'):
        raise RenewalError('invalid observer')
    pb = (_preview_source(p, reg) if defer_source_mac_to_verifier else
          verify_signed(p, reg, 'S', 'renewal_plan'))
    # S's plan might be corrupt: the independent verifier must authenticate and
    # recompute the action policy, not rely on this producer preview.
    actions = pb['proposal']['actions']
    if not isinstance(actions, list) or any(x not in ACTIONS for x in actions):
        raise RenewalError('undeclared action')
    misses, fp, absent = set(missing), set(false_positive), set(unavailable)
    if any(type(b) is not int or type(i) is not int or b not in range(len(actions)) or
           i not in range(ACTIONS[actions[b]][2]) for b,i in misses | fp | absent):
        raise RenewalError('fault injection out of batch domain')
    parent = None
    records = []
    state = 0
    for b, action in enumerate(actions):
        stratum, action_protocol, count, _, _ = ACTIONS[action]
        observations = []
        after = _state_after(state, action)
        for i in range(count):
            if (b,i) in absent:
                status = 'unavailable'
            elif stratum == 'sham':
                status = 'detected' if (b,i) in fp else 'not_detected'
            else:
                status = 'not_detected' if (b,i) in misses else 'detected'
            observations.append({'index': i, 'status':status,
                  'event_id': _expected_event(p['digest'],b,i,action)
                              if status == 'detected' else None})
        rec = sign(reg, role, 'renewal_batch',
             {'plan_digest':p['digest'], 'batch':b, 'action':action,
              'sensor': sensor or SENSOR_IDS[role], 'firmware': FIRMWARE_IDS[role],
              'state_before':state, 'state_after':after, 'observations':observations,
              'parent':parent})
        records.append(rec)
        state = after
        parent = rec['digest']
    final = sign(reg, role, 'renewal_seal',
                 {'plan_digest':p['digest'], 'batch_count':len(records),
                  'head':parent, 'final_state':state})
    return {'records':records, 'seal':final}


def _verification_key(reg: Mapping[str, Any]) -> bytes:
    try:
        raw = reg['keys']['V']
        result = bytes.fromhex(raw)
        if len(result) != 32 or hashlib.sha256(result).hexdigest() != reg['key_ids']['V']:
            raise ValueError('bad V enrollment')
        return result
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise RenewalError('independent verifier key not enrolled') from exc


def _verifier_signed(reg: Mapping[str, Any], body: Mapping[str, Any]) -> dict[str, Any]:
    public = {'schema':SCHEMA,'kind':'reissued_certificate','role':'V',
              'challenge':reg['challenge'],'key_id':reg['key_ids']['V'],
              'body':dict(body)}
    mac = hmac.new(_verification_key(reg),canonical(public),hashlib.sha256).hexdigest()
    return {**public,'mac':mac,'digest':sha({**public,'mac':mac})}


def _verify_verifier_signed(rec: Any, reg: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(rec, dict) or set(rec) != CLAIM_FIELDS | {'mac','digest'} or \
         rec.get('schema') != SCHEMA or rec.get('kind') != 'reissued_certificate' or \
         rec.get('role') != 'V' or rec.get('challenge') != reg['challenge'] or \
         rec.get('key_id') != reg['key_ids']['V'] or not isinstance(rec.get('body'),dict):
        raise RenewalError('independent verifier receipt identity invalid')
    unsigned = {k:v for k,v in rec.items() if k not in ('mac','digest')}
    expected = hmac.new(_verification_key(reg),canonical(unsigned),hashlib.sha256).hexdigest()
    if not isinstance(rec['mac'],str) or not hmac.compare_digest(rec['mac'],expected) or \
            rec['digest'] != sha({**unsigned,'mac':rec['mac']}):
        raise RenewalError('independent verifier authentication invalid')
    return rec['body']


def _validate_reports(reg: Mapping[str, Any], p: Mapping[str, Any],
                      a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    action_names = p['body']['proposal']['actions']
    stats = {'ordinary':{'n':0,'joint_misses':0}, 'edge':{'n':0,'joint_misses':0},
             'sham':{'n':0,'false_positive':0}}
    parsed = {}
    for role, report in (('A',a),('B',b)):
        if not isinstance(report,dict) or set(report) != {'records','seal'} or \
                not isinstance(report['records'],list) or len(report['records']) != len(action_names):
            raise RenewalError('signed observer report archive incomplete')
        parent = None
        state = 0
        values=[]
        for batch, (rec,action) in enumerate(zip(report['records'], action_names)):
            body = verify_signed(rec,reg,role,'renewal_batch')
            stratum, protocol, count, _, _ = ACTIONS[action]
            expected_state = _state_after(state,action)
            if set(body) != {'plan_digest','batch','action','sensor','firmware','state_before',
                            'state_after','observations','parent'} or \
               body['plan_digest'] != p['digest'] or type(body['batch']) is not int or \
               body['batch'] != batch or body['action'] != action or \
               body['sensor'] != SENSOR_IDS[role] or body['firmware'] != FIRMWARE_IDS[role] or \
               body['parent'] != parent or type(body['state_before']) is not int or \
               type(body['state_after']) is not int or body['state_before'] != state or \
               body['state_after'] != expected_state or not isinstance(body['observations'],list) or \
               len(body['observations']) != count:
                raise RenewalError('observer scope, provenance or intervention state inconsistent')
            for i, observation in enumerate(body['observations']):
                if not isinstance(observation,dict) or set(observation) != {'index','status','event_id'} or \
                   type(observation['index']) is not int or observation['index'] != i or \
                   observation['status'] not in ('detected','not_detected','unavailable','refused') or \
                   observation['event_id'] != (_expected_event(p['digest'],batch,i,action)
                           if observation['status'] == 'detected' else None):
                    raise RenewalError('observer status or event correspondence invalid')
            values.append(body['observations'])
            parent = rec['digest']
            state = expected_state
        seal_body = verify_signed(report['seal'],reg,role,'renewal_seal')
        if set(seal_body) != {'plan_digest','batch_count','head','final_state'} or \
           seal_body != {'plan_digest':p['digest'],'batch_count':len(action_names),
                         'head':parent,'final_state':state}:
            raise RenewalError('observer final seal does not close the batch evidence')
        parsed[role]=values
    for index, action in enumerate(action_names):
        stratum, protocol, count, _, _ = ACTIONS[action]
        for i in range(count):
            observed = [parsed[r][index][i]['status'] for r in ('A','B')]
            if stratum == 'sham':
                stats['sham']['n'] += 1
                if 'detected' in observed:
                    stats['sham']['false_positive'] += 1
            else:
                stats[stratum]['n'] += 1
                if all(status != 'detected' for status in observed):
                    stats[stratum]['joint_misses'] += 1
    return stats


def evaluate(reg: Mapping[str, Any], prior: Mapping[str, Any],
             p: Mapping[str, Any], a: Mapping[str, Any], b: Mapping[str, Any],
             *, assumptions_accepted: bool = False) -> dict[str, Any]:
    """Recompute every certificate premise; issue revision 2 only under explicit assumptions."""
    if type(assumptions_accepted) is not bool:
        raise RenewalError('assumptions_accepted must be Boolean')
    finding = verify_prior(reg, prior)
    body = verify_signed(p,reg,'S','renewal_plan')
    if not isinstance(body,dict) or set(body) != {'schema','prior_digest','invalidation_digest',
            'proposal','target_edge_weight','revision'} or body['schema'] != SCHEMA or \
            body['revision'] != 2 or type(body['revision']) is not int or \
            body['prior_digest'] != prior['old_certificate']['digest'] or \
            body['invalidation_digest'] != sha(finding) or \
            body['target_edge_weight'] != TARGET_EDGE_WEIGHT or \
            not isinstance(body['proposal'],dict) or \
            body['proposal'] != choose_plan(body['proposal'].get('protocol','invalid')):
        raise RenewalError('renewal plan policy, predecessor or suspension binding invalid')
    stats = _validate_reports(reg,p,a,b)
    protocol = body['proposal']['protocol']
    n_o, n_e = stats['ordinary']['n'], stats['edge']['n']
    actual_bound = bound(n_o,n_e,stats['ordinary']['joint_misses'],stats['edge']['joint_misses'])
    controls_good = stats['sham']['n'] == SHAM_BATCHES*SHAM_SIZE and \
             stats['sham']['false_positive'] == 0 and \
             stats['ordinary']['joint_misses'] == stats['edge']['joint_misses'] == 0
    sufficient = controls_good and actual_bound < MAX_JOINT_NONDETECTION
    result = {'schema':SCHEMA, 'status':'conditional_revision_issued' if sufficient and assumptions_accepted else 'renewal_not_admitted',
       'reasons':([] if sufficient and assumptions_accepted else
            (['statistical_and_physical_assumptions_unestablished'] if sufficient else
             ['calibration_controls_or_detection_failed'])),
       'predecessor_digest':prior['old_certificate']['digest'],
       'invalidation_digest':sha(finding),'plan_digest':p['digest'],
       'report_seals':{'A':a['seal']['digest'],'B':b['seal']['digest']},
       'protocol':protocol,'counts':stats,
       'conditional_simultaneous_upper':round(actual_bound,12),
       'assumptions_explicitly_accepted':assumptions_accepted,
       'physical_detection_guarantee':None,'adversarial_detection_guarantee':None,
       'physical_source_truth_established':False, 'hardware_identity_established':False,
       'original_certificate_restored':False}
    if sufficient and assumptions_accepted:
        content={'revision':2,'predecessor':prior['old_certificate']['digest'],
                 'predecessor_status':'suspended','invalidation':sha(finding),
                 'plan':p['digest'],'evidence':result['report_seals'],
                 'protocol':protocol, 'counts':stats,
                 'conditional_simultaneous_upper':result['conditional_simultaneous_upper'],
                 'max_conditional_miss':MAX_JOINT_NONDETECTION,
                 'edge_weight':TARGET_EDGE_WEIGHT,
                 'assumptions': ['truthful_synthetic_injection_reference',
                     'iid_trials_within_strata','stationary_response_within_protocol',
                     'representative_event_population','stable_enrolled_sensor_configuration'],
                 'physical_guarantee':None}
        result['new_certificate']=_verifier_signed(reg,content)
        result['history']=[{'revision':1,'digest':prior['old_certificate']['digest'],
                           'status':'suspended','invalidation':sha(finding)},
                          {'revision':2,'digest':result['new_certificate']['digest'],
                           'status':'conditionally_issued','scope':protocol}]
    else:
        result['new_certificate']=None
        result['history']=[{'revision':1,'digest':prior['old_certificate']['digest'],
                           'status':'suspended','invalidation':sha(finding)}]
    return result


def verify_revision(reg: Mapping[str,Any], prior: Mapping[str,Any],
                    p: Mapping[str,Any], a: Mapping[str,Any], b: Mapping[str,Any],
                    received: Mapping[str,Any], *, assumptions_accepted: bool = True,
                    expected_protocol: str | None = None) -> dict[str,Any]:
    expected = evaluate(reg,prior,p,a,b,assumptions_accepted=assumptions_accepted)
    if expected != received:
        raise RenewalError('replayed or altered renewal report')
    cert = received['new_certificate']
    if cert is None:
        raise RenewalError('no new certificate issued')
    content = _verify_verifier_signed(cert,reg)
    if expected_protocol is not None and content['protocol'] != expected_protocol:
        raise RenewalError('protocol scope mismatch: stimulated evidence cannot certify passive')
    if content['predecessor'] != prior['old_certificate']['digest'] or \
       content['invalidation'] != sha(verify_prior(reg,prior)):
        raise RenewalError('certificate ancestry invalid')
    return content


def demonstration() -> dict[str,Any]:
    reg = registration(deterministic=True)
    prior = old_fixture(reg)
    plans = {protocol:choose_plan(protocol) for protocol in ('passive','stimulated')}
    p = signed_plan(reg,prior['old_certificate']['digest'],sha(prior['suspension']))
    a = observer_report(reg,p,'A')
    b = observer_report(reg,p,'B')
    blocked = evaluate(reg,prior,p,a,b)
    admitted = evaluate(reg,prior,p,a,b,assumptions_accepted=True)
    verify_revision(reg,prior,p,a,b,admitted,expected_protocol='passive')
    return {'experiment':'RE-013','status':'synthetic_exact_regression',
            'original_status':prior['suspension']['status'],
            'renewal_plans':plans,
            'without_assumption':{'status':blocked['status'],'reasons':blocked['reasons']},
            'conditional_reissue':{'status':admitted['status'],'counts':admitted['counts'],
               'upper':admitted['conditional_simultaneous_upper'],
               'history':admitted['history'],'protocol':admitted['protocol'],
               'physical_detection_guarantee':None},
            'limits':['fixture event source and sensors only',
               'CI HMACs do not attest hardware','conditional IID/physical assumptions not established',
               'stimulated and passive response claims have different scopes']}


if __name__ == '__main__':
    print(json.dumps(demonstration(),indent=2,sort_keys=True))
