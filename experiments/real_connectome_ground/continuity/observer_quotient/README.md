# RCG-006 — Learning observer-relative Grounds from synthetic computational traces

**Status:** source-bound research implementation, independent exact proof and local
large-scale evidence. **No trained language model, learned neural parameters,
general neural fast-forwarding, or verified E-CPU network run is claimed.**

## Purpose and continuity

RCG-004 learned a scalar temporal recurrence for one source/output; RCG-005
checked a common **source-vector** annihilator so several nonlinear readouts
could share one distant-time query. Neither creates a small reusable
representation valid for arbitrary source states.

RCG-006 moves the unit of discovery from one initial state to an **observer
channel**. An observer can care about fewer distinctions than the underlying
network has. The training task is to infer which internal states have equal
future responses to that observation. Any proposed equivalence is rejected
unless an independent receiver proves it for the **whole finite-field operator**.

Existing foundations reused:

- RCG-001 original c302 source identity, unaltered directed synapse observations;
- RCG-004 `SparseTransfer` and field semantics;
- RCG-005 `ConjugatedGround`, `prepare_shared`, independent vector-annihilator
  verification and shared quotient polynomial time jumps;
- VGI finite observer quotients and typed operator/temporal navigation;
- E-CPU `law_certifier`/M1/M3/Transit/evidence authority, **not replaced**;
- IFS PNF neural construction and existing mTLS tensor workers for downstream
  actual body realization, **not claimed to have executed here**.

## Model: real source -> synthetic expansion -> discovered observer quotient

The input is the version-pinned OpenWorm c302 source Ground (full 7,379-edge
source in the parent RCG-001 PR; compact source-row fixture in local tests).
Choose a power-of-two `g` group count and `c` synthetic microstates per group.
Positive chemical synapse statistics of the source determine **heterogeneous**
source-group coefficients. A deterministic generator constructs `n=g*c`
distinct addressed microstates, with **8 directed connections per microstate**,
and scrambles their visible address order. Weights and connections are defined
by a precise finite-field source-dependent law, not sampled trained parameters.

This **is not a quotient or trained simulation of the original biological
connectome**. It is a synthetic compute Ground *generated from observed source
statistics*. Its macro-level repetition is deliberately verifiable. Microstate
count and generated edge count do not measure independent learned information.

Let `M` be its sparse linear operator over GF(1,000,000,007). Only a declared
output channel `l` (mass at output group zero) is available to the learning
procedure. It observes `l`, `lM`, `lM²`, ... by symbolic reverse propagation,
and groups source states with equal observed histories. The generator's hidden
group identities **are not passed to the learner**. It proposes a partition
`P`, and a compressed operator `Q` from observed equivalence classes.

**Critical independent proof:** For every microstate `i`, the receiver checks
all outgoing source edges and their total weight into **every proposed class**.
The outgoing signatures must agree for all microstates proposed equivalent:

\[
P M = Q P, \qquad l = \bar{l}P.
\]

The first identity proves `P M^t = Q^t P` for *every* `t >= 0` and *every*
initial vector over the field. This is strictly stronger than one-source
prefix agreement. The second preserves the declared observer channel.

**Navigation:** For any permitted microstate source, project the one-hot input
through `P`, form the small `Q` and reuse RCG-005's reversible polynomial
neural chart around it. RCG-005's vector annihilator and quotient polynomial
then recover nonlinear observations at `t=2^56+73` without materializing the
original microstate trajectory. The nonlinear decoder is fully procedural;
its exactness follows from the certified quotient and explicit reversible
chart, not a learned behavioral predictor.

The retained certificate includes a source-bound generator description,
compressed partition assignment, complete quotient coefficients, observation
trace digests, proof contract and SHA-256. The receiver may independently replay
training traces, reconstruct the original synthetic sparse operator on demand,
and check *every microstate column*. Certificate hashes are integrity evidence,
not a signature or session authority. The application capsule remains subject
to E-CPU's existing receiver authority and durable-lineage checks when deployed.

## Direct negative control: the original graph

`DirectSourceOperator` can apply the **same** algorithm to the unaltered
source-pinned connectivity operator over the prime field. A small exact
partition **is not guaranteed**. The compact 8-label source-row fixture
finds a 6-class exact quotient for the `AIYL` output and refuses a proposed
low-dimensional quotient for another output channel (`AWCL`). The real 448-node
source is checked when available in hosted tests, without asserting it will
compress. This separates *whether the source is observed* from *whether the
requested observation admits a useful exact quotient*.

