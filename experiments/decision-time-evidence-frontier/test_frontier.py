from __future__ import annotations

import copy
import unittest

import frontier


class DecisionTimeEvidenceFrontierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = frontier.build_fixture()
        self.report = frontier.build_report(self.bundle)
        self.decisions = {
            item["decision_id"]: item for item in self.report["decision_assessments"]
        }

    @staticmethod
    def message(decision: dict, message_id: str) -> dict:
        return next(item for item in decision["messages"] if item["message_id"] == message_id)

    def test_old_send_precedes_d1_but_arrives_after_it(self) -> None:
        d1 = self.decisions["D1"]
        m1 = self.message(d1, "m1")
        self.assertEqual(m1["source_send_to_decision"], "before")
        self.assertEqual(m1["decision_to_receiver_intake"], "before")
        self.assertEqual(m1["availability"], "arrived_after_decision")
        self.assertFalse(m1["controller_declared_used"])

    def test_newer_message_is_available_and_used_at_d1(self) -> None:
        d1 = self.decisions["D1"]
        m2 = self.message(d1, "m2")
        self.assertEqual(d1["frontier_status"], "complete")
        self.assertEqual(d1["reconstructed_available_message_ids"], ["m2"])
        self.assertEqual(m2["source_send_to_decision"], "before")
        self.assertEqual(m2["decision_to_receiver_intake"], "after")
        self.assertEqual(m2["availability"], "available_at_decision")
        self.assertTrue(m2["controller_declared_used"])

    def test_available_and_used_are_not_collapsed(self) -> None:
        d2 = self.decisions["D2"]
        self.assertEqual(d2["reconstructed_available_message_ids"], ["m1", "m2"])
        self.assertEqual(d2["controller_declared_used_message_ids"], ["m2"])
        m1 = self.message(d2, "m1")
        self.assertEqual(m1["availability"], "available_at_decision")
        self.assertFalse(m1["controller_declared_used"])

    def test_missing_receiver_prefix_is_unknown_not_absent_or_late(self) -> None:
        report = frontier.build_report(frontier.build_fixture(omit_receiver_event=1))
        d1 = next(item for item in report["decision_assessments"] if item["decision_id"] == "D1")
        self.assertEqual(d1["frontier_status"], "unknown_incomplete_log")
        self.assertIsNone(d1["reconstructed_available_message_ids"])
        self.assertEqual(self.message(d1, "m1")["availability"], "unknown_incomplete_log")
        self.assertEqual(self.message(d1, "m2")["availability"], "unknown_incomplete_log")

    def test_available_claim_must_match_complete_receiver_prefix(self) -> None:
        altered = copy.deepcopy(self.bundle)
        decision = altered["receiver_events"][1]
        decision["available_message_ids"] = []
        core = {key: value for key, value in decision.items() if key != "event_digest"}
        decision["event_digest"] = frontier.digest(core)
        following = altered["receiver_events"][2]
        following["previous_digest"] = decision["event_digest"]
        following_core = {key: value for key, value in following.items() if key != "event_digest"}
        following["event_digest"] = frontier.digest(following_core)
        last = altered["receiver_events"][3]
        last["previous_digest"] = following["event_digest"]
        last["frontier_head_digest"] = following["event_digest"]
        last_core = {key: value for key, value in last.items() if key != "event_digest"}
        last["event_digest"] = frontier.digest(last_core)
        with self.assertRaisesRegex(frontier.FrontierError, "available set"):
            frontier.build_report(altered)

    def test_unreceived_message_is_not_mislabeled_lost(self) -> None:
        report = frontier.build_report(frontier.build_fixture(omit_receiver_event=3))
        d1 = next(item for item in report["decision_assessments"] if item["decision_id"] == "D1")
        self.assertEqual(
            self.message(d1, "m1")["availability"],
            "not_recorded_as_admitted_at_snapshot",
        )
        self.assertEqual(
            self.message(d1, "m1")["decision_to_receiver_intake"],
            None,
        )

    def test_used_message_must_be_declared_available(self) -> None:
        altered = copy.deepcopy(self.bundle)
        decision = altered["receiver_events"][1]
        decision["used_message_ids"] = ["m1", "m2"]
        core = {key: value for key, value in decision.items() if key != "event_digest"}
        decision["event_digest"] = frontier.digest(core)
        following = altered["receiver_events"][2]
        following["previous_digest"] = decision["event_digest"]
        following_core = {key: value for key, value in following.items() if key != "event_digest"}
        following["event_digest"] = frontier.digest(following_core)
        last = altered["receiver_events"][3]
        last["previous_digest"] = following["event_digest"]
        last["frontier_head_digest"] = following["event_digest"]
        last_core = {key: value for key, value in last.items() if key != "event_digest"}
        last["event_digest"] = frontier.digest(last_core)
        with self.assertRaisesRegex(frontier.FrontierError, "does not declare available"):
            frontier.build_report(altered)

    def test_corrupt_event_bytes_are_rejected(self) -> None:
        altered = copy.deepcopy(self.bundle)
        altered["receiver_events"][0]["message_id"] = "m1"
        with self.assertRaisesRegex(frontier.FrontierError, "digest"):
            frontier.build_report(altered)

    def test_broken_contiguous_hash_link_is_rejected(self) -> None:
        altered = copy.deepcopy(self.bundle)
        altered["receiver_events"][1]["previous_digest"] = "0" * 64
        altered["receiver_events"][1]["frontier_head_digest"] = "0" * 64
        core = {key: value for key, value in altered["receiver_events"][1].items() if key != "event_digest"}
        altered["receiver_events"][1]["event_digest"] = frontier.digest(core)
        with self.assertRaisesRegex(frontier.FrontierError, "hash-chain mismatch"):
            frontier.build_report(altered)

    def test_intake_must_bind_exact_source_payload_and_stamp(self) -> None:
        altered = copy.deepcopy(self.bundle)
        altered["receiver_events"][0]["payload_digest"] = "0" * 64
        core = {key: value for key, value in altered["receiver_events"][0].items() if key != "event_digest"}
        altered["receiver_events"][0]["event_digest"] = frontier.digest(core)
        with self.assertRaisesRegex(frontier.FrontierError, "payload digest"):
            frontier.build_report(altered)

    def test_decision_must_not_claim_a_message_used_before_admission(self) -> None:
        altered = copy.deepcopy(self.bundle)
        decision = altered["receiver_events"][1]
        decision["used_message_ids"] = ["m1", "m2"]
        decision["available_message_ids"] = ["m1", "m2"]
        core = {key: value for key, value in decision.items() if key != "event_digest"}
        decision["event_digest"] = frontier.digest(core)
        following = altered["receiver_events"][2]
        following["previous_digest"] = decision["event_digest"]
        following_core = {key: value for key, value in following.items() if key != "event_digest"}
        following["event_digest"] = frontier.digest(following_core)
        last = altered["receiver_events"][3]
        last["previous_digest"] = following["event_digest"]
        last["frontier_head_digest"] = following["event_digest"]
        last_core = {key: value for key, value in last.items() if key != "event_digest"}
        last["event_digest"] = frontier.digest(last_core)
        with self.assertRaisesRegex(frontier.FrontierError, "available set"):
            frontier.build_report(altered)

    def test_report_reconstruction_rejects_tampered_assessment(self) -> None:
        altered = copy.deepcopy(self.report)
        altered["decision_assessments"][0]["messages"][0]["availability"] = "available_at_decision"
        altered["report_digest"] = frontier.digest({
            key: value for key, value in altered.items() if key != "report_digest"
        })
        with self.assertRaisesRegex(frontier.FrontierError, "independent reconstruction"):
            frontier.validate_report(altered)

    def test_clock_policy_does_not_invent_global_time(self) -> None:
        self.assertEqual(self.report["clock_policy"], {
            "wall_clock_used": False,
            "global_total_order": None,
            "combined_cross_host_elapsed_ns": None,
        })


if __name__ == "__main__":
    unittest.main()
