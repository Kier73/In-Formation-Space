# CIG-033A — Cross-Ground adaptive Seeds

## Research question

Can an exact rank Seed acquired in one source-qualified temporal Ground activate in a different Ground without reconstructing that Ground's rank arithmetic? This extends [CIG-032A](CIG-032A.md) and [CIG-031A](CIG-031A.md), using the actual CIG-019 shared-proof source decoder, CIG-021 independently checked transport and total source section, CIG-024 temporal decision diagrams, CIG-025 rank arithmetic, and CIG-029A/030A retained rank anchors. Related developments: [NCR-008](https://github.com/Kier73/Navigable-Compute/blob/main/docs/NCR-008.md) distinguishes whole-domain observer images from a particular trajectory; [VGI ProofGround](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/docs/PROOFGROUND_NAVIGATION.md) retains verified future-observation equivalences. [E-CPU IPS-006](https://github.com/Kier73/E-CPU/blob/main/docs/DISTRIBUTED_GENERATED_GROUND_IPS006.md) provides an existing distributed recovery integration opportunity. This increment is a local proof-qualified utility, not authenticated network migration.

## 1. Uniform bridge

Let old and new total-image transports satisfy `T_old(u)[j]=F_j(u[p(j)])` and `T_new(v)[l]=F'_l(v[p'(l)])`. Let `a` inject old locations into new locations and `h_j` be a surjective map from the new local alphabet to the old. Define `phi(v)[j]=h_j(v[a(j)])`. Verify for all old locations j and all new local symbols x:

```
p'(a(j)) = a(p(j))
h_j(F'_{a(j)}(x)) = F_j(h_{p(j)}(x))
phi(v0) = u0
O_new(v) = O_old(phi(v)) for all v in the new observation cube
```

The first two equations prove `phi T_new = T_old phi` on the whole cube. Surjectivity of local maps and distinct mapped locations prove surjectivity of phi on the whole cube (not necessarily a bijection). Total source sections ensure every observation code in both cubes is realizable in the original respective source CNFs. The last equation is proved by translating both actual source-qualified decoder cones into a common reduced ordered multi-valued diagram over new local-symbol variables. These variables are independent, not CRT time coordinates. The producer's canonical reduction is checked by `verify_temporal_algebra.Checked`: explicit input atoms, signed-literal complements, Boolean gate relations, and identical canonical output roots. No old or new global observation cube is enumerated. Equality of the selected observation streams follows for every t by induction.

`cross_ground_seed.discover` searches a finite grammar of signed bit projections (permutations of distinct new bit positions, with inversions) and rotations of equal-length spatial cycles. Sparse port correspondences `(old block, old bit, new block, new bit, invert)` guide the search. The full location/symbol maps are not supplied. For each aligned ring, initial symbols and port constraints filter domains; lookup by composed successor table joins neighboring domains, and a ring-closing check selects a compatible path. Distinct old rings are assigned greedily to distinct new rings, pinned first. It can miss a possible bridge (different ring matching, alternative symbol maps, or outside the signed-projection grammar). It returns UNKNOWN on refusal, including when the discovered map fails full-cube decoder equivalence. The checker accepts any valid surjective local map with the above equations, not merely signed projections. Discovery work charges table generation, candidate filtering by local alphabet size, rotations and candidate compatibility; diagram work charges arcs/operations. Python path copies, bit arithmetic, port scans and source proof construction are not represented fully by these abstract counts. Wall time measured separately. Uniform verification checks every local symbol and independently audits the output decision diagram under its work budget.

```
proposal = discover(old_receiver, new_receiver, 0, 0, ports=ports)
assert proposal['status'] == 'FOUND'
bridge = BridgeAdmission(old_receiver, new_receiver, old_algebra_receipt,
                         old_memory_receiver, proposal['proof'])
rank = old_memory.book(0).compact(ordinal, budget=128)
packet = dict(bridge=bridge.key, output=0, ordinal=str(ordinal), rank=rank)
answer = bridge.accept(ordinal, packet)
```

The bridge verifies both source/initial identities, re-admits the old algebra from its receipt, matches the previously admitted old book to the qualified output/prefix/node prefix, then uses native CIG-029A compact ordinal receipts. The caller updates the producer book only after acceptance. No new target rank proof or target temporal algebra is required for this route. The benchmark independently checks terminal new-receiver results, outside both measured selection routes. Old and new source qualification are explicit costs. The old rank book must already be independently admitted; CIG-032A recipes can reconstruct it in a fresh receiver (tested). A bridge digest alone is not authority. The receiver objects are trusted local objects as in predecessor CIGs; this does not establish adversarial process isolation or a durable distributed commit protocol.

## 2. Trajectory-only bridge (different state topology or width)

Some new processors cannot realize a full old-state projection but still have an identical or shifted observation stream. Independently admit each Ground's own CIG-024 diagram and transient prefix. For an offered nonnegative delta, verify

```
B(t) = A(t+delta), for all t >= 0
R_B(t) = R_A(t+delta) - R_A(delta)
Select_B(k) = Select_A(k + R_A(delta)) - delta
```

