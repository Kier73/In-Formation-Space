"""CGR-005: native E-CPU quorum and IPS-008 receiver for a non-affine NCR Ground.

Compatibility adapter for IPS-008's *existing* FencedGroundLineage proof interface:
overrides affine-specific session/assignment/compute/publication, but retains
the original FencedGroundHead, FencedGroundCandidate, durable RecoveryStateManifest,
strict-majority RecoveryLineageCoordinator, NavigableComputationDAG, real
Hypervisor and unmodified IPS-008 SQLite receiver + mTLS service.

The receiver reopens this publisher and independently checks source evidence,
NCR-004's mathematical verifier, every native DAG commit, original Hypervisor
effect bytes and latest quorum root. Neither a hash nor source observation
alone authenticates a physical host or gives a resource effect right.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from mailcpu.computation_dag import ComputationNode, NavigableComputationDAG
from mailcpu.fenced_generated_ground import (
    FencedGroundLineage, FencedGroundHead, FencedGroundCandidate, FencedGroundError,
)
from mailcpu.recovery_lineage import RecoveryLineageCoordinator, RecoveryLineageError
from mailcpu.seed import SystemIdentity
from mailcpu.semantic_translation import canonical_value_digest
from mailcpu.virtual_layer import VirtualGroundRef
from cgr003_observed_ecpu import load_epoch
from cgr004_language_hypervisor import (
    OPERATOR, GroundLanguageRefused, QualifiedFiniteHost,
    _admission, execute_qualified_language,
)
from navigable_compute.observed_ground import navigate_observed
from test_fenced_generated_ground import _membership, _authorities

STATE = "ifs.cgr005.general-source-quorum.v1"
CHECKPOINT = "ifs.cgr005.general-source-dag-checkpoint.v1"
STAGE = "ifs.cgr005.qualified-general-stage.v1"
WORDS = ((0,), (0,))
RESOURCE = "/virtual-layer/effects/ips008-register"


class GeneralGroundRefused(FencedGroundError):
    """Unqualified source, DAG, Hypervisor evidence, quorum or recovery."""


def _detach(value: Any):
    return json.loads(json.dumps(value,sort_keys=True,separators=(",",":"),
                                 ensure_ascii=False,allow_nan=False))


def _nodes(source_head: str, language_digest: str) -> NavigableComputationDAG:
    nodes=[]
    for i,word in enumerate(WORDS):
        nodes.append(ComputationNode(
            f"ips003.stage.{i:03d}",1,OPERATOR,RESOURCE,language_digest,
            () if i==0 else (f"ips003.stage.{i-1:03d}",),
            {"schema":STAGE,"source_head":source_head,
             "language_digest":language_digest,"word":list(word),"index":i},
        ))
    return NavigableComputationDAG(nodes)


def _receipt(index: int, initial: int, observed: int, host_id: str,
             source_head: str, language_digest: str,
             original_effect: dict[str,Any]) -> dict[str,Any]:
    result=original_effect["result"]
    body={
        "schema":STAGE, "index":index,"input":initial,
        "output":{"value":observed},"host":host_id,
        "source_head":source_head,"language_digest":language_digest,
        "hypervisor_effect_digest":canonical_value_digest(original_effect),
        "native_receipt_digest":result["native_receipt_digest"],
        "qualification_digest":result["qualification_digest"],
    }
    return {**body,"receipt_digest":canonical_value_digest(body)}


@dataclass
class GeneralGroundSession:
    """Actual native E-CPU dependency DAG reconstructed from semantic evidence."""
    system: SystemIdentity
    ground: VirtualGroundRef
    dag: NavigableComputationDAG
    stages: list[dict[str,Any]]
    source_head: str
    language_digest: str

    @property
    def complete(self):
        return self.dag.is_complete

    @property
    def value(self):
        if not self.stages:
            return None
        return self.stages[-1]["stage_receipt"]["output"]["value"]

    def checkpoint(self):
        payload={
            "schema":CHECKPOINT, "source_head":self.source_head,
            "language_digest":self.language_digest,
            "system":self.system.snapshot(),"ground":self.ground.to_dict(),
            "stages":_detach(self.stages),"dag_snapshot":self.dag.snapshot(),
            "claim":"source-mathematical-and-native-Hypervisor-only;no-host-attestation",
        }
        return {"payload":payload,"digest":canonical_value_digest(payload)}


class GeneralGroundLineage(FencedGroundLineage):
    """A *separate generalized mathematical publisher* for original IPS-008.

    Subtyping is intentionally narrow because original IPS-008 checks for
    FencedGroundLineage and FencedGroundHead. All affine-specific methods that
    establish meaning are overridden. The quorum persistence/restore code and
    receiver lock, mTLS and effect checks are inherited unchanged.
    """

    def __init__(self, root: Path, *, members: tuple[str,...] | None = None):
        epoch=load_epoch(root)
        admission=_admission(root,epoch.source_head)
        if (len(admission.source.states)!=6 or
            admission.source.states!=tuple(range(6)) or
            admission.source.initial!=tuple(range(6)) or
            len(admission.source.generators)!=2 or
            admission.source.outputs!=tuple(str(s) for s in range(6))):
            raise GeneralGroundRefused("source does not match provisioned general finite environment")
        self.workspace=Path(root)
        self.source_head=epoch.source_head
        self.language_digest=admission.language.digest
        self.admission=admission
        plan={"schema":STATE+".plan","source_head":self.source_head,
              "language_digest":self.language_digest,
              "initial":2,"words":[list(w) for w in WORDS]}
        self.plan=SimpleNamespace(digest=canonical_value_digest(plan))
        self.intention=SimpleNamespace(digest=canonical_value_digest({
            "schema":STATE+".intention","plan_digest":self.plan.digest,
            "observation":"exact-integer-state","initial":2,
        }))
        self.primitives=()
        self.root=self.workspace/"artifacts"
        self.root.mkdir(parents=True,exist_ok=True)
        membership=_membership()
        authority=_authorities(self.workspace,membership)
        if members is not None:
            authority={k:v for k,v in authority.items() if k in members}
        self.lineage=RecoveryLineageCoordinator(membership,authority)

    def _session(self, checkpoint: Any) -> GeneralGroundSession:
        """Reconstruct original DAG with source proof and strict stage receipts."""
        if (not isinstance(checkpoint,dict) or
            set(checkpoint)!={"payload","digest"} or
            not isinstance(checkpoint["payload"],dict) or
            checkpoint["digest"] != canonical_value_digest(checkpoint["payload"])):
            raise GeneralGroundRefused("checkpoint digest/schema mismatch")
        data=checkpoint["payload"]
        if (set(data)!={"schema","source_head","language_digest","system","ground",
                       "stages","dag_snapshot","claim"} or
            data["schema"]!=CHECKPOINT or data["source_head"]!=self.source_head or
            data["language_digest"]!=self.language_digest or
            data["claim"]!="source-mathematical-and-native-Hypervisor-only;no-host-attestation" or
            not isinstance(data["stages"],list) or len(data["stages"])>len(WORDS)):
            raise GeneralGroundRefused("checkpoint source or scope is not qualified")
        if _admission(self.workspace,self.source_head).language.digest!=self.language_digest:
            raise GeneralGroundRefused("source mathematical revision differs")
        system=SystemIdentity.from_snapshot(data["system"])
        ground=VirtualGroundRef.from_dict(data["ground"])
        if (system.system_id!=self.lineage.membership.system_id or
            system.incarnation!=self.lineage.membership.incarnation):
            raise GeneralGroundRefused("virtual system differs from current quorum identity")
        dag=_nodes(self.source_head,self.language_digest)
        current=2
        for index,stage in enumerate(data["stages"]):
            if (not isinstance(stage,dict) or
                set(stage)!={"index","host","stage_receipt","hypervisor_effect"} or
                type(stage["index"]) is not int or stage["index"]!=index or
                type(stage["host"]) is not str or not stage["host"] or
                not isinstance(stage["hypervisor_effect"],dict) or
                not isinstance(stage["stage_receipt"],dict)):
                raise GeneralGroundRefused("saved stage record is malformed")
            wanted=navigate_observed(
                self.admission,expected_head=self.source_head,
                initial=current,word=WORDS[index],repetitions=1,
            )
            if not wanted.isdecimal() or wanted!=str(int(wanted)):
                raise GeneralGroundRefused("only exact integer Ground can affect native register")
            value=int(wanted)
            effect=stage["hypervisor_effect"]
            result=effect.get("result")
            if (not isinstance(result,dict) or
                effect.get("kind")!="virtual_layer.operator_result" or
                effect.get("operator_id")!=OPERATOR or
                effect.get("node_id")!="cgr004-native" or
                effect.get("logical_time")!=index+1 or
                effect.get("ground")!=ground.to_dict() or
                effect.get("result_digest")!=canonical_value_digest(result) or
                result.get("source_head")!=self.source_head or
                result.get("ncr_language_sha256")!=self.language_digest or
                result.get("host")!=stage["host"] or
                result.get("state")!=value or
                result.get("output")!=wanted or
                result.get("effect_authorized") is not False or
                type(result.get("qualification_digest")) is not str or
                type(result.get("native_receipt_digest")) is not str or
                len(result["qualification_digest"])!=64 or
                len(result["native_receipt_digest"])!=64):
                raise GeneralGroundRefused("saved native Hypervisor effect violates Ground proof")
            receipt=_receipt(index,current,value,stage["host"],
                             self.source_head,self.language_digest,effect)
            if stage["stage_receipt"]!=receipt:
                raise GeneralGroundRefused("rehashed stage receipt disagrees with original semantics")
            dag.commit(f"ips003.stage.{index:03d}", {
                "input":current,"value":value,
                "stage_receipt_digest":receipt["receipt_digest"],
                "hypervisor_effect_digest":canonical_value_digest(effect),
            })
            current=value
        if dag.snapshot()!=data["dag_snapshot"]:
            raise GeneralGroundRefused("native E-CPU DAG differs from exact stage prefix")
        return GeneralGroundSession(system,ground,dag,_detach(data["stages"]),
                                    self.source_head,self.language_digest)

    def _validate_state(self,state:Any)->GeneralGroundSession:
        if (not isinstance(state,dict) or
            set(state)!={"schema","plan_digest","intention_digest",
                        "checkpoint","epoch","assignment","event"} or
            state["schema"]!=STATE or state["plan_digest"]!=self.plan.digest or
            state["intention_digest"]!=self.intention.digest or
            type(state["epoch"]) is not int or state["epoch"]<0 or
            state["event"] not in ("bootstrap","assign","reassign","publish")):
            raise GeneralGroundRefused("sealed general Ground schema or plan differs")
        session=self._session(state["checkpoint"])
        assignment=state["assignment"]
        if assignment is not None:
            if (not isinstance(assignment,dict) or
                set(assignment)!={"host_id","epoch","stage","source_checkpoint_digest"} or
                type(assignment["host_id"]) is not str or not assignment["host_id"] or
                assignment["epoch"]!=state["epoch"] or
                assignment["stage"]!=len(session.stages) or
                assignment["source_checkpoint_digest"]!=state["checkpoint"]["digest"] or
                session.complete or state["event"] not in ("assign","reassign")):
                raise GeneralGroundRefused("noncurrent or incoherent assigned general Ground")
        elif state["event"] in ("assign","reassign"):
            raise GeneralGroundRefused("assignment event omitted its host")
        if state["event"]=="bootstrap" and (state["epoch"]!=0 or session.stages):
            raise GeneralGroundRefused("bootstrap cannot contain previously executed stages")
        if state["event"]=="publish" and (not session.stages or state["epoch"]<=0):
            raise GeneralGroundRefused("publication requires a qualified stage")
        return session

    def bootstrap(self, system: SystemIdentity,ground: VirtualGroundRef)->FencedGroundHead:
        if self.lineage.high_water()!=(0,self.lineage.membership.genesis_state_digest):
            raise GeneralGroundRefused("quorum already owns another Ground state")
        session=GeneralGroundSession(system,ground,_nodes(
            self.source_head,self.language_digest),[],self.source_head,self.language_digest)
        checkpoint=session.checkpoint()
        self._session(checkpoint)
        return self._seal({
            "schema":STATE,"plan_digest":self.plan.digest,
            "intention_digest":self.intention.digest,"checkpoint":checkpoint,
            "epoch":0,"assignment":None,"event":"bootstrap",
        },capture_cut="cgr005.bootstrap",expected_parent=(
            0,self.lineage.membership.genesis_state_digest))

    def assign(self,head:FencedGroundHead,host:QualifiedFiniteHost)->FencedGroundHead:
        session=self._check_head(head)
        if (not isinstance(host,QualifiedFiniteHost) or
            host.source_head!=self.source_head or
            host.language_digest!=self.language_digest or
            host.host_id not in host.policy_allowed_hosts or
            session.complete):
            raise GeneralGroundRefused("general operator host or pending stage unavailable")
        previous=head.assignment
        if previous and previous["host_id"]==host.host_id:
            raise GeneralGroundRefused("same-host reassignment refused")
        epoch=head.state["epoch"]+1
        return self._seal({
            "schema":STATE,"plan_digest":self.plan.digest,
            "intention_digest":self.intention.digest,
            "checkpoint":head.checkpoint,"epoch":epoch,
            "assignment":{"host_id":host.host_id,"epoch":epoch,
                          "stage":len(session.stages),
                          "source_checkpoint_digest":head.checkpoint["digest"]},
            "event":"reassign" if previous else "assign",
        },capture_cut="cgr005.assign",expected_parent=(
            head.manifest.generation,head.manifest.digest))

    def compute(self,head:FencedGroundHead,host:QualifiedFiniteHost,
                operating_system,pid:int)->FencedGroundCandidate:
        session=self._check_head(head)
        assignment=head.assignment
        if (assignment is None or
            not isinstance(host,QualifiedFiniteHost) or
            assignment["host_id"]!=host.host_id or
            host.source_head!=self.source_head or
            host.language_digest!=self.language_digest):
            raise GeneralGroundRefused("worker is not current qualified majority-assigned host")
        index=len(session.stages)
        ready=session.dag.ready_nodes()
        if (len(ready)!=1 or ready[0].node_id!=f"ips003.stage.{index:03d}"):
            raise GeneralGroundRefused("native E-CPU DAG frontier is not ready")
        initial=2 if index==0 else session.value
        result=execute_qualified_language(
            self.workspace,host,expected_head=self.source_head,
            operating_system=operating_system,pid=pid,system=session.system,
            ground=session.ground,initial=initial,
            word=WORDS[index],repetitions=1,request_sequence=index+1,
        )
        value=int(result["value"])
        effect=_detach(result["hypervisor_effect"])
        receipt=_receipt(index,initial,value,host.host_id,self.source_head,
                         self.language_digest,effect)
        session.stages.append({
            "index":index,"host":host.host_id,
            "stage_receipt":receipt,"hypervisor_effect":effect,
        })
        session.dag.commit(f"ips003.stage.{index:03d}",{
            "input":initial,"value":value,
            "stage_receipt_digest":receipt["receipt_digest"],
            "hypervisor_effect_digest":canonical_value_digest(effect),
        })
        candidate=session.checkpoint()
        self._session(candidate)
        return FencedGroundCandidate(
            head.manifest.digest,assignment["epoch"],host.host_id,candidate)

    def publish(self,head:FencedGroundHead,candidate:FencedGroundCandidate)->FencedGroundHead:
        previous=self._check_head(head)
        current=head.assignment
        if (current is None or not isinstance(candidate,FencedGroundCandidate) or
            candidate.assignment_manifest_digest!=head.manifest.digest or
            candidate.assignment_epoch!=current["epoch"] or
            candidate.host_id!=current["host_id"]):
            raise GeneralGroundRefused("stale candidate cannot publish through native quorum")
        advanced=self._session(candidate.next_checkpoint)
        if (len(advanced.stages)!=len(previous.stages)+1 or
            advanced.stages[:-1]!=previous.stages or
            advanced.stages[-1]["host"]!=candidate.host_id or
            advanced.system!=previous.system or advanced.ground!=previous.ground):
            raise GeneralGroundRefused("proposed candidate changes prior Ground identity")
        return self._seal({
            "schema":STATE,"plan_digest":self.plan.digest,
            "intention_digest":self.intention.digest,
            "checkpoint":candidate.next_checkpoint,"epoch":current["epoch"],
            "assignment":None,"event":"publish",
        },capture_cut="cgr005.publish",expected_parent=(
            head.manifest.generation,head.manifest.digest))


def open_general(root:Path)->GeneralGroundLineage:
    """A fresh participant reconstructs source, native math and original quorum."""
    return GeneralGroundLineage(Path(root))
