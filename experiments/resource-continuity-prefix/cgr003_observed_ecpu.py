"""CGR-003: source-witnessed NCR-004 Ground lowered to original IPS-004/005.

Only an *exactly discovered finite affine subfamily* may enter E-CPU's
existing affine stage runner. All transitions come from source witnesses.
The Hypervisor, native quorum, mTLS receiver and receiver-owned effect remain
unaltered. Neither this module nor an NCR-004 certificate mints effect rights.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path

from navigable_compute.observed_ground import (
    ObservedEpoch, TransitionObservation, SourceAdmission,
    admit_observed_epoch, navigate_observed,
)
from mailcpu.evidence_path_resolver import RouteMetric
from mailcpu.fenced_generated_ground import FencedGroundHead, FencedGroundLineage
from mailcpu.generative_ground_construction import (
    AffineBehaviorIntention, AffinePrimitive, GroundConstructionPlan,
    synthesize_ground,
)
from mailcpu.inverse_architecture_synthesis import ProposedRelation
from mailcpu.qualified_generated_ground import QualifiedGroundExecution
from mailcpu.recovery_lineage import RecoveryLineageCoordinator
from mailcpu.semantic_translation import RepresentationRef, canonical_value_digest

# Use original E-CPU quorum fixture authorities, not a parallel consensus.
from test_fenced_generated_ground import _membership, _authorities

SOURCE_FILE = "cgr003-source-epoch.json"
PIN_FILE = "cgr003-source-head.txt"
ACTIONS = ("first", "second")
RESOURCE = "/virtual-layer/effects/ips008-register"


class ObservedNativeRefused(ValueError):
    """Observed source, native plan or published stage was not qualified."""


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def persist_epoch(root: Path, epoch: ObservedEpoch) -> None:
    """One locally controlled supervisor pins a source before native boot."""
    root.mkdir(parents=True, exist_ok=True)
    if (root / SOURCE_FILE).exists() or (root / PIN_FILE).exists():
        raise ObservedNativeRefused("source policy already provisioned")
    for path, raw in ((root / SOURCE_FILE, _canonical(epoch.packet())),
                      (root / PIN_FILE, epoch.source_head.encode("ascii"))):
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def load_epoch(root: Path) -> ObservedEpoch:
    """Refuse source mutation against a separately provisioned local pin."""
    try:
        raw = (root / SOURCE_FILE).read_bytes()
        packet = json.loads(raw)
        if (type(packet) is not dict or set(packet) != {
                "schema", "source", "context", "states", "actions",
                "initial", "witnesses"} or
            packet["schema"] != "navigable-compute.observed-source-epoch.v0.1" or
            _canonical(packet) != raw):
            raise ObservedNativeRefused("noncanonical source record")
        witnesses = []
        fields = {"sequence", "before", "action", "after",
                  "before_output", "after_output"}
        for row in packet["witnesses"]:
            if type(row) is not dict or set(row) != fields:
                raise ObservedNativeRefused("source witness schema changed")
            witnesses.append(TransitionObservation(**row))
        epoch = ObservedEpoch(packet["source"], packet["context"],
                             tuple(packet["states"]), tuple(packet["actions"]),
                             tuple(packet["initial"]), tuple(witnesses))
        if epoch.source_head != (root / PIN_FILE).read_text(encoding="ascii"):
            raise ObservedNativeRefused("source differs from independently pinned epoch")
        return epoch
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ObservedNativeRefused("source bytes or local pin cannot be qualified") from exc


@dataclass(frozen=True)
class NativeObservedGround:
    """NCR Ground plus *native* E-CPU plan, no execution privilege."""

    source_head: str
    admission: SourceAdmission
    intention: AffineBehaviorIntention
    primitives: tuple[AffinePrimitive, ...]
    plan: GroundConstructionPlan

    @property
    def language_digest(self) -> str:
        return self.admission.language.digest


def construct_native(epoch: ObservedEpoch, *, expected_head: str) -> NativeObservedGround:
    """Discover both affine primitives from FULL witnessed finite transitions.

    This is a finite hypothesis-family admission, not arbitrary language
    synthesis. The E-CPU primitive definition is derived from the observations
    and checks against all states; no caller supplies its coefficients.
    """
    try:
        admission = admit_observed_epoch(epoch, expected_head=expected_head)
    except ValueError as exc:
        raise ObservedNativeRefused("native NCR-004 source admission failed") from exc
    states = admission.source.states
    if (epoch.actions != ACTIONS or len(states) != 17 or
        states != tuple(range(17)) or epoch.states != states or
        epoch.initial != (9,) or
        admission.source.outputs != tuple(str(s) for s in states)):
        raise ObservedNativeRefused("this native host requires exact 17-state identity observation")
    generators = admission.source.generators
    def successor(action: int, state: int) -> int:
        return states[generators[action][states.index(state)]]
    primitives = []
    for action, name in enumerate(ACTIONS):
        offset = successor(action, 0)
        multiplier = (successor(action, 1) - offset) % 17
        if any(successor(action, state) !=
               (multiplier * state + offset) % 17 for state in states):
            raise ObservedNativeRefused("witnessed law is not native finite affine")
        primitives.append(AffinePrimitive(name, 17, multiplier, offset))
    target = lambda x: successor(1, successor(0, x))
    relation = ProposedRelation(
        sha256(b"cgr003-relation:" + bytes.fromhex(expected_head)).hexdigest(),
        RepresentationRef.from_payload("cgr003.source", 1,
                                       {"source_head": expected_head}),
        RepresentationRef.from_payload("cgr003.output", 1,
                                       {"source_head": expected_head, "observation": "state"}),
        expected_head,
        sha256(epoch.context.encode("ascii")).hexdigest(),
        admission.language.digest,
        (RouteMetric("latency_us", "us", 1),),
    )
    intention = AffineBehaviorIntention(relation, 17, target(0), target(1), 9)
    palette = tuple(primitives)
    plan = synthesize_ground(intention, palette)
    if plan.primitive_names != ACTIONS or plan.status != "constructed_exact_affine_ground":
        raise ObservedNativeRefused("E-CPU did not synthesize the witnessed operation word")
    native_observation = navigate_observed(admission, expected_head=expected_head,
                                          initial=9, word=(0, 1), repetitions=1)
    if native_observation != str(target(9)):
        raise ObservedNativeRefused("native NCR-004 observation differs from E-CPU plan")
    return NativeObservedGround(expected_head, admission, intention, palette, plan)


def open_lineage(root: Path) -> FencedGroundLineage:
    """Reconstruct original native quorum with source-generated plan."""
    grounded = construct_native(load_epoch(root),
                                expected_head=(root / PIN_FILE).read_text("ascii"))
    membership = _membership()
    native = RecoveryLineageCoordinator(membership, _authorities(root, membership))
    return FencedGroundLineage(native, root / "artifacts", grounded.plan,
                               grounded.intention, grounded.primitives)


def verify_published(root: Path, head: FencedGroundHead) -> dict:
    """Reopen original quorum, replay original native DAG, match source edges.

    This content-bound receipt is deliberately NON-authoritative; the original
    IPS-008 receiver independently verifies quorum high-water and effect.
    """
    grounded = construct_native(load_epoch(root),
                                expected_head=(root / PIN_FILE).read_text("ascii"))
    publisher = open_lineage(root)
    current = publisher.restore(head)
    if (current.state["event"] != "publish" or
        current.state["plan_digest"] != grounded.plan.digest or
        current.state["intention_digest"] != grounded.intention.digest):
        raise ObservedNativeRefused("published native Ground differs from witnessed construction")
    session: QualifiedGroundExecution = publisher._session(current.checkpoint)
    records = current.checkpoint["payload"]["stages"]
    if not records:
        raise ObservedNativeRefused("native publication has no executed stages")
    observed = grounded.intention.query_input
    for index, record in enumerate(records):
        action = ACTIONS.index(grounded.plan.primitive_names[index])
        states = grounded.admission.source.states
        expected = states[grounded.admission.source.generators[action][states.index(observed)]]
        receipt = record["stage_receipt"]
        if (receipt["output"]["value"] != expected or
            record["hypervisor_effect"]["result"]["value"] != expected or
            record["index"] != index):
            raise ObservedNativeRefused("native Hypervisor result differs from source Ground")
        observed = expected
    if (records[-1]["stage_receipt"]["output"]["value"] != observed or
        (session.complete and session.value != observed)):
        raise ObservedNativeRefused("native final DAG disagrees with source mathematics")
    body = {
        "schema": "ifs.cgr003.observed-native-publication.v1",
        "source_head": grounded.source_head,
        "ncr004_language_sha256": grounded.language_digest,
        "ecpu_plan_digest": grounded.plan.digest,
        "ecpu_quorum_root": current.manifest.digest,
        "ecpu_generation": current.manifest.generation,
        "executed_stages": len(records),
        "observed_value": observed,
        "stage_receipt_digest": records[-1]["stage_receipt"]["receipt_digest"],
        "effect_authorized": False,
        "claim": "source-qualified-original-hypervisor-and-quorum;receiver-controls-effects",
    }
    return {**body, "sha256": canonical_value_digest(body)}
