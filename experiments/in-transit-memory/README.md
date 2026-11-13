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

This is the repository's initial experiment focused on retention in a delay loop; the BTL-001 extension above adds two explicitly different correlated-loss structures without replacing the iid baseline. The [Encounter Envelope](../../formats/encounter-envelope/README.md) and [Poset Causal Interleaver](../description-to-realization/trials/trial-01-poset-interleaver/brief.md) work concerns ordering and causal reconstruction, not packet retention. [Finite Description, Unbounded Space](../description-to-realization/trials/trial-02-finite-description-unbounded-space/README.md) concerns finite descriptions of unbounded state spaces, not lossy transport. The [Observation Equivalence bridge](../../bridges/observation-equivalence/README.md) concerns quotienting states by observations. None of those experiments supplies the retention calculation developed here.


## 9. Correlated-loss extension: BTL-001

The base experiment asks what happens when each packet is independently lost on every circulation. Its open questions explicitly call for burst or correlated loss. This extension tests two different ways that a two-state Gilbert-Elliott channel can change the result. It does not modify the independent-loss baseline.

### 9.1 Two different correlation structures

Let G and B denote good and bad channel states. In state G, a packet is lost with probability \(p_G\); in state B, it is lost with probability \(p_B\), with \(0 \le p_G \le p_B \le 1\). At the end of each circulation, the state transitions according to:

- \(\alpha = P(G \rightarrow B)\)
- \(\beta = P(B \rightarrow G)\)

The state active at the start of a circulation controls that circulation's losses; the transition happens afterward. The initial bad-state probability \(\pi_B\) is an explicit input. The scan uses the stationary value \(\pi_B=\alpha/(\alpha+\beta)\); custom runs may use another initial distribution.

**Per-packet Markov states.** Every packet has its own independent G/B Markov chain. Losses are correlated over time for one packet, but packet state paths are independent of one another. If \(g_r\) and \(b_r\) are the probabilities that one packet is alive and in G or B after \(r\) circulations, respectively, then:

\[
\begin{bmatrix}g_{r+1} & b_{r+1}\end{bmatrix}
=
\begin{bmatrix}g_r(1-p_G) & b_r(1-p_B)\end{bmatrix}
\begin{bmatrix}1-\alpha & \alpha\\ \beta & 1-\beta\end{bmatrix}.
\]

The single-packet survival probability is \(q_r=g_r+b_r\). Since packet chains are independent, the number of survivors is binomial at a fixed horizon and retention is \(\Pr(\operatorname{Binomial}(n,q_r)\ge k)\).

**Shared channel state.** All packets share one G/B channel state per circulation. Conditional on that shared state, packet losses are independent; across circulations and across the block, however, the common environment correlates the outcomes. A dynamic programme tracks \(D_r(m,s)\), the probability that \(m\) packets remain and the next circulation begins in state \(s\). The transition thins \(m\) packets using the current state's binomial loss law, then advances the shared channel state. States with fewer than \(k\) survivors are discarded because this model has no repair. Retention is the sum of \(D_r(m,s)\) over both channel states and all \(m \ge k\).

These are not interchangeable interpretations of “burst loss.” The first represents packet-specific temporal persistence; the second represents a common environmental condition affecting the whole block. The comparison keeps both visible.

### 9.2 Matched iid comparison and half-life definition

The report includes an iid-per-round baseline with the same marginal first-round loss probability:

\[
\bar p=(1-\pi_B)p_G+\pi_B p_B.
\]

For stationary initialisation, this is also the marginal loss probability on each circulation. The baseline removes temporal and cross-packet state correlation. It is a controlled comparison, not a claim that one model is the true channel.

The Gilbert-Elliott channel changes state only at circulation boundaries, so this extension defines half-life as the **first integer circulation** at which retention is at or below \(1/2\). It does not interpolate a fractional crossing. A result marked **not_reached_within_horizon** is right-censored at the scan horizon, not evidence of infinite retention. **no_finite_half_life** is emitted only when a loss-free absorbing-good-state regime has an analytically reconstructed limiting retention strictly above one half. The calculation includes packets/blocks that survive a transient bad state long enough to enter the absorbing good state; exact limiting equality is conservatively not labelled infinite.

### 9.3 Illustrative scan

