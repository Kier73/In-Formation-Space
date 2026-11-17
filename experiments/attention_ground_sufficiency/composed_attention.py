"""AKS-002: compositional causal attention over AKS-001's exact Ground.

This is a finite-field affine-kernel network, NOT Transformer softmax.
No authority, network side effects, or cryptographic origin authentication.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Sequence

from attention_ground import (
    AttentionGround, GroundRefused, PrefixGround, TokenEvidence, _digest, _int,
    _vector, direct_observe,
)


@dataclass(frozen=True)
class Head:
    """Immutable Wq, Wk and Wv; rows are output-major field coordinates."""
    query: tuple[tuple[int, ...], ...]
    key: tuple[tuple[int, ...], ...]
    value: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class Layer:
    """Parallel heads, one output projection and one residual connection."""
    heads: tuple[Head, ...]
    output: tuple[tuple[int, ...], ...]
    normalized: bool = False


@dataclass(frozen=True)
class Network:
    """Fully specified finite-field neural Ground and exact projected outputs."""
    modulus: int
    model_dim: int
    layers: tuple[Layer, ...]

    def __post_init__(self) -> None:
        _int(self.model_dim, "model dimension", 1, 32)
        if not isinstance(self.layers, tuple) or not 1 <= len(self.layers) <= 8:
            raise GroundRefused("network needs 1..8 layers")
        # Reuse AKS-001's prime-field admission instead of defining a new ring.
        AttentionGround(self.modulus, 1, 1)
        for layer in self.layers:
            if not isinstance(layer, Layer) or not isinstance(layer.heads, tuple) or not 1 <= len(layer.heads) <= 16:
                raise GroundRefused("network layer needs 1..16 typed heads")
            if type(layer.normalized) is not bool:
                raise GroundRefused("normalized must be a strict Boolean")
            total_values = 0
            for head in layer.heads:
                if not isinstance(head, Head):
                    raise GroundRefused("invalid head")
                for projection in (head.query, head.key, head.value):
                    if not isinstance(projection, tuple) or not 1 <= len(projection) <= 32:
                        raise GroundRefused("projection output dimension invalid")
                    for row in projection:
                        _vector(row, self.model_dim, self.modulus, "projection row")
                if len(head.query) != len(head.key):
                    raise GroundRefused("query/key dimensions differ")
                total_values += len(head.value)
            if not isinstance(layer.output, tuple) or len(layer.output) != self.model_dim:
                raise GroundRefused("output projection dimension invalid")
            for row in layer.output:
                _vector(row, total_values, self.modulus, "output projection row")

    @property
    def fingerprint(self) -> str:
        return _digest({"schema": "ifs.aks002.network.v1", "p": self.modulus,
                        "d": self.model_dim, "layers": asdict(self)["layers"]})


def _matrix_apply(rows: tuple[tuple[int, ...], ...], vector: tuple[int, ...], p: int) -> tuple[int, ...]:
    """Exact local reference realization; VGI separately checks this algebra."""
    return tuple(sum(a * b for a, b in zip(row, vector)) % p for row in rows)


def _head_ground(network: Network, head: Head) -> AttentionGround:
    return AttentionGround(network.modulus, len(head.key), len(head.value))


@dataclass(frozen=True)
class InputEvidence:
    """Source observation; integrity chain is not a trusted signature."""
    network: str
    index: int
    previous: str
    vector: tuple[int, ...]
    digest: str

    @classmethod
    def form(cls, network: Network, index: int, previous: str, vector: Sequence[int]) -> "InputEvidence":
        _int(index, "input index", 0, 1_000_000)
        if not isinstance(previous, str) or len(previous) != 64 or any(c not in "0123456789abcdef" for c in previous):
            raise GroundRefused("malformed source predecessor")
        x = _vector(vector, network.model_dim, network.modulus, "input")
        d = _digest({"network": network.fingerprint, "index": index, "previous": previous, "vector": x})
        return cls(network.fingerprint, index, previous, x, d)


def _origin(network: Network) -> str:
    return _digest({"schema": "ifs.aks002.origin.v1", "network": network.fingerprint})


@dataclass(frozen=True)
class StepReceipt:
    """Exact per-layer/head observations, not independent peer authentication."""
    network: str
    index: int
    input_digest: str
    layer_heads: tuple[tuple[tuple[int, ...], ...], ...]
    layer_outputs: tuple[tuple[int, ...], ...]
    prefix_fingerprints: tuple[tuple[str, ...], ...]
    output: tuple[int, ...]
    state_digest: str


@dataclass(frozen=True)
class CausalState:
    """Multi-layer, multi-head fixed-shape sufficient states at one source prefix."""
    network: Network
    count: int
    source_head: str
    prefixes: tuple[tuple[PrefixGround, ...], ...]

    @classmethod
    def empty(cls, network: Network) -> "CausalState":
        return cls(network, 0, _origin(network), tuple(
            tuple(PrefixGround.empty(_head_ground(network, head)) for head in layer.heads)
            for layer in network.layers
        ))

    @property
    def fingerprint(self) -> str:
        return _digest({"schema": "ifs.aks002.causal-state.v1", "network": self.network.fingerprint,
                        "count": self.count, "source_head": self.source_head,
                        "prefixes": [[p.fingerprint for p in row] for row in self.prefixes]})

    def advance(self, token: InputEvidence) -> tuple["CausalState", StepReceipt]:
        if not isinstance(token, InputEvidence) or token != InputEvidence.form(
                self.network, self.count, self.source_head, token.vector):
            raise GroundRefused("input does not extend receiver-selected source prefix")
        p = self.network.modulus
        x = token.vector
        new_prefixes: list[tuple[PrefixGround, ...]] = []
        observations: list[tuple[tuple[int, ...], ...]] = []
        outputs: list[tuple[int, ...]] = []
        for layer, previous in zip(self.network.layers, self.prefixes):
            heads_out = []
            heads_next = []
            for head, state in zip(layer.heads, previous):
                q = _matrix_apply(head.query, x, p)
                k = _matrix_apply(head.key, x, p)
                v = _matrix_apply(head.value, x, p)
                witnessed = TokenEvidence.form(state.ground, state.count, state.history_head, k, v)
                advanced = state.admit(witnessed)
                value = advanced.query(q, normalized=layer.normalized).result
                heads_out.append(value)
                heads_next.append(advanced)
            flattened = tuple(v for vector in heads_out for v in vector)
            update = _matrix_apply(layer.output, flattened, p)
            x = tuple((a + b) % p for a, b in zip(x, update))
            new_prefixes.append(tuple(heads_next))
            observations.append(tuple(heads_out))
            outputs.append(x)
        result = CausalState(self.network, self.count + 1, token.digest, tuple(new_prefixes))
        receipt = StepReceipt(self.network.fingerprint, self.count, token.digest,
                              tuple(observations), tuple(outputs),
                              tuple(tuple(s.fingerprint for s in row) for row in result.prefixes),
                              x, result.fingerprint)
        return result, receipt


def direct_history_reference(network: Network, inputs: Sequence[InputEvidence]) -> tuple[tuple[int, ...], ...]:
    """Quadratic separate reference: direct per-token summation, no prefix moments used."""
    p = network.modulus
    histories: list[list[list[tuple[tuple[int, ...], tuple[int, ...]]]]] = [
        [[] for _ in layer.heads] for layer in network.layers
    ]
    expected_predecessor = _origin(network)
    results = []
    for index, item in enumerate(inputs):
        if item != InputEvidence.form(network, index, expected_predecessor, item.vector):
            raise GroundRefused("independent history has an unbound input")
        expected_predecessor = item.digest
        x = item.vector
        for li, layer in enumerate(network.layers):
            heads_out = []
            for hi, head in enumerate(layer.heads):
                q = _matrix_apply(head.query, x, p)
                k = _matrix_apply(head.key, x, p)
                v = _matrix_apply(head.value, x, p)
                history = histories[li][hi]
                history.append((k, v))
                num = [0] * len(v)
                den = 0
                for past_k, past_v in history:
                    weight = (1 + sum(a * b for a, b in zip(q, past_k))) % p
                    den = (den + weight) % p
                    for j, b in enumerate(past_v):
                        num[j] = (num[j] + weight * b) % p
                if layer.normalized:
                    if den == 0:
                        raise GroundRefused("normalization denominator is zero in the admitted field")
                    heads_out.append(tuple(n * pow(den, -1, p) % p for n in num))
                else:
                    heads_out.append(tuple(num))
            flattened = tuple(v for head_values in heads_out for v in head_values)
            update = _matrix_apply(layer.output, flattened, p)
            x = tuple((a + b) % p for a, b in zip(x, update))
        results.append(x)
    return tuple(results)


def independently_verify_trace(network: Network, inputs: Sequence[InputEvidence],
                               receipts: Sequence[StepReceipt], *, expected_source_head: str,
                               expected_state_digest: str) -> CausalState:
    """Replay source, compare independent quadratic oracle, enforce external pins."""
    if len(inputs) != len(receipts):
        raise GroundRefused("missing or extra receipts")
    state = CausalState.empty(network)
    actual = []
    for source, claimed in zip(inputs, receipts):
        state, calculated = state.advance(source)
        if claimed != calculated:
            raise GroundRefused("compositional Ground receipt mismatch")
        actual.append(claimed.output)
    if state.source_head != expected_source_head or state.fingerprint != expected_state_digest:
        raise GroundRefused("receiver-pinned source/state root mismatch")
    if tuple(actual) != direct_history_reference(network, inputs):
        raise GroundRefused("independent historical neural oracle disagrees")
    return state


@dataclass(frozen=True)
class MomentSegment:
    """An exact contiguous interval's associative neural moments and lineage."""
    ground: AttentionGround
    start: int
    end: int
    previous: str
    head: str
    matrix: tuple[tuple[int, ...], ...]
    mass: tuple[int, ...]

    @property
    def fingerprint(self) -> str:
        return _digest({"schema": "ifs.aks002.segment.v1", "ground": self.ground.fingerprint,
                        "start": self.start, "end": self.end, "previous": self.previous,
                        "head": self.head, "matrix": self.matrix, "mass": self.mass})

    def combine(self, right: "MomentSegment") -> "MomentSegment":
        """Compose neighboring disjoint intervals without rereading token payloads."""
        if not isinstance(right, MomentSegment) or self.ground != right.ground or \
                self.end != right.start or self.head != right.previous:
            raise GroundRefused("segments are not adjacent in the same witnessed Ground")
        p = self.ground.modulus
        rows = tuple(tuple((a+b) % p for a,b in zip(ra, rb))
                     for ra, rb in zip(self.matrix, right.matrix))
        mass = tuple((a+b) % p for a,b in zip(self.mass, right.mass))
        return MomentSegment(self.ground, self.start, right.end, self.previous, right.head, rows, mass)

    def query(self, query: Sequence[int], *, normalized: bool) -> tuple[int, ...]:
        """Query the interval only, using its exact aggregate moments."""
        q = _vector(query, self.ground.key_dim, self.ground.modulus, "query")
        f = (1,) + q
        p = self.ground.modulus
        numer = tuple(sum(a*row[j] for a,row in zip(f, self.matrix)) % p
                      for j in range(self.ground.value_dim))
        den = sum(a*b for a,b in zip(f, self.mass)) % p
        if normalized and den == 0:
            raise GroundRefused("normalization denominator is zero in the admitted field")
        return tuple(v * pow(den, -1, p) % p for v in numer) if normalized else numer


