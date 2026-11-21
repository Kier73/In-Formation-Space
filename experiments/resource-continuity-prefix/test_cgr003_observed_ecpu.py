"""CGR-003: witnessed NCR-004 construction -> actual E-CPU DAG -> IPS-008 mTLS.

This test uses genuine native E-CPU test authorities, subprocess-qualified
hosts, original Hypervisor, original quorum, and real mTLS receiver service.
The observation source is a deterministic test fixture, not a physical sensor.
"""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic, sleep

import pytest

from navigable_compute.observed_ground import ObservedEpoch, TransitionObservation
from mailcpu.effect_receiver_service import EffectReceiverServiceError
from mailcpu.fenced_effect_receiver import EffectFencingRefused, published_effect
from mailcpu.qualified_generated_ground import QualifiedGroundExecution
from test_effect_receiver_service import _client, _kill
from test_fenced_generated_ground import _receiver, _host, _restart
from test_recovery_lineage_service import _make_certificates

from cgr003_observed_ecpu import (
    RESOURCE, SOURCE_FILE, ObservedNativeRefused,
    construct_native, load_epoch, open_lineage, persist_epoch, verify_published,
)

MODULE = Path(__file__).resolve().parent
WORKER = MODULE / "cgr003_receiver_worker.py"


def observed_epoch() -> ObservedEpoch:
    """Fixture emits measurements of unknown-to-constructor finite functions."""
    source = {"first": lambda s: (3*s+2) % 17,
              "second": lambda s: (8*s+5) % 17}
    events = []
    for s in range(17):
        for action in ("first", "second"):
            after = source[action](s)
            events.append(TransitionObservation(
                len(events), s, action, after, str(s), str(after)))
    return ObservedEpoch(
        "cgr003-observer-fixture", "finite-stationary-context-v1",
        tuple(range(17)), ("first", "second"), (9,), tuple(events),
    )


