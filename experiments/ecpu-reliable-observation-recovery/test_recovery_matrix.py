import unittest

from run_recovery_matrix import (
    DROP_FIRST_ACK,
    DROP_FIRST_DATA_FRAME,
    QUORUM_WIDTHS,
    SOURCE_COUNTS,
    fault_drop_indices,
    matrix_conditions,
    validate_attempt_result,
    validate_condition,
)


class RecoveryMatrixTests(unittest.TestCase):
    def test_source_count_and_quorum_are_orthogonally_crossed(self):
        conditions = matrix_conditions()
        self.assertEqual(len(conditions), 24)
        self.assertEqual(
            {(item["source_count"], item["quorum"]) for item in conditions},
            {(source_count, quorum)
             for source_count in SOURCE_COUNTS
             for quorum in QUORUM_WIDTHS},
        )
        self.assertEqual(
            {item["drop_first_data_frame"] for item in conditions},
            set(DROP_FIRST_DATA_FRAME),
        )
        self.assertEqual(
            {item["drop_first_ack"] for item in conditions},
            set(DROP_FIRST_ACK),
        )
        for condition in conditions:
            self.assertEqual(validate_condition(condition), condition)

    def test_quorum_levels_are_feasible_for_every_source_count(self):
        self.assertTrue(all(
            quorum <= source_count
            for source_count in SOURCE_COUNTS
            for quorum in QUORUM_WIDTHS
        ))

    def test_fault_schedule_separates_data_and_ack_loss(self):
        self.assertEqual(
            fault_drop_indices(
                "S00", "S00",
                drop_first_data_frame=False, drop_first_ack=False,
            ),
            frozenset(),
        )
        self.assertEqual(
            fault_drop_indices(
                "S00", "S00",
                drop_first_data_frame=True, drop_first_ack=False,
            ),
            frozenset({1}),
        )
        self.assertEqual(
            fault_drop_indices(
                "S00", "S00",
                drop_first_data_frame=False, drop_first_ack=True,
            ),
            frozenset({2}),
        )
        self.assertEqual(
            fault_drop_indices(
                "S00", "S00",
                drop_first_data_frame=True, drop_first_ack=True,
            ),
            frozenset({1, 3}),
        )

    def test_non_target_sources_never_receive_injected_loss(self):
        self.assertEqual(
            fault_drop_indices(
                "S01", "S00",
                drop_first_data_frame=True, drop_first_ack=True,
            ),
            frozenset(),
        )

    def test_condition_rejects_quorum_outside_full_cross(self):
        invalid = {
            "source_count": 4,
            "quorum": 8,
            "drop_first_data_frame": False,
            "drop_first_ack": False,
        }
        with self.assertRaisesRegex(ValueError, "quorum"):
            validate_condition(invalid)

    def test_attempt_contract_rejects_double_application(self):
        valid = {
            "source_count": 4,
            "drop_first_data_frame": True,
            "drop_first_ack": True,
            "authorization_status": "AUTHORIZED",
            "admitted_source_count_after_recovery": 4,
            "data_retry_count": 1,
            "data_recovery_link_count": 1,
            "ack_retry_count": 1,
            "duplicate_cleanup_count": 1,
            "application_count": 1,
            "register_readback": 1,
            "checkpoint_digest_reconstructed": True,
            "durable_log_verified": True,
            "final_pending_sequences": {"S00": [], "S01": [], "S02": [], "S03": []},
        }
        self.assertEqual(validate_attempt_result(valid), valid)
        invalid = dict(valid, application_count=2)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            validate_attempt_result(invalid)


if __name__ == "__main__":
    unittest.main()
