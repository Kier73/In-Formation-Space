"""Deterministic TCN-010 benchmark and falsification receipts; Python standard library."""
import json
import time
from itertools import product
from relational_ground import (Action, Host, Intent, synthesize, receipt,
                               verify_receipt, navigate_action_counts)


def cube(bits=2, *, visible=None, safety=None, extra=None, p=7):
    states=tuple('s'+''.join(map(str,v)) for v in product((0,1),repeat=bits))
    bits_by_state={s:tuple(map(int,s[1:])) for s in states}
    encoded={s:sum(bit<<i for i,bit in enumerate(bits_by_state[s])) for s in states}
    by_code={v:k for k,v in encoded.items()}
    masks={f'flip_{i}':1<<i for i in range(bits)}
    if extra:
        masks.update(extra)
    actions=tuple(Action(name,tuple((s,by_code[encoded[s]^mask]) for s in states))
                  for name,mask in masks.items())
    outputs=tuple((s,bits_by_state[s]+(sum(bits_by_state[s])%2,)) for s in states)
    safe=states if safety is None else tuple(s for s in states if safety(bits_by_state[s]))
    return Intent(p,states,actions,outputs,visible if visible is not None else tuple(range(bits)),
                  safe,states[0],tuple((i,1) for i in range(bits)),
                  (Host('declared-tables',tuple(masks),1),),max_group_probes=256)


def noncommuting():
    states=('alpha','beta','gamma')
    a=Action('swap_ab',(('alpha','beta'),('beta','alpha'),('gamma','gamma')))
    b=Action('swap_bg',(('alpha','alpha'),('beta','gamma'),('gamma','beta')))
    return Intent(7,states,(a,b),tuple((s,(i,)) for i,s in enumerate(states)),
                  (0,),states,'alpha',((0,2),),(Host('general-matrix',('swap_ab','swap_bg'),1),))


def summarize(result):
    return {k:result.get(k) for k in ('status','family','observed_classes','latent_bits','affine_dimension',
                                      'representation_cost','goal_readout','witness') if k in result} | {
        'plan':result.get('plan'), 'selection':result.get('selection')}


def run():
    t=time.perf_counter()
    small=cube(2,extra={'flip_both':3})
    x=synthesize(small)
    dt=time.perf_counter()-t
    safe=cube(2,extra={'flip_both':3},safety=lambda b:b[0]==b[1])
    safe_plan=synthesize(safe)
    full=cube(3,p=11)
    first=Intent(**{**full.__dict__,'visible_channels':(0,), 'goal':((0,1),)})
    parity=Intent(**{**full.__dict__,'visible_channels':(3,), 'goal':((3,1),)})
    non=noncommuting()
    large=cube(8,p=11)
    start=time.perf_counter()
    large_model=synthesize(large)
    large_dt=time.perf_counter()-start
    hop=navigate_action_counts(small,x,{'flip_0':10**100+1,'flip_1':10**100+1})
    return {'experiment':'TCN-010',
      'premise':'fully specified deterministic finite transition table; observer projection; odd-prime algebra',
      'four_state':summarize(x),
      'four_state_trivial_scalar_capacity':bool(len(small.states)<=small.p),
      'quadratic_character_lower_bound':2,
      'guarded':summarize(safe_plan),
      'observer_full_three_bit':summarize(synthesize(full)),
      'observer_one_bit':summarize(synthesize(first)),
      'observer_parity':summarize(synthesize(parity)),
      'noncommuting_fallback':summarize(synthesize(non)),
      'noncommuting_without_fallback':summarize(synthesize(Intent(**{**non.__dict__,'enable_onehot':False}))),
      'eight_bit_256_states':summarize(large_model),
      'long_action_count':hop,
      'receipt_reconstructed':verify_receipt(small,receipt(small)),
      'local_timing_ms':{'four_state_synthesis':round(1000*dt,4),
                         '256_state_synthesis':round(1000*large_dt,4)},
      'cost_context':'one local Python interpreter, end-to-end synthesis; not a universal speed benchmark',
      'authority':'declared synthetic hosts, no live E-CPU/VGI execution or external observation'}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
