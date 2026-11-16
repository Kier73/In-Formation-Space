# RCG-005 — Nonlinear procedural Grounds with a shared vector-time certificate

**Status:** research integration (stacked on RCG-004, RCG-003, RCG-002, RCG-001). Source identity, operator semantics and execution authority remain distinct. **Body** = E-CPU observer-hosts, authenticated communication paths, qualified execution and recoverable state. **Mind** = synthetic/procedural operators, mathematical Grounds, learned or constructed navigation, and independently checked observations. The OpenWorm graph is a source of heterogeneous topology, *not* an artificial animal body or a biological dynamics model.

## Why this experiment rather than a new substrate?

Before implementation, we inspected:

- [E-CPU law_certifier](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/mailcpu/law_certifier.py): existing prime-field Berlekamp–Massey, distant-time algebra and source Ground admission. **RCG-004** already uses and independently cross-checks BM; RCG-005 reuses its `berlekamp_massey` and `_multiply_mod` rather than inventing another field/polynomial engine.
- [VGI `polynomial_lift`](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/vgi/polynomial_lift.py), [typed operator navigation](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/vgi/typed_operator_navigation.py): exact polynomial lift / prepared temporal navigation; RCG-005's reversible polynomial chart is **constructed**, not discovered by fitting a new biological dynamics law.
- [IFS RCG-001/004](../../README.md): pinned OpenWorm source, sparse field operator, recurrence certificates, full-graph references. RCG-005 uses RCG-004's `SparseTransfer` and RCG-001's exact source parser.
- [IFS TCR-002](../../../tensor_cut_realization/transit_tensor.py) and [RCG-004 mTLS host](../temporal_fabric/temporal_transport.py): `mailcpu.mtls_transport`, `ReliableChannel`, source/target pinning, and TCR's SAN certificate fixtures. RCG-005 delegates all transport there rather than building a competing channel stack.
- [IFS PNF](../../../procedural_neural_formation/formation.py): neural construction and Net2Wider; RCG-005 is a **different algebraic model family** (finite-field polynomial coupling), not an attempted replacement for PNF's floating-point affine–activation–affine block compiler.
- [IFS RCG-002 Chronicle](../continuity.py): durable source and query lineage. RCG-005 exports content-addressed certificates for **that existing storage** or E-CPU M1; it does **not** create another ledger/quorum authority.

## The mathematical Ground

Let `M` be RCG-004's source-bound, directed, outgoing-count-normalized sparse operator over `GF(1,000,000,007)`. It is not the RCG-001 rational transfer law; the finite-field interpretation is explicitly a separate model. Let `p0,...,pd` be distinct node coordinates, with `p0` the source (initial state `x0=e_p0`). A SHA-256-addressed seed deterministically defines nonzero coefficients `alpha_i`.

Construct a depth-`d` reversible polynomial neural chart:

```
E(x): for i=0..d-1: x[p_i] += alpha_i * x[p_(i+1)]^2 (mod p)
D(y): for i=d-1..0: y[p_i] -= alpha_i * y[p_(i+1)]^2 (mod p)
F(x) = D(M E(x))
```

Each shear is an invertible polynomial cell on the full finite field, even when `M` is not invertible. Direct substitution proves `D(E(x))=x`. The computationally nontrivial fact is **conjugacy**:

\[ F^t(x) = D\,M^t\,E(x). \]

For the admitted source-basis initial state, `E(e_p0)=e_p0`. Therefore the requested nonlinear output at arbitrary time `t` can be reconstructed using only `d+1` latent linear coordinates `y[p_0..p_d]` and the inverse polynomial decoder. With depth three, the readout is at most degree eight as a polynomial in those latent values. This is an established conjugacy technique, **not** a universal accelerator for unstructured nonlinear systems. A genuinely nonlinear `F` was independently witnessed by failure of the superposition identity in a source-derived fixture.

## Shared all-future-time certificate (central new integration)

RCG-004 individually prepares one scalar recurrence for each `(source,target)` observation. RCG-005 instead prepares a single recurrence for the entire source-vector orbit:

