"""IGC-003: existing E-CPU mTLS recovery quorum owns latest constructed Ground checkpoint.

No new consensus or transport. A receiver does NOT receive a candidate checkpoint
during recovery: quorum high-water selects the archived bytes, which are independently
reverified against the pinned mathematical intention before any new execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from construct import canonical, digest
from native_execution import initial_checkpoint, validate_source, verify_checkpoint

from mailcpu import (
    DistributedRecoveryLineageCoordinator,
    RecoveryLineageAuthority,
    RecoveryLineagePeerClient,
    RecoveryLineageTransportError,
    RecoveryStateManifest,
    SeedCommitMembership,
)

MEMBERS=("A","B","C")
DNS={"B":"member-b.mailcpu.test","C":"member-c.mailcpu.test"}
SCHEMA="ifs.igc003.quorum-ground.v1"


class GroundQuorumError(ValueError):
    """Quorum/observation authority was unavailable or contradicted."""


def require(ok,reason):
    """Refuse unauthenticated or noncurrent mathematical/physical state."""
    if not ok:
        raise GroundQuorumError("IGC-003 refused: "+reason)


def sha(raw):
    """SHA-256 content identity, never a source signature."""
    return hashlib.sha256(raw).hexdigest()


def membership_for(intention_sha,ground_sha):
    """Pin one independent fixed membership to one immutable machine Ground."""
    require(all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}",value)
                for value in (intention_sha,ground_sha)),
            "trusted intention and mathematical Ground identities missing")
    seed=sha(("IGC003:"+intention_sha+":"+ground_sha).encode("ascii"))
    return SeedCommitMembership("igc003-"+seed[:32],1,MEMBERS,"A",1,
                                sha(("IGC003-GENESIS:"+seed).encode("ascii")))


def open_quorum(membership,owner_journal,tls_dir,endpoints_file):
    """Use unchanged native E-CPU mTLS peer clients, owner and durable vote ledger."""
    endpoints=json.loads(endpoints_file.read_text(encoding="utf8"))
    require(type(endpoints) is dict and set(endpoints)==set(DNS),
            "authority endpoints not externally provisioned")
    ctx=ssl.create_default_context(ssl.Purpose.SERVER_AUTH,
                                   cafile=str(tls_dir/"ca.pem"))
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(tls_dir/"A.pem"),str(tls_dir/"A.key"))
    peers={}
    try:
        for member,dns in DNS.items():
            ep=endpoints[member]
            require(type(ep) is dict and set(ep)=={"host","port","dns"}
                    and ep["host"]=="127.0.0.1" and ep["dns"]==dns
                    and type(ep["port"]) is int and 0<ep["port"]<65536,
                    "authority member endpoint mismatch")
            for attempt in range(5):
                try:
                    peers[member]=RecoveryLineagePeerClient.connect_mutual_tls(
                        membership,member,ep["host"],ep["port"],ctx,
                        server_hostname=dns,timeout=2,handshake_timeout=2)
                    break
                except RecoveryLineageTransportError:
                    if attempt==4:raise
                    time.sleep(.10*(attempt+1))
        owner=RecoveryLineageAuthority(membership,"A",owner_journal)
        return DistributedRecoveryLineageCoordinator(membership,{"A":owner,**peers})
    except Exception:
        for peer in peers.values():peer.close()
        raise


def archived(archive,kind,hexdigest):
    """Content-addressed state objects and quorum manifests, never untrusted paths."""
    require(kind in ("objects","manifests") and
            type(hexdigest) is str and re.fullmatch(r"[0-9a-f]{64}",hexdigest),
            "archive location not content addressed")
    return archive/kind/(hexdigest+".json")


def store(path,raw):
    """Durably create immutable bytes before asking quorum to seal the reference."""
    path.parent.mkdir(parents=True,exist_ok=True)
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    try:
        descriptor=os.open(path,flags,0o600)
    except FileExistsError:
        require(path.read_bytes()==raw,"content archive alias changed")
        return
    try:
        with os.fdopen(descriptor,"wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if os.name=="posix":
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)


def load_latest(coordinator,membership,archive,ground,intention_sha,*,hint=None):
    """Quorum-root-first recovery with exact archive and semantic reconstruction."""
    proof=coordinator.latest_proof()
    require(proof is not None,"no prior quorum-sealed state")
    generation=proof.proposal.slot
    root=proof.proposal.result_state_digest
    require(hint is None or hint==root,
            "superseded manifest hint cannot override recovery high-water")
    raw_manifest=archived(archive,"manifests",root).read_bytes()
    descriptor=json.loads(raw_manifest)
    require(raw_manifest==canonical(descriptor),"archive manifest is not canonical")
    manifest=RecoveryStateManifest.from_snapshot(descriptor)
    require(manifest.digest==root and manifest.generation==generation
            and manifest.machine_id==membership.system_id
            and manifest.capture_cut=="igc003:stage:"+str(generation),
            "recovered manifest identity or stage differs")
    raw_state=archived(archive,"objects",manifest.state_digest).read_bytes()
    manifest.verify_payload(raw_state)
    checkpoint=json.loads(raw_state)
    require(raw_state==canonical(checkpoint),
            "state archive is not exact canonical JSON")
    count,state,_=verify_checkpoint(checkpoint,ground,intention_sha)
    require(count==generation,"quorum slot and observed transition count differ")
    verified=coordinator.verify_state(manifest)
    require(verified.proposal.digest==proof.proposal.digest,
            "quorum high-water moved during restore")
    return checkpoint,manifest,proof,state


def seal(intention_path,receipt_path,expected_intention_sha,checkpoint_path,
         archive,owner_journal,tls_dir,endpoints):
    """Commit a *preverified* next transition under native quorum monotonicity."""
    _,_,ground=validate_source(intention_path,receipt_path,expected_intention_sha)
    candidate=json.loads(checkpoint_path.read_text(encoding="utf8"))
    count,state,_=verify_checkpoint(candidate,ground,expected_intention_sha)
    membership=membership_for(expected_intention_sha,ground["ground_sha256"])
    coordinator=open_quorum(membership,owner_journal,tls_dir,endpoints)
    try:
        previous_generation,root=coordinator.high_water()
        require(count==previous_generation+1,
                "new Ground checkpoint does not extend current quorum generation")
        if previous_generation:
            old,_,_,_=load_latest(coordinator,membership,archive,ground,
                                  expected_intention_sha)
            old_prefix=old["payload"]["events"]
            require(candidate["payload"]["events"][:len(old_prefix)]==old_prefix
                    and candidate["payload"]["events"][-1]["previous_head"]==
                        old["payload"]["head"],
                    "candidate cannot fork previously sealed mathematical history")
        else:
            genesis=initial_checkpoint(expected_intention_sha,
                                       ground["ground_sha256"])
            require(candidate["payload"]["events"][0]["previous_head"]==
                    genesis["payload"]["head"],"missing immutable mathematical genesis")
        raw=canonical(candidate)
        manifest=RecoveryStateManifest(
            membership.system_id,membership.incarnation,
            membership.owner_id,membership.owner_term,membership.digest,
            count,root,sha(raw),"igc003:stage:"+str(count))
        store(archived(archive,"objects",manifest.state_digest),raw)
        store(archived(archive,"manifests",manifest.digest),
              canonical(manifest.snapshot()))
        proof=coordinator.seal(manifest)
        verified=coordinator.verify_state(manifest)
        require(proof.proposal.digest==verified.proposal.digest,
                "new Ground state was not independently quorum readable")
        return {"schema":SCHEMA,"status":"quorum_sealed_igc_ground",
                "generation":count,"state":state,"manifest_root":manifest.digest,
                "state_digest":manifest.state_digest,
                "checkpoint_sha256":candidate["sha256"],
                "decision_members":sorted(d.member_id for d in proof.decisions),
                "current_execution_authorized":False}
    finally:
        coordinator.close()


def recover(intention_path,receipt_path,expected_intention_sha,archive,
            owner_journal,tls_dir,endpoints,*,candidate_hint=None,output=None):
    """Recover latest math state from independent mTLS quorum with NO proposed snapshot."""
    _,_,ground=validate_source(intention_path,receipt_path,expected_intention_sha)
    membership=membership_for(expected_intention_sha,ground["ground_sha256"])
    coordinator=open_quorum(membership,owner_journal,tls_dir,endpoints)
    try:
        checkpoint,manifest,proof,state=load_latest(
            coordinator,membership,archive,ground,expected_intention_sha,
            hint=candidate_hint)
        if output is not None:
            # Only checked quorum-selected bytes, not a sender's proposed checkpoint.
            store(output,canonical(checkpoint))
        return {"schema":SCHEMA,"status":"quorum_reconstructed_igc_ground",
                "generation":manifest.generation,
                "state":state,"manifest_root":manifest.digest,
                "state_digest":manifest.state_digest,
                "checkpoint_sha256":checkpoint["sha256"],
                "quorum_decisions":sorted(d.member_id for d in proof.decisions),
                "state_selected_from_quorum_not_local_candidate":True,
                "source_reverified_by_independent_node":True,
                "current_execution_authorized":False}
    finally:
        coordinator.close()


def main():
    """Read external mTLS and source bootstrap, never from an executable receipt."""
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("seal","recover"))
    parser.add_argument("--intention",type=Path,required=True)
    parser.add_argument("--receipt",type=Path,required=True)
    parser.add_argument("--expected-intention-sha256",required=True)
    parser.add_argument("--checkpoint",type=Path)
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--owner-journal",type=Path,required=True)
    parser.add_argument("--tls-dir",type=Path,required=True)
    parser.add_argument("--endpoints",type=Path,required=True)
    parser.add_argument("--candidate-hint")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.action=="seal":
        require(args.checkpoint is not None,"new seal requires a measured transition")
        require(args.candidate_hint is None and args.output is None,
                "seal cannot select a fabricated prior root")
        result=seal(args.intention,args.receipt,args.expected_intention_sha256,
                    args.checkpoint,args.archive,args.owner_journal,
                    args.tls_dir,args.endpoints)
    else:
        require(args.checkpoint is None,"recovery cannot receive a candidate checkpoint")
        result=recover(args.intention,args.receipt,args.expected_intention_sha256,
                       args.archive,args.owner_journal,args.tls_dir,args.endpoints,
                       candidate_hint=args.candidate_hint,output=args.output)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
