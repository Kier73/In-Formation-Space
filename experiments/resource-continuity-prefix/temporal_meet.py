"""RCP-002: recover a nontrivial common causal interpretation from forked VL-I.

Use the ORIGINAL VL-I TIME-001 observer, native exact-rational compiled processor
and independently checked source-observation history. Then use the ORIGINAL
E-CPU RecoveryLineageCoordinator to seal a real shared checkpoint, clone
its durable member journals at a later point, and commit two incompatible
histories. This module constructs neither a new quorum nor a neural model.

RCP-001 already treats external EFFECT authority separately. RCP-002 tests a
different missing property: whether the maximal shared history still carries
an executable and externally pinned mathematical interpretation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any

from mailcpu.recovery_lineage import (
    RecoveryLineageAuthority,RecoveryLineageCoordinator,
    RecoveryLineageError,RecoveryStateManifest,
)
from mailcpu.seed_commit_quorum import SeedCommitMembership
from vli.temporal_intelligence import (
    TemporalIntelligenceGround,
    verify_temporal_snapshot,verify_temporal_processor,
    verify_temporal_navigation,
)

SCHEMA="ifs.rcp002.nontrivial-temporal-causal-meet.v1"
SYSTEM="ifs-vli-temporal-fork-machine"
GENESIS=sha256(b"rcp002-externally-anchored-vli-environment").hexdigest()
OLD=("old-a","old-b","old-c")
NEW=("new-a","new-b","new-c")


class TemporalMeetRefused(ValueError):
    """An alleged shared interpretation lacks exact independent evidence."""


def _bytes(doc:Any)->bytes:
    return json.dumps(doc,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _sha(raw:bytes)->str:
    return sha256(raw).hexdigest()


def _observe(g:TemporalIntelligenceGround, i:int, v:int, *, host:str):
    """Supply external source identity explicitly, without claiming authentication."""
    t=f"{i}/1"
    value=f"{v}/1"
    source=_sha(f"{g.identity}|{t}|{value}|{host}".encode("ascii"))
    return g.observe(t,[value],source_digest=source,
                     host=host,expected_head=g.head)


def initial_ground()->TemporalIntelligenceGround:
    """Five exact observations qualify a meaningful affine law before the fork."""
    g=TemporalIntelligenceGround("rcp002:shared-environment")
    for i in range(5):
        _observe(g,i,2*i+1,host="source-host-A")
    if g.compile_epoch(0,expected_head=g.head)["rate"]!=["2/1"]:
        raise AssertionError("real observed source failed to qualify original law")
    return g


def fork_ground(original:TemporalIntelligenceGround):
    """Clone verified original evidence, then diverge under different observations."""
    seed=original.checkpoint()
    a=TemporalIntelligenceGround.restore(
        deepcopy(seed),expected_head=original.head,expected_identity=original.identity)
    b=TemporalIntelligenceGround.restore(
        deepcopy(seed),expected_head=original.head,expected_identity=original.identity)
    _observe(a,5,11,host="fork-host-A")
    _observe(b,5,30,host="fork-host-B")
    return a,b


def find_common_temporal_section(
    left:dict[str,Any],right:dict[str,Any], *,
    expected_identity:str,
    expected_left_head:str,
    expected_right_head:str,
    externally_pinned_common_head:str,
)->dict[str,Any]:
    """Independently rebuild the LONGEST exact event-digest common prefix.

    Not value-based equality: different source evidence, observer host or
    temporal ordering means different causal history even if numbers match.
    Both full snapshots must verify against separately pinned external heads
    before the common section is constructed.
    """
    for snapshot,head in ((left,expected_left_head),(right,expected_right_head)):
        try:
            verified=verify_temporal_snapshot(
                snapshot,expected_head=head,expected_identity=expected_identity,
            )
        except (TypeError,ValueError,KeyError) as exc:
            raise TemporalMeetRefused("source temporal checkpoint is not independently verified") from exc
        if verified is not True:
            raise TemporalMeetRefused("source temporal checkpoint was refused")
    if left["contract"]!=right["contract"]:
        raise TemporalMeetRefused("observers disagree about environment semantics")
    a,b=left["events"],right["events"]
    count=0
    for x,y in zip(a,b):
        if x["digest"]!=y["digest"]:
            break
        count+=1
    if count==0:
        raise TemporalMeetRefused("no reconstructable shared environment observation")
    observed_head=a[count-1]["digest"]
    if observed_head!=externally_pinned_common_head:
        raise TemporalMeetRefused("common prefix does not match external causal witness")
    contract=left["contract"]
    reconstituted=TemporalIntelligenceGround(
        contract["environment"],dimensions=contract["dimensions"],
        observer=contract["observer"],
    )
    for source in a[:count]:
        try:
            candidate=reconstituted.observe(
                source["time"],source["values"],
                source_digest=source["source_digest"],
                host=source["host"],expected_head=reconstituted.head,
            )
        except (ValueError,TypeError,KeyError) as exc:
            raise TemporalMeetRefused("shared causal evidence cannot be replayed") from exc
        if candidate!=source:
            raise TemporalMeetRefused("reconstructed event differs from original source")
    prefix=reconstituted.checkpoint()
    if not verify_temporal_snapshot(
        prefix,expected_head=observed_head,expected_identity=expected_identity,
    ):
        raise TemporalMeetRefused("common-prefix temporal Ground has no independent proof")
    # The first qualified law is independently reconstructed, not copied from
    # a source-selected predecessor processor with stale lineage-head pins.
    if count<3 or reconstituted.epochs[0]["status"]!="QUALIFIED_SAMPLES_ONLY":
        raise TemporalMeetRefused("common section has no qualified source-derived interpreter")
    processor=reconstituted.compile_epoch(0,expected_head=observed_head)
    if not verify_temporal_processor(
        prefix,processor,expected_head=observed_head,
        expected_identity=expected_identity,
    ):
        raise TemporalMeetRefused("reconstituted executable temporal law was refused")
    navigation=reconstituted.navigate(
        "5/2",epoch_index=0,expected_head=observed_head,
    )
    if (navigation["values"]!=["6/1"]
            or navigation["status"]!="UNVERIFIED_INTERPOLATION"
            or not verify_temporal_navigation(
                prefix,navigation,expected_head=observed_head,
                expected_identity=expected_identity,
            )):
        raise TemporalMeetRefused("common mathematical interpreter changed its semantics")
    return {
        "schema":SCHEMA,
        "identity":expected_identity,
        "common_event_count":count,
        "common_head":observed_head,
        "common_checkpoint":prefix,
        "common_checkpoint_sha256":_sha(_bytes(prefix)),
        "qualified_processor":processor,
        "verified_interpolation":navigation,
        "discarded_left_events":len(a)-count,
        "discarded_right_events":len(b)-count,
        "disputed_branch_winner":None,
    }


def original_membership()->SeedCommitMembership:
    return SeedCommitMembership(SYSTEM,1,OLD,"old-a",1,GENESIS)


def successor_membership(common_root:str)->SeedCommitMembership:
    """New externally installed authority set; no old cloned quorum authorizes it."""
    return SeedCommitMembership(SYSTEM,2,NEW,"new-a",2,common_root)


def _quorum(folder:Path,membership:SeedCommitMembership):
    folder.mkdir(parents=True,exist_ok=True)
    members={
        member:RecoveryLineageAuthority(
            membership,member,folder/(member+".jsonl"),
        ) for member in membership.member_ids
    }
    return RecoveryLineageCoordinator(membership,members)


def _manifest(membership:SeedCommitMembership,*,generation:int,
              predecessor:str,state:bytes)->RecoveryStateManifest:
    return RecoveryStateManifest(
        machine_id=membership.system_id,incarnation=membership.incarnation,
        owner_id=membership.owner_id,owner_term=membership.owner_term,
        membership_digest=membership.digest,
        generation=generation,
        predecessor_digest=predecessor,
        state_digest=_sha(state),
        capture_cut="after_response_publish",
    )


@dataclass(frozen=True)
class TemporalForkEvidence:
    """Original quorum objects, exact state payload bytes, and recovered prefix."""

    original_membership: SeedCommitMembership
    shared_manifest: RecoveryStateManifest
    left_manifest: RecoveryStateManifest
    right_manifest: RecoveryStateManifest
    left_directory: Path
    right_directory: Path
    meet: dict[str,Any]
    original_temporal_identity: str


def construct_real_temporal_quorum_fork(root:Path)->TemporalForkEvidence:
    """Seal actual E-CPU generation 1, CLONE journals, seal rival generation 2."""
    original=initial_ground()
    left,right=fork_ground(original)
    meet=find_common_temporal_section(
        left.checkpoint(),right.checkpoint(),
        expected_identity=original.identity,
        expected_left_head=left.head,expected_right_head=right.head,
        externally_pinned_common_head=original.head,
    )
    if meet["common_event_count"]!=5:
        raise AssertionError("source-generated fork lost its nontrivial shared section")
    membership=original_membership()
    common_bytes=_bytes(meet["common_checkpoint"])
    common_journals=root/"prior-members"
    coord=_quorum(common_journals,membership)
    shared=_manifest(membership,generation=1,
                     predecessor=GENESIS,state=common_bytes)
    coord.seal(shared)
    assert coord.high_water()==(1,shared.digest)
    # Fork the *durable authority storage* after a shared qualified generation,
    # not merely the in-memory interpretation of a model.
    manifests=[]
    directories=[]
    for suffix,ground in (("left",left),("right",right)):
        target=root/suffix
        shutil.copytree(common_journals,target)
        clone=_quorum(target,membership)
        latest=_manifest(
            membership,generation=2,predecessor=shared.digest,
            state=_bytes(ground.checkpoint()),
        )
        clone.seal(latest)
        assert clone.high_water()==(2,latest.digest)
        manifests.append(latest)
        directories.append(target)
    if manifests[0].digest==manifests[1].digest:
        raise AssertionError("two source-derived interpretations did not fork")
    return TemporalForkEvidence(
        membership,shared,manifests[0],manifests[1],
        directories[0],directories[1],meet,original.identity,
    )


def verify_forked_quorums(e:TemporalForkEvidence)->dict[str,Any]:
    """Reopen every E-CPU member journal; no fabricated proof flags accepted."""
    if e.left_manifest.predecessor_digest!=e.shared_manifest.digest or \
       e.right_manifest.predecessor_digest!=e.shared_manifest.digest:
        raise TemporalMeetRefused("actual fork does not share the qualified predecessor")
    if e.left_manifest.digest==e.right_manifest.digest:
        raise TemporalMeetRefused("fork roots are identical")
    for name,folder,head in (
        ("left",e.left_directory,e.left_manifest),
        ("right",e.right_directory,e.right_manifest),
    ):
        q=_quorum(folder,e.original_membership)
        try:
            proof=q.verify_state(head)
            latest=q.high_water()
        except RecoveryLineageError as exc:
            raise TemporalMeetRefused(f"{name} quorum is no longer independently verifiable") from exc
        if latest!=(2,head.digest) or proof.proposal.result_state_digest!=head.digest:
            raise TemporalMeetRefused("fork participant supplied stale quorum high-water")
    return {
        "original_system_id":e.original_membership.system_id,
        "original_membership_digest":e.original_membership.digest,
        "shared_quorum_root":e.shared_manifest.digest,
        "common_temporal_events":e.meet["common_event_count"],
        "common_temporal_head":e.meet["common_head"],
        "new_rights_from_old_forks":False,
        "forked_quorum_roots":[e.left_manifest.digest,e.right_manifest.digest],
        "global_winner":None,
    }


def reconstitute_semantic_interpreter(
    e:TemporalForkEvidence, root:Path,
)->tuple[TemporalIntelligenceGround,RecoveryStateManifest]:
    """Rebuild a meaningful Ground, then seal independently authorized E-CPU state.

    The common checkpoint's exact bytes are independently hashed and checked
    against the original *quorum-published* shared manifest. The new quorum
    incarnation must be separately provisioned; this is not an old-fork vote.
    """
    verify_forked_quorums(e)
    meet=e.meet
    original_bytes=_bytes(meet["common_checkpoint"])
    if _sha(original_bytes)!=e.shared_manifest.state_digest:
        raise TemporalMeetRefused("shared prefix does not match original quorum-pinned bytes")
    recovered=TemporalIntelligenceGround.restore(
        meet["common_checkpoint"],
        expected_head=meet["common_head"],
        expected_identity=e.original_temporal_identity,
    )
    if (recovered.identity!=e.original_temporal_identity
            or len(recovered.events)!=5
            or recovered.compile_epoch(0,expected_head=recovered.head)["rate"]!=["2/1"]):
        raise TemporalMeetRefused("recovery lost the previously learned interpreter")
    membership=successor_membership(e.shared_manifest.digest)
    fresh=_quorum(root/"new-members",membership)
    manifest=_manifest(membership,generation=1,
                      predecessor=e.shared_manifest.digest,state=original_bytes)
    try:
        fresh.seal(manifest)
        if fresh.high_water()!=(1,manifest.digest):
            raise RecoveryLineageError("fresh quorum root mismatch")
        fresh.verify_state(manifest)
        # The old generation-two roots must be rejected by new authority.
        for old in (e.left_manifest,e.right_manifest):
            try:
                fresh.verify_state(old)
            except RecoveryLineageError:
                continue
            raise TemporalMeetRefused("old cloned root was misadmitted under new membership")
    except RecoveryLineageError as exc:
        raise TemporalMeetRefused("new quorum reconstitution did not qualify") from exc
    return recovered,manifest


def observe_new_environment(
    recovered:TemporalIntelligenceGround,
)->TemporalIntelligenceGround:
    """Continue at new host with fresh observations; do NOT select fork A/B."""
    for t,value in ((5,20),(6,21),(7,22)):
        _observe(recovered,t,value,host="fresh-observer-host-C")
    if (recovered.epochs[0]["status"]!="QUALIFIED_SAMPLES_ONLY"
            or recovered.epochs[1]["status"]!="QUALIFIED_SAMPLES_ONLY"
            or recovered.compile_epoch(0,expected_head=recovered.head)["rate"]!=["2/1"]
            or recovered.compile_epoch(1,expected_head=recovered.head)["rate"]!=["1/1"]):
        raise TemporalMeetRefused("fresh environment failed to generate its new interpreter")
    return recovered
