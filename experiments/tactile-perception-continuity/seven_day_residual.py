"""TPP-007: seven-day residual continuity using raw NOAA predictions and observations.

Two fixed-date, bounded HTTPS requests capture a week's provider-reported
measurements and model predictions. A day-one residual correction is held
fixed; a second, strictly causal comparator uses only the preceding day.
No physical actuation, issue-time forecast, or external sensor authenticity.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction as Q
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"tactile-perception-prediction"))
from residual_observer import (HOST, NOAA_PATH, DATUM, STATION,
                               median, as_ratio, MIN_OVERLAP)
SCHEMA="in-formation-space.tpp007.seven-day-residual-continuity.v1"
N_DAYS=7
MAX_RAW=512_000
MAX_POINTS=7*240+20


def period(start=None,end=None):
    today=datetime.now(timezone.utc).date()
    def day(v,default):
        if v is None:
            return default
        if not isinstance(v,str) or not re.fullmatch(r"\d{8}",v):
            raise ValueError("day must be UTC YYYYMMDD")
        return datetime.strptime(v,"%Y%m%d").date()
    first=day(start,today-timedelta(days=N_DAYS))
    last=day(end,today-timedelta(days=1))
    if (last-first).days!=N_DAYS-1 or last>=today:
        raise ValueError("require exactly seven fully elapsed consecutive UTC days")
    return first,last


def url(product,first,last):
    if product not in ("water_level","predictions"):
        raise ValueError("unknown NOAA product")
    if not isinstance(first,date) or not isinstance(last,date):
        raise ValueError("dates required")
    if (last-first).days!=N_DAYS-1:
        raise ValueError("only fixed seven-day intervals")
    args={
        "application":"InFormationSpace_TPP007",
        "begin_date":first.strftime("%Y%m%d"),"end_date":last.strftime("%Y%m%d"),
        "datum":DATUM,"format":"json","product":product,
        "station":STATION,"time_zone":"gmt","units":"metric",
    }
    if product=="predictions":
        args["interval"]="6"
    return f"https://{HOST}{NOAA_PATH}?{urlencode(args)}"


def fetch(product,first,last):
    target=url(product,first,last)
    try:
        req=Request(target,headers={"Accept":"application/json",
                                    "User-Agent":"InFormationSpace-TPP007/1.0"})
        with urlopen(req,timeout=20) as response:
            final=urlsplit(response.geturl())
            if final.scheme!="https" or final.hostname!=HOST or final.path!=NOAA_PATH:
                raise ValueError("unapproved provider redirect")
            if response.status!=200:
                raise ValueError("non-successful public request")
            raw=response.read(MAX_RAW+1)
            if len(raw)>MAX_RAW:
                raise ValueError("oversized public response")
        return {"status":"received","source":target,"product":product,
                "start_utc_day":first.strftime("%Y%m%d"),
                "end_utc_day":last.strftime("%Y%m%d"),
                "retrieved_utc":datetime.now(timezone.utc).isoformat(),
                "raw_bytes":len(raw),"raw_sha256":sha256(raw).hexdigest(),
                "raw_body_base64":base64.b64encode(raw).decode("ascii"),
                "scope":"public-provider-read-only-no-instrument-attestation"}
    except (OSError,TimeoutError,ValueError) as exc:
        return {"status":"unavailable","source":target,"product":product,
                "start_utc_day":first.strftime("%Y%m%d"),
                "end_utc_day":last.strftime("%Y%m%d"),
                "reason":type(exc).__name__,
                "scope":"read-unavailable-no-physical-observation"}


def raw_body(doc):
    if not isinstance(doc,dict) or doc.get("product") not in ("water_level","predictions"):
        raise ValueError("unknown document product")
    for field in ("start_utc_day","end_utc_day"):
        if not isinstance(doc.get(field),str) or not re.fullmatch(r"\d{8}",doc[field]):
            raise ValueError("invalid claimed observation period")
    first=datetime.strptime(doc["start_utc_day"],"%Y%m%d").date()
    last=datetime.strptime(doc["end_utc_day"],"%Y%m%d").date()
    if doc.get("source")!=url(doc["product"],first,last):
        raise ValueError("mismatched request context")
    if doc.get("status")=="unavailable":
        if any(k in doc for k in ("raw_body_base64","raw_sha256","raw_bytes")):
            raise ValueError("received source bytes relabeled unavailable")
        return None
    if doc.get("status")!="received" or doc.get("scope")!="public-provider-read-only-no-instrument-attestation":
        raise ValueError("invalid source scope/status")
    try:
        original=base64.b64decode(doc["raw_body_base64"],validate=True)
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError("invalid base64 source") from exc
    if len(original)>MAX_RAW or len(original)!=doc.get("raw_bytes"):
        raise ValueError("original response length differs")
    if sha256(original).hexdigest()!=doc.get("raw_sha256"):
        raise ValueError("original response digest differs")
    return original


def value(s):
    if not isinstance(s,str) or not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?",s):
        raise ValueError("invalid decimal provider quantity")
    return Q(s)


def parse(doc):
    """Independent reconstruction of two distinct NOAA product grammars."""
    raw=raw_body(doc)
    if raw is None:
        return None
    try:
        obj=json.loads(raw.decode("utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise ValueError("source JSON unreadable") from exc
    if not isinstance(obj,dict):
        raise ValueError("unexpected source JSON shape")
    if "error" in obj:
        return None
    day0=datetime.strptime(doc["start_utc_day"],"%Y%m%d").date()
    day1=datetime.strptime(doc["end_utc_day"],"%Y%m%d").date()
    if doc["product"]=="water_level":
        metadata=obj.get("metadata")
        if not isinstance(metadata,dict) or str(metadata.get("id"))!=STATION:
            raise ValueError("unmatched physical station metadata")
        rows=obj.get("data")
    else:
        metadata=obj.get("metadata")
        if metadata is not None and (not isinstance(metadata,dict) or str(metadata.get("id"))!=STATION):
            raise ValueError("unmatched prediction station metadata")
        rows=obj.get("predictions")
    if not isinstance(rows,list) or len(rows)>MAX_POINTS:
        raise ValueError("provider readings absent or excessive")
    parsed={}
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("unexpected data row")
        try:
            stamp=datetime.strptime(row["t"],"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError("invalid source timestamp") from exc
        if not day0<=stamp.date()<=day1:
            raise ValueError("sample outside claimed seven days")
        clock=stamp.isoformat()
        if clock in parsed:
            raise ValueError("duplicate timestamp cannot be interpreted twice")
        if doc["product"]=="water_level":
            quality=row.get("q")
            flags=row.get("f")
            if quality not in ("p","v") or not isinstance(flags,str):
                raise ValueError("unknown observation quality")
            sig=row.get("s")
            if sig not in (None,"") and value(sig)<0:
                raise ValueError("negative sample deviation")
            raw_value=row.get("v")
            reading=None if raw_value in (None,"") else value(raw_value)
        else:
            quality="model-prediction"
            reading=value(row.get("v"))
        parsed[clock]=(reading,quality)
    return parsed


def day_pairs(observed,predicted,first):
    """Group only exact timestamp-matched nonmissing observations by UTC day."""
    output={}
    for i in range(N_DAYS):
        d=(first+timedelta(days=i)).strftime("%Y-%m-%d")
        output[d]=[]
    for t in sorted(observed.keys() & predicted.keys()):
        o,q=observed[t];p,_=predicted[t]
        if o is None or p is None:
            continue
        output[t[:10]].append((t,o,p,q))
    return output


def mae(pairs,offset):
    return sum((abs(o-p-offset) for _,o,p,_ in pairs),Q(0))/len(pairs)


def comparison(baseline,corrected):
    return "improved" if corrected<baseline else ("worse" if corrected>baseline else "unchanged")


def evaluate(docs):
    if not isinstance(docs,list) or len(docs)!=2:
        return {"status":"invalid-manifest","reason":"expected-two-batched-products"}
    if [d.get("product") for d in docs]!=["water_level","predictions"]:
        return {"status":"invalid-manifest","reason":"wrong-product-order"}
    if any(docs[0].get(k)!=docs[1].get(k) for k in ("start_utc_day","end_utc_day")):
        return {"status":"invalid-manifest","reason":"reference-range-mismatch"}
    try:
        first=datetime.strptime(docs[0]["start_utc_day"],"%Y%m%d").date()
        last=datetime.strptime(docs[0]["end_utc_day"],"%Y%m%d").date()
        if (last-first).days!=N_DAYS-1:
            raise ValueError("wrong interval length")
        observed,predicted=(parse(d) for d in docs)
    except (ValueError,TypeError,KeyError,ArithmeticError,OverflowError) as exc:
        return {"status":"invalid-source-evidence","reason":type(exc).__name__}
    if observed is None or predicted is None:
        return {"status":"undetermined","reason":"source-unavailable-or-provider-error"}
    grouped=day_pairs(observed,predicted,first)
    train_day=first.strftime("%Y-%m-%d")
    training=grouped[train_day]
    if len(training)<MIN_OVERLAP:
        return {"status":"undetermined","reason":"insufficient-initial-day-evidence",
                "training_samples":len(training)}
    frozen=median([o-p for _,o,p,_ in training])
    previous=frozen
    evaluated=[]
    base_sum=frozen_sum=rolling_sum=Q(0)
    n_baseline=n_rolling=0
    for i in range(1,N_DAYS):
        d=(first+timedelta(days=i)).strftime("%Y-%m-%d")
        pairs=grouped[d]
        if len(pairs)<MIN_OVERLAP:
            evaluated.append({"day":d,"status":"undetermined","reason":"insufficient-day-evidence",
                              "samples":len(pairs)})
            previous=None
            continue
        baseline=mae(pairs,Q(0))
        frozen_error=mae(pairs,frozen)
        adaptive_error=mae(pairs,previous) if previous is not None else None
        item={"day":d,"status":"compared",
              "samples":len(pairs),
              "provider_quality_counts":dict(sorted(Counter(q for *_,q in pairs).items())),
              "baseline_mae_m":as_ratio(baseline),
              "frozen_mae_m":as_ratio(frozen_error),
              "frozen_vs_baseline":comparison(baseline,frozen_error),
              "rolling_one_day_lag_mae_m":as_ratio(adaptive_error) if adaptive_error is not None else None,
              "rolling_vs_baseline":comparison(baseline,adaptive_error) if adaptive_error is not None else "undetermined",
              "applied_rolling_correction_m":as_ratio(previous) if previous is not None else None}
        evaluated.append(item)
        base_sum+=baseline*len(pairs)
        frozen_sum+=frozen_error*len(pairs)
        n_baseline+=len(pairs)
        if adaptive_error is not None:
            rolling_sum+=adaptive_error*len(pairs)
            n_rolling+=len(pairs)
        # The corrected observation for the current day may inform tomorrow,
        # but must never change this day's prediction after it was scored.
        previous=median([o-p for _,o,p,_ in pairs])
    all_complete=all(day["status"]=="compared" for day in evaluated)
    return {
        "status":"complete" if all_complete else "partial-undetermined",
        "scope":"seven-complete-historical-days-one-provider-no-prospective-issue-time",
        "first_utc_day":train_day,
        "last_utc_day":last.strftime("%Y-%m-%d"),
        "frozen_day_one_correction_m":as_ratio(frozen),
        "day_one_samples":len(training),
        "day_one_quality_counts":dict(sorted(Counter(q for *_,q in training).items())),
        "per_day":evaluated,
        "evaluated_heldout_samples":n_baseline,
        "full_week_heldout_baseline_mae_m":as_ratio(base_sum/n_baseline) if n_baseline else None,
        "full_week_heldout_frozen_mae_m":as_ratio(frozen_sum/n_baseline) if n_baseline else None,
        "one_day_lag_scored_samples":n_rolling,
        "one_day_lag_mae_m":as_ratio(rolling_sum/n_rolling) if n_rolling else None,
        "source_sha256":[doc["raw_sha256"] for doc in docs],
    }


def run(start=None,end=None):
    first,last=period(start,end)
    sources=[fetch(product,first,last) for product in ("water_level","predictions")]
    return {"schema":SCHEMA,"acquisition":"real-public-two-batched-requests",
            "actual_request_attempts":2,
            "documents":sources,"assessment":evaluate(sources)}


def replay(report):
    if not isinstance(report,dict) or report.get("schema")!=SCHEMA:
        raise ValueError("wrong experiment schema")
    if report.get("acquisition") not in ("real-public-two-batched-requests","synthetic-two-batched-fixtures"):
        raise ValueError("unrecognized acquisition mode")
    if type(report.get("actual_request_attempts")) is not int or report["actual_request_attempts"]!=2:
        raise ValueError("request count not supported by manifest")
    result=evaluate(report["documents"])
    if result!=report.get("assessment"):
        raise ValueError("retained assessment differs from independently reconstructed bytes")
    return {"status":result["status"],"replayed":True,"source_authentication":"not-established",
            "scope":"retained-provider-bytes-not-prospective-or-independent-observation"}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    choices=parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--live",action="store_true")
    choices.add_argument("--replay")
    parser.add_argument("--start-day")
    parser.add_argument("--end-day")
    args=parser.parse_args()
    if args.live:
        print(json.dumps(run(args.start_day,args.end_day),indent=2,sort_keys=True))
    else:
        print(json.dumps(replay(json.loads(Path(args.replay).read_text(encoding="utf8"))),
                         indent=2,sort_keys=True))
