"""Export the actual native CLT-001 marker quotient, indexed by distance to marker."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("upstream-clt") / "experiments" / "computational_law_transport"))
from clt import fixture, form_observer_machine, verify_formed_machine

law, _ = fixture(8, 17)
machine = form_observer_machine(law, ("zero",))
assert verify_formed_machine(law, machine)
assert len(machine.groups) == 8
step = machine.actions.index("step")
chart = {}
for i in range(len(machine.groups)):
    s = i
    for distance in range(8):
        if machine.outputs[s] == (1,):
            chart[i] = (-distance) % 8
            break
        s = machine.transitions[s][step]
    else:
        raise AssertionError("marker unreachable")
assert sorted(chart.values()) == list(range(8))
rows = [None] * 8
for i, z in chart.items():
    rows[z] = [chart[j] for j in machine.transitions[i]]
Path("native-prior.json").write_text(json.dumps([v for row in rows for v in row]), encoding="utf-8")
