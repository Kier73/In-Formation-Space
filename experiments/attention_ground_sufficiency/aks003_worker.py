"""Externally supervised receiver: abrupt death after quorum commit, new host restore."""
import json
import sys
import time
from pathlib import Path

from attention_ground import GroundRefused
from composed_attention import CausalState, InputEvidence, independently_verify_trace
from aks003_attention_session import (
    advance_session, compatible, decode_state, digest, encode_state,
    load_attention, make_store, native_virtual_layer_probe, network_ground,
    observe_probe, save_json, source_vector,
)


def prepare(root: Path, marker: Path) -> None:
    network = network_ground()
    store = make_store(root, network, 'A')
    empty = CausalState.empty(network)
    original = store.create_session(encode_state(empty))
    state = empty
    tokens, receipts = [], []
    for i in range(73):
        item = InputEvidence.form(network, state.count, state.source_head, source_vector(i))
        state, receipt = state.advance(item)
        tokens.append(item)
        receipts.append(receipt)
    independently_verify_trace(network, tokens, receipts,
                               expected_source_head=state.source_head,
                               expected_state_digest=state.fingerprint)
    saved = store.commit_state(
        encode_state(state), expected_revision=original.revision,
        expected_checkpoint_digest=original.checkpoint_digest,
        transition_id='aks003.initial-prefix-73', operation_id='aks003.attention.observe-prefix',
        input_digest=digest(b'aks003-pinned-demo-source-73'), logical_time=73,
    )
    assert saved.revision == 2
    export = store.export_latest()
    save_json(root / 'export-A.json', export)
    save_json(marker, {'pid': __import__('os').getpid(), 'revision': saved.revision,
                       'checkpoint_digest': saved.checkpoint_digest,
                       'state_digest': state.fingerprint, 'source_head': state.source_head,
                       'quorum_root': saved.lineage_manifest.digest,
                       'page_manifest': saved.checkpoint.state_manifest.manifest_digest,
                       'count': state.count, 'source_bytes': len(saved.state_bytes)})
    while True:
        time.sleep(1)


def resume(root: Path, result: Path) -> None:
    network = network_ground()
    store = make_store(root, network, 'B')
    export = json.loads((root / 'export-A.json').read_text())
    # No B executor can silently infer compatibility between backend profiles.
    incompatible_refused = False
    try:
        store.restore_export(export)
    except Exception as exc:
        from mailcpu.computational_session import ComputationalSessionIntegrityError
        if not isinstance(exc, ComputationalSessionIntegrityError):
            raise
        incompatible_refused = True
    assert incompatible_refused
    restored = store.restore_export(export, backend_compatibility=compatible)
    before, state = load_attention(store, network, migrated=True)
    assert before.checkpoint_digest == restored.checkpoint_digest
    assert state.count == 73
    probe = (1, 11, 17)
    refused = native_virtual_layer_probe(
        store, network, probe, expected_revision=before.revision,
        expected_checkpoint_digest=before.checkpoint_digest, grant_compute=False)
    accepted = native_virtual_layer_probe(
        store, network, probe, expected_revision=before.revision,
        expected_checkpoint_digest=before.checkpoint_digest, grant_compute=True)
    assert refused['action'] == 'DENY'
    assert tuple(accepted['effect']['result']['output']) == observe_probe(state, probe)
    vector = source_vector(73)
    committed, next_state, receipt = advance_session(store, network, before, state, vector,
                                                      migrated=True)
    assert committed.revision == 3
    # The exact same stale base+transition is recognized as replay, never re-anchored.
    again, _, _ = advance_session(store, network, before, state, vector, migrated=True)
    assert again.replayed and again.checkpoint_digest == committed.checkpoint_digest
    # Old checkpoint export cannot be reinstalled over new quorum high-water.
    stale_export_refused = False
    try:
        store.restore_export(export, backend_compatibility=compatible)
    except Exception as exc:
        from mailcpu.computational_session import ComputationalSessionIntegrityError
        if not isinstance(exc, ComputationalSessionIntegrityError):
            raise
        stale_export_refused = True
    assert stale_export_refused
    save_json(result, {
        'original_revision': before.revision,
        'resumed_revision': committed.revision,
        'incompatible_refused': incompatible_refused,
        'denied': refused, 'allowed': {'action': accepted['action'], 'calls': accepted['calls']},
        'probe_output': accepted['effect']['result']['output'],
        'probe_checkpoint': accepted['effect']['result']['checkpoint_digest'],
        'checkpoint_digest': committed.checkpoint_digest,
        'quorum_root': committed.lineage_manifest.digest,
        'source_head': next_state.source_head,
        'state_digest': next_state.fingerprint, 'receipt_output': list(receipt.output),
        'replayed': again.replayed, 'stale_export_refused': stale_export_refused,
        'old_source_reads': 0,
    })


if __name__ == '__main__':
    command, root, output = sys.argv[1:4]
    if command == 'prepare':
        prepare(Path(root), Path(output))
    elif command == 'resume':
        resume(Path(root), Path(output))
    else:
        raise SystemExit('unknown receiver command')
