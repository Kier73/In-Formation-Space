"""RIV-003: synthesize a compact memory controller for the RIV-002 example."""
import json
from bounded_memory_relevance import build_report

report = build_report(
    states=("a", "b", "after-a", "after-b", "dead"),
    actions=("prepare", "protect-a", "protect-b"),
    initial_distribution={"a": "1/2", "b": "1/2", "after-a": 0, "after-b": 0, "dead": 0},
    transitions={
        "prepare": {"a": "after-a", "b": "after-b", "after-a": "dead", "after-b": "dead", "dead": "dead"},
        "protect-a": {"a": "dead", "b": "dead", "after-a": "after-a", "after-b": "dead", "dead": "dead"},
        "protect-b": {"a": "dead", "b": "dead", "after-a": "dead", "after-b": "after-b", "dead": "dead"},
    },
    viable_states=("a", "b", "after-a", "after-b"),
    representations=(
        {"representation_id": "fine", "cells": {"a": "A", "b": "B", "after-a": "C", "after-b": "C", "dead": "C"}},
        {"representation_id": "coarse", "cells": {"a": "A", "b": "A", "after-a": "C", "after-b": "C", "dead": "C"}},
    ),
    ablations=({"baseline": "fine", "ablated": "coarse"},),
    horizon=2,
    memory_sizes=(1, 2),
)
print(json.dumps(report, indent=2, sort_keys=True))
