# RE-003 — Independent observers, intervention-aware reconstruction

**Status:** reproducible exact finite synthetic fixture; local tests passing. Runs two Python observer processes and a separate Python verifier process on one machine. **No physical/network host independence, actual E-CPU admission, signed host attestation, hardware sensor, or universal generator discovery is claimed.**

## Question

> Can independently evolving computational observers combine partial response evidence to identify a common generating law, while preserving that a measurement itself may alter the observed state?

This is the next question after [RE-001](README.md) (a response law is not an internal realization) and [RE-002](RE002_README.md) (active probing distinguishes candidate laws in resettable models). Unlike RE-002's independent zero-state impulse trials, RE-003 carries state forward *after each probe* on each observer's separate replica.

The design borrows **mathematical/contract ideas**, not runtime implementations, from:

- [VGI Builds 14–17](https://github.com/Kier73/Virtual-Ground-Interpreter/tree/main/theory_development): observer-relative response geometry, clock invariants, and the limits of event matching.
- [In-Formation-Space Trial 08](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md): a probe gives both an observation and a post-intervention state; the next observation depends on the latter.
- [In-Formation-Space MOR-001](../multi-observer-causal-reconstruction/README.md): host-local temporal evidence does not define a global wall-time order.
- [In-Formation-Space observation-path](../../bridges/observation-path/README.md) and [E-CPU gated observation](https://github.com/Kier73/E-CPU/blob/main/mailcpu/gated_observation.py): refusal is not a negative sensor reading or committed intervention.
- [E-CPU operational semantics](https://github.com/Kier73/E-CPU/blob/main/docs/OPERATIONAL_SEMANTICS_AND_STATE_SPACE.md): meaningful comparisons bind context, interpretation and observation contract, not just a matching byte vector.

## Exact finite law catalogue

Each host contains a private state `(x,z,h)` over `Z/17Z`. Every host starts from `(0,0,0)`, but then evolves *independently* according to its own selected interventions. The two processes are initialized with the same planted law during fixture construction; the verifier receives neither the planted law ID nor the private states. Five candidate laws are declared:

| Candidate | `alpha` | `beta` | Hidden state |
| --- | ---: | ---: | --- |
| `reference` | 1 | 1 | no additional active mode |
| `gain_variant` | 2 | 1 | no additional active mode |
| `hidden_variant` | 1 | 2 | no additional active mode |
| `both_variant` | 2 | 2 | no additional active mode |
| `observational_alias` | 1 | 1 | third internal mode advances but cannot affect either declared readout |

Available actions act as follows (modulo 17):

- `pulse`: **intervene**, then observe new `x`. `x' = x+1+alpha*z`, `z'=z+beta`. The hidden coordinate `h` evolves independently for `observational_alias`.
- `inspect`: observe **old** `z`, then **intervene** with `z'=z+1`; available only through host B and only under the fixture's explicit `inspect:z` grant.
- `observe`: observe old `x` without changing the state.

Host A emits the `x` reading as an integer. Host B emits the same declared underlying reading through a different known sensor calibration, `raw_B=2*value+1`. Host B can additionally inspect `z`; Host A cannot. The verifier compares calibrated predictions against raw records; it never compares unlike raw channels directly.

## Discriminating encounter

For true law `gain_variant`, two pulses on independent Host A yield raw observations `[1,4]`. The compatible law set is:

`H_A = {gain_variant, hidden_variant}`.

A bounded two-step future-state-aware probe search then proposes **`inspect`, followed by `pulse`** on a fresh independent Host B. Inspection itself returns raw `1` under *all* surviving candidates (the initial `z` is zero). Yet inspection advances `z` by one, so the subsequent pulse distinguishes their different `alpha` coefficients. Host B returns `[1,7]`, giving:

`H_B = {gain_variant, both_variant}`.

Combining the independent constraints gives:

`H_A intersect H_B = {gain_variant}`.

Neither host alone has a singleton. The verifier does not need to compare their clocks or pretend that their different stateful histories were one shared timeline. It replays each candidate's **host-local sequence of probe transitions**, checks exact raw outcomes and intersects compatible laws.

**Intervention negative control:** a wrong model that treats `inspect` as a non-invasive observation predicts Host B's `[1,3]` rather than the actual `[1,7]`. It therefore gives an incorrect account of what later probes see. This is an explicit calculation, not a label attached to a qualitative result.

**Admission negative control:** with `inspect:z` not granted, Host B's attempted inspection produces `refused` and `raw=null`, and does not update its state. Host A still leaves `{gain_variant, hidden_variant}`; later Host B pulses do not separate them. The correct conclusion is **unresolved**, not a fabricated negative measurement.

**Unobservable mode negative control:** `reference` and `observational_alias` remain indistinguishable under every declared action, even when inspection is authorized. One has an additional evolving internal coordinate. The experiment does not claim to recover a unique internal realization.

## What the host processes and verifier actually do

`multi_host_reconstruction.py` provides `--host` and `--verify` stdin/stdout JSON modes. The demonstration driver starts distinct OS child processes for Host A and Host B, then a third verifier process. Observer processes own their private state; their emitted event records expose only action, observation (or refusal), local tick, declared sensor, authority label, local sequence, predecessor digest and record digest. The verifier is supplied only these records, the finite law catalogue in its implementation, and the independent **synthetic grant manifest**; it does not receive the fixture's true law or private state.

The verifier:

1. Checks an exact record schema, fixture session, action/readout contract, claimed statuses, input ranges and declared synthetic grant policy before using any raw observation.
2. Validates each producer's sequence-number continuity, monotonic *local* ticks, predecessor record hashes and SHA-256 record hashes, including when the collection arrived in reverse order.
3. Replays each candidate separately on each host's own private predicted state; `refused` neither mutates nor constrains a state.
4. Reports the surviving candidate names, first incompatible observation for each rejected candidate, and `global_event_order: null`.

Hash linking detects accidental or unsophisticated event mutation **under a trusted pinned root**; it is **not** source authentication. A producer with control of all records can rewrite the chain and its digests. PIDs demonstrate only separate processes on one machine, not independent hardware hosts or authentic identities. The supplied grant manifest is a **mock authority decision**, not an E-CPU capability or live Hypervisor authorization. The fixture's A/B local ticks use deliberately far-separated local coordinates; this is not measured drift, nor does their ordering establish causality.

No network transport, independently signed artifacts, secure cross-host handoff, live admission, concurrent effects or exogenous plant drift are exercised. The deterministic planner searches finite non-branching sequences of at most two actions for a **fresh host replica**. It is neither an optimal multi-step contingent policy nor an inductive discovery method for a previously unknown model class.

## Reproduce

From the repository root on Python 3.11+ (standard library only):

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/multi_host_reconstruction.py > /tmp/re003_report.json
cmp /tmp/re003_report.json experiments/response-equivalence/re003_report.json
```

The frozen report removes nondeterministic local PIDs but retains `different_process_ids=true`. The executable test checks that the two producer PIDs differ, checks multiple negative controls, and exercises the independent verifier subprocess.

## Open question

Can we preserve the same distinctions using **genuinely independent, authenticated hosts** and E-CPU `TemporalFrame` / `GatedObservationCoordinator` receipts, where the system may also undergo unobserved external drift between probes? Such evidence needs an explicit causal handoff, authority/admission receipts, externally verifiable origin, and a policy for unknown model families. RE-003's finite controlled fixture does not supply those guarantees.
