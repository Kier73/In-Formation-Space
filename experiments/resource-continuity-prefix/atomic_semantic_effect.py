"""RCP-003: source-qualified interpretation AND effect authority become one receipt.

This receiver composes the *original* E-CPU quorum and VL-I TIME-001 source
verification from RCP-002 with the receiver-owned SQLite atomic effect
admission from RCP-001. Neither a valid mathematical processor nor a quorum
proof alone authorizes the effect.

The receiver is a separately protected local failure domain. The protocol is
not safe if its SQLite database, bootstrap and trust root are cloned or rolled
back together; it does not authorize physical/remote effects or replace IPS-008.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from mailcpu.recovery_lineage import (
    RecoveryLineageError, RecoveryLineageCoordinator, RecoveryStateManifest,
)
from mailcpu.seed_commit_quorum import SeedCommitMembership
from vli.temporal_intelligence import (
    TemporalIntelligenceGround, verify_temporal_snapshot,
    verify_temporal_processor, verify_temporal_navigation,
)

from temporal_meet import (
    TemporalForkEvidence, TemporalMeetRefused,
    _bytes, _sha, _quorum, _manifest, initial_ground, fork_ground,
    find_common_temporal_section, construct_real_temporal_quorum_fork,
    successor_membership, verify_forked_quorums,
)

SCHEMA="ifs.rcp003.atomic-semantic-resource-continuation.v1"
RESOURCE="/ifs/rcp003/qualified-local-register"


class HandoffRefused(ValueError):
    """External evidence, receiver continuity or typed effect was not qualified."""


def _digest(value:Any)->str:
    return sha256(_bytes(value)).hexdigest()


def _hex(value:Any)->bool:
    return (type(value) is str and len(value)==64
            and all(x in "0123456789abcdef" for x in value))


def _atomic_json(path:Path, payload:dict)->None:
    """Retain immutable test evidence; receiver DB, not this file, owns effects."""
    raw=_bytes(payload)
    temp=path.with_name(path.name+".uncommitted")
    with open(temp,"wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp,path)


@dataclass(frozen=True)
class PersistedTemporalFork:
    """Original typed E-CPU journal references + exact branch source bytes."""
    evidence: TemporalForkEvidence
    left_checkpoint: dict
    right_checkpoint: dict


def create_workspace(root:Path)->PersistedTemporalFork:
    """Execute true VL-I source production and fork original E-CPU journals."""
    root.mkdir(parents=True,exist_ok=True)
    e=construct_real_temporal_quorum_fork(root)
    original=initial_ground()
    left,right=fork_ground(original)
    a,b=left.checkpoint(),right.checkpoint()
    if (_sha(_bytes(a))!=e.left_manifest.state_digest
            or _sha(_bytes(b))!=e.right_manifest.state_digest
            or _sha(_bytes(e.meet["common_checkpoint"]))!=e.shared_manifest.state_digest):
        raise HandoffRefused("source checkpoint bytes differ from actual quorum commitments")
    body={
        "schema":"ifs.rcp003.durable-fork-evidence.v1",
        "original_membership":e.original_membership.snapshot(),
        "shared_manifest":e.shared_manifest.snapshot(),
        "left_manifest":e.left_manifest.snapshot(),
        "right_manifest":e.right_manifest.snapshot(),
        "meet":e.meet,
        "temporal_identity":e.original_temporal_identity,
        "left_checkpoint":a,"right_checkpoint":b,
    }
    _atomic_json(root/"fork-evidence.json",body)
    return PersistedTemporalFork(e,a,b)


def load_workspace(root:Path)->PersistedTemporalFork:
    """A fresh OS process uses actual journal files, never a cached proof flag."""
    try:
        p=json.loads((root/"fork-evidence.json").read_text(encoding="utf8"))
        if type(p) is not dict or set(p)!={
            "schema","original_membership","shared_manifest","left_manifest",
            "right_manifest","meet","temporal_identity","left_checkpoint",
            "right_checkpoint",
        } or p["schema"]!="ifs.rcp003.durable-fork-evidence.v1":
            raise HandoffRefused("unsupported durable fork evidence")
        membership=SeedCommitMembership.from_snapshot(p["original_membership"])
        e=TemporalForkEvidence(
            membership,
            RecoveryStateManifest.from_snapshot(p["shared_manifest"]),
            RecoveryStateManifest.from_snapshot(p["left_manifest"]),
            RecoveryStateManifest.from_snapshot(p["right_manifest"]),
            root/"left",root/"right",p["meet"],p["temporal_identity"],
        )
        return PersistedTemporalFork(e,p["left_checkpoint"],p["right_checkpoint"])
    except (OSError,KeyError,TypeError,ValueError,json.JSONDecodeError) as exc:
        raise HandoffRefused("durable fork evidence cannot be reconstructed") from exc


def qualify_common_context(p:PersistedTemporalFork, *,
                           expected_identity:str, expected_temporal_head:str,
                           expected_common_root:str, expected_old_membership:str
                           )->dict[str,Any]:
    """Verify real conflicting quorums, BOTH source histories, and exact prefix.

    Do not accept an untrusted caller's precomputed "meet" or fork proof alone.
    Full branch snapshots are required to match original committed E-CPU state
    hashes; the common history is reconstructed independently by VL-I.
    """
    e=p.evidence
    if (not _hex(expected_identity) or not _hex(expected_temporal_head)
            or not _hex(expected_common_root) or not _hex(expected_old_membership)
            or e.original_temporal_identity!=expected_identity
            or e.original_membership.digest!=expected_old_membership
            or e.shared_manifest.digest!=expected_common_root
            or e.shared_manifest.generation!=1
            or e.left_manifest.generation!=2 or e.right_manifest.generation!=2):
        raise HandoffRefused("fork does not match independently pinned source identity")
    try:
        fork=verify_forked_quorums(e)
        a,b=p.left_checkpoint,p.right_checkpoint
        if (_sha(_bytes(a))!=e.left_manifest.state_digest
                or _sha(_bytes(b))!=e.right_manifest.state_digest):
            raise HandoffRefused("actual fork state bytes do not match quorum manifests")
        checked=find_common_temporal_section(
            a,b,expected_identity=expected_identity,
            expected_left_head=a["head"],expected_right_head=b["head"],
            externally_pinned_common_head=expected_temporal_head,
        )
        if _bytes(checked)!=_bytes(e.meet):
            raise HandoffRefused("untrusted common-prefix report differs from independent verifier")
        common=checked["common_checkpoint"]
        if _sha(_bytes(common))!=e.shared_manifest.state_digest:
            raise HandoffRefused("shared original quorum is not pinned to checkpoint bytes")
        if not verify_temporal_snapshot(
            common,expected_head=expected_temporal_head,
            expected_identity=expected_identity,
        ) or not verify_temporal_processor(
            common,checked["qualified_processor"],
            expected_head=expected_temporal_head,
            expected_identity=expected_identity,
        ):
            raise HandoffRefused("semantic source-derived interpretation unqualified")
    except (TemporalMeetRefused,RecoveryLineageError,KeyError,TypeError,ValueError) as exc:
        raise HandoffRefused("independent temporal/quorum qualification failed") from exc
    if (fork["global_winner"] is not None
            or checked["common_event_count"]<3
            or checked["discarded_left_events"]<1
            or checked["discarded_right_events"]<1):
        raise HandoffRefused("source does not contain a qualified disputed late fork")
    witness={
        "schema":"ifs.rcp003.qualified-common-context.v1",
        "common_quorum_root":expected_common_root,
        "source_identity":expected_identity,
        "causal_head":expected_temporal_head,
        "original_membership":expected_old_membership,
        "fork_roots":sorted(fork["forked_quorum_roots"]),
        "shared_events":checked["common_event_count"],
        "checkpoint_sha256":checked["common_checkpoint_sha256"],
        "processor_digest":checked["qualified_processor"]["processor_digest"],
        "new_membership_digest":successor_membership(expected_common_root).digest,
        "no_fork_winner":True,
    }
    witness["digest"]=_digest(witness)
    return {"witness":witness,"checkpoint":common,
            "processor":checked["qualified_processor"]}


class AtomicSemanticResourceReceiver:
    """Single protected destination linearizes interpretation + effect authority."""

    def __init__(self, database:str|Path, *, resource:str,
                 source_identity:str, temporal_head:str, common_quorum_root:str,
                 original_membership_digest:str, successor_membership_digest:str,
                 native_guard:Mapping[str,str]|None=None):
        if type(resource) is not str or resource!=RESOURCE:
            raise HandoffRefused("receiver resource is not independently provisioned")
        self.path=Path(database)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.policy={
            "schema":SCHEMA, "resource":resource,
            "source_identity":source_identity,"temporal_head":temporal_head,
            "common_quorum_root":common_quorum_root,
            "original_membership":original_membership_digest,
            "successor_membership":successor_membership_digest,
        }
        if native_guard is None:
            self.policy["ips008_native_guard"]=None
        elif (isinstance(native_guard,Mapping)
              and set(native_guard)=={"resource","plan_digest","source_root","target_host","target_epoch"}
              and type(native_guard["resource"]) is str
              and native_guard["resource"].startswith("/")
              and len(native_guard["resource"])<=128
              and _hex(native_guard["plan_digest"])
              and _hex(native_guard["source_root"])
              and type(native_guard["target_host"]) is str
              and 1<=len(native_guard["target_host"])<=128
              and type(native_guard["target_epoch"]) is int
              and native_guard["target_epoch"]>=2):
            self.policy["ips008_native_guard"]={
                "resource":native_guard["resource"],
                "plan_digest":native_guard["plan_digest"],
                "source_root":native_guard["source_root"],
                "target_host":native_guard["target_host"],
                "target_epoch":native_guard["target_epoch"],
            }
        else:
            raise HandoffRefused("invalid independently provisioned IPS-008 native guard")
        for key in ("source_identity","temporal_head","common_quorum_root",
                    "original_membership","successor_membership"):
            if not _hex(self.policy[key]):
                raise HandoffRefused("receiver trust bootstrap has invalid identity")
        if successor_membership(common_quorum_root).digest!=successor_membership_digest:
            raise HandoffRefused("successor membership is not provisioned by the receiver")
        self.policy_json=_bytes(self.policy).decode("ascii")
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS handoff_policy (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS handoff_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    revision INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    context_digest TEXT,
                    successor_root TEXT,
                    checkpoint_sha256 TEXT,
                    processor_digest TEXT,
                    causal_head TEXT,
                    checkpoint_json TEXT,
                    native_root TEXT
                );
                CREATE TABLE IF NOT EXISTS handoff_effects (
                    operation_id TEXT PRIMARY KEY,
                    epoch INTEGER NOT NULL,
                    successor_root TEXT NOT NULL,
                    context_digest TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    navigation_digest TEXT NOT NULL,
                    receipt_json TEXT NOT NULL
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT document FROM handoff_policy WHERE singleton=1").fetchone()
                if row is None:
                    db.execute("INSERT INTO handoff_policy VALUES (1,?)",(self.policy_json,))
                    db.execute(
                        "INSERT INTO handoff_state VALUES "
                        "(1,0,'unprepared',NULL,NULL,NULL,NULL,NULL,NULL,NULL)"
                    )
                elif row[0]!=self.policy_json:
                    raise HandoffRefused("receiver trust bootstrap changed")
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _connect(self)->sqlite3.Connection:
        db=sqlite3.connect(str(self.path),timeout=8,isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=8000")
        return db

    @staticmethod
    def _state(db:sqlite3.Connection)->tuple:
        row=db.execute(
            "SELECT revision,mode,context_digest,successor_root,"
            "checkpoint_sha256,processor_digest,causal_head,checkpoint_json,native_root "
            "FROM handoff_state WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise HandoffRefused("receiver high-water missing")
        return row

    def _check_ips008_guard(self,db:sqlite3.Connection,root:str|None)->None:
        """Validate IPS-008 installed *published* root under THIS same DB lock.

        The original IPS-008 mTLS service owns the exact host/quorum barrier.
        This adapter cannot install, unfreeze or invent that native authority.
        """
        policy=self.policy["ips008_native_guard"]
        if policy is None:
            if root is not None:
                raise HandoffRefused("native IPS-008 root supplied to an unguarded receiver")
            return
        if not _hex(root):
            raise HandoffRefused("exact current native IPS-008 root required")
        try:
            binding=db.execute(
                "SELECT root,plan_digest,event,epoch,host FROM installed_authority WHERE resource=?",
                (policy["resource"],),
            ).fetchone()
            pending=db.execute(
                "SELECT 1 FROM effect_handoffs WHERE resource=?",
                (policy["resource"],),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise HandoffRefused("native IPS-008 receiver not provisioned") from exc
        if (binding!=(root,policy["plan_digest"],"publish",
                     policy["target_epoch"],policy["target_host"])
                or root==policy["source_root"] or pending is not None):
            raise HandoffRefused("native receiver is stale, frozen or unpublished")

    def _qualified(self,p:PersistedTemporalFork)->dict[str,Any]:
        return qualify_common_context(
            p,
            expected_identity=self.policy["source_identity"],
            expected_temporal_head=self.policy["temporal_head"],
            expected_common_root=self.policy["common_quorum_root"],
            expected_old_membership=self.policy["original_membership"],
        )

    def freeze(self,p:PersistedTemporalFork)->dict[str,Any]:
        """One durable resource-local barrier fences BOTH old quorum branches."""
        qualified=self._qualified(p)
        witness=qualified["witness"]
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rev,mode,context,root,sha,proc,head,bytes_,current_native_root=self._state(db)
                if mode=="unprepared" and rev==0:
                    db.execute(
                        "UPDATE handoff_state SET revision=1,mode='frozen',"
                        "context_digest=?,checkpoint_sha256=?,"
                        "processor_digest=?,causal_head=?,checkpoint_json=? "
                        "WHERE singleton=1",
                        (witness["digest"],witness["checkpoint_sha256"],
                         witness["processor_digest"],witness["causal_head"],
                         _bytes(qualified["checkpoint"]).decode("ascii")),
                    )
                elif (mode not in ("frozen","active")
                      or context!=witness["digest"]
                      or sha!=witness["checkpoint_sha256"]
                      or proc!=witness["processor_digest"]
                      or head!=witness["causal_head"]):
                    raise HandoffRefused("different fork cannot replace installed freeze")
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {"schema":"ifs.rcp003.receiver-freeze.v1",
                "resource":RESOURCE,"context_digest":witness["digest"],
                "state":"frozen_or_already_active","old_forks_effect_eligible":False}

    def activate(self,p:PersistedTemporalFork, *,
                 quorum:RecoveryLineageCoordinator,
                 manifest:RecoveryStateManifest,
                 native_root:str|None=None)->dict[str,Any]:
        """Atomic *one-row* binding of semantic capsule and successor effect epoch.

        Verification happens outside the SQLite transaction, but any effect is
        gated by its installed exact root/context/epoch inside the same writer
        lock as the resulting SQLite effect. No effect is allowed in the
        intermediate window after the external quorum seal.
        """
        qualified=self._qualified(p)
        e=p.evidence
        membership=successor_membership(e.shared_manifest.digest)
        if (not isinstance(quorum,RecoveryLineageCoordinator)
                or quorum.membership.snapshot()!=membership.snapshot()
                or not isinstance(manifest,RecoveryStateManifest)
                or manifest.machine_id!=membership.system_id
                or manifest.incarnation!=membership.incarnation
                or manifest.owner_id!=membership.owner_id
                or manifest.owner_term!=membership.owner_term
                or manifest.membership_digest!=self.policy["successor_membership"]
                or manifest.generation!=1
                or manifest.predecessor_digest!=e.shared_manifest.digest
                or manifest.state_digest!=qualified["witness"]["checkpoint_sha256"]):
            raise HandoffRefused("new quorum does not reconstitute exact qualified Ground")
        try:
            quorum.verify_state(manifest)
            if quorum.high_water()!=(1,manifest.digest):
                raise HandoffRefused("new quorum is not current")
        except RecoveryLineageError as exc:
            raise HandoffRefused("new quorum lacks exact independent high-water") from exc
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rev,mode,context,root,sha,proc,head,bytes_,current_native_root=self._state(db)
                if context!=qualified["witness"]["digest"]:
                    raise HandoffRefused("receiver was not frozen for this exact common Ground")
                self._check_ips008_guard(db,native_root)
                if (mode=="active" and rev==2 and root==manifest.digest
                        and current_native_root==native_root):
                    db.execute("COMMIT")
                elif mode=="frozen" and rev==1 and root is None:
                    # Atomic release of resource authority is *this* row
                    # update: new quorum root, exact semantic context, and
                    # source-state digests must become visible together.
                    db.execute(
                        "UPDATE handoff_state SET revision=2,mode='active',"
                        "successor_root=?,checkpoint_sha256=?,"
                        "processor_digest=?,causal_head=?,native_root=? WHERE singleton=1",
                        (manifest.digest,qualified["witness"]["checkpoint_sha256"],
                         qualified["witness"]["processor_digest"],
                         qualified["witness"]["causal_head"],native_root),
                    )
                    db.execute("COMMIT")
                else:
                    raise HandoffRefused("receiver epoch was altered or superseded")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {
            "schema":"ifs.rcp003.atomic-activation.v1",
            "receiver_epoch":2,
            "root":manifest.digest,
            "context_digest":qualified["witness"]["digest"],
            "checkpoint_sha256":qualified["witness"]["checkpoint_sha256"],
            "processor_digest":qualified["witness"]["processor_digest"],
            "old_forks_effect_eligible":False,
            "native_ips008_root":native_root,
            "effect_applied":False,
        }

    def apply(self, *, epoch:int, root:str, context_digest:str,
              operation_id:str, navigation:Mapping[str,Any])->dict[str,Any]:
        """One local effect commits iff its EXACT installed math + root match.

        The result is a local demonstration register, not automatic permission
        to act on the physical environment. Under BEGIN IMMEDIATE the receiver
        re-verifies a VL-I navigation proof against its durable qualified
        common checkpoint, and deduplicates the effect before committing.
        """
        if (type(epoch) is not int or epoch!=2
                or not _hex(root) or not _hex(context_digest)
                or type(operation_id) is not str or not 1<=len(operation_id)<=100
                or type(navigation) is not dict):
            raise HandoffRefused("effect requires exact typed installed context")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rev,mode,context,active,checkpoint_sha,proc,head,raw,native_root=self._state(db)
                if (rev!=epoch or mode!="active" or root!=active
                        or context_digest!=context or raw is None
                        or not _hex(checkpoint_sha) or not _hex(proc)):
                    raise HandoffRefused("semantic effect authority is frozen, stale or cloned")
                self._check_ips008_guard(db,native_root)
                snap=json.loads(raw)
                if _sha(_bytes(snap))!=checkpoint_sha:
                    raise HandoffRefused("receiver's pinned common checkpoint bytes changed")
                if not verify_temporal_snapshot(
                    snap,expected_head=head,
                    expected_identity=self.policy["source_identity"],
                ):
                    raise HandoffRefused("receiver persisted source evidence is invalid")
                restored=TemporalIntelligenceGround.restore(
                    snap,expected_head=head,
                    expected_identity=self.policy["source_identity"],
                )
                qualified=restored.compile_epoch(0,expected_head=head)
                if qualified["processor_digest"]!=proc:
                    raise HandoffRefused("receiver processor is not source-qualified")
                candidate=restored.navigate(
                    navigation.get("time",""),epoch_index=0,
                    expected_head=head,
                )
                if (_bytes(candidate)!=_bytes(navigation)
                        or candidate["status"]!="UNVERIFIED_INTERPOLATION"
                        or not verify_temporal_navigation(
                            snap,candidate,expected_head=head,
                            expected_identity=self.policy["source_identity"],
                        )):
                    raise HandoffRefused("effect navigation does not match admitted source law")
                value=candidate["values"]
                row=db.execute(
                    "SELECT epoch,successor_root,context_digest,value_json,"
                    "navigation_digest,receipt_json FROM handoff_effects "
                    "WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if row:
                    if row[:5]!=(epoch,root,context,_bytes(value).decode("ascii"),
                                 candidate["navigation_digest"]):
                        raise HandoffRefused("same effect ID has conflicting semantic content")
                    db.execute("COMMIT")
                    return json.loads(row[5])
                effect={
                    "schema":"ifs.rcp003.receiver-qualified-navigation-effect.v1",
                    "resource":RESOURCE,"receiver_epoch":epoch,"root":root,
                    "context_digest":context,"checkpoint_sha256":checkpoint_sha,
                    "processor_digest":proc,"navigation_digest":candidate["navigation_digest"],
                    "navigation_time":candidate["time"],
                    "value":value,"operation_id":operation_id,
                    "receiver_local_commit":True,
                    "source_observed_at_navigation":False,
                    "native_ips008_root":native_root,
                    "old_fork_winner_elected":False,
                    "external_effect_attested":False,
                }
                effect["digest"]=_digest(effect)
                db.execute(
                    "INSERT INTO handoff_effects VALUES (?,?,?,?,?,?,?)",
                    (operation_id,epoch,root,context,_bytes(value).decode("ascii"),
                     candidate["navigation_digest"],_bytes(effect).decode("ascii")),
                )
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return effect

    def snapshot(self)->dict[str,Any]:
        """Expose only resource-local truth, never an implicit global fork winner."""
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            try:
                rev,mode,context,root,sha,proc,head,raw,native_root=self._state(db)
                effects=db.execute("SELECT operation_id,receipt_json "
                                   "FROM handoff_effects ORDER BY operation_id").fetchall()
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {
            "schema":SCHEMA,"receiver_revision":rev,"mode":mode,
            "context_digest":context,"active_root":root,
            "checkpoint_sha256":sha,"processor_digest":proc,
            "causal_head":head,"committed_effects":len(effects),
            "native_ips008_root":native_root,
            "effect_history_digest":_digest([list(x) for x in effects]),
            "old_fork_winner":None,
        }


def open_receiver(root:Path)->AtomicSemanticResourceReceiver:
    """Receiver policy is pinned separately from mutable fork evidence JSON.

    This demonstration provisions it using the known pre-fork common head
    and shared original quorum manifest established during source setup.
    A real deployment MUST protect these bootstrap values independently.
    """
    original=initial_ground()
    # Immutable common state is derived again, never trusted from a branch.
    from temporal_meet import original_membership, _manifest, GENESIS
    common_bytes=_bytes(original.checkpoint())
    old=original_membership()
    common=_manifest(old,generation=1,predecessor=GENESIS,state=common_bytes)
    return AtomicSemanticResourceReceiver(
        root/"protected-receiver.sqlite3",
        resource=RESOURCE,
        source_identity=original.identity,
        temporal_head=original.head,
        common_quorum_root=common.digest,
        original_membership_digest=old.digest,
        successor_membership_digest=successor_membership(common.digest).digest,
    )


def seal_successor(root:Path,p:PersistedTemporalFork)->RecoveryStateManifest:
    """Crash-idempotent E-CPU seal: read high-water before sealing exact bytes."""
    e=p.evidence
    new=successor_membership(e.shared_manifest.digest)
    q=_quorum(root/"new-members",new)
    exact=_bytes(e.meet["common_checkpoint"])
    if _sha(exact)!=e.shared_manifest.state_digest:
        raise HandoffRefused("successor would seal tampered common bytes")
    manifest=_manifest(new,generation=1,
                       predecessor=e.shared_manifest.digest,state=exact)
    try:
        high=q.high_water()
        if high==(0,new.genesis_state_digest):
            q.seal(manifest)
        elif high!=(1,manifest.digest):
            raise HandoffRefused("different successor quorum root already installed")
        q.verify_state(manifest)
        if q.high_water()!=(1,manifest.digest):
            raise HandoffRefused("successor quorum has no independently verified high-water")
    except RecoveryLineageError as exc:
        raise HandoffRefused("successor E-CPU quorum refuses recovered interpretation") from exc
    return manifest


def navigation_for(root:Path)->dict[str,Any]:
    """Make a SOURCE-QUALIFIED demonstration navigation, not a physical reading."""
    original=initial_ground()
    return original.navigate("5/2",epoch_index=0,expected_head=original.head)


def continue_after_restart(root:Path)->dict[str,Any]:
    """Idempotent recovery from ANY durable cut using a fresh host context."""
    p=load_workspace(root)
    r=open_receiver(root)
    freeze=r.freeze(p)
    successor=seal_successor(root,p)
    quorum=_quorum(root/"new-members",successor_membership(p.evidence.shared_manifest.digest))
    activation=r.activate(p,quorum=quorum,manifest=successor)
    result=r.apply(
        epoch=2,root=activation["root"],
        context_digest=activation["context_digest"],
        operation_id="verified-sample-span-navigation",
        navigation=navigation_for(root),
    )
    current=r.snapshot()
    if (current["mode"]!="active" or current["committed_effects"]!=1
            or result["value"]!=["6/1"]
            or current["active_root"]!=successor.digest):
        raise HandoffRefused("continued receiver state was not qualified")
    return {
        "freeze":freeze,"activation":activation,
        "effect":result,"snapshot":current,
    }
