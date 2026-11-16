> **2026-11-16 RCG-004 update:** Here, *body* means the E-CPU observer-host and communication-path computational fabric—not animal biology or sensorimotor behavior. The historical RCG-002 language below is retained as provenance; [RCG-003's correction](RCG-003-CORRECTION.md), [training tracks v3](training_tracks_v3.json), and the [certified temporal transit experiment](temporal_fabric/README.md) supersede it for current work. Original Chronicle entries remain unchanged.

> **2026-11-16 semantic correction (RCG-003):** In the E-CPU objective, the **body is observer-hosts and computation-bearing communication paths**, not biological sensing, actuation or sensorimotor behavior. The **mind is procedural/synthetic computational Grounds and adaptive verified inference**. The OpenWorm connectome is a structural dataset for synthetic tasks, not a biological embodiment target. Read [RCG-003 correction](RCG-003-CORRECTION.md), [adaptive fabric](adaptive_fabric/README.md) and [training curriculum v2](training_tracks_v2.json). This v1 document remains for historical evidence, not a current development directive.

# RCG-002 — Persistent connectome Ground and embodied virtual intelligence

**Location:** \`experiments/real_connectome_ground/continuity/\`  
**Upstream:** RCG-001 query-specific causal Grounds (draft PR #248)  
**Status:** evidence-retaining research program; not a biological brain model, not trained virtual intelligence, not network-attested recovery.

## Why this folder exists

The source connectome and query-specific causal subcircuits must survive changes of interpreter, research agent, observer-host and training direction without conflating a new interpretation with a new biological observation.

The "body" is the observer-host's sensory, action and feedback capacity; the "mind" is its model of the world, planning, memory, interpretation and trainable decision policies. Both are grounded in **retained evidence** and E-CPU/VGI/IFS mechanisms. Neither depends on a single particular hardware architecture for its *identity*. This does not mean a communication path performs computation without an active physical realizable operation.

Existing foundations, reused rather than rebuilt:
- RCG-001: pinned original OpenWorm c302 CSV, exact source Git blob, indexed causal-cone planner, unsigned structural propagation model and independent full-graph oracle.
- VGI: observer-relative Grounds, sparse attention, proof and unresolved-state distinctions; use to **certify** rather than predict equivalence.
- E-CPU: Transit observer-hosts, Virtual Layer/Hypervisor, content-addressed computation DAGs, M1 object stores, M3 sessions and recovery quorum; use those for real federation and authority when execution advances beyond this local research fixture.
- IFS ObservationPath, sufficient statistics, task-relative relevance, and active acquisition experiments.

## Persistent structure

The original source remains in \`../data/herm_full_edgelist.csv\`, imported at OpenWorm commit \`d542a44bf2662f79e0ad23342a959a181a920877\` (Git blob \`89ffc2a2d9e1934ddc462d51032acead5e4cfc91\`). That is the stable biological *connectivity observation*; it does not contain physiological spike dynamics or measured behavior.

\`continuity.py\` supplies a **local, verifiable source-and-query Chronicle**:

1. First record: immutable source manifest, carrying the actual Ground fingerprint, OpenWorm source identity and counted chemical/electrical edges.
2. Further records: content-addressed query capsules, including the selected subcircuit, numerical observation, existing attribution and **independent unpruned exact rational result**; or explicitly proposed training-intention records.
3. Each record is SHA-256 chained to its predecessor. Objects are write-once and fsynced. A missing object, incomplete ledger tail, forged plan/receipt, source replacement or stale externally-held high-water pin causes refusal.
4. On restore, \`audit\` replays the complete chain and **recalculates every query against the pinned original source**. A hash is integrity evidence, not third-party authentication. A malicious rewrite of *both* the ledger and all local pins cannot be detected without an independently trusted high-water or signed E-CPU recovery lineage.

The committed code and original source persist in Git. An active Chronicle is a **runtime state directory** and must be explicitly backed up or anchored to E-CPU M3 for cross-host persistence. No unobserved background job is implied.

### Run a source-pinned Chronicle

From the repository root:

\`\`\`bash
python -m unittest discover -s experiments/real_connectome_ground -p 'test_*.py' -v

STORE="$(mktemp -d)"
BASE="experiments/real_connectome_ground/continuity/continuity.py"
export PYTHONPATH="experiments/real_connectome_ground:${PYTHONPATH:-}"

python "$BASE" --store "$STORE" init
# Save the emitted SHA-256 'head' OUTSIDE the writable Chronicle store.
python "$BASE" --store "$STORE" --expected-head '<last trusted head>' \
  --from-node ASHL --to-node AVAL --steps 3 query
# Save the new emitted head outside the store.
python "$BASE" --store "$STORE" --expected-head '<latest trusted head>' audit
\`\`\`

**Operational rule:** persist the returned high-water head with a distinct trusted observer, E-CPU M3/quorum, or other independently controlled record. Do not learn that pin exclusively from the store that is being verified. Lock files left behind after abrupt process death must be adjudicated by a supervisor after verifying no writer remains; do not silently delete them. A partially written journal is rejected rather than automatically repaired.

\`evaluate_curriculum.py\` accepts an audited Chronicle, checks training prerequisites, and distinguishes \`design-ready\` research opportunities from proposals lacking source evidence. It never claims that a training run occurred.

## Body ↔ mind training progression

The machine-readable list of six opportunities is \`training_tracks.json\`. Work should add **observed outcomes, source revisions, evaluation splits and model checkpoints** as new typed, verified artifacts rather than editing historical evidence.

| Priority | Track | Smallest useful result | Evidence needed |
|---|---|---|---|
| 1 | **Body: structural transfer distillation** | Learned sparse readout reproduces held-out *declared structural-transfer* queries; compare against direct original-source calculation | Existing OpenWorm structure and RCG-001 exact oracle; synthetic labels only |
| 2 | **Mind: observation-valued navigation** | Reduce planner probes/latency without one incorrect source-grounded answer | Many varied query capsules and source-aware validation |
| 3 | **Body: biological dynamics** | Model withheld real stimulus-neural responses on a compatible, cell-mapped connectome | Real recordings, stimulus timing, neurotransmitter/response evidence, provenance; **blocked currently** |
| 4 | **Mind: Ground equivalence and memory** | Retain fewer bytes while reconstructing the same task-relative observations; abstain on unknowns | VGI proofs, independent oracle and negative counterexamples |
| 5 | **Body: authenticated sensorimotor continuity** | Same bounded task continues after an observer-host hard kill with no duplicate effects | Existing E-CPU mTLS, M3 recovery, action authority and external task metrics |
| 6 | **Mind: continuous learning and model choice** | Calibrated policy navigates/reconstructs/calls a model or abstains based on verified cost and task outcomes | Admitted model Grounds, validated task labels, E-CPU authority and source-pinned checkpoints |

A **training intention** is not a **trained model**. A fitted graph whose only labels come from our unsigned structural-transfer law has learned *that law*, not the animal's physiology. Artificially generated reward is not evidence of general intelligence. Before making stronger claims, record task success on genuinely held-out measured observations and source/model evidence independently.

## Durable development checkpoints

- **RCG-001 (implemented in parent PR):** original real structure, four exact source→target questions, time-expanded causal cones, signed/unsigned interpretation separated, independent oracle and attribution. Upstream model remains an unsigned transfer law.
- **RCG-002 (this folder):** immutable source identity, content-addressed query and proposed-training capsules, hash-linked append-only local continuity, receiver-pin checks, full-source semantic replay, machine-readable body/mind learning progression.
- **Next planned, not implemented here:** source-pinned neural-stimulus observations and sign/dynamics calibration; E-CPU mTLS/M3 authority-backed replacement observers; learned query planning under exact verification; expansion to real FlyVis or larger fly connectomes only with source/version and neuron identity alignment.

## Reproducibility and integrity

\`test_continuity.py\` covers reopening a store, independent whole-graph reconstruction, object tampering, missing objects, torn tails, concurrent writer refusal, stale trusted heads, source changes and source-inconsistent but freshly hashed observations. \`test_curriculum.py\` refuses false curriculum promotion. Full-original-source tests run in GitHub CI; local fixture tests alone are insufficient.

A successful local test is not an E-CPU host-authenticated event or a peer-replicated recovery certificate. For cross-observer durable state use the actual existing E-CPU recovery services rather than interpreting this simple local Chronicle as a substitute.


## RCG-005 — nonlinearly conjugated observer-host computation (2026-11-16)

[RCG-005 nonlinear_orbit](nonlinear_orbit/README.md) extends the corrected **body = E-CPU observer-hosts/communication paths; mind = procedural synthetic neural Grounds** architecture. The real source-pinned connectome supplies a heterogeneous topology, not animal dynamics. An exact full-vector Krylov annihilator makes multiple nonlinear readouts share one distant-time polynomial navigation, and [training curriculum v4](training_tracks_v4.json) records measured-transport and evidence-gated development directions. The executable local Ground, independent receiver-checkable capsule, scaling experiments and a native E-CPU mTLS four-host hard-kill/rehome gate are in the new subfolder. It introduces **no** parallel transport, Hypervisor, quorum, scheduler or durable Chronicle; mTLS and full original-source hosted checks remain pending exact-head CI.