The checked-in scan uses four deliberately varied fixtures. The first three share \(p_G=0.001\), \(p_B=0.35\), \(\alpha=0.025\), \(\beta=0.20\), and stationary \(\pi_B=1/9\). The fourth uses a much more damaging but less frequent bad state.

| Word | Marginal loss | iid-average | Per-packet Markov | Shared channel |
| --- | ---: | ---: | ---: | ---: |
| 32-of-32 intact | 3.98% | 1 | 1 | 11 |
| 32-of-64 threshold | 3.98% | 18 | 35 | 32 |
| 1-of-64 replication | 3.98% | 112 | 235 | 110 |
| 24-of-32, persistent bad state | 15.04% | 2 | 14 | 52 |

Values are first integer crossings in circulations, not measured elapsed time. The same marginal loss rate does not determine the k-of-n retention curve: the correlation structure and recovery threshold interact. In the shared-state model, common good periods can preserve many packets together, while common bad periods can damage many together. Whether that helps or hurts depends on the threshold. The table is an illustration of model sensitivity, not a universal ordering between burst and iid channels.

A seeded 2,000-trial Monte Carlo check accompanies each reported crossing in [the scan receipt](results/burst-loss-scan.json). The simulation is a numerical implementation check against the finite-state calculations; it is not an empirical observation of a network.

### 9.4 Reproduction

~~~bash
python -m unittest discover -s experiments/in-transit-memory -p "test_*.py" -v
python experiments/in-transit-memory/burst_loss.py --scan --max-rounds 500 --json
python experiments/in-transit-memory/burst_loss.py --scan --max-rounds 500 --simulate --trials 2000 --seed 20261112 --json --output experiments/in-transit-memory/results/burst-loss-scan.json
~~~

The 22 focused tests include absorbing-state limiting-retention reconstruction (including recovery from a transient bad state), reductions to the original iid expression when \(p_G=p_B\), explicit enumeration of short Markov state paths, monotonic retention, single-packet equivalence, common-mode counterexamples, integer half-life and censoring behavior, seeded Monte Carlo agreement, parameter validation, and CLI output.

### 9.5 Interpretation limits and next step

This is a two-state, finite-horizon mathematical model. It does not estimate \(p_G\), \(p_B\), \(\alpha\), or \(\beta\) from link traces. It does not inspect or claim to reproduce E-CPU's DelayLoopEngine, RRNS implementation, or any deployed channel. Packet drops are conditionally independent within a state; the shared-state variant is the only one here with cross-packet dependence. There is no repair, retransmission, reordering, finite readout window, decode failure, or repair latency. The base experiment's iid repair-epoch calculation has not yet been combined with these Markov models.

The next discriminating experiment would add a repair/rewrite operation at a declared interval and make repair success depend on whether at least \(k\) packets survive to the repair boundary. A later implementation comparison would need actual packet traces or operation evidence, independently documented state classification, and a declared clock/measurement scope before any fitted model could be treated as descriptive evidence about a real path.

## 10. State-preserving repair under burst loss: MRE-002

BTL-001 treated packet loss as absorbing because it contained no repair. MRE-002 introduces a fixed repair interval \(L\) and a recovery threshold \(k\). At the end of each interval:

1. If fewer than \(k\) of the \(n\) data packets remain, the logical word is lost.
2. If at least \(k\) remain, the word is reconstructed into all \(n\) slots.
3. The channel state is **not** reset by reconstruction. It continues from the state reached at the repair boundary, including for slots whose data packet was lost earlier in the epoch.

Repair itself is instantaneous in this model. Its count is recorded, but duration, energy, bandwidth, and decoder failure are not assigned invented costs.

### Two persistent environments

For independent per-packet Markov channels, the epoch transition matrix has states \(b=0,\ldots,n\), where \(b\) is the number of bad channel slots at the start of an epoch. Each slot has four possible epoch outcomes: survived/end-good, survived/end-bad, lost/end-good, and lost/end-bad. The implementation computes the exact joint probability of these outcomes over \(L\) circulations, then uses a capped two-dimensional dynamic programme over the number of survivors and the number of bad endpoint slots. Only paths with at least \(k\) survivors enter the transition matrix; at the next epoch, every data slot is rewritten but the endpoint bad-slot count persists.

