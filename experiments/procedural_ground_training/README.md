# PGT-001 — Procedural Ground Training of Intention-Relative Neural Representations

**Status:** directly executed local synthetic model-training experiment; native E-CPU cross-check is CI-gated and has not yet passed on the published branch. Zero public model weights and zero credentials are used. This is not a natural-language model or general AGI.

## Research question and conversation continuity

The work following PyBot (COG-006) acquired relational capabilities, then learned minimal predictive conversation structures (COG-007), revised them with partial counterexamples (COG-008), admitted multi-observer signed evidence (COG-009), and navigated intention-relative Grounds (COG-010). This experiment asks a new, falsifiable question: **can a neural model learn a transferable observation-planning representation from synthetic mathematical Grounds instead of being given the solution as procedural weights?**

Our model learns to recommend `READY`, a minimal subset of three possible measurements, or `REFUSE` (nine output classes), from an observation-relative signature of a finite Ground. This is **supervised optimization** of 20→96→64→9 real-valued neural parameters with AdamW and cross-entropy. It is distinct from IFS SNC's constructive neural compilation, PNF's Net2Wider formation, or E-CPU's existing manually seeded `ProceduralWeightField` and its earlier small trained admission policy.

## Communication topology: what HTTP actually contributes

| Existing implementation | Role in this experiment |
| --- | --- |
| E-CPU `mailcpu/intent_embedding.py` | Advisory structural representation; no new classifier or Hypervisor authority is introduced |
| E-CPU IOS-001 `mailcpu/intention_sufficiency.py` | Exact minimum-cost observation planning; **mandatory native CI oracle** rather than an invented replacement |
| IFS HFR-001 `experiments/external_neural_structure_reading/hub.py` | Pinned HTTPS byte ranges for external model metadata; no unrelated model weights fetched by this training experiment |
| IFS PON-003 read-only HTTP origins | Content-addressed, verified retrieval and failure recovery precedent; the new narrow local `.npz` handler is required because PON-003's fixed object type/12 kB ceiling does not admit this larger weight blob |
| IFS SNC and PNF | Neural parameter provenance, separated mathematical and implementation identities, independent reconstruction precedents |

In HTTP, URL, origin, resource representation, source-ground semantic identity and model parameter identity are **different**. The HTTP server only returns bytes; it neither trains the network nor realizes the IOS Ground. The model's 64-dimensional **learned internal embedding** is created by supervised optimization from exact relational observations. It is not an embedding furnished by an HTTP packet. HTTP is an exchangeable *representation path*.

For this reproducible test, each model source is a separate `http://127.0.0.1:<ephemeral-port>/objects/<weights-SHA256>.npz` service in a real child Python process. The receiver requires its separately supplied manifest and SHA pin, refuses redirects and off-loopback URLs, and limits response bytes. It reconstructs **exactly the same learned model** from the returned array bytes, then matches its predictions. Kill the first origin → second works. Tamper the remaining object → unresolved. These two servers share one machine and admin domain; this is **not independent public CDN hosting, HTTP/TLS encryption, authentication, mTLS or passive-path inference**.

## Synthetic ground generator

The generator creates 16- or 32-state mathematical worlds from Boolean compositions over 4- or 5-bit state coordinates, with three available observable feature projections and one requested Boolean target. For each finite world the provider's whole model is known **to the teacher**, not to the neural student as a latent state. It enumerates every feature subset and admits the least-cost subset by the exact ordering `(sum of symbolic costs, feature count, feature IDs)`. If none suffices, the answer is `REFUSE`. This matches the restricted finite semantics of E-CPU IOS-001 and is compared independently against the native E-CPU module in CI.

The student input is a versioned 20-component vector: two normalized 8-bin histograms over unordered state pairs (same/different target × feature-distinction mask), three measurement costs, and a state-count coordinate. **The teacher's optimal mask, sufficiency bit or target output is not provided as a feature.** The learned 64-unit internal state is a neural embedding of the intention-relative *distinction structure*; it is not a semantic proof or authority grant.

