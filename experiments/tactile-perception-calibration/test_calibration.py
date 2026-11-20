"""TPP-004: exact feasible relation, negative controls and independent byte provenance."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction as Q
import json
import unittest

from calibration import (fit, infer, challenge, EPS, KNOWN_FOOT_TO_M, rational)
from noaa_bridge import decode, request_url, compare_expressions

STATION="9414290"
WHEN="2026-11-20T06:00:00+00:00"


def synthetic_provider(n=40, *, change_metric=None, quality_disagree=False):
    """Synthetic NOAA-shaped bytes, with explicit separate readings and flags."""
    readings=[]
    for unit in ("metric","english"):
        records=[]
        for i in range(n):
            # Cyclic variation avoids a monotonic-only calibration fixture.
            x=Decimal("2.0")+Decimal(i%11)/Decimal("5")+Decimal(i)/Decimal("1000")
            y=x*Decimal("0.3048")+Decimal("0.02")
            if unit=="metric":
                if change_metric and i in change_metric:
                    y+=Decimal(str(change_metric[i]))
                value=y.quantize(Decimal("0.001"),rounding=ROUND_HALF_UP)
            else:
                value=x.quantize(Decimal("0.001"),rounding=ROUND_HALF_UP)
            time=datetime(2026,11,17,tzinfo=timezone.utc)+timedelta(minutes=6*i)
            records.append({"t":time.strftime("%Y-%m-%d %H:%M"),"v":str(value),
                            "s":"0.010","f":"0,0,0,0",
                            "q":"v" if quality_disagree and unit=="english" else "p"})
        body=json.dumps({"metadata":{"id":STATION,"name":"Synthetic Fixture"},
                         "data":records},separators=(",",":")).encode("utf8")
        readings.append(decode(body,unit,STATION,request_url(unit),WHEN))
    return {"experiment":"TPP-003","observations":readings,
            "cross_unit_relation":compare_expressions(*readings)}


class CalibrationTests(unittest.TestCase):
    def test_exact_interval_contains_known_scale_without_using_it(self):
        # Exact constant deliberately appears in the *test oracle*, not fit().
        samples=[(Q(i),KNOWN_FOOT_TO_M*i+Q(1,20)) for i in (1,2,3,4,6,7,8,10)]
        model,status=fit(samples)
        self.assertEqual(status,"fit")
        self.assertLessEqual(model.lower,KNOWN_FOOT_TO_M)
        self.assertGreaterEqual(model.upper,KNOWN_FOOT_TO_M)
        self.assertGreater(model.upper-model.lower,Q(0))
        self.assertTrue(all(abs(y-model.predict(x))<=EPS for x,y in samples))

    def test_fit_does_not_know_exact_scale_or_zero_offset(self):
        samples=[(Q(i),Q(2,7)*i+Q(3,5)) for i in (0,1,2,3,4,7)]
        model,status=fit(samples,epsilon=Q(1,10000))
        self.assertEqual(status,"fit")
        self.assertTrue(model.lower<=Q(2,7)<=model.upper)
        self.assertEqual(model.intercept,Q(3,5))
        self.assertFalse(model.lower<=KNOWN_FOOT_TO_M<=model.upper)

    def test_exact_pairwise_refusal_to_fit_non_affine_training(self):
        model,status=fit([(Q(i),Q(i*i)) for i in range(5)])
        self.assertIsNone(model)
        self.assertEqual(status,"contradictory-training-observations")

    def test_unidentifiable_scale_remains_unknown(self):
        model,status=fit([(Q(1),Q(7))]*5)
        self.assertIsNone(model)
        self.assertEqual(status,"no-observed-input-variation")
        model,status=fit([(Q(i,10000),Q(i,10000)) for i in range(5)])
        self.assertEqual(status,"insufficient-input-variation")

    def test_too_few_samples_are_not_calibration(self):
        model,status=fit([(Q(i),Q(i)) for i in range(3)])
        self.assertIsNone(model)
        self.assertEqual(status,"insufficient-training-observations")

    def test_exact_holdout_detects_non_linear_switch(self):
        train=[(Q(i),Q(2)*i+Q(1)) for i in range(8)]
        model,status=fit(train)
        self.assertEqual(status,"fit")
        tests=[("t0",Q(10),Q(21)),("t1",Q(11),Q(26))]
        result=challenge(model,tests)
        self.assertEqual(result["status"],"falsified")
        self.assertEqual(result["violations"],1)
        self.assertEqual(result["first_counterexample_utc"],"t1")

    def test_archived_provider_bytes_replayed_before_learning(self):
        report=synthetic_provider()
        fit_report=infer(report,stride=5)
        self.assertEqual(fit_report["status"],"heldout-consistent")
        self.assertEqual(fit_report["paired_timestamps"],40)
        self.assertEqual(fit_report["training_pairs"],8)
        self.assertEqual(fit_report["heldout_pairs"],32)
        self.assertTrue(fit_report["model"]["reference_scale_inside_interval_posthoc"])

    def test_previous_conversion_claim_not_consulted_during_fit(self):
        report=synthetic_provider()
        report["cross_unit_relation"]={"status":"contradicted","matches":0}
        # A previously calculated comparison must not pre-authorize or block
        # finding a relation from independently replayed raw readings.
        self.assertEqual(infer(report,stride=5)["status"],"heldout-consistent")

    def test_rehashed_interpretation_cannot_override_source_bytes(self):
        report=synthetic_provider()
        report["observations"][0]["observations"][0]["value"]="7.0"
        self.assertEqual(infer(report,stride=5)["status"],"invalid-source-evidence")

    def test_mismatch_in_provider_quality_is_not_erased(self):
        report=synthetic_provider(quality_disagree=True)
        self.assertEqual(infer(report,stride=5)["reason"],"provider-quality-mismatch")

    def test_provider_expression_revision_can_falsify_after_training(self):
        report=synthetic_provider(change_metric={37:"0.040"})
        outcome=infer(report,stride=5)
        self.assertEqual(outcome["status"],"falsified")
        self.assertEqual(outcome["heldout"]["violations"],1)
        self.assertEqual(outcome["heldout"]["first_counterexample_utc"],"2026-11-17T03:42:00+00:00")

    def test_malformed_evidence_and_unavailable_remain_nonobservations(self):
        report=synthetic_provider()
        report["observations"][0]={"status":"unavailable","observations":[]}
        self.assertEqual(infer(report,stride=5)["status"],"undetermined")
        contradictory=synthetic_provider()
        contradictory["observations"][0]["status"]="unavailable"
        # Retained observations cannot be re-labelled as non-observations.
        self.assertEqual(infer(contradictory,stride=5)["status"],"invalid-source-evidence")
        report=synthetic_provider()
        report["observations"][1]["raw_sha256"]="0"*64
        self.assertEqual(infer(report,stride=5)["status"],"invalid-source-evidence")

    def test_requires_declared_nonzero_tolerance_and_sampling(self):
        with self.assertRaises(ValueError):
            fit([(Q(i),Q(i)) for i in range(4)],epsilon=Q(0))
        with self.assertRaises(ValueError):
            infer(synthetic_provider(),stride=1)


if __name__=="__main__":
    unittest.main()
