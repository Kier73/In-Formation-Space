"""RE-004 regression: causal attribution, admission, handoff, negative controls."""
import copy
import unittest

from intervention_or_drift import (
    LAWS, EvidenceError, canonical, digest, initial_state, produce_a, produce_b,
    raw_from, reconstruct, run, transition, validate,
)


class GeneratingLawTests(unittest.TestCase):
    def test_action_and_triggered_external_are_identical_through_original_readout(self):
        strong = initial_state()
        triggered = initial_state()
        for action in ("apply", "idle", "apply", "idle", "read", "apply"):
            a, strong, _ = transition(LAWS["high_gain"], strong, action)
            b, triggered, _ = transition(LAWS["triggered_external"], triggered, action)
            self.assertEqual(a, b)
        self.assertNotEqual(strong[1], triggered[1])

    def test_ambient_drift_is_distinguished_by_no_command_control(self):
        p = initial_state()
        q = initial_state()
        observed = []
        for action in ("apply", "idle"):
            u, p, _ = transition(LAWS["triggered_external"], p, action)
            v, q, _ = transition(LAWS["ambient_external"], q, action)
            observed.append((u, v))
        self.assertEqual(observed, [(2, 2), (2, 3)])

    def test_external_witness_reveals_unobserved_component(self):
        a = initial_state()
        b = initial_state()
        for law, init in ((LAWS["high_gain"], a), (LAWS["triggered_external"], b)):
            pass
        _, a, _ = transition(LAWS["high_gain"], a, "apply")
        _, b, _ = transition(LAWS["triggered_external"], b, "apply")
        y1, a, _ = transition(LAWS["high_gain"], a, "witness")
        y2, b, _ = transition(LAWS["triggered_external"], b, "witness")
        self.assertEqual((y1, y2), (0, 1))

    def test_isolation_changes_predictions_but_requires_modeled_assumption(self):
        a, b = initial_state(), initial_state()
        strong, a, _ = transition(LAWS["high_gain"], a, "isolated_apply")
        triggered, b, _ = transition(LAWS["triggered_external"], b, "isolated_apply")
        self.assertEqual((strong, triggered), (2, 1))

    def test_observational_alias_never_separated_by_declared_probes(self):
        a = b = initial_state()
        for action in ("apply", "idle", "witness", "isolated_apply", "read") * 4:
            av, a, _ = transition(LAWS["high_gain"], a, action)
            bv, b, _ = transition(LAWS["coordinate_alias"], b, action)
            self.assertEqual(av, bv)
        self.assertNotEqual(a, b)

    def test_separate_sensor_calibrations_are_not_equal_raw_readings(self):
        self.assertEqual(raw_from("A", 2), 2)
        self.assertEqual(raw_from("B", 2), 8)


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.a = produce_a("triggered_external")
        self.grants = frozenset({"environment:read"})
        self.b = produce_b("triggered_external", self.a["handoff"],
                           self.a["private_checkpoint"], self.a["private_nonce"],
                           ("witness",), self.grants)

    def check(self, *, a=None, b=None, handoff=None, grants=None):
        return reconstruct(self.a["records"] if a is None else a,
                           self.b["records"] if b is None else b,
                           self.a["handoff"] if handoff is None else handoff,
                           self.grants if grants is None else grants)

    def test_a_observations_leave_causally_distinct_laws(self):
        self.assertEqual(self.check(b=[])['survivors'],
                         ["coordinate_alias", "high_gain", "triggered_external"])

    def test_authorized_witness_selects_single_model_within_catalogue(self):
        self.assertEqual(self.check()['survivors'], ["triggered_external"])
        self.assertIsNone(self.check()['physical_source_attribution'])

    def test_authority_refusal_does_not_change_state_or_eliminate_candidate(self):
        b = produce_b("triggered_external", self.a["handoff"],
                      self.a["private_checkpoint"], self.a["private_nonce"],
                      ("witness",), ())
        self.assertEqual(b['records'][0]['status'], 'refused')
        self.assertIsNone(b['records'][0]['raw'])
        self.assertEqual(self.check(b=b['records'], grants=frozenset())['survivors'],
                         ["coordinate_alias", "high_gain", "triggered_external"])

    def test_isolated_action_differentiates_actuation_if_isolation_guarantee_trusted(self):
        b = produce_b("triggered_external", self.a["handoff"],
                      self.a["private_checkpoint"], self.a["private_nonce"],
                      ("isolated_apply",), ("external:isolate",))
        self.assertEqual(self.check(b=b['records'], grants=frozenset({"external:isolate"}))['survivors'],
                         ["triggered_external"])

    def test_denied_isolation_leaves_equivalence(self):
        b = produce_b("triggered_external", self.a["handoff"],
                      self.a["private_checkpoint"], self.a["private_nonce"],
                      ("isolated_apply",), ())
        self.assertEqual(self.check(b=b['records'], grants=frozenset())['survivors'],
                         ["coordinate_alias", "high_gain", "triggered_external"])

    def test_witness_claim_without_verifier_permission_fails_closed(self):
        with self.assertRaisesRegex(EvidenceError, 'unadmitted'):
            self.check(grants=frozenset())

    def test_changed_record_payload_fails(self):
        changed = copy.deepcopy(self.b['records'])
        changed[0]['raw'] = 8
        with self.assertRaisesRegex(EvidenceError, 'digest mismatch'):
            self.check(b=changed)

    def test_rehashed_measurement_can_fool_naive_digest_but_not_model_consistency(self):
        changed = copy.deepcopy(self.b['records'])
        changed[0]['raw'] = raw_from('B', 0)
        changed[0]['digest'] = digest({k:v for k,v in changed[0].items() if k != 'digest'})
        self.assertEqual(self.check(b=changed)['survivors'], ['coordinate_alias', 'high_gain'])
        # Non-cryptographic trust: this is a concrete reason unkeyed hashes are not signatures.

    def test_lost_host_a_event_rejected(self):
        with self.assertRaisesRegex(EvidenceError, 'missing host A'):
            self.check(a=self.a['records'][1:])

    def test_handoff_source_head_tampering_rejected_even_after_rehash(self):
        h = copy.deepcopy(self.a['handoff'])
        h['source_head'] = '0' * 64
        h['digest'] = digest({k:v for k,v in h.items() if k != 'digest'})
        with self.assertRaisesRegex(EvidenceError, 'disconnected'):
            self.check(handoff=h)

    def test_wrong_private_checkpoint_rejected_at_receiver(self):
        with self.assertRaisesRegex(EvidenceError, 'checkpoint bytes'):
            produce_b('triggered_external', self.a['handoff'], [2, 0, 0],
                      self.a['private_nonce'], ('witness',), self.grants)

    def test_local_clock_regression_detected(self):
        a = copy.deepcopy(self.a['records'])
        a[1]['local_tick'] = a[0]['local_tick']
        a[1]['digest'] = digest({k:v for k,v in a[1].items() if k != 'digest'})
        with self.assertRaisesRegex(EvidenceError, 'local clock'):
            self.check(a=a)

    def test_per_host_clock_values_cannot_establish_global_elapsed(self):
        self.assertLess(self.b['records'][0]['local_tick'], self.a['records'][0]['local_tick'])
        self.assertIsNone(self.check()['global_elapsed'])

    def test_cannot_infer_external_causality_from_source_handoff(self):
        self.assertIn('no inferred external event causality', self.check()['causal_scope'])

    def test_separate_processes_and_verifier(self):
        r = run()
        self.assertTrue(r['separate_producer_pids'])
        self.assertEqual(r['combined']['survivors'], ['triggered_external'])
        self.assertEqual(r['a_only_survivors'], ['coordinate_alias', 'high_gain', 'triggered_external'])

    def test_refusal_still_requires_handoff_chain(self):
        b = produce_b('triggered_external', self.a['handoff'],
                      self.a['private_checkpoint'], self.a['private_nonce'], ('witness',), ())
        bad = copy.deepcopy(b['records'])
        bad[0]['handoff_digest'] = '1' * 64
        bad[0]['digest'] = digest({k:v for k,v in bad[0].items() if k != 'digest'})
        with self.assertRaisesRegex(EvidenceError, 'continuity'):
            self.check(b=bad, grants=frozenset())

    def test_no_witness_implies_no_unique_attribution(self):
        for name in ('high_gain', 'triggered_external', 'coordinate_alias'):
            a = produce_a(name)
            result = reconstruct(a['records'], [], a['handoff'])
            self.assertEqual(result['survivors'], ['coordinate_alias', 'high_gain', 'triggered_external'])

if __name__ == '__main__':
    unittest.main()
