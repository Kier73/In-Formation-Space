"""CLT-001: observer-relative transport of exact finite laws.
Native E-CPU constructs and independently audits each minimal machine.
The chart discovery receives only the formed machine tables, not source pairs.
"""
from collections import deque
from itertools import combinations
from random import Random

from mailcpu.intention_formed_fabric import (
    FiniteObserverLaw, form_observer_machine, verify_formed_machine,
)
from mailcpu.weight_space import compile_boolean_gate, ARCHITECTURE, DEEP_ARCHITECTURE

ACTIONS = ("step", "fold", "square")
FIELDS = ("zero", "parity", "upper1", "upper2")


def fixture(width, seed, neural=False, corrupt=False):
    """Generate an observed full transition table from a heterogeneous realizer."""
    if not 1 <= width <= 8:
        raise ValueError("fixture width outside native source bounds")
    states = [(z, nuisance) for z in range(8) for nuisance in range(width)]
    Random(seed).shuffle(states)
    index = {s: i for i, s in enumerate(states)}
    if neural:
        both = compile_boolean_gate("and", architecture=ARCHITECTURE)
        either = compile_boolean_gate("xor", architecture=DEEP_ARCHITECTURE)

    rows, outputs = [], []
    for z, h in states:
        a, b = (z >> 1) & 1, (z >> 2) & 1
        if neural:
            u, v = both.forward((a, b))[0], either.forward((a, b))[0]
            if u not in (0.0, 1.0) or v not in (0.0, 1.0):
                raise ValueError("neural observation not a bit")
            u, v = int(u), int(v)
        else:
            u, v = a & b, a ^ b
        # Nuisance dynamics differ across width and seed; the visible
        # fold has genuine nonlinear Boolean AND and noninvertibility.
        next_z = ((z + (2 if corrupt and z == 2 else 1)) % 8,
                  (z & 1) | (2*u) | (4*v), (z*z + 1) % 8)
        rows.append(tuple(index[(n, (h*(i+1)+z*z+seed+i) % width)]
                          for i, n in enumerate(next_z)))
        outputs.append((int(z == 0), z & 1, a, b))
    law = FiniteObserverLaw(
        tuple(f"r{seed}-{i}" for i in range(len(states))),
        ACTIONS, FIELDS, tuple(rows), tuple(outputs))
    return law, tuple(states)


def match(a, i, b, j):
    """All-future equivalence by reachable product-pair exploration."""
    todo, seen = deque([(i, j)]), set()
    while todo:
        x, y = todo.popleft()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        if a.outputs[x] != b.outputs[y]:
            return False
        todo.extend(zip(a.transitions[x], b.transitions[y]))
    return True


def transport(a, b):
    """Discover a unique bijective observer-machine chart without state anchors."""
    if a.fields != b.fields or a.actions != b.actions:
        raise ValueError("incompatible observation or action alphabet")
    matches = [tuple(j for j in range(len(b.groups)) if match(a, i, b, j))
               for i in range(len(a.groups))]
    if any(len(row) != 1 for row in matches):
        raise ValueError("no unique all-future transport")
    chart = tuple(row[0] for row in matches)
    check_chart(a, b, chart)
    return chart


def check_chart(a, b, chart):
    """Separate local commutation checker; never calls transport or match."""
    if a.fields != b.fields or a.actions != b.actions:
        raise ValueError("incompatible observation or action alphabet")
    if (len(chart) != len(a.groups) or sorted(chart) != list(range(len(b.groups)))):
        raise ValueError("chart not a bijection")
    for i, j in enumerate(chart):
        if (a.outputs[i] != b.outputs[j] or
                tuple(chart[k] for k in a.transitions[i]) != b.transitions[j]):
            raise ValueError("chart does not commute")
    return True


def derived_parity(fine):
    """A new intention formed from an admitted prior law, not raw source states.
    The derived observation is distance-to-marker parity under step.
    """
    if fine.fields != ("zero",):
        raise ValueError("requires marker observer")
    step = fine.actions.index("step")
    values = []
    for start in range(len(fine.groups)):
        state = start
        for d in range(len(fine.groups)):
            if fine.outputs[state] == (1,):
                values.append((d & 1,))
                break
            state = fine.transitions[state][step]
        else:
            raise ValueError("marker unreachable")
    return FiniteObserverLaw(tuple(f"q{i}" for i in range(len(values))),
                             fine.actions, ("parity",), fine.transitions, tuple(values))


def witness_plan(source, old, new):
    """Exact cheapest (unit-cost) subset of offered upper-bit observations.
    Select by separating all pairs whose old state agrees but new state differs.
    """
    offered = ("upper1", "upper2")
    for k in range(len(offered)+1):
        for subset in combinations(offered, k):
            positions = tuple(source.fields.index(f) for f in subset)
            decoder = {}
            for i, row in enumerate(source.observations):
                key = (old.state_groups[i], *(row[p] for p in positions))
                value = new.state_groups[i]
                if key in decoder and decoder[key] != value:
                    break
                decoder[key] = value
            else:
                return subset, decoder
    raise ValueError("no sufficient offered witness")


def power_navigation(transitions, state, word, repetitions):
    """Compose a word map then square it; count table reads, including setup."""
    if not isinstance(repetitions, int) or repetitions < 0:
        raise ValueError("nonnegative repetition coordinate required")
    n = len(transitions)
    if not repetitions or not word:
        return state, 0
    mapping = list(range(n))
    work = 0
    for action in word:
        mapping = [transitions[i][action] for i in mapping]
        work += n
    while repetitions:
        if repetitions & 1:
            state = mapping[state]
            work += 1
        repetitions >>= 1
        if repetitions:
            mapping = [mapping[i] for i in mapping]
            work += n
    return state, work


def raw_cycle(transitions, state, word, repetitions):
    """Independent source oracle: step through word-boundaries until recurrence."""
    seen, history = {}, []
    while repetitions and state not in seen:
        seen[state] = len(history)
        history.append(state)
        for a in word:
            state = transitions[state][a]
        repetitions -= 1
    if not repetitions:
        return state
    start = seen[state]
    return history[start + repetitions % (len(history)-start)]