1. Evaluate `2*n` sparse steps of `M^t e_p0` once, and project with deterministic challenge vectors. Use the existing BM implementation to propose recurrence `c_1,..,c_r` of degree at most `n`, retrying a bounded number of independent deterministic projections if necessary.
2. **Do not trust the fit.** Recompute the source-owned vector states `e_p0,M e_p0,...,M^r e_p0` and require the **complete vector identity**

   \[ M^r e_{p0} = \sum_{i=1}^{r} c_i M^{r-i} e_{p0}. \]

   This is stronger and cheaper than validating each scalar readout over `n` more residuals. For *every* `t >= 0`, multiplying by `M^t` proves the recurrence simultaneously in **every vector coordinate**, whether presently requested or not.
3. Retain `r` initial terms for just the selected `d+1` coordinates, bind the model/source byte digest and coupling coefficients, and independently verify those terms plus the global vector equality at the receiver.
4. Compute the quotient polynomial `X^t mod (X^r - sum_i c_i X^(r-i))` **once**, then use the same length-`r` coefficients to reconstruct every requested latent value. Decode the nonlinear observation from the small, selected coordinate set.

Producer candidate selection is heuristic, but a candidate is **admitted only if the full-vector recurrence equality holds**. No short-prefix extrapolation, rehashed forged receipt, unaudited altered source, or changed polynomial chart can bypass verification. Cost after preparation is `O(r^2 log t + (d+1)r + d)`, in pure Python, with `O(n^2)` preparation memory (n initial vector states). This is *not* `O(1)` computation, and not a claim about generic RNNs/transformers.

## Reproducible local results (2026-11-16, Python 3.13)

| Source topology | n nodes | Directed edges | Depth/latents | Vector recurrence degree | Prepare | Independent verify | One shared far jump |
|---|---:|---:|---:|---:|---:|---:|---:|
| Deterministic **synthetic** | 448 | 3,559 | 3 / 4 | 448 | 0.476 s | 0.188 s | **2.138 s** |
| Deterministic **synthetic** | 1,024 | 8,172 | 3 / 4 | 1,024 | 2.702 s | 1.179 s | **11.572 s** |
| Deterministic **synthetic** | 448 | 3,559 | **6 / 7** | 448 | 0.49 s | 0.19 s | **2.170 s** |
| Deterministic **synthetic** | 1,024 | 8,172 | **6 / 7** | 1,024 | 2.95 s | 1.17 s | **11.487 s** |

All jumps were at `t=2^56+73`. Each required 60 quotient-polynomial products, not 72 quadrillion state updates. For the 448-node case, four separate scalar navigators (RCG-004 reference) took **8.601 s combined** for the same four latent readouts; the shared navigator took **2.138 s** (4.02x reduction in the *navigation stage only*). This is not an end-to-end speedup once indexing, preparation, I/O and verification are charged. Exact expected result on the 448-node synthetic fixture is `997717564 mod p`; on 1,024 nodes it is `374119182 mod p`. For depth six, seven separate scalar navigations took **15.547 s** combined, versus **2.170 s** for the shared vector jump (**7.17x reduction in navigation only**). A depth-six decoder may have polynomial degree up to 64 in its latent variables, but it remains an explicitly constructed reversible family, not a learned intelligence benchmark. The original biological connectome file is Git-pinned on the parent PR, not locally available in this machine's Python runtime, so **original-source full-network success is not claimed until hosted CI**.

Independent checks: a separately coded small dense matrix-power oracle at `t=2^56+73` and `2^63-1`, repeated direct nonlinear recurrence for small times, full vector annihilator for every state coordinate, source/seed mutation refusal, rehashed coefficient/readout/output refusal, and independent subprocess `prepare -> verify -> replay` with receiver-owned SHA-256 pin. The tests do not confer external signing authority.

## Embodiment: actual E-CPU observer-hosts rather than biological dynamics

`distributed_run.py` composes `d=2` nonlinear readouts **across existing RCG-004 `TemporalHost` receivers**. It starts four authenticated loopback worker processes with independently provisioned original source bytes, TLS certificates and explicit allowed source/target. Two workers are qualified for one latent coordinate. For each request:

