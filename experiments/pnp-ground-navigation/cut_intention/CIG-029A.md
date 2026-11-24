# CIG-029A — Retained exact temporal rank anchors

Parallel continuation of [CIG-028B](CIG-028B.md), the demand-directed partial-rank experiment integrated through PR #360. The suffix avoids colliding with other temporal-capacity and availability research. Uses actual CIG-024 admitted diagrams, CIG-025 signed rank, CIG-028B partial checker, CIG-019 shared decoder, CIG-021 transport and constructive source section. VGI sparse partial evidence and E-CPU structural memory motivate the reuse; no distributed authority is asserted by this local implementation.

## Mathematical construction

Let D be the finite transient cutoff, P the common period, N the count of accepted phases per period, and B the exact number of prefix events. For 0<=p<=P define A(p)=sum_{j=0}^{p-1} I(D+j), with A(0)=0 and A(P)=N. For t>=D, t=D+qP+p, 0<=p<P:

    R(t) = B+qN+A(p).

A retained anchor is an exact pair (p,A(p)) scoped to the receiver's admitted language and output index. It is reusable at every period. An interior seed is constructed using a CIG-025 full signed proof or an EXACT CIG-028B partial proof. The independent receiver reconstructs the proof before retaining the pair. The full signed expansion is not stored by the anchor books; the benchmark keeps it separately for comparison. This is an amortization technique, not a faster general method of acquiring an arbitrary first interior seed.

For a<=p<=b with admitted anchors (a,l),(b,r), monotonicity and unit increments imply:

    max(l,r-(b-p)) <= A(p) <= min(r,l+(p-a)).

The receiver verifies both inequalities with exact arithmetic. No point evaluations are required for this comparison. Intersecting with additional admitted anchors tightens these bounds. For an exact local translation, count only the interval between a known phase a and the requested phase p, adding or subtracting from A(a). The receiver re-evaluates each phase in the bounded interval independently on its own admitted MDD. If the budget is exhausted, the endpoint and exact accumulated rank can still be admitted; UNKNOWN is not a claim of unreachability.

For one-based ordinal k>B and N>0, write k-B-1=qN+j-1 with 1<=j<=N. Choose the last retained anchor with rank<j or the first with rank>=j. The producer chooses between these using event distance then a density-based tie break. Walk forward from the lower anchor or backward from the upper one, stopping at the j-th event or the scan budget. Exact phase p is accepted only if A(p)=j-1 and A(p+1)=j. The destination is D+qP+p. A failed local search admits exact progress if the independent interval count matches. There is no requirement to use the producer's search heuristic on the verifier. With positive scan budget, continued local exploration advances the bracketing anchors, but worst-case work can approach a period. Use CIG-025 or CIG-028B for far-away queries instead. The conservative 4096-bit guard admits the whole target period; a period crossing this guard refuses even if some individual times might fit.

## Receipt semantics and local API

```python
from rank_anchors import Anchors
from verify_rank_anchors import CheckedAnchors
from temporal_rank import Rank
p = Anchors(language, 0)
v = CheckedAnchors(admission, 0)
seed = p.seed(p.P//3, exact=Rank(language, 0))
assert v.admit_seed(seed)
p.commit_seed(seed)
# One-based ordinal, supplied independently to the receiver.
z = p.compact(k, budget=128)
result = v.admit_compact(k, z, budget=128)
if result is not None:
    p.commit(z)
# result is FOUND with the derived time, or UNKNOWN with exact admitted progress.
```

A compact receipt omits absolute ordinal and time; the caller supplies k, the receiver reconstructs q,j and verifies the phase. The same residual-ordinal proof can deliberately be reused in another period. A distinct residual ordinal is rejected unless the local proof actually establishes it. The request and source admission are still required; this is not transport authentication, signed authority, durable checkpointing or replay protection. Those can use existing E-CPU mechanisms in later work. Local admission failures do not mutate the anchor book; the producer commits only after receiver acceptance. The books are scoped to the original admission and output. Wire accounting measures serialized JSON response only, not request, transport framing or total process memory. The compact producer currently constructs the full result internally then omits large fields from the response.

## Executed campaign

Four actual source-qualified parity circuits, using the marker transport fixture from CIG-022/023. At each size seed phase floor(P/3), acquire its exact rank, then request 32 ordinals within a declared rank neighborhood (radius min(32,N//10), at least 1) across different period indices near 10^900. Each returned time agrees with CIG-025 and with an independently constructed marker inclusion-exclusion oracle at both adjacent ranks. The comparator is the existing complete signed-rank selector, not an optimized alternative anchor index. All methods share the source-qualified diagram preparation. The full proof and seed costs are separated. The local method is intentionally tested with clustered, repeated phase intentions; far-phase and cold controls demonstrate the limit of this policy.

| Observed bits | Period | Local phase evaluations (32 queries) | Full producer+receiver ms | Anchor producer+receiver ms |
|---:|---:|---:|---:|---:|
|60|210|101|1.282|2.984|
|174|510510|246|5.891|3.697|
|384|446185740|241|41.672|3.629|
|1023|614889782588491410|247|1895.856|6.408|

At 1023 bits: 3,084 source variables; 16,384 signed terms; source/transport/proof preparation 391.21 ms shared. Full signed construction 38.374 ms and independent admission 114.313 ms. Anchor setup 0.159+2.004 ms, seed calculation 2.807 ms, seed verification 70.740 ms (separate run of full proof checker); the anchor route additionally requires the 38.374 ms full construction in this test. Total measured post-common-source cost 120.49 ms versus 2048.54 ms for the complete rank route. These single-run timings fluctuate; independent verification is included. Largest scan 60 phases in a query. Seed receipt 410,821 bytes. Final 35-anchor coordinate map 1,367 serialized bytes; excludes full original diagram, transient, Python object overhead, receiver metadata, proof history, temporary seed construction and external archives. Compact query responses total 3,944 bytes; baseline full-rank responses 30,656 bytes. Initial seed transmission can dominate this short workload, so compact responses are a warm communication advantage only. A cold interior query and an unrelated distant phase query both returned UNKNOWN under 128-phase budget at 174,384,1023 bits; their partial progress was independently admitted. At 60 bits local scanning resolves them but exact rank is cheaper overall.

32 additional nearby comparison requests use only anchor inequalities, no point evaluations; 13 are decisive (five exact) at largest scale, the remaining 19 retain sound uncertain intervals. This does not solve arbitrary interior rank. Next: a cost-aware portfolio that chooses where to acquire anchors, amortizes multiple seeds under one checked proof, uses CIG-028B interval refinements or complete signed rank for distant requests, and evicts redundant anchors under a declared storage budget. Durable source-bound anchor recovery can then connect to availability and E-CPU receiver authority.

## Verification

375 local tests passed (364 predecessor-stack + 11 new), including 100 randomly generated source-qualified laws, three outputs per law including a shifted expression, transient-only sources, exact seeds from both methods, forward/backward progress, zero-budget UNKNOWN, huge ordinals, forged bounds, malformed proof and wrong residual ordinal. The local stack does not include the parallel CIG-026/027 or availability research; remote CI is separate. The source and receipt checker are independent code paths using CIG-024's separate admitted MDD. No claim of universal rank compression, arbitrary polynomial-time SAT or physical computation acceleration.

Reproduce in the CIG directory:

```sh
python -m unittest discover -s . -p 'test_*.py' -q
python run_rank_anchors.py --sizes 60 174 384 1023 --output CIG-029A-results.json
```
