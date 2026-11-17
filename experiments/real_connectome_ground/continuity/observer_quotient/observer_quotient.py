"""RCG-006: source-bound synthetic state expansion and learned exact observer quotient.

Body: available E-CPU observer-host and communication paths (not biological anatomy).
Mind: discover state equivalence from generated temporal response observations;
only a full-edge intertwining check admits the quotient. No neural weights are
trained here. This is finite-field system identification + exact state abstraction.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import zlib
from typing import Any, Iterable

from connectome_ground import ConnectomeGround
from temporal_ground import MODULUS, SparseTransfer, hash_object

SCHEMA = "ifs.rcg006.observer-quotient.v1"
MAX_NODES = 131072
MAX_COPIES = 8192
MAX_GROUPS = 64
MAX_EDGES = 1_048_576


class QuotientRefused(ValueError):
    """No qualified source, observation, quotient or proof was established."""


def insist(condition: bool, reason: str) -> None:
    if not condition:
        raise QuotientRefused(reason)


class ExpandedSyntheticGround:
    """Reconstructable 8-regular *synthetic* expansion of an observed source.

    Source c302 connectivity informs group coefficients via synapse statistics;
    this does NOT claim to preserve the source graph's biological dynamics or
    be an exact quotient of the original 448 node graph. Each generated micro
    column distributes its mass across two successor groups. Names are
    permuted, so the observer cannot discover groups from prefix labels.
    """
    def __init__(self, source: ConnectomeGround, *, groups: int = 16,
                 copies: int = 256, seed: int = 73):
        insist(isinstance(source, ConnectomeGround), "receiver-owned input Ground required")
        insist(type(groups) is int and groups >= 4 and groups <= MAX_GROUPS and
               groups & (groups - 1) == 0, "group count must be a bounded power of two")
        insist(type(copies) is int and 8 <= copies <= MAX_COPIES and
               copies & (copies - 1) == 0, "copies must be a bounded power of two")
        insist(type(seed) is int and 0 <= seed < 2**31, "invalid procedural seed")
        n = groups * copies
        insist(n <= MAX_NODES and 8*n <= MAX_EDGES,
               "expansion exceeds declared microstate or edge budget")
        counts = [0] * groups
        squared = [0] * groups
        labels = {name: pos % groups for pos, name in enumerate(sorted(source.nodes))}
        for edge in source.edges:
            if edge.kind == "chemical":
                g = labels[edge.source]
                counts[g] += edge.count
                squared[g] += edge.count**2
        weights = tuple((1 + value % 61, 1 + squared[i] % 67)
                        for i, value in enumerate(counts))
        a = (int(hashlib.sha256((source.fingerprint+str(seed)).encode()).hexdigest()[:8], 16) | 1) % n
        if a == 1:
            a = 5
        b = (int(hashlib.sha256((str(seed)+source.fingerprint).encode()).hexdigest()[:8],16)) % n
        self._a, self._b, self._inverse = a, b, pow(a, -1, n)
        self.source = source
        self.groups, self.copies, self.seed, self.n = groups, copies, seed, n
        self.field, self.weights = MODULUS, weights
        self.source_blob = source.source_blob
        self.source_fingerprint = source.fingerprint
        self.description = {
            "schema":SCHEMA+".expanded.v1", "source_ground":source.fingerprint,
            "source_blob":source.source_blob, "groups":groups, "copies":copies,
            "microstate_count":n, "directed_edge_count":8*n, "seed":seed,
            "weights":[list(w) for w in weights], "field":self.field,
            "law":"source-synapse-statistics-to-two-ring-successors-4-edges-each-v1",
            "addressing":"source-pinned-affine-permutation-of-microstates-v1",
            "scope":"synthetic-sparse-ground-not-the-original-connectome-dynamics",
        }
        self.fingerprint = hash_object(self.description)
        self._factors = tuple((
            a0 * pow(4*(a0+b0),-1,MODULUS) % MODULUS,
            b0 * pow(4*(a0+b0),-1,MODULUS) % MODULUS)
            for a0,b0 in weights)

    def internal(self, visible: int) -> int:
        insist(type(visible) is int and 0 <= visible < self.n, "unknown microstate")
        return (visible*self._a+self._b) % self.n

    def visible(self, internal: int) -> int:
        return ((internal-self._b)*self._inverse) % self.n

    def output_mask(self) -> list[int]:
        """Explicit observer channel: aggregate group zero, not hidden labels."""
        return [int(self.internal(i)//self.copies == 0) for i in range(self.n)]

    def outgoing(self, visible: int) -> tuple[tuple[int,int], ...]:
        internal = self.internal(visible)
        g,j = divmod(internal,self.copies)
        c = self.copies
        w1,w2 = self._factors[g]
        offset = ((g+1)*71+self.seed*17) % c
        return tuple(
            (self.visible(((g+1+side) % self.groups)*c +
                          ((j*5+offset+side*23+slot) % c)), w1 if side == 0 else w2)
            for side in range(2) for slot in range(4)
        )

    def transpose_step(self, row: list[int]) -> list[int]:
        insist(isinstance(row,list) and len(row)==self.n and
               all(type(v) is int and 0<=v<self.field for v in row),
               "invalid synthetic observer row")
        p=self.field
        return [sum(w*row[dst] for dst,w in self.outgoing(i))%p for i in range(self.n)]

    def step(self, state: list[int]) -> list[int]:
        insist(isinstance(state,list) and len(state)==self.n and
               all(type(v) is int and 0<=v<self.field for v in state),
               "invalid synthetic microstate vector")
        out=[0]*self.n
        for src,val in enumerate(state):
            if val:
                for dst,w in self.outgoing(src):
                    out[dst]=(out[dst]+val*w)%self.field
        return out



class DirectSourceOperator:
    """Observe the *unmodified* pinned connectome; a negative compression control.

    A valid learned quotient is accepted only after the same full-edge check.
    The experiment makes no promise that a 448-label biological graph admits a
    small partition for the chosen output channel.
    """
    def __init__(self,source:ConnectomeGround,*,target:str,kind:str='chemical'):
        insist(isinstance(source,ConnectomeGround) and target in source.nodes,
               'unavailable original-source output channel')
        internal=SparseTransfer.from_ground(source,source=sorted(source.nodes)[0],
                                            target=target,kind=kind)
        self.op=internal
        self.n,self.field=internal.n,internal.field
        self.source_fingerprint,self.source_blob=source.fingerprint,source.source_blob
        self.description={
            'schema':SCHEMA+'.direct-source.v1','source_ground':source.fingerprint,
            'source_blob':source.source_blob,'source_label_count':internal.n,
            'directed_edge_count':internal.sparse_edge_count,'field':internal.field,
            'target':target,'kind':kind,
            'scope':'unaltered-original-connectome-mathematical-field-interpretation',
        }
        self.fingerprint=hash_object(self.description)
        self._mask=[int(name==target) for name in internal.names]

    def output_mask(self)->list[int]:
        return self._mask.copy()

    def outgoing(self,src:int)->tuple[tuple[int,int],...]:
        insist(type(src) is int and 0<=src<self.n,'unknown original node')
        return self.op.column_edges[src]

    def transpose_step(self,row:list[int])->list[int]:
        insist(type(row) is list and len(row)==self.n and
               all(type(z) is int and 0<=z<self.field for z in row),
               'invalid direct-source observer row')
        return [sum(w*row[dst] for dst,w in self.outgoing(i))%self.field for i in range(self.n)]

    def step(self,state:list[int])->list[int]:
        return self.op.step(state)

def _canonical_partition(signatures: list[tuple[int, ...]]) -> tuple[list[int],int]:
    unique=sorted(set(signatures))
    groups={sig:i for i,sig in enumerate(unique)}
    return [groups[s] for s in signatures],len(unique)


def _equitable(op: ExpandedSyntheticGround | DirectSourceOperator, partition: list[int],
               group_count: int, mask: list[int]) -> tuple[tuple[tuple[int,int],...],...]:
    """Independent full-column check P M = Q P over the entire micrograph."""
    insist(type(group_count) is int and 1 <= group_count <= MAX_GROUPS and
           isinstance(partition,list) and len(partition)==op.n and
           all(type(v) is int and 0 <= v < group_count for v in partition) and
           set(partition)==set(range(group_count)), "invalid candidate partition")
    signatures: list[tuple[int,tuple[tuple[int,int],...]]|None] = [None]*group_count
    p=op.field
    for src,g in enumerate(partition):
        agg: dict[int,int]={}
        for dst,w in op.outgoing(src):
            h=partition[dst]
            agg[h]=(agg.get(h,0)+w)%p
        signature=(mask[src], tuple(sorted((h,w) for h,w in agg.items() if w)))
        if signatures[g] is None:
            signatures[g]=signature
        else:
            insist(signatures[g]==signature,
                   "intertwining violated: purported equivalent internal states differ")
    return tuple(sig[1] for sig in signatures if sig is not None)


def _pack_partition(partition: list[int]) -> str:
    insist(all(0<=v<=255 for v in partition),"partition byte coding budget")
    return base64.b64encode(zlib.compress(bytes(partition),level=9)).decode("ascii")


def _unpack_partition(packed: Any, n: int) -> list[int]:
    insist(type(packed) is str and len(packed) <= MAX_NODES*3,
           "invalid partition transport size")
    try:
        raw=base64.b64decode(packed,validate=True)
        decomp=zlib.decompressobj()
        data=decomp.decompress(raw,max_length=n+1)
        insist(decomp.eof and not decomp.unused_data and not decomp.unconsumed_tail and
               len(data)==n and _pack_partition(list(data))==packed,
               "noncanonical or oversized partition encoding")
        return list(data)
    except (ValueError,zlib.error) as err:
        raise QuotientRefused("invalid compressed partition") from err


def discover(op: ExpandedSyntheticGround | DirectSourceOperator, *, horizon: int = 32) -> dict[str,Any]:
    """Infer grouped microstate response signatures, then require global proof.

    The learner observes the *one target readout* under many hypothetical
    starting states by applying the transpose. It neither reads nor receives
    the hidden generator's group coordinate. Failed candidate partitions are
    never promoted to Grounds.
    """
    insist(isinstance(op,(ExpandedSyntheticGround,DirectSourceOperator)) and type(horizon) is int and
           1 <= horizon <= 64, "unsupported observation horizon")
    row=op.output_mask()
    signatures=[(v,) for v in row]
    row_hashes=[hash_object(row)]
    group_history=[]
    prev=-1
    for step in range(horizon+1):
        partition,k = _canonical_partition(signatures)
        group_history.append(k)
        if k>=2 and k<=MAX_GROUPS and k==prev:
            try:
                compressed=_equitable(op,partition,k,op.output_mask())
            except QuotientRefused:
                pass
            else:
                body={
                    "schema":SCHEMA+".certificate.v1",
                    "expanded":op.description,"expanded_digest":op.fingerprint,
                    "readout":"sum-of-declared-output-channel-zero-microstates",
                    "training_type":"exact-temporal-response-signature-partition-refinement",
                    "training_horizon":step,
                    "observation_row_digests":row_hashes,
                    "classes_per_horizon":group_history,
                    "microstates":op.n,"class_count":k,
                    "partition_deflate_b64":_pack_partition(partition),
                    "quotient_columns":[[list(x) for x in column] for column in compressed],
                    "assurance":"complete-source-column-check-PM=QP-plus-observer-readout",
                    "training_claim":"deterministic-synthetic-observation-learning-not-trained-neural-weights",
                }
                return {**body,"digest":hash_object(body)}
        if step==horizon:
            break
        prev=k
        row=op.transpose_step(row)
        row_hashes.append(hash_object(row))
        signatures=[sig+(v,) for sig,v in zip(signatures,row)]
    raise QuotientRefused("no globally verified low-dimensional observer quotient")


def verify(op: ExpandedSyntheticGround | DirectSourceOperator, certificate: dict[str,Any], *,
           replay_observations: bool = True) -> tuple[list[int],tuple[tuple[tuple[int,int],...],...]]:
    """Receiver-owned proof: no trust in producer's training or stated Q."""
    require_fields={"schema","expanded","expanded_digest","readout","training_type",
                    "training_horizon","observation_row_digests","classes_per_horizon",
                    "microstates","class_count","partition_deflate_b64",
                    "quotient_columns","assurance","training_claim","digest"}
    insist(isinstance(op,(ExpandedSyntheticGround,DirectSourceOperator)) and type(certificate) is dict and
           set(certificate)==require_fields and
           certificate["schema"]==SCHEMA+".certificate.v1" and
           certificate["expanded"]==op.description and
           certificate["expanded_digest"]==op.fingerprint and
           certificate["readout"]=="sum-of-declared-output-channel-zero-microstates" and
           certificate["training_type"]=="exact-temporal-response-signature-partition-refinement" and
           certificate["assurance"]=="complete-source-column-check-PM=QP-plus-observer-readout" and
           certificate["training_claim"]=="deterministic-synthetic-observation-learning-not-trained-neural-weights" and
           certificate["microstates"]==op.n and
           certificate["digest"]==hash_object({k:v for k,v in certificate.items() if k!='digest'}),
           "receiver refuses source, semantic or certificate identity")
    n=op.n
    k=certificate["class_count"]
    h=certificate["training_horizon"]
    insist(type(h) is int and 1<=h<=64 and type(k) is int and 2<=k<=MAX_GROUPS and
           type(certificate["classes_per_horizon"]) is list and
           len(certificate["classes_per_horizon"])==h+1 and
           type(certificate["observation_row_digests"]) is list and
           len(certificate["observation_row_digests"])==h+1 and
           all(type(c) is str and len(c)==64 for c in certificate["observation_row_digests"]) and
           all(type(v) is int and 1<=v<=MAX_GROUPS for v in certificate["classes_per_horizon"]) and
           certificate["classes_per_horizon"][-1]==k,
           "unreconstructable observation transcript")
    partition=_unpack_partition(certificate["partition_deflate_b64"],n)
    q=_equitable(op,partition,k,op.output_mask())
    insist(certificate["quotient_columns"]==[[list(x) for x in col] for col in q],
           "quotient coefficients are not the full-source weighted aggregation")
    if replay_observations:
        row=op.output_mask()
        signatures=[(v,) for v in row]
        for t in range(h+1):
            p,observed_classes=_canonical_partition(signatures)
            insist(hash_object(row)==certificate["observation_row_digests"][t] and
                   observed_classes==certificate["classes_per_horizon"][t],
                   "observed training trace changed")
            if t==h:
                insist(p==partition,"claimed learner partition differs from observed signatures")
            else:
                row=op.transpose_step(row)
                signatures=[old+(value,) for old,value in zip(signatures,row)]
    return partition,q


