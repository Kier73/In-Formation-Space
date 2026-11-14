# GCI-003 — Intention-relative observation sufficiency

**Research question:** Given an evidence-admitted Ground, can an observer prove that its currently available information suffices for a particular intention? When not, can it request the lowest-cost permitted additional observation and refuse unsupported answers?

GCI-003 reuses [GCI-002's verified eight-state closed VGI Ground](../gci002/README.md) and the original CAG-004 signed mathematical intention, with no new publisher authority. The mathematical source law is x(t+1)=(5x(t)+1) mod 65536 and y(t)=(3x(t)+11) mod 65536. The finite Ground uses its exact reduction modulo eight.

## Intention-relative factoring

For states s and t, initial observation o, additional measured feature set Q, and requested result T at logical horizon h, the sufficiency requirement is

    o(s)=o(t) AND every q in Q has q(s)=q(t)
       IMPLIES T_h(s)=T_h(t).

The test is scoped to all states in the *current observed fiber*, not an unrestricted universe. Exact finite enumeration of eight Ground states is feasible. It distinguishes the information needed to answer a particular intention from stronger one-step transition congruence.

Initial observation: threshold(x)=1 when x>=4, else 0. The blind planner receives only that bit and a receiver commitment, not the selected private coordinate.

Receiver-owned candidate measurements, with declared *symbolic* costs, are parity (cost 1), bit1 (cost 1), and low2 (cost 2). These are software capabilities, not real latency, bandwidth or energy measurements. The planner examines all subsets of the small permitted catalogue and chooses minimum (total declared cost, number of queries, feature names) that makes the intended result constant in every remaining observation fiber.

Time navigation uses independent O(log h) modular-affine composition, including logical offsets around 10^15. It never iterates 10^15 transitions.

## Four distinct intentions

| Intention | Permitted additional observations | Expected determination |
| --- | --- | --- |
| Future threshold after 10^15+136 steps | None | READY: the eight-state orbit repeats, so no measurement is required |
| Future projected-output parity after 10^15+137 steps | Parity, low2 | MEASURE parity at symbolic cost 1 |
| Threshold after one transition | Parity, bit1, low2 | MEASURE low2 at symbolic cost 2 |
| Full future projected output modulo eight after 10^15+137 steps | Parity only | REFUSE: no authorized feature set determines the complete result |

The same initial threshold can be inadequate to model every next transition yet sufficient for a particular long-horizon intention. The restricted case retains a concrete pair of states that remain indistinguishable even after every authorized measurement, but have different intended results.

## Hosted roles and provenance

1. The previously verified GCI-002 E-CPU/VGI evidence-admitted eight-state Ground and original CAG-004 signed source remain the foundation.
2. A receiver-owned E-CPU host chooses a logical source phase in [0,7] and produces two *different artifacts*: a public threshold observation with salted commitment, and a private phase witness.
3. A separately scheduled planner receives the public artifact, signed source and certified Ground, **never** the private phase. It proves sufficiency, selects licensed measurements, or refuses.
4. A controlled receiver host receives the private phase and validates the plan against its own allowed observation capabilities. It runs the pinned E-CPU navigator and returns only the requested feature values, not the phase or full state.
5. A blind resolver receives the public observation, plan and measured features, but **never** the private phase. It issues a result only when every remaining candidate implies the same output.
6. A final independent auditor receives the private witness only after resolution, re-verifies GCI-001 and GCI-002, checks exact measurement authorization and Ground bindings, and compares each resolved value against the held source phase.

The branch workflow is in the same CAG-004 / GCI-001 / GCI-002 pipeline; on main it verifies exact GitHub workflow attestations for every upstream artifact before consumption and attests the resulting reports. The main branch is **not branch-protected**; workflow-attested origin is not independent administrative trust.

The deliberate input separation is **not** cryptographic secrecy from repository maintainers, GitHub administrators, workflow artifact readers, or anyone familiar with the experiment's source. The local phase is a mathematically sampled state, not a physical sensor reading or authenticated external measurement. It is hidden only from the declared planner/resolver inputs.

## Tests and reproducing

Run the focused state-complete tests:

    python -m pip install 'cryptography>=43,<47'
    python -m unittest discover -s experiments/cross-ground-continuity/gci003 -p 'test_intention_model.py' -v

The complete hosted proof follows [.github/workflows/cag004-topology-neutral.yml](../../../.github/workflows/cag004-topology-neutral.yml). A successful workflow must be checked before calling the hosted experiment verified. Source records, each host report and the final audit are retained as separate artifacts.

This is an eight-state research experiment. It does not establish universal observational equivalence, real-world sensing, autonomous provider authority, independent physical host domains, or measured performance acceleration.

## Next research step

Use a federated, authenticated observer-capability directory to find *actual* available measurements and estimate real cost. Before dispatch, prove the measurement set sufficient for the requested intention under a versioned Ground; after receiving evidence, re-check context authority and reconstruct the result without leaking the receiver's full internal state.
