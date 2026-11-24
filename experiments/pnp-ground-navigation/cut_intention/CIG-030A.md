# CIG-030A — Demand-directed mathematical memory portfolios

Continuation of CIG-028B and CIG-029A; complementary to the parallel CIG-028/029 continuous-processor work. Reuses actual source-qualified CIG-019/021/024 diagrams, CIG-025 exact rank, CIG-028B partial rank, and CIG-029A phase anchors and checker. CIG-013 anticipatory structural memory and Navigable-Compute NCR-009 costed representation portfolios motivate the acquisition/retention accounting. This local experiment implements no distributed authority.

## Mathematical facts and receiver transitions

For the admitted eventual-periodic Boolean intention with transient length D, period P, transient event count B and N events per period, retain A(p)=R(D+p)-B for 0<=p<=P. Endpoints A(0)=0 and A(P)=N are permanent. For ordinal k>B, write k-B-1=qN+j-1 with 1<=j<=N. An exact selection t=D+qP+p proves A(p)=j-1, A(p+1)=j. The receiver verifies the original CIG-025 or CIG-028B selection proof before adding both anchors. Adjacent admitted ranks are sufficient to derive the time of that event in any admitted period without any predicate evaluation. A compact hit receipt is {index,phase}; ordinal is separately supplied to receiver. The CIG-029A local route can extend one exact anchor by bounded scan. A partially completed local scan may preserve exact progress. CIG-028B partial selection is optional; when enabled it is attempted only in absence of a retained full basis. If the signed expansion refuses, the unresolved request remains UNKNOWN. It is not treated as unreachable.

`PortfolioReceiver.open_rank(packet)` independently constructs CheckedRank from the admitted original diagram. Many subsequent select receipts can use the same checked basis. `close_rank()` removes the basis; `admit_exact()` then refuses until a new basis has been checked. `retain(phases, capacity)` only permits a subset of existing anchors, with endpoints and the caller's declared capacity enforced for that operation. The paired driver trims on query/batch completion and synchronizes producer and receiver anchor books. The capacity is a logical interior-anchor count; temporary additions, source diagrams, work buffers, Python object metadata and the exact basis are separate. The receiver is scoped to an admitted output, not an isolated authenticated server. No hard memory cap or durable recovery is claimed.

## Planning and cost policy

For residual j and an exact anchor with rank r, the necessary number of event crossings is d(j,r)=j-r if r<j, else r-j+1. A scan of length s cannot cross more than s events; if every anchor requires more, skip the scan. A density heuristic estimates phase distance ceil(d P/N); it is not a guaranteed bound for nonuniform events. The forecast planner evaluates up to 256 distinct supplied residuals using weighted coverage, capped by the declared full-route cost and scan threshold. Greedily add a candidate seed if predicted weighted savings exceed seed and retention prices. The executed batch acquires each candidate from a single admitted complete rank basis, with each selection independently verified. The policy is not a globally optimal solver. False forecasts affect cost, never correctness.

For a bounded interior anchor book, demand retention greedily minimizes weighted event distance from the last 64 residual requests (and declared forecast at batch trim), using recency for tie-breaking; LRU is a control. Actual scans can be slower for sparse or nonuniform sets, so exact fallback remains important. Full mode disables local routes and keeps zero interior anchors. A complete expansion can be retained, made ephemeral, or adaptively released. In adaptive mode the measured mean compilation+audit time C_ns and recent fraction m/w of queries needing full fallback are compared against a supplied ns-equivalent retention price lambda per serialized basis byte per query:

    drop if (m/w) * C_ns < lambda * serialized_rank_bytes

A complete window is required. This is a myopic empirical choice, not a guarantee on future workloads or measured physical memory costs. Serialized-byte-query residency samples state at query completion; it excludes transient peak usage and is not byte-seconds. Direct-hit receipts reuse an independently qualified local phase proof, not an authenticated communication protocol.

## Usage campaigns

Seeded parity circuits are constructed from shuffled original CNFs with independently qualified block transport, using 60,174,384,1023 observation bits. At largest: 3084 Boolean variables; period 614889782588491410. The marker-parity oracle uses independent inclusion-exclusion and checks BOTH adjacent chronological ranks for each output, including huge period coordinates near 10^900. A sparse conjunction control uses a separate marker congruence count oracle. Cases: clustered residuals; moving/drifting residuals; three recurring clusters; uniform draws; one regime shift; repeated residuals. Each measured run has 24 queries. Forecasts are independent seeded samples with same regime or deliberately wrong, not future query access; forecast acquisition costs included. Cold common source preparation is separately charged in ledger. `CIG-030A-results.json`: 137 runs, 3288 checked outputs, original implementation before residency accounting. `CIG-030A-adaptive.json`: 9 runs, 216 further checked outputs after adding adaptive policy and residency accounting. `CIG-030A-regimes.json`: 6 runs, 168 further checked outputs, hold-out hot/cold/hot (10 repeated, 8 scattered, 10 repeated), also compares actual direct CIG-025 Rank + CheckedRank without portfolio overhead. Total 152 measured runs, 3672 outputs. Historical single-run timings are not expected to reproduce exactly; all shared source construction is excluded from post-source elapsed comparisons.

