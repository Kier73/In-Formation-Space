# In-transit memory: retention in a lossy delay loop

**Status:** Exploratory probability model with exact calculations, tests, and a seeded Monte Carlo check. This is not a hardware or network measurement.  
**Date:** 2026-11-11  
**Lineage:** Derived from the delay-loop and "state in transit" concept in an E-CPU/MailCPU exploration note. This experiment reimplements a simplified retention model from the description; it does not copy E-CPU code and does not inspect the implementation. Read alongside [Mathematical Cautions](../../maps/mathematical-cautions.md).

## 1. Question

If a logical word is carried by packets circulating in a delay loop, how long does it survive when packets are lost independently? More specifically, what does a proposed block-retention half-life assume, and how does a `k`-of-`n` recovery threshold change the answer?

A source note proposes a conservation law for an unprotected memory block of `M` packets in a loop of period `τ` with independent per-packet loss probability `p`:

\[
t_{1/2} = \frac{\tau \ln 2}{M p}.
\]

In the source formula, `M` is the block size; this experiment writes `n`.

This experiment treats that expression as a model to examine, not as an established law. It separates three cases that the formula does not distinguish:

- an intact block, where every packet must survive (`k = n`);
- an erasure-coded word, where any `k` of `n` packets suffice (`1 < k < n`);
- full replication, where any one packet suffices (`k = 1`).

## 2. Model

- `n` packets occupy `n` independent slots in a circulating loop.
- One circulation takes `period` time units, written `τ`.
- Each packet independently survives one circulation with probability `q = 1 - p`.
- A logical word is recoverable while at least `k` of its `n` packets survive.
- There is no repair, refresh, duplication, correlated loss, reordering, or readout cost.

After `r` circulations, the number of surviving packets is

\[
X \sim \operatorname{Binomial}(n, q^r),
\]

so the exact retention probability is

\[
R(r) = \Pr(X \ge k) = \sum_{j=k}^{n} \binom{n}{j} (q^r)^j (1-q^r)^{n-j}.
\]

The half-life `r₁/₂` solves `R(r₁/₂) = 1/2`, and `t₁/₂ = τ r₁/₂`. The search is over continuous `r`; this is an interpolation used to define a half-life, not a claim that packets are inspected between circulations.

Two cases have closed forms:

- **Intact block (`k = n`):** `R(r) = q^{rn}`, so `r₁/₂ = ln(2) / (-n ln q)`.
- **Any one packet (`k = 1`):** `R(r) = 1 - (1 - q^r)^n`, so `r₁/₂ = ln(1 - 2^{-1/n}) / ln(q)`.

The source formula is the first-order small-`p` approximation of the intact-block case:

\[
\frac{\tau \ln 2}{n p}
\approx
\frac{\tau \ln 2}{n\,(-\ln(1-p))}
= \tau r_{1/2}.
\]

It is not a `k`-of-`n` formula, and it is not exact when `p` is large. At `n = 64`, `p = 0.01`, the approximation is within 0.51%; at `p = 0.10`, it overestimates the intact-block half-life by 5.36%. At `p = 0.50`, it overestimates by 38.6%; that ratio is independent of `n` for the intact block.

## 3. Results

The scan below uses `period = 1`, so `exact r₁/₂` and `exact t₁/₂` have the same numerical value. The source-formula column is shown only for comparison; an asterisk marks a `k < n` row where the formula is not applicable as a retention model.