Sources are segregated by generated-world seed, with exact canonical Ground hashes checked for no sample overlap between training, validation, holdout and OOD sets. OOD worlds have twice as many states and an extended function family. This is nonetheless the *same overall finite Boolean task family*. Generalization to real web semantics, natural language, new measurement categories or infinite state-spaces has not been demonstrated.

## Actual local training (Python 3.13, PyTorch 2.10 CPU)

Reproduce:

```bash
python train_ground_model.py --train 10000 --valid 1500 --test 1500 --ood 900 --epochs 35 --batch 256 --output results
python run_ablation.py
python -m unittest -v test_training.py
```

| Measurement | Result |
| --- | ---: |
| Procedurally generated training worlds | 10,000 |
| Validation worlds | 1,500 |
| Unseen 16-state worlds | 1,500 |
| Unseen 32-state OOD worlds | 900 |
| Best validation exact policy accuracy | 99.267% |
| 16-state heldout exact plan | **1,489/1,500 = 99.267%** |
| 32-state OOD exact plan | **876/900 = 97.333%** |
| Insufficient plans proposed (16-state / 32-state) | **4 / 8** |
| Unnecessary `REFUSE` proposals (both sets) | **0** |
| Training and data-generation wall time (local) | **6.493 seconds** |
| Cost-only masked-input ablation on same heldout | **14.467%** |
| Untrained random-initialized model on same heldout | **21.467%** |

These observed mistakes **cannot** be allowed to execute as if the network were a certified navigator. E-CPU rechecks every proposed feature set against the exact admitted model; it rejects insufficient proposals and applies receiver-owned policy before dispatch. A student recommendation may be correct without being authoritative. The exact E-CPU oracle still wins correctness; any claimed performance advantage for neural approximation must be benchmarked separately, including model loading, CPU arithmetic, and trust verification.

In the 16-state heldout, the exact planner's total symbolic selected-measurement cost was 5,135 versus 14,535 if every nonrefused intention naively measured all features; this cost saving belongs to the **exact planner**. The neural student's unverified raw selected cost was 5,121 only because some of its plans were missing necessary evidence. It is not an authorized saving. Similar OOD costs: 3,356 exact versus 8,611 full.

The manifest has source, architecture, encoder, training schedule, and SHA-256 of the actual `.npz` learned tensors. The receiver uses `np.load(..., allow_pickle=False)`, checks parameter keys, shapes, dtype and finite values, and rebuilds the declared architecture; no untrusted code, pickle, checkpoint-specific Python or dynamic imports are run.

## Validation and adversarial controls

- Exact finite planner positive tests: `READY`, cheapest equivalent features and genuine irresolvable hidden distinctions.
- Input representation invariant to arbitrary state-row order; heldout Ground identity hashes disjoint.
- Artifact model imported from an actual HTTP response; byte-identical predictions tested independently of the origin.
- First HTTP process killed, second origin still serves unchanged content.
- Corrupt both sources or change local checkpoint bytes: refuse rather than fabricate learned weights.
- Unsupported network origin, redirects and arbitrary HTTP paths: refuse.
- Native E-CPU suite compares 280 independently generated worlds (16 and 32 state) against the **real** IOS-001 planner. A missing E-CPU import is a test failure in that job, not a permissive skip.

## Next direct frontier

1. Feed *actual* COG-010 partial-observation and network path evidence into the trained embedding, rather than complete synthetic finite tables; preserve ambiguity.
2. Extend the learned policy to choose among finite observation operations, symbolic inverse navigation and reliable HTTP retrieval; prove action selection adds benefit beyond an exact planner.
3. Compare pretraining on different procedural law families (finite-state/LCG/GF2 and HTTP cache/ETag/conditional GET) with held-out law-family transfer and compositional training.
4. Return verified model proposals to E-CPU Hypervisor + IOS-003 `ReliableChannel` under receiver-owned permissions; checkpoint learned weights and replay evidence through existing M1/M3 rather than rewriting authority.

Relevant public research: [Shinnick et al. on modular learned algorithmic structures](https://arxiv.org/abs/2505.22308) and [Kang et al. on synthetic-data composition pitfalls](https://aclanthology.org/2025.emnlp-main.544/). These are context, not citations for the experimental numbers above.
