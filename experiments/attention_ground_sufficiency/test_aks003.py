"""AKS-003 native recovery gates and source-independent neural observation oracle."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from attention_ground import GroundRefused
from composed_attention import CausalState, InputEvidence, direct_history_reference
from aks003_attention_session import (
    FilePageBacking, decode_state, digest, direct_probe_oracle, encode_state,
    make_store, network_ground, observe_probe, source_vector,
)

WORKER = Path(__file__).with_name('aks003_worker.py')
NATIVE = importlib.util.find_spec('mailcpu') is not None


def source_state(count):
    network = network_ground()
    state = CausalState.empty(network)
    sources = []
    for i in range(count):
        evidence = InputEvidence.form(network, state.count, state.source_head, source_vector(i))
        state, _ = state.advance(evidence)
        sources.append(evidence)
    return state, tuple(sources)


class MathematicalSessionTests(unittest.TestCase):
    def test_bounded_state_matches_independent_quadratic_probe(self):
        network = network_ground()
        for count in (1, 7, 29, 73):
            state, sources = source_state(count)
            self.assertEqual(state.count, count)
            self.assertEqual(len(state.prefixes), 3)
            for vector in ((1, 11, 17), (1, 0, 1), (7, 12, 9)):
                self.assertEqual(observe_probe(state, vector), direct_probe_oracle(
                    network, tuple(source.vector for source in sources), vector))
            self.assertEqual(state, decode_state(network, encode_state(state)))
            self.assertEqual(len(state.source_head), 64)

    def test_compact_state_refuses_wrong_network_and_changed_moments(self):
        network = network_ground()
        state, _ = source_state(9)
        original = json.loads(encode_state(state))
        altered = dict(original)
        altered['network'] = 'f' * 64
        with self.assertRaises(GroundRefused):
            decode_state(network, json.dumps(altered).encode())
        changed = json.loads(encode_state(state))
        changed['checkpoint']['prefixes'][0][0]['mass'][0] += 1
        with self.assertRaisesRegex(GroundRefused, 'receiver-owned'):
            decode_state(network, json.dumps(changed).encode())


@unittest.skipUnless(NATIVE, 'native E-CPU not installed (CI native job requires the import)')
class NativeSessionTests(unittest.TestCase):
    def test_quorum_page_integrity_refuses_bit_flip(self):
        from mailcpu.computational_session import ComputationalSessionIntegrityError
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            network = network_ground()
            store = make_store(root, network, 'A')
            state, _ = source_state(12)
            saved = store.create_session(encode_state(state))
            self.assertEqual(store.load_latest().checkpoint_digest, saved.checkpoint_digest)
            for name in ('A.jsonl', 'B.jsonl', 'C.jsonl'):
                self.assertTrue((root / 'quorum' / name).is_file())
            pages = sorted((root / 'pages').iterdir())
            self.assertGreater(len(pages), 0)
            path = pages[0]
            raw = bytearray(path.read_bytes())
            raw[0] ^= 0x01
            path.write_bytes(raw)
            with self.assertRaisesRegex(ComputationalSessionIntegrityError, 'M1 integrity'):
                store.load_latest()

    def test_hard_kill_and_new_receiver_host_quorum_reattach_without_history_replay(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            marker = root / 'marker.json'
            result = root / 'result.json'
            child = subprocess.Popen(
                [sys.executable, str(WORKER), 'prepare', str(root), str(marker)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                deadline = time.monotonic() + 50
                while not marker.exists() and time.monotonic() < deadline:
                    if child.poll() is not None:
                        out, err = child.communicate(timeout=10)
                        self.fail('initial receiver exited without durable marker: ' + err + out)
                    time.sleep(0.1)
                self.assertTrue(marker.is_file(), 'initial receiver never fsynced marker')
                evidence = json.loads(marker.read_text())
                self.assertEqual(evidence['revision'], 2)
                self.assertEqual(evidence['count'], 73)
                self.assertEqual(child.poll(), None)
                self.assertEqual(evidence['pid'], child.pid)
                self.assertTrue((root / 'export-A.json').is_file())
            finally:
                if child.poll() is None:
                    child.kill()
                out, err = child.communicate(timeout=10)
            self.assertNotEqual(child.returncode, 0, 'prepare process exited gracefully')
            # New interpreter, fresh HeadlessOS, new M3 session root (host B).
            renewed = subprocess.run(
                [sys.executable, str(WORKER), 'resume', str(root), str(result)],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(renewed.returncode, 0, renewed.stdout + renewed.stderr)
            self.assertTrue(result.is_file())
            data = json.loads(result.read_text())
            self.assertEqual((data['original_revision'], data['resumed_revision']), (2, 3))
            self.assertTrue(data['incompatible_refused'])
            self.assertEqual(data['denied'], {'action': 'DENY', 'calls': 0})
            self.assertEqual(data['allowed'], {'action': 'ALLOW', 'calls': 1})
            self.assertTrue(data['replayed'])
            self.assertTrue(data['stale_export_refused'])
            self.assertEqual(data['old_source_reads'], 0)
            self.assertEqual(data['probe_checkpoint'], evidence['checkpoint_digest'])
            unbroken, inputs = source_state(74)
            self.assertEqual(data['state_digest'], unbroken.fingerprint)
            self.assertEqual(data['source_head'], unbroken.source_head)
            self.assertEqual(tuple(data['receipt_output']),
                             direct_history_reference(network_ground(), inputs)[-1])
            expected_probe = direct_probe_oracle(
                network_ground(), tuple(source.vector for source in inputs[:73]),
                (1, 11, 17))
            self.assertEqual(tuple(data['probe_output']), expected_probe)
            self.assertEqual(len(data['quorum_root']), 64)
            self.assertEqual(len(data['checkpoint_digest']), 64)
            # The target is a different interpreter with a different session root.
            self.assertTrue((root / 'hosts' / 'B').is_dir())
            for journal in ('A.jsonl', 'B.jsonl', 'C.jsonl'):
                self.assertTrue((root / 'quorum' / journal).is_file())


if __name__ == '__main__':
    unittest.main()
