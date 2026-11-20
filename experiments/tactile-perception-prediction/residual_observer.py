"""TPP-006: compare provider tide predictions with physical observations.

Learn one constant correction from one fully elapsed UTC day. Freeze it before
testing another, distinct day. The evidence is historical/provider-reported,
not a prospective forecast or proof of independent instrument calibration.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timedelta, timezone
from fractions import Fraction as Q
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"tactile-perception-observations"))
from noaa_bridge import HOST, PATH as NOAA_PATH, STATION, DATUM, MAX_RESPONSE_BYTES
from independent_replay import replay_source

SCHEMA="in-formation-space.tpp006.prediction-observation-residual.v1"
MIN_OVERLAP=120
MAX_DAY_RECORDS=360


def as_ratio(value):
    if not isinstance(value,Q):
        raise TypeError("ratio must be exact")
    return f"{value.numerator}/{value.denominator}"


def utc_days(train=None,test=None):
    """Never test a future or currently incomplete physical-observation day."""
    today=datetime.now(timezone.utc).date()
    def parse(raw,default):
        if raw is None:
            return default
        if not isinstance(raw,str) or not re.fullmatch(r"\d{8}",raw):
            raise ValueError("date must be YYYYMMDD")
        try:
            return datetime.strptime(raw,"%Y%m%d").date()
        except ValueError as exc:
            raise ValueError("invalid UTC calendar date") from exc
    training=parse(train,today-timedelta(days=2))
    testing=parse(test,today-timedelta(days=1))
    if not training < testing < today:
        raise ValueError("require training day before distinct fully elapsed test day")
    return training,testing


def url(product,day):
    """Fixed origin, station, datum and metric expression."""
    if product not in ("water_level","predictions"):
        raise ValueError("unsupported physical observation/model product")
    if not hasattr(day,"strftime"):
        raise ValueError("invalid day")
    query={
        "application":"InFormationSpace_TPP006",
        "begin_date":day.strftime("%Y%m%d"),
        "end_date":day.strftime("%Y%m%d"),
        "datum":DATUM,"format":"json","product":product,
        "station":STATION,"time_zone":"gmt","units":"metric",
    }
    if product=="predictions":
        query["interval"]="6"
    return f"https://{HOST}{NOAA_PATH}?{urlencode(query)}"


def collect(product,day):
    """One read-only HTTPS attempt per product; preserve full provider bytes."""
    target=url(product,day)
    try:
        request=Request(target,headers={
            "Accept":"application/json",
            "User-Agent":"InFormationSpace-TPP006/1.0",
        })
        with urlopen(request,timeout=15) as response:
            final=urlsplit(response.geturl())
            if final.scheme!="https" or final.hostname!=HOST or final.path!=NOAA_PATH:
                raise ValueError("unexpected redirect")
            if response.status!=200:
                raise ValueError("unexpected response code")
            original=response.read(MAX_RESPONSE_BYTES+1)
            if len(original)>MAX_RESPONSE_BYTES:
                raise ValueError("response exceeds acquisition bound")
        return {
            "status":"received","source":target,"product":product,
            "utc_day":day.strftime("%Y%m%d"),
            "retrieved_utc":datetime.now(timezone.utc).isoformat(),
            "raw_bytes":len(original),"raw_sha256":sha256(original).hexdigest(),
            "raw_body_base64":base64.b64encode(original).decode("ascii"),
            "scope":"one-provider-read-only-physical-data",
        }
    except (OSError,ValueError,TimeoutError) as exc:
        return {"status":"unavailable","source":target,"product":product,
                "utc_day":day.strftime("%Y%m%d"),"reason":type(exc).__name__,
                "scope":"failed-read-no-physical-observation"}


def _source_bytes(doc):
    """Check bytes, URL, exact intended product/day and no silently changed datum."""
    if not isinstance(doc,dict) or doc.get("product") not in ("water_level","predictions"):
        raise ValueError("unknown product")
    stamp=doc.get("utc_day")
    if not isinstance(stamp,str) or not re.fullmatch(r"\d{8}",stamp):
        raise ValueError("invalid source day")
    day=datetime.strptime(stamp,"%Y%m%d").date()
    if doc.get("source")!=url(doc["product"],day):
        raise ValueError("unexpected source reference")
    if doc.get("status")=="unavailable":
        if any(k in doc for k in ("raw_sha256","raw_body_base64","raw_bytes")):
            raise ValueError("unavailable label conflicts with received data")
        return None
    if doc.get("status")!="received":
        raise ValueError("invalid source status")
    if doc.get("scope")!="one-provider-read-only-physical-data":
        raise ValueError("scope mismatch")
    try:
        original=base64.b64decode(doc["raw_body_base64"],validate=True)
    except (KeyError,ValueError,TypeError) as exc:
        raise ValueError("invalid original response encoding") from exc
    if len(original)>MAX_RESPONSE_BYTES or len(original)!=doc.get("raw_bytes"):
        raise ValueError("original response length mismatch")
    if sha256(original).hexdigest()!=doc.get("raw_sha256"):
        raise ValueError("original response digest mismatch")
    return original


def _decimal(raw):
    # Exact decimal readings, with canonical base-10 representation.
    if not isinstance(raw,str) or not re.fullmatch(r"-?(?:[0-9]+)(?:\.[0-9]+)?",raw):
        raise ValueError("invalid numeric prediction/observation")
    return Q(raw)


def read(doc):
    """Return (UTC timestamp -> exact value, quality) from retained source bytes."""
    raw=_source_bytes(doc)
    if raw is None:
        return None
    try:
        obj=json.loads(raw.decode("utf8"))
    except (ValueError,UnicodeError) as exc:
        raise ValueError("invalid source JSON") from exc
    if not isinstance(obj,dict):
        raise ValueError("unexpected JSON top-level")
    if "error" in obj:
        return None
    day=doc["utc_day"]
    if doc["product"]=="water_level":
        # The previous experiment's independent verifier handles observations.
        # It expects the richer TPP-003 source document; reconstruct exactly
        # that documented wrapper from the unchanged original bytes.
        info={
            "status":"observed","source":doc["source"],"product":"water_level",
            "station":STATION,"datum":DATUM,"time_zone":"UTC","units":"m",
            "raw_body_base64":doc["raw_body_base64"],"raw_bytes":doc["raw_bytes"],
            "raw_sha256":doc["raw_sha256"],
        }
        metadata=obj.get("metadata")
        records=obj.get("data")
        if not isinstance(metadata,dict) or str(metadata.get("id"))!=STATION or not isinstance(records,list):
            raise ValueError("unexpected physical-observation schema")
        normalized=[]
        for entry in records:
            if not isinstance(entry,dict):
                raise ValueError("malformed observation row")
            t=datetime.strptime(entry["t"],"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).isoformat()
            value=entry.get("v")
            sig=entry.get("s")
            if value not in (None,""):
                _decimal(value)
            if sig not in (None,""):
                _decimal(sig)
            q=entry.get("q")
            if q not in ("p","v") or not isinstance(entry.get("f"),str):
                raise ValueError("invalid provider quality")
            normalized.append({"timestamp_utc":t,"value":value or None,
                               "sigma":sig or None,
                               "flags_raw":entry["f"],"provider_quality":q,
                               "status":"missing" if value in (None,"") else
                                        ("provider-verified" if q=="v" else "preliminary")})
        info["observations"]=normalized
        result=replay_source(info)
        if result is None:
            return None
        values={t:(_decimal(str(v)),q) for t,(v,q) in result.items()}
    else:
        if "metadata" in obj and str(obj["metadata"].get("id"))!=STATION:
            raise ValueError("prediction metadata station mismatch")
        records=obj.get("predictions")
        if not isinstance(records,list):
            raise ValueError("prediction data missing")
        values={}
        for item in records:
            if not isinstance(item,dict):
                raise ValueError("invalid prediction row")
            stamp=datetime.strptime(item["t"],"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).isoformat()
            if stamp in values:
                raise ValueError("duplicate prediction timestamp")
            values[stamp]=(_decimal(item["v"]),"model-prediction")
    if len(values)>MAX_DAY_RECORDS:
        raise ValueError("excessive samples for one day")
    for t in values:
        if t[:10]!=datetime.strptime(day,"%Y%m%d").strftime("%Y-%m-%d"):
            raise ValueError("out-of-day provider timestamp")
    return values


def paired(observed,predicted):
    """Never fabricate matches, interpolate timestamps or convert absent to zero."""
    if observed is None or predicted is None:
        return None
    return [(t,observed[t][0],predicted[t][0],observed[t][1])
            for t in sorted(observed.keys() & predicted.keys())]


def median(values):
    values=sorted(values)
    if not values:
        raise ValueError("median requires actual observations")
    k=len(values)//2
    return values[k] if len(values)%2 else (values[k-1]+values[k])/2


def score(pairs,offset):
    baseline=[abs(y-yhat) for _,y,yhat,_ in pairs]
    corrected=[abs(y-yhat-offset) for _,y,yhat,_ in pairs]
    n=len(pairs)
    return {"samples":n,
            "baseline_mae_m":as_ratio(sum(baseline,Q(0))/n),
            "corrected_mae_m":as_ratio(sum(corrected,Q(0))/n),
            "maximum_baseline_error_m":as_ratio(max(baseline)),
            "maximum_corrected_error_m":as_ratio(max(corrected)),
            "provider_quality_counts":dict(sorted(Counter(q for *_,q in pairs).items()))}


def evaluate(documents):
    """Learn only from prior day; apply frozen correction to later day."""
    if not isinstance(documents,list) or len(documents)!=4:
        return {"status":"invalid-encounter","reason":"expected-two-days-two-products"}
    expected=("water_level","predictions","water_level","predictions")
    if tuple(x.get("product") for x in documents)!=expected:
        return {"status":"invalid-encounter","reason":"unexpected-source-order"}
    if documents[0].get("utc_day")!=documents[1].get("utc_day") or documents[2].get("utc_day")!=documents[3].get("utc_day"):
        return {"status":"invalid-encounter","reason":"day-product-mismatch"}
    if documents[0].get("utc_day")>=documents[2].get("utc_day"):
        return {"status":"invalid-encounter","reason":"future-leakage-or-reversed-days"}
    try:
        histories=[read(x) for x in documents]
    except (ValueError,TypeError,KeyError,ArithmeticError,OverflowError) as exc:
        return {"status":"invalid-evidence","reason":type(exc).__name__}
    train=paired(*histories[:2]); test=paired(*histories[2:])
    if train is None or test is None:
        return {"status":"undetermined","reason":"missing-physical-or-model-observation"}
    if len(train)<MIN_OVERLAP or len(test)<MIN_OVERLAP:
        return {"status":"undetermined","reason":"insufficient-overlap",
                "training_overlap":len(train),"heldout_overlap":len(test)}
    offset=median([observed-predicted for _,observed,predicted,_ in train])
    training=score(train,offset)
    heldout=score(test,offset)
    x=Q(heldout["baseline_mae_m"]);y=Q(heldout["corrected_mae_m"])
    return {"status":"heldout-improved" if y<x else ("heldout-worse" if y>x else "heldout-unchanged"),
            "scope":"historical-one-provider-tide-prediction-vs-preliminary-measurement",
            "train_day":documents[0]["utc_day"],"heldout_day":documents[2]["utc_day"],
            "frozen_median_residual_correction_m":as_ratio(offset),
            "training":training,"heldout":heldout,
            "delta_heldout_mae_m":as_ratio(y-x),
            "source_sha256":[doc["raw_sha256"] for doc in documents],
            "strictly_separated_days":True}


def experiment(train=None,test=None):
    train_day,test_day=utc_days(train,test)
    docs=[collect(product,day) for day in (train_day,test_day)
          for product in ("water_level","predictions")]
    return {"schema":SCHEMA,"mode":"public-read-only",
            "documents":docs,"assessment":evaluate(docs),
            "request_attempts":len(docs)}


def replay(report):
    if not isinstance(report,dict) or report.get("schema")!=SCHEMA:
        raise ValueError("unexpected experiment schema")
    if report.get("mode") not in ("public-read-only","offline-synthetic-model"):
        raise ValueError("unknown evidence origin")
    if report.get("request_attempts")!=len(report.get("documents",[])):
        raise ValueError("request accounting mismatch")
    again=evaluate(report["documents"])
    if again!=report.get("assessment"):
        raise ValueError("outcome does not reconstruct from retained source bytes")
    return {"status":again["status"],"reconstructed":True,
            "source_authentication":"not-established",
            "scope":"model-consistency-not-independent-instrument-verification"}


if __name__=="__main__":
    args=argparse.ArgumentParser()
    opts=args.add_mutually_exclusive_group(required=True)
    opts.add_argument("--live",action="store_true")
    opts.add_argument("--replay")
    args.add_argument("--train-day")
    args.add_argument("--test-day")
    options=args.parse_args()
    if options.live:
        print(json.dumps(experiment(options.train_day,options.test_day),indent=2,sort_keys=True))
    else:
        print(json.dumps(replay(json.loads(Path(options.replay).read_text(encoding="utf8"))),
                         indent=2,sort_keys=True))