| `n` | `k` | `p` | exact `r₁/₂` (circulations) | exact `t₁/₂` (`τ`) | source formula (`τ`) | formula / exact | `R(r₁/₂)` |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 64 | 0.01 | 1.07762 | 1.07762 | 1.08304 | 1.00503 | 0.500 |
| 64 | 32 | 0.01 | 70.5263 | 70.5263 | 1.08304* | 0.0153566 | 0.500 |
| 64 | 1 | 0.01 | 450.811 | 450.811 | 1.08304* | 0.00240243 | 0.500 |
| 64 | 64 | 0.10 | 0.102794 | 0.102794 | 0.108304 | 1.05361 | 0.500 |
| 64 | 32 | 0.10 | 6.72750 | 6.72750 | 0.108304* | 0.0160987 | 0.500 |
| 64 | 1 | 0.10 | 43.0029 | 43.0029 | 0.108304* | 0.00251853 | 0.500 |
| 8 | 8 | 0.50 | 0.125000 | 0.125000 | 0.173287 | 1.38629 | 0.500 |

The ratios between thresholds are independent of `p` here because every half-life scales with `1 / -ln(1-p)` at fixed `n` and `k`. At `n = 64`, the 32-of-64 threshold extends the intact-block half-life by a factor of about 65.45, and full replication extends it by about 418.35.

Three observations follow directly from the model:

1. **The source formula is a small-loss intact-block approximation.** The exact intact-block denominator is `-ln(1-p)`, not `p`. The difference is negligible for very small `p` and substantial near `p = 0.5`.
2. **Recovery threshold matters more than the raw packet count.** An intact block loses its word when any one packet is lost. A `k`-of-`n` code can survive many losses, so its half-life can be orders of magnitude longer under the same per-packet loss.
3. **More slots cut both ways.** For an intact block, `r₁/₂ ≈ ln(2)/(n p)`, which shrinks as `n` grows. For full replication, `r₁/₂ ≈ (ln n - ln ln 2)/p`, which grows only logarithmically in `n`. Adding packets increases the number of things that can be lost unless the recovery threshold makes the extra packets useful.

### Monte Carlo check

`delay_loop.py` can also estimate retention at the exact half-life by sampling packet survival under the same independence assumption. With 20,000 trials per row and seed `20261111`, the seven estimates were `0.4965`, `0.50015`, `0.4950`, `0.4965`, `0.50015`, `0.4950`, and `0.4996`. The exact target is `0.5`. At `R = 0.5`, the binomial standard error for 20,000 independent trials is about `0.0035`, so these deviations are consistent with sampling noise. This is a sanity check on the implementation, not a formal test of the model against an external system.

The complete JSON artifact is [results/retention-scan.json](results/retention-scan.json).

## 4. Repair changes the question

Without repair, every finite `k`-of-`n` word still decays: the survival probability approaches zero as the number of circulations grows. The source note's stronger phrase—state persisting "indefinitely"—requires a repair or renewal process, or a continuing supply of fresh redundancy, that the half-life formula does not model.

A simple repair model makes the dependency explicit. At the end of each repair epoch of `L` circulations, if at least `k` packets survive, the word is decoded and all `n` packets are rewritten. Otherwise it is lost. Under the same independence assumptions, the per-epoch survival is `P_epoch = R(L)`, and survival after `m` epochs is `P_epoch^m`.

For `n = 64`, `p = 0.01`, and `period = 1`:

| Repair interval `L` | `k = 32`: per-epoch survival | `k = 32`: median epochs | `k = 64`: per-epoch survival | `k = 64`: median epochs |
| ---: | ---: | ---: | ---: | ---: |
| 1 | ≈1 (rounds to 1.000000) | 5.28 × 10⁴⁷ | 0.525596 | 1.078 |
| 10 | ≈1 (rounds to 1.000000) | 3.49 × 10¹⁶ | 0.001609 | 0.108 |
| 50 | 0.966451 | 20.312 | ≈0 | 0.022 |
| 100 | 0.019392 | 0.176 | ≈0 | 0.011 |

The median is the continuous value `ln(0.5) / ln(P_epoch)`; the first integer epoch at which survival reaches `1/2` is this value rounded up. The near-1 entries are computed from the shorter binomial tail and its log-probability, so a very small failure probability is not silently rounded away. They are still finite: under `p > 0` and a positive repair interval, no fixed `n`, `k`, or repair interval yields survival probability exactly 1 forever.

