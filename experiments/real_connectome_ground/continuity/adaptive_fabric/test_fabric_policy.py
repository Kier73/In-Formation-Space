"""RCG-003: synthetic host-path adaptation never changes verified Ground results."""
from __future__ import annotations
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[2]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
if str(BASE/'continuity') not in sys.path:
    sys.path.insert(0, str(BASE/'continuity'))

from test_connectome_ground import small_ground
from connectome_ground import Query
from adaptive_fabric.fabric_policy import (
    FabricRefused, HostPath, Workload, candidates, experiment, fit, navigate,
    observation, observe_synthetic_latency, predict, realize_selected,
    synthesize_workloads, training_data, verify_observation,
)


class FabricTests(unittest.TestCase):
    def setUp(self):
        self.ground = small_ground()
        self.example = Workload.from_ground(self.ground, Query('AWCL', 'AIYL', 2))

    def test_features_are_ground_bounded(self):
        w = self.example
        self.assertEqual(w.cone_edges, 8)
        self.assertEqual(w.full_edges, 40)
        self.assertGreater(w.cone_payload_bytes, w.full_payload_bytes)
        self.assertEqual(w.feature(candidates()[0], 0)[1], 8)
        self.assertEqual(w.feature(candidates()[1], 0)[1], 40)

    def test_train_genuine_exact_fitted_cost_estimator_and_holdout(self):
        tasks = synthesize_workloads(self.ground, 19, seed=62)
        self.assertEqual(len({tuple(sorted(w.request.items())) for w in tasks}), 19)
        fit_records = training_data(self.ground, tasks[:13], seed=63)
        trained = fit(self.ground, fit_records)
        self.assertEqual(len(trained['coefficients']), 6)
        for task in tasks[13:]:
            for path in candidates():
                expected = observe_synthetic_latency(path, task.feature(path, 45))
                self.assertEqual(predict(trained, self.ground, task, path, 45), expected)
        selected = navigate(trained, self.ground, tasks[-1], candidates(),
                            {'local-worker': 30, 'transit-worker': 7, 'artifact-worker': 1})
        realized = realize_selected(self.ground, tasks[-1], selected)
        self.assertTrue(realized['oracle_checked'])
        self.assertEqual(realized['status'], 'local-reference-execution-not-remote-authorization')

    def test_adapts_to_host_permission_and_queue_changes(self):
        tasks = synthesize_workloads(self.ground, 18, seed=77)
        trained = fit(self.ground, training_data(self.ground, tasks[:14], seed=78))
        query = tasks[-1]
        routes = candidates()
        a = navigate(trained, self.ground, query, routes,
                     {'local-worker': 0, 'transit-worker': 0, 'artifact-worker': 0})
        denied = [replace(p, permitted=False) if p.host == a['chosen']['host'] else p
                  for p in routes]
        b = navigate(trained, self.ground, query, denied,
                     {'local-worker': 0, 'transit-worker': 0, 'artifact-worker': 0})
        self.assertNotEqual(b['chosen']['host'], a['chosen']['host'])
        with self.assertRaisesRegex(FabricRefused, 'all candidates'):
            navigate(trained, self.ground, query,
                     [replace(p, available=False) for p in routes],
                     {'local-worker': 0, 'transit-worker': 0, 'artifact-worker': 0})
        with self.assertRaises(FabricRefused):
            navigate(trained, self.ground, query, routes, {'local-worker': 0})

    def test_tamper_and_unearned_authority_refused(self):
        host = candidates()[0]
        record = observation(self.ground, self.example, host, 5)
        verify_observation(self.ground, self.example, record)
        with self.assertRaises(FabricRefused):
            verify_observation(self.ground, self.example,
                               {**record, 'duration': '0/1'})
        trained = fit(self.ground, training_data(self.ground,
                                                 synthesize_workloads(self.ground, 14, seed=31),seed=4))
        selected = navigate(trained, self.ground, self.example, candidates(),
                            {'local-worker': 0, 'transit-worker': 0, 'artifact-worker': 0})
        with self.assertRaises(FabricRefused):
            realize_selected(self.ground, self.example, {**selected, 'digest': 'a'*64})
        with self.assertRaises(FabricRefused):
            predict({**trained, 'digest': '0'*64}, self.ground, self.example, host, 0)
        with self.assertRaises(FabricRefused):
            observation(self.ground, self.example, replace(host, permitted=False), 0)

    def test_source_pinned_synthetic_experiment_is_repeatable(self):
        x = experiment(self.ground, train_count=14, test_count=8, seed=200)
        y = experiment(self.ground, train_count=14, test_count=8, seed=200)
        self.assertEqual(x, y)
        self.assertEqual(x['synthetic_policy_regret'], '0/1')
        self.assertEqual(x['synthetic_prediction_absolute_error'], '0/1')
        self.assertEqual(len(x['verified_held_out_results']), 8)
        self.assertTrue(x['train_measurements'] > 0)
        self.assertEqual(set(x['training_query_digests']) &
                         set(x['held_out_query_digests']), set())

    def test_real_source_if_present(self):
        source = BASE / 'data' / 'herm_full_edgelist.csv'
        if not source.is_file():
            self.skipTest('full OpenWorm CSV is committed on ancestor PR; GitHub CI tests it')
        from connectome_ground import ConnectomeGround
        ground = ConnectomeGround.from_csv(source.read_bytes())
        result = experiment(ground, train_count=18, test_count=12, seed=61)
        self.assertEqual(result['held_out_tasks'], 12)
        self.assertEqual(result['synthetic_policy_regret'], '0/1')
        self.assertGreater(len(result['selected_paths']), 0)


if __name__ == '__main__':
    unittest.main()
