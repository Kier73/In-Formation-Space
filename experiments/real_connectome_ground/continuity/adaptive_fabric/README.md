# RCG-003 — Adaptive observer-host fabric from synthetic evidence

**Scope correction (2026-11-16).** **Body** = observer-hosts, communication paths,
qualified transport endpoints, available realization substrates, admission, data
movement, persistent sessions and recovery. **Mind** = source-bound procedural
models, synthetic training, semantics, attention, Ground navigation and evidence.
The real OpenWorm connectome is one **heterogeneous source topology** from
which reproducible synthetic computational tasks are formed, not an intention
to reconstruct an animal or run sensorimotor behaviors.

## Existing systems, reused rather than rebuilt

| Project | Existing implementation | How RCG-003 uses it |
| --- | --- | --- |
| E-CPU | `mailcpu/evidence_path_resolver.py`, `computational_host.py`, Transit/mTLS, Hypervisor, M1/M3 quorum | Authoritative transport/execution and persistent state **future integration**, not reinvented |
| In-Formation-Space | `procedural_neural_formation`, `tensor_cut_realization/transit_tensor.py`, `run_transit_local.py` | Existing neural model construction and *actual* mTLS tensor-handoff experiment; do not duplicate |
| In-Formation-Space | `realization-cost-navigation`, `in-transit-memory/adaptive_repair.py` | Existing cost/evidence and adaptive channel reasoning, distinct from this synthetic supervised host-cost fit |
| In-Formation-Space | RCG-001 `connectome_ground.py` | Exact original-source query, causal cone, full-graph oracle and source identity |
| In-Formation-Space | RCG-002 `continuity.py` | Immutable Ground/query chronicle; no parallel data authority introduced |
| VGI | `typed_operator_navigation.py`, `relational.py` | Ground demand operators and observer-equivalence semantics, to be adapted for learned models |
| Virtual Processor | `vp/navigable_experts.py`, `native_inference.py` | Existing synthetic parameter navigation and E-CPU-native operator admission |

## What actually executes

`fabric_policy.py` generates source-bound query intentions from RCG-001's real
connectome and enumerates bounded candidate routes: local IPC, modeled TLS, and
modeled GitHub-job transport. **Only local IPC is actually executed** in this
experiment; the other two have synthetic, explicit cost laws and are never
presented as measured remote execution.

A deterministic simulator supplies cost labels: duration = a + b × stage-edge
visits + c × transmitted 256-byte units + d × queue units. This is **synthetic
telemetry**, not any observed CPU/network benchmark. `fit` learns the four
coefficients from an exact Fraction-based rank-checked least-squares normal
system for each host/method. The policy predicts cost, filters unavailable or
unpermitted hosts, selects the lowest estimated cost, and records only a
*proposal*.

**Mind correctness is separate:** the selected route cannot set task output.
The original RCG-001 Ground independently checks exact rational transfer, and
modified source/plan/receipt/host policy refuses. A fresh subprocess receives a
bounded JSON request over **real stdio IPC**, independently loads/pins the source,
refuses modeled remote routes, and reconstructs the query from the source in a
new interpreter. This is not an mTLS/TCP remote authority test.

## Local results (source-derived compact fixture)

- 18 disjoint synthetic training queries, 12 held-out source-target-horizon
  intentions; 6 candidate host/method pairs with two synthetic queue/frame
  observations per training task (216 observations).
- Exact linear regression on the same synthetic cost family gives **0 total
  held-out regret** and **0 prediction error**, versus **1,309 synthetic ticks**
  of baseline regret for a local-first selection rule.
- The policy chose modeled transit/cone 9 times and local/cone 3 times. This
  is a *policy simulation*, not nine remote computations.
- Fresh subprocess local IPC verifies the source-grounded observation twice,
  with identical receipt bytes; changed source, denied media and tampering refuse.
- Full original OpenWorm CSV tests are configured in GitHub Actions; the fixture
  result does not prove deployment or operation on the complete connectome.

These results deliberately reflect an **identifiable linear synthetic law**;
they are a regression/integration gate, not a difficult learned-AI benchmark,
new network throughput result, or proof of general adaptive intelligence.

## Reproduce

From repository root with Python 3.11+ (no third-party dependencies):

```bash
export PYTHONPATH="experiments/real_connectome_ground:experiments/real_connectome_ground/continuity"
python -m unittest discover -s experiments/real_connectome_ground/continuity/adaptive_fabric -p 'test_*.py' -v
python experiments/real_connectome_ground/continuity/adaptive_fabric/fabric_policy.py \
    --train 18 --test 12 --seed 61 --output /tmp/rcg003-synthetic-study.json
```

New training curriculum: `../training_tracks_v2.json`; v1 remains immutable for
historical Chronicle reference. A study file does not automatically authorize
a capability or change the RCG-002 Chronicle. The separate assessor refuses
self-reported results as live host evidence.

## Next useful build

Use existing **TCR-002 mTLS tensor-cut receiver** or E-CPU `TransitComputationalHost`
as the *actual path execution adapter*, including receiver-owned Ground and
model identities. Replace the cost simulator with a measured operation-span
record from real path traffic. Compare local, mTLS and job-artifact paths under
matched task/byte conditions; force failed hosts and rehome using E-CPU's
existing M3 quorum/route-epoch authority. Then, with SNC/PNF, produce actual
synthetic trainable neural operators rather than solely fitting route latency.
