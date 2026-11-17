"""RCG-002 genuine persistence and source/authority-negative tests."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from dataclasses import replace

from connectome_ground import ConnectomeGround, ConnectomeRefused, Query, canonical, sha
from test_connectome_ground import ACTUAL_SOURCE_ROWS
from continuity.continuity import Chronicle, ContinuityRefused, GENESIS, queried_capsule, source_manifest


def fixture() -> ConnectomeGround:
    return ConnectomeGround.from_csv(ACTUAL_SOURCE_ROWS.encode(), require_original=False)


class DurableConnectomeContinuityTests(unittest.TestCase):
    def test_restart_query_audit_training_intent_and_external_pin(self):
        with tempfile.TemporaryDirectory() as base:
            g = fixture()
            first = Chronicle(Path(base))
            source = first.source(g, expected_head=GENESIS)
            self.assertEqual(first.read_event(0), source_manifest(g))
            source_head = source['head']
            # New process-equivalent Chronicle instance opens the persisted files.
            reopened = Chronicle(Path(base))
            result = reopened.query(g, Query('AWCL', 'AIYL', 2), expected_head=source_head)
            self.assertEqual(result['index'], 1)
            capsule = reopened.read_event(1)
            self.assertEqual(capsule['plan']['query']['source'], 'AWCL')
            self.assertEqual(capsule['independent_full_reference'],
                             str(g.independent_whole_graph(Query('AWCL', 'AIYL', 2))))
            next_head = result['head']
            episode = {'id': 'body.structural-probe.v1', 'status': 'proposed',
                       'label_source': 'mathematical-reference', 'not_biological_labels': True}
            final = Chronicle(Path(base)).training_plan(g, episode, expected_head=next_head)
            self.assertEqual(final['index'], 2)
            audit = Chronicle(Path(base)).audit(g, expected_head=final['head'])
            self.assertEqual(audit['counts'], {'source': 1, 'query': 1, 'training-plan': 1})
            self.assertEqual(len(reopened.verify(expected_head=final['head'])), 3)
            with self.assertRaisesRegex(ContinuityRefused, 'high-water'):
                reopened.verify(expected_head=next_head)
            with self.assertRaisesRegex(ContinuityRefused, 'high-water'):
                reopened.query(g, Query('AWCL', 'AIYL', 2), expected_head=source_head)

    def test_durable_objects_tamper_missing_and_partial_lineage_refuse(self):
        with tempfile.TemporaryDirectory() as base:
            g = fixture()
            store = Chronicle(Path(base))
            first = store.source(g)
            second = store.query(g, Query('AWCL', 'AIYL', 2), expected_head=first['head'])
            item = store.objects / (second['object'] + '.json')
            good = item.read_bytes()
            item.write_bytes(good[:-1] + b'0')
            with self.assertRaisesRegex(ContinuityRefused, 'bytes differ'):
                Chronicle(Path(base)).verify()
            item.write_bytes(good)
            item.unlink()
            with self.assertRaisesRegex(ContinuityRefused, 'missing'):
                Chronicle(Path(base)).verify()
            item.write_bytes(good)
            with store.ledger.open('ab') as f:
                f.write(b'{"partial":')
            with self.assertRaisesRegex(ContinuityRefused, 'truncated'):
                Chronicle(Path(base)).verify()

    def test_rehashing_new_source_or_forged_observation_cannot_pass_audit(self):
        with tempfile.TemporaryDirectory() as base:
            g = fixture()
            other = ConnectomeGround.from_csv(ACTUAL_SOURCE_ROWS.replace(
                'AWCL,AFDL,2,chemical', 'AWCL,AFDL,3,chemical').encode(), require_original=False)
            store = Chronicle(Path(base))
            first = store.source(g)
            with self.assertRaisesRegex(ContinuityRefused, 'source identity differs'):
                store.source(other, expected_head=first['head'])
            with self.assertRaisesRegex(ContinuityRefused, 'differs from retained original source'):
                store.query(other, Query('AWCL', 'AIYL', 2), expected_head=first['head'])
            # Construct forged but internally hash-consistent capsule by intentionally
            # bypassing semantic query API through the underscored test-only method.
            plan = queried_capsule(g, Query('AWCL', 'AIYL', 2))
            plan['observation']['transfer'] = '0/1'
            forged = store._append('query', plan, expected_head=first['head'])
            self.assertEqual(len(store.verify(expected_head=forged['head'])), 2)
            with self.assertRaisesRegex(ContinuityRefused, 'independently recomputed'):
                store.audit(g, expected_head=forged['head'])

    def test_concurrent_writer_refusal_and_unpermitted_training_celebration(self):
        with tempfile.TemporaryDirectory() as base:
            g = fixture()
            store = Chronicle(Path(base))
            first = store.source(g)
            store.lock.write_text('different writer')
            with self.assertRaisesRegex(ContinuityRefused, 'another writer'):
                store.training_plan(g, {'id': 'mind.v1', 'status': 'proposed'}, expected_head=first['head'])
            store.lock.unlink()
            with self.assertRaisesRegex(ContinuityRefused, 'explicitly proposed'):
                store.training_plan(g, {'id': 'mind.v1', 'status': 'trained'}, expected_head=first['head'])

    def test_full_source_when_pinned_release_present(self):
        p = Path(__file__).resolve().parents[1] / 'data' / 'herm_full_edgelist.csv'
        if not p.is_file():
            self.skipTest('source is committed to RCG-001 branch and checked by hosted CI')
        ground = ConnectomeGround.from_csv(p.read_bytes())
        self.assertEqual(len(ground.edges), 7379)
        self.assertEqual(len(ground.nodes), 448)
        self.assertEqual(source_manifest(ground)['synapse_types'],
                         {'chemical': 4681, 'electrical': 2698})
        with tempfile.TemporaryDirectory() as base:
            store = Chronicle(Path(base))
            first = store.source(ground, expected_head=GENESIS)
            second = store.query(ground, Query('ASHL', 'AVAL', 3), expected_head=first['head'])
            self.assertEqual(store.audit(ground, expected_head=second['head'])['counts']['query'], 1)


if __name__ == '__main__':
    unittest.main()