For a shared channel, the epoch transition matrix is \(2\times2\), indexed by the shared good/bad state at the beginning and end of the interval. Its dynamic programme tracks current survivor count and shared channel state through the \(L\) circulations. It discards paths that fall below \(k\), because they cannot recover before the epoch boundary.

The iid-marginal comparator uses the same first-round marginal loss probability but removes both forms of channel-state persistence.

### Quantities kept separate

The successful-epoch transition matrix \(K\) is sub-stochastic. With initial channel-state distribution \(\mu\), survival after \(m\) successful repair intervals is:

\[
P(\text{survive }m\text{ intervals})=\mu K^m \mathbf{1}.
\]

The expected number of attempted intervals, including the final failed interval, is reconstructed from the fundamental matrix:

\[
E[N]=\mu (I-K)^{-1}\mathbf{1},
\]

when the fundamental matrix is finite and numerically resolvable. Expected successful repairs are \(E[N]-1\); expected lifetime in circulations is \(L\,E[N]\). A singular or ill-conditioned system is reported as unbounded/ill-conditioned, not assigned a fabricated finite lifetime.

The sweep also computes a Pareto frontier that maximizes expected lifetime while minimizing the ratio of expected successful repairs to expected lifetime rounds. It does **not** collapse lifetime and repair work into one score. This frontier is only with respect to those two reported dimensions: it does not assign a value to extra redundancy, decoder complexity, repair bandwidth, or repair duration.

For each policy, the report compares its median-failure horizon with the original no-repair BTL-001 process over the same total number of circulations. The repair model can preserve the logical word even when the original set of surviving packets would not have lasted that long, because successful recovery rewrites previously lost data.

### Reproduction

~~~bash
python -m unittest discover -s experiments/in-transit-memory -p "test_*.py" -v
python experiments/in-transit-memory/repair_epochs.py --scan --json
python experiments/in-transit-memory/repair_epochs.py --scan --simulate --trials 1000 --seed 20261112 --json --output experiments/in-transit-memory/results/markov-repair-scan.json
~~~

The focused suite independently enumerates short per-packet state/loss paths and shared-channel state paths; checks the iid geometric special case; reconstructs multi-epoch survival, expected repair count, and the no-repair comparison; verifies seeded simulations; and rejects altered transition matrices even when the outer report digest is recomputed.

### Interpretation limits

- \(p_G,p_B,\alpha,\beta\) are supplied synthetic model parameters, not estimates fitted to link traces.
- Repair happens at a fixed interval, instantaneously, and only if the threshold is met.
- Data reconstruction resets packet availability; it does not reset the underlying channel states.
- The per-packet channel state continues evolving even after its data packet is lost, so a later repair can write new data into that slot under its then-current state.
- The expected repair rate is a ratio of expectations, not the expected sample-path repair rate.
- The Pareto frontier is a comparison, not a universal optimal policy. Selecting one policy requires an explicit utility or resource constraint.
- This is not a measurement of E-CPU, MailCPU, a real fibre link, or any physical communication system.

The next experiment should relax the fixed periodic schedule: can repair be delayed or triggered by a partial observation of channel state or survivor count without paying more in sensing/coordination than the expected lifetime gain?


### 10.1 First deterministic policy sweep

