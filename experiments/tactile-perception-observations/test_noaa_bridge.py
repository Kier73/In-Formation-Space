"""TPP-003 offline conformance tests for provider observation and unit bridging."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

from noaa_bridge import decode, compare_expressions, request_url, live, SCHEMA

WHEN = "2026-11-19T21:00:00+00:00"
def packet(units, rows=None, station="9414290"):
    if rows is None:
        rows = [
            {"t":"2026-11-19 20:00", "v":"1.524" if units=="metric" else "5.000",
             "s":"0.011", "f":"1,0,0,0", "q":"p"},
            {"t":"2026-11-19 20:06", "v":"1.600" if units=="metric" else "5.249",
             "s":"0.005", "f":"0,0,0,0", "q":"v"},
            {"t":"2026-11-19 20:12", "v":"" if units=="metric" else "5.252",
             "s":"", "f":"0,0,0,0", "q":"p"},
        ]
    return json.dumps({"metadata":{"id":station,"name":"San Francisco"},
                       "data":rows},separators=(",",":")).encode("utf-8")

def read(units, raw=None):
    return decode(raw if raw is not None else packet(units), units, "9414290",
                  request_url(units), WHEN)

class ObservationBridgeTests(unittest.TestCase):
    def test_bounded_official_origin_and_unit_contract(self):
        u=request_url("metric")
        self.assertEqual(urlsplit(u).hostname,"api.tidesandcurrents.noaa.gov")
        params=parse_qs(urlsplit(u).query)
        self.assertEqual(params["product"],["water_level"])
        self.assertEqual(params["datum"],["MLLW"])
        self.assertEqual(params["time_zone"],["gmt"])
        for unit in ("F", "meters", "m"):
            with self.assertRaises(ValueError):
                request_url(unit)
        with self.assertRaises(ValueError):
            request_url("metric",station="9414290&evil=1")

    def test_parsed_quality_timestamp_sigma_and_datum(self):
        raw=packet("metric")
        doc=read("metric",raw)
        self.assertEqual(doc["schema"],SCHEMA)
        self.assertEqual(doc["status"],"observed")
        self.assertEqual(doc["raw_sha256"],sha256(raw).hexdigest())
        self.assertEqual(doc["units"],"m")
        self.assertEqual(doc["datum"],"MLLW")
        self.assertEqual(doc["observations"][0]["timestamp_utc"],"2026-11-19T20:00:00+00:00")
        self.assertEqual(doc["observations"][0]["status"],"preliminary")
        self.assertEqual(doc["observations"][1]["status"],"provider-verified")
        self.assertEqual(doc["observations"][0]["sigma"],"0.011")
        self.assertEqual(doc["observations"][0]["flags_raw"],"1,0,0,0")

    def test_missing_value_is_not_zero(self):
        doc=read("metric")
        self.assertEqual(doc["observations"][2]["status"],"missing")
        self.assertIsNone(doc["observations"][2]["value"])
        self.assertIsNone(doc["observations"][2]["sigma"])

    def test_two_unit_expressions_match_at_same_timestamps(self):
        result=compare_expressions(read("metric"),read("english"))
        self.assertEqual(result["status"],"unit-expression-consistent")
        self.assertEqual(result["matched_timestamps"],2)
        self.assertEqual(result["matches"],2)
        self.assertTrue(Decimal(result["max_absolute_deviation_m"]) <= Decimal("0.001"))

    def test_quality_disagreement_not_erased(self):
        english=json.loads(packet("english"))
        english["data"][1]["q"]="p"
        result=compare_expressions(read("metric"),read("english",json.dumps(english).encode()))
        self.assertEqual(result["status"],"unit-expression-consistent")
        self.assertEqual(result["quality_disagreement_timestamps"],["2026-11-19T20:06:00+00:00"])

    def test_large_discrepancy_is_not_rounded_away(self):
        english=json.loads(packet("english"))
        english["data"][1]["v"]="6.249"
        result=compare_expressions(read("metric"),read("english",json.dumps(english).encode()))
        self.assertEqual(result["status"],"contradicted")
        self.assertEqual(result["matches"],1)
        self.assertEqual(result["first_disagreement_utc"],"2026-11-19T20:06:00+00:00")

    def test_no_common_time_is_undetermined(self):
        english=json.loads(packet("english"))
        for row in english["data"]:
            row["t"]="2026-11-18 "+row["t"].split(" ")[1]
        result=compare_expressions(read("metric"),read("english",json.dumps(english).encode()))
        self.assertEqual(result["status"],"undetermined")
        self.assertEqual(result["matches"],0)

    def test_context_mismatch_is_not_equivalence(self):
        english=read("english")
        english["datum"]="MSL"
        self.assertEqual(compare_expressions(read("metric"),english)["status"],"incompatible-context")
        english=read("english")
        english["units"]="m"
        self.assertEqual(compare_expressions(read("metric"),english)["status"],"incompatible-context")

    def test_error_and_empty_results_are_unavailable(self):
        error=json.dumps({"error":{"message":"temporarily unavailable"}}).encode()
        self.assertEqual(read("metric",error)["status"],"unavailable")
        empty=json.dumps({"metadata":{"id":"9414290"},"data":[]}).encode()
        self.assertEqual(read("metric",empty)["status"],"unavailable")
        self.assertEqual(compare_expressions(read("metric",empty),read("english"))["status"],"undetermined")

    def test_corrupt_source_bytes_and_wrong_station_are_invalid(self):
        self.assertEqual(read("metric",b"not-json")["status"],"invalid")
        self.assertEqual(read("metric",packet("metric",station="8518750"))["reason"],"station-mismatch")

    def test_nonfinite_or_unknown_quality_is_invalid(self):
        for key,value in (("v","NaN"),("v","inf"),("s","-0.01"),("q","?"),("t","not-a-time")):
            obj=json.loads(packet("metric"))
            obj["data"][0][key]=value
            with self.subTest(field=key):
                self.assertEqual(read("metric",json.dumps(obj).encode())["status"],"invalid")

    def test_duplicate_timestamps_not_silently_deduplicated(self):
        obj=json.loads(packet("metric"))
        obj["data"][1]["t"]=obj["data"][0]["t"]
        self.assertEqual(read("metric",json.dumps(obj).encode())["status"],"invalid")

    def test_bytes_not_provider_authenticity(self):
        first=packet("metric")
        second=first.replace(b"1.524",b"1.525")
        self.assertNotEqual(read("metric",first)["raw_sha256"],read("metric",second)["raw_sha256"])
        self.assertEqual(read("metric",second)["status"],"observed")
        # Rewritten JSON can have a valid digest; it is NOT a trusted sensor signature.

    def test_live_failure_is_explicit_without_network(self):
        with patch("noaa_bridge.fetch",side_effect=TimeoutError):
            report=live(date="latest")
        self.assertEqual(report["cross_unit_relation"]["status"],"undetermined")
        self.assertTrue(all(d["status"]=="unavailable" for d in report["observations"]))
        self.assertTrue(all(len(d["observations"])==0 for d in report["observations"]))

if __name__ == "__main__":
    unittest.main()
