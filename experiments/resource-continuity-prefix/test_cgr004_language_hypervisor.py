"""CGR-004 tests: actual original Hypervisor runs non-affine source-derived words."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from navigable_compute.observed_ground import ObservedEpoch, TransitionObservation
from mailcpu import Capability
from mailcpu.runtime_qualification import digest, SubprocessQualificationEndpoint

from cgr003_observed_ecpu import (
    SOURCE_FILE, ObservedNativeRefused, construct_native, persist_epoch,
)
from cgr004_language_hypervisor import (
    GroundLanguageRefused, _admission,
    qualify_finite_host, execute_qualified_language,
)
from test_fenced_generated_ground import _receiver


def non_affine_epoch(reverse=False) -> ObservedEpoch:
    states = tuple(range(6))
    actions = ("cycle", "swap")
    source = {}
    for s in states:
        for action in actions:
            if action == "cycle":
                cycle = ({2:3,3:4,4:2} if not reverse
                         else {2:4,4:3,3:2})
                after = cycle.get(s,s)
            else:
                after = {0:1,1:0}.get(s,s)
            source[s,action] = after
    events = tuple(TransitionObservation(
        i,s,a,source[s,a],str(s),str(source[s,a]))
        for i,(s,a) in enumerate(source))
    return ObservedEpoch(
        "cgr004-observed-nonaffine-source",
        "fixed-six-state-observer-v2" if reverse else "fixed-six-state-observer-v1",
        states,actions,(0,2,5),events,
    )


def host(root: Path,name: str,head: str):
    return qualify_finite_host(root,name,expected_head=head,
                              allowed_hosts=frozenset({"cgr004-host-a","cgr004-host-b"}))


def execute(root: Path,qualified,epoch,*,initial,word,repetitions,
            operating_system=None,pid=None):
    if operating_system is None:
        operating_system,identity,envelope,ground,process_pid = _receiver()
        pid = process_pid
    else:
        identity = operating_system._cgr004_test_identity
        ground = operating_system._cgr004_test_ground
    return execute_qualified_language(
        root,qualified,expected_head=epoch.source_head,
        operating_system=operating_system,pid=pid,
        system=identity,ground=ground,
        initial=initial,word=word,repetitions=repetitions,
    )


def test_general_non_affine_language_is_not_cgr003_affine(tmp_path):
    epoch = non_affine_epoch()
    persist_epoch(tmp_path,epoch)
    admission = _admission(tmp_path,epoch.source_head)
    assert len(admission.language.state_classes) == 6
    assert len(admission.language.operators) == 6
    with pytest.raises(ObservedNativeRefused):
        construct_native(epoch,expected_head=epoch.source_head)
    worker = host(tmp_path,"cgr004-host-a",epoch.source_head)
    record = execute(tmp_path,worker,epoch,initial=2,
                     word=(0,1),repetitions=10**80+19)
    assert record["value"] == "4"
    assert record["hypervisor_effect"]["kind"] == "virtual_layer.operator_result"
    assert record["hypervisor_effect"]["operator_id"] == "cgr004.qualified_finite_word"
    assert record["hypervisor_effect"]["result"]["output"] == "4"
    assert record["physical_effect_authorized"] is False
    assert record["hypervisor_effect"]["result"]["effect_authorized"] is False


def test_original_hypervisor_denies_missing_compute_capability(tmp_path):
    epoch = non_affine_epoch();persist_epoch(tmp_path,epoch)
    worker = host(tmp_path,"cgr004-host-a",epoch.source_head)
    os,identity,envelope,ground,pid = _receiver()
    denied = os.environment.kernel.spawn(
        "cgr004-unpermitted",
        capabilities=(Capability("/unrelated",frozenset({"read"})),),
        parent_pid=os.environment.init_pid,
    )
    with pytest.raises(GroundLanguageRefused,match="Hypervisor"):
        execute_qualified_language(
            tmp_path,worker,expected_head=epoch.source_head,
            operating_system=os,pid=denied,system=identity,ground=ground,
            initial=0,word=(1,),repetitions=1,
        )
    # Native Hypervisor identities are (source, channel, sequence).
    # Do NOT reuse the denied event's sequence for an independent request.
    valid = execute_qualified_language(
        tmp_path,worker,expected_head=epoch.source_head,
        operating_system=os,pid=pid,system=identity,ground=ground,
        initial=0,word=(1,),repetitions=1,request_sequence=2,
    )
    assert valid["value"] == "1"
    assert valid["request_sequence"] == 2
    second = execute_qualified_language(
        tmp_path,worker,expected_head=epoch.source_head,
        operating_system=os,pid=pid,system=identity,ground=ground,
        initial=2,word=(0,),repetitions=1,request_sequence=3,
    )
    assert second["value"] == "3"
    # The same sequence with a different request MUST refuse, not mutate a
    # previously committed Hypervisor identity.
    with pytest.raises(Exception,match="conflicting execution retransmission"):
        execute_qualified_language(
            tmp_path,worker,expected_head=epoch.source_head,
            operating_system=os,pid=pid,system=identity,ground=ground,
            initial=0,word=(1,),repetitions=3,request_sequence=2,
        )


def test_same_ground_executes_on_separately_selected_native_hosts(tmp_path):
    epoch = non_affine_epoch();persist_epoch(tmp_path,epoch)
    a = host(tmp_path,"cgr004-host-a",epoch.source_head)
    b = host(tmp_path,"cgr004-host-b",epoch.source_head)
    assert a.qualification_digest != b.qualification_digest
    ra = execute(tmp_path,a,epoch,initial=2,word=(0,1),repetitions=11)
    rb = execute(tmp_path,b,epoch,initial=2,word=(0,1),repetitions=11)
    assert ra["value"] == rb["value"] == "4"
    assert ra["source_head"] == rb["source_head"]
    assert ra["language_sha256"] == rb["language_sha256"]
    assert ra["receiver_effect_digest"] != rb["receiver_effect_digest"]


def test_changed_source_reconstructs_different_processor(tmp_path):
    first = non_affine_epoch()
    renewed = non_affine_epoch(reverse=True)
    assert first.source_head != renewed.source_head
    left = tmp_path/"left"
    right = tmp_path/"right"
    persist_epoch(left,first)
    persist_epoch(right,renewed)
    a = _admission(left,first.source_head)
    b = _admission(right,renewed.source_head)
    assert a.language.digest != b.language.digest
    host_old = host(left,"cgr004-host-a",first.source_head)
    with pytest.raises(GroundLanguageRefused,match="unqualified"):
        execute_qualified_language(
            right,host_old,expected_head=renewed.source_head,
            operating_system=None,pid=1,system=None,ground=None,
            initial=2,word=(0,),repetitions=1,
        )
    host_new = host(right,"cgr004-host-b",renewed.source_head)
    record = execute(right,host_new,renewed,initial=2,word=(0,),repetitions=1)
    assert record["value"] == "4"


def test_tampered_pinned_source_and_incomplete_source_refuse(tmp_path):
    epoch=non_affine_epoch()
    persist_epoch(tmp_path,epoch)
    fake = replace(epoch,context="altered-source-epoch")
    (tmp_path/SOURCE_FILE).write_text(
        json.dumps(fake.packet(),sort_keys=True,separators=(",",":")),encoding="ascii")
    with pytest.raises(GroundLanguageRefused,match="pinned"):
        _admission(tmp_path,epoch.source_head)
    partial = replace(epoch,witnesses=epoch.witnesses[:-1])
    unknown = tmp_path/"partial"
    persist_epoch(unknown,partial)
    with pytest.raises(GroundLanguageRefused):
        _admission(unknown,partial.source_head)


def test_wrong_host_policy_and_invalid_time_refused(tmp_path):
    epoch=non_affine_epoch();persist_epoch(tmp_path,epoch)
    with pytest.raises(GroundLanguageRefused,match="policy"):
        qualify_finite_host(tmp_path,"not-allowed",expected_head=epoch.source_head,
                            allowed_hosts=frozenset({"cgr004-host-a"}))
    selected = host(tmp_path,"cgr004-host-a",epoch.source_head)
    os,identity,envelope,ground,pid = _receiver()
    for word,repetitions in (((True,),1),((0,),-1),((0,),1<<4096)):
        with pytest.raises(GroundLanguageRefused,match="request"):
            execute_qualified_language(tmp_path,selected,
                expected_head=epoch.source_head,operating_system=os,pid=pid,
                system=identity,ground=ground,initial=0,
                word=word,repetitions=repetitions)


def test_rehashed_false_worker_result_cannot_pass_independent_ground(tmp_path):
    epoch=non_affine_epoch();persist_epoch(tmp_path,epoch)
    qualified=host(tmp_path,"cgr004-host-a",epoch.source_head)
    good=qualified.endpoint

    class RehashedFalseWorker:
        def exchange(self,request,*,max_bytes):
            response=good.exchange(request,max_bytes=max_bytes)
            response["output"]="WRONG-RESULT"
            response["receipt_digest"]=digest({
                k:v for k,v in response.items() if k != "receipt_digest"})
            return response

    replaced=replace(qualified,endpoint=RehashedFalseWorker())
    os,identity,envelope,ground,pid = _receiver()
    with pytest.raises(GroundLanguageRefused,match="native process differs"):
        execute_qualified_language(tmp_path,replaced,expected_head=epoch.source_head,
            operating_system=os,pid=pid,system=identity,ground=ground,
            initial=2,word=(0,),repetitions=1)
