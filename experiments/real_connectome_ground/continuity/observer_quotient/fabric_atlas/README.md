# RCG-007 — Portable, all-state capability atlas on the E-CPU observer fabric

**Status:** mathematical atlas independently checked locally; native M1 and
mTLS integration tests require native E-CPU, are separately gated in CI and
must not be claimed as run until an exact-commit hosted run succeeds.

The system's **body** remains its qualified observer-host and communication-path
substrate. Its **mind** remains typed procedural computational Grounds and
certified observers. This work does not pursue biological dynamics or autonomous
sensorimotor behavior. OpenWorm supplies a **pinned heterogeneous source** for
synthetic compute generation, not an animal to simulate.

## Why this work exists

RCG-006 discovers and proves an observer quotient from a single output channel
by checking *every* generated micro-edge: `P M = Q P`, and the readout identity.
This was already strong enough to serve **any starting vector**, but its example
query path created a nonlinear model tied to one source microstate at a time.
We extend this to a **universal multi-intention atlas** with a single global
recurrence for all projected source states, all supported readouts, and all
future times. An independent receiver verifies both exact algebraic relations.

We found existing components and reuse them instead of introducing competing
ones:

- **RCG-001/006**: original source pin, exact connectome-derived procedural
  graph, signature-based discovery, independent `P M = Q P` proof;
- **RCG-005** `conjugate_ground.quotient_power`: already implemented fast modular
  time navigation; the atlas calls it once for an entire batch;
- **E-CPU M1** `ComputationalObjectStore` + `StructuralMemoryPageBacking`:
  actual content-addressed page objects and recoverable page snapshots;
- **RCG-004** `temporal_transport.send_once`, `channels`, `poll_ack`, existing
  native `mailcpu.mtls_transport` and `SocketTransport`: mTLS and reliable
  requests; **TCR-002** supplies SAN test certificates;
- **E-CPU M3** recovery/quorum and existing computational sessions:
  explicitly *not* replaced. The local high-water snapshot in this experiment
  is **not** an M3 or quorum commit. Future integration should anchor it using
  the native E-CPU recovery-lineage authority.

## Mathematical contract

Let `M` act on the generated `N`-microstate vector `x` over GF(1000000007),
`P` be the verified class projection, and `Q` be the quotient operator.
With `P M = Q P`, every initial `x` and logical tick `t ≥ 0` satisfy
`P M^t x = Q^t P x`. On the **small** quotient, we derive a characteristic
polynomial `q(X)` by Faddeev–LeVerrier, then independently verify `q(Q)=0`
using a full matrix Horner calculation. This global relation holds for **all**
projected initial states; there is no one-source shortcut assumption.

We reuse the existing modular quotient-polynomial evaluator to calculate
`X^t mod q(X)` **once for a batch**. Every query may have a different sparse
initial microstate mixture (up to 64 coordinates) and typed readout:
`class` coordinate, `linear` class combination, `sum_squares`, or
`shear_pair` nonlinear polynomial. The nonlinear outputs are deliberately
functions of the **already certified projected state**: no unwarranted claim
that arbitrary hidden microstate readouts survive the quotient.

The result depends on source bytes, procedural generator law, learned
partition, verified quotient coefficients, a global annihilator, query
intention and output definition. Hashes protect content integrity under
independent source ownership; no hash grants execution authority.

## Evidence on a 131,072-state source-derived synthetic workload

Local Python 3.13, **10 source CSV rows in an explicitly labeled fixture**,
16 observer classes, 1,048,576 procedurally reconstructed micro-edges,
64 heterogeneous queries, `tick=2^56+73`:

| Cost phase | Measured |
|---|---:|
| Initial Ground/source indexing | 0.345 ms |
| Learn observer quotient | 5,044.6 ms |
| Prepare globally valid temporal atlas (includes independent `P M=Q P` proof) | 4,876.8 ms |
| Independently verify universal atlas and source | 4,864.4 ms |
| Median all-64-query batch navigation | **6.611 ms** |
| Modular polynomial compositions for whole batch | **60** |
| RCG-006 quotient certificate | 3,421 bytes |
| New universal atlas certificate | 869 bytes |

