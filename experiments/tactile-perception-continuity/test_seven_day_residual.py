"""TPP-007 deterministic synthetic 7-day fixtures and adversarial evidence tests."""
from __future__ import annotations

import base64
from datetime import datetime,timedelta,timezone,date
from fractions import Fraction as Q
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from seven_day_residual import (SCHEMA,STATION,N_DAYS,MAX_POINTS,period,url,raw_body,
                                parse,evaluate,replay,run,MIN_OVERLAP)

FIRST=date(2026,11,13)
LAST=date(2026,11,19)
START=datetime(2026,11,13,tzinfo=timezone.utc)
QUALITY="p"

def bodies(offsets=None,n=120,drop_day=None):
    if offsets is None:
        offsets=[Q(45,100)]*N_DAYS
    if len(offsets)!=N_DAYS:
        raise ValueError("exact seven-day fixture required")
    all_docs=[]
    for product in ("water_level","predictions"):
        rows=[]
        for di in range(N_DAYS):
            for i in range(n):
                if drop_day==di and product=="water_level" and i==n-1:
                    continue
                t=START+timedelta(days=di,minutes=i*12)
                pred=Q(1)+Q(i%19,1000)
                obs=pred+offsets[di]
                value=obs if product=="water_level" else pred
                row={"t":t.strftime("%Y-%m-%d %H:%M"),
                     "v":f"{value.numerator/value.denominator:.3f}"}
                if product=="water_level":
                    row.update({"s":"0.005","f":"0,0,0,0","q":QUALITY})
                rows.append(row)
        payload=({"metadata":{"id":STATION,"name":"SYNTHETIC ONLY"},"data":rows}
                 if product=="water_level" else {"predictions":rows})
        raw=json.dumps(payload,separators=(",",":"),sort_keys=True).encode("utf8")
        all_docs.append({
            "status":"received","source":url(product,FIRST,LAST),
            "product":product,"start_utc_day":"20261113","end_utc_day":"20261119",
            "retrieved_utc":datetime.now(timezone.utc).isoformat(),
            "raw_bytes":len(raw),"raw_sha256":sha256(raw).hexdigest(),
            "raw_body_base64":base64.b64encode(raw).decode("ascii"),
            "scope":"public-provider-read-only-no-instrument-attestation"})
    return all_docs

def fixture(offsets=None,n=120,drop_day=None):
    docs=bodies(offsets,n,drop_day)
    return {"schema":SCHEMA,"acquisition":"synthetic-two-batched-fixtures",
            "actual_request_attempts":2,"documents":docs,
            "assessment":evaluate(docs)}

def rewrite_doc(doc,modify):
    obj=json.loads(base64.b64decode(doc["raw_body_base64"]))
    modify(obj)
    raw=json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
    doc["raw_body_base64"]=base64.b64encode(raw).decode()
    doc["raw_bytes"]=len(raw)
    doc["raw_sha256"]=sha256(raw).hexdigest()

