# CKN-003c — Mixed navigation: the n-th prime, exactly, from tiers of knowledge

- **Status:** Experiment, Verified. Every answer was checked four ways: published values (OEIS A006988), deterministic Miller–Rabin, exact π(p) = n, and agreement across all methods. The run was staged (four stages in one environment, results merged into `results_ckn3c.json`) because the sandbox limits a single long run.
- **Lineage:** CKN-003 (zeros, spectral estimates); CKN-002 (exact anchors plus navigation); E-CPU: observe, estimate, admit only exact evidence.
- **Reproduce:** `python run_ckn3c.py`. Needs `zeta_zeros_t6000.npy` from `run_ckn3.py`; takes about 4 minutes.

## 1. Design: estimates buy time, never correctness

Query: given n, return p_n **exactly**.

```
x_hat  <- estimate            (tier of knowledge; may be wrong)
c      <- pi(x_hat)  EXACT    one "anchor": Lucy_Hedgehog DP, O(x^3/4)
p_n    <- sieve outward from x_hat, EXACT, until the count reaches n
```

A wrong estimate makes the walk longer, but it cannot make the answer wrong. This is the Putnam guard taken to its limit: the interpreter's guess carries no authority, and the exact steps alone certify the result.

Tiers compared:

| Tier | Knowledge used | Guarantee |
|---|---|---|
| none | — | pure sieve to p_n |
| unconditional | Rosser/Dusart bracket n(ln n + lnln n − 1) < p_n < n(ln n + lnln n) | binary search with anchors |
| **RH-certified** | li⁻¹(n) plus Schoenfeld: \|π(x) − li(x)\| < √x·ln x / 8π | **1 anchor, walk bounded in advance** |
| smooth | Riemann R⁻¹(n) | 1 anchor (walk length empirical) |
| spectral | R plus K zeta zeros (sharp truncation, best of 4 tapers on 60 exact test points) | 1 anchor (walk length empirical) |

## 2. Exact counter (Verified)
Chunked numpy Lucy_Hedgehog, with peak memory bounded by 2¹⁸-element temporaries. It reproduced every published π(10^k) for k = 9…13: π(10¹³) = 346,065,536,839 in 15.6 s. It also matched brute force at 200 random x ≤ 3·10⁶.

## 3. Headline queries (all exact; all four checks pass)

Walk = |p_n − x̂| in numbers. Time = anchor + walk.

| n | p_n | RH certified max walk | li (RH) walk | R walk | R + 5598 zeros walk | unconditional anchors | time: 1 anchor vs bracket |
|---|---|---|---|---|---|---|---|
| 10⁸ | 2,038,074,743 | 833,580 | 50,318 | 1,844 | 966 | 5 | 0.09 s vs 0.53 s |
| 10⁹ | 22,801,763,489 | 3.45 M | 136,074 | 34,087 | 2,190 | 8 | 0.34 s vs 2.7 s |
| 10¹⁰ | 252,097,800,623 | 13.9 M | 640,609 | 84,846 | 18,604 | 12 | 1.43 s vs 17.7 s |
| 10¹¹ | 2,760,727,302,517 | 54.8 M | 1.37 M | 449,836 | 48,169 | — | 6.6 s |
| 10¹² | 29,996,224,275,833 | 212 M | — | 1.12 M | **84,465** | — | **33.2 s** (anchor 32.9 s, walk 0.35 s) |

Pure sieve at the measured 1.9·10⁸ numbers/s would take 1,326 s at 10¹⁰ and about **44 hours** at 10¹² (extrapolated).

**Batch** (40 random n in [1.06·10⁸, 8.6·10⁹]; all methods agree and every answer passes Miller–Rabin):

| estimate | median \|primes off\| | median walk | max walk |
|---|---|---|---|
| R | 656 | 17,028 | 198,923 |
| R + 1000 zeros | 198 | 4,689 | 27,056 |
| R + 5598 zeros | **82.5** | **1,988** | **14,177** |

## 4. What each tier actually buys (Inference from the measurements)

1. **Some estimate vs none:** 44 hours → 33 s at 10¹², and 12 anchors → 1 at 10¹⁰. Nearly all the gain comes from having *any* good estimate.
2. **RH: a guarantee, not speed.** A proven RH turns "one anchor usually suffices" into **one anchor always suffices, with the walk bounded in advance**: at most 212 M numbers at 10¹², about 1.1 s at the measured sieve rate. The worst case is known before the query runs. This is the E-CPU budget principle with a theorem behind it: declare the cost and refuse beyond it.
3. **Zeros: a shorter walk, with shrinking returns.** The 5,598 zeros shorten the walk 13× at 10¹² and about 8.6× (median) in the batch. But the anchor dominates: total time is 33.2 s against 35.7 s, an 8% saving. Anchor cost grows like x^¾ (x^⅔ for the best known methods) while walk cost grows like √x, so the zeros' share of an exact query shrinks like x^−¼.
4. **The rule that emerges:** the more exact an answer must be, the less the spectral tier is worth, and the more a *certified bound* is worth. Spectral knowledge pays when the query tolerates approximation (CKN-003 §4: ψ(10⁷) within 65 using 5,598 terms and no sieve). Exact queries need exact counting, and their cost is fixed by the anchor.
5. **The anchor is itself stored causality.** One Lucy pass yields π(⌊x/k⌋) at all ≈2√x coordinates at once. That is a causal kernel in CKN-001's sense, and it could be reused for batches of queries near x/k. This is untested here and proposed as CKN-003d.

## 5. Limits
- Estimates used zeros only up to t = 6000. More zeros shorten the walk further but cannot reduce the anchor cost.
- The anchor is Lucy, O(x^¾), not the state-of-the-art Deléglise–Rivat or Gourdon methods. Their better exponent shifts the constants but leaves conclusion 3 unchanged.
- The pure-sieve figure is extrapolated from measured throughput, not run.
- The RH-certified band uses Schoenfeld's bound with a 1.01 safety factor. Correctness of every answer does not depend on RH.
