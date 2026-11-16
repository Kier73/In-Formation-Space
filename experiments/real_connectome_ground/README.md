# RCG-001 — Real connectome → query-specific causal Ground

**Status:** prototype grounded in a pinned original OpenWorm c302 hermaphrodite connectome snapshot, with an exact limited-horizon structural-transfer observation contract. This is not a biological neuron simulation or a trained model.

## Source provenance

- Original repository: [openworm/c302](https://github.com/openworm/c302) (MIT; upstream LICENSE attributed to OpenWorm 2024).
- Commit: `d542a44bf2662f79e0ad23342a959a181a920877`.
- Source: `c302/data/herm_full_edgelist.csv` (Git blob SHA-1 `89ffc2a2d9e1934ddc462d51032acead5e4cfc91`; 245,463 bytes).
- Imported **without normalization or changing raw bytes**; the parser trims padded neuron labels after verifying the original Git blob. 7,379 recorded directed typed rows; 4,681 chemical, 2,698 electrical; 448 node labels (some represent muscle structures).
- The upstream data is not a complete specification of spike dynamics, neurotransmitter sign, cell morphology or context-dependent learning. Its synapse counts are observations, not learned weights or measured transfer probabilities.

## A concrete question and a declared model

Given an initial unit impulse at source neuron `s`, a target `t`, exact horizon `H`, and a *single* synapse type, define a non-biological **unsigned normalized structural transfer**:

\[
 x_0(s)=1,\quad x_{n+1}(v)=\sum_{u\to v} x_n(u)\,{w_{uv}\over \sum_{u\to z\;\mathrm{in\;the\;original\;graph}} w_{uz}}.
\]

The source counts `w` are positive integers and all observations are exact rationals. This law answers *which directed routes can structurally transfer mass in H steps and how much under this stated normalization*. It makes **no claim** about actual excitation, inhibition, firing, behavior, functional importance, or biological prediction. An absent path is exact only for the pinned source and selected edge type/horizon.

A query constructs a time-expanded causal cone: `C_i = reachable_exact_i(s) ∩ can_reach_exact_(H-i)(t)`. Only stage-specific edges from `C_i` to `C_(i+1)` are realized. **The denominator always comes from the whole indexed source graph**, not from the pruned subgraph—otherwise the answer silently changes. This handles loops by using `(neuron,stage)` as the state identity. Source-time loops remain valid; other neurons need not be numerically realized for this query.

`ConnectomeGround.verify()` independently recomputes the entire pinned graph via original edge streaming, using exact `fractions.Fraction` arithmetic, and checks source identity, bounded plan, every layered stage, receipt, and final transfer. A SHA-256 content digest is integrity evidence, **not** cryptographic authentication or permission to execute. Optional `native_ecpu_stage_dag()` reuses E-CPU's original `NavigableComputationDAG` for sequential stage dependencies and snapshot recovery; it does not create a new Hypervisor, authority, or transport substrate.

## Queries and observed results

The following *structural* sizes come from an independent scan of the **actual** pinned OpenWorm CSV, and will be checked with exact rational end-to-end tests in CI:

| Sensory/source → target | Chemical steps | Layered causal-cone widths | Distinct node labels | Realized stage edges | Full reference stage-edge visits | Approx. transfer |
|---|---:|---|---:|---:|---:|---:|
| `ASHL → AVAL` | 3 | `1,20,49,1` | 58 | 245 | 14,043 | 0.0289897649 |
| `ASER → AVBL` | 3 | `1,16,27,1` | 42 | 110 | 14,043 | 0.0200009094 |
| `AWCL → AIYL` | 2 | `1,4,1` | 6 | 8 | 9,362 | 0.0406881551 |
| `ASHL → AVAR` | 3 | `1,18,44,1` | 55 | 215 | 14,043 | — |

The index must first be built in `O(E+V)`, and **planning** does indexed forward/reverse graph probes; for `ASHL → AVAL` it inspected 7,657 candidate edge references. Its 245 selected edge realizations compared with 14,043 full-reference visits should **not** be presented as a 57× measured runtime speedup. Repeated queries could amortize index construction; actual wall time/memory/transport require benchmarking.

## Run

```bash
python experiments/real_connectome_ground/connectome_ground.py
python -m unittest discover -s experiments/real_connectome_ground -p 'test_connectome_ground.py' -v
```

The source is vendored with its Git blob fingerprint and OpenWorm MIT attribution; no runtime network connection or pretrained framework is required. Python 3.11 and 3.13 CI jobs check the full graph, all four query cones, full-graph oracle, tamper refusals, and native E-CPU stage DAG (in a separately pinned job). They fail if source bytes change.

## Next experimental frontier

First: external stimuli/actual recorded neural activity (FlyVis or OpenWorm response data), synaptic signs and cell dynamics as **new evidence-backed Ground dimensions**; then ask which selected, source-pinned subcircuit reproduces reference dynamics under a task-defined error tolerance. Causal-cone reachability for a linear, bounded-horizon model is exact; general spiking systems may require context/state and cannot be presumed to use this closed cone without proof.

Second: connect selected stage operations to E-CPU observer-host Transport/Virtual Layer, signed receipts, and state recovery using existing IFS ObservationPath/VGI authority integration. Do not misrepresent a mathematical local optimization as a remote path executing neuron arithmetic.