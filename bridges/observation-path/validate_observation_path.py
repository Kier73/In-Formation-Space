#!/usr/bin/env python3
"""Validate an observation-path JSON record against schema and lifecycle rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

from observation_path import _ALLOWED_NEXT, _TERMINAL


def validate_path_record(document: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError(
            "jsonschema is required for this CLI; install jsonschema>=4,<5"
        ) from exc

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(instance=document, schema=schema)

    events = document["events"]
    stages = [event["stage"] for event in events]
    if stages[0] != "planned":
        raise ValueError("first observation-path event must be planned")

    for current, following in zip(stages, stages[1:]):
        if following not in _ALLOWED_NEXT.get(current, set()):
            raise ValueError(f"invalid lifecycle transition: {current} -> {following}")

    intent = document.get("intent", {})
    authority_required = intent.get("authority_required", False)
    application_required = intent.get("application_required", False)
    sender_ack_required = intent.get("sender_ack_required", False)
    if authority_required and "returned" in stages:
        returned_index = stages.index("returned")
        authority_indices = [
            index for index, stage in enumerate(stages)
            if stage in {"evidence_authorized", "evidence_refused"}
        ]
        if not authority_indices or authority_indices[0] <= returned_index:
            raise ValueError("authority_required path must record evidence_authorized or evidence_refused after returned")
        if "interpreted" in stages and stages.index("interpreted") <= authority_indices[0]:
            raise ValueError("interpretation must follow evidence authorization")
    if application_required and "interpreted" in stages:
        if "applied" not in stages or stages.index("applied") <= stages.index("evidence_authorized"):
            raise ValueError("application_required path must record applied after evidence_authorized and before interpretation")
        if stages.index("interpreted") <= stages.index("applied"):
            raise ValueError("interpretation must follow receiver application")
    if sender_ack_required and "interpreted" in stages:
        if "sender_acknowledged" not in stages:
            raise ValueError("sender_ack_required path must record sender_acknowledged before interpretation")
        if "applied" not in stages or stages.index("sender_acknowledged") <= stages.index("applied"):
            raise ValueError("sender acknowledgement must follow receiver application")
        if stages.index("interpreted") <= stages.index("sender_acknowledged"):
            raise ValueError("interpretation must follow sender acknowledgement")

    final_stage = stages[-1]
    if document["status"] != final_stage:
        raise ValueError("record status must match the final event stage")
    if document["terminal"] != (final_stage in _TERMINAL):
        raise ValueError("terminal flag does not match the final lifecycle stage")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).with_name("observation-path.schema.json"),
    )
    args = parser.parse_args(argv)

    try:
        document = json.loads(args.record.read_text(encoding="utf-8"))
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        validate_path_record(document, schema)
    except Exception as exc:
        print(f"[INVALID] {exc}", file=sys.stderr)
        return 1

    print(f"[VALID] {args.record} conforms to the observation-path structure and lifecycle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
