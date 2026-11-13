"""RE-002: active, observer-relative response discrimination.

Exact-rational synthetic models; no real E-CPU dispatcher, VGI runtime, sensor,
or host attestation. The authorization gate is an explicit injected test input.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import combinations
from statistics import median
import json

from resonance_equivalence import Plant, recover_two_mode_recurrence, squared_distance


@dataclass(frozen=True)
class Probe:
    name: str
    port: str
    observer: str
    horizon: int
    cost: int
    authority: str | None = None


@dataclass(frozen=True)
class Hypothesis:
    name: str
    A: tuple[tuple[Q, ...], ...]
    drives: dict[str, tuple[Q, ...]]
    readouts: dict[str, tuple[Q, ...]]

    def predict(self, probe: Probe) -> tuple[Q, ...]:
        if probe.port not in self.drives or probe.observer not in self.readouts:
            raise ValueError('undeclared probe port or observer')
        if probe.horizon < 1:
            raise ValueError('positive observation horizon required')
        return tuple(Plant(self.A, self.drives[probe.port],
                           self.readouts[probe.observer]).markov(probe.horizon))


def candidates() -> dict[str, Hypothesis]:
    a = ((Q(1, 2), Q(0)), (Q(0), Q(1, 4)))
    ports = {'u': (Q(1), Q(0)), 'v': (Q(0), Q(1))}
    readouts = {'primary': (Q(1), Q(1)), 'auxiliary': (Q(0), Q(0))}
    baseline = Hypothesis('baseline', a, ports, readouts)
    alternate_third = Hypothesis('alternate_third',
        ((Q(1, 2), Q(0)), (Q(0), Q(1, 3))), ports, readouts)
    alternate_three_quarters = Hypothesis('alternate_three_quarters',
        ((Q(1, 2), Q(0)), (Q(0), Q(3, 4))), ports, readouts)
    # Extend the baseline with an actively driven, but primary-invisible mode.
    hidden = Hypothesis('hidden_extra_mode',
        ((Q(1, 2), Q(0), Q(0)),
         (Q(0), Q(1, 4), Q(0)),
         (Q(0), Q(0), Q(7, 8))),
        {'u': (Q(1), Q(0), Q(0)), 'v': (Q(0), Q(1), Q(1))},
        {'primary': (Q(1), Q(1), Q(0)), 'auxiliary': (Q(0), Q(0), Q(1))})
    # z=T x with T=[[1,1],[0,1]]: internal matrix and ports change,
    # but both declared observer responses remain exactly equal to baseline.
    alias = Hypothesis('coordinate_alias',
        ((Q(1, 2), Q(-1, 4)), (Q(0), Q(1, 4))),
        {'u': (Q(1), Q(0)), 'v': (Q(1), Q(1))},
        {'primary': (Q(1), Q(0)), 'auxiliary': (Q(0), Q(0))})
    return {h.name: h for h in (
        baseline, alternate_third, alternate_three_quarters, hidden, alias)}


def probe_catalogue() -> tuple[Probe, ...]:
    return (
        Probe('primary_u', 'u', 'primary', 4, 1),
        Probe('secondary_v', 'v', 'primary', 4, 2),
        Probe('auxiliary_v', 'v', 'auxiliary', 4, 3, 'auxiliary_read'),
    )


def partition(hypotheses: dict[str, Hypothesis], probe: Probe,
              survivors: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    outcome_groups: dict[tuple[Q, ...], list[str]] = {}
    for name in survivors:
        predicted = hypotheses[name].predict(probe)
        outcome_groups.setdefault(predicted, []).append(name)
    return tuple(sorted((tuple(sorted(names)) for names in outcome_groups.values()),
                        key=lambda group: (len(group), group)))


def choose_probe(hypotheses: dict[str, Hypothesis],
                 survivors: tuple[str, ...],
                 used: frozenset[str] = frozenset()) -> Probe | None:
    """Minimize worst surviving class; then maximize branches; then cost.

    All predictions are supplied by the finite hypothesis set, not learned
    online. This is a deterministic minimax heuristic, not a globally optimal
    adaptive decision tree nor a probability-calibrated policy.
    """
    scored = []
    for probe in probe_catalogue():
        if probe.name in used:
            continue
        classes = partition(hypotheses, probe, survivors)
        if len(classes) < 2:
            continue
        scored.append((max(map(len, classes)), -len(classes), probe.cost,
                       probe.name, probe))
    return min(scored)[-1] if scored else None


def navigate(actual: str, authorized: frozenset[str] = frozenset()) -> dict:
    """Synthetic evidence-gated active discrimination of a known candidate.

    Refusal is *not* interpreted as a measurement. Every synthetic probe is a
    fresh reset-state impulse; interventional state is never carried across
    probes. Only explicit authorization permits auxiliary measurement.
    """
    models = candidates()
    if actual not in models:
        raise ValueError('actual must be a declared synthetic candidate')
    survivors = tuple(sorted(models))
    used: set[str] = set()
    log = []
    while len(survivors) > 1:
        probe = choose_probe(models, survivors, frozenset(used))
        if probe is None:
            break
        used.add(probe.name)
        entry = {'probe': probe.name, 'before': list(survivors),
                 'predicted_partition': [list(x) for x in partition(models, probe, survivors)],
                 'stage': 'planned', 'cost_units': probe.cost}
        if probe.authority and probe.authority not in authorized:
            entry['stage'] = 'evidence_refused'
            entry['reason'] = f'missing explicit authority: {probe.authority}'
            entry['after'] = list(survivors)
            log.append(entry)
            continue
        observed = models[actual].predict(probe)
        survivors = tuple(x for x in survivors
                          if models[x].predict(probe) == observed)
        entry['stage'] = 'interpreted'
        entry['observation'] = [str(x) for x in observed]
        entry['after'] = list(survivors)
        log.append(entry)
    return {'actual_synthetic_candidate': actual,
            'status': ('singleton_within_declared_candidates' if len(survivors) == 1
                       else 'unresolved_equivalence_class'),
            'survivors': list(survivors), 'steps': log,
            'authorization_model': 'injected synthetic allow/refuse, not E-CPU admission'}


def normalized_rdm(traces: dict[str, tuple[Q, ...]]) -> dict[str, Q]:
    """Within-observer normalized squared response distances.

    Only common nonzero affine sensor gain and constant offset cancel. Probe
    pairing and sample/event alignment are assumed, not independently inferred.
    """
    keys = sorted(traces)
    if len(keys) < 2:
        raise ValueError('at least two response traces are required')
    distances = {'|'.join(pair): squared_distance(traces[pair[0]], traces[pair[1]])
                 for pair in combinations(keys, 2)}
    anchor = next((d for d in distances.values() if d), None)
    if anchor is None:
        raise ValueError('all responses identical: normalized geometry undefined')
    return {k: v/anchor for k, v in distances.items()}


def compare_event_clock_shapes(first: tuple[tuple[str, Q], ...],
                               second: tuple[tuple[str, Q], ...]) -> dict:
    """Only compare normalized intervals when paired event IDs are supplied.

    Equal interval shape is not a proof of causal handoff or synchronized clocks.
    Unknown pairing is explicitly unresolved.
    """
    if len(first) < 3 or len(second) < 3:
        return {'status': 'unresolved_insufficient_events'}
    labels_a, labels_b = [x[0] for x in first], [x[0] for x in second]
    if len(set(labels_a)) != len(labels_a) or len(set(labels_b)) != len(labels_b):
        raise ValueError('event IDs must not repeat')
    if labels_a != labels_b:
        return {'status': 'unresolved_unpaired_event_ids'}
    times_a, times_b = [x[1] for x in first], [x[1] for x in second]
    def normalized(times):
        diffs = [times[i+1]-times[i] for i in range(len(times)-1)]
        if any(d <= 0 for d in diffs):
            raise ValueError('event timestamps must increase within each clock')
        scale = median(diffs)
        return tuple(d/scale for d in diffs)
    a, b = normalized(times_a), normalized(times_b)
    return {'status': 'matched_interval_shape' if a == b else 'different_interval_shape',
            'normalized_a': [str(x) for x in a],
            'normalized_b': [str(x) for x in b],
            'causal_order_established': False}


def analyze() -> dict:
    hypotheses = candidates()
    probes = probe_catalogue()
    all_names = tuple(sorted(hypotheses))
    # First permitted input reveals which second mode is present, but cannot
    # distinguish a true internal coordinate change or primary-invisible mode.
    primary_partition = partition(hypotheses, probes[0], all_names)
    selected = choose_probe(hypotheses, all_names)
    assert selected is not None and selected.name == 'secondary_v'
    chosen_partition = partition(hypotheses, selected, all_names)
    no_authority = navigate('baseline')
    with_authority = navigate('baseline', frozenset({'auxiliary_read'}))
    hidden_with_authority = navigate('hidden_extra_mode', frozenset({'auxiliary_read'}))
    assert no_authority['survivors'] == ['baseline', 'coordinate_alias', 'hidden_extra_mode']
    assert with_authority['survivors'] == ['baseline', 'coordinate_alias']
    assert hidden_with_authority['survivors'] == ['hidden_extra_mode']
    # Under full input family u+v the baseline and its coordinate alias have
    # the same two-mode recurrence; a single-u response exposes only one mode.
    base = hypotheses['baseline']
    combined = [a+b for a,b in zip(base.predict(Probe('u','u','primary',8,1)),
                                  base.predict(Probe('v','v','primary',8,1)))]
    recurrence = recover_two_mode_recurrence(combined)
    assert recurrence == (Q(3,4), Q(-1,8))
    assert all(combined[k+2] == recurrence[0]*combined[k+1] + recurrence[1]*combined[k]
               for k in range(6))
    # RDM is an observer-relative geometry: affine calibration can be
    # factored out, while squared responses generally cannot.
    series = {p.name: base.predict(p) for p in probes[:2]}
    series['u_plus_v'] = tuple(a+b for a,b in zip(series['primary_u'], series['secondary_v']))
    d1 = normalized_rdm(series)
    d2 = normalized_rdm({k: tuple(3*y+5 for y in v) for k,v in series.items()})
    assert d1 == d2
    event_ids = ['e0','e1','e2','e3','e4']
    latent = [Q(0),Q(1),Q(4),Q(6),Q(11)]
    a = tuple(zip(event_ids, (Q(5)+2*t for t in latent)))
    b = tuple(zip(event_ids, (Q(-11)+3*t for t in latent)))
    clocks = compare_event_clock_shapes(a,b)
    assert clocks['status'] == 'matched_interval_shape'
    unpaired = compare_event_clock_shapes(a, tuple((f'not-{k}',t) for k,t in b))
    assert unpaired['status'] == 'unresolved_unpaired_event_ids'
    return {
        'experiment': 'RE-002',
        'scope': 'finite supplied rational LTI hypotheses; reset-state impulses; no noise',
        'candidate_labels': list(all_names),
        'initial_primary_partition': [list(x) for x in primary_partition],
        'minimax_first_probe': selected.name,
        'first_probe_partition': [list(x) for x in chosen_partition],
        'baseline_without_auxiliary_authority': no_authority,
        'baseline_with_auxiliary_authority': with_authority,
        'hidden_with_auxiliary_authority': hidden_with_authority,
        'recovered_combined_input_recurrence': [str(x) for x in recurrence],
        'normalized_affine_sensor_rdm_equal': d1 == d2,
        'independent_affine_clocks_with_explicit_pairing': clocks,
        'clocks_without_pairing': unpaired,
        'not_established': [
            'global generator identity outside finite candidate set',
            'inferred causal event correspondence without provenance',
            'real receiver admission, physical clocks, transport or sensor calibration',
            'general adaptive policy optimality or noisy sensor performance',
        ],
    }


if __name__ == '__main__':
    print(json.dumps(analyze(), indent=2))