class SevenDayContinuityTests(unittest.TestCase):
    def test_stable_residual_survives_six_unseen_days(self):
        report=fixture()
        result=report["assessment"]
        self.assertEqual(result["status"],"complete")
        self.assertEqual(result["frozen_day_one_correction_m"],"9/20")
        self.assertEqual(result["day_one_samples"],120)
        self.assertEqual(len(result["per_day"]),6)
        self.assertEqual(result["evaluated_heldout_samples"],720)
        self.assertEqual(result["full_week_heldout_baseline_mae_m"],"9/20")
        self.assertEqual(result["full_week_heldout_frozen_mae_m"],"0/1")
        self.assertEqual(result["one_day_lag_mae_m"],"0/1")
        self.assertEqual(replay(report)["status"],"complete")

    def test_frozen_offset_can_fail_as_context_changes(self):
        offsets=[Q(4,10),Q(4,10),Q(1,10),Q(-2,10),Q(0),Q(45,100),Q(6,10)]
        result=fixture(offsets)["assessment"]
        self.assertEqual(result["status"],"complete")
        self.assertEqual(result["frozen_day_one_correction_m"],"2/5")
        self.assertEqual(result["per_day"][0]["frozen_vs_baseline"],"improved")
        self.assertEqual(result["per_day"][2]["frozen_vs_baseline"],"worse")
        self.assertNotEqual(result["full_week_heldout_frozen_mae_m"],
                            result["full_week_heldout_baseline_mae_m"])

    def test_one_day_lag_uses_only_preceding_day(self):
        offsets=[Q(i,10) for i in range(1,8)]
        result=fixture(offsets)["assessment"]
        self.assertEqual(result["frozen_day_one_correction_m"],"1/10")
        self.assertEqual(result["per_day"][0]["applied_rolling_correction_m"],"1/10")
        self.assertEqual(result["per_day"][1]["applied_rolling_correction_m"],"1/5")
        self.assertEqual(result["per_day"][2]["applied_rolling_correction_m"],"3/10")
        self.assertEqual(result["per_day"][-1]["applied_rolling_correction_m"],"3/5")
        self.assertEqual(result["one_day_lag_scored_samples"],720)

    def test_future_day_changes_do_not_refit_initial_bias(self):
        a=fixture([Q(1,10)]*7)["assessment"]
        b=fixture([Q(1,10)]+[Q(-1,10)]*6)["assessment"]
        self.assertEqual(a["frozen_day_one_correction_m"],b["frozen_day_one_correction_m"])
        self.assertNotEqual(a["full_week_heldout_frozen_mae_m"],
                            b["full_week_heldout_frozen_mae_m"])

    def test_missing_day_forces_partial_undetermined_and_breaks_rolling_chain(self):
        result=fixture(drop_day=3)["assessment"]
        self.assertEqual(result["status"],"partial-undetermined")
        self.assertEqual(result["per_day"][2]["status"],"undetermined")
        self.assertEqual(result["per_day"][3]["rolling_vs_baseline"],"undetermined")
        self.assertIsNone(result["per_day"][3]["applied_rolling_correction_m"])
        self.assertLess(result["one_day_lag_scored_samples"],
                        result["evaluated_heldout_samples"])

    def test_missing_train_day_never_fabricates_model(self):
        report=fixture(n=119)
        self.assertEqual(report["assessment"]["status"],"undetermined")
        self.assertEqual(report["assessment"]["reason"],"insufficient-initial-day-evidence")

    def test_two_range_requests_not_fourteen_day_requests(self):
        docs=bodies()
        with patch("seven_day_residual.fetch",side_effect=docs) as remote:
            result=run("20261113","20261119")
        self.assertEqual(remote.call_count,2)
        self.assertEqual(result["actual_request_attempts"],2)
        self.assertEqual(result["assessment"]["status"],"complete")

    def test_strict_seven_complete_days_reference(self):
        with self.assertRaises(ValueError):
            period("20261113","20261118")
        with self.assertRaises(ValueError):
            period("20261119","20261125")
        with self.assertRaises(ValueError):
            period("20261301","20261307")
        with self.assertRaises(ValueError):
            url("wind",FIRST,LAST)

    def test_digest_tamper_and_disguised_unavailable(self):
        report=fixture()
        report["documents"][0]["raw_sha256"]="0"*64
        self.assertEqual(evaluate(report["documents"])["status"],"invalid-source-evidence")
        with self.assertRaisesRegex(ValueError,"assessment"):
            replay(report)
        report=fixture()
        report["documents"][0]["status"]="unavailable"
        self.assertEqual(evaluate(report["documents"])["status"],"invalid-source-evidence")

    def test_provider_quality_and_timestamp_duplicate_refused(self):
        report=fixture()
        rewrite_doc(report["documents"][0],lambda obj: obj["data"][0].update(q="?"))
        self.assertEqual(evaluate(report["documents"])["status"],"invalid-source-evidence")
        report=fixture()
        rewrite_doc(report["documents"][1],lambda obj: obj["predictions"][1].update(
            t=obj["predictions"][0]["t"]))
        self.assertEqual(evaluate(report["documents"])["status"],"invalid-source-evidence")

    def test_source_reference_and_cross_day_rows_refused(self):
        report=fixture()
        report["documents"][1]["source"]="https://example.invalid/"
        self.assertEqual(evaluate(report["documents"])["status"],"invalid-source-evidence")
        report=fixture()
        rewrite_doc(report["documents"][0],lambda obj: obj["data"][0].update(
            t="2026-11-20 00:00"))
        self.assertEqual(evaluate(report["documents"])["status"],"invalid-source-evidence")

    def test_no_prediction_source_is_undetermined(self):
        report=fixture()
        original=report["documents"][1]
        report["documents"][1]={k:original[k] for k in
                                 ("source","product","start_utc_day","end_utc_day")}
        report["documents"][1].update({"status":"unavailable","scope":"read-unavailable-no-physical-observation"})
        self.assertEqual(evaluate(report["documents"])["status"],"undetermined")

    def test_replay_rejects_modifying_result_even_with_intact_data(self):
        report=fixture()
        report["assessment"]["frozen_day_one_correction_m"]="99/1"
        with self.assertRaisesRegex(ValueError,"assessment"):
            replay(report)

    def test_invalid_request_count_not_attested(self):
        report=fixture()
        report["actual_request_attempts"]=15
        with self.assertRaisesRegex(ValueError,"request count"):
            replay(report)

if __name__=="__main__":
    unittest.main()
