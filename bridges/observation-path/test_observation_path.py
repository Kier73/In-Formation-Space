import json
import unittest

from observation_path import ObservationIntent, ObservationPath


def intent():
    return ObservationIntent(
        attempt_id="attempt-01",
        candidate_name="sensor.mode",
        query="Did the mode become warm?",
        hypothesis_set_digest="sha256:prior-hypotheses",
        estimated_cost=1.25,
        plan_ref="plans/policy-01.json",
    )


class ObservationPathTests(unittest.TestCase):
    def test_happy_path_keeps_every_stage_distinct(self):
        path = ObservationPath(intent())
        path.append("dispatched", "host", evidence_ref="transport/send-01.json")
        path.append("admitted", "receiver", evidence_ref="receiver/admit-01.json")
        path.append(
            "returned",
            "sensor",
            evidence_ref="encounters/reading-01.json",
            details={
                "encounter_id": "sensor-reading-01",
                "payload_digest": "sha256:raw-payload",
                "canonicalization": "utf8-raw-v1",
            },
        )
        path.append(
            "interpreted",
            "interpreter",
            evidence_ref="interpretations/reading-01.json",
            details={"method": "mode-parser-v1"},
        )
        path.append(
            "query_determined",
            "verifier",
            evidence_ref="proofs/query-01.json",
            details={
                "query_result": True,
                "hypothesis_set_digest": "sha256:updated-hypotheses",
                "basis": "proofs/query-01.json",
            },
        )

        self.assertEqual(
            [event.stage for event in path.events],
            ["planned", "dispatched", "admitted", "returned", "interpreted", "query_determined"],
        )
        self.assertEqual(path.status, "query_determined")
        self.assertTrue(path.terminal)
        self.assertEqual(path.events[3].details["encounter_id"], "sensor-reading-01")

    def test_planning_does_not_mean_dispatch_or_observation(self):
        path = ObservationPath(intent())
        self.assertEqual(path.status, "planned")
        self.assertFalse(path.terminal)
        self.assertEqual(len(path.events), 1)
        with self.assertRaises(ValueError):
            path.append(
                "returned",
                "sensor",
                evidence_ref="encounters/reading.json",
                details={
                    "encounter_id": "reading",
                    "payload_digest": "sha256:x",
                    "canonicalization": "utf8-raw-v1",
                },
            )

    def test_receiver_admission_is_not_an_observation(self):
        path = ObservationPath(intent())
        path.append("dispatched", "host", evidence_ref="transport/send.json")
        path.append("admitted", "receiver", evidence_ref="receiver/admission.json")
        self.assertEqual(path.status, "admitted")
        self.assertFalse(path.terminal)
        with self.assertRaises(ValueError):
            path.append("interpreted", "interpreter", evidence_ref="interpretation.json", details={"method": "v1"})

    def test_rejection_is_not_a_negative_sensor_value(self):
        path = ObservationPath(intent())
        path.append("dispatched", "host", evidence_ref="transport/send.json")
        path.append("rejected", "receiver", details={"reason": "capacity limit"})
        self.assertEqual(path.status, "rejected")
        self.assertTrue(path.terminal)
        self.assertFalse(any(event.stage == "returned" for event in path.events))
        with self.assertRaises(ValueError):
            path.append("returned", "sensor", evidence_ref="reading.json", details={
                "encounter_id": "reading",
                "payload_digest": "sha256:x",
                "canonicalization": "utf8-raw-v1",
            })

    def test_return_without_admission_is_preserved_but_not_interpretable(self):
        path = ObservationPath(intent())
        path.append("dispatched", "host", evidence_ref="transport/send.json")
        path.append(
            "returned_unadmitted",
            "transport",
            evidence_ref="encounters/unadmitted.json",
            details={
                "encounter_id": "unadmitted-reading",
                "payload_digest": "sha256:raw",
                "canonicalization": "utf8-raw-v1",
            },
        )
        self.assertEqual(path.status, "returned_unadmitted")
        self.assertTrue(path.terminal)
        with self.assertRaises(ValueError):
            path.append("interpreted", "interpreter", evidence_ref="interpretation.json", details={"method": "v1"})

    def test_admitted_request_with_no_result_is_not_a_negative_observation(self):
        path = ObservationPath(intent())
        path.append("dispatched", "host", evidence_ref="transport/send.json")
        path.append("admitted", "receiver", evidence_ref="receiver/admission.json")
        path.append("no_result", "sensor", details={"reason": "read timeout"})
        self.assertEqual(path.status, "no_result")
        self.assertTrue(path.terminal)
        self.assertFalse(any(event.stage == "returned" for event in path.events))

    def test_clock_values_require_domains_and_are_not_aligned(self):
        path = ObservationPath(intent())
        with self.assertRaises(ValueError):
            path.append("dispatched", "host", clock_value="100")
        path.append(
            "dispatched",
            "host",
            clock_value="100",
            clock_domain="controller-C",
            evidence_ref="transport/send.json",
        )
        path.append(
            "admitted",
            "receiver",
            clock_value="8",
            clock_domain="receiver-S",
            evidence_ref="receiver/admission.json",
        )
        record = path.to_dict()
        self.assertEqual(record["events"][1]["clock_domain"], "controller-C")
        self.assertEqual(record["events"][2]["clock_domain"], "receiver-S")
        self.assertEqual(record["events"][1]["clock_value"], "100")
        self.assertEqual(record["events"][2]["clock_value"], "8")

    def test_event_details_are_snapshotted(self):
        path = ObservationPath(intent())
        path.append("dispatched", "host", evidence_ref="transport/send.json")
        path.append("admitted", "receiver", evidence_ref="receiver/admission.json")
        details = {
            "encounter_id": "reading",
            "payload_digest": "sha256:x",
            "canonicalization": "utf8-raw-v1",
        }
        path.append("returned", "sensor", evidence_ref="encounters/reading.json", details=details)
        details["payload_digest"] = "sha256:changed"
        self.assertEqual(path.events[-1].details["payload_digest"], "sha256:x")
        public_copy = path.events[-1].details
        public_copy["payload_digest"] = "sha256:mutated-copy"
        self.assertEqual(path.events[-1].details["payload_digest"], "sha256:x")

    def test_intent_and_terminal_claims_are_validated(self):
        with self.assertRaises(ValueError):
            ObservationIntent(" ", "sensor", "query", "digest", 1.0)
        with self.assertRaises(ValueError):
            ObservationIntent("id", "sensor", "query", "digest", float("inf"))
        path = ObservationPath(intent())
        path.append("dispatched", "host", evidence_ref="transport/send.json")
        path.append("admitted", "receiver", evidence_ref="receiver/admission.json")
        path.append(
            "returned",
            "sensor",
            evidence_ref="encounters/reading.json",
            details={"encounter_id": "reading", "payload_digest": "sha256:x", "canonicalization": "utf8-raw-v1"},
        )
        path.append("interpreted", "interpreter", evidence_ref="interpretation.json", details={"method": "v1"})
        with self.assertRaises(ValueError):
            path.append("query_determined", "verifier", evidence_ref="proof.json", details={
                "query_result": "true",
                "hypothesis_set_digest": "digest",
                "basis": "proof.json",
            })


if __name__ == "__main__":
    unittest.main()