def segment_from_tokens(ground: AttentionGround, tokens: Sequence[TokenEvidence]) -> MomentSegment:
    """Check all source receipts in this interval, then retain only its moments."""
    if not tokens:
        raise GroundRefused("cannot construct empty evidenced interval")
    start = tokens[0].index
    prev = tokens[0].previous
    p = ground.modulus
    rows = [[0] * ground.value_dim for _ in range(ground.key_dim+1)]
    mass = [0] * (ground.key_dim+1)
    for j, token in enumerate(tokens):
        if not isinstance(token, TokenEvidence) or token.index != start+j or token.previous != prev or \
                token != TokenEvidence.form(ground, token.index, token.previous, token.key, token.value):
            raise GroundRefused("invalid or discontinuous segment evidence")
        prev = token.digest
        for i, a in enumerate((1,) + token.key):
            mass[i] = (mass[i]+a) % p
            for k, value in enumerate(token.value):
                rows[i][k] = (rows[i][k] + a*value) % p
    return MomentSegment(ground, start, start+len(tokens), tokens[0].previous,
                         prev, tuple(tuple(row) for row in rows), tuple(mass))


def vgi_operator_crosscheck(network: Network, vector: Sequence[int]) -> int:
    """Use *existing VGI* FiniteSpace/DenseMap/TypedVector for every projection.

    The checked result is not a VGI ProofGround or E-CPU execution admission.
    Requires the separately installed pinned VGI interpreter package.
    """
    from vgi.typed_operator_navigation import FiniteSpace, DenseMap, TypedVector
    x = _vector(vector, network.model_dim, network.modulus, "VGI probe")
    checked = 0
    for li, layer in enumerate(network.layers):
        blocks = []
        for hi, head in enumerate(layer.heads):
            for kind, rows in (("query", head.query), ("key", head.key), ("value", head.value)):
                blocks.append((f"L{li}.H{hi}.{kind}", rows, network.model_dim))
        blocks.append((f"L{li}.output", layer.output, sum(len(h.value) for h in layer.heads)))
        for identifier, rows, in_dim in blocks:
            domain = FiniteSpace(identifier+".input", in_dim, network.modulus)
            codomain = FiniteSpace(identifier+".output", len(rows), network.modulus)
            mapping = DenseMap(identifier, domain, codomain, rows)
            # Check separate vectors for output map, since it has different input dimensionality.
            probe = x if in_dim == network.model_dim else tuple(range(in_dim))
            vgi = mapping.apply(TypedVector(domain, probe)).values
            if vgi != _matrix_apply(rows, probe, network.modulus):
                raise GroundRefused("VGI and local field projection disagree")
            checked += 1
    return checked