def quotient_operator(op: ExpandedSyntheticGround | DirectSourceOperator, certificate: dict[str,Any],
                      source_micro: int, *, trusted: tuple[list[int],tuple]|None=None) -> tuple[SparseTransfer,int]:
    partition,q=trusted if trusted is not None else verify(op,certificate)
    insist(type(source_micro) is int and 0<=source_micro<op.n, "source address outside Ground")
    source_class=partition[source_micro]  # externally named microstate
    names=tuple(f"observable.{i:03d}" for i in range(len(q)))
    readout_class=partition[next(i for i,v in enumerate(op.output_mask()) if v)]
    ground_id=certificate["digest"]
    operator=SparseTransfer(source=names[source_class],target=names[readout_class],
                            kind='chemical',ground=ground_id,blob=op.source_blob,
                            field=op.field,n=len(q),names=names,column_edges=q)
    return operator,source_class


def micro_observation(op:ExpandedSyntheticGround,partition:list[int],
                      source_micro:int,tick:int)->list[int]:
    insist(type(tick) is int and 0<=tick<=24, "full microstate oracle is bounded")
    insist(type(source_micro) is int and 0<=source_micro<op.n,"invalid source address")
    s=[0]*op.n
    s[source_micro]=1
    for _ in range(tick):
        s=op.step(s)
    result=[0]*(max(partition)+1)
    for node,weight in enumerate(s):
        result[partition[node]]=(result[partition[node]]+weight)%op.field
    return result


