"""Qualify original TPP-007 source bytes through SGN-001's actual admission code.

No refit or model selection on the final 480 observations. The archived
NOAA model predictions were retrieved retrospectively; not a live forecast.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spectral-ground-navigation"))
from navigator import fit_spectral, test_report  # noqa: E402

EXPECTED = {
    "water_level": "8a31edbda35209261cbba2cc1fa8d7e3955449fda2d928ac31287028bc74f79d",
    "predictions": "7bb2a2a473aac47a268991816aa7e23f06a12daaa7dbf7922bb60d514ad413f8",
}
SOURCE_SCHEMA = "in-formation-space.tpp007.seven-day-residual-continuity.v1"
TRAIN, VALID, TEST = 720, 480, 480


def archived_series(document):
    """Validate the original provider body and every six-minute source row."""
    if not isinstance(document, dict) or document.get("schema") != SOURCE_SCHEMA:
        raise ValueError("unexpected original report schema")
    if document.get("assessment", {}).get("status") != "complete":
        raise ValueError("archived encounter is not complete")
    sources = {}
    for entry in document.get("documents", []):
        product = entry.get("product")
        if product not in EXPECTED or product in sources:
            raise ValueError("unexpected or repeated product")
        raw = base64.b64decode(entry["raw_body_base64"], validate=True)
        actual = sha256(raw).hexdigest()
        if (actual != EXPECTED[product] or actual != entry["raw_sha256"]
                or len(raw) != int(entry["raw_bytes"])):
            raise ValueError("source bytes differ from pinned evidence")
        if entry.get("start_utc_day") != "20261113" or entry.get("end_utc_day") != "20261119":
            raise ValueError("unexpected time interval")
        obj = json.loads(raw)
        if product == "water_level" and str(obj.get("metadata", {}).get("id")) != "9414290":
            raise ValueError("unexpected physical station")
        rows = obj["data" if product == "water_level" else "predictions"]
        parsed = {}
        for row in rows:
            stamp = datetime.strptime(row["t"], "%Y-%m-%d %H:%M")
            if stamp in parsed:
                raise ValueError("duplicate source timestamp")
            if product == "water_level" and row.get("q") not in ("p", "v"):
                raise ValueError("missing physical quality provenance")
            value = float(row["v"])
            if not np.isfinite(value):
                raise ValueError("nonfinite observation")
            parsed[stamp] = value
        sources[product] = parsed
    if set(sources) != set(EXPECTED):
        raise ValueError("missing source")
    ticks = [datetime(2026, 11, 13) + timedelta(minutes=6*i) for i in range(1680)]
    if any(set(rows) != set(ticks) for rows in sources.values()):
        raise ValueError("archived series has missing or extra times")
    obs = np.asarray([sources["water_level"][t] for t in ticks])
    pred = np.asarray([sources["predictions"][t] for t in ticks])
    if document["assessment"]["source_sha256"] != [EXPECTED["water_level"], EXPECTED["predictions"]]:
        raise ValueError("assessment digest mismatch")
    return np.arange(1, 1681, dtype=float), obs, pred


def qualify(document):
    """Fit only train+validation; disconfirm on untouched later observations."""
    times, obs, pred = archived_series(document)
    result = {
        "schema": "ifs.tpp007-sgn001.chronological-qualification.v1",
        "physical_evidence": EXPECTED,
        "splits": {"train": [1, TRAIN], "validation": [TRAIN+1, TRAIN+VALID],
                   "final_test": [TRAIN+VALID+1, TRAIN+VALID+TEST]},
        "scope": "historical NOAA preliminary observations, not prospective forecast",
        "lanes": {},
    }
    for name, y in (("noaa_residual", obs-pred), ("water_level", obs)):
        ground = fit_spectral(times, y, train_count=TRAIN, validation_count=VALID)
        final = test_report(ground, times, y)
        # SGN-001's validation decision alone is never promoted to final-test authority.
        result["lanes"][name] = {
            "model_selection": ground.receipt(),
            "held_out_test": final,
            "effective_admission": (
                "qualified_for_witnessed_interval" if final["status"] == "corroborated"
                else "refused_after_independent_test"
            ),
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path,
                        help="Archived tpp007-live.json from run 44685425942")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = qualify(json.loads(args.archive.read_text(encoding="utf8")))
    serialized = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf8")
    print(serialized)


if __name__ == "__main__":
    main()
