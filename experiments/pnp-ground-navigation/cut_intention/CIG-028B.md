# CIG-028B — Demand-directed partial temporal rank

## Research question

Can ordinal navigation proceed using only enough admitted mathematical information to decide a rank comparison, rather than compiling the complete chronological rank function? This extends [CIG-025](CIG-025.md) and [CIG-024](CIG-024.md). The concurrently merged CIG-026/027 state-image and capacity research (PR #358) retains its numbering. VGI's sparse partial refinement and three-valued proof obligations motivate the demand-directed route; its implementation is not imported here. The actual CIG-024 source admission, decoder, transport, and diagram are used directly. CIG-025's signed expansion is called only for affordable subnodes (and separately for the full comparison baseline).

## Conditional rank bounds

The qualified decision diagram describes a periodic Boolean function. Each unresolved frontier term is `(v,r,m,c)`: an integer coefficient c times the indicator at node v restricted to t=r mod m. The modulus m uses only earlier CRT coordinates and is coprime to Q, the product of the remaining coordinates at v. The number of integers in the requested interval on this cylinder is n. Compute N, the exact number of satisfying residues in the Q-period, by bottom-up counting. Writing n=qQ+s, the number H of satisfying times on this cylinder obeys

```
q*N + max(0,s-(Q-N)) <= H <= q*N + min(s,N).
```

This holds because the stride m permutes the Q phases; the s residual phases are distinct. No assumptions of independence, equidistribution in a partial interval, or probabilistic inference are used. Terminals are exact. The default-child signed decomposition from CIG-025 is

```
F_v = F_h + sum_{a: child(a)!=h} [t mod b=a]*(F_child(a)-F_h)
```

where h is the most frequent child, with deterministic first-occurrence ties. Bound the unmerged absolute coefficient mass by E(0)=0, E(1)=1 and `E(v)=E(h)+sum_{exceptions}(E(child)+E(h))`. For any cylinder the signed term's rounding discrepancy has magnitude less than one per unit coefficient, including after CRT restriction. Thus `ceil(n*N/Q)-E(v) <= H <= floor(n*N/Q)+E(v)`. Intersect the two bound families. E is a conservative structural bound, not the actual coefficient sum after cancellations. All arithmetic is exact integer arithmetic. The prior finite prefix is counted exactly; complete periods are charged by their exact cardinality; count the shorter of the two complementary residual intervals and subtract if useful.

## Exact frontier operations and verification

An uncertain term can be (1) split into disjoint child cylinders, (2) rewritten using the signed default identity, (3) counted by bounded direct local scan, or (4) evaluated with a CIG-025 exact signed expansion of an affordable subnode. Each operation preserves the represented signed sum. Negative coefficients reverse the endpoints. The producer chooses the widest interval first and chooses the cheaper branch decomposition by estimated child count. It intersects new global bounds with all preceding global bounds, since the naive bound for a signed rewrite can be wider. This gives monotone narrowing for a fixed query and policy when budget is increased. Only requested subnode tables are retained, not the complete root expansion unless the small root itself fits the declared cap. The per-query charged work counts cylinder expansion (arity plus created-term upper count), scanned times, and structural coefficient mass for signed subnode evaluation. It is NOT a wall time, bit-complexity, memory, or total gate-count bound. Initial whole-diagram metadata construction, exact suffix compilation and caches are recorded separately (compiler itself has its inherited 2-million-work budget per subnode).

`PartialRank.compare(t,k,budget=...)` returns EXACT, BELOW, AT_LEAST or UNKNOWN, with canonical integer bounds and replay trace; k=None requests an exact count. The receiver `CheckedPartial` accepts only its own CIG-024 Admission and reconstructs the exact metadata independently, joins CRT classes with the symmetric formula, checks the requested split/scan/subnode method, verifies the trace, and recomputes both bounds. It does not trust search order. There is no claim that partial proof is complete for arbitrary functions under finite budget. The verifier owns the source admission, not a producer-provided digest alone. Results are local receipts, not host authority or network authentication.

For one-based selection, the exact complete-period count locates the period containing ordinal k. The unexpanded discrepancy bounds give a phase interval. When close to an endpoint, try a bounded endpoint-relative rank obligation before binary search; this avoids unnecessarily refining a wide interior rank. At a probe only `upper<k` or `lower>=k` is needed, otherwise return UNKNOWN when budget is exhausted. A final result requires two replayable adjacent comparisons: `R+(t)<k<=R-(t+1)`. Since the exact rank increases by at most one per integer time, these imply `R(t)=k-1`, `R(t+1)=k`. Exact transient-only selection and unreachable empty tails are also checked. Times and ordinal use the existing 4096-bit contract; results beyond it refuse. Budgets apply per comparison, not the whole ordinal search; cumulative work/probes are diagnostic. No partial evidence is interpreted as a negative proof.

```python
from partial_rank import PartialRank
from verify_partial_rank import CheckedPartial
# lang and admission come from the actual CIG-024 source-qualified algebra
p = PartialRank(lang, 0, suffix_mass=32, scan=64)
v = CheckedPartial(admission)
b = p.compare(10**900, 10**899, budget=5000)
assert v.verify(b, budget=5000)
r = p.select(10**900 * p.total + 3, budget=20000)
if r['status'] == 'FOUND':
    assert v.verify_select(0, 10**900 * p.total + 3, r, budget=20000)
```

## Measured source campaign

Use the original shuffled CIG-024 CNF, CIG-019 shared proof circuit, CIG-021 source section and transport, and CIG-024 admission. Compare with actual CIG-025 full signed rank and receiver. Separate independent inclusion-exclusion from marker periods supplies exact ranks, including two adjacent ranks for every completed ordinal. 32 comparisons per size have thresholds equal to average density plus/minus max(1,P//1000); times include 10^900 complete periods and a seeded residual phase. Broad comparison workload is deliberately not an exact-rank request. Single local Python run; small timings vary. Each method pays its own rank preparation and check. Shared source/decoder/algebra preparation is recorded separately.

| Observation bits | Complete period | Signed root terms (full comparator) | Zero-work comparisons / 32 | Partial comparison+check ms | Full exact rank+check ms |
|---:|---:|---:|---:|---:|---:|
|60|210|8|1|5.575|0.181|
|174|510510|128|0|22.898|1.574|
|384|446185740|767|32|3.649|5.120|
|1023|614889782588491410|16384|32|3.863|179.717|

Largest source has 3118 original variables; partial metadata prep+check 7.234 ms, full signed prep+check 111.304 ms. The large partial archive constructed zero suffix tables over the complete measured campaign. Broad comparisons resolve using period cardinality and conservative rank bounds only, not exact residual ranks; full comparison intentionally computes exact ranks. For all 32 the independent checker replays metadata-derived bounds and external marker oracle confirms correctness. Combined prep+comparison+verification is 11.097 ms partial versus 291.021 ms full. Metadata lookup is not zero work: zero-work refers only to charged residual refinement. Full exact arithmetic is better on the two smaller cases. The 32 large certificates serialize to 122128 bytes (canonical JSON diagnostic size; repeats large time and rank integers); no network or physical memory benchmark.

At the largest scale, choose k=10^900*N+3 and k=(10^900+1)*N-2, i.e. near the beginning/end of a remote period. Both found and independently verified via adjacent comparisons; 146 and 150 charged residual work respectively across the search and final certificates. Producer+receiver selection times 1.315 and 1.115 ms; CIG-025 producer alone took 33.647 and 51.243 ms. For the original arbitrary interior ordinal 10^900+173, CIG-028B returns UNKNOWN after 19976 charged units at the first probe; CIG-025 produces the exact answer in 60.890 ms producer time. At 384 bits the same interior ordinal completes via partial proofs but requires 290162 cumulative work and is much slower than CIG-025. These are distinct workload regimes, not universal speedup.

For the difficult partial-period exact rank at 1023 bits, residual uncertainty width starts at 4782970 (a bounded rank interval despite P>6e17), falls to 3188622 with budget 100, to 3188484 with budget 1000, and to 3186800 at budget 20000. All bounds are independently verified and contain the oracle value. The result remains UNKNOWN for the exact count. Smaller parity roots resolve exact within 20k. This exposes the cost of signed cancellation in partially expanded frontiers. A local rank-anchor or better residual architecture is needed for interior queries. No polynomial worst-case claim.

Irregular algebra-only control: seeded random 30030-phase truth table, 2265 diagram nodes. CIG-025 full expansion refuses the 10000-work budget. The partial navigator counts the first and last seven phases exactly with seven scans, and selects the third occurrence in period 10^900 with 134 total charged units, independently compared with exhaustive truth table (not a source-qualified receiver benchmark). The half-period count remains UNKNOWN with 7105 uncertainty at budget 10000. This shows query-local sufficiency even when a global signed representation is not admitted.

## Regression and next integration

364 tests passed locally across predecessor CIG-001–025 and six new methods (120 seeded qualified nonlinear transport laws with four roots including shift and XOR; 40 random 210-phase tables, 800 sampled times and four budgets each; exact/partial comparisons against explicit trajectories, huge ordinal cases, malformed and forged receipts, transient/empty cases). After renumbering, six focused tests passed again. The concurrently merged CIG-026/027 branch's nine final-head workflow runs independently passed; those new tests are not part of the 364 local result. Remote CI of this iteration is separate. Reproduce `python -m unittest discover -s . -p 'test_*.py' -q`, `python run_partial_rank.py`.

Next: retain independently established chronological rank anchors, use the nearest one to turn an interior rank into a small local counting obligation; choose between full signed translation, partial bound refinement, and anchor-local scans according to predicted and measured costs. Then connect partial rank/selection to CIG-027 capacity-constrained continuous computation: a capacity cutoff can be an anchor, and feasibility can be proved by inequalities without rebuilding a full rank language. Preserve exact rank identity relative to source, diagram, prefix, root and logical coordinate.