def quotient_at(op:ExpandedSyntheticGround,certificate:dict[str,Any],
                source_micro:int,tick:int,*,depth:int=6,
                trusted:tuple[list[int],tuple]|None=None)->dict[str,Any]:
    from conjugate_ground import ConjugatedGround,prepare_shared,verify_shared,navigate
    partition,q=trusted if trusted is not None else verify(op,certificate)
    operator,g=quotient_operator(op,certificate,source_micro,trusted=(partition,q))
    insist(type(depth) is int and 1<=depth<operator.n,"invalid neural decoder depth")
    positions=[(g+i)%operator.n for i in range(depth+1)]
    model=ConjugatedGround(operator,tuple(operator.names[j] for j in positions),
                           seed="rcg006-observer-quotient-neural-v1")
    shared=prepare_shared(model,attempts=4)
    verify_shared(model,shared)
    result=navigate(model,shared,tick,trusted_certificate=True)
    body={"schema":SCHEMA+".navigated-neural-readout.v1",
          "original_source":op.source_fingerprint,"expanded_digest":op.fingerprint,
          "quotient_certificate":certificate["digest"],
          "source_micro":source_micro,"source_observer_class":g,
          "microstate_count":op.n,"quotient_dimension":len(q),
          "decoder_depth":depth,"logical_tick":tick,
          "neural_model":model.description,"neural_certificate":shared,
          "neural_result":result,
          "microstate_vectors_realized_for_query":0,
          "scope":"exact finite-field derived synthetic model, no physical host invoked"}
    return {**body,"digest":hash_object(body)}


def verify_query(op:ExpandedSyntheticGround,certificate:dict[str,Any],
                 report:dict[str,Any],*,trusted:tuple[list[int],tuple]|None=None)->None:
    insist(type(report) is dict and set(report)=={
        'schema','original_source','expanded_digest','quotient_certificate','source_micro',
        'source_observer_class','microstate_count','quotient_dimension','decoder_depth',
        'logical_tick','neural_model','neural_certificate','neural_result',
        'microstate_vectors_realized_for_query','scope','digest'},
        "malformed neural observation")
    reference=quotient_at(op,certificate,report['source_micro'],report['logical_tick'],
                          depth=report['decoder_depth'],trusted=trusted)
    insist(report==reference,"independent source-owned neural observation disagrees")