These timings **exclude** TLS, network transmission, M1 cold provisioning,
filesystem persistence, attestation and remote-host performance. High logical
time and the existence of synthetic network addresses are not evidence of an
arbitrarily trained intelligent model. The synthetic generator intentionally
has a compressible 16-state observer quotient; the certifier must refuse
nonconforming or unsupported programs.

## Native computational-body experiment

`m1_bridge.NativeM1Atlas` is a typed adapter to native M1 objects, **not**
a new store. It admits the original source and quotient certificate, builds a
content-addressed paged M1 object and reads it back, then exports a local
checkpoint with an **externally held** head. Restoring rechecks every original
source microstate and rejects altered pages, wrong pinned heads, or changed
source bytes. This is durable state in the local filesystem only when the
checkpoint and its pages are actually persisted. No quorum, globally fenced
idempotence, M3 epoch, or operator Hypervisor authorization is claimed.

`native_handoff.py` is an experimental application handler on **the existing**
E-CPU mTLS/ReliableChannel. It cold-provisions one atlas certificate through an
authenticated TCP loopback receiver, sends subsequent **warm reference-only**
queries, kills that receiver interpreter, and creates a new authenticated
receiver from a separately pinned snapshot. The replacement must answer
without retransmitting the atlas. Sender independently re-evaluates every
response against its own source-pinned Ground; the two endpoint TLS
certificate identities, request/response digests and separate host clock
spans remain visible. Application request IDs are fenced **within one receiver**;
there is no cross-host exactly-once guarantee yet.

A separate Python process is a separate observer **process**, not an
independently attested physical machine. TLS transport itself still runs on
physical hardware. No passive packet claims to compute semantics by itself.

## Reproduce

From the In-Formation-Space root:

```bash
export PYTHONPATH="$PWD/experiments/real_connectome_ground:$PWD/experiments/real_connectome_ground/continuity/temporal_fabric:$PWD/experiments/real_connectome_ground/continuity/nonlinear_orbit:$PWD/experiments/real_connectome_ground/continuity/observer_quotient:$PWD/experiments/real_connectome_ground/continuity/observer_quotient/fabric_atlas"
python -m unittest discover -s experiments/real_connectome_ground/continuity/observer_quotient/fabric_atlas -p 'test_*.py' -v
python experiments/real_connectome_ground/continuity/observer_quotient/fabric_atlas/benchmark.py --fixture --groups 16 --copies 8192 --count 64 --output /tmp/rcg007-131072.json
```

Native E-CPU integration (requires installed native E-CPU package and OpenSSL):

```bash
python -m unittest discover -s experiments/real_connectome_ground/continuity/observer_quotient/fabric_atlas -p 'test_*native*.py' -v
python -m unittest discover -s experiments/real_connectome_ground/continuity/observer_quotient/fabric_atlas -p 'test_m1_bridge.py' -v
```

The native **fixture** loopback test sends actual bytes and exercises M1
cold/warm/restore; the GitHub workflow additionally runs source-pinned original
OpenWorm tests and the full 131K scale. See `results/local_131072.json`.

## Next qualified work

1. Promote the receiver checkpoint into existing E-CPU **M3 quorum lineage**;
   test stale-owner refusal and hard-kill split-brain behavior.
2. Admit `atlas` as a qualified local operator through `TransitComputationalHost`
   and Hypervisor capability, using existing admission and forwarding.
3. Train task/host selection against **actual** transport timings and exchange
   verified multi-source information across distinct qualified observer-hosts.
4. Measure how many **nontrivial** independent observer quotients survive
   composition on original and newly generated neural topologies. A synthetic
   count alone is not evidence of generalizable intelligence.

Never report a passing native network test merely because the workflow was
enqueued; gate claims on exact-head hosted evidence.