"""RE-012: scoped validity of a detection-calibration claim under changing conditions.

Authenticates synthetic CI records; never establishes physical stationarity,
source truthfulness, sensor identity, independence, or adversarial guarantees.
The one-sided statistical limits are conditional, and admission is an explicit
verifier-side hypothesis, not a property discovered from signed data.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping

from detection_calibration import (
    CalibrationError, POSITIVE, _key, canonical, enrollment, produce_source,
    produce_observer, reconstruct, sha, upper_binomial_miss, verify_log,
)

SCHEMA = 'in-formation.response-re012/0.1'
STRATA = ('ordinary', 'edge')
SENSORS = {'A': 'fixture-A@1', 'B': 'fixture-B@1'}
FIRMWARE = {'A': 'detector-1', 'B': 'detector-1'}
WINDOW_SIZE = 12
MAX_LATENCY = 50  # one reporter's own elapsed-millisecond coordinate
MAX_EDGE_WEIGHT = 3 / 10
MAX_JOINT_MISS_FRACTION = 1 / 12
TARGET_MISS_LIMIT = 0.15
CLAIM_FIELDS = frozenset({'schema','kind','challenge','role','key_id','body'})

class ApplicabilityError(CalibrationError):
    """Evidence shape, signature, sequence, or provenance is invalid."""


def _body(reg: Mapping[str, Any], role: str, kind: str, body: Mapping[str, Any]) -> dict[str, Any]:
    return {'schema': SCHEMA, 'kind': kind, 'challenge': reg['challenge'],
            'role': role, 'key_id': reg['key_ids'][role], 'body': dict(body)}


def sign(reg: Mapping[str, Any], role: str, kind: str, body: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = _body(reg, role, kind, body)
    digest = hmac.new(_key(reg, role), canonical(unsigned), hashlib.sha256).hexdigest()
    return {**unsigned, 'mac': digest, 'digest': sha({**unsigned, 'mac': digest})}


def verify_signed(rec: Any, reg: Mapping[str, Any], role: str, kind: str) -> dict[str, Any]:
    if not isinstance(rec, dict) or set(rec) != CLAIM_FIELDS | {'mac','digest'}:
        raise ApplicabilityError('invalid signed envelope shape')
    if (rec['schema'] != SCHEMA or rec['kind'] != kind or rec['role'] != role or
            rec['challenge'] != reg['challenge'] or
            rec['key_id'] != reg['key_ids'][role] or not isinstance(rec['body'], dict)):
        raise ApplicabilityError('signed envelope identity mismatch')
    unsigned = {k:v for k,v in rec.items() if k not in ('mac','digest')}
    expected = hmac.new(_key(reg, role), canonical(unsigned), hashlib.sha256).hexdigest()
    if not isinstance(rec['mac'], str) or not hmac.compare_digest(rec['mac'], expected):
        raise ApplicabilityError('signed envelope HMAC invalid')
    if rec['digest'] != sha({**unsigned,'mac':rec['mac']}):
        raise ApplicabilityError('signed envelope digest invalid')
    return rec['body']


def calibration(reg: Mapping[str, Any]) -> tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    """Synthetic baseline. Reporter logs are fixture products, not real instruments."""
    source=produce_source(reg)
    a=produce_observer(source,reg,'A','complementary_dropouts')
    b=produce_observer(source,reg,'B','complementary_dropouts')
    return source,a,b


def stratum(trial: int) -> str:
    return 'edge' if trial % 5 == 0 else 'ordinary'


def _baseline_summary(source: Mapping[str,Any], a: Mapping[str,Any],
                      b: Mapping[str,Any], reg: Mapping[str,Any]) -> dict[str,Any]:
    reconstruct(source,a,b,reg)
    src=verify_log(source,reg,'S'); ar=verify_log(a,reg,'A');br=verify_log(b,reg,'B')
    counts={s:{'n':0,'joint_misses':0} for s in STRATA}
    for i in range(POSITIVE):
        s=stratum(i)
        counts[s]['n']+=1
        counts[s]['joint_misses']+=int(ar[i]['status']!='detected' and br[i]['status']!='detected')
    return counts


def per_stratum_limits(counts: Mapping[str,Any]) -> dict[str,float]:
    # Bonferroni alpha/2 per stratum -> simultaneous conditional coverage >= 95%.
    return {s:round(upper_binomial_miss(counts[s]['joint_misses'],counts[s]['n'],0.025),12)
            for s in STRATA}


def weighted_limit(limits: Mapping[str,float], edge_weight: float) -> float:
    return (1-edge_weight)*limits['ordinary']+edge_weight*limits['edge']


def create_certificate(reg: Mapping[str,Any], source: Mapping[str,Any],
                       a: Mapping[str,Any], b: Mapping[str,Any]) -> dict[str,Any]:
    counts=_baseline_summary(source,a,b,reg)
    limits=per_stratum_limits(counts)
    weighted=weighted_limit(limits,.2)
    if weighted>=TARGET_MISS_LIMIT:
        raise ApplicabilityError('fixture does not meet conditional baseline limit')
    body={'baseline_seals':{r:log['seal']['digest'] for r,log in (('S',source),('A',a),('B',b))},
          'sensors':SENSORS,'firmware':FIRMWARE,'calibration_counts':counts,
          'limits':limits,'baseline_edge_weight':'1/5',
          'conditional_weighted_upper':round(weighted,12),
          'max_conditional_miss':TARGET_MISS_LIMIT,
          'max_edge_weight':MAX_EDGE_WEIGHT,
          'max_local_latency_ms':MAX_LATENCY,
          'max_observed_joint_miss_fraction':'1/12',
          'valid_window_range':[1,5],
          'assumptions':['iid_trials_within_each_stratum','stationary_stratum_response',
                         'representative_source_injections','true_enrolled_sensor_identity',
                         'trusted_population_labels_and_weights'],
          'claim_scope':'synthetic-stratified-joint-nondetection'}
    return sign(reg,'S','calibration_certificate',body)


def verify_certificate(cert: Mapping[str,Any], reg: Mapping[str,Any],
                       source: Mapping[str,Any], a: Mapping[str,Any],
                       b: Mapping[str,Any]) -> dict[str,Any]:
    body=verify_signed(cert,reg,'S','calibration_certificate')
    recomputed=create_certificate(reg,source,a,b)
    if cert != recomputed:
        raise ApplicabilityError('certificate does not match verified baseline evidence')
    return body


def plan(reg: Mapping[str,Any], *, window: int=1, mode: str='baseline',
         parent: str | None=None) -> dict[str,Any]:
    if type(window) is not int or window<1 or mode not in ('baseline','shifted','edge_focused','unseen_stratum'):
        raise ApplicabilityError('invalid monitor plan')
    if window == 1 and parent is not None or window>1 and (not isinstance(parent,str) or len(parent)!=64):
        raise ApplicabilityError('monitor plan history parent invalid')
    if mode=='baseline':labels=['edge' if i in (2,8) else 'ordinary' for i in range(WINDOW_SIZE)]
    elif mode=='shifted': labels=['edge' if i<8 else 'ordinary' for i in range(WINDOW_SIZE)]
    elif mode=='edge_focused':labels=['edge' if i in (2,8) else 'ordinary' for i in range(WINDOW_SIZE)]
    else:labels=['unrepresented' if i==11 else ('edge' if i in (2,8) else 'ordinary') for i in range(WINDOW_SIZE)]
    return sign(reg,'S','monitor_plan',{'window':window,'mode':mode,'parent':parent,
                                       'slots':[{'index':i,'stratum':labels[i],
                                                 'event_id':sha({'challenge':reg['challenge'],'window':window,'slot':i})}
                                                for i in range(WINDOW_SIZE)]})


def observer_plan_preview(rec: Any, reg: Mapping[str,Any]) -> dict[str,Any]:
    """Only public shape/digest check. Source HMAC admission is verifier-only.

    A scoped A/B producer cannot verify S's MAC without learning S's private
    signing key. The producer may prepare a provisional response, while the
    independent verifier later verifies S's MAC using a separately held key.
    """
    if not isinstance(rec,dict) or set(rec)!=CLAIM_FIELDS | {'mac','digest'}:
        raise ApplicabilityError('untrusted source plan envelope invalid')
    if (rec['schema']!=SCHEMA or rec['kind']!='monitor_plan' or rec['role']!='S' or
            rec['challenge']!=reg['challenge'] or rec['key_id']!=reg['key_ids']['S'] or
            not isinstance(rec['body'],dict) or
            not isinstance(rec['mac'],str) or len(rec['mac'])!=64 or
            rec['digest']!=sha({k:v for k,v in rec.items() if k!='digest'})):
        raise ApplicabilityError('untrusted source plan digest/identity invalid')
    return rec['body']


def observer(reg: Mapping[str,Any], plan_receipt: Mapping[str,Any], role: str,
             *, sensor: str|None=None, firmware: str|None=None,
             miss_slots: tuple[int,...]=(), late_slots: tuple[int,...]=(),
             refused_slots: tuple[int,...]=(),
             defer_source_mac_to_verifier: bool=False) -> dict[str,Any]:
    if role not in ('A','B'):
        raise ApplicabilityError('invalid observer role')
    if type(defer_source_mac_to_verifier) is not bool:
        raise ApplicabilityError('deferred source verification flag must be Boolean')
    plan_body=(observer_plan_preview(plan_receipt,reg) if defer_source_mac_to_verifier else
               verify_signed(plan_receipt,reg,'S','monitor_plan'))
    if any(type(i) is not int or i not in range(WINDOW_SIZE)
           for i in (*miss_slots,*late_slots,*refused_slots)):
        raise ApplicabilityError('invalid declared fault slot')
    slots=[]
    for slot in plan_body['slots']:
        i=slot['index']
        status='refused' if i in refused_slots else 'not_detected' if i in miss_slots else 'detected'
        slots.append({'index':i,'status':status,
                      'event_id':slot['event_id'] if status=='detected' else None,
                      'local_latency_ms':None if status=='refused' else (75 if i in late_slots else 10)})
    return sign(reg,role,'monitor_observation',{'plan_digest':plan_receipt['digest'],
             'window':plan_body['window'], 'sensor':sensor or SENSORS[role],
             'firmware':firmware or FIRMWARE[role],'slots':slots})


def validate_window(reg: Mapping[str,Any], p: Mapping[str,Any],
                    a: Mapping[str,Any],b: Mapping[str,Any],
                    *, expected_window: int,expected_parent: str|None=None) -> dict[str,Any]:
    data=verify_signed(p,reg,'S','monitor_plan')
    if set(data)!={'window','mode','parent','slots'} or data['window']!=expected_window or \
       data['parent']!=expected_parent or type(data['window']) is not int:
        raise ApplicabilityError('monitor window sequence/replay invalid')
    slots=data['slots']
    if (not isinstance(slots,list) or len(slots)!=WINDOW_SIZE or
        any(not isinstance(s,dict) or set(s)!={'index','stratum','event_id'} or
            type(s['index']) is not int or s['index']!=i or
            s['stratum'] not in (*STRATA,'unrepresented') or
            s['event_id']!=sha({'challenge':reg['challenge'],'window':expected_window,'slot':i})
            for i,s in enumerate(slots))):
        raise ApplicabilityError('monitor plan slot completeness/identity invalid')
    readings={}
    for role,receipt in (('A',a),('B',b)):
        ob=verify_signed(receipt,reg,role,'monitor_observation')
        if set(ob)!={'plan_digest','window','sensor','firmware','slots'} or \
           ob['plan_digest']!=p['digest'] or ob['window']!=expected_window or \
           not isinstance(ob['slots'],list) or len(ob['slots'])!=WINDOW_SIZE:
            raise ApplicabilityError('monitor observation bound to wrong plan or missing slots')
        for i,r in enumerate(ob['slots']):
            if (not isinstance(r,dict) or set(r)!={'index','status','event_id','local_latency_ms'} or
                 type(r['index']) is not int or r['index']!=i or
                 r['status'] not in ('detected','not_detected','unavailable','refused') or
                 ((r['status']=='detected' and r['event_id']!=slots[i]['event_id']) or
                  (r['status']!='detected' and r['event_id'] is not None)) or
                 (r['status'] in ('refused','unavailable'))!=(r['local_latency_ms'] is None) or
                 (r['local_latency_ms'] is not None and (type(r['local_latency_ms']) is not int or r['local_latency_ms']<0))):
                raise ApplicabilityError('monitor slot status/identity/latency invalid')
        if not isinstance(ob['sensor'],str) or not isinstance(ob['firmware'],str):
            raise ApplicabilityError('sensor identification invalid')
        readings[role]=ob
    return {'plan':data,'readings':readings}


def assess(cert: Mapping[str,Any], reg: Mapping[str,Any], source: Mapping[str,Any],
           baseline_a: Mapping[str,Any],baseline_b: Mapping[str,Any],
           p: Mapping[str,Any],a: Mapping[str,Any],b: Mapping[str,Any],
           *, expected_window: int=1, expected_parent: str|None=None,
           assumptions_accepted: bool=False, prior_suspended: bool=False) -> dict[str,Any]:
    if type(assumptions_accepted) is not bool or type(prior_suspended) is not bool:
        raise ApplicabilityError('verifier assumption/state flags must be boolean')
    c=verify_certificate(cert,reg,source,baseline_a,baseline_b)
    m=validate_window(reg,p,a,b,expected_window=expected_window,expected_parent=expected_parent)
    slots=m['plan']['slots']; obs=m['readings']
    n_edge=sum(1 for s in slots if s['stratum']=='edge')
    distribution=n_edge/WINDOW_SIZE
    joint_miss=sum(all(obs[r]['slots'][i]['status']!='detected' for r in ('A','B'))
                   for i in range(WINDOW_SIZE))
    reasons=[]
    if expected_window not in range(c['valid_window_range'][0],c['valid_window_range'][1]+1):
        reasons.append('certificate_expired')
    if any(obs[r]['sensor']!=c['sensors'][r] or obs[r]['firmware']!=c['firmware'][r] for r in ('A','B')):
        reasons.append('sensor_configuration_changed')
    if any(s['stratum'] not in STRATA for s in slots):reasons.append('unrepresented_event_stratum')
    if distribution>c['max_edge_weight']:
        reasons.append('event_population_shift')
    if any(r['local_latency_ms'] is not None and r['local_latency_ms']>c['max_local_latency_ms']
           for role in ('A','B') for r in obs[role]['slots']):
        reasons.append('latency_envelope_exceeded')
    if joint_miss/WINDOW_SIZE>1/12:
        reasons.append('observed_joint_miss_trigger')
    # This upper bound can be recomputed for a new declared mixture, but is
    # not a transfer guarantee if the conditional response itself has shifted.
    weighted=weighted_limit(c['limits'],distribution)
    if weighted>c['max_conditional_miss']:
        reasons.append('conditional_performance_limit_exceeded')
    if prior_suspended:reasons.append('previously_suspended_requires_new_calibration')
    if not assumptions_accepted:reasons.append('statistical_and_physical_assumptions_unestablished')
    return {'schema':SCHEMA,'status':'conditionally_applicable' if not reasons else 'suspended',
            'reasons':sorted(reasons),'window':expected_window,
            'monitor_plan_digest':p['digest'],'certificate_digest':cert['digest'],
            'reported_joint_misses':joint_miss,'reported_edge_fraction':round(distribution,12),
            'hypothetical_simultaneous_95pct_upper':round(weighted,12),
            'sampling_assumptions_explicitly_accepted':assumptions_accepted,
            'physical_detection_guarantee':None,'adversarial_detection_guarantee':None,
            'source_truthfulness_verified':False,'hardware_identity_verified':False,
            'future_stationarity_established':False}


def fixture(mode: str='baseline', *, assumptions_accepted:bool=True,
            window:int=1,parent:str|None=None,**kwargs:Any) -> dict[str,Any]:
    reg=enrollment(deterministic=True)
    source,ba,bb=calibration(reg)
    cert=create_certificate(reg,source,ba,bb)
    p=plan(reg,window=window,mode=mode,parent=parent)
    a=observer(reg,p,'A',**kwargs.get('A',{}))
    b=observer(reg,p,'B',**kwargs.get('B',{}))
    r=assess(cert,reg,source,ba,bb,p,a,b,expected_window=window,
             expected_parent=parent,assumptions_accepted=assumptions_accepted)
    return {'certificate':cert,'monitor':r,'source_plan':p,'source':source,'A':a,'B':b,'registration':reg,
            'baseline_A':ba,'baseline_B':bb}


def demonstration()->dict[str,Any]:
    base=fixture()
    shift=fixture('shifted',window=2,parent=base['source_plan']['digest'])
    late=fixture('baseline',A={'late_slots':(4,)})
    replacement=fixture('baseline',A={'sensor':'fixture-A@2'})
    targeted=fixture('edge_focused',A={'miss_slots':(2,8)},B={'miss_slots':(2,8)})
    return {'schema':SCHEMA,'calibration':base['certificate']['body'],
            'baseline_window':base['monitor'],'population_shift':shift['monitor'],
            'latency_shift':late['monitor'],'sensor_replacement':replacement['monitor'],
            'targeted_common_mode':targeted['monitor'],
            'limits':['CI synthetic records do not establish IID sampling or physical truth',
                      'a signed false health report is indistinguishable from an honest report',
                      'passing windows cannot exclude unobserved out-of-support events']}

if __name__=='__main__':print(json.dumps(demonstration(),sort_keys=True,indent=2))
