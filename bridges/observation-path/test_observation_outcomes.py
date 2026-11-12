import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

from observation_outcomes import (
    build_observation_outcome,
    validate_observation_outcome,
)

SCHEMA_PATH = Path(__file__).with_name("observation-outcome.schema.json")
EVIDENCE_DIGEST = hashlib.sha256(b"observed-value").hexdigest()
HYPOTHESES = [
    {"hypothesis_id": "h0", "prior_probability": 0.90, "predicted_outcome": "a", "query_value": False},
    {"hypothesis_id": "h1", "prior_probability": 0.05, "predicted_outcome": "b", "query_value": True},
    {"hypothesis_id": "h2", "prior_probability": 0.03, "predicted_outcome": "b", "query_value": False},
    {"hypothesis_id": "h3", "prior_probability": 0.02, "predicted_outcome": "c", "query_value": True},
]


def build(outcome="b", hypotheses=None):
    return build_observation_outcome(
        attempt_id="attempt-1",
        observation_id="observation-1",
        evidence_ref="encounters/observation-1.json",
        evidence_digest=EVIDENCE_DIGEST,
        model_ref="models/symbol-classifier-v1.json",
        prior_hypotheses=HYPOTHESES if hypotheses is None else hypotheses,
        observed_outcome=outcome,
    )


class ObservationOutcomeTests(unittest.TestCase):
    def test_expected_information_and_realized_entropy_change_are_distinct(self):
        analysis = build("b")["analysis"]
        self.assertGreater(analysis["expected_information_gain_bits"], 0)
        self.assertGreater(analysis["realized_entropy_change_bits"], 0)
        self.assertGreater(analysis["posterior_entropy_bits"], analysis["prior_entropy_bits"])
        self.assertEqual(analysis["query_status"], "undetermined")

    def test_query_resolution_probability_is_prior_mass_of_resolving_buckets(self):
        analysis = build("a")["analysis"]
        self.assertAlmostEqual(analysis["expected_query_resolution_probability"], 0.92)
        self.assertEqual(analysis["query_status"], "resolved")
        self.assertIs(analysis["query_value"], False)
        self.assertEqual(analysis["posterior"], [{"hypothesis_id": "h0", "probability": 1.0}])

    def test_observed_bucket_posterior_and_probability_reconstruct(self):
        analysis = build("b")["analysis"]
        self.assertAlmostEqual(analysis["observed_outcome_probability"], 0.08)
        posterior = {item["hypothesis_id"]: item["probability"] for item in analysis["posterior"]}
        self.assertAlmostEqual(posterior["h1"], 0.625)
        self.assertAlmostEqual(posterior["h2"], 0.375)
        self.assertAlmostEqual(sum(posterior.values()), 1.0)

    def test_model_mismatch_has_no_fabricated_posterior_or_zero_cost_information(self):
        analysis = build("unexpected")["analysis"]
        self.assertEqual(analysis["model_status"], "model_mismatch")
        self.assertEqual(analysis["query_status"], "model_mismatch")
        self.assertEqual(analysis["posterior"], [])
        self.assertIsNone(analysis["observed_outcome_probability"])
        self.assertIsNone(analysis["posterior_entropy_bits"])
        self.assertIsNone(analysis["realized_entropy_change_bits"])
        self.assertGreater(analysis["expected_information_gain_bits"], 0)

    def test_query_can_be_omitted_without_inventing_resolution_probability(self):
        hypotheses = [
            {key: value for key, value in item.items() if key != "query_value"}
            for item in HYPOTHESES
        ]
        analysis = build("a", hypotheses)["analysis"]
        self.assertIsNone(analysis["expected_query_resolution_probability"])
        self.assertEqual(analysis["query_status"], "not_scoped")
        self.assertIsNone(analysis["query_value"])

    def test_model_digest_is_order_invariant_and_reconstructible(self):
        first = build("b")
        second = build("b", list(reversed(HYPOTHESES)))
        self.assertEqual(first["model_digest"], second["model_digest"])
        self.assertEqual(first["outcome_digest"], second["outcome_digest"])
        self.assertEqual(validate_observation_outcome(first), first)
        jsonschema.validate(first, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))

    def test_tampered_analysis_or_digest_is_rejected(self):
        report = build("b")
        changed = copy.deepcopy(report)
        changed["analysis"]["expected_information_gain_bits"] += 1
        with self.assertRaisesRegex(ValueError, "reconstruction"):
            validate_observation_outcome(changed)
        changed = copy.deepcopy(report)
        changed["outcome_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "reconstruction"):
            validate_observation_outcome(changed)

    def test_invalid_priors_are_rejected(self):
        bad = copy.deepcopy(HYPOTHESES)
        bad[0]["prior_probability"] = 0.5
        with self.assertRaisesRegex(ValueError, "sum to 1"):
            build("a", bad)
        bad = copy.deepcopy(HYPOTHESES)
        bad[0]["prior_probability"] = True
        with self.assertRaisesRegex(ValueError, "numeric"):
            build("a", bad)
        bad = copy.deepcopy(HYPOTHESES)
        bad[0]["prior_probability"] = float("nan")
        with self.assertRaisesRegex(ValueError, "in"):
            build("a", bad)

    def test_duplicate_hypothesis_ids_and_partial_query_predicates_are_rejected(self):
        bad = copy.deepcopy(HYPOTHESES)
        bad[1]["hypothesis_id"] = "h0"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build("a", bad)
        bad = copy.deepcopy(HYPOTHESES)
        bad[0]["query_value"] = None
        with self.assertRaisesRegex(ValueError, "every hypothesis"):
            build("a", bad)

    def test_non_json_and_non_finite_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite JSON"):
            build(float("nan"))
        with self.assertRaisesRegex(ValueError, "finite JSON"):
            bad = copy.deepcopy(HYPOTHESES)
            bad[0]["predicted_outcome"] = object()
            build("a", bad)

    def test_evidence_digest_is_checked_but_evidence_is_not_authenticated(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_observation_outcome(
                attempt_id="a", observation_id="o", evidence_ref="external://e",
                evidence_digest="not-a-digest", model_ref="m",
                prior_hypotheses=HYPOTHESES, observed_outcome="a",
            )
        report = build("a")
        self.assertIn("not fetched, authenticated, or validated", " ".join(report["interpretation_limits"]))

    def test_cli_writes_a_reconstructible_record(self):
        request = {
            "attempt_id": "attempt-cli",
            "observation_id": "observation-cli",
            "evidence_ref": "encounters/cli.json",
            "evidence_digest": EVIDENCE_DIGEST,
            "model_ref": "models/cli.json",
            "prior_hypotheses": HYPOTHESES,
            "observed_outcome": "a",
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "request.json"
            destination = Path(directory) / "outcome.json"
            source.write_text(json.dumps(request), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("observation_outcomes.py")),
                 "--input", str(source), "--output", str(destination)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            record = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(validate_observation_outcome(record), record)


if __name__ == "__main__":
    unittest.main()
