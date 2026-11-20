"""TPP-005: exact evidence and acquisition-order tests; no network needed.

Retrospective NOAA-shaped payloads are synthesized and re-encoded into
separate target-window response bodies, not claimed to be real HTTP requests.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone, timedelta
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"tactile-perception-calibration"))
sys.path.insert(0,str(HERE.parent/"tactile-perception-observations"))
from test_calibration import synthetic_provider
from noaa_bridge import decode, STATION
from selective_observer import (SCHEMA, EPS, N_TRAIN, N_CHALLENGE,
    canonical, policy, evaluate, replay, target_uri, fixed_day,
    live, _check_english, _target, day_uri, uri, rational)

WHEN="2026-11-20T06:00:00+00:00"

def fixture(n=80, curved=False):
    full=synthetic_provider(n=n)
    english=full["observations"][1]
    metric=full["observations"][0]
    plan=policy(english)
    assert plan["status"]=="planned"
    source=json.loads(base64.b64decode(metric["raw_body_base64"]).decode())
    lookup={}
    for row in source["data"]:
        timestamp=datetime.strptime(row["t"],"%Y-%m-%d %H:%M").replace(
            tzinfo=timezone.utc).isoformat()
        lookup[timestamp]=row
    out=[]
    for purpose in ("training","challenge"):
        for t in plan[purpose]:
            row=dict(lookup[t])
            if curved and purpose=="challenge" and t==plan["challenge"][0]:
                row["v"]=str(F(row["v"])+F(1,5))
            payload=json.dumps({"metadata":source["metadata"],"data":[row]},
                               sort_keys=True,separators=(",",":")).encode()
            doc=decode(payload,"metric",STATION,target_uri(t),WHEN)
            out.append({"timestamp_utc":t,"purpose":purpose,"source":doc})
    encounter={"schema":SCHEMA,"encounter":"masked-retrospective-fixture",
               "fixed_utc_day":"20261117","input_source":english,
               "plan":plan,"returns":out}
    encounter["result"]=evaluate(english,plan,out)
    return encounter

class SelectiveAcquisitionTests(unittest.TestCase):
    def test_input_only_selection_and_four_plus_four_budget(self):
        result=fixture()
        plan=result["plan"]
        self.assertEqual(len(plan["training"]),N_TRAIN)
        self.assertEqual(len(plan["challenge"]),N_CHALLENGE)
        self.assertFalse(set(plan["training"]) & set(plan["challenge"]))
        self.assertEqual(plan["scope"],"only-input-expression-observed-before-selection")
        self.assertEqual(plan["status"],"planned")

    def test_extremes_minimize_pairwise_worst_case_slope_width(self):
        report=fixture()
        plan=report["plan"]
        self.assertLessEqual(F(plan["maximal_two_point_slope_width_upper_bound"]),
                             F(plan["chronological_baseline_two_point_upper_bound"]))
        english,_=_check_english(report["input_source"])
        times=dict((t,x) for t,x,q in english)
        sampled=[times[t] for t in plan["training"]]
        self.assertIn(min(times.values()),sampled)
        self.assertIn(max(times.values()),sampled)

    def test_training_selection_independent_of_target_values(self):
        a=fixture()
        b=fixture(curved=True)
        self.assertEqual(a["plan"],b["plan"])
        self.assertEqual(a["input_source"]["raw_sha256"],b["input_source"]["raw_sha256"])

    def test_discover_feasible_affine_relation_and_replay(self):
        report=fixture()
        self.assertEqual(report["result"]["status"],"heldout-consistent")
        self.assertEqual(report["result"]["training_requests"],4)
        self.assertEqual(report["result"]["challenge_requests"],4)
        self.assertEqual(report["result"]["heldout"]["tested"],4)
        self.assertEqual(report["result"]["heldout"]["violations"],0)
        self.assertEqual(replay(report)["status"],"heldout-consistent")

    def test_discover_counterexample_from_unseen_target(self):
        report=fixture(curved=True)
        self.assertEqual(report["result"]["status"],"falsified")
        self.assertEqual(report["result"]["heldout"]["violations"],1)
        self.assertEqual(report["result"]["heldout"]["first_counterexample_utc"],
                         report["plan"]["challenge"][0])
        self.assertEqual(replay(report)["status"],"falsified")

    def test_refuse_rehashed_summary_with_original_bytes(self):
        report=fixture()
        report["returns"][0]["source"]["observations"][0]["value"]="99.999"
        self.assertEqual(evaluate(report["input_source"],report["plan"],
                                  report["returns"])["status"],"invalid-evidence")
        with self.assertRaises(ValueError):
            replay(report)

    def test_cannot_choose_target_without_original_input_evidence(self):
        report=fixture()
        english=report["input_source"]
        english["raw_sha256"]="0"*64
        self.assertEqual(policy(english)["status"],"undetermined")
        self.assertEqual(policy(english)["reason"],"invalid-source-evidence")
        with self.assertRaises(ValueError):
            replay(report)

    def test_wrong_requested_timestamp_does_not_become_a_measurement(self):
        report=fixture()
        wrong=dict(report["returns"][0])
        wrong["timestamp_utc"]=report["plan"]["challenge"][0]
        report["returns"][0]=wrong
        self.assertEqual(evaluate(report["input_source"],report["plan"],
                                  report["returns"])["status"],"invalid-return")

    def test_wrong_request_url_disallows_target(self):
        report=fixture()
        report["returns"][0]["source"]["source"]="https://example.net/"
        self.assertEqual(evaluate(report["input_source"],report["plan"],
                                  report["returns"])["status"],"invalid-evidence")

    def test_missing_requested_target_is_unknown_not_zero(self):
        report=fixture()
        report["returns"][0]["source"]={"status":"unavailable","observations":[]}
        self.assertEqual(evaluate(report["input_source"],report["plan"],
                                  report["returns"])["status"],"undetermined")

    def test_provider_quality_change_not_masked(self):
        report=fixture()
        selected=report["returns"][0]
        doc=selected["source"]
        obj=json.loads(base64.b64decode(doc["raw_body_base64"]))
        obj["data"][0]["q"]="v"
        doc=decode(json.dumps(obj).encode(),"metric",STATION,
                   target_uri(selected["timestamp_utc"]),WHEN)
        report["returns"][0]["source"]=doc
        outcome=evaluate(report["input_source"],report["plan"],report["returns"])
        self.assertEqual(outcome["status"],"undetermined")
        self.assertEqual(outcome["reason"],"provider-quality-mismatch")

    def test_report_claim_cannot_override_independent_reconstruction(self):
        report=fixture()
        report["result"]["heldout"]["violations"]=99
        with self.assertRaisesRegex(ValueError,"claimed outcome"):
            replay(report)

    def test_bad_selection_digest_is_refused(self):
        report=fixture()
        report["plan"]["training"]=list(reversed(report["plan"]["training"]))
        self.assertEqual(evaluate(report["input_source"],report["plan"],
                                  report["returns"])["status"],"invalid-plan")

    def test_source_only_outcome_must_not_ask_for_targets(self):
        with patch("selective_observer.fetch_document") as fetch:
            fetch.return_value={"status":"unavailable","observations":[]}
            report=live()
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(report["result"]["status"],"undetermined")
        self.assertEqual(report["returns"],[])

    def test_only_completed_utc_days_and_bounded_endpoints(self):
        with self.assertRaises(ValueError):
            fixed_day((datetime.now(timezone.utc)+timedelta(days=2)).strftime("%Y%m%d"))
        with self.assertRaises(ValueError):
            fixed_day("20262135")
        t=datetime(2026,11,19,23,54,tzinfo=timezone.utc).isoformat()
        url=target_uri(t)
        self.assertIn("begin_date=20261119+23%3A54",url)
        self.assertIn("end_date=20261120+00%3A00",url)
        with self.assertRaises(ValueError):
            uri("metric",datetime.now(),datetime.now()+timedelta(minutes=6))

if __name__=="__main__":
    unittest.main()
