# CIG-034A — Navigable network of exact temporal Grounds

## Architecture and cross-repository consolidation

Uses CIG-021 source-qualified transport, CIG-024 admitted temporal languages, CIG-029A compact ordinal anchors, CIG-032A Seed restoration, and CIG-033A cross-Ground trajectory equality. The new dependency-free `ground_network.py` and `ground_network_verify.py` are identical to the consolidated Navigable-Compute kernel. `seed_network.py` is the IFS-specific adapter; it independently reconstructs CIG-024 Admission for each original output, snapshots the reachable reduced diagram and binds its identity to the source receiver key, initial code and output index. Attaching a Seed requires matching producer and checked observation snapshots. No unrelated external proof or physical host authority is admitted.

## Exact suffix edges

An edge points from a new target B toward a reusable source A, and admits B(t)=A(t+d) for t>=s, with s>=0 and s+d>=0. Signed shifts are supported. This extends CIG-033A's whole-trajectory nonnegative shifts: prefixes may differ. Let a=R_A(s+d), b=R_B(s). Then R_B(t)=R_A(t+d)-(a-b) for t>=s, and a target ordinal k>b becomes source ordinal k+a-b. A certified source destination gives the target destination after subtracting d. An earlier event k<=b is not eligible for this edge. Both finite prefix ranks and the synchronized CRT-tail relationship are independently verified. The bounded discovery grammar tries supplied (shift,cutoff) candidates; it does not enumerate every possible shift, cutoff or relationship.

## Path composition is an independently qualifiable mathematical resource

For a path from target to reusable Seed with edges i, define prior cumulative shift D_i and rank offset H_i. Let S=max_i(s_i-D_i), D=sum_i d_i and H=sum_i h_i. If a is any active cutoff index attaining that maximum, the new target prefix rank is b_a-H_a. The new source prefix rank is b_a-H_a+H. These exact facts establish a derived edge with shift D, cutoff S and offset H. The producer finds the active cutoff; the independent checker composes pairs and verifies the summary. It needs no fresh endpoint rank or diagram comparison. Constituent edge IDs are retained as proof provenance in the local graph. This is not durable/authenticated host recovery.

`Network.plan` uses nonnegative declared costs over bounded walks, keeping translated ordinal, displacement and hop count in its state. `SeedNetwork.activate` quotes endpoint costs from the actual retained rank books; rank-distance estimates guide selection but cannot authorize results. It asks the selected producer book for a compact ordinal receipt, checks the actual CIG-029A receiver, and independently replays the admitted path. An unresolved local attempt may retain valid progress; another endpoint/ordinal can be tried. No path or exhausted proof budget returns UNKNOWN. The native core also provides standalone exact CRT rank selection for callers not using CIG.

## Direct usage

The benchmark constructs three separate source-qualified CNF/transport processors. A retains the original 3-bit-block nonlinear marker fixture; B contracts to one bit per block with an independently moving ring and a one-step displacement; C contracts similarly, adds another ring and an irreversible one-step bit in the actual source output, with displacement three. The source languages and temporal diagrams are independently constructed, not asserted by fixture naming. A receives 16 exact interior phase anchors under the CIG-032A-style rank preparation, then retains only the book. Discovery admits A-to-B and B-to-C edges. B-to-C is only valid from t=1 because of the extra transient. A direct A-to-C edge is qualified separately as a control. Declared edge prices 3+4 versus 20 select the two-hop route; a verified shortcut of price 1 subsequently selects the composed edge. These are controlled cost units, not learned physical latency estimates.

Each scale submits 16 ordinal requests near period 10^900, then 16 more in different periods at the same residual ranks through the shortcut. The first 16 agree with fresh CIG-025 exact rank selection and independent admission on C. All 32 agree with an independent marker inclusion-exclusion oracle and actual CIG-021 target terminal receiver. Large source common periods: A=614889782588491410, B=1229779565176982820, C=614889782588491410. The combined shift is 3, cutoff 1, offset 0 for this fixture (other scales have offsets 2 and 3).

Final measured campaign (ms; all timings empirical, no timing asserted as mathematical invariant):

| A -> B -> C observed bits | Fresh C rank setup + 16 queries | Two-hop verified queries | Shortcut verified queries (second, reused phase workload) | Direct edge discovery+check | Composite proposal+check |
|---|---:|---:|---:|---:|---:|
| 60 -> 24 -> 27 | 0.727 | 2.101 | 2.209 | 0.077 | 0.045 |
| 174 -> 62 -> 65 | 4.231 | 2.387 | 2.433 | 0.231 | 0.054 |
| 384 -> 132 -> 135 | 28.118 | 2.638 | 2.534 | 0.398 | 0.070 |
| 1023 -> 345 -> 348 | 1166.210 | 3.222 | 2.566 | 1.181 | 0.089 |

At largest scale, 48 expanded route states for the 16 two-hop queries, 32 for the shortcut; 73 local phase steps in the first group, 30 in the second (anchor reuse also contributes, so warm difference is not an isolated shortcut speed comparison). The serialized retained anchor map is 1,747 bytes; excludes diagrams, admission/verification state, working memory, path receipts and code. Fresh rank timings include CIG-025 independent rank verification. Seed query timings include path planning, checked endpoint receipt and path replay. Terminal and independent marker oracle audit (2253.51 ms at largest scale) is recorded separately and applies to the transferred outputs; fresh queries already have their own native checked rank results. No full end-to-end timing advantage is asserted including these separate audits. The source setup at largest scale: A 780.99 ms, A Seed 218.18 ms, B source 96.81 ms, C source 102.10 ms, graph re-admission 37.84 ms, two edge discovery+checks 1.85 ms. Constructing all Grounds and Seed from scratch costs much more than warm transfer; small cases favor direct rank. The fresh direct edge control was separately paid and is not required by composite qualification.

## Verification

420 tests in the local CIG predecessor stack (410 prior + seven shared kernel + three native CIG adapter tests). This stack excludes parallel CIG-026/027 and CIG-028/029 branches with separately qualified workflow contracts. Shared kernel tests: 240 random language pairs with 720 exhaustive signed-suffix comparisons; 160 random compatible three-edge chains and independently checked composite edges; 60 random costed graph checks against exhaustive bounded walks; invalid bases and nodes, forged path, rank/offset/eligibility, budget controls, signed delays, cycles, finite and large sparse events. Adapter tests use actual proof-derived CIG languages, restored Seeds, request mismatch refusal, multi-hop activation and finite exhaustion. Native kernel and checker test bytes differ between the repos only in test import paths; the two implementation modules are identical. Remote CI separate.

Reproduce:

```sh
python -m unittest discover -s . -p 'test_*.py' -q
python run_seed_network.py
```

Next: learn edge candidate ordering and prices from observed usage; preserve independently replayable graph evidence with durable source admission and E-CPU authority; explore selective graph contraction and generalized affine observation identities. Physical resource and energy measurements remain future work.