The equality test examines the finite prefix `t < max(D_new,D_old-delta,0)`, then synchronizes the two reduced temporal diagrams over the union of their prime-power coordinates. At a common prime p, branch over the maximum of the two powers of p; old arc index `(r+delta) mod b_old`, new arc index `r mod b_new`. Missing coordinates do not constrain the corresponding root. The shared basis would be the factorization of `lcm(P_old,P_new)`; only reachable pairs of decision nodes are explored, not its product. The old and new diagrams are source-qualified separately. This proof is about the declared pair of initial trajectories, not about other states. The independent receiver implements recursive synchronized traversal; the producer uses an explicit stack, visited pairs and bounded shift palette. Both have explicit traversal budgets; budget exhaustion or unrepresented shift is UNKNOWN. The equality proof can be expensive on general unrelated diagrams. The offset rank must already be independently known (prefix or retained phase anchor). The 4096-bit existing time/ordinal contracts remain; an out-of-contract translated ordinal is refused. `TrajectoryAdmission` reconstructs both admitted algebras and reuses the existing old book. No target signed rank construction is needed.

Small control: old two locations with swapping bits, new one location cycling through four symbols. Old initial output sequence is 1,0,1,0,...; new 0,1,0,1,... . No injection of two old locations into one new exists. The shift bridge discovers delta=1 and proves new Select(k)=2k-1. Another control verifies equality for initial zero states even when other initial states disagree, and refuses uniform signed projection. A transient-only old event removed by the shift yields an empty new set. In contrast to the uniform map route, trajectory equivalence cannot authorize arbitrary new initial states or a different selected output.

## 3. Measured usage

`run_cross_ground_seed.py`: original 3-bit symbols, independently compiled new 4-bit symbols with hidden shuffled spatial locations and local signed encodings, irreversible extra bit (initialized then drained), unrelated four-location cycle. One port correspondence per original spatial cycle (all live marker inputs); no full map supplied. Original parity Seed has 16 interior anchors. All 64 ordinals near period 10^900 checked against native new CIG-025, independent original marker arithmetic and new CIG-021 terminal receiver. The 1023->1380 attempt exceeded the inherited 1024-observation decoder admission budget; the runner now records preflight UNKNOWN for this expansion. Largest admitted pair old 756/new 1024; 14 ports, 252 mapped locations, 256 new locations, 259 full-cube diagram nodes. The receiver checks 4032 local symbol commuting equalities. Periods 304250263527210 and 608500527054420; D=0 and D'=1. 783799 charged mapping units, 4681 diagram units, 27937-byte bridge. Timings in ledger: new source 1929.14 ms shared by both routes, original source 578.27 ms and old seed 87.24 ms separate; discovery 11.88 ms, bridge admission 18.76 ms, 16 warm results 3.25 ms, fresh new algebra/rank preparation 82.94 ms plus selection 544.79 ms. Full bridge route ~33.89 ms vs ~627.73 ms excluding shared new source admission and existing old source/Seed preparation. With seed acquisition ~121.13 ms; starting from scratch with old source preparation as well ~699.40 ms, so fresh is preferable in this particular cold comparison. Small workloads also favor fresh selection. The local rank-query packet intentionally repeats the caller's ordinal for binding; `query_bytes` is not total communication or memory.

`run_trajectory_bridge.py`: original three-bit nonlinear transport, new one-bit marker-only ring transport with shuffled labels and unrelated independent four-location ring, initial code advanced one original step. Two new source-qualified outputs; discovery receives no port correspondences, only the two selected output indices and a shift palette (0,1,2,3). It discovers shift 1 and refuses transfer to the unrelated second output in all four workloads. Largest pair original 1023 and new 345 bits, periods 614889782588491410 and 1229779565176982820, respectively. The width-reducing pair is outside the uniform surjective projection grammar. 994 charged discovery units, 0.624 ms discovery, 23.616 ms re-admission, 2.604 ms warm 16 ordinal results (73 local phase evaluations). Target source preparation 78.377 ms, new algebra qualification 14.940 ms shared, fresh target signed rank setup 204.768 ms and 16 selections 1516.170 ms. Fresh signed representation 24575 terms, 629908 serialized bytes; retained original anchor map after use 1319 bytes, not including source diagrams, proofs, or other runtime memory. Total additional bridge and query time ~26.84 ms versus ~1720.94 ms (64.1x). Original Seed acquisition 259.497 ms separate; original source plus algebra preparation 690.475 ms separate. All 64 contracted-target ordinal requests match fresh selection, separate marker-level arithmetic and terminal new-source execution. The independent oracle/terminal check time is recorded separately and excluded equally from the two selection timings. The chosen clustered workload is favorable to anchor reuse. No universal speedup, physical energy measurement, or P versus NP conclusion follows.

## 4. Validation and reproduction

```
python -m unittest test_cross_ground_seed -v
python -m unittest discover -s . -p 'test_*.py' -q
python run_cross_ground_seed.py
python run_trajectory_bridge.py
```

Nine new test methods: 80 randomized qualified uniform-law pairs, exhaustive small full-cube checks or sampled larger codes, 100 randomized pairs of unrelated temporal laws with three shift candidates each compared against exhaustive prefix + common-period trajectories, adversarial maps/atoms/source/output and receipt substitution, budget refusal, restored CIG-032A recipe, no-hint control, trajectory-only vs uniform scope and removed transient event. 128 ordinal results in the two measured campaigns, all independently verified. The regression suite is the 401-test local predecessor stack plus nine tests (parallel CIG-026/027/028 availability branches not part of this local stack). See regression log and the two measured ledgers.

## 5. Next development

Compose admitted bridges into a source-bound Ground graph. Qualify the exact scope (uniform map, trajectory equivalence, shift, partial output relation), preserve anchor and source identity at every edge, and select a route whose discovery, qualification, restoration, communication and execution costs are measured. A useful experiment: transfer rank knowledge across three or more distinct Grounds with composed shifts, then reuse a compact Seed on a previously unencountered Ground. Integrate actual E-CPU authenticated recovery/fencing after the mathematical graph is verified locally, rather than treating local receipt acceptance as distributed authority.
