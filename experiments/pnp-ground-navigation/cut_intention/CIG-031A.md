# CIG-031A — Compositional mathematical memory

Research checkpoint: 24 November 2026. Builds directly on CIG-024 admitted temporal diagrams, CIG-025 signed chronological rank, CIG-029A phase anchors, and CIG-030A receiver-owned rank admission. CIG-013 anticipatory memory and Navigable-Compute NCR-009 motivate charging acquisition, retention and query work separately. This experiment uses one source-qualified temporal language and an in-process independent checker. Time is logical time; wall-clock runtime is measured separately. No energy measurements or distributed recovery experiments are included.

## Mathematical construction

For a common admitted period P and transient cutoff D, define A_i(p) = sum over 0 <= s < p of I_i(D+s), for 0 <= p <= P, and N_i=A_i(P). Full rank is the exact prefix count plus q*N_i+A_i(p) at D+q*P+p. All new transfer receipts concern phase ranks, with transient membership already qualified by CIG-024. They are subsequently used by the actual CIG-029A local ordinal selector and independent checker.

Three relationship types are admitted:

1. Residual: choose a retained view V=A or not A. Define X=B and not V, Y=V and not B. Pointwise B=V+X-Y, hence A_B=A_V+A_X-A_Y. Complement changes a phase rank r to p-r. The producer uses actual `Language.extend`; the receiver independently checks source-admitted complement/intersection identities and transient prefixes using `Checked.relation`. It also checks period cardinality conservation. For retained view bounds [l,h], let n=|V|, x=|X|, y=|Y|. In addition to signed residual rank bounds, a disjoint four-cell partition gives lower=max(0,l-y)+max(0,p-h-(P-n-x)), upper=min(h,n-y)+min(p-l,x). This uses interval capacity, not independence of observations. The result intersects these bounds with existing target anchor bounds. Residual ranks may remain unresolved, or acquire exact CIG-025 expansions under an explicit work budget.
2. Linear: a proposed pointwise integer identity B=c+sum_j w_j I_j, with c in {-1,0,1}, up to eight distinct non-target terms and weights +/-1 or +/-2. The receiver checks the finite transient and traverses the synchronized product of admitted decision diagrams to prove the identity at every terminal. This is bounded by an explicit work budget and never trusts statistical similarity. For example, rank(A and B)=rank(A)+rank(B)-rank(A or B); a subsequent XOR can reuse the resulting exact joint rank. Coefficient signs determine lower and upper endpoints; independent link bounds may be intersected. The caller proposes identities; automatic discovery is active development.
3. Shift: B(t)=A(t+delta). For delta+p=q1 P+s1, delta=q0 P+s0, exact phase rank A_B(p)=(q1-q0)N_A+A_A(s1)-A_A(s0). If s0=s1 the correction cancels, even with partial anchor knowledge. For a unit shift, a retained anchor at p transfers to p-1 modulo P after admitting A_A(1). This is exact coordinate translation, even when the Boolean symmetric difference is enormous. The receiver checks the actual shift relation and original transient prefix.

`Memory` is a producer-side proposal object. `MemoryReceiver` retains verified `PortfolioReceiver` books and exact rank proofs. `admit_fact` checks a phase-rank fact against the currently opened independently checked rank; closing a proof prevents new facts from being admitted from that proof alone. `transfer` proposes bounds using existing facts; `verify` checks against receiver-owned books, checks exact phase, target, threshold, relationship indices and recomputes bounds independently; only exact outcomes enter the target book. Admission is local and depends on the existing immutable-prefix CIG-024 source contract. A receipt's numeric indices are scoped to that admission; no globally portable identity, authenticated host authority, durable checkpoint, or automatic eviction/planner policy is asserted. Existing trusted local producer commit interfaces assume a successful independent admission before commit. Query bounds can change after eviction, so old uncommitted receipts may need reconstruction. Partial results are not promoted to exact facts. The receiver's rank calculation uses all retained anchors; the producer uses bracketing anchors.

## Reproduction

```sh
python -m unittest test_compositional_rank -v
python -m unittest discover -s . -p 'test_*.py' -q
python run_compositional_rank.py --sizes 60 174 384 1023 --queries 16
```

Example: after admitting a new target `target` with the existing language and receiver:

```python
from compositional_rank import Memory, make_link
from verify_compositional_rank import MemoryReceiver
m, v = Memory(language), MemoryReceiver(admission)
# Acquire one old proof, admit its facts, then release the proof.
r = m.open(base)
assert v.book(base).open_rank(r.packet())
m.commit_open(r)
fact = m.fact(base, phase)
assert v.admit_fact(base, phase, fact)
m.commit_fact(fact)
m.close(base)
v.book(base).close_rank()
link = make_link(language, base, target)
admission.extend(language.export())
assert v.admit_link(link)
m.commit_link(link)
# Optional: open the two independently checked residual ranks if affordable.
for i in (link['plus'], link['minus']):
    r = m.open(i, max_work=4096)
    assert v.book(i).open_rank(r.packet())
    m.commit_open(r)
receipt = m.transfer(target, phase)
assert v.verify(target, phase, None, receipt)
m.commit_transfer(receipt)
# Exact transferred facts now support native CIG-029A ordinal navigation.
result = m.book(target).select(ordinal, budget=128)
assert v.book(target).admit_select(ordinal, result, budget=128)
m.book(target).commit(result)
```

