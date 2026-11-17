"""AKS-003: AKS-002 attention state on native E-CPU M3/M1/quorum sessions.

No new quorum, scheduler, page-object format, or hypervisor authority. Attention
is exact for the admitted finite-field affine kernel; NOT Transformer softmax.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from attention_ground import GroundRefused, _vector
from composed_attention import (
    CausalState, Head, InputEvidence, Layer, Network, _matrix_apply,
    checkpoint, restore_checkpoint, independently_verify_trace,
)

SCHEMA = 'ifs.aks003.affine-attention.v1'
SESSION = 'aks003-attention'
GENESIS = hashlib.sha256(b'mailcpu-recovery-lineage-genesis-v1').hexdigest()
_BACKENDS = {
    'A': hashlib.sha256(b'aks003-attention-native-A').hexdigest(),
    'B': hashlib.sha256(b'aks003-attention-native-B').hexdigest(),
}


def network_ground() -> Network:
    """Three layers of three heads; source identity is a complete model digest."""
    heads = (
        Head(((0, 1, 0),), ((1, 0, 0),), ((0, 0, 1),)),
        Head(((1, 0, 0),), ((0, 1, 0),), ((0, 0, 1), (1, 0, 0))),
        Head(((1, 0, 0),), ((1, 0, 0),), ((0, 1, 0),)),
    )
    width = sum(len(h.value) for h in heads)
    projection = ((0,) * width, (0,) * width, tuple((i+1) % 5 for i in range(width)))
    return Network(65521, 3, (Layer(heads, projection, False),) * 3)


def source_vector(index: int) -> tuple[int, ...]:
    return (1, index % 7, (3*index + index*index) % 23)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def encode_state(state: CausalState) -> bytes:
    return canonical_bytes({'schema': SCHEMA, 'network': state.network.fingerprint,
                            'checkpoint': checkpoint(state)})


def decode_state(network: Network, state_bytes: bytes) -> CausalState:
    """The expected source/state heads come from quorum-bound M1 bytes, not a caller."""
    raw = json.loads(state_bytes)
    if not isinstance(raw, dict) or set(raw) != {'schema', 'network', 'checkpoint'} or \
            raw['schema'] != SCHEMA or raw['network'] != network.fingerprint:
        raise GroundRefused('invalid network and state schema bound to session')
    cp = raw['checkpoint']
    if not isinstance(cp, dict) or type(cp.get('source_head')) is not str or \
            type(cp.get('state_digest')) is not str:
        raise GroundRefused('checkpoint root fields malformed')
    return restore_checkpoint(network, cp, expected_source_head=cp['source_head'],
                              expected_state_digest=cp['state_digest'])


class FilePageBacking:
    """Durable, immutable SHA-256 page backing for E-CPU's existing M1 object store.

    This is a local filesystem fixture, NOT new authority or page-object logic.
    The M1 store owns the padded object manifests and verifies content identity.
    """
    page_size = 256

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, value: str) -> Path:
        if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
            raise ValueError('invalid page digest')
        return self.root / value

    def put_page(self, data: bytes) -> str:
        if not isinstance(data, bytes) or len(data) != self.page_size:
            raise ValueError('invalid fixed-size page')
        key = digest(data)
        path = self._path(key)
        try:
            with path.open('xb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
        except FileExistsError:
            if self.get_page(key) != data:
                raise ValueError('existing page differs')
        return key

    def get_page(self, value: str) -> bytes:
        data = self._path(value).read_bytes()
        if len(data) != self.page_size or digest(data) != value:
            raise ValueError('page integrity mismatch')
        return data


def make_store(root: Path, network: Network, host: str):
    """Reuse real M3 computational session and 3 persistent quorum authorities."""
    from mailcpu.computational_objects import ComputationalObjectStore
    from mailcpu.computational_session import ComputationalSessionStore
    from mailcpu.recovery_lineage import RecoveryLineageAuthority, RecoveryLineageCoordinator
    from mailcpu.seed_commit_quorum import SeedCommitMembership

    if host not in _BACKENDS:
        raise ValueError('unknown admitted backend')
    root = Path(root)
    membership = SeedCommitMembership(SESSION, 1, ('A', 'B', 'C'), 'A', 1, GENESIS)
    authorities = {member: RecoveryLineageAuthority(
        membership, member, root / 'quorum' / (member + '.jsonl'))
        for member in membership.member_ids}
    lineage = RecoveryLineageCoordinator(membership, authorities)
    objects = ComputationalObjectStore(FilePageBacking(root / 'pages'), chunk_size=256)
    return ComputationalSessionStore(
        root / 'hosts' / host, objects, lineage,
        artifact_manifest_digest=network.fingerprint,
        backend_fingerprint=_BACKENDS[host],
        state_schema_id=SCHEMA,
        state_media_type='application/json',
    )


def compatible(source: str, target: str, schema: str) -> bool:
    """Explicitly accept only the known A->B field/shape-compatible adapter."""
    return source == _BACKENDS['A'] and target == _BACKENDS['B'] and schema == SCHEMA


def load_attention(store, network: Network, *, migrated: bool = False):
    snapshot = store.load_latest(backend_compatibility=compatible if migrated else None)
    if snapshot.checkpoint.artifact_manifest_digest != network.fingerprint or \
            snapshot.checkpoint.state_schema_id != SCHEMA:
        raise GroundRefused('session scope differs from admitted neural Ground')
    state = decode_state(network, snapshot.state_bytes)
    return snapshot, state


def advance_session(store, network: Network, previous, state: CausalState,
                    vector: tuple[int, ...], *, migrated: bool = False):
    """CAS anchor one observation, not a second session ledger or scheduler."""
    if decode_state(network, previous.state_bytes) != state:
        raise GroundRefused('supplied state differs from authenticated session bytes')
    token = InputEvidence.form(network, state.count, state.source_head, vector)
    next_state, receipt = state.advance(token)
    request = canonical_bytes({'network': network.fingerprint, 'index': state.count,
                               'predecessor': state.source_head, 'vector': list(vector)})
    saved = store.commit_state(
        encode_state(next_state), expected_revision=previous.revision,
        expected_checkpoint_digest=previous.checkpoint_digest,
        transition_id='aks003.step.' + str(state.count),
        operation_id='aks003.attention.advance',
        input_digest=digest(request), logical_time=next_state.count,
        backend_compatibility=compatible if migrated else None,
    )
    if decode_state(network, saved.state_bytes) != next_state:
        raise GroundRefused('quorum-anchored continuation differs from neural observation')
    return saved, next_state, receipt


def observe_probe(state: CausalState, vector: tuple[int, ...]) -> tuple[int, ...]:
    """One non-mutating query from bounded prefix state, no old-source replay."""
    p = state.network.modulus
    x = _vector(vector, state.network.model_dim, p, 'probe')
    for layer, prefixes in zip(state.network.layers, state.prefixes):
        heads = [prefix.query(_matrix_apply(head.query, x, p),
                              normalized=layer.normalized).result
                 for head, prefix in zip(layer.heads, prefixes)]
        flattened = tuple(v for values in heads for v in values)
        increment = _matrix_apply(layer.output, flattened, p)
        x = tuple((a + b) % p for a, b in zip(x, increment))
    return x


def direct_probe_oracle(network: Network, sources: tuple[tuple[int, ...], ...],
                       vector: tuple[int, ...]) -> tuple[int, ...]:
    """Independent quadratic source-history oracle; never used in recovered host."""
    p = network.modulus
    history = [[[] for head in layer.heads] for layer in network.layers]
    for original in sources:
        x = original
        for li, layer in enumerate(network.layers):
            values = []
            for hi, head in enumerate(layer.heads):
                q = _matrix_apply(head.query, x, p)
                k = _matrix_apply(head.key, x, p)
                v = _matrix_apply(head.value, x, p)
                h = history[li][hi]
                h.append((k, v))
                numerator = [0] * len(v)
                denominator = 0
                for old_key, old_value in h:
                    w = (1 + sum(a*b for a,b in zip(q, old_key))) % p
                    denominator = (denominator + w) % p
                    for j, value in enumerate(old_value):
                        numerator[j] = (numerator[j] + w*value) % p
                values.append(tuple(n*pow(denominator, -1, p) % p for n in numerator)
                              if layer.normalized else tuple(numerator))
            flattened = tuple(y for ys in values for y in ys)
            delta = _matrix_apply(layer.output, flattened, p)
            x = tuple((a+b) % p for a,b in zip(x, delta))
    x = _vector(vector, network.model_dim, p, 'oracle probe')
    for li, layer in enumerate(network.layers):
        values = []
        for hi, head in enumerate(layer.heads):
            q = _matrix_apply(head.query, x, p)
            numerator = [0] * len(head.value)
            denominator = 0
            for old_key, old_value in history[li][hi]:
                w = (1 + sum(a*b for a,b in zip(q, old_key))) % p
                denominator = (denominator + w) % p
                for j, value in enumerate(old_value):
                    numerator[j] = (numerator[j] + w*value) % p
            values.append(tuple(n*pow(denominator, -1, p) % p for n in numerator)
                          if layer.normalized else tuple(numerator))
        delta = _matrix_apply(layer.output, tuple(y for ys in values for y in ys), p)
        x = tuple((a+b) % p for a,b in zip(x, delta))
    return x


def native_virtual_layer_probe(store, network: Network, vector, *, expected_revision: int,
                               expected_checkpoint_digest: str, grant_compute: bool):
    """Invoke *real* E-CPU VirtualLayerRuntime + HeadlessOS Hypervisor.

    The handler re-reads M3 quorum high-water; old session pointers refuse.
    Virtual Layer authorizes one pure query, not a session state mutation.
    """
    from mailcpu import (
        Capability, HeadlessOS, HypervisorAction, HypervisorPolicy,
        LexicalDecisionModel, SystemIdentity, SystemSeed, SystemSeedEnvelope,
        VirtualBudget, VirtualGroundRef, VirtualLayerRuntime,
        VirtualLayerWorkload, VirtualOperatorRef, OperatorRegistry, OperatorSpec,
    )
    host_os = HeadlessOS()
    host_os.hypervisor.classifier = LexicalDecisionModel()
    host_os.hypervisor.policy = HypervisorPolicy(embedding_review_confidence=1.0)
    identity = SystemIdentity('aks003-virtual-query', 1)
    envelope = SystemSeedEnvelope(identity, 'executor', 'virtual-layer', SystemSeed.from_system(host_os))
    if not host_os.seed_admission.admit(envelope).accepted:
        raise GroundRefused('receiver refused Virtual Ground admission')
    calls = []

    def handler(value, workload):
        calls.append(workload.workload_id)
        current, state = load_attention(store, network, migrated=True)
        if current.revision != value['revision'] or \
                current.checkpoint_digest != value['checkpoint_digest']:
            raise GroundRefused('virtual-layer request references stale M3 high-water')
        return {'output': list(observe_probe(state, tuple(value['vector']))),
                'checkpoint_digest': current.checkpoint_digest,
                'revision': current.revision, 'source_head': state.source_head}

    registry = OperatorRegistry()
    registry.register(OperatorSpec(
        operator_id='aks003.attention_probe', version=1,
        description='Observe an exact quorum-anchored attention prefix',
        input_kind='object', output_kind='object', substrates=('cpu',),
        required_rights=frozenset({'compute'}),
        base_energy=8, energy_per_byte=1, max_input_bytes=2048,
        max_output_bytes=1024, deterministic=True, effect_mode='pure'), handler)
    runtime = VirtualLayerRuntime(registry, 'node-B', frozenset({'cpu'}))
    workload = VirtualLayerWorkload(
        workload_id='aks003-probe-' + str(expected_revision),
        system=identity, ground=VirtualGroundRef.from_envelope(envelope),
        intention={'goal': {'observe': 'quorum-anchored affine attention'}},
        operators=(VirtualOperatorRef('aks003.attention_probe', 1, 'cpu'),),
        input_value={'vector': list(vector), 'revision': expected_revision,
                     'checkpoint_digest': expected_checkpoint_digest},
        budget=VirtualBudget(50000, 20000, 1000), logical_time=expected_revision,
        eligible_nodes=('node-B',), max_hops=1)
    capabilities = ((Capability('/virtual-layer/operators', frozenset({'compute'})),)
                    if grant_compute else (Capability('/unrelated', frozenset({'read'})),))
    pid = host_os.environment.kernel.spawn('aks003-receiver', capabilities=capabilities,
                                           parent_pid=host_os.environment.init_pid)
    verdict = runtime.execute_operator(host_os, pid, 'origin', 'aks003', 1,
                                       workload.logical_time, workload, 'aks003.attention_probe')
    if not grant_compute:
        if verdict.action is not HypervisorAction.DENY or verdict.executed or calls:
            raise GroundRefused('Virtual Layer accepted a request without compute authority')
        return {'action': 'DENY', 'calls': 0}
    if verdict.action is not HypervisorAction.ALLOW or not verdict.executed or len(calls) != 1:
        raise GroundRefused('Virtual Layer did not realize the authorized observation once')
    if verdict.effect['result']['revision'] != expected_revision:
        raise GroundRefused('authorized response not bound to M3 revision')
    return {'action': 'ALLOW', 'calls': 1, 'effect': verdict.effect}


def save_json(path: Path, value: object):
    """Atomic fsynced supervisor evidence; NOT the quorum authority itself."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False,
                                     encoding='utf-8') as f:
        try:
            json.dump(value, f, sort_keys=True, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
            tmp = f.name
        except BaseException:
            Path(f.name).unlink(missing_ok=True)
            raise
    os.replace(tmp, path)
    try:
        fd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    except OSError:
        pass
