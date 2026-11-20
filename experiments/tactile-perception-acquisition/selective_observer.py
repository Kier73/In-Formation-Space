"""TPP-005: select a small number of physical-data expressions before reading them.

The observer first obtains the 'English' NOAA series, selects target times using
only those input values, then makes separately addressed metric HTTPS requests.
No physical intervention or independent sensor is claimed. A GitHub-runner read
is a communication encounter, not proof of NOAA instrument calibration.

Uses the existing TPP-003 raw-byte replay and TPP-004 exact affine estimator.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tactile-perception-observations"))
sys.path.insert(0, str(HERE.parent / "tactile-perception-calibration"))
from noaa_bridge import (HOST, PATH as NOAA_PATH, STATION, DATUM,
                         MAX_RESPONSE_BYTES, decode)
from independent_replay import replay_source
from calibration import fit, challenge, rational, EPS

SCHEMA = "in-formation-space.tpp005.selective-acquisition.v1"
N_TRAIN = 4
N_CHALLENGE = 4

def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")

def digest(obj):
    return sha256(canonical(obj)).hexdigest()

def fixed_day(utc_day=None):
    """Only completed UTC days; no current/future observation inferred."""
    previous = datetime.now(timezone.utc).date() - timedelta(days=1)
    if utc_day is None:
        return previous
    if not isinstance(utc_day, str) or not re.fullmatch(r"\d{8}", utc_day):
        raise ValueError("UTC day must be YYYYMMDD")
    try:
        chosen = datetime.strptime(utc_day, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("invalid calendar date") from exc
    if chosen > previous:
        raise ValueError("only fully elapsed UTC days")
    return chosen

def uri(unit, begin, end):
    """Bound every request to one NOAA station and declared unit/datum."""
    if unit not in ("metric", "english"):
        raise ValueError("unknown unit expression")
    if not isinstance(begin, datetime) or not isinstance(end, datetime):
        raise ValueError("UTC datetime required")
    if begin.tzinfo != timezone.utc or end.tzinfo != timezone.utc or end <= begin:
        raise ValueError("invalid UTC interval")
    if end - begin > timedelta(days=1):
        raise ValueError("interval too long")
    args = urlencode({
        "application": "InFormationSpace_TPP005",
        "begin_date": begin.strftime("%Y%m%d %H:%M"),
        "end_date": end.strftime("%Y%m%d %H:%M"),
        "datum": DATUM,
        "format": "json",
        "product": "water_level",
        "station": STATION,
        "time_zone": "gmt",
        "units": unit,
    })
    return f"https://{HOST}{NOAA_PATH}?{args}"

def day_uri(day):
    first = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return uri("english", first, first + timedelta(hours=23, minutes=59))

def target_uri(timestamp):
    start = datetime.fromisoformat(timestamp)
    if start.tzinfo != timezone.utc or start.second or start.microsecond:
        raise ValueError("timestamp must be whole UTC minute")
    return uri("metric", start, start + timedelta(minutes=6))

def fetch_document(request_url, unit):
    """One bounded read-only HTTPS attempt. Failures are missing observations."""
    try:
        response = Request(request_url, headers={
            "Accept": "application/json",
            "User-Agent": "InFormationSpace-TPP005/1.0",
        })
        with urlopen(response, timeout=15) as handle:
            from urllib.parse import urlsplit
            actual = urlsplit(handle.geturl())
            if actual.scheme != "https" or actual.hostname != HOST or actual.path != NOAA_PATH:
                raise ValueError("redirect outside approved data endpoint")
            if handle.status != 200:
                raise ValueError("non-200 response")
            original = handle.read(MAX_RESPONSE_BYTES + 1)
            if len(original) > MAX_RESPONSE_BYTES:
                raise ValueError("oversized provider response")
        return decode(original, unit, STATION, request_url,
                      datetime.now(timezone.utc).isoformat())
    except (OSError, TimeoutError, ValueError) as exc:
        return {"status": "unavailable", "reason": type(exc).__name__,
                "source": request_url, "observations": [],
                "scope": "failed-read-no-observation"}

def _check_english(doc):
    """Admit only raw-byte replayed, timestamped input expression."""
    if doc.get("status") != "observed":
        if (doc.get("status") != "unavailable" or doc.get("observations") != []
                or any(k in doc for k in ("raw_body_base64","raw_sha256","raw_bytes"))):
            return None, "invalid-source-evidence"
        return None, "source-unavailable"
    if doc.get("units") != "ft" or doc.get("station") != STATION or doc.get("datum") != DATUM:
        return None, "incompatible-source-reference"
    try:
        reconstructed = replay_source(doc)
    except (TypeError, ValueError, KeyError, ArithmeticError, OverflowError):
        return None, "invalid-source-evidence"
    if reconstructed is None:
        return None, "source-unavailable"
    candidates = []
    for t, (value, quality) in sorted(reconstructed.items()):
        dt = datetime.fromisoformat(t)
        if dt.tzinfo != timezone.utc:
            return None, "invalid-source-timestamp"
        candidates.append((t, F(value), quality))
    if len(candidates) < 12:
        return None, "insufficient-source-variation-or-coverage"
    if max(x for _,x,_ in candidates) - min(x for _,x,_ in candidates) <= EPS:
        return None, "insufficient-source-variation-or-coverage"
    return candidates, "ready"

def policy(english):
    """Observe input expression only; never inspect metric target before choice.

    Two extremes maximize input separation. Two interior x quantiles challenge
    an affine relationship. Four time-spaced nontraining points are selected
    for later falsification. Tie-breaking is deterministic by timestamp.
    """
    candidates, reason = _check_english(english)
    if candidates is None:
        return {"schema": SCHEMA, "status": "undetermined", "reason": reason}
    ordered = sorted(candidates, key=lambda t: (t[1], t[0]))
    n = len(ordered)
    choice = [ordered[i] for i in (0, (n-1)//3, (2*(n-1))//3, n-1)]
    chosen = {t[0] for t in choice}
    if len(chosen) != N_TRAIN:
        return {"schema":SCHEMA, "status":"undetermined","reason":"duplicate-training-time"}
    times = sorted(candidates)
    available = [r for r in times if r[0] not in chosen]
    if len(available) < N_CHALLENGE:
        return {"schema":SCHEMA,"status":"undetermined","reason":"insufficient-heldout-coverage"}
    # Midpoints of four chronological quarters, excluding training timestamps.
    indices = [(len(available) * (2*i+1)) // 8 for i in range(N_CHALLENGE)]
    challenges = [available[i] for i in indices]
    if len({r[0] for r in challenges}) != N_CHALLENGE:
        raise AssertionError("chronological challenge plan duplicated a timestamp")
    low, high = ordered[0][1], ordered[-1][1]
    baseline = [times[i] for i in
                (0, (len(times)-1)//3, (2*(len(times)-1))//3, len(times)-1)]
    base_span = max(v for _,v,_ in baseline) - min(v for _,v,_ in baseline)
    # The two-point worst-case interval-width bound is 4*EPS/delta_x,
    # not a probability or a guarantee that the 4-point fit will succeed.
    plan = {
        "schema": SCHEMA,
        "status": "planned",
        "scope": "only-input-expression-observed-before-selection",
        "english_raw_sha256": english["raw_sha256"],
        "n_source_observations":len(candidates),
        "training": [x[0] for x in choice],
        "challenge": [x[0] for x in challenges],
        "input_range": [rational(low), rational(high)],
        "maximal_two_point_slope_width_upper_bound":
            rational(4*EPS/(high-low)),
        "chronological_baseline_two_point_upper_bound":
            rational(4*EPS/base_span) if base_span > 0 else None,
        "assumed_cost": "one-selected-metric-window-request",
        "training_budget": N_TRAIN,
        "challenge_budget": N_CHALLENGE,
        "selection_rules": "x-extremes-x-tertiles-then-time-quarter-holdouts",
    }
    plan["plan_digest"] = digest(plan)
    return plan

def _target(doc, timestamp, expected_url, english_quality):
    """Require a separately addressed byte-replayed response at exact time."""
    if doc.get("source") != expected_url:
        return None, "invalid-target-source-url"
    if doc.get("status") != "observed":
        if (doc.get("status") != "unavailable" or doc.get("observations") != []
                or any(k in doc for k in ("raw_body_base64","raw_sha256","raw_bytes"))):
            return None, "invalid-target-evidence"
        return None, "unavailable"
    if doc.get("units") != "m" or doc.get("station") != STATION or doc.get("datum") != DATUM:
        return None, "incompatible-target-reference"
    try:
        rows = replay_source(doc)
    except (ValueError, TypeError, KeyError, ArithmeticError, OverflowError):
        return None, "invalid-target-raw-evidence"
    if rows is None or timestamp not in rows:
        return None, "requested-target-not-returned"
    value, quality = rows[timestamp]
    if quality != english_quality:
        return None, "provider-quality-mismatch"
    return F(value), "observed"

def evaluate(input_doc, plan, returns):
    """Strict evidence gate; never silently replace a refused target with zero."""
    independent = policy(input_doc)
    if plan != independent or plan.get("status") != "planned":
        return {"status":"invalid-plan","reason":"source-or-selection-mismatch"}
    if not isinstance(returns,list) or len(returns) != N_TRAIN + N_CHALLENGE:
        return {"status":"undetermined","reason":"incomplete-request-set"}
    expected = [(t,"training") for t in plan["training"]] + [
        (t,"challenge") for t in plan["challenge"]]
    english, reason = _check_english(input_doc)
    if english is None:
        return {"status":"invalid-plan","reason":reason}
    available = {t:(x,q) for t,x,q in english}
    acquired = {}
    for item, (stamp,purpose) in zip(returns,expected):
        if not isinstance(item,dict) or item.get("timestamp_utc") != stamp or item.get("purpose") != purpose:
            return {"status":"invalid-return","reason":"wrong-order-or-unrequested-target"}
        if set(item) != {"timestamp_utc","purpose","source"}:
            return {"status":"invalid-return","reason":"unexpected-return-fields"}
        if not isinstance(item["source"],dict):
            return {"status":"invalid-return","reason":"nonobject-source"}
        y, status = _target(item["source"],stamp,target_uri(stamp),available[stamp][1])
        if status != "observed":
            return {"status": "invalid-evidence" if status.startswith(("invalid", "incompatible")) else "undetermined",
                    "reason":status,"at":stamp}
        acquired[stamp] = (available[stamp][0], y)
    relation, status = fit([acquired[t] for t in plan["training"]])
    if relation is None:
        return {"status":"undetermined","reason":status}
    heldout = challenge(relation,[(t,*acquired[t]) for t in plan["challenge"]])
    return {
        "status": heldout["status"],
        "scope": "one-provider-multirequest-not-independent-physical-sensing",
        "training_requests":N_TRAIN,
        "challenge_requests":N_CHALLENGE,
        "source_day_requests":1,
        "logical_requests":1+len(returns),
        "retained_original_response_bytes":
            input_doc["raw_bytes"] + sum(item["source"]["raw_bytes"] for item in returns),
        "retained_target_response_bytes":
            sum(item["source"]["raw_bytes"] for item in returns),
        "slope_min":rational(relation.lower),
        "slope_max":rational(relation.upper),
        "selected_slope":rational(relation.alpha),
        "selected_offset":rational(relation.intercept),
        "observed_training_interval_width":rational(relation.upper-relation.lower),
        "heldout":heldout,
    }

def live(day=None):
    day=fixed_day(day)
    first=datetime(day.year,day.month,day.day,tzinfo=timezone.utc)
    doc=fetch_document(day_uri(day),"english")
    plan=policy(doc)
    returns=[]
    if plan["status"]=="planned":
        for purpose in ("training","challenge"):
            for t in plan[purpose]:
                returns.append({"timestamp_utc":t,"purpose":purpose,
                                "source":fetch_document(target_uri(t),"metric")})
    return {"schema":SCHEMA,"encounter":"live-read-only-noaa",
            "actual_http_request_attempts":1+len(returns),
            "fixed_utc_day":day.strftime("%Y%m%d"),"input_source":doc,
            "plan":plan,"returns":returns,
            "result":evaluate(doc,plan,returns) if plan["status"]=="planned"
                     else {"status":"undetermined","reason":plan["reason"]}}

def replay(data):
    if not isinstance(data,dict) or data.get("schema")!=SCHEMA:
        raise ValueError("wrong experiment schema")
    if data.get("encounter") not in ("live-read-only-noaa", "masked-retrospective-fixture"):
        raise ValueError("unrecognized source context")
    if data["encounter"] == "live-read-only-noaa":
        stamp=data.get("fixed_utc_day")
        if not isinstance(stamp,str) or not re.fullmatch(r"\\d{8}",stamp):
            raise ValueError("invalid declared source day")
        try:
            day=datetime.strptime(stamp,"%Y%m%d").date()
        except ValueError as exc:
            raise ValueError("invalid calendar day") from exc
        if data["input_source"].get("source") != day_uri(day):
            raise ValueError("source-day request contract differs")
        if any(datetime.fromisoformat(r["timestamp_utc"]).date()!=day
               for r in data["returns"]):
            raise ValueError("target outside declared UTC day")
        if (type(data.get("actual_http_request_attempts")) is not int
                or data["actual_http_request_attempts"]!=1+len(data["returns"])):
            raise ValueError("request attempt accounting mismatch")
    plan=policy(data["input_source"])
    if plan != data["plan"]:
        raise ValueError("tampered acquisition plan")
    expected = evaluate(data["input_source"],plan,data["returns"]) if plan["status"]=="planned" else {
        "status":"undetermined","reason":plan["reason"]}
    if expected != data["result"]:
        raise ValueError("claimed outcome does not reconstruct from raw evidence")
    return {"replay": "source-bytes-and-observer-policy", "status":expected["status"],
            "training_requests":expected.get("training_requests"),
            "challenge_requests":expected.get("challenge_requests"),
            "scope":"not-an-instrument-authenticity-check"}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live",action="store_true")
    mode.add_argument("--replay",metavar="REPORT.json")
    p.add_argument("--day",help="Completed UTC YYYYMMDD for a live observation")
    args=p.parse_args()
    if args.live:
        print(json.dumps(live(args.day),indent=2,sort_keys=True))
    else:
        print(json.dumps(replay(json.loads(Path(args.replay).read_text(encoding="utf8"))),
                         indent=2,sort_keys=True))
