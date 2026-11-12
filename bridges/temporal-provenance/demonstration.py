"""Generate the split-clock relay and vector-clock examples for temporal provenance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from temporal_provenance import FORMAT, analyze_observations


def _frame(actor: str, vector: dict[str, int]) -> dict[str, Any]:
    return {
        "actor_id": actor,
        "monotonic": None,
        "wall": None,
        "causal": {
            "actor_id": actor,
            "lamport": max(vector.values()),
            "vector": vector,
        },
        "scheduler": None,
        "event_lambda": None,
        "chronon_phase": None,
        "chemical_tau": None,
    }


def _counter(event_id: str, clock_id: str, coordinate: int) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "event_id": event_id,
        "local_counter": {
            "clock_id": clock_id,
            "coordinate": coordinate,
            "unit": "tick",
        },
        "temporal_frame": None,
    }


def _causal_event(event_id: str, actor: str, vector: dict[str, int]) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "event_id": event_id,
        "local_counter": None,
        "temporal_frame": _frame(actor, vector),
    }


def build_demonstration() -> dict[str, Any]:
    relay_records = [
        _counter("C100-received", "controller:C", 100),
        _counter("C101-accepted", "controller:C", 101),
        _counter("C105-worker-start", "controller:C", 105),
        _counter("C108-worker-complete", "controller:C", 108),
        _counter("S8-idle", "sensor:S", 8),
        _counter("S11-warm", "sensor:S", 11),
        _counter("S14-idle", "sensor:S", 14),
    ]
    relay_report = analyze_observations(relay_records)

    causal_records = [
        _causal_event("controller-send", "controller", {"controller": 1}),
        _causal_event(
            "receiver-accept",
            "receiver",
            {"controller": 1, "receiver": 1},
        ),
        _causal_event("independent-sensor-sample", "sensor", {"sensor": 1}),
    ]
    causal_report = analyze_observations(causal_records)

    return {
        "format": "in-formation.temporal-provenance-demonstration/0.1",
        "schema": "in-formation.temporal-provenance-demonstration/0.1",
        "source_material": {
            "cold_start_packet": "experiments/cold-start-continuity/packet.md",
            "ecpu_repository": "https://github.com/Kier73/E-CPU",
            "ecpu_revision": "800f94f83ffd6f527ed093c8d1c1e93e153c34f6",
            "vgi_repository": "https://github.com/Kier73/Virtual-Ground-Interpreter",
            "vgi_revision": "cedcc4540a9d75228cf83aaf21e1ba960fe8a555",
            "reuse": "The temporal-frame wire shape is compatible with E-CPU TemporalFrame.to_dict(); no E-CPU or VGI code is copied into this bridge.",
        },
        "relay_packet_case": {
            "records": relay_records,
            "analysis": relay_report,
            "interpretation": (
                "The controller and sensor streams each retain their own local order. "
                "All 12 cross-stream pairs are incomparable under the supplied clock IDs. "
                "No causal stamps are present, so all 21 causal comparisons are unobserved, "
                "not concurrent. The two local maximal events are both retained; there is "
                "no global total order."
            ),
        },
        "instrumented_causal_case": {
            "records": causal_records,
            "analysis": causal_report,
            "interpretation": (
                "A receiver vector stamp that includes the controller's counter is after "
                "the controller send. The independent sensor stamp is concurrent with both. "
                "This is synthetic protocol evidence showing what causal stamps can add; "
                "it is not retroactive evidence about the split-clock relay packet."
            ),
        },
        "boundaries": [
            "Local counters are comparable only when clock ID and unit match.",
            "Monotonic readings are comparable only for the same actor and restore segment.",
            "Scheduler ticks are comparable only for the same scheduler ID.",
            "Vector-clock concurrency is reported only when both vector stamps were recorded.",
            "Wall/calendar timestamps are retained but never used here as causal order.",
            "Correspondence, correlation, and physical causation are not inferred by this analyzer.",
            "Clock IDs and actor IDs are provenance labels, not authenticated identities.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate clock-domain-safe temporal provenance examples."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    example = build_demonstration()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(example, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    relay = example["relay_packet_case"]["analysis"]
    print(json.dumps({
        "output": str(args.output),
        "relay_observations": relay["observation_count"],
        "cross_stream_incomparables": relay["domains"]["local_counter"]["pair_status_counts"]["incomparable"],
        "missing_causal_stamps": relay["domains"]["causal"]["pair_status_counts"]["unobserved"],
        "global_total_order": relay["global_total_order"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
