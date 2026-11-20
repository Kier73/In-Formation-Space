"""RCP-001: fork-safe continuation at the resource, not cloned host authority.

Two locally valid E-CPU quorum histories can share IDENTICAL member names,
journals and TLS keys after an authority snapshot is cloned. This receiver
does not elect either history. It independently verifies both archived
quorums with the existing IFS DAD-001 checker, quarantines their disputed
slot, and admits effects ONLY after an external, independently installed
successor membership has sealed a new checkpoint from the *actual bytes* of
the last shared predecessor.

The receiver is a single locally protected SQLite authority. This is a
resource-scoped effect continuity experiment, not a global unique-authority
protocol, a replacement for IPS-008, or proof against cloned receiver storage.
"""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

from fork_detection import (
    GENESIS, SYSTEM_ID, ForkDetectionError, observe_two_clusters, digest,
)
from mailcpu.recovery_lineage import (
    RecoveryLineageCoordinator, RecoveryStateManifest, RecoveryLineageError,
)
from mailcpu.seed_commit_quorum import SeedCommitMembership

SCHEMA="ifs.rcp001.fork-safe-resource-continuation.v1"
SEED=b"ifs-duplicated-authority-domain-genesis-v1"


class ForkContinuityRefused(ValueError):
    """Refuse an unsupported fork, stale branch or ungrounded continuation."""


def _json(value: Any)->bytes:
    """Distinct typed values have distinct exact JSON representations."""
    try:
        return json.dumps(value,sort_keys=True,separators=(",",":"),
                          ensure_ascii=True,allow_nan=False).encode("ascii")
    except (ValueError,TypeError,UnicodeError) as exc:
        raise ForkContinuityRefused("invalid effect witness encoding") from exc


def _hash(value:Any)->str:
    return sha256(_json(value)).hexdigest()


def _sha(s: Any, label:str)->str:
    if (type(s) is not str or len(s)!=64
            or any(x not in "0123456789abcdef" for x in s)):
        raise ForkContinuityRefused(f"invalid {label}")
    return s


def successor_membership() -> SeedCommitMembership:
    """Out-of-fork *receiver-provisioned* membership, never inferred from clones.

    The former system ID remains the same, but the incarnation, members, term
    and trust domain change. Member names alone are not authentication.
    """
    return SeedCommitMembership(
        SYSTEM_ID,2,("successor-a","successor-b","successor-c"),
        "successor-a",2,GENESIS,
    )


