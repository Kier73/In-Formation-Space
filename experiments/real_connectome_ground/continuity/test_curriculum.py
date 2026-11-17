"""Guarantee incomplete evidence cannot promote biological/adaptive training."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from continuity.continuity import Chronicle, ContinuityRefused, GENESIS
from continuity.evaluate_curriculum import assess
from continuity.test_continuity import fixture
from connectome_ground import Query

COURSES = json.loads(Path(__file__).with_name('training_tracks.json').read_text())


class CurriculumEvidenceGates(unittest.TestCase):
    def test_proposed_training_has_explicit_missing_gates(self):
        g = fixture()
        with tempfile.TemporaryDirectory() as location:
            store = Chronicle(Path(location))
            start = store.source(g, expected_head=GENESIS)
            empty = assess(g, store, expected_head=start['head'], curricula=COURSES)
            self.assertTrue(all(x['status'] == 'blocked' for x in empty['opportunities']))
            result = store.query(g, Query('AWCL', 'AIYL', 2), expected_head=start['head'])
            report = assess(g, Chronicle(Path(location)), expected_head=result['head'], curricula=COURSES)
            status = {row['id']: row for row in report['opportunities']}
            self.assertEqual(status['body.structural-transfer-distillation.v1']['status'], 'design-ready')
            self.assertEqual(status['mind.observation-valued-navigation-policy.v1']['status'], 'blocked')
            self.assertEqual(status['body.dynamics-with-calibrated-signals.v1']['status'], 'blocked')
            self.assertTrue(all(not r['trained_model_exists'] for r in report['opportunities']))
            self.assertEqual(report['ground'], g.fingerprint)
            # Three observations of one pair must not satisfy a varied-corpus gate.
            current = result['head']
            for _ in range(2):
                current = store.query(g, Query('AWCL', 'AIYL', 2), expected_head=current)['head']
            repeat_report = assess(g, store, expected_head=current, curricula=COURSES)
            by_id = {row['id']: row for row in repeat_report['opportunities']}
            self.assertEqual(by_id['mind.observation-valued-navigation-policy.v1']['status'], 'blocked')

    def test_forged_curriculum_refused(self):
        g = fixture()
        with tempfile.TemporaryDirectory() as location:
            store = Chronicle(Path(location))
            start = store.source(g)
            altered = {**COURSES, 'schema': 'forged'}
            with self.assertRaises(ContinuityRefused):
                assess(g, store, expected_head=start['head'], curricula=altered)
            changed = {**COURSES, 'opportunities': COURSES['opportunities'][:-1]}
            with self.assertRaises(ContinuityRefused):
                assess(g, store, expected_head=start['head'], curricula=changed)


if __name__ == '__main__':
    unittest.main()