def native_ecpu_dag_snapshot(network: Network, receipt: StepReceipt) -> dict[str, Any]:
    """Project one checked step into E-CPU's *actual* bounded DAG readiness.

    Caller must first independently_verify_trace; native DAG scheduling is not
    neural arithmetic, receiver capability admission, or verified proof.
    """
    from mailcpu.computation_dag import ComputationNode, NavigableComputationDAG
    if not isinstance(receipt, StepReceipt) or receipt.network != network.fingerprint or \
            len(receipt.layer_heads) != len(network.layers) or \
            len(receipt.layer_outputs) != len(network.layers):
        raise GroundRefused("invalid native DAG input receipt")
    ctx = network.fingerprint
    def node(identifier, deps, operation, payload):
        return ComputationNode(identifier, 1, operation, "/computational-ground/aks002",
                               ctx, deps, payload)
    nodes = [node("source", (), "read bound source observation",
                  {"input_digest": receipt.input_digest, "step": receipt.index})]
    previous_join = "source"
    for li, layer in enumerate(network.layers):
        heads = []
        for hi, head in enumerate(layer.heads):
            name = f"L{li}.H{hi}"
            heads.append(name)
            nodes.append(node(name, (previous_join,), "observe exact affine attention",
                              {"head": hi, "layer": li, "state": receipt.prefix_fingerprints[li][hi]}))
        join = f"L{li}.join"
        nodes.append(node(join, tuple(heads), "compose residual and head projections",
                          {"layer": li, "network": ctx}))
        previous_join = join
    dag = NavigableComputationDAG(nodes)
    if tuple(v.node_id for v in dag.ready_nodes()) != ("source",):
        raise GroundRefused("native source frontier mismatch")
    dag.commit("source", {"input_digest": receipt.input_digest})
    for li, layer in enumerate(network.layers):
        expected = {f"L{li}.H{hi}" for hi in range(len(layer.heads))}
        if {node.node_id for node in dag.ready_nodes()} != expected:
            raise GroundRefused("native parallel head frontier mismatch")
        dag.commit_frontier({f"L{li}.H{hi}": {
            "result": list(receipt.layer_heads[li][hi]),
            "prefix_fingerprint": receipt.prefix_fingerprints[li][hi]}
            for hi in range(len(layer.heads))}, expected_node_ids=tuple(sorted(expected)))
        join = f"L{li}.join"
        if tuple(node.node_id for node in dag.ready_nodes()) != (join,):
            raise GroundRefused("native residual dependency mismatch")
        dag.commit(join, {"output": list(receipt.layer_outputs[li])})
    if not dag.is_complete:
        raise GroundRefused("native dependency frontier incomplete")
    recovered = NavigableComputationDAG.from_snapshot(dag.snapshot())
    if not recovered.is_complete or recovered.digest != dag.digest:
        raise GroundRefused("native DAG recovery mismatch")
    return {"graph_digest": dag.digest, "snapshot": dag.snapshot(),
            "committed_nodes": list(recovered.committed_nodes),
            "terminal_output": recovered.result(previous_join)["output"]}


