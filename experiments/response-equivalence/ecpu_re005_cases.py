"""Hosted checks against the pinned real E-CPU TemporalContext implementation."""
from __future__ import annotations

import copy
import unittest

from mailcpu.temporal import CausalRelation, CausalStamp
from ecpu_re005_hosts import source, witness, receiver, verify
from independent_event_causation import EvidenceError, enroll, sha


class HostedECPUChecks(unittest.TestCase):
    def setUp(self):
        self.registration = enroll()
        self.a = source()
        self.c = witness(self.registration)
        self.b = receiver(self.a, self.c)

    def test_real_stamps_reconstruct_concurrent_producers_and_dual_handoff(self):
        result = verify(self.a, self.c, self.b, self.registration)
        self.assertEqual(result["causal_relation"]["A2_C2"], "concurrent")
        self.assertEqual(result["causal_relation"]["A2_B0"], "before")
        self.assertEqual(result["causal_relation"]["C2_B0"], "before")
        self.assertIsNone(result["combined_cross_host_elapsed"])

    def test_independent_witness_does_not_prove_physical_cause(self):
        result = verify(self.a, self.c, self.b, self.registration)
        self.assertEqual(result["identification"]["survivors"],
                         ["common_cause_alias", "common_cause_marker", "event_causal"])
        self.assertFalse(result["physical_causation_proved"])

    def test_control_requires_explicit_outside_assumption(self):
        result = verify(self.a, self.c, self.b, self.registration, controlled_exclusion_assured=True)
        self.assertEqual(result["identification"]["survivors"],
                         ["common_cause_alias", "common_cause_marker"])
        self.assertFalse(result["physical_causation_proved"])

    def test_refused_witness_is_unobserved(self):
        c = witness(self.registration, permitted=False)
        b = receiver(self.a, c)
        result = verify(self.a, c, b, self.registration, controlled_exclusion_assured=True)
        self.assertEqual(result["identification"]["survivors"],
                         ["common_cause_alias", "common_cause_marker", "event_causal"])

    def test_false_causal_dependence_between_sources_is_rejected(self):
        changed = copy.deepcopy(self.c)
        for i, r in enumerate(changed["records"]):
            r["causal"]["vector"]["A"] = 1
            r["causal"]["lamport"] += 1
            r["digest"] = sha({k:v for k,v in r.items() if k != "digest"})
        # Changes cannot pass the separate witness authentication key.
        with self.assertRaisesRegex(EvidenceError, "authentication"):
            verify(self.a, changed, self.b, self.registration)

    def test_rewritten_receiver_stamp_without_dual_merge_rejected(self):
        b = copy.deepcopy(self.b)
        for rec in b["records"]:
            rec["causal"]["vector"]["C"] = 0
            rec["digest"] = sha({k:v for k,v in rec.items() if k != "digest"})
        with self.assertRaisesRegex(EvidenceError, "handoffs"):
            verify(self.a, self.c, b, self.registration)

    def test_replayed_source_stamp_not_valid_increment(self):
        a = copy.deepcopy(self.a)
        a["records"][1]["causal"] = copy.deepcopy(a["records"][0]["causal"])
        a["records"][1]["digest"] = sha({k:v for k,v in a["records"][1].items() if k != "digest"})
        # The receiver's existing linkage no longer matches, even before clock validation.
        with self.assertRaisesRegex(EvidenceError, "different evidence"):
            verify(a, self.c, self.b, self.registration)

if __name__ == "__main__":
    unittest.main(verbosity=2)
