"""TPP-006: blind train/test residual comparison and source evidence adversarial tests.

All fake NOAA-like payloads are synthetic and are NEVER described as a
measurement from a physical source.
"""
from __future__ import annotations

import base64
from datetime import datetime,timedelta,timezone,date
from fractions import Fraction as Q
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from residual_observer import (SCHEMA, url, read, paired, median, score, evaluate,
                               replay, utc_days, experiment, STATION, MIN_OVERLAP)

def source(product,day,offset,*,n=150,step=6,quality="p"):
    """Create an archived but clearly synthetic provider response."""
    begin=datetime.strptime(day,"%Y%m%d").replace(tzinfo=timezone.utc)
    rows=[]
    for k in range(n):
        clock=begin+timedelta(minutes=k*step)
        pred=Q(1)+Q(k%17,30)
        value=pred+(offset if product=="water_level" else Q(0))
        record={"t":clock.strftime("%Y-%m-%d %H:%M"),
                "v":f"{float(value):.3f}"}
        if product=="water_level":
            record.update({"s":"0.004","f":"0,0,0,0","q":quality})
        rows.append(record)
    obj=({"metadata":{"id":STATION,"name":"Synthetic"},"data":rows}
         if product=="water_level" else
         {"predictions":rows})
    raw=json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
    return {"status":"received","source":url(product,datetime.strptime(day,"%Y%m%d").date()),
            "product":product,"utc_day":day,
            "retrieved_utc":datetime.now(timezone.utc).isoformat(),
            "raw_bytes":len(raw),"raw_sha256":sha256(raw).hexdigest(),
            "raw_body_base64":base64.b64encode(raw).decode(),
            "scope":"one-provider-read-only-physical-data"}

def encounter(train=Q(1,10),holdout=Q(11,100)):
    docs=[source("water_level","20261117",train),
          source("predictions","20261117",Q(0)),
          source("water_level","20261118",holdout),
          source("predictions","20261118",Q(0))]
    return {"schema":SCHEMA,"mode":"offline-synthetic-model",
            "documents":docs,"request_attempts":4,
            "assessment":evaluate(docs)}

