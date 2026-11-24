# CIG-032A — Adaptive mathematical Seeds

## Goal and cross-repository context

Build on CIG-031A's `Memory` / `MemoryReceiver`, CIG-029A phase anchors, CIG-025 exact signed rank arithmetic, and CIG-024 source-admitted temporal algebra. NCR-009 motivates costed selection among representations; VGI's ProofGround sparse partial-refinement and active-attention mechanisms motivate obtaining only evidence that resolves the current question. CIG-013 motivates retention according to future usefulness. The supplied external `matching_seed_005 (4).py`, `round6_hot_002 (3).py`, and `seed_log (7).md` contribute the idea of an activation context and representation grammar, exact residual/defect construction, whole-problem hot observations, and checkpoints. Their numerical fitting/heuristic confidence is treated as advisory, not a mathematical certificate. Original external code is not redistributed. The supplied `defect_expansion` was checked separately against 12 random defect selections at each of n=6,8,10 (12,780 exact matching-coefficient comparisons). See `CIG-032A-external-check.json`.

## Mathematical operation

An admitted CIG-024 Ground specifies a deterministic trajectory, transient cutoff D, common period P, and reduced ordered CRT decision diagram for each observation. A Seed is a bounded set of retained rank books in one Ground, not an approximate model or a proof imported from an unrelated source. The book entries are independently admitted exact phase ranks

```
A_i(p) = R_i(D+p) - R_i(D),  0 <= p <= P.
```

Combine two Seeds by union of their members, provided they share the same producer memory; the receiver separately recognizes the members in its own source-qualified memory. A successful transfer may extend the Seed by incorporating the target's new checked rank book. The compact descriptor names the CRT basis, cutoff, each root's index and structural semantic digest, transient prefix, and exact anchors. Its content hash is a description identity, not a proof or remote authentication authority. The receiver compares a descriptor with its own admitted books, including a bottom-up root digest calculation.

### Activation grammar

`Seed.discover(target, deltas=range(1,9), max_work=500000, max_difference=16, phases=())` searches a bounded grammar; no target construction-history (`Language.ops`) is examined. The target is already admitted as a temporal predicate, not previously compiled to rank arithmetic. Discovery checks equal roots first, then candidate shifts from a supplied finite palette, then a rational span, then a small periodic symmetric difference (including complements). Requested phases prioritize existing exact anchors and then other retained books; this is a heuristic, not an optimality theorem. Shift samples only reject candidates; exact synchronized CRT graph traversal and the existing independent CIG-031A shift admission qualify them. General unknown shifts outside the palette may be missed. For a rational span, solve

```
d * [J(t)] = c + sum_i w_i * [I_i(t)]
```

using exact rational elimination of a small set of observed Boolean patterns, with free coefficients set to zero. Find a counterexample on the synchronized CRT diagram product (and finite transient); add its pattern and resolve. All CRT assignments are realizable phases because the basis is pairwise coprime. The independently checked identity then implies, for each phase,

```
d * A_J(p) = c*p + sum_i w_i * A_i(p).
```

For interval rank facts L_i <= A_i(p) <= U_i, sign-correctly accumulate endpoints, round lower upward and upper downward by d, intersect with the target's own rank bounds. Exact results become receiver-admitted anchors. The verifier does not import the producer: it traverses a product of only the nonzero-coefficient roots, checking the integer identity at every distinct terminal tuple and each transient point. The grammar permits <=12 seed members, 1<=d<=16, |w_i|,|c|<=32. This is a limited exact linear span search; alternate coefficient solutions outside the selected free-variable convention, larger shifts, and nonlinear relations beyond the residual route may remain undiscovered. A failed discovery is UNKNOWN, not proof of no relation.

For residual selection, a memoized weighted joint diagram traversal obtains exact disagreement cardinality without allocating target-specific intermediate diagrams for rejected candidates. The selected residual plan uses actual CIG-031A `make_link` and independent admission of `B\\A` and `A\\B`. Residual arithmetic may itself exceed its budget; no successful rank is implied by small disagreement alone. The benchmark opens and checks residual rank packets under a 4096-work producer limit. The receiver's rank checks remain independent. Discovery work is a bounded symbolic state/arc and row-operation ledger, not CPU cycles or exact bit complexity; cached count calls, phase-ranking preference, descriptor hashes, and admission have separate wall-clock costs. No physical energy measurement.

### Local executable usage

```python
from adaptive_seed import Seed
from verify_adaptive_seed import SeedReceiver, restore_capsule
# m = CIG-031A Memory; v = independently qualified MemoryReceiver.
# Independently admit source rank books first, then evict full rank proofs.
s = Seed(m, [0, 1]).combine(Seed(m, [2, 3]))
sr = SeedReceiver(v, s.members)
assert sr.verify_descriptor(s.descriptor())
proposal = s.discover(target, phases=[p])
if proposal['status'] == 'FOUND':
    relation = s.activate(proposal)
    if relation['kind'] == 'residual':
        v.a.extend(m.lang.export())
    assert sr.admit(relation)
    if relation['kind'] == 'span':
        fact = s.transfer_span(relation, p)
        assert sr.verify_span(len(sr.relations)-1, p, fact)
        s.commit_span(relation, fact)
    # shift/residual use the existing CIG-031A link and transfer methods;
    # see run_adaptive_seed.py for full admission and ordinal realization.
```

### Cold activation: descriptor, capsule, recipe