Caller handles `Budget` from optional residual acquisition, or chooses another route. The above example assumes the chosen residual route fits the budget. `UNKNOWN` is a sound refusal, not a proof of infeasibility.

## Measured usage

Actual source-qualified shared interpolant decoders, original marker transport and independent CIG-024 admission, through 3,115 source variables and 1,023 observation bits. Four periods: 210, 510510, 446185740, 614889782588491410. The previous intention is parity of the markers. Sixteen old interior phase anchors are acquired under one checked complete rank proof; the proof is released before new intentions. New queries are deliberately generated near these prior phases (by an independent marker-level arithmetic oracle), in widely separated periods near 10^900. No claim of acceleration for unrelated uniform queries. Each new intention has a fresh admitted CIG-025 reference. Its resulting ordinal is checked against the independent original-marker oracle. The rare event is the OR of two complete marker configurations. At the largest scale it is disjoint from parity: XOR and OR have equal semantics and therefore are alternate tests of the same resulting temporal set, not independent new functions. Complement and time shift exercise different representations. A sparse nonempty intersection at 174 bits cannot be reached by the local scan budget despite exact phase ranks; empty intersection at the two largest sizes is correctly unreachable. A direct exact rank or existing `next` route is preferable for such sparse or empty sets.

20 residual-route runs (290 requested ordinals, 226 qualified FOUND or UNREACHABLE, 64 UNKNOWN); eight additional direct-identity runs (128/128 qualified). `found` in the JSON includes UNREACHABLE for empty sets. No false definitive outcomes; every resolved outcome agrees with fresh CIG-025 and its checker. Prior source and target diagram construction are common costs and separately recorded. New transfer costs include residual relationship construction, independent admission, coarse comparisons, residual rank preparation, exact transfer, and local ordinal realization/checking. Independent marker-oracle checks are outside the measured route timings. Python wall-clock measurements are not deterministic guarantees. Serialized rank receipts and anchor maps are not total memory, nor energy measurements. Direct-identity alternatives use separate local target books and already admitted old facts; they do not copy the target result from the residual trial.

Largest-scale totals (ms), from `CIG-031A-results.json`:

| Target | Fresh checked rank + queries | Residual route | Direct identity | Resolved (residual/direct) |
|---|---:|---:|---:|---:|
| XOR rare | 1432.39 | 65.36 | — | 16/16 |
| OR rare | 1485.54 | 52.88 | — | 16/16 |
| NOT XOR | 1575.12 | 57.92 | 12.95 | 16/16 each |
| AND rare | 8.21 | 125.22 | — | 1/1 (UNREACHABLE) |
| Shift +1 | 1420.33 | 56.32 (UNKNOWN) | 18.64 | 0/16 vs 16/16 |

Common source qualification 969.59 ms; common target diagram preparation ~5–7 ms each. Old anchor acquisition 563.35 ms, 16,384 terms, 410,729-byte rank receipt before release. Retained base anchor map 680 bytes (after unit-shift acquisition this may gain an additional phase). The XOR residual uses three terms, 211-byte receipts; the new target full rank would use 20,483 terms / 519,329 bytes. New target anchors after selection are 1,313 bytes. With no residual expansion, 16/16 broad XOR comparisons resolve with rank uncertainty at most two, because the symmetric difference contains only two phases. After residual preparation, all 16 phase ranks are exact and local ordinal navigation uses 65 phase evaluations per producer/receiver side. The complement can instead transfer from the newly acquired XOR anchors, 59-byte linear relationship metadata, without further expansion. For shift +1, the two residual sets each contain 153023451783617415 phases; the residual compiler exceeds its 4096-work budget and local selection returns UNKNOWN. Direct shift uses the old anchor at p+1 and one additional local fact, 47-byte relation metadata, with 68 local phase evaluations for the 16 requests. The learned shift route is a distinct mathematical identity, not a faster execution of the dense residual route. The partial difference route uses more than a simple similarity score: relation suitability depends on exact structure and on the requested operation.

All 392 local regression tests pass (384 predecessor + eight new methods). 120 seeded randomized Boolean/transport sources with direct explicit trajectories and 80 further random irreversible/reversible laws with large shift coordinates; multi-parent exact identities, chained transfers, complement, ordinal reconstruction, forged indices/ranks/thresholds, budget refusal, and proof closure. This predecessor stack does not include every parallel repository experiment; remote CI is separate.

## To Do

- Discover and cost alternative cross-intention identities automatically from source-qualified expression DAGs, including multiple parents and offset symmetries. Prefer proof of a sparse or exact translation over a guessed similarity metric.
- Build a budgeted proof-dependency ledger with durable receiver identity and eviction that retains the exact independently admitted facts required for future transfer. Connect to E-CPU authority and recovery only through native verified mechanisms; current in-process receiver is not a distributed authority.
- Extend to unrelated and adversarial intention streams; compare fresh full compilation, cached identical-root results, residuals, direct shifts, and joint linear identities using common cost contracts. Measure actual resident/peak memory, bytes transferred and physical energy separately; the present experiment supports a time/knowledge-retention trade-off on structured cases, not a physical complexity equivalence or a universal theorem.