class PredictionObservationTests(unittest.TestCase):
    def test_earlier_day_bias_can_improve_later_day(self):
        d=encounter()
        a=d["assessment"]
        self.assertEqual(a["status"],"heldout-improved")
        self.assertEqual(a["frozen_median_residual_correction_m"],"1/10")
        self.assertEqual(a["training"]["samples"],150)
        self.assertEqual(a["heldout"]["samples"],150)
        self.assertEqual(a["heldout"]["provider_quality_counts"],{"p":150})
        self.assertLess(Q(a["heldout"]["corrected_mae_m"]),
                        Q(a["heldout"]["baseline_mae_m"]))
        self.assertEqual(replay(d)["status"],"heldout-improved")

    def test_correction_can_worsen_heldout(self):
        a=encounter(holdout=Q(-1,5))["assessment"]
        self.assertEqual(a["status"],"heldout-worse")
        self.assertGreater(Q(a["heldout"]["corrected_mae_m"]),
                           Q(a["heldout"]["baseline_mae_m"]))

    def test_heldout_has_no_influence_on_fitted_offset(self):
        first=encounter(holdout=Q(1,20))["assessment"]
        other=encounter(holdout=Q(-1,5))["assessment"]
        self.assertEqual(first["frozen_median_residual_correction_m"],
                         other["frozen_median_residual_correction_m"])
        self.assertNotEqual(first["delta_heldout_mae_m"],
                            other["delta_heldout_mae_m"])

    def test_exact_median_and_absolute_error_contract(self):
        self.assertEqual(median([Q(2),Q(1),Q(3)]),Q(2))
        self.assertEqual(median([Q(2),Q(3),Q(7),Q(9)]),Q(5))
        with self.assertRaises(ValueError):
            median([])
        pairs=[("t0",Q(2),Q(1),"p"),("t1",Q(3),Q(1),"v")]
        a=score(pairs,Q(1))
        self.assertEqual(a["baseline_mae_m"],"3/2")
        self.assertEqual(a["corrected_mae_m"],"1/2")
        self.assertEqual(a["provider_quality_counts"],{"p":1,"v":1})

    def test_request_and_day_contract(self):
        from urllib.parse import urlsplit,parse_qs
        day=date(2026,11,17)
        u=url("predictions",day)
        self.assertEqual(urlsplit(u).hostname,"api.tidesandcurrents.noaa.gov")
        q=parse_qs(urlsplit(u).query)
        self.assertEqual(q["interval"],["6"])
        self.assertEqual(q["time_zone"],["gmt"])
        self.assertEqual(q["datum"],["MLLW"])
        self.assertEqual(q["units"],["metric"])
        with self.assertRaises(ValueError):
            url("currents",day)
        with self.assertRaises(ValueError):
            utc_days("20261120","20261119")
        with self.assertRaises(ValueError):
            utc_days("20263118","20263119")

    def test_distinct_day_order_and_context_enforced(self):
        d=encounter()
        d["documents"][2]["utc_day"]="20261117"
        self.assertEqual(evaluate(d["documents"])["status"],"invalid-encounter")
        d=encounter()
        d["documents"][1]["product"]="water_level"
        self.assertEqual(evaluate(d["documents"])["status"],"invalid-encounter")

    def test_no_sample_overlap_not_a_prediction(self):
        d=encounter()
        bad=source("predictions","20261118",Q(0),n=150,step=6)
        obj=json.loads(base64.b64decode(bad["raw_body_base64"]))
        for row in obj["predictions"]:
            t=datetime.strptime(row["t"],"%Y-%m-%d %H:%M")+timedelta(minutes=1)
            row["t"]=t.strftime("%Y-%m-%d %H:%M")
        raw=json.dumps(obj).encode()
        bad["raw_body_base64"]=base64.b64encode(raw).decode()
        bad["raw_sha256"]=sha256(raw).hexdigest()
        bad["raw_bytes"]=len(raw)
        d["documents"][3]=bad
        result=evaluate(d["documents"])
        self.assertEqual(result["status"],"undetermined")
        self.assertEqual(result["reason"],"insufficient-overlap")

    def test_absent_model_is_not_zero(self):
        d=encounter()
        doc=d["documents"][1]
        d["documents"][1]={k:doc[k] for k in ("source","product","utc_day")}
        d["documents"][1]["status"]="unavailable"
        self.assertEqual(evaluate(d["documents"])["status"],"undetermined")

    def test_observed_bytes_checksum_mismatch_refused(self):
        d=encounter()
        d["documents"][2]["raw_sha256"]="f"*64
        self.assertEqual(evaluate(d["documents"])["status"],"invalid-evidence")
        with self.assertRaisesRegex(ValueError,"outcome"):
            replay(d)

    def test_station_datum_and_prediction_timestamp_refused(self):
        d=encounter()
        d["documents"][3]["source"]="https://example.invalid"
        self.assertEqual(evaluate(d["documents"])["status"],"invalid-evidence")
        d=encounter()
        doc=d["documents"][1]
        payload=json.loads(base64.b64decode(doc["raw_body_base64"]))
        payload["predictions"][1]["t"]=payload["predictions"][0]["t"]
        raw=json.dumps(payload).encode()
        doc["raw_body_base64"]=base64.b64encode(raw).decode()
        doc["raw_sha256"]=sha256(raw).hexdigest()
        doc["raw_bytes"]=len(raw)
        self.assertEqual(evaluate(d["documents"])["status"],"invalid-evidence")

    def test_missing_quality_and_stale_hypothesis_are_refused(self):
        d=encounter()
        doc=d["documents"][0]
        payload=json.loads(base64.b64decode(doc["raw_body_base64"]))
        payload["data"][0].pop("q")
        raw=json.dumps(payload).encode()
        doc["raw_body_base64"]=base64.b64encode(raw).decode()
        doc["raw_sha256"]=sha256(raw).hexdigest()
        doc["raw_bytes"]=len(raw)
        self.assertEqual(evaluate(d["documents"])["status"],"invalid-evidence")
        d=encounter()
        d["assessment"]["frozen_median_residual_correction_m"]="100/1"
        with self.assertRaisesRegex(ValueError,"outcome"):
            replay(d)

    def test_too_few_samples_do_not_support_stable_correction(self):
        docs=[source("water_level","20261117",Q(1,10),n=10),
              source("predictions","20261117",Q(0),n=10),
              source("water_level","20261118",Q(1,10)),
              source("predictions","20261118",Q(0))]
        result=evaluate(docs)
        self.assertEqual(result["status"],"undetermined")
        self.assertEqual(result["training_overlap"],10)
        self.assertEqual(result["heldout_overlap"],150)

    def test_live_request_plan_requires_no_target_leak(self):
        d=encounter()
        with patch("residual_observer.collect",side_effect=d["documents"]) as read:
            encounter_result=experiment("20261117","20261118")
        self.assertEqual(read.call_count,4)
        self.assertEqual(encounter_result["request_attempts"],4)
        self.assertEqual(encounter_result["assessment"]["status"],"heldout-improved")

if __name__=="__main__":
    unittest.main()