The table also shows why repair frequency cannot be chosen independently of the encoding. An intact block repaired only every 50 or 100 circulations is almost certain to be lost before repair, while a 32-of-64 code at the same interval has a much larger per-epoch survival probability. Conversely, repairing an intact block every circulation gives a reasonable per-epoch survival but requires frequent rewriting.

## 5. What this supports and does not support

**Supports (within the stated model):**

- Exact retention probabilities and half-lives for independent per-packet loss with a `k`-of-`n` recovery threshold.
- The source formula's role as a small-`p`, intact-block approximation, including its exact correction and its breakdown at high loss.
- A quantified distinction between intact, erasure-coded, and fully replicated retention.
- The claim that repair or renewal is needed for persistence beyond a finite half-life, together with a simple way to calculate the repair-epoch trade-off.

**Does not support:**

- Any claim about the actual E-CPU `DelayLoopEngine`, RRNS implementation, a real fiber or DWDM link, or a deployed network.
- Independence of packet losses, permanent loss, zero repair cost, no reordering, or no correlated failures in a real system. These are model assumptions, not observations.
- Literal indefinite persistence from `k`-of-`n` coding alone. Without repair or renewal, retention decays; with repair, the repair process has its own failure modes and costs.
- The bandwidth-delay product capacity claim `C = B × τ`. This experiment models retention, not link capacity.
- A probability for any causal explanation, a hardware reliability prediction, or a comparison with an implementation that was not run.

## 6. Reproduction

Requirements: Python 3.11 or newer, standard library only. The local run used Python 3.14.0.

```text
python -m unittest discover -s experiments/in-transit-memory -p "test_*.py" -v
python experiments/in-transit-memory/delay_loop.py --scan --period 1.0
python experiments/in-transit-memory/delay_loop.py --scan --simulate --trials 20000 --seed 20261111 --json --output experiments/in-transit-memory/results/retention-scan.json
```

Files:

- [delay_loop.py](delay_loop.py) — exact retention, half-life search, source-formula comparison, Monte Carlo, repair-epoch calculations, and CLI.
- [test_delay_loop.py](test_delay_loop.py) — 21 standard-library tests covering closed forms, threshold monotonicity, approximation limits, numerical edge cases, repair epochs, and the CLI.
- [results/retention-scan.json](results/retention-scan.json) — the seeded scan artifact shown above.

## 7. Open questions and next experiments

- Replace independent loss with burst or correlated loss, such as a Gilbert-Elliott model, and measure how the `k`-of-`n` threshold changes the half-life.
- Add repair latency, imperfect recovery, and repair cost. A repair that arrives after the recovery deadline is not a repair.
- Model finite readout windows and reordering. The source note's slot-clamping condition (`Δ_slot ≥ 3σ_jitter`) is an ordering constraint that this retention model does not include.
- Compare the simplified `k`-of-`n` threshold with the modulus and consistency constraints of an RRNS code. Not every `(n, k)` pair is realizable with a given integer range.
- Establish whether the source formula was intended as a block-level or packet-level statement, and pin the source revision if the implementation is inspected. This experiment only reimplements the description.

## 8. Relationship to existing work

This is the first experiment in the repository focused on retention in a delay loop. The [Encounter Envelope](../../formats/encounter-envelope/README.md) and [Poset Causal Interleaver](../description-to-realization/trials/trial-01-poset-interleaver/brief.md) work concerns ordering and causal reconstruction, not packet retention. [Finite Description, Unbounded Space](../description-to-realization/trials/trial-02-finite-description-unbounded-space/README.md) concerns finite descriptions of unbounded state spaces, not lossy transport. The [Observation Equivalence bridge](../../bridges/observation-equivalence/README.md) concerns quotienting states by observations. None of those experiments supplies the retention calculation developed here.