def start(root: Path, certificates: dict) -> tuple[subprocess.Popen, dict]:
    marker = root / "cgr003-receiver-ready.json"
    marker.unlink(missing_ok=True)
    process = subprocess.Popen([
        sys.executable, str(WORKER), str(root),
        str(certificates["B_cert"]), str(certificates["B_key"]),
        str(certificates["ca"]), str(marker), "owner-a.mailcpu.test",
    ], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = monotonic() + 18
        while monotonic() < deadline:
            if marker.exists():
                return process, json.loads(marker.read_text(encoding="ascii"))
            if process.poll() is not None:
                out, err = process.communicate(timeout=5)
                raise AssertionError("CGR-003 native receiver failed: " +
                                     err[-2300:] + out[-400:])
            sleep(.025)
        raise AssertionError("native IPS-008 receiver did not advertise listener")
    except BaseException:
        _kill(process)
        raise


def boot(root: Path):
    epoch = observed_epoch()
    persist_epoch(root, epoch)
    constructed = construct_native(epoch, expected_head=epoch.source_head)
    assert constructed.plan.primitive_names == ("first", "second")
    assert tuple((p.multiplier,p.offset) for p in constructed.primitives) == ((3,2),(8,5))
    assert constructed.intention.coefficients == (7,4)
    lineage = open_lineage(root)
    operating_system, identity, envelope, ground, pid = _receiver()
    session = QualifiedGroundExecution(
        lineage.plan, lineage.intention, lineage.primitives, identity, ground)
    initial = lineage.bootstrap(session)
    return epoch, lineage, initial, operating_system, envelope, pid


def test_witnessed_native_plan_is_not_hardcoded():
    epoch = observed_epoch()
    qualified = construct_native(epoch, expected_head=epoch.source_head)
    assert qualified.plan.primitive_names == ("first", "second")
    assert len(qualified.admission.source.states) == 17
    assert len(qualified.admission.language.state_classes) == 17
    assert qualified.intention.output_at_zero == 4
    assert qualified.intention.output_at_one == 11
    assert qualified.intention.query_input == 9
    assert qualified.intention.relation.ground_digest == epoch.source_head
    assert qualified.intention.relation.verifier_digest == qualified.language_digest
    assert qualified.plan.authoritative is False


def test_reobserved_different_affine_law_generates_a_new_native_processor():
    # Entire new source law, not a parameter hardcoded into lowering code.
    old = observed_epoch()
    changed = []
    for event in old.witnesses:
        if event.action == "second":
            after = (event.after + 1) % 17
            changed.append(replace(event, after=after, after_output=str(after)))
        else:
            changed.append(event)
    new = replace(old, context="reobserved-affine-epoch-v2",
                  witnesses=tuple(changed))
    first = construct_native(old, expected_head=old.source_head)
    second = construct_native(new, expected_head=new.source_head)
    assert new.source_head != old.source_head
    assert second.intention.relation.ground_digest == new.source_head
    assert second.primitives[1].offset == 6
    assert second.intention.output_at_zero == 5
    assert second.intention.output_at_one == 12
    assert second.plan.primitive_names == ("first", "second")
    assert second.plan.digest != first.plan.digest


def test_non_affine_source_and_partial_source_refuse_native_lowering():
    epoch = observed_epoch()
    changed = list(epoch.witnesses)
    item = changed[4]  # observed state=2, action='first'
    changed[4] = replace(item, after=9, after_output="9")
    inconsistent_family = replace(epoch, witnesses=tuple(changed))
    with pytest.raises(ObservedNativeRefused, match="not native finite affine"):
        construct_native(inconsistent_family,
                         expected_head=inconsistent_family.source_head)
    partial = replace(epoch, witnesses=epoch.witnesses[:-1])
    with pytest.raises(ObservedNativeRefused, match="source admission"):
        construct_native(partial, expected_head=partial.source_head)
    revision = replace(epoch, context="new epoch")
    with pytest.raises(ObservedNativeRefused, match="source admission"):
        construct_native(revision, expected_head=epoch.source_head)


def test_source_pin_refuses_rewritten_source(tmp_path: Path):
    epoch = observed_epoch()
    persist_epoch(tmp_path, epoch)
    assert load_epoch(tmp_path) == epoch
    changed = replace(epoch, context="stale source revision")
    (tmp_path / SOURCE_FILE).write_text(
        json.dumps(changed.packet(), sort_keys=True, separators=(",", ":")),
        encoding="ascii")
    with pytest.raises(ObservedNativeRefused, match="source bytes"):
        load_epoch(tmp_path)


@pytest.mark.skipif(shutil.which("openssl") is None,
                    reason="native E-CPU test certificate issuer requires OpenSSL")
def test_newly_constructed_ground_executes_native_quorum_and_survives_mtls_rehome(
    tmp_path: Path,
):
    """Use source-derived plan, real qualified stage hosts, mTLS/SQLite fencing."""
    epoch, lineage, initial, operating_system, envelope, pid = boot(tmp_path)
    stage_one = _host(tmp_path, "cgr003-original")
    assigned = lineage.assign(initial, stage_one)
    first_candidate = lineage.compute(assigned, stage_one, operating_system, pid)
    first = lineage.publish(assigned, first_candidate)
    first_check = verify_published(tmp_path, first)
    assert first_check["observed_value"] == 12
    assert first_check["executed_stages"] == 1
    assert first_check["source_head"] == epoch.source_head
    assert first_check["effect_authorized"] is False
    assert first.checkpoint["payload"]["stages"][0]["host"] == stage_one.locus
    assert first.checkpoint["payload"]["stages"][0]["hypervisor_effect"]["kind"] == "virtual_layer.operator_result"

    certificates = _make_certificates(tmp_path)
    receiver, info = start(tmp_path, certificates)
    reopened_receiver = None
    try:
        owner = _client(info, certificates)
        assert owner.activate(first.manifest.digest)["event"] == "publish"
        original_effect = published_effect(first, RESOURCE)
        assert owner.apply(original_effect)["value"] == 12

        successor_host = _host(tmp_path, "cgr003-successor")
        barrier = owner.prepare(first.manifest.digest, successor_host.locus)
        assert barrier["target_host"] == successor_host.locus
        assert barrier["target_epoch"] == 2
        with pytest.raises(EffectFencingRefused):
            owner.apply(original_effect)

        # Destroy receiver after durable barrier ACK, recover original SQLite
        # authority in fresh OS process, while old quorum is still current.
        _kill(receiver)
        reopened_receiver, new_info = start(tmp_path, certificates)
        owner2 = _client(new_info, certificates)
        assert owner2.snapshot()["pending_handoff_digest"] == barrier["barrier_digest"]
        with pytest.raises(EffectFencingRefused):
            owner2.apply(original_effect)

        recovered_lineage = open_lineage(tmp_path)
        assert recovered_lineage.restore_latest().manifest.digest == first.manifest.digest
        assigned_next = recovered_lineage.assign(first, successor_host)
        assert owner2.activate(assigned_next.manifest.digest)["event"] == "assign"
        with pytest.raises(EffectFencingRefused):
            owner2.apply(original_effect)

        next_os, next_pid = _restart(envelope)
        candidate = recovered_lineage.compute(
            assigned_next, successor_host, next_os, next_pid)
        final = recovered_lineage.publish(assigned_next, candidate)
        checked = verify_published(tmp_path, final)
        assert checked["source_head"] == epoch.source_head
        assert checked["observed_value"] == 16
        assert checked["executed_stages"] == 2
        assert checked["ecpu_quorum_root"] == final.manifest.digest
        assert checked["stage_receipt_digest"] == final.checkpoint["payload"]["stages"][-1]["stage_receipt"]["receipt_digest"]
        assert [s["host"] for s in final.checkpoint["payload"]["stages"]] == [
            "cgr003-original", "cgr003-successor"]

        assert owner2.activate(final.manifest.digest)["event"] == "publish"
        new_effect = published_effect(final, RESOURCE)
        result = owner2.apply(new_effect)
        assert result["value"] == 16
        assert owner2.apply(new_effect)["value"] == 16
        snapshot = owner2.snapshot()
        assert snapshot["accepted_effects"] == 2
        assert snapshot["register_value"] == 16
        with pytest.raises(EffectFencingRefused):
            owner2.apply(original_effect)

        # The authenticated connection identity does not override source or
        # quorum: changed source bytes cannot create a new native lineage.
        with pytest.raises(EffectReceiverServiceError):
            _client(new_info, certificates, dns="unauthorized.mailcpu.test").snapshot()

        # Freeze once more without a matching new assignment; both newly
        # published and older effects must now remain refused.
        second_barrier = owner2.prepare(final.manifest.digest, "cgr003-third-host")
        assert second_barrier["target_epoch"] == 3
        with pytest.raises(EffectFencingRefused):
            owner2.apply(new_effect)
        with pytest.raises(EffectFencingRefused):
            owner2.apply(original_effect)
    finally:
        _kill(receiver)
        if reopened_receiver is not None:
            _kill(reopened_receiver)
