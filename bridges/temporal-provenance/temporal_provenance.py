"""Clock-domain-safe temporal provenance for portable encounter records.

This module consumes the serialized TemporalFrame shape used by E-CPU's
mailcpu.temporal.TemporalFrame without importing E-CPU. It preserves the
distinction between a local clock coordinate, vector-clock causality,
scheduler order, and wall/calendar time.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.temporal-provenance/0.1"
FRAME_FIELDS = {
    "actor_id",
    "monotonic",
    "wall",
    "causal",
    "scheduler",
    "event_lambda",
    "chronon_phase",
    "chemical_tau",
}
DOMAINS = ("local_counter", "causal", "monotonic", "scheduler")
RELATIONS = {"before", "after", "equal", "concurrent", "incomparable", "unobserved"}


class TemporalProvenanceError(ValueError):
    """A portable temporal observation or comparison is invalid."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise TemporalProvenanceError(f"{label} must be non-empty text without NUL")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TemporalProvenanceError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: object, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TemporalProvenanceError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise TemporalProvenanceError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise TemporalProvenanceError(f"{label} must be >= {minimum}")
    return result


def _exact_fields(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TemporalProvenanceError(f"{label} must contain exactly {sorted(fields)}")
    return value


def validate_temporal_frame(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Validate E-CPU-compatible TemporalFrame.to_dict() fields without importing E-CPU."""
    frame = _exact_fields(frame, FRAME_FIELDS, "temporal_frame")
    actor = _text(frame["actor_id"], "temporal_frame.actor_id")
    normalized: dict[str, Any] = {"actor_id": actor}

    monotonic = frame["monotonic"]
    if monotonic is None:
        normalized["monotonic"] = None
    else:
        monotonic = _exact_fields(
            monotonic, {"actor_id", "segment", "elapsed_ns"}, "monotonic"
        )
        if _text(monotonic["actor_id"], "monotonic.actor_id") != actor:
            raise TemporalProvenanceError("monotonic reading belongs to a different actor")
        normalized["monotonic"] = {
            "actor_id": actor,
            "segment": _integer(monotonic["segment"], "monotonic.segment"),
            "elapsed_ns": _integer(monotonic["elapsed_ns"], "monotonic.elapsed_ns"),
        }

    wall = frame["wall"]
    if wall is None:
        normalized["wall"] = None
    else:
        wall = _exact_fields(
            wall, {"actor_id", "utc_ns", "sample_index"}, "wall"
        )
        if _text(wall["actor_id"], "wall.actor_id") != actor:
            raise TemporalProvenanceError("wall reading belongs to a different actor")
        utc_ns = wall["utc_ns"]
        if isinstance(utc_ns, bool) or not isinstance(utc_ns, int):
            raise TemporalProvenanceError("wall.utc_ns must be an integer")
        normalized["wall"] = {
            "actor_id": actor,
            "utc_ns": utc_ns,
            "sample_index": _integer(wall["sample_index"], "wall.sample_index"),
        }

    causal = frame["causal"]
    if causal is None:
        normalized["causal"] = None
    else:
        causal = _exact_fields(
            causal, {"actor_id", "lamport", "vector"}, "causal"
        )
        if _text(causal["actor_id"], "causal.actor_id") != actor:
            raise TemporalProvenanceError("causal stamp belongs to a different actor")
        lamport = _integer(causal["lamport"], "causal.lamport")
        vector = causal["vector"]
        if not isinstance(vector, Mapping) or not vector:
            raise TemporalProvenanceError("causal.vector must be a non-empty actor-counter map")
        normalized_vector: dict[str, int] = {}
        for vector_actor, counter in vector.items():
            key = _text(vector_actor, "causal.vector actor")
            if key in normalized_vector:
                raise TemporalProvenanceError("causal.vector actor IDs must be unique")
            normalized_vector[key] = _integer(
                counter, f"causal.vector[{key!r}]"
            )
            if normalized_vector[key] > lamport:
                raise TemporalProvenanceError("causal vector counter exceeds Lamport scalar")
        if actor not in normalized_vector:
            raise TemporalProvenanceError("causal.vector must include its own actor")
        normalized["causal"] = {
            "actor_id": actor,
            "lamport": lamport,
            "vector": dict(sorted(normalized_vector.items())),
        }

    scheduler = frame["scheduler"]
    if scheduler is None:
        normalized["scheduler"] = None
    else:
        scheduler = _exact_fields(
            scheduler, {"scheduler_id", "tick"}, "scheduler"
        )
        normalized["scheduler"] = {
            "scheduler_id": _text(scheduler["scheduler_id"], "scheduler.scheduler_id"),
            "tick": _integer(scheduler["tick"], "scheduler.tick"),
        }

    event_lambda = frame["event_lambda"]
    normalized["event_lambda"] = (
        None if event_lambda is None
        else _integer(event_lambda, "event_lambda")
    )

    phase = frame["chronon_phase"]
    if phase is None:
        normalized["chronon_phase"] = None
    else:
        if not isinstance(phase, (list, tuple)) or len(phase) != 2:
            raise TemporalProvenanceError("chronon_phase must be a real/imaginary pair")
        real = _number(phase[0], "chronon_phase[0]")
        imaginary = _number(phase[1], "chronon_phase[1]")
        if not math.isclose(math.hypot(real, imaginary), 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise TemporalProvenanceError("chronon_phase must lie on the unit circle")
        normalized["chronon_phase"] = [real, imaginary]

    chemical_tau = frame["chemical_tau"]
    normalized["chemical_tau"] = (
        None if chemical_tau is None
        else _number(chemical_tau, "chemical_tau", minimum=0.0)
    )
    return normalized


def validate_observation(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one portable event observation with zero or more typed clock witnesses."""
    required = {"format", "event_id", "local_counter", "temporal_frame"}
    record = _exact_fields(record, required, "temporal observation")
    if record["format"] != FORMAT:
        raise TemporalProvenanceError(f"unsupported format: {record['format']!r}")
    event_id = _text(record["event_id"], "event_id")

    local_counter = record["local_counter"]
    if local_counter is None:
        normalized_counter = None
    else:
        local_counter = _exact_fields(
            local_counter, {"clock_id", "coordinate", "unit"}, "local_counter"
        )
        normalized_counter = {
            "clock_id": _text(local_counter["clock_id"], "local_counter.clock_id"),
            "coordinate": _integer(local_counter["coordinate"], "local_counter.coordinate"),
            "unit": _text(local_counter["unit"], "local_counter.unit"),
        }

    frame = record["temporal_frame"]
    normalized_frame = None if frame is None else validate_temporal_frame(frame)
    if normalized_counter is None and normalized_frame is None:
        raise TemporalProvenanceError("observation must carry a local counter or temporal frame")

    return {
        "format": FORMAT,
        "event_id": event_id,
        "local_counter": normalized_counter,
        "temporal_frame": normalized_frame,
    }


def attach_to_encounter_envelope(
    envelope: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a copied encounter envelope with one namespaced temporal extension."""
    if not isinstance(envelope, Mapping):
        raise TypeError("envelope must be a mapping")
    if envelope.get("format") != "in-formation.encounter/0.1":
        raise TemporalProvenanceError("unsupported encounter envelope format")
    envelope_id = _text(envelope.get("id"), "encounter.id")
    normalized = validate_observation(observation)
    if normalized["event_id"] != envelope_id:
        raise TemporalProvenanceError("temporal event_id must match the encounter id")
    extensions = envelope.get("extensions", {})
    if not isinstance(extensions, Mapping):
        raise TemporalProvenanceError("encounter.extensions must be an object")
    updated_extensions = copy.deepcopy(dict(extensions))
    if FORMAT in updated_extensions:
        raise TemporalProvenanceError("encounter already contains this temporal extension")
    updated_extensions[FORMAT] = normalized
    updated = copy.deepcopy(dict(envelope))
    updated["extensions"] = updated_extensions
    return updated


def extract_from_encounter_envelope(
    envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and return the namespaced temporal observation from an encounter."""
    if not isinstance(envelope, Mapping):
        raise TypeError("envelope must be a mapping")
    if envelope.get("format") != "in-formation.encounter/0.1":
        raise TemporalProvenanceError("unsupported encounter envelope format")
    envelope_id = _text(envelope.get("id"), "encounter.id")
    extensions = envelope.get("extensions")
    if not isinstance(extensions, Mapping) or FORMAT not in extensions:
        raise TemporalProvenanceError("encounter has no temporal-provenance extension")
    normalized = validate_observation(extensions[FORMAT])
    if normalized["event_id"] != envelope_id:
        raise TemporalProvenanceError("temporal event_id does not match encounter id")
    return normalized


def _ordered(left: int, right: int) -> str:
    if left < right:
        return "before"
    if left > right:
        return "after"
    return "equal"


def _vector_relation(left: Mapping[str, int], right: Mapping[str, int]) -> str:
    actors = set(left) | set(right)
    less = any(left.get(actor, 0) < right.get(actor, 0) for actor in actors)
    greater = any(left.get(actor, 0) > right.get(actor, 0) for actor in actors)
    if less and greater:
        return "concurrent"
    if less:
        return "before"
    if greater:
        return "after"
    return "equal"


def _comparison(status: str, witness: str) -> dict[str, str]:
    return {"status": status, "witness": witness}


def compare_observations(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare two observations separately in each clock domain.

    A domain's result is never inferred from another domain. Wall/calendar
    timestamps are retained but not used to establish event or causal order.
    """
    left = validate_observation(left)
    right = validate_observation(right)
    if left["event_id"] == right["event_id"]:
        raise TemporalProvenanceError("cannot compare an event with itself")

    result: dict[str, Any] = {
        "left_event_id": left["event_id"],
        "right_event_id": right["event_id"],
        "relations": {},
        "cross_domain_consistency": "not_assessed",
    }

    lc, rc = left["local_counter"], right["local_counter"]
    if lc is None or rc is None:
        result["relations"]["local_counter"] = _comparison(
            "unobserved", "one or both events lack a local-counter witness"
        )
    elif (lc["clock_id"], lc["unit"]) != (rc["clock_id"], rc["unit"]):
        result["relations"]["local_counter"] = _comparison(
            "incomparable",
            "clock IDs or units differ; no calibration or conversion is recorded",
        )
    else:
        result["relations"]["local_counter"] = _comparison(
            _ordered(lc["coordinate"], rc["coordinate"]),
            f"same local clock {lc['clock_id']!r} and unit {lc['unit']!r}",
        )

    lf, rf = left["temporal_frame"], right["temporal_frame"]
    if lf is None or rf is None or lf["causal"] is None or rf["causal"] is None:
        result["relations"]["causal"] = _comparison(
            "unobserved", "one or both events lack a vector-clock causal stamp"
        )
    else:
        result["relations"]["causal"] = _comparison(
            _vector_relation(lf["causal"]["vector"], rf["causal"]["vector"]),
            "componentwise vector-clock comparison",
        )

    if lf is None or rf is None or lf["monotonic"] is None or rf["monotonic"] is None:
        result["relations"]["monotonic"] = _comparison(
            "unobserved", "one or both events lack a monotonic reading"
        )
    else:
        lm, rm = lf["monotonic"], rf["monotonic"]
        if (lm["actor_id"], lm["segment"]) != (rm["actor_id"], rm["segment"]):
            result["relations"]["monotonic"] = _comparison(
                "incomparable",
                "monotonic readings belong to different actors or restore segments",
            )
        else:
            result["relations"]["monotonic"] = _comparison(
                _ordered(lm["elapsed_ns"], rm["elapsed_ns"]),
                f"same monotonic actor {lm['actor_id']!r}, segment {lm['segment']}",
            )

    if lf is None or rf is None or lf["scheduler"] is None or rf["scheduler"] is None:
        result["relations"]["scheduler"] = _comparison(
            "unobserved", "one or both events lack a scheduler reading"
        )
    else:
        ls, rs = lf["scheduler"], rf["scheduler"]
        if ls["scheduler_id"] != rs["scheduler_id"]:
            result["relations"]["scheduler"] = _comparison(
                "incomparable", "scheduler IDs differ"
            )
        else:
            result["relations"]["scheduler"] = _comparison(
                _ordered(ls["tick"], rs["tick"]),
                f"same scheduler {ls['scheduler_id']!r}",
            )

    result["relations"]["wall"] = _comparison(
        "not_used",
        "wall/calendar readings are not causal witnesses and are not compared across actors",
    )

    causal_status = result["relations"]["causal"]["status"]
    monotonic_status = result["relations"]["monotonic"]["status"]
    if (
        causal_status in {"before", "after"}
        and monotonic_status in {"before", "after"}
        and causal_status != monotonic_status
    ):
        result["cross_domain_consistency"] = "local_causal_disagreement"
    return result


def _cycle_and_components(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
) -> tuple[bool, list[list[str]]]:
    """Detect directed cycles and report weakly connected order components.

    Components are intentionally not joined by a chosen linear extension:
    nodes in separate components have no ordering witness in this domain.
    """
    outgoing = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    undirected = {node: set() for node in nodes}
    for source, target in edges:
        if target not in outgoing[source]:
            outgoing[source].add(target)
            indegree[target] += 1
            undirected[source].add(target)
            undirected[target].add(source)

    ready = sorted(node for node in nodes if indegree[node] == 0)
    visited = 0
    while ready:
        node = ready.pop(0)
        visited += 1
        for target in sorted(outgoing[node]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()

    unseen = set(nodes)
    components: list[list[str]] = []
    while unseen:
        root = min(unseen)
        stack = [root]
        unseen.remove(root)
        component = []
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in sorted(undirected[node], reverse=True):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return visited != len(nodes), sorted(components, key=lambda item: item[0])


def analyze_observations(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build independent partial orders for local counters, causality, monotonic and scheduler clocks."""
    if not isinstance(records, (list, tuple)):
        raise TypeError("records must be a sequence")
    normalized = sorted(
        (validate_observation(record) for record in records),
        key=lambda record: record["event_id"],
    )
    event_ids = [record["event_id"] for record in normalized]
    if len(set(event_ids)) != len(event_ids):
        raise TemporalProvenanceError("event IDs must be unique within an analysis")

    comparisons = []
    domain_pairs: dict[str, list[dict[str, str]]] = {domain: [] for domain in DOMAINS}
    for index, left in enumerate(normalized):
        for right in normalized[index + 1:]:
            comparison = compare_observations(left, right)
            comparisons.append(comparison)
            for domain in DOMAINS:
                domain_pairs[domain].append({
                    "left_event_id": comparison["left_event_id"],
                    "right_event_id": comparison["right_event_id"],
                    "status": comparison["relations"][domain]["status"],
                })

    domains: dict[str, Any] = {}
    for domain in DOMAINS:
        edges: list[tuple[str, str]] = []
        for pair in domain_pairs[domain]:
            if pair["status"] == "before":
                edges.append((pair["left_event_id"], pair["right_event_id"]))
            elif pair["status"] == "after":
                edges.append((pair["right_event_id"], pair["left_event_id"]))
        has_cycle, components = _cycle_and_components(event_ids, edges)
        outgoing = {source for source, _ in edges}
        domains[domain] = {
            "edge_count": len(set(edges)),
            "edges": [
                {"before": source, "after": target}
                for source, target in sorted(set(edges))
            ],
            "has_cycle": has_cycle,
            "weakly_connected_components": components,
            "maximal_event_ids": sorted(set(event_ids) - outgoing),
            "pair_status_counts": {
                status: sum(pair["status"] == status for pair in domain_pairs[domain])
                for status in ("before", "after", "equal", "concurrent", "incomparable", "unobserved")
            },
        }

    return {
        "format": "in-formation.temporal-provenance-analysis/0.1",
        "observation_count": len(normalized),
        "event_ids": sorted(event_ids),
        "domains": domains,
        "pairwise_comparisons": comparisons,
        "global_total_order": None,
        "global_order_boundary": (
            "Clock domains are analyzed independently. No global order is inferred "
            "from wall timestamps, unrelated local counters, or missing causal stamps."
        ),
        "cross_domain_disagreements": [
            {
                "left_event_id": item["left_event_id"],
                "right_event_id": item["right_event_id"],
                "status": item["cross_domain_consistency"],
            }
            for item in comparisons
            if item["cross_domain_consistency"] != "not_assessed"
        ],
    }


def load_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping) and set(payload) == {"observations"}:
        if not isinstance(payload["observations"], list):
            raise TemporalProvenanceError("observations must be a JSON array")
        return payload["observations"]
    raise TemporalProvenanceError("input must be an array or an object with observations")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze clock-domain-safe temporal provenance observations."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = analyze_observations(load_records(args.input))
    except (OSError, json.JSONDecodeError, TemporalProvenanceError, TypeError) as exc:
        parser.exit(1, f"temporal provenance analysis failed: {exc}\n")
    serialized = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
