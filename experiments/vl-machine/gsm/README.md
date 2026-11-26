# GSM-001 / GSM-002 — Generative Structural Memory and structured attention

Parallel development alongside the VLM mathematical research. Learn how to navigate source-resident information, and study how exact structural knowledge can change a neural operator's input and execution path. The experiment is inspired by the compact llm.asm inference/training substrate; no llm.asm code is imported and its assembly trainer is not yet used. Actual numerical training is hosted CPU PyTorch 2.10.0.

## Experience Ground

A task contains a source identity, addresses of eight derived records (two-byte key and four-byte payload), query key, relative byte coordinate and case kind. Every field is recovered from pinned source ranges. Ambiguous tasks deliberately reuse the key address while retaining another record's payload address. Absent keys are constructed outside the episode's key set, not claimed absent from the original source. These are synthetic record views rather than general semantic parsing, and label generation is independent of the learner. Distinct source identities across training, validation and final phases: actual VLM code and the VLM-011 ledger/catalogue, generated multilingual UTF-8 and synthetic binary sources containing all 256 byte values. Source identities do not imply absence of shared content or generalization to linguistic semantics. All sources are loaded into host memory; logical range bytes are counted, not physical I/O, remote fetch or network traffic.

The model has 28,738 allocated parameters, d=32, four attention heads, one encoder layer and a pointer/reject output head plus corpus vocabulary head. Different objectives activate different parameter subsets. The query contains the key and relative offset; candidate tokens encode keys, payload byte and offset. Dense input has 1+4N token positions. The sensor route adds exact key equality but retains the dense sequence. Gathered routes select the actual matching records before tensor construction, at most two in the initial task grammar; a padded batch has nine positions. No claim of exact preservation of arbitrary dense softmax, of causal language-model equivalence, or of general Transformer acceleration. Corpus control uses the same allocated architecture and an ordered 32-byte context to predict its next byte, not a full causal decoder or matched navigation supervision.

## GSM-001

Two initialization seeds, each 180 AdamW updates, 48 examples/update; identical training episodes for fixed navigation policies, adaptive policy adjusts task-kind mixture based on validation errors every 45 steps. The corpus control has no navigation labels; it is an objective-transfer control, not an apples-to-apples comparison with supervised navigation. Token budgets deliberately differ because gathering changes computational extent. Held-out 960 episodes per seed, 326 unique / 328 ambiguous / 306 absent.

| Condition | Seed 1 correct | Seed 2 correct |
|---|---:|---:|
| Corpus only | 25 | 17 |
| Dense pointer | 555 | 529 |
| Dense + equality sensor | 895 | 892 |
| Gathered structural attention | 823 | 936 |
| Adaptive gathered | 634 | 913 |
| Exact direct navigation | 960 | 960 |

Gathered inputs reduce active tokens from 31,680 to 4,888 at evaluation, with nine padded positions instead of 33. Initial adaptation is unstable: seed 1 abstains on every task. This is retained as a failed policy, not excluded from the comparison.

## GSM-002

Use the observed failure to design three new routes: cardinality-aware gathered attention (a query sensor says exactly one matching record exists); stable adaptive curriculum (unique examples at least 50%, nonunique classes at least 15% each); qualified acquisition (read only keys, acquire four payload bytes if unique, bypass the model for absent/multiple matches, restrict the pointer output to the four payload positions). The first two retain neural reject decisions; the third uses exact structural authority for ambiguity only. The model can still choose the wrong relative coordinate: evaluate byte and coordinate independently and count verified non-null proposals. No false answer in the qualified ambiguous/absent cases by construction, not evidence of learned uncertainty. No production admission or security boundary. A deterministic read is a stronger baseline and should bypass the model entirely for this exact task.

Refined models train on original training sources with the same 180 update budget and select checkpoints by coordinate accuracy/false-answer count on the original validation cohort (step 90 for all six refined models). Fixed cardinality and guarded routes are human-designed architecture changes based on observed evidence, not autonomously synthesized architecture search. Fresh final sources are rewrite_ground.py, measured_acquisition.py, new generated multilingual and binary data. Three separate 384-task cohorts at 8, 32 and 64 records; models trained only with eight. Evaluate retained initial models and newly trained models on identical cohorts. Synthetic record keys deliberately disjoint except generated collisions. Aggregate correct out of 768 across two seeds:

| Route | 8 | 32 | 64 |
|---|---:|---:|---:|
| Dense | 473 | 363 | 372 |
| Dense + sensor | 716 | 506 | 508 |
| Gathered | 695 | 694 | 696 |
| Initial adaptive | 639 | 602 | 593 |
| Cardinality | 767 | 768 | 766 |
| Stable adaptive | 768 | 767 | 767 |
| Qualified | 768 | 768 | 766 |
| Direct oracle | 768 | 768 | 768 |

At 64 records, mean of two seed-specific medians (three repeats, includes source slicing, packing and inference, excludes independent scoring): dense sensor 762.511 ms, cardinality 25.301 ms, stable 27.716 ms, qualified 13.983 ms. Exact direct lookup median 7.039 ms over eleven repeats; it wins. Logical acquisition 147,456 bytes full vs 49,748 qualified; all candidate keys still scanned (linear in N), resident source preparation and task generation excluded. Qualified model sees 149 unique cases and skips 235 nonunique cases. Padded attention shape proxy, per head: dense 25,362,816 pairs, gathered 31,104, qualified 3,725. This is a count of sequence-position pairs, not measured FLOPs, physical RAM or a general sparse-attention speed claim. Dense sensor baseline is a simple hosted Transformer, not optimized sparse attention. A stronger deterministic indexed navigator can do better still.

## Reproduce and retain

Run from experiments/vl-machine/gsm with Python 3.13.5 and CPU PyTorch 2.10.0:
    python -m unittest -v test_gsm test_refine
    python gsm.py --root .. --output results --steps 180 --seeds 1 2
    python refine.py --root .. --initial results --out refined

Eight local tests passed, including source identity, pointer correctness, full-byte vocabulary, bounds, backward pass, lazy source reads, arbitrary multiple-match rejection and neural skipping. The report recipe pins sources, cohort digests, report hashes and trained state-dict hashes; full local report/weights are retained as experiment artifacts outside Git, and workflow regenerates them. State dictionaries omit optimizer state; not exact resume checkpoints. Timing/weights not asserted bit-identical across hardware. Final implementation adds strict source pins to the measured refinement. Full existing VLM regression and independent CI not rerun here.

Next: make source selection and attention structure themselves learned proposals; qualify them against dense baselines and source certificates, with deterministic fast-path selection when already-sufficient observations solve the intention. Progress to compositional multi-hop navigation, genuinely ambiguous semantics, unknown operator selection and learned residual computation; include compute for acquisition/verification and equal-token as well as equal-update budgets. Then evaluate on the actual pinned llm.asm training/inference substrate, VL-I causal operators and source-resident VL-64 paths. No actual external model, E-CPU execution, bare-metal training or upstream modifications in this increment.
