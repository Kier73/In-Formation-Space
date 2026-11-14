"""PNF-003 actual socket delivery followed by native execution or denial."""
import unittest

from .test_native_execution import pair
from .transfer import transfer_pair


class NativeTransferTests(unittest.TestCase):
    def test_received_capsule_executes_native_cuts_in_separate_process(self):
        result = transfer_pair(*pair(), native_execution=True)
        native = result["receiver"]["report"]["native_execution"]
        self.assertNotEqual(result["sender_pid"], result["receiver_pid"])
        self.assertEqual(native["status"], "executed")
        self.assertEqual(native["native_handler_calls"], 4)
        self.assertEqual(native["numerical_verification"]["status"], "passed")

    def test_receiver_local_denial_survives_successful_authenticated_delivery(self):
        result = transfer_pair(*pair(), native_execution=True, grant_compute=False)
        report = result["receiver"]["report"]
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["native_execution"]["status"], "denied")
        self.assertEqual(report["native_execution"]["native_handler_calls"], 0)


if __name__ == "__main__":
    unittest.main()
