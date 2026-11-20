"""Independent TPP-003 replay: raw NOAA bytes -> parsed observations -> unit report.

Does not import the producer (noaa_bridge). Checks exact content consistency,
NOT NOAA server identity or physical measurement correctness.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

HOST="api.tidesandcurrents.noaa.gov"
PATH="/api/prod/datagetter"
TOL=Decimal("0.001")
FOOT_M=Decimal("0.3048")
MAX=512000

def fail(reason):
    raise ValueError(reason)

def _number(x):
    if x in ("", None):
        return None
    if not isinstance(x,str):
        fail("not a reported numeric string")
    n=Decimal(x)
    if not n.is_finite():
        fail("nonfinite number")
    return n

def replay_source(record):
    if record.get("status") != "observed":
        if record.get("status") not in ("unavailable","invalid"):
            fail("unknown source state")
        if record.get("observations") != []:
            fail("unavailable source asserts observations")
        return None
    body=record.get("raw_body_base64")
    if not isinstance(body,str):
        fail("missing exact bytes")
    try:
        raw=base64.b64decode(body,validate=True)
    except (ValueError,base64.binascii.Error) as exc:
        raise ValueError("invalid raw base64") from exc
    if len(raw)>MAX or len(raw)!=record.get("raw_bytes"):
        fail("raw length differs")
    if sha256(raw).hexdigest()!=record.get("raw_sha256"):
        fail("raw bytes digest differs")
    try:
        data=json.loads(raw.decode("utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise ValueError("raw JSON invalid") from exc
    if not isinstance(data,dict) or not isinstance(data.get("metadata"),dict):
        fail("missing provider metadata")
    station=record.get("station")
    if str(data["metadata"].get("id"))!=station:
        fail("station differs")
    parsed=urlsplit(record.get("source",""))
    if parsed.scheme!="https" or parsed.hostname!=HOST or parsed.path!=PATH:
        fail("unexpected source")
    params=parse_qs(parsed.query)
    units={"m":"metric","ft":"english"}.get(record.get("units"))
    if units is None:
        fail("unexpected units")
    requirements={"station":station,"units":units,"product":"water_level",
                  "datum":"MLLW","time_zone":"gmt","format":"json"}
    if any(params.get(k)!=[v] for k,v in requirements.items()):
        fail("source contract differs")
    if record.get("datum")!="MLLW" or record.get("time_zone")!="UTC":
        fail("observation reference differs")
    values=data.get("data")
    normalized=record.get("observations")
    if not isinstance(values,list) or not isinstance(normalized,list) or len(values)!=len(normalized):
        fail("observation count differs")
    seen=set()
    parsed_rows={}
    for source,interpreted in zip(values,normalized):
        if not isinstance(source,dict) or not isinstance(interpreted,dict):
            fail("row structure differs")
        t=datetime.strptime(source["t"],"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).isoformat()
        if t in seen:
            fail("duplicate source time")
        seen.add(t)
        value=_number(source.get("v"))
        sigma=_number(source.get("s"))
        if sigma is not None and sigma < 0:
            fail("negative sigma")
        q=source.get("q")
        if q not in ("p","v") or not isinstance(source.get("f"),str):
            fail("unexpected quality flags")
        status="missing" if value is None else ("provider-verified" if q=="v" else "preliminary")
        expected={"timestamp_utc":t,"value":str(value) if value is not None else None,
                  "sigma":str(sigma) if sigma is not None else None,
                  "flags_raw":source["f"],"provider_quality":q,"status":status}
        if interpreted!=expected:
            fail("normalized observation disagrees with original bytes")
        if value is not None:
            parsed_rows[t]=(value,q)
    return parsed_rows

def verify(report):
    if report.get("experiment")!="TPP-003":
        fail("wrong experiment")
    sources=report.get("observations")
    if not isinstance(sources,list) or len(sources)!=2:
        fail("expected two source expressions")
    m=replay_source(sources[0])
    e=replay_source(sources[1])
    claim=report.get("cross_unit_relation")
    if not isinstance(claim,dict):
        fail("missing comparison claim")
    if m is None or e is None:
        if claim.get("status")!="undetermined":
            fail("unavailable source claimed comparison")
        return {"checked_sources":sum(x is not None for x in (m,e)),
                "status":"undetermined","verified_raw_bytes":False}
    if sources[0].get("units")!="m" or sources[1].get("units")!="ft":
        fail("unexpected source order or unit")
    if sources[0].get("station")!=sources[1].get("station"):
        fail("different stations")
    if sources[0].get("datum")!=sources[1].get("datum"):
        fail("different datums")
    times=sorted(m.keys()&e.keys())
    if not times:
        if claim.get("status")!="undetermined" or claim.get("matches")!=0:
            fail("non-overlap misreported")
        return {"checked_sources":2,"status":"undetermined","verified_raw_bytes":True}
    deltas=[abs(m[t][0]-e[t][0]*FOOT_M) for t in times]
    bad=[t for t,d in zip(times,deltas) if d>TOL]
    expected={
        "status":"contradicted" if bad else "unit-expression-consistent",
        "matched_timestamps":len(times),"matches":len(times)-len(bad),
        "max_absolute_deviation_m":str(max(deltas)),"tolerance_m":str(TOL),
        "first_disagreement_utc":bad[0] if bad else None,
        "quality_disagreement_timestamps":[t for t in times if m[t][1]!=e[t][1]][:10],
        "metric_sha256":sources[0]["raw_sha256"],"english_sha256":sources[1]["raw_sha256"],
    }
    if any(claim.get(k)!=v for k,v in expected.items()):
        fail("claimed translation disagrees with independent replay")
    return {"checked_sources":2,"checked_observations":len(times),
            "status":expected["status"],"verified_raw_bytes":True,
            "source_authentication":"not-established"}

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("usage: independent_replay.py path/to/tpp003-live-report.json")
    with Path(sys.argv[1]).open(encoding="utf-8") as f:
        report=json.load(f)
    print(json.dumps(verify(report),indent=2,sort_keys=True))