- The existing E-CPU ReliableChannel carries a bounded request over mutual TLS with SAN-validated receiver identities.
- The sender checks its own expected peer-certificate pin, request, source/ground, process identity, byte counts and measured sender clock spans.
- An independent RCG-004 scalar recurrence certificate is verified for each distinct received target; the chosen outputs are checked against the already independently verified RCG-005 shared vector Ground.
- The small procedural decoder combines the separately hosted latent readouts into the nonlinear result. A measured-cost EWMA (reused from RCG-004) selects eligible hosts; one receiver is forcibly killed midway and the surviving authorized receiver answers its coordinate.

**Scope:** this uses actual loopback TCP/TLS, separate local processes, and mathematically real arithmetic at receivers. Artificial service queues are fixture perturbations. It does **not** prove network paths perform arithmetic by being passive, physically independent trust domains, M3 restoration of a killed process, native Hypervisor operator grants, learned language semantics, or trained intelligence. A replacement replays from the shared immutable source Ground; not necessarily durable continuation of a stateful nonlinear host.

## Persistent capsules, reproducibility and original source

Source: OpenWorm c302 `c302/data/herm_full_edgelist.csv` commit `d542a44bf2662f79e0ad23342a959a181a920877` (Git blob `89ffc2a2d9e1934ddc462d51032acead5e4cfc91`), 7,379 typed edges among 448 connected labels (neurons **plus** other structures). Original source rights and attribution are retained by RCG-001. Synthetic expanded topology is explicitly marked synthetic; positive connection counts do not encode excitation/inhibition or trained neural weights.

From repository root:

```bash
export PYTHONPATH="$PWD/experiments/real_connectome_ground:$PWD/experiments/real_connectome_ground/continuity/temporal_fabric:$PWD/experiments/real_connectome_ground/continuity/nonlinear_orbit"
python -m unittest discover -s experiments/real_connectome_ground/continuity/nonlinear_orbit -p 'test_*.py' -v
python experiments/real_connectome_ground/continuity/nonlinear_orbit/benchmark.py --nodes 448 --depth 3
python experiments/real_connectome_ground/continuity/nonlinear_orbit/benchmark.py --nodes 1024 --depth 3 --skip-scalar-comparison

SRC=experiments/real_connectome_ground/data/herm_full_edgelist.csv
git hash-object "$SRC"  # must match original pinned Git blob
PIN="$(sha256sum "$SRC" | cut -d' ' -f1)"
python -m capsule prepare --source "$SRC" --expected-source-sha256 "$PIN" --out /tmp/nonlinear-ground.json
# Independently in a fresh Python interpreter (or another authenticated host):
python -m capsule verify --source "$SRC" --expected-source-sha256 "$PIN" \
  --certificate /tmp/nonlinear-ground.json --tick 72057594037928009 --out /tmp/nonlinear-observation.json
python -m capsule replay --source "$SRC" --expected-source-sha256 "$PIN" \
  --certificate /tmp/nonlinear-ground.json --result /tmp/nonlinear-observation.json --out /tmp/confirmed.json
```

The CLI explicitly checks the receiver-owned source SHA-256, refuses duplicate JSON keys and non-finite values, then repeats the full vector proof. Its output can be registered into RCG-002's existing Chronicle or E-CPU M1, **not** treated as an independent ledger.

An optional **native E-CPU job** on Python 3.11 installs pinned E-CPU and runs the 4-worker mTLS, failure, and independent comparison tests. Local mathematical tests do not count that native job as passing. If GHA remains queued, it remains unresolved and this PR stays draft.

## Research frontier

Construct or learn procedures `E,D` for which source observations certify their exact inverse and the conjugated operator still has a compact vector annihilator; extend beyond fixed triangular polynomial shears and source-basis initial states. Train a route policy on *measured* host latency and failure data, with held-out workload families, source/authority gates, measured energy, and end-to-end cost. Migrate certificates and communication-session state using existing M1/M3, after actual hard receiver failures and independently trusted recovery-lineage checks. **No model scale or arbitrary neural intelligence claim follows from the size of a named Ground alone.**
