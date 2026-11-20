"""Independent TPP-007 verifier using Decimal and separate source parsing.

This checker does not import seven_day_residual.py or its fit/evaluation
functions. It reconstructs a COMPLETE seven-day source-byte record and all
claimed MAEs; unavailable/incomplete provider records remain undetermined.
Both implementations still depend on NOAA's claimed sensor/model provenance.
"""
from __future__ import annotations

import base64
from collections import Counter
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from fractions import Fraction as Q
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit,parse_qs

SCHEMA="in-formation-space.tpp007.seven-day-residual-continuity.v1"
HOST="api.tidesandcurrents.noaa.gov"
PATH="/api/prod/datagetter"
STATION="9414290"

def refuse(message):
    raise ValueError(message)

def fraction(value):
    f=Q(value)
    return f"{f.numerator}/{f.denominator}"

def provider_doc(doc,product,first,last):
    if doc.get("product")!=product or doc.get("status")!="received":
        return None
    source=urlsplit(doc.get("source",""))
    if source.scheme!="https" or source.hostname!=HOST or source.path!=PATH:
        refuse("source origin inconsistent")
    params=parse_qs(source.query,keep_blank_values=True)
    req={"application":"InFormationSpace_TPP007",
         "begin_date":first,"end_date":last,
         "datum":"MLLW","format":"json","product":product,
         "station":STATION,"time_zone":"gmt","units":"metric"}
    if product=="predictions":
        req["interval"]="6"
    if params!={k:[v] for k,v in req.items()}:
        refuse("source query differs from declared reference")
    if doc.get("start_utc_day")!=first or doc.get("end_utc_day")!=last:
        refuse("source period differs")
    try:
        original=base64.b64decode(doc["raw_body_base64"],validate=True)
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError("cannot decode original source bytes") from exc
    if len(original)>512000 or len(original)!=doc.get("raw_bytes"):
        refuse("original body length differs")
    if sha256(original).hexdigest()!=doc.get("raw_sha256"):
        refuse("original source checksum differs")
    try:
        parsed=json.loads(original.decode("utf-8"))
    except (UnicodeError,ValueError) as exc:
        raise ValueError("original JSON malformed") from exc
    if not isinstance(parsed,dict) or "error" in parsed:
        return None
    if product=="water_level":
        if str((parsed.get("metadata") or {}).get("id"))!=STATION:
            refuse("observation station mismatch")
        records=parsed.get("data")
    else:
        if parsed.get("metadata") is not None and str(parsed["metadata"].get("id"))!=STATION:
            refuse("prediction station mismatch")
        records=parsed.get("predictions")
    if not isinstance(records,list) or len(records)>1700:
        refuse("unexpected source record count")
    values={}
    for record in records:
        try:
            t=datetime.strptime(record["t"],"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            if not first<=t.strftime("%Y%m%d")<=last:
                refuse("observation outside full-week contract")
            timestamp=t.isoformat()
            if timestamp in values:
                refuse("duplicate source timestamp")
            raw=record.get("v")
            if raw in (None,"") and product=="water_level":
                number=None
            else:
                if not isinstance(raw,str) or not re.fullmatch(r"-?\d+(?:\.\d+)?",raw):
                    refuse("invalid provider number")
                number=Decimal(raw)
                if not number.is_finite():
                    refuse("nonfinite number")
            if product=="water_level":
                q=record.get("q")
                if q not in ("p","v") or not isinstance(record.get("f"),str):
                    refuse("unknown observed quality")
                sigma=record.get("s")
                if sigma not in (None,""):
                    if not isinstance(sigma,str) or not re.fullmatch(r"\d+(?:\.\d+)?",sigma):
                        refuse("invalid sample deviation")
                values[timestamp]=(number,q)
            else:
                values[timestamp]=(number,"model-prediction")
        except (KeyError,TypeError,ValueError,OverflowError) as exc:
            raise ValueError("invalid or out-of-scope original record") from exc
    return values

def mae(rows,offset):
    # Sum measurements independently in Decimal; divide only *after*
    # lifting the exact finite-decimal total into a rational. Decimal
    # division by e.g. 240 otherwise rounds the repeating quotient.
    total=sum((abs(obs-model-offset) for obs,model,quality in rows),Decimal(0))
    return Q(total)/len(rows)

def med(values):
    xs=sorted(values)
    k=len(xs)//2
    return xs[k] if len(xs)%2 else (xs[k-1]+xs[k])/2

def sign(base,other):
    return "improved" if other<base else ("worse" if other>base else "unchanged")

def verify(report):
    if not isinstance(report,dict) or report.get("schema")!=SCHEMA:
        refuse("unexpected report schema")
    if report.get("actual_request_attempts")!=2:
        refuse("unexplained request count")
    docs=report.get("documents")
    if not isinstance(docs,list) or len(docs)!=2:
        refuse("expected two source documents")
    first=docs[0].get("start_utc_day")
    last=docs[0].get("end_utc_day")
    if not isinstance(first,str) or not isinstance(last,str):
        refuse("missing source period")
    try:
        start=datetime.strptime(first,"%Y%m%d").date()
        end=datetime.strptime(last,"%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("invalid source day") from exc
    if (end-start).days!=6:
        refuse("not seven consecutive days")
    observation=provider_doc(docs[0],"water_level",first,last)
    prediction=provider_doc(docs[1],"predictions",first,last)
    claim=report.get("assessment")
    if observation is None or prediction is None:
        if not isinstance(claim,dict) or claim.get("status")!="undetermined":
            refuse("missing source with claimed completed result")
        return {"status":"undetermined","checked_complete":False}
    dates=[(start+timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    groups={day:[] for day in dates}
    for stamp in sorted(observation.keys() & prediction.keys()):
        obs,q=observation[stamp];model,_=prediction[stamp]
        if obs is not None and model is not None:
            groups[stamp[:10]].append((obs,model,q))
    if any(len(v)<120 for v in groups.values()):
        if not isinstance(claim,dict) or claim.get("status") not in ("undetermined","partial-undetermined"):
            refuse("incomplete weekly readings asserted complete")
        return {"status":"undetermined","checked_complete":False}
    frozen=med([o-p for o,p,_ in groups[dates[0]]])
    preceding=frozen
    items=[]
    baseline_sum=frozen_sum=rolling_sum=Q(0)
    total=0
    for d in dates[1:]:
        samples=groups[d]
        n=len(samples)
        b=mae(samples,Decimal(0))
        f=mae(samples,frozen)
        l=mae(samples,preceding)
        quality=dict(sorted(Counter(q for _,_,q in samples).items()))
        items.append({"day":d,"status":"compared","samples":n,
                      "provider_quality_counts":quality,
                      "baseline_mae_m":fraction(b),
                      "frozen_mae_m":fraction(f),
                      "frozen_vs_baseline":sign(b,f),
                      "rolling_one_day_lag_mae_m":fraction(l),
                      "rolling_vs_baseline":sign(b,l),
                      "applied_rolling_correction_m":fraction(preceding)})
        baseline_sum+=b*n
        frozen_sum+=f*n
        rolling_sum+=l*n
        total+=n
        preceding=med([o-p for o,p,_ in samples])
    expected={
        "status":"complete",
        "scope":"seven-complete-historical-days-one-provider-no-prospective-issue-time",
        "first_utc_day":dates[0],"last_utc_day":dates[-1],
        "frozen_day_one_correction_m":fraction(frozen),
        "day_one_samples":len(groups[dates[0]]),
        "day_one_quality_counts":dict(sorted(Counter(q for _,_,q in groups[dates[0]]).items())),
        "per_day":items,
        "evaluated_heldout_samples":total,
        "full_week_heldout_baseline_mae_m":fraction(baseline_sum/total),
        "full_week_heldout_frozen_mae_m":fraction(frozen_sum/total),
        "one_day_lag_scored_samples":total,
        "one_day_lag_mae_m":fraction(rolling_sum/total),
        "source_sha256":[x["raw_sha256"] for x in docs],
    }
    if claim!=expected:
        refuse("claimed seven-day result differs from independent Decimal reconstruction")
    return {"status":"complete","checked_complete":True,
            "verified_days":7,"heldout_observations":total,
            "source_authentication":"not-established",
            "scope":"independent-mathematical-reconstruction-of-provider-bytes"}

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("usage: independent_weekly_check.py tpp007-live.json")
    report=json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))
    print(json.dumps(verify(report),sort_keys=True,indent=2))
