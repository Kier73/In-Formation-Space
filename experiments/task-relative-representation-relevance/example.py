import json
from task_relative_relevance import build_report

report = build_report(
    states=("low", "high", "dead"),
    actions=("protect-low", "protect-high"),
    initial_distribution={"low": "1/2", "high": "1/2", "dead": 0},
    transitions={
        "protect-low": {"low": "low", "high": "dead", "dead": "dead"},
        "protect-high": {"low": "dead", "high": "high", "dead": "dead"},
    },
    viable_states=("low", "high"),
    representations=(
        {"representation_id": "state-aware", "cells": {"low": "L", "high": "H", "dead": "D"}},
        {"representation_id": "signal-ablated", "cells": {"low": "same", "high": "same", "dead": "D"}},
    ),
    ablations=({"baseline": "state-aware", "ablated": "signal-ablated"},),
    horizon=1,
)
print(json.dumps(report, indent=2, sort_keys=True))
