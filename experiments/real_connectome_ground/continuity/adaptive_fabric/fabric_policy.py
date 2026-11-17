"""RCG-003: train a path-cost predictor for synthetic observer-host workloads.

'Body' means E-CPU's replaceable communication/observer fabric. 'Mind' means
source-bound procedural Grounds and trained policy decisions. This trainer uses
SYNTHETIC TELEMETRY, not an actual mTLS/Transit trace or biological responses.

No new transport, Hypervisor, memory authority, or scheduler is implemented.
Every selected realization is checked through RCG-001's existing Ground oracle.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import random
from typing import Any, Mapping, Sequence

from connectome_ground import ConnectomeGround, Query, canonical, sha, value_text

SCHEMA = 'ifs.rcg003.fabric-adaptation.v1'
COST_KIND = 'synthetic-duration-ticks-not-observed-time'
FEATURES = ('bias', 'stage_edge_visits', 'transmitted_256B_units', 'observed_queue_units')


class FabricRefused(ValueError):
    """A proposed fabric observation cannot be admitted under the stated model."""


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def exact_int(v: object, name: str, lo: int = 0, hi: int = 10_000_000) -> int:
    if type(v) is not int or not lo <= v <= hi:
        raise FabricRefused(f'{name} must be an integer in [{lo}, {hi}]')
    return v


@dataclass(frozen=True)
class HostPath:
    """An observed scheduling candidate, NOT an assertion of network authority."""
    host: str
    medium: str
    method: str
    available: bool = True
    permitted: bool = True
    framing_units: int = 0

    def __post_init__(self) -> None:
        if self.host not in ('local-worker', 'transit-worker', 'artifact-worker') or \
                self.medium not in ('local-ipc', 'modeled-tls', 'modeled-github-job') or \
                self.method not in ('cone', 'full') or type(self.available) is not bool or \
                type(self.permitted) is not bool or type(self.framing_units) is not int or \
                not 0 <= self.framing_units <= 1000:
            raise FabricRefused('unrecognized host, execution mode, or capability state')
        medium = {'local-worker': 'local-ipc', 'transit-worker': 'modeled-tls',
                  'artifact-worker': 'modeled-github-job'}[self.host]
        if medium != self.medium:
            raise FabricRefused('host path disagrees with its declared medium')

    @property
    def key(self) -> str:
        return self.host + '/' + self.method

    def to_dict(self) -> dict[str, object]:
        return {'host': self.host, 'medium': self.medium, 'method': self.method,
                'available': self.available, 'permitted': self.permitted,
                'framing_units': self.framing_units}


@dataclass(frozen=True)
class Workload:
    """Features derived from an *exact* original-source connectome intention."""
    ground: str
    request: dict[str, Any]
    plan_digest: str
    cone_edges: int
    full_edges: int
    cone_payload_bytes: int
    full_payload_bytes: int

    @classmethod
    def from_ground(cls, ground: ConnectomeGround, query: Query) -> 'Workload':
        plan = ground.plan(query)
        # The cone plan is sent to the receiver. The whole method only needs
        # query identity, because the receiver has its own pinned original source.
        cone_payload = len(canonical(plan))
        full_payload = len(canonical({'query': query.encode(), 'ground': ground.fingerprint}))
        return cls(ground.fingerprint, query.encode(), plan['digest'],
                   len(plan['layered_edges']),
                   query.steps * sum(e.kind == query.kind for e in ground.edges),
                   cone_payload, full_payload)

    def describe(self) -> dict[str, Any]:
        return {'ground': self.ground, 'query': self.request, 'plan_digest': self.plan_digest,
                'cone_edges': self.cone_edges, 'full_edges': self.full_edges,
                'cone_payload_bytes': self.cone_payload_bytes,
                'full_payload_bytes': self.full_payload_bytes}

    def feature(self, path: HostPath, queue: int) -> tuple[int, int, int, int]:
        exact_int(queue, 'queue', 0, 1000)
        count = self.cone_edges if path.method == 'cone' else self.full_edges
        byte_count = self.cone_payload_bytes if path.method == 'cone' else self.full_payload_bytes
        return (1, count, (byte_count + 255) // 256 + path.framing_units, queue)


# Hidden synthetic environment parameters. These are labels for a controlled
# regression experiment, NOT user-accessible facts about real hosts/networks.
_SYNTHETIC_COST = {
    'local-worker/cone': (20, Fraction(9, 2), 0, 2),
    'local-worker/full': (20, Fraction(9, 2), 0, 2),
    'transit-worker/cone': (115, Fraction(3, 2), 3, 1),
    'transit-worker/full': (115, Fraction(3, 2), 3, 1),
    'artifact-worker/cone': (390, Fraction(3, 4), 6, 1),
    'artifact-worker/full': (390, Fraction(3, 4), 6, 1),
}


def candidates() -> tuple[HostPath, ...]:
    return tuple(HostPath(host, medium, method)
                 for host, medium in (('local-worker', 'local-ipc'),
                                      ('transit-worker', 'modeled-tls'),
                                      ('artifact-worker', 'modeled-github-job'))
                 for method in ('cone', 'full'))


def observe_synthetic_latency(path: HostPath, features: Sequence[int]) -> Fraction:
    if not path.permitted or not path.available:
        raise FabricRefused('host capability unavailable or not granted')
    if len(features) != 4 or any(type(v) is not int or v < 0 for v in features):
        raise FabricRefused('invalid measured feature vector')
    return sum((Fraction(c) * v for c, v in zip(_SYNTHETIC_COST[path.key], features)),
               Fraction(0))


def observation(ground: ConnectomeGround, workload: Workload, path: HostPath,
                queue: int) -> dict[str, Any]:
    if workload.ground != ground.fingerprint or Workload.from_ground(
            ground, Query(**workload.request)) != workload:
        raise FabricRefused('workload identity not admitted by original Ground')
    features = workload.feature(path, queue)
    measured = observe_synthetic_latency(path, features)
    body = {'schema': SCHEMA + '.synthetic-telemetry.v1',
            'ground': ground.fingerprint, 'task': sha(workload.describe()),
            'path': path.to_dict(), 'feature_names': list(FEATURES),
            'features': list(features), 'duration': value_text(measured),
            'status': COST_KIND}
    return {**body, 'digest': canonical_hash(body)}


def verify_observation(ground: ConnectomeGround, workload: Workload,
                       receipt: Mapping[str, Any]) -> None:
    if type(receipt) is not dict or type(receipt.get('path')) is not dict:
        raise FabricRefused('malformed telemetry receipt')
    try:
        route = HostPath(**receipt['path'])
        observed = observation(ground, workload, route, receipt['features'][3])
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise FabricRefused('cannot reconstruct synthetic cost observation') from exc
    if canonical(dict(receipt)) != canonical(observed):
        raise FabricRefused('synthetic telemetry differs from independently reconstructed source law')


def solve_exact(features: Sequence[Sequence[int]], values: Sequence[Fraction]) -> tuple[Fraction, ...]:
    """Train an exact linear estimator using rank-checked normal equations.

    Coefficients are fitted from synthetic observations, not copied from hidden
    simulator constants. This is system identification, not a trained LLM.
    """
    dim = len(FEATURES)
    if len(features) != len(values) or len(features) < dim:
        raise FabricRefused('insufficient training measurements')
    if any(len(f) != dim for f in features):
        raise FabricRefused('incorrect observation feature dimension')
    augmented = []
    for i in range(dim):
        row = [sum((Fraction(f[i]) * f[j] for f in features), Fraction(0))
               for j in range(dim)]
        rhs = sum((Fraction(f[i]) * y for f, y in zip(features, values)), Fraction(0))
        augmented.append(row + [rhs])
    for c in range(dim):
        pivot = next((r for r in range(c, dim) if augmented[r][c]), None)
        if pivot is None:
            raise FabricRefused('unidentifiable host law: synthetic dataset is rank deficient')
        augmented[c], augmented[pivot] = augmented[pivot], augmented[c]
        val = augmented[c][c]
        augmented[c] = [v / val for v in augmented[c]]
        for r in range(dim):
            if r != c:
                val = augmented[r][c]
                augmented[r] = [v - val * y for v, y in zip(augmented[r], augmented[c])]
    return tuple(row[-1] for row in augmented)


def fit(ground: ConnectomeGround, items: Sequence[tuple[Workload, dict[str, Any]]]) -> dict[str, Any]:
    """Fit one measured cost model per host/method after receiver-owned validation."""
    by_route = {candidate.key: ([], []) for candidate in candidates()}
    pins = []
    for workload, record in items:
        verify_observation(ground, workload, record)
        path = HostPath(**record['path'])
        f, y = by_route[path.key]
        f.append(record['features'])
        y.append(Fraction(record['duration']))
        pins.append(record['digest'])
    coefficients = {name: [value_text(v) for v in solve_exact(*groups)]
                    for name, groups in sorted(by_route.items())}
    body = {'schema': SCHEMA + '.model.v1', 'ground': ground.fingerprint,
            'training_type': 'exact-linear-regression-on-synthetic-fabric-telemetry',
            'source_observation_hashes': pins, 'coefficients': coefficients,
            'feature_names': list(FEATURES),
            'not': 'not-real-transport-benchmark-or-learnt-neural-weights'}
    return {**body, 'digest': canonical_hash(body)}


def predict(model: Mapping[str, Any], ground: ConnectomeGround,
            workload: Workload, path: HostPath, queue: int) -> Fraction:
    if type(model) is not dict or model.get('ground') != ground.fingerprint or \
            model.get('schema') != SCHEMA + '.model.v1' or \
            canonical_hash({k: v for k, v in model.items() if k != 'digest'}) != model.get('digest'):
        raise FabricRefused('untrusted trained model or mismatched Ground')
    if not path.available or not path.permitted:
        raise FabricRefused('no local authority to select this path')
    values = model.get('coefficients', {}).get(path.key)
    if type(values) is not list or len(values) != len(FEATURES):
        raise FabricRefused('no learned cost law for this path')
    try:
        coefficients = [Fraction(value) for value in values]
    except (TypeError, ZeroDivisionError, ValueError) as exc:
        raise FabricRefused('malformed cost law coefficients') from exc
    return sum((a * b for a, b in zip(coefficients, workload.feature(path, queue))),
               Fraction(0))


def navigate(model: Mapping[str, Any], ground: ConnectomeGround,
             workload: Workload, paths: Sequence[HostPath],
             queue: Mapping[str, int]) -> dict[str, Any]:
    """A policy *proposal*, not evidence of execution or external permission."""
    if not paths:
        raise FabricRefused('no admissible host was supplied')
    options = []
    for path in paths:
        if not path.available or not path.permitted:
            continue
        if path.host not in queue:
            raise FabricRefused('missing queue observation')
        value = predict(model, ground, workload, path, queue[path.host])
        if value < 0:
            raise FabricRefused('negative predicted cost')
        options.append((value, path.key, path))
    if not options:
        raise FabricRefused('all candidates lack available capability')
    options.sort(key=lambda z: (z[0], z[1]))
    chosen = options[0][2]
    body = {'schema': SCHEMA + '.selection.v1', 'ground': ground.fingerprint,
            'policy': model['digest'], 'task': sha(workload.describe()),
            'chosen': chosen.to_dict(), 'synthetic_predicted_cost': value_text(options[0][0]),
            'available_candidates': [p.key for _, _, p in options],
            'status': 'proposal-only-not-host-execution'}
    return {**body, 'digest': canonical_hash(body)}


def synthesize_workloads(ground: ConnectomeGround, count: int,
                         *, seed: int = 901) -> tuple[Workload, ...]:
    """Sample heterogeneous *source-grounded* synthetic intentions.

    Walk the original graph to avoid mostly-zero training labels in small
    fixtures. Optional unreachable targets remain present as negative cases.
    """
    exact_int(count, 'task count', 1, 250)
    nodes = sorted(ground.nodes)
    rng = random.Random(seed)
    result, seen = [], set()
    kinds = [kind for kind in ('chemical', 'electrical')
             if any(ground.forward[kind].values())]
    for _ in range(count * 100):
        kind = rng.choice(kinds)
        active = [n for n in nodes if ground.forward[kind].get(n)]
        src = rng.choice(active)
        length = rng.choice((1, 2, 3))
        current = src
        valid = True
        for _ in range(length):
            neighbors = ground.forward[kind].get(current, ())
            if not neighbors:
                valid = False
                break
            current = rng.choice(neighbors).target
        if not valid:
            continue
        target = rng.choice(nodes) if rng.randrange(5) == 0 else current
        q = Query(src, target, length, kind)
        key = (q.source, q.target, q.steps, q.kind)
        if key in seen:
            continue
        seen.add(key)
        result.append(Workload.from_ground(ground, q))
        if len(result) == count:
            break
    if len(result) != count:
        raise FabricRefused('failed to create sufficient distinct source-bound intentions')
    return tuple(result)


def training_data(ground: ConnectomeGround, workloads: Sequence[Workload],
                  *, seed: int) -> tuple[tuple[Workload, dict[str, Any]], ...]:
    rng = random.Random(seed)
    result = []
    for workload in workloads:
        for p in candidates():
            # Two independently sampled queue conditions per host/mode to
            # ensure a rank-identifiable feature family without touching held-out tasks.
            for _ in range(2):
                from dataclasses import replace
                path = replace(p, framing_units=rng.randrange(0, 21))
                record = observation(ground, workload, path, rng.randrange(0, 101))
                result.append((workload, record))
    return tuple(result)


def realize_selected(ground: ConnectomeGround, workload: Workload,
                     selected: Mapping[str, Any], *, independent: bool = True) -> dict[str, Any]:
    """Only the ORIGINAL Ground executes. Policy cannot decide answer semantics."""
    if selected.get('status') != 'proposal-only-not-host-execution' or \
            selected.get('ground') != ground.fingerprint or \
            selected.get('task') != sha(workload.describe()):
        raise FabricRefused('policy proposal is not bound to the current task Ground')
    if canonical_hash({k: v for k, v in selected.items() if k != 'digest'}) != selected.get('digest'):
        raise FabricRefused('altered or unbound route-selection digest')
    path = HostPath(**selected['chosen'])
    if not path.available or not path.permitted:
        raise FabricRefused('selected host is not eligible')
    request = Query(**workload.request)
    if Workload.from_ground(ground, request) != workload:
        raise FabricRefused('changed source task metrics')
    plan = ground.plan(request)
    if path.method == 'cone':
        verified = ground.verify(plan, ground.run(plan), whole_graph=independent)
    else:
        verified = ground.independent_whole_graph(request)
        if independent and verified != ground.verify(plan, ground.run(plan), whole_graph=True):
            raise FabricRefused('full/reference and cone realization disagree')
    body = {'schema': SCHEMA + '.local-execution.v1', 'ground': ground.fingerprint,
            'selection': selected['digest'], 'host': path.host,
            'execution_method': path.method,
            'transfer': value_text(verified), 'oracle_checked': independent,
            'status': 'local-reference-execution-not-remote-authorization'}
    return {**body, 'digest': canonical_hash(body)}


def experiment(ground: ConnectomeGround, *, train_count: int = 18,
               test_count: int = 12, seed: int = 61) -> dict[str, Any]:
    """Train on disjoint synthetic intentions; evaluate held-out host conditions."""
    source = synthesize_workloads(ground, train_count + test_count, seed=seed)
    train = source[:train_count]
    test = source[train_count:]
    records = training_data(ground, train, seed=seed + 1)
    model = fit(ground, records)
    errors, baseline_regrets, policy_regrets, winners, outputs = [], [], [], {}, []
    rng = random.Random(seed + 2)
    for workload in test:
        from dataclasses import replace
        hosts = [replace(p, framing_units=rng.randrange(0, 21))
                 for p in candidates() if rng.randrange(0, 9) != 0]
        if not hosts:
            hosts = [candidates()[0]]
        queues = {p.host: rng.randrange(0, 251 if p.host == 'local-worker' else 101)
                  for p in hosts}
        selected = navigate(model, ground, workload, hosts, queues)
        available = [p for p in hosts if p.available and p.permitted]
        observed = {p.key: observe_synthetic_latency(p, workload.feature(p, queues[p.host]))
                    for p in available}
        oracle = min(observed.values())
        chosen = selected['chosen']['host'] + '/' + selected['chosen']['method']
        policy_regrets.append(observed[chosen] - oracle)
        baseline = next((p.key for p in available if p.host == 'local-worker' and p.method == 'cone'),
                        available[0].key)
        baseline_regrets.append(observed[baseline] - oracle)
        winners[chosen] = winners.get(chosen, 0) + 1
        # Actual semantic verification uses RCG-001 exact source (local).
        result = realize_selected(ground, workload, selected)
        outputs.append({'query': workload.request, 'selected': chosen,
                        'actual_reference': result['transfer'], 'receipt': result['digest']})
        errors.append(observed[chosen] - predict(model, ground, workload,
                                                  next(p for p in available if p.key == chosen),
                                                  queues[selected['chosen']['host']]))
    if any(e != 0 for e in errors) or any(r < 0 for r in policy_regrets):
        raise FabricRefused('held-out synthetic policy does not satisfy fitted law')
    body = {'schema': SCHEMA + '.study.v1', 'ground': ground.fingerprint,
            'seed': seed, 'train_tasks': train_count, 'held_out_tasks': test_count,
            'train_measurements': len(records), 'model': model,
            'training_query_digests': [sha(w.describe()) for w in train],
            'held_out_query_digests': [sha(w.describe()) for w in test],
            'synthetic_policy_regret': value_text(sum(policy_regrets, Fraction(0))),
            'synthetic_fixed_baseline_regret': value_text(sum(baseline_regrets, Fraction(0))),
            'synthetic_prediction_absolute_error': value_text(sum((abs(v) for v in errors), Fraction(0))),
            'selected_paths': winners, 'verified_held_out_results': outputs,
            'experiment_kind': 'synthetic-causal-ground-adaptive-observer-fabric-cost-learning',
            'interpretation': 'all numerical output verified locally with original source; path costs simulated and no remote host authorized'}
    return {**body, 'digest': canonical_hash(body)}


def main() -> None:
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2] / 'data' / 'herm_full_edgelist.csv')
    parser.add_argument('--train', type=int, default=18)
    parser.add_argument('--test', type=int, default=12)
    parser.add_argument('--seed', type=int, default=61)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ground = ConnectomeGround.from_csv(args.source.read_bytes())
    record = experiment(ground, train_count=args.train, test_count=args.test, seed=args.seed)
    raw = json.dumps(record, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw)
    else:
        print(raw)


if __name__ == '__main__':
    main()
