"""TCN-010: synthesize latent finite-field coordinates from relational intention.

Finite fully observed deterministic action systems only. A commuting involution
family generates (Z/2)^r; its observer quotient is encoded by r independent
characters over an ODD prime field. No unknown physical dynamics are inferred.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from heapq import heappop, heappush
import json
import math
from typing import Mapping

SCHEMA = 'ifs.relational-ground-synthesis.v1'


def _canon(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(x):
    return sha256(_canon(x).encode('utf-8')).hexdigest()


def _prime(p):
    return type(p) is int and 3 <= p <= 257 and all(p % k for k in range(2, math.isqrt(p) + 1))


class SpecificationError(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    name: str
    edges: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Host:
    name: str
    supported: tuple[str, ...]
    cost: int = 1
    families: tuple[str, ...] = ('character', 'onehot')
    max_dimension: int = 256


@dataclass(frozen=True)
class Intent:
    p: int
    states: tuple[str, ...]
    actions: tuple[Action, ...]
    outputs: tuple[tuple[str, tuple[int, ...]], ...]
    visible_channels: tuple[int, ...]
    safe_states: tuple[str, ...]
    start: str
    goal: tuple[tuple[int, int], ...]
    hosts: tuple[Host, ...]
    max_cost: int = 100
    max_group_probes: int = 1024
    switch_cost: int = 0
    enable_onehot: bool = True
    max_onehot_dimension: int = 32

    def __post_init__(self):
        if not _prime(self.p):
            raise SpecificationError('odd prime p in [3,257] required')
        n = len(self.states)
        if (not 1 <= n <= 256 or len(set(self.states)) != n or
            any(type(s) is not str or not s or len(s) > 64 for s in self.states)):
            raise SpecificationError('1..256 distinct state labels required')
        if (not 1 <= len(self.actions) <= 8 or
            len({a.name for a in self.actions}) != len(self.actions)):
            raise SpecificationError('1..8 distinct actions required')
        names = set(self.states)
        for act in self.actions:
            if (type(act.name) is not str or not act.name or
                len(act.edges) != n or
                set(x for x, _ in act.edges) != names or
                len({x for x, _ in act.edges}) != n or
                any(y not in names for _, y in act.edges)):
                raise SpecificationError('action requires complete deterministic known transitions')
        if set(s for s, _ in self.outputs) != names or len(self.outputs) != n:
            raise SpecificationError('one observable record per state required')
        channels = len(self.outputs[0][1])
        if not channels or channels > 16 or any(len(out) != channels or any(type(z) is not int or not 0 <= z < self.p for z in out) for _, out in self.outputs):
            raise SpecificationError('bounded exact integer observable channels required')
        if (len(set(self.visible_channels)) != len(self.visible_channels) or
            any(type(i) is not int or not 0 <= i < channels for i in self.visible_channels)):
            raise SpecificationError('invalid observer channel selection')
        if set(self.safe_states) - names or len(set(self.safe_states)) != len(self.safe_states) or not self.safe_states:
            raise SpecificationError('nonempty unique safe states required')
        if self.start not in self.safe_states:
            raise SpecificationError('start violates declared invariant')
        if (not self.goal or any(type(i) is not int or i not in self.visible_channels or type(value) is not int or not 0 <= value < self.p for i, value in self.goal)):
            raise SpecificationError('goal requires observed channel equality')
        if len({i for i, _ in self.goal}) != len(self.goal):
            raise SpecificationError('conflicting/duplicated goal channels')
        if not self.hosts or len({h.name for h in self.hosts}) != len(self.hosts):
            raise SpecificationError('distinct host names required')
        action_names = {a.name for a in self.actions}
        for h in self.hosts:
            if (type(h.name) is not str or not h.name or type(h.cost) is not int or h.cost <= 0 or
                len(set(h.supported)) != len(h.supported) or set(h.supported) - action_names or
                type(h.max_dimension) is not int or not 1 <= h.max_dimension <= 256 or
                not h.families or len(set(h.families)) != len(h.families) or
                set(h.families) - {'character','onehot'}):
                raise SpecificationError('invalid declared host capabilities or cost')
        if (any(type(v) is not int or v < 0 for v in (self.max_cost, self.switch_cost)) or
            type(self.max_group_probes) is not int or self.max_group_probes < 1):
            raise SpecificationError('invalid finite budgets')
        if type(self.enable_onehot) is not bool or type(self.max_onehot_dimension) is not int or not 1 <= self.max_onehot_dimension <= 64:
            raise SpecificationError('invalid finite fallback representation cap')

    def record(self):
        return json.loads(_canon(asdict(self)))


def _model(spec: Intent):
    states = spec.states
    edges = {a.name: dict(a.edges) for a in spec.actions}
    outputs = dict(spec.outputs)
    safe = set(spec.safe_states)
    # Like VGI observer quotients: distinguish only by selected observation
    # channels, requested actions, and declared safety. Full transition evidence
    # is mandatory; unlike VGI partial observations, UNKNOWN is not admitted.
    fingerprint = {s: (s in safe, tuple(outputs[s][i] for i in spec.visible_channels)) for s in states}
    blocks = []
    for sig in sorted(set(fingerprint.values())):
        blocks.append(tuple(s for s in states if fingerprint[s] == sig))
    rounds = 0
    while True:
        index = {s: j for j, block in enumerate(blocks) for s in block}
        refined = {}
        for s in states:
            sig = (index[s], tuple(index[edges[a.name][s]] for a in spec.actions))
            refined.setdefault(sig, []).append(s)
        new = [tuple(group) for _, group in sorted(refined.items(), key=lambda item: states.index(item[1][0]))]
        if new == blocks:
            break
        blocks = new
        rounds += 1
        if rounds > len(states):
            raise ArithmeticError('quotient refinement did not converge')
    index = {s: j for j, block in enumerate(blocks) for s in block}
    transitions = []
    for a in spec.actions:
        permutation = tuple(index[edges[a.name][block[0]]] for block in blocks)
        if any(index[edges[a.name][s]] != permutation[j] for j, b in enumerate(blocks) for s in b):
            raise ArithmeticError('quotient action not well defined')
        transitions.append(permutation)
    return blocks, index, transitions, outputs, rounds


def _obstruction(spec: Intent, transitions):
    n = len(transitions[0])
    for name, perm in zip((a.name for a in spec.actions), transitions):
        if len(set(perm)) != n:
            return {'kind': 'nonpermutation', 'action': name, 'targets': list(perm)}
        for j in range(n):
            if perm[perm[j]] != j:
                return {'kind': 'not_involution', 'action': name, 'class': j,
                        'twice': perm[perm[j]]}
    for i, left in enumerate(transitions):
        for j, right in enumerate(transitions[:i]):
            for x in range(n):
                if left[right[x]] != right[left[x]]:
                    return {'kind': 'noncommuting', 'actions': [spec.actions[j].name, spec.actions[i].name],
                            'class': x, 'first_then_second': left[right[x]],
                            'second_then_first': right[left[x]]}
    return None


def _coordinates(start: int, transforms):
    """Discover independent generators by subgroup doubling, not name hints."""
    seen = {start: 0}
    independent = []
    for index, perm in enumerate(transforms):
        if perm[start] in seen:
            continue
        bit = len(independent)
        snapshot = tuple(seen.items())
        for state, code in snapshot:
            target = perm[state]
            if target in seen:
                raise ArithmeticError('invalid abelian doubling')
            seen[target] = code | (1 << bit)
        independent.append(index)
    deltas = [seen[perm[start]] for perm in transforms]
    for perm, delta in zip(transforms, deltas):
        for state, code in seen.items():
            if perm[state] not in seen or seen[perm[state]] != code ^ delta:
                raise ArithmeticError('character encoding does not reconstruct permutation')
    return seen, tuple(independent), tuple(deltas)


def _walsh(values, p):
    """Normalized Walsh coefficients over odd F_p: complete multilinear readout."""
    a = [v % p for v in values]
    n = len(a)
    step = 1
    while step < n:
        for i in range(0, n, step * 2):
            for j in range(i, i + step):
                u, v = a[j], a[j + step]
                a[j], a[j + step] = (u + v) % p, (u - v) % p
        step *= 2
    inv = pow(n, -1, p)
    return tuple(x * inv % p for x in a)


def _eval_readout(coefs, signs, p):
    total = 0
    for mask, coefficient in enumerate(coefs):
        term = coefficient
        for i, sign in enumerate(signs):
            if mask & (1 << i):
                term = term * sign % p
        total += term
    return total % p


def _shortest(spec, blocks, codes, transforms, observed, *, use_hosts, family='character', dimension=0):
    safe = set(spec.safe_states)
    start_class = next(j for j, b in enumerate(blocks) if spec.start in b)
    targets = dict(spec.goal)
    finals = {j for j, b in enumerate(blocks) if
              all(observed[b[0]][channel] == value for channel, value in targets.items())}
    start = (start_class, '')
    q = [(0, 0, (), (), start_class, '')]
    best = {start: (0, 0, (), ())}
    while q:
        cost, steps, anames, hnames, x, last = heappop(q)
        if best.get((x, last)) != (cost, steps, anames, hnames):
            continue
        if x in finals:
            seq = [start_class]
            state = start_class
            for name in anames:
                i = next(i for i, a in enumerate(spec.actions) if a.name == name)
                state = transforms[i][state]
                seq.append(state)
            return {'cost': cost, 'actions': list(anames), 'hosts': list(hnames),
                    'classes': seq, 'states': [blocks[z][0] for z in seq]}
        for i, act in enumerate(spec.actions):
            nxt = transforms[i][x]
            if not all(s in safe for s in blocks[nxt]):
                continue  # synthesized guard forbids invariant-breaking actuation
            hosts = [h for h in spec.hosts if act.name in h.supported
                     and family in h.families and dimension <= h.max_dimension] if use_hosts else (Host('mathematical', (act.name,), 1),)
            for host in hosts:
                charge = host.cost + (spec.switch_cost if last and host.name != last else 0)
                new = (cost + charge, steps + 1, anames + (act.name,), hnames + (host.name,))
                key = (nxt, host.name)
                if key not in best or new < best[key]:
                    best[key] = new
                    heappush(q, (*new, nxt, host.name))
    return None


def _synthesize_character(spec: Intent):
    if not isinstance(spec, Intent):
        raise SpecificationError('typed Intent required')
    blocks, index, transforms, observed, rounds = _model(spec)
    basic = {'schema': SCHEMA, 'observed_classes': len(blocks),
             'quotient': [list(b) for b in blocks], 'refinement_rounds': rounds}
    err = _obstruction(spec, transforms)
    if err is not None:
        return {**basic, 'status': 'unsupported_action_algebra', 'witness': err,
                'scope': 'only commuting involutive action/odd-field affine-character family'}
    probes = 1 << len(transforms)
    if probes > spec.max_group_probes:
        return {**basic, 'status': 'refused_search_budget', 'required_group_probes': probes,
                'budget': spec.max_group_probes, 'scope': 'incomplete symmetry enumeration; not unreachable'}
    source = index[spec.start]
    codes, independent, deltas = _coordinates(source, transforms)
    if len(codes) != len(blocks):
        return {**basic, 'status': 'unsupported_nontransitive_orbit',
                'witness': {'orbit_classes': sorted(codes), 'all_classes': len(blocks)},
                'scope': 'single-transitive-orbit family only'}
    r = len(independent)
    if len(blocks) != (1 << r):
        raise ArithmeticError('group dimension does not match orbit')
    p = spec.p
    dims = max(1, r)  # VGI FiniteSpace requires at least one coordinate
    signs = {j: tuple((p - 1 if (code >> i) & 1 else 1) for i in range(r)) or (1,)
             for j, code in codes.items()}
    diagonals = [tuple((p - 1 if (delta >> i) & 1 else 1) for i in range(r)) or (1,)
                 for delta in deltas]
    for i, perm in enumerate(transforms):
        for j in range(len(blocks)):
            if tuple(signs[j][k] * diagonals[i][k] % p for k in range(dims)) != signs[perm[j]]:
                raise ArithmeticError('exact affine transition verification failed')
    channel_count = len(spec.outputs[0][1])
    polynomial_readouts = []
    for channel in range(channel_count):
        if channel not in spec.visible_channels:
            polynomial_readouts.append(None)  # unselected outputs are NOT inferable from a quotient
            continue
        observed_values = [0] * (1 << r)
        for j, code in codes.items():
            observed_values[code] = observed[blocks[j][0]][channel]
        coeffs = _walsh(observed_values, p)
        for j, code in codes.items():
            if _eval_readout(coeffs, signs[j][:r], p) != observed_values[code] % p:
                raise ArithmeticError('readout interpolation lost exactness')
        polynomial_readouts.append(list(coeffs))
    guarded = []
    safe = set(spec.safe_states)
    for i, act in enumerate(spec.actions):
        guarded.append({'action': act.name, 'allowed_classes':
                        [j for j, b in enumerate(blocks) if all(s in safe for s in b)
                         and all(s in safe for s in blocks[transforms[i][j]] )]})
    constructed = {**basic,
        'family': 'character', 'status': 'constructed', 'field_modulus': p,
        'independent_generator_actions': [spec.actions[i].name for i in independent],
        'latent_bits': r, 'affine_dimension': dims,
        'group_elements_constructed': len(codes), 'group_probe_admission_envelope': probes,
        'affine_lower_bound': r, 'character_coordinates': [list(signs[j]) for j in range(len(blocks))],
        'class_codes': [codes[j] for j in range(len(blocks))],
        'operator_diagonals': {a.name: list(v) for a, v in zip(spec.actions, diagonals)},
        'observable_polynomials': polynomial_readouts,
        'observable_scope': {'selected_channels': list(spec.visible_channels),
                             'unselected_channels': [i for i in range(channel_count) if i not in spec.visible_channels]},
        'representation_cost': {'stored_operator_entries':len(spec.actions)*dims,
                                'stored_state_coordinates':len(blocks)*dims},
        'vgi_space': {'frame': 'ifs.tcn010.character', 'dimension': dims,
                      'ring': 'Z/modulus Z', 'modulus': p},
        'safety_guards': guarded,
        'operator_scope': 'exact diagonal finite-field affine maps on synthesized character state space',
        'minimality_scope': 'faithful affine representations of this observer quotient over odd characteristic',
        'external_realization_witnessed': False, 'authenticated_hosts': False,
    }
    abstract_path = _shortest(spec, blocks, codes, transforms, observed, use_hosts=False)
    if abstract_path is None:
        return {**constructed, 'status': 'unreachable_under_safety_guards',
                'witness': {'goal': [list(g) for g in spec.goal],
                            'reason': 'exhaustive guarded quotient graph contains no goal'}}
    hosted = _shortest(spec, blocks, codes, transforms, observed, use_hosts=True, family='character', dimension=dims)
    if hosted is None:
        return {**constructed, 'status': 'unreachable_with_declared_hosts',
                'witness': {'mathematical_plan': abstract_path,
                            'reason': 'no admissible hosted path; not a mathematical impossibility'}}
    if hosted['cost'] > spec.max_cost:
        return {**constructed, 'status': 'refused_execution_budget',
                'witness': {'least_cost': hosted['cost'], 'budget': spec.max_cost}}
    # Independently replay the selected plan through character diagonals.
    z = signs[source]
    for name in hosted['actions']:
        diag = constructed['operator_diagonals'][name]
        z = tuple(a * b % p for a, b in zip(z, diag))
    final_class = hosted['classes'][-1]
    if z != signs[final_class]:
        raise ArithmeticError('latent plan does not reproduce abstract goal')
    if not all(_eval_readout(polynomial_readouts[k], z[:r], p) == v % p for k, v in spec.goal):
        raise ArithmeticError('synthesized observer did not satisfy intention')
    return {**constructed, 'status': 'realizable', 'plan': hosted,
            'terminal_character_state': list(z),
            'goal_readout': {str(k): _eval_readout(polynomial_readouts[k], z[:r], p)
                             for k, _ in spec.goal},
            'scope': 'exact declared finite-graph mathematical construction; host identity and physical execution unverified'}




def _synthesize_onehot(spec: Intent):
    """Exact generic deterministic finite-map Ground, even if actions don't commute.

    This is a declared larger operator algebra; NO minimality guarantee. Each
    abstract quotient class has a basis vector, each action a one-hot-column
    map. The cost of storing its complete operators is O(actions * states^2).
    """
    blocks, index, transforms, observed, rounds = _model(spec)
    n, p = len(blocks), spec.p
    if n > spec.max_onehot_dimension:
        return {'status':'refused_representation_budget', 'family':'onehot',
                'required_dimension':n, 'cap':spec.max_onehot_dimension,
                'scope':'no one-hot construction attempted beyond declared dimension cap'}
    coord = [tuple(int(i == j) for i in range(n)) for j in range(n)]
    matrices = {}
    for op, perm in zip(spec.actions,transforms):
        matrix = [[0]*n for _ in range(n)]
        for j, dst in enumerate(perm):
            matrix[dst][j] = 1
        matrices[op.name] = matrix
    channel_count = len(spec.outputs[0][1])
    readouts = []
    for channel in range(channel_count):
        if channel not in spec.visible_channels:
            readouts.append(None)
        else:
            readouts.append([observed[block[0]][channel] for block in blocks])
    safe = set(spec.safe_states)
    guards = []
    for op, perm in zip(spec.actions, transforms):
        guards.append({'action': op.name, 'allowed_classes':
                       [j for j, block in enumerate(blocks) if all(s in safe for s in block)
                        and all(s in safe for s in blocks[perm[j]] )]})
    constructed = {'schema':SCHEMA, 'family':'onehot', 'status':'constructed',
        'observed_classes':n, 'quotient':[list(b) for b in blocks], 'refinement_rounds':rounds,
        'field_modulus':p, 'affine_dimension':n, 'latent_bits':None,
        'affine_lower_bound':None,
        'coordinates':[list(v) for v in coord],
        'operator_matrices':matrices,
        'observable_readouts':readouts,
        'observable_scope':{'selected_channels':list(spec.visible_channels),
                            'unselected_channels':[i for i in range(channel_count) if i not in spec.visible_channels]},
        'safety_guards':guards,
        'vgi_space':{'frame':'ifs.tcn010.onehot', 'dimension':n,
                      'ring':'Z/modulus Z', 'modulus':p},
        'representation_cost':{'stored_operator_entries':len(spec.actions)*n*n,
                               'stored_state_coordinates':n*n},
        'operator_scope':'exact finite functional maps over one-hot basis, not necessarily invertible',
        'minimality_scope':'NO dimension optimality claimed for generic one-hot fallback',
        'external_realization_witnessed':False, 'authenticated_hosts':False}
    abstract = _shortest(spec, blocks, None, transforms, observed, use_hosts=False,
                         family='onehot',dimension=n)
    if abstract is None:
        return {**constructed, 'status':'unreachable_under_safety_guards',
                'witness':{'reason':'complete guarded quotient graph contains no target'}}
    hosted = _shortest(spec, blocks, None, transforms, observed, use_hosts=True,
                       family='onehot',dimension=n)
    if hosted is None:
        return {**constructed, 'status':'unreachable_with_declared_hosts',
                'witness':{'mathematical_plan':abstract,
                            'reason':'no available one-hot host realizes a guarded goal path'}}
    if hosted['cost'] > spec.max_cost:
        return {**constructed, 'status':'refused_execution_budget',
                'witness':{'least_cost':hosted['cost'], 'budget':spec.max_cost}}
    # Direct independent matrix-vector reference; no diagonal shortcuts used.
    vector = list(coord[index[spec.start]])
    for name in hosted['actions']:
        matrix = matrices[name]
        vector = [sum(a*x for a,x in zip(row,vector)) % p for row in matrix]
    destination = hosted['classes'][-1]
    if vector != list(coord[destination]):
        raise ArithmeticError('onehot program did not reconstruct desired state')
    for channel, expected in spec.goal:
        if sum(a*x for a,x in zip(readouts[channel],vector)) % p != expected:
            raise ArithmeticError('onehot observer readout failed goal')
    return {**constructed, 'status':'realizable','plan':hosted,
            'terminal_vector':vector,
            'goal_readout':{str(c):sum(a*x for a,x in zip(readouts[c],vector))%p
                            for c,_ in spec.goal},
            'scope':'exact finite deterministic mathematical model; onehot expansion not minimal; hosts unauthenticated'}


def synthesize(spec: Intent):
    """Select feasible Grounds by declared execution cost, then representation size.

    Character family is attempted first; one-hot is an explicitly budgeted
    fallback. If one family cannot be evaluated, no global optimality is claimed.
    """
    if not isinstance(spec, Intent):
        raise SpecificationError('typed Intent required')
    character = _synthesize_character(spec)
    if not spec.enable_onehot:
        return character
    onehot = _synthesize_onehot(spec)
    possibilities = [r for r in (character, onehot) if r.get('status')=='realizable']
    if possibilities:
        chosen = min(possibilities, key=lambda r:
                     (r['plan']['cost'], r['affine_dimension'],
                      r['representation_cost']['stored_operator_entries'],r['family']))
        return {**chosen, 'selection':{
            'criterion':'declared execution cost, then dimension, then operator entries',
            'considered':[
                {'family':r.get('family','character'), 'status':r['status'],
                 'cost':r.get('plan',{}).get('cost'),
                 'dimension':r.get('affine_dimension')}
                for r in (character,onehot)],
            'global_optimality':False,
            'scope':'only two declared candidate algebras and bounded construction'}}
    # Preserve meaningful mathematical refusals, not an apparent universal no.
    priority = {'refused_execution_budget':0,'unreachable_with_declared_hosts':1,
                'unreachable_under_safety_guards':2,
                'refused_search_budget':3,'refused_representation_budget':4,
                'unsupported_action_algebra':5,'unsupported_nontransitive_orbit':6}
    chosen = min((character,onehot),key=lambda r:priority.get(r['status'],10))
    return {**chosen, 'selection':{'considered':[
        {'family':r.get('family','character'), 'status':r['status']}
        for r in (character,onehot)],
        'global_optimality':False,
        'scope':'failure/refusal is relative to declared operators, hosts and budgets'}}


def receipt(spec: Intent):
    base = {'schema': SCHEMA, 'intention': spec.record(), 'result': synthesize(spec)}
    return {**base, 'sha256': _digest(base)}


def verify_receipt(spec: Intent, claim: Mapping):
    """Reject retagged/tampered models by recomputing synthesis and digest.

    SHA-256 of unkeyed JSON checks integrity, not source authentication.
    """
    if not isinstance(claim, Mapping) or set(claim) != {'schema', 'intention', 'result', 'sha256'}:
        return False
    try:
        base = {k: claim[k] for k in ('schema', 'intention', 'result')}
        return (claim['schema'] == SCHEMA and
                claim['intention'] == spec.record() and
                claim['sha256'] == _digest(base) and
                claim['result'] == synthesize(spec))
    except (ValueError, TypeError, ArithmeticError, KeyError):
        return False


def render_terminal_phase(spec: Intent, result: Mapping, phase_hosts, *, max_cost=100):
    """Reuse TCN-008 to construct a witnessed synthetic phase readout.

    This reuses the existing intention_ground implementation in the same repo.
    A supplied observer convention makes the selected goal value the slope.
    """
    if result.get('status') != 'realizable' or spec.p < 7:
        raise SpecificationError('phase rendering requires realized p>=7 Ground')
    from intention_ground import make_intent, make_receipt, synthesize as phase_synthesize, verify_receipt as phase_verify
    k = spec.goal[0][0]
    slope = result['goal_readout'][str(k)]
    phases = tuple((slope * y + y**3) % spec.p for y in range(spec.p))
    phase_intent = make_intent(spec.p, phases, max_cost=max_cost)
    hosts = tuple(phase_hosts)
    artifact = make_receipt(phase_intent, hosts)
    if not phase_verify(artifact):
        raise ArithmeticError('TCN-008 independent mathematical receipt failed')
    plan = phase_synthesize(phase_intent, hosts)
    return {'status': plan['status'], 'phase_receipt': artifact,
            'relative_phase_slope': slope,
            'terminal_class': result['plan']['classes'][-1],
            'scope': 'observer-chosen TCN-008 polynomial phase readout, not physical host observation'}


def materialize_vgi_typed_maps(result: Mapping):
    """Optional *actual* VGI interoperability; requires vgi installed on PYTHONPATH.

    Delegates schema/type validation to VGI's native FiniteSpace and DenseMap.
    No observation admission, host authentication, or VM execution is implied.
    """
    if result.get('status') not in {
            'constructed', 'realizable', 'refused_execution_budget',
            'unreachable_with_declared_hosts', 'unreachable_under_safety_guards'}:
        raise SpecificationError('no synthesized affine ground to export')
    from vgi.typed_operator_navigation import FiniteSpace, DenseMap
    p = result['field_modulus']
    d = result['affine_dimension']
    space = FiniteSpace(result['vgi_space']['frame'], d, p)
    maps = {}
    if result['family'] == 'character':
        for name, diag in result['operator_diagonals'].items():
            rows = tuple(tuple((diag[i] if i == j else 0) for j in range(d)) for i in range(d))
            maps[name] = DenseMap(name, space, space, rows)
    else:
        for name, rows in result['operator_matrices'].items():
            maps[name] = DenseMap(name, space, space, tuple(tuple(row) for row in rows))
    return space, maps


def navigate_action_counts(spec: Intent, result: Mapping, counts: Mapping[str, int]):
    """Jump by arbitrarily large grouped action counts in a commuting Ground.

    Requires every requested action to preserve the declared safe set globally.
    Otherwise reordering/skipping intermediate states could hide a guard failure,
    and navigation explicitly refuses. This is mathematical observer-quotient
    evaluation: no external action or authenticated host executes here.
    """
    if result.get('status') != 'realizable' or result.get('family') != 'character':
        raise SpecificationError('count navigation requires a realized character Ground')
    if not isinstance(counts, Mapping) or any(
            action not in result['operator_diagonals'] or type(steps) is not int or steps < 0
            for action, steps in counts.items()):
        raise SpecificationError('nonnegative integer counts for declared actions required')
    safe_classes = {j for j, b in enumerate(result['quotient'])
                    if all(s in spec.safe_states for s in b)}
    guards = {a['action']:set(a['allowed_classes']) for a in result['safety_guards']}
    for name, steps in counts.items():
        if steps and not safe_classes.issubset(guards[name]):
            raise SpecificationError('unsafe grouped navigation would bypass per-step guards')
    start = next(i for i, b in enumerate(result['quotient']) if spec.start in b)
    vector = list(result['character_coordinates'][start])
    p = spec.p
    products = 0
    for name, steps in sorted(counts.items()):
        if steps % 2:
            vector = [v * d % p for v, d in zip(vector, result['operator_diagonals'][name])]
            products += len(vector)
    destination = next(j for j, z in enumerate(result['character_coordinates']) if z == vector)
    outputs = {str(k):_eval_readout(result['observable_polynomials'][k],vector[:result['latent_bits']],p)
               for k in spec.visible_channels}
    return {'state_class':destination, 'observer_state':result['quotient'][destination][0],
            'state_vector':vector, 'observed_outputs':outputs,
            'total_logical_steps_decimal':str(sum(counts.values())),
            'modular_products':products, 'goal_satisfied':all(outputs[str(k)]==v for k,v in spec.goal),
            'scope':'conditional action-count quotient navigation only; no external execution'}
