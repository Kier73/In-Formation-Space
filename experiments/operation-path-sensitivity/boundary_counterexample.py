"""OPS-004 exact boundary counterexample; run directly with Python 3.11+.

Assume A and B request one mutex simultaneously, A acquires first, and there
is no overhead. Work durations are a,b and join j. Inclusive invocation
durations are a and a+b. A fork/join graph therefore fits root time a+b+j
exactly without recording resource order.

Shortening A by d changes BOTH inclusive durations. A fixed-node hypothesis
that subtracts d only from A predicts no gain, although root gain is d.
Shortening both work operations by d predicts only d instead of 2*d.
These are exact model calculations, not measured observations.

Run: python experiments/operation-path-sensitivity/boundary_counterexample.py
Provenance: continuation of OPS-003 at ac8cd789ec6afb71c5dfe62551b859ecbd0402fb.
Next: instrument nested work-only/invocation spans in the same live trial;
do not manufacture invocation spans from samples taken at different boundaries.
"""
import json


def compare(a, b, j, da, db):
    for value in (a, b, j, da, db):
        if type(value) is not int or value < 0:
            raise ValueError("durations and reductions must be nonnegative integers")
    if da > a or db > b:
        raise ValueError("reduction exceeds work duration")
    baseline = a + b + j
    # Hypothesis: change each invocation only by its own work reduction.
    frozen_wait_prediction = max(a - da, a + b - db) + j
    # Structural model: B's wait changes when A's work changes.
    realized = a - da + b - db + j
    return dict(baseline_root=baseline,
                baseline_inclusive_graph=max(a, a + b) + j,
                predicted_gain=baseline - frozen_wait_prediction,
                realized_gain=baseline - realized,
                propagated_inclusive_b=a - da + b - db,
                frozen_inclusive_b=a + b - db)


def verify():
    count = 0
    for a in range(9):
        for b in range(9):
            for da in range(a + 1):
                for db in range(b + 1):
                    r = compare(a, b, 3, da, db)
                    assert r["baseline_root"] == r["baseline_inclusive_graph"]
                    assert r["realized_gain"] == da + db
                    assert r["predicted_gain"] == db
                    assert r["frozen_inclusive_b"] - r["propagated_inclusive_b"] == da
                    count += 1
    for args in [(True, 1, 0, 0, 0), (1, 1, 0, 2, 0), (1, -1, 0, 0, 0)]:
        try:
            compare(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid input accepted")
    return count


if __name__ == "__main__":
    print(json.dumps(dict(verified_cases=verify(),
        a_only=compare(80, 80, 10, 60, 0),
        both=compare(80, 80, 10, 60, 60)), indent=2))
