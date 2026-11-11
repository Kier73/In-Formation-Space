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