- Descriptor: verify against a receiver which already holds the exact facts. No new knowledge admitted.
- `Seed.capsule(proofs)`: includes the prior signed rank proof per member and the descriptor. A new receiver must first independently admit the original source/transport/algebra. `restore_capsule(a, packet)` creates a fresh receiver-owned memory; each rank proof is independently replayed once, every anchor is checked and the proof is released. A partial failure returns None rather than a usable memory.
- `Seed.recipe()`: transmits the descriptor and an explicit reconstruction instruction. The existing independent CIG-025 checker has been refactored into `checked_expansion` and `CheckedRank.from_ground`, so it can reconstruct and qualify the rank arithmetic directly from the admitted source diagram, instead of comparing a transmitted term list. This does not call the producer. Cold work is still charged. `max_work` is a per-member expansion ceiling, `max_terms` a total term ceiling (checked after recipe expansion), `max_facts` a total anchor ceiling. Forged ranks, including recomputed descriptor hashes, are independently rejected. Neither route transfers the source Ground itself or provides authenticated durable host ownership. Cross-process E-CPU fencing/recovery remains a next experiment. A fresh source must retain matching canonical root/index coordinates; no implicit cross-source remapping is claimed.

## Measured direct usage

16 requests per target, four sizes. Requests are deliberately near acquired phase anchors, in periods near 10^900. The independent reference is CIG-025 `Rank` and `CheckedRank`, plus a separate marker-level inclusion-exclusion oracle. The latter is outside both measured routes. Warm Seed time includes descriptor construction/check, automatic discovery, relation admission, residual acquisition, phase transfer and ordinal selection/check. Cold target rank time includes independent admission and selection/check. Common source and original Seed acquisition are separate. Source proof, not random samples, establishes the identity.

| Observation bits | Shift fresh / Seed ms | XOR fresh / Seed ms | Complement fresh / Seed ms | Majority fresh / Seed ms |
|---:|---:|---:|---:|---:|
| 60 | 0.72 / 2.32 | 1.22 / 4.56 | 0.76 / 2.19 | 0.74 / 4.26 |
| 174 | 3.74 / 4.23 | 5.12 / 8.17 | 6.21 / 5.14 | 4.40 / 7.25 |
| 384 | 24.68 / 6.05 | 77.16 / 13.73 | 57.01 / 6.22 | 25.73 / 10.44 |
| 1023 | 1112.10 / 27.27 | 1363.15 / 64.90 | 1562.42 / 23.85 | 1104.82 / 16.14 |

All 256 requested ordinal destinations checked. At 1023 bits, period 614889782588491410. The pair source has 3115 original CNF variables. Original parity seed acquisition 340.51 ms; source setup 1046.96 ms. Three target campaigns reuse that acquisition. XOR requires 3 residual signed terms instead of 20483 target terms. Majority requires 0 target terms, rational identity discovered from 5 distinct patterns, `2*majority = a+b+c-parity`. The four Seed books acquired in 227.70 ms. The large majority source uses 3082 CNF variables with three separately proved subgroup outputs and admitted CIG-024 composition for total parity and majority. The direct five-output source (3128 vars) exhausted the CIG-019 shared proof budget for the majority goal in 681.18 ms; recorded in the ledger. The three smaller sizes use direct five-output CNFs. Largest majority source setup includes the failed direct attempt (1213.32 ms). This is a useful control: compositional activation works where direct proof architecture needs improvement. The rational grammar never reads the extension history. All four deliberate low-budget controls and all four insufficient single-subgroup seeds report UNKNOWN. Small problems favor fresh construction.

### Cold recipe experiment

Rebuild the source-qualified Ground independently, then restore the 16 original anchors. For both cold methods the original source admission is separately measured. After recipe restoration, discover a shifted goal and independently verify another 16 ordinal destinations per size.

| Bits | Full capsule bytes | Recipe bytes | Capsule restore ms | Recipe restore ms | Activation + 16 queries ms |
|---:|---:|---:|---:|---:|---:|
| 60 | 676 | 544 | 0.60 | 0.56 | 2.32 |
| 384 | 13428 | 779 | 8.51 | 7.51 | 5.15 |
| 1023 | 411853 | 1107 | 178.18 | 179.53 | 19.52 |

At 1023 bits, fresh source admission 1129.88 ms, initial Seed acquisition 349.03 ms. Recipe transmits ~372x fewer serialized bytes than the capsule but pays similar independent arithmetic verification. Capsule construction 41.59 ms, recipe construction 0.50 ms. The numbers are serialized mathematical payload, not total process memory, network latency, or energy. 48 additional verified ordinal results. Reconstructing all roots, evaluating arbitrary unrelated ordinals, and physical host migration remain different costs.

## Verification and reproducibility

```
python -m unittest discover -s . -p 'test_*.py' -q
python run_adaptive_seed.py --output CIG-032A-results.json
python run_seed_restore.py --output CIG-032A-restore.json
```

Nine new tests, including 120 independently generated source-qualified transport laws with direct step oracle, rational denominator and signed bounds, sparse residual, shift and transient, budget and unrelated controls, forged identities and facts, memory-aware basis choice, source re-admission and tampered capsules/recipes. Local predecessor-stack regression 401 tests (does not imply all concurrently merged experiments have been run locally). Source and verifier budget refusal is distinct from unreachable. The benchmark uses intentionally clustered phase requests; uniform unfamiliar requests may still require full exact construction. The activation selector is a heuristic fixed route order, not a proof of least-cost activation. Next: costed multi-route activation and provenance-aware proof DAGs for general adaptive Seed transport across separately authorized hosts; retain source qualification, relation identity, and acquisition/realization costs separately. Evaluate energy with actual meter support, not operation counts alone.