The checked-in [MRE-002 scan summary](results/markov-repair-scan-summary.json) contains the 72 policy/model combinations and the reconstructed Pareto frontiers from CI run [43366801290](https://github.com/Kier73/In-Formation-Space/actions/runs/43366801290). The sweep uses 12 slots, thresholds \(k\in\{1,6,12\}\), intervals \(L\in\{1,2,4,8\}\), and a 100-epoch median-censor horizon.

| Scenario | \(p_G\) | \(p_B\) | \(\alpha\) | \(\beta\) | Initial bad-state mass | Marginal first-round loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stationary moderate bursts | 0.010 | 0.40 | 0.08 | 0.25 | 24.24% | 10.45% |
| Rare persistent bad bursts | 0.001 | 0.70 | 0.02 | 0.08 | 20.00% | 14.08% |

The rare-persistent-burst scenario gives a useful reversal:

| Recovery policy | iid-marginal | Per-packet Markov | Shared channel |
| --- | ---: | ---: | ---: |
| \(k=1,L=1\): expected lifetime rounds | 16,472,837,436 | 16,600,138,212 | 397 |
| \(k=12,L=8\): expected lifetime rounds | 8.00 | 8.14 | 30.22 |

These are expected circulation counts under the synthetic model, not wall-clock durations. The \(k=1,L=1\) median was not crossed within the 100-epoch scan horizon for any of the three models; the displayed mean comes from the fundamental-matrix calculation and is not a median estimate.

The common channel is dramatically worse for the permissive one-packet recovery rule because a bad-state burst can remove the entire block together. Under the strict all-packet threshold with a longer interval, persistent common-good periods can instead help all slots survive together. Independent packet channels do not preserve that alignment. Correlation therefore has no universal “penalty” sign; its effect depends on the reconstruction rule and repair schedule.

The Pareto frontier keeps repair-event rate visible alongside expected lifetime. For the rare-persistent-burst shared-channel case, its nondominated policies are \(k=1,L=1\), \(k=1,L=2\), \(k=1,L=8\), \(k=6,L=8\), and \(k=12,L=8\). No one of these is declared best without a resource value or repair budget.

The CI summary receipt stores the complete tested grid and the frontier entries. Reproduce the full transition matrices and reports with the CLI commands above. Results whose median is not reached by 100 repair intervals are explicitly right-censored; they are not assigned an infinite half-life.


## 11. Observed-state adaptive repair: MRE-003

MRE-002 compared fixed repair intervals. MRE-003 asks whether observing the current survivor count and shared channel state can improve repair decisions by waiting through good conditions and repairing before another risky circulation.

At each circulation boundary the controller receives the exact state \((m,s)\), where \(m\) is the number of surviving data packets and \(s\in\{G,B\}\) is the shared channel state. It chooses:

- **WAIT:** leave the current data packet count unchanged before the next circulation.
- **REPAIR:** reconstruct all \(n\) data packets immediately, without resetting the channel state.

The current state governs packet loss during the next circulation; the Markov transition occurs after losses. Falling below the recovery threshold \(k\) is absorbing. The horizon terminal reward is 1 if at least \(k\) packets remain, otherwise 0.

### Explicit objective and exact dynamic programme

The finite-horizon objective is:

\[
U=P(\text{recoverable at horizon})-c\,E[\text{number of repairs}],
\]

where \(c\ge0\) is a declared repair cost in units of terminal survival reward. It is an explicit policy input, not an implicit utility weight. The optimiser uses backward induction over \((t,m,s)\), stores both WAIT and REPAIR continuation values, and chooses WAIT on ties to avoid unnecessary repairs.

A separate forward probability propagation evaluates the selected policy and reconstructs terminal survival and expected repair count. Its expected utility must equal the backward-induction initial value. The controller is compared against every declared fixed interval under the same objective, including a no-repair candidate. Consequently the adaptive policy's utility cannot be lower than the best fixed candidate in the supplied schedule set, up to numerical tolerance.

### Observation assumption and evidence boundary

The first version assumes that exact survivor count and exact shared channel state are observable before each action at zero sensing cost. This is deliberately strong. The report does not claim that a real receiver can infer these values, that a state label is authenticated, or that a telemetry path is free. Partial/noisy observation, sensing delay, communication overhead, and observation-path authorization remain outside MRE-003. The current controller is a finite mathematical policy, not a live E-CPU action adapter.

Only the shared-channel model is controlled in MRE-003. Extending to independent per-packet channel states would require a larger observable state or a belief state over hidden per-slot channel states, and is not silently approximated here.

### Reproduction

~~~bash
python -m unittest discover -s experiments/in-transit-memory -p "test_*.py" -v
python experiments/in-transit-memory/adaptive_repair.py --scan --json
python experiments/in-transit-memory/adaptive_repair.py --scan --simulate --trials 2000 --seed 20261112 --json
~~~

The report includes the full state/action table, the count of survivor-count cells where the selected action differs between good and bad channel states, and the number of state rows selecting repair. The focused tests check backward-vs-forward reconstruction, dominance over fixed schedules, the no-repair special case, repair-cost monotonicity, explicit state/action coverage, agreement with the original BTL-001 no-repair retention, report/sweep digests, and seeded simulation against exact policy metrics. The CLI prints a direct adaptive-vs-best-fixed comparison for each threshold and repair-cost pair.
