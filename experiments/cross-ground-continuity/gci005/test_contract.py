"""GCI-005 finite phase-blind consensus/refusal contract tests."""
from __future__ import annotations
import unittest
import honesty_contract as h

class GCI005DecisionTests(unittest.TestCase):
    def test_agreement_admits_only_unique_parity(self):
        for bit in (0,1):
            decision=h.decisions({"observer-a":bit,"observer-b":bit})
            self.assertEqual(decision["status"],"ADMITTED_AGREEMENT")
            self.assertEqual(decision["admitted_value"],bit)
            self.assertEqual(decision["matching_receipt_count"],2)
            self.assertTrue(decision["returned_result"])

    def test_conflicting_authenticated_values_fail_closed(self):
        for bit in (0,1):
            decision=h.decisions({"observer-a":bit,"observer-b":1-bit})
            self.assertEqual(decision["status"],"REFUSED_DISAGREEMENT")
            self.assertIsNone(decision["admitted_value"])
            self.assertFalse(decision["returned_result"])

    def test_boolean_not_parity(self):
        for val in (True,False):
            with self.assertRaises(h.gci3.SufficiencyRefused):
                h.decisions({"observer-a":val,"observer-b":1})

    def test_one_peer_cannot_impersonate_quorum(self):
        for malformed in ({},{"observer-a":0},{"observer-a":0,"observer-c":0},
                          {"observer-a":0,"observer-b":0,"observer-c":0}):
            with self.assertRaises(h.gci3.SufficiencyRefused):
                h.decisions(malformed)

    def test_non_bit_refused(self):
        for val in (-1,2,1.0,None,"1"):
            with self.assertRaises(h.gci3.SufficiencyRefused):
                h.decisions({"observer-a":0,"observer-b":val})

if __name__=="__main__":
    unittest.main()