Largest original campaign, total producer+receiver ms, including all per-policy preparation:

|Workload|Full|LRU|Demand|Declared forecast|Wrong forecast|
|---|---:|---:|---:|---:|---:|
|Clustered|1673.74|251.17|201.53|199.49|311.23|
|Drifting|1610.53|287.64|205.86|312.12|264.88|
|Recurring|1631.71|376.20|330.66|381.22|549.24|
|Regime shift|1723.61|256.83|310.92|252.62|324.53|
|Uniform|1808.67|1858.42|1717.99|1803.45|1758.17|
|Repeated|1795.84|248.18|193.36|231.95|333.74|

All 24 recurring requests use local routes with a declared forecast; three seeds acquired in a single full-basis audit. Demand has three full selections instead and is faster including acquisition. A forecast is therefore optional. Demand resolves 23/24 clustered, 23/24 drifting and 23/24 repeated without complete selection; uniform needs 24 full selections. Repeated residual: 23 direct adjacent-anchor hits with no predicate evaluations. At small sizes the simpler full route can be cheaper. Sparse single-event control at 1023 bits: full 3.37 ms, demand 2.00 ms, 23 direct hits. No universal rank acceleration claim.

Adaptive accounting on largest clustered/uniform/repeated runs: exact basis 410728 canonical serialized bytes. Demand retain samples 9857472 byte-queries each. Moderate adaptive price (5 ns-equivalent/byte/query) releases the basis on clustered and repeated cases, retaining 3285824 sampled basis byte-queries; uniform retains all 9857472. Uniform ephemeral opens/audits basis 24 times (9857472 bytes of serialized proof packets), versus once for retain/adaptive. Elapsed uniform: retain 1780.73 ms, adaptive 1823.39 ms, ephemeral 5379.71 ms. Clustered after completion: 527 serialized anchor bytes plus original mathematical admission (not included). Retained full rank bytes are zero only in the released route, not all system memory.

Hold-out hot/cold/hot (28 requests), largest source:

|Mode|Price (ns-equivalent)|Total ms|Basis admissions|Basis byte-queries|
|---|---:|---:|---:|---:|
|Direct CIG-025|0|1883.59|1|11500384|
|Retain|0|783.68|1|11500384|
|Adaptive|0|756.82|1|11500384|
|Adaptive|5|998.51|2|9446744|
|Adaptive|500|1985.14|9|2875096|
|Ephemeral|0|2183.72|9|0|

All methods agree. The moderate price causes a re-audit after the cold regime begins and eventual release after recurrence. High price can prefer memory savings at substantial runtime cost. The retention price is a choice, not a measured network or memory latency. The initial common source construction at 1023 bits in the original clustered campaign was 649.83 ms. It is not erased by warm reuse.

## Verification and reproduction

384 tests pass in local predecessor stack (375 prior + nine new). New random usage: 60 independently qualified small irreversible/reversible laws, two outputs, three policies, nine ordinal queries each; 3240 comparisons with explicitly stepped source orbit, including huge ordinals and transient/unreachable cases. Other tests include malformed rank basis, invalid or absent anchors, wrong ordinal/root, rejected retention preserving prior state, full budget refusal with local recovery, batch basis reuse, adaptive close/reopen. No test of the parallel CIG-026/027/028/029 availability suite in this local bundle, no physical distributed execution. The retention book is in-process; durable proof-qualified recovery and cross-repository host-authority integration remain To Do.

```
python -m unittest discover -s . -p 'test_*.py' -q
python run_anchor_portfolio.py --sizes 60 174 384 1023 --count 24 --output reproduced.json
python run_anchor_regimes.py --bits 1023 --labels hot_cold_hot --output reproduced-regimes.json
```

The final runner includes adaptive and residency accounting not present in the initial 137 runs. In constrained environments split runs by size/labels using `run(k,24,labels=...,modes=...)`; the historical ledgers preserve original evidence. Timing includes producer/independent receiver and planning, but excludes the separate independent oracle's comparison time. Next experiments: rank-range evidence shared across related intentions, proof-qualified checkpoint recovery, cost-aware host placement using existing E-CPU authority (not a new quorum protocol).

## Publication record

The five executable modules were matched against their locally tested Git blob identities. This repository revision includes the mathematical record, final regression log and reproducible runners. The complete three measured JSON ledgers are bundled in the locally exported CIG-030A_adaptive_mathematical_memory.zip research package; the tables above preserve the principal measured comparisons. Reproduction generates new detailed ledgers. Remote CI evidence is separate from the local regression.