def checkpoint(state: CausalState) -> dict[str, Any]:
    """Export bounded mathematical state, not an authority-approved recovery commit."""
    return {"schema": "ifs.aks002.checkpoint.v1", "network": state.network.fingerprint,
            "count": state.count, "source_head": state.source_head,
            "prefixes": [[{"count": p.count, "matrix": [list(r) for r in p.matrix],
                           "mass": list(p.mass), "history_head": p.history_head}
                          for p in row] for row in state.prefixes],
            "state_digest": state.fingerprint}


def restore_checkpoint(network: Network, snapshot: dict[str, Any], *,
                       expected_source_head: str, expected_state_digest: str) -> CausalState:
    """Recover compact state only from an externally pinned, previously audited root.

    Neither JSON hashing nor this function proves a remote source's honesty.
    Its inputs must be anchored in receiver-owned E-CPU recovery authority.
    """
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "schema", "network", "count", "source_head", "prefixes", "state_digest"
    } or snapshot["schema"] != "ifs.aks002.checkpoint.v1" or snapshot["network"] != network.fingerprint:
        raise GroundRefused("checkpoint schema or network binding invalid")
    _int(snapshot["count"], "checkpoint count", 0, 1_000_001)
    if not isinstance(snapshot["prefixes"], list) or len(snapshot["prefixes"]) != len(network.layers):
        raise GroundRefused("checkpoint layer structure invalid")
    result_rows = []
    for li, layer in enumerate(network.layers):
        row = snapshot["prefixes"][li]
        if not isinstance(row, list) or len(row) != len(layer.heads):
            raise GroundRefused("checkpoint head structure invalid")
        result = []
        for head, value in zip(layer.heads, row):
            if not isinstance(value, dict) or set(value) != {"count", "matrix", "mass", "history_head"}:
                raise GroundRefused("checkpoint prefix malformed")
            ground = _head_ground(network, head)
            if value["count"] != snapshot["count"]:
                raise GroundRefused("checkpoint head count inconsistent")
            if not isinstance(value["matrix"], list) or not isinstance(value["mass"], list):
                raise GroundRefused("checkpoint moments malformed")
            moment = PrefixGround(ground, value["count"],
                                  tuple(tuple(r) for r in value["matrix"]),
                                  tuple(value["mass"]), value["history_head"])
            result.append(moment)
        result_rows.append(tuple(result))
    result = CausalState(network, snapshot["count"], snapshot["source_head"], tuple(result_rows))
    if (result.source_head != expected_source_head or result.fingerprint != expected_state_digest
            or snapshot["state_digest"] != result.fingerprint):
        raise GroundRefused("checkpoint disagrees with receiver-owned high-water root")
    return result


def verify_segment(ground: AttentionGround, tokens: Sequence[TokenEvidence],
                   claimed: MomentSegment, *, expected_head: str) -> bool:
    """Independent receiver source-replay for initial segment admission."""
    if not isinstance(claimed, MomentSegment) or claimed != segment_from_tokens(ground, tokens):
        raise GroundRefused("segment is not the claimed source-derived moments")
    if claimed.head != expected_head:
        raise GroundRefused("segment history disagrees with receiver-owned source root")
    return True
