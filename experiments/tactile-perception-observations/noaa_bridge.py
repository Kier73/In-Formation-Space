"""TPP-003: read-only public observation ingestion and unit-expression comparison.

A real HTTPS source may supply physical sensor observations, but this module
only validates provider-format evidence. It does not authenticate instruments,
prove measurement accuracy, issue commands or claim independent calibration.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
import urllib.parse
import urllib.request

SCHEMA = "in-formation-space.tpp003.noaa-water-level.v1"
HOST = "api.tidesandcurrents.noaa.gov"
PATH = "/api/prod/datagetter"
STATION = "9414290"  # NOAA CO-OPS, San Francisco (public US instrument)
DATUM = "MLLW"
FOOT_M = Decimal("0.3048")
TOLERANCE_M = Decimal("0.001")
MAX_RESPONSE_BYTES = 512_000


def request_url(units, station=STATION, date="recent"):
    """Only the NOAA endpoint is addressable; user input cannot supply a URL."""
    if units not in ("metric", "english") or not re.fullmatch(r"[0-9]{7}", station):
        raise ValueError("invalid unit or station")
    if date not in ("latest", "recent"):
        raise ValueError("unsupported bounded date window")
    query = urllib.parse.urlencode({
        "application": "InFormationSpace_TPP003", "date": date, "datum": DATUM,
        "format": "json", "product": "water_level", "station": station,
        "time_zone": "gmt", "units": units,
    })
    return "https://" + HOST + PATH + "?" + query


def fetch(units, station=STATION, date="recent"):
    url = request_url(units, station, date)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "InFormationSpace-TPP003/1.0",
    })
    # urllib uses Python's default certificate verification for HTTPS.
    with urllib.request.urlopen(req, timeout=15) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != HOST or final.path != PATH:
            raise ValueError("unapproved redirect")
        if response.status != 200:
            raise ValueError("unexpected HTTP status")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response too large")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    return decode(raw, units, station, url, retrieved_at)


def _number(value, *, optional=False):
    if optional and value in (None, ""):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"-?(?:[0-9]+)(?:\.[0-9]+)?", value):
        raise ValueError("invalid numeric field")
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not d.is_finite():
        raise ValueError("nonfinite decimal")
    return d


def _time(raw):
    if not isinstance(raw, str):
        raise ValueError("timestamp not a string")
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("unsupported UTC timestamp") from exc
    return dt.isoformat()


def decode(raw, units, station, url, retrieved_at):
    """Preserve byte provenance, timestamps, datum, measurement flags and status."""
    if units not in ("metric", "english") or not re.fullmatch(r"[0-9]{7}", station):
        raise ValueError("invalid observation contract")
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("invalid response bytes")
    provenance = {
        "schema": SCHEMA, "scope": "provider-data-not-independent-physical-verification",
        "source": url, "retrieved_utc": retrieved_at,
        "raw_sha256": sha256(raw).hexdigest(), "raw_bytes": len(raw),
        "raw_body_base64": base64.b64encode(raw).decode("ascii"),
        "station": station, "units": "m" if units == "metric" else "ft",
        "datum": DATUM, "time_zone": "UTC", "product": "water_level",
    }
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {**provenance, "status": "invalid", "reason": "unparseable-json", "observations": []}
    if not isinstance(payload, dict):
        return {**provenance, "status": "invalid", "reason": "unexpected-top-level", "observations": []}
    if "error" in payload:
        # NOAA may provide an error message with HTTP 200; preserve non-observation.
        return {**provenance, "status": "unavailable", "reason": "provider-error",
                "provider_error": payload["error"], "observations": []}
    meta = payload.get("metadata")
    if not isinstance(meta, dict) or str(meta.get("id")) != station:
        return {**provenance, "status": "invalid", "reason": "station-mismatch", "observations": []}
    records = payload.get("data")
    if not isinstance(records, list):
        return {**provenance, "status": "invalid", "reason": "missing-data-array", "observations": []}
    if not records:
        return {**provenance, "status": "unavailable", "reason": "no-observations", "observations": []}
    results = []
    seen = set()
    for entry in records:
        if not isinstance(entry, dict):
            return {**provenance, "status": "invalid", "reason": "invalid-row", "observations": []}
        try:
            timestamp = _time(entry.get("t"))
            if timestamp in seen:
                raise ValueError("duplicate time")
            seen.add(timestamp)
            value = _number(entry.get("v"), optional=True)
            sigma = _number(entry.get("s"), optional=True)
            if sigma is not None and sigma < 0:
                raise ValueError("negative sigma")
            flags = entry.get("f")
            quality = entry.get("q")
            if not isinstance(flags, str) or quality not in ("p", "v"):
                raise ValueError("unknown provider flags or quality")
        except ValueError:
            return {**provenance, "status": "invalid", "reason": "invalid-row-value", "observations": []}
        results.append({
            "timestamp_utc": timestamp, "value": str(value) if value is not None else None,
            "sigma": str(sigma) if sigma is not None else None,
            "flags_raw": flags, "provider_quality": quality,
            "status": "missing" if value is None else ("provider-verified" if quality == "v" else "preliminary"),
        })
    return {**provenance, "status": "observed", "reason": None,
            "station_name": str(meta.get("name", "")), "observations": results}


def compare_expressions(metric, english):
    """Compare matched timestamps with an explicit rounding tolerance.

    Agreement shows consistency between two *provider expressions*, not
    independent reproduction of the sensor or common physical accuracy.
    """
    if any(doc.get("status") != "observed" for doc in (metric, english)):
        return {"status": "undetermined", "reason": "source-unavailable-or-invalid", "matches": 0}
    for key in ("station", "datum", "time_zone", "product"):
        if metric.get(key) != english.get(key):
            return {"status": "incompatible-context", "reason": key, "matches": 0}
    if metric.get("units") != "m" or english.get("units") != "ft":
        return {"status": "incompatible-context", "reason": "units", "matches": 0}
    m = {v["timestamp_utc"]: v for v in metric["observations"] if v["status"] != "missing"}
    e = {v["timestamp_utc"]: v for v in english["observations"] if v["status"] != "missing"}
    times = sorted(m.keys() & e.keys())
    if not times:
        return {"status": "undetermined", "reason": "no-matched-observations", "matches": 0}
    deviations = [abs(Decimal(m[t]["value"]) - FOOT_M*Decimal(e[t]["value"])) for t in times]
    discrepant = [t for t, d in zip(times, deviations) if d > TOLERANCE_M]
    quality_changes = [t for t in times if m[t]["provider_quality"] != e[t]["provider_quality"]]
    return {
        "status": "contradicted" if discrepant else "unit-expression-consistent",
        "scope": "matched-noaa-observations-not-independent-sensor-evidence",
        "matched_timestamps": len(times), "matches": len(times)-len(discrepant),
        "max_absolute_deviation_m": str(max(deviations)),
        "tolerance_m": str(TOLERANCE_M),
        "first_disagreement_utc": discrepant[0] if discrepant else None,
        "quality_disagreement_timestamps": quality_changes[:10],
        "metric_sha256": metric["raw_sha256"], "english_sha256": english["raw_sha256"],
    }


def live(station=STATION, date="recent"):
    """One read-only live attempt; failures are recorded, never converted to zero."""
    docs = []
    for units in ("metric", "english"):
        url = request_url(units, station, date)
        try:
            docs.append(fetch(units, station, date))
        except (OSError, ValueError, TimeoutError) as exc:
            docs.append({"schema": SCHEMA, "scope": "remote-fetch-unavailable",
                         "status": "unavailable", "source": url,
                         "reason": type(exc).__name__, "observations": []})
    return {"experiment": "TPP-003", "source": "NOAA CO-OPS public water-level service",
            "observations": docs, "cross_unit_relation": compare_expressions(*docs)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--date", choices=("latest", "recent"), default="recent")
    parser.add_argument("--station", default=STATION)
    args = parser.parse_args()
    if not args.live:
        parser.error("live network retrieval must be explicitly requested with --live")
    print(json.dumps(live(args.station, args.date), indent=2, sort_keys=True))
