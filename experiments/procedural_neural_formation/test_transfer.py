"""Actual separate-process E-CPU mTLS transfer, not mocked transport."""
import unittest

from .capsule import pack_pair
from .formation import FormationError, procedural_block, widen
from .transfer import transfer_pair
from .test_capsule import rewrite, rehash


class TransferTests(unittest.TestCase):
    def pair(self, hidden=16):
        source = procedural_block(8, hidden, 8)
        generated, certificate = widen(source, hidden * 2)
        return pack_pair(source, generated, certificate, {"kind": "procedural", "seed": 31}, [[0.5] * 8])

    def test_separate_receiver_reconstructs_multiframe_model_pair(self):
        raw, policy = self.pair(1024)
        result = transfer_pair(raw, policy)
        self.assertNotEqual(result["sender_pid"], result["receiver_pid"])
        self.assertGreater(result["chunk_count"], 1)
        self.assertEqual(result["receiver"]["report"]["status"], "verified")
        self.assertFalse(result["shared_parameter_file_used"])

    def test_receiver_refuses_wrong_external_source_identity(self):
        raw, policy = self.pair()
        result = transfer_pair(raw, {**policy, "source_digest": "a" * 64})
        self.assertEqual(result["receiver"]["report"]["status"], "rejected")
        self.assertIn("model identity", result["receiver"]["report"]["reason"])

    def test_rehashed_bad_certificate_rejected_at_receiver(self):
        raw, policy = self.pair()
        altered = rewrite(raw, lambda h: h["certificate"]["parent_index"].__setitem__(0, 1))
        result = transfer_pair(altered, rehash(altered, policy))
        self.assertEqual(result["receiver"]["report"]["status"], "rejected")
        self.assertIn("incoming", result["receiver"]["report"]["reason"])

    def test_bad_receiver_certificate_pin_prevents_transfer(self):
        raw, policy = self.pair()
        with self.assertRaisesRegex(FormationError, "certificate pin"):
            transfer_pair(raw, policy, expected_receiver_pin="0" * 64)


if __name__ == "__main__":
    unittest.main()