## Local scale results (2026-11-16, Python 3.13, compact source fixture)

| Synthetic microstates | Directed connections | Discovered classes | Observation horizon | Learn | Deep verify | Mean distant neural query |
|---:|---:|---:|---:|---:|---:|---:|
| 8,192 | 65,536 | 16 | 8 | see `benchmark.py` | see benchmark | see benchmark |
| 16,384 | 131,072 | 16 | 8 | see `benchmark.py` | see benchmark | see benchmark |
| **131,072** | **1,048,576** | **16** | **8** | **4.895 s** | **4.727 s** | **27.0 ms** |

The 131,072-state certificate is **3,421 canonical JSON bytes**. Each of eight
distant-time queries uses a new source address with 0 materialized microstate
vectors *after* admission; discovery and full-edge verification are fully
charged separately. The generator does not store its million-edge table.
The small certificate exists because the **constructed** network has a true
16-class observable quotient, not because a million arbitrary independent
weights were reconstructed or compressed. Timings were measured locally;
there is no claim of TLS, WAN, energy or multi-host speedup.

## Run

```bash
export PYTHONPATH="$PWD/experiments/real_connectome_ground:$PWD/experiments/real_connectome_ground/continuity/temporal_fabric:$PWD/experiments/real_connectome_ground/continuity/nonlinear_orbit:$PWD/experiments/real_connectome_ground/continuity/observer_quotient"
python -m unittest discover -s experiments/real_connectome_ground/continuity/observer_quotient -p 'test_*.py' -v
python experiments/real_connectome_ground/continuity/observer_quotient/benchmark.py --fixture --groups 16 --copies 8192 --output /tmp/rcg006-scale.json

SRC=experiments/real_connectome_ground/data/herm_full_edgelist.csv
PIN="$(sha256sum "$SRC" | cut -d' ' -f1)"
BR=experiments/real_connectome_ground/continuity/observer_quotient/capsule.py
python "$BR" train --source "$SRC" --expected-source-sha256 "$PIN" --groups 16 --copies 1024 --out /tmp/rcg006-cert.json
python "$BR" verify --source "$SRC" --expected-source-sha256 "$PIN" --certificate /tmp/rcg006-cert.json --out /tmp/rcg006-proof.json
python "$BR" query --source "$SRC" --expected-source-sha256 "$PIN" --certificate /tmp/rcg006-cert.json --micro-source 123 --tick 72057594037928009 --out /tmp/rcg006-answer.json
python "$BR" replay --source "$SRC" --expected-source-sha256 "$PIN" --certificate /tmp/rcg006-cert.json --receipt /tmp/rcg006-answer.json --out /tmp/rcg006-verdict.json
```

Every CLI action requires an independently supplied original-source SHA-256.
The full original source additionally requires the exact upstream Git blob;
`--fixture` permits only non-original test evidence. Files are write-once
within the CLI and duplicate-key/oversized JSON is refused. Separate process
verification still does **not** authenticate a remote transport peer.

## Verification and unresolved work

Local: 9 tests passed, 1 source-pinned original-data test skipped until the
full GitHub branch is checked out. Independent full microstate oracles run for
multiple *unseen* initial vectors and short horizons. Adversarial tests include
changed and rehashed partition, a moved micro edge, rehashed wrong quotient,
wrong training row, wrong source, forged nonlinear output and an independent
receiver rejecting corrupted JSON. `rcg006.yml` runs full-source tests under
Python 3.11/3.13 and a separate source-pinned scale benchmark; check the
exact-head CI result before accepting those claims.

Next body integration: retain the certificate in E-CPU's existing M1/M3 object
and recovery lineage, carry the query/receipt over existing mTLS `ReliableChannel`
/ `TransitComputationalHost`, use `EvidencePathResolver` for qualified route
selection and measure path-specific delivery, realization, failover and proof
cost. **Do not create another transport or authorization system.**

Next mind integration: learn new observer masks and candidate quotient families
from synthetic workload distributions, preserve unresolved status when exact
intertwining fails, and compare cost vs approximation using explicit error
budgets. Learn reversible nonlinear charts only after exact inverse/equivalence
admission. A general neural model need not possess any compact exact quotient.