class ForkSafeEffectReceiver:
    """One protected resource local linearization point across cloned histories."""

    def __init__(self, path: str|Path, *, resource: str,
                 old_membership_digest: str,
                 new_membership_digest: str) -> None:
        if type(resource) is not str or not resource.startswith("/") or len(resource)>128:
            raise ForkContinuityRefused("receiver resource identity invalid")
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.resource=resource
        self.policy={
            "schema":SCHEMA,"resource":resource,
            "old_membership":_sha(old_membership_digest,"original membership"),
            "new_membership":_sha(new_membership_digest,"receiver-provisioned successor"),
            "common_seed_digest":GENESIS,
        }
        self.policy_json=_json(self.policy).decode("ascii")
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS fork_effect_policy (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fork_effect_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    revision INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    fork_digest TEXT,
                    common_root TEXT,
                    new_root TEXT
                );
                CREATE TABLE IF NOT EXISTS fork_effect_log (
                    operation_id TEXT PRIMARY KEY,
                    epoch INTEGER NOT NULL,
                    root TEXT NOT NULL,
                    value INTEGER NOT NULL,
                    receipt_json TEXT NOT NULL
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT document FROM fork_effect_policy WHERE singleton=1").fetchone()
                if row is None:
                    db.execute("INSERT INTO fork_effect_policy VALUES (1,?)",(self.policy_json,))
                    db.execute(
                        "INSERT INTO fork_effect_state VALUES (1,0,'unobserved',NULL,NULL,NULL)"
                    )
                elif row[0]!=self.policy_json:
                    raise ForkContinuityRefused("resource trust bootstrap is immutable")
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _connect(self):
        db=sqlite3.connect(str(self.path),timeout=8,isolation_level=None)
        db.execute("PRAGMA busy_timeout=8000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def _state(self, db):
        row=db.execute(
            "SELECT revision,mode,fork_digest,common_root,new_root "
            "FROM fork_effect_state WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise ForkContinuityRefused("local resource authority was not initialized")
        return row

    def observe_and_freeze(self, left: Path, right: Path)->dict[str,Any]:
        """Independently replay genuine cloned quorum journals BEFORE freezing.

        The only semantically unambiguous predecessor in DAD-001's generation
        one fork is its original seed. Do not elect left/right by arrival time.
        """
        try:
            observed=observe_two_clusters(left,right)
        except (ForkDetectionError,RecoveryLineageError,ValueError) as exc:
            raise ForkContinuityRefused("cloned authority evidence did not verify") from exc
        if (observed["classification"]!="cloned_membership_split_brain"
                or observed["winner"] is not None
                or observed["membership_digest"]!=self.policy["old_membership"]
                or observed["predecessor_digest"]!=GENESIS
                or observed["generation"]!=1
                or not observed["same_generation_and_predecessor"]
                or not observed["each_cluster_reconstructed_its_own_quorum"]
                or not observed["left_rejects_right_manifest"]
                or not observed["right_rejects_left_manifest"]):
            raise ForkContinuityRefused("no qualified common-prefix cloned-authority fork")
        roots=tuple(sorted(c["root_digest"] for c in observed["clusters"]))
        if len(set(roots))!=2:
            raise ForkContinuityRefused("conflicting quorum roots required")
        witness={
            "schema":"ifs.rcp001.qualified-fork-witness.v1",
            "old_membership":self.policy["old_membership"],
            "common_prefix":GENESIS,
            "incompatible_roots":list(roots),
            "checkpoint_generation":1,
            "globally_legitimate_winner":None,
        }
        fork_digest=_hash(witness)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                revision,mode,known,common,head=self._state(db)
                if mode=="unobserved" and revision==0:
                    db.execute(
                        "UPDATE fork_effect_state SET revision=1, mode='quarantined', "
                        "fork_digest=?,common_root=?,new_root=NULL WHERE singleton=1",
                        (fork_digest,GENESIS),
                    )
                elif known!=fork_digest or common!=GENESIS or mode not in ("quarantined","reconstituted"):
                    raise ForkContinuityRefused("receiver cannot replace an observed fork")
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {**witness,"digest":fork_digest,
                "resource_state":"quarantined_at_shared_prefix",
                "automatic_winner_selected":False}

    def reconstitute(
        self, *,
        checkpoint_bytes: bytes,
        membership: SeedCommitMembership,
        coordinator: RecoveryLineageCoordinator,
        manifest: RecoveryStateManifest,
    )->dict[str,Any]:
        """Commit a NEW receiver-epoch only from independently verifiable seed.

        The witness's protected policy names an independently installed new
        membership; a claimant cannot fabricate a root, provide a forked
        successor, or reuse the old member keys as sufficient authority.
        """
        if (type(checkpoint_bytes) is not bytes
                or len(checkpoint_bytes)>1024*1024
                or sha256(checkpoint_bytes).hexdigest()!=GENESIS):
            raise ForkContinuityRefused("unavailable/incorrect last-common checkpoint bytes")
        if (not isinstance(membership,SeedCommitMembership)
                or membership.snapshot()!=successor_membership().snapshot()
                or membership.digest!=self.policy["new_membership"]
                or not isinstance(coordinator,RecoveryLineageCoordinator)
                or not isinstance(manifest,RecoveryStateManifest)):
            raise ForkContinuityRefused("independent successor quorum is not receiver-provisioned")
        if (manifest.machine_id!=SYSTEM_ID
                or manifest.incarnation!=2
                or manifest.owner_id!=membership.owner_id
                or manifest.owner_term!=membership.owner_term
                or manifest.membership_digest!=membership.digest
                or manifest.generation!=1
                or manifest.predecessor_digest!=GENESIS
                or manifest.state_digest!=sha256(checkpoint_bytes).hexdigest()):
            raise ForkContinuityRefused("new root is not grounded in last common checkpoint")
        try:
            coordinator.verify_state(manifest)
            high=coordinator.high_water()
        except RecoveryLineageError as exc:
            raise ForkContinuityRefused("successor quorum high-water is not independently verifiable") from exc
        if high!=(1,manifest.digest):
            raise ForkContinuityRefused("successor root is not the current quorum head")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                revision,mode,known,common,old=self._state(db)
                if mode=="reconstituted" and old==manifest.digest:
                    db.execute("COMMIT")
                    return {"resource":self.resource,"epoch":revision,"root":old,
                            "status":"reconstituted_from_common_prefix"}
                if mode!="quarantined" or revision!=1 or common!=GENESIS or not known:
                    raise ForkContinuityRefused("receiver did not quarantine exact fork first")
                db.execute(
                    "UPDATE fork_effect_state SET revision=2,mode='reconstituted',"
                    "new_root=? WHERE singleton=1",(manifest.digest,),
                )
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {"resource":self.resource,"epoch":2,"root":manifest.digest,
                "status":"reconstituted_from_common_prefix",
                "old_fork_still_has_no_global_winner":True}

    def apply(self, *, epoch: int, root: str, operation_id: str,
              value: int)->dict[str,Any]:
        """Check current receiver epoch and publish effect atomically in one DB."""
        if (type(epoch) is not int or epoch<0
                or type(operation_id) is not str or not 1<=len(operation_id)<=100
                or type(value) is not int or not -10**9<=value<=10**9):
            raise ForkContinuityRefused("effect input types are not exact")
        _sha(root,"requested effect head")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                current,mode,_,_,active=self._state(db)
                if mode!="reconstituted" or current!=epoch or active!=root:
                    raise ForkContinuityRefused("stale, cloned, or not yet reconstituted effect authority")
                row=db.execute(
                    "SELECT epoch,root,value,receipt_json FROM fork_effect_log WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if row:
                    if row[:3]!=(epoch,root,value):
                        raise ForkContinuityRefused("same effect identity has conflicting content")
                    db.execute("COMMIT")
                    return json.loads(row[3])
                effect={
                    "schema":"ifs.rcp001.qualified-resource-effect.v1",
                    "resource":self.resource,"epoch":epoch,"root":root,
                    "operation_id":operation_id,"value":value,
                    "receiver_local_commit":True,
                    "global_quorum_winner_proven":False,
                    "physical_host_attested":False,
                }
                effect["digest"]=_hash(effect)
                db.execute(
                    "INSERT INTO fork_effect_log VALUES (?,?,?,?,?)",
                    (operation_id,epoch,root,value,_json(effect).decode("ascii")),
                )
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return effect

    def snapshot(self)->dict[str,Any]:
        """Report local effect continuity; never expose phantom global winner."""
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            try:
                revision,mode,known,common,head=self._state(db)
                rows=db.execute(
                    "SELECT operation_id,epoch,root,value FROM fork_effect_log ORDER BY operation_id"
                ).fetchall()
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {
            "schema":SCHEMA,"resource":self.resource,
            "receiver_revision":revision,"mode":mode,
            "fork_digest":known,"last_unambiguous_root":common,
            "active_successor_root":head,
            "committed_effect_count":len(rows),
            "effect_history_digest":_hash([list(row) for row in rows]),
            "global_fork_winner":None,
        }
