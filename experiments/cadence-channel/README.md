# Cadence channel: exact timing-symbol error, PLL limits, and horizon-aware zero-error claims

**Status:** Exploratory exact model, seeded simulation, and source-claim audit. This is not a hardware or network measurement.  
**Date:** 2026-11-12  
**Lineage:** Independent model of the timing-channel semantics in [E-CPU](https://github.com/Kier73/E-CPU) `mailcpu/timing_channel.py` and the timing benchmark in `mailcpu/substrate_sim.py`, inspected at commit `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`. The model is reimplemented from the described operations; it is not a copy of the source module. Read alongside [Mathematical Cautions](../../maps/mathematical-cautions.md).

## 1. Question

A source exploration note describes discrete cadence modulation (DCM): a symbol \(d \in \{0,\ldots,2^B-1\}\) is transmitted as the inter-packet interval

\[
\Delta t_d = \Delta_0 + d\,\delta,
\]

and a phase-locked-loop (PLL) demodulator recovers the symbol from a noisy observed interval. The note says a wide-area-network benchmark "demonstrates zero bit error rate under bounded Gaussian jitter" over a Gilbert-Elliott burst-loss channel. A source test also states that for Gaussian jitter \(\sigma < \delta/3\), the decision boundaries "maintain zero error rate."

This experiment asks four narrower questions:

1. When is zero symbol error actually guaranteed?
2. What is the exact symbol and bit error probability under the stated Gaussian model?
3. What does the PLL change, and what does it not change?
4. What horizon does a finite zero-BER observation support?

The short answer is that the source's zero-BER observations are real but finite-horizon and parameter-specific. Gaussian jitter is unbounded, so the exact error probability is positive for every \(\sigma>0\). The PLL is useful for common-mode baseline drift, but it does not remove white jitter; in the error-free regime it slightly increases the decision variance, and once symbol errors occur its decision-directed updates add baseline excursions.

## 2. Model and source boundary

The model keeps the source's symbol alphabet and update rule, and states assumptions the source benchmark leaves implicit:

- \(L=2^B\) symbols, transmitted with equal probability.
- The ideal interval for symbol \(d\) is \(\Delta_0 + d\delta\).
- The observation is \(y=\max(0,\Delta_0+d\delta+J)\) with \(J\sim\mathcal{N}(0,\sigma^2)\). The zero clamp is part of the source demodulator's input path; it matters only for negative observations.
- The **static decoder** computes \(\hat d=\operatorname{clamp}(\operatorname{round}((y-\Delta_0)/\delta),0,L-1)\).
- The **PLL decoder** starts at \(\hat\Delta_0=\Delta_0\), computes \(\hat d\) from \(y\), and updates
  \[
  \hat\Delta_0 \leftarrow \hat\Delta_0 + \alpha\left(y-\hat\Delta_0-\hat d\,\delta\right).
  \]
  This is the source's decision-directed update: the phase error uses the *decoded* symbol, not the transmitted one.
- Jitter is independent across symbols, symbols are independent, and the baseline is constant unless a drift experiment says otherwise.
- There is no packet loss, reordering, clock quantization, or uncertainty in the symbol clock in the core model.

The source's timing benchmark calls `self._rng.gauss` directly and does not call `transmit`. The Gilbert-Elliott channel is a packet-erasure model used by the delay-loop benchmark; it is not exercised by the timing benchmark. The reported zero BER is therefore a jitter-only symbol result, not a burst-loss result. A combined model would need to state how erased symbols are handled and how timing is recovered from the surviving ones.

## 3. Exact symbol and bit error

For a fixed baseline and uniform symbols, the two edge symbols have one decision boundary and the \(L-2\) interior symbols have two. The exact average symbol error probability is therefore

\[
P_{\text{sym}} =
\frac{2(L-1)}{L}\,
Q\!\left(\frac{\delta}{2\sigma}\right),
\qquad
Q(x)=\frac{1}{2}\operatorname{erfc}\!\left(\frac{x}{\sqrt 2}\right).
\]

This is exact for the stated model, including the zero clamp. It is positive for every \(\sigma>0\); the only exact zero is \(\sigma=0\).

The bit error rate is not simply the symbol error rate. Symbol labels are ordinary binary integers, so a one-symbol slip can change several bits. The code computes the full transition matrix

\[
P(\hat d=e\mid d)
=
\Phi\!\left(\frac{(e-d+\tfrac12)\delta}{\sigma}\right)
-
\Phi\!\left(\frac{(e-d-\tfrac12)\delta}{\sigma}\right),
\]

with the edge cells extended to \(\pm\infty\), and then

\[
P_{\text{bit}} =
\frac{1}{L B}
\sum_{d=0}^{L-1}\sum_{e=0}^{L-1}
P(\hat d=e\mid d)\,
\operatorname{popcount}(d\oplus e).
\]

The scan below uses `quantum = 1`, `bits_per_symbol = 4`, and `200,000` symbols per row with seed `20261112`. `N95` is the largest message length whose probability of a clean run is at least 95%:

\[
N_{95}=\left\lfloor
\frac{\ln(0.95)}{\ln(1-P_{\text{sym}})}
\right\rfloor .
\]

| \(\sigma/\delta\) | exact symbol error | exact bit error | clean \(P\) over 32 symbols | \(N_{95}\) |
| ---: | ---: | ---: | ---: | ---: |
| 0.02 | \(5.731\times10^{-138}\) | \(1.242\times10^{-138}\) | rounds to 1 | \(>10^9\) |
| 0.05 | \(1.429\times10^{-23}\) | \(3.096\times10^{-24}\) | rounds to 1 | \(>10^9\) |
| 0.10 | \(5.375\times10^{-7}\) | \(2.329\times10^{-7}\) | 0.999983 | 95,434 |
| 0.15 | \(8.045\times10^{-4}\) | \(3.486\times10^{-4}\) | 0.974575 | 63 |
| 0.20 | \(1.164\times10^{-2}\) | \(5.045\times10^{-3}\) | 0.687450 | 4 |
| 0.25 | \(4.266\times10^{-2}\) | \(1.848\times10^{-2}\) | 0.247839 | 1 |
| 0.30 | \(8.961\times10^{-2}\) | \(3.883\times10^{-2}\) | 0.049582 | 0 |
| 0.40 | \(1.981\times10^{-1}\) | \(8.583\times10^{-2}\) | \(8.550\times10^{-4}\) | 0 |
| 0.50 | \(2.975\times10^{-1}\) | \(1.288\times10^{-1}\) | \(1.239\times10^{-5}\) | 0 |

The table makes the horizon dependence explicit. At \(\sigma/\delta=0.20\), a 32-symbol clean run is a 69% event; at \(0.30\), it is a 5% event. The exact error rates at the two smallest jitter values are not observably zero; they are simply far below the resolution of any practical simulation.

The Monte Carlo static decoder agrees with the exact columns where the error count is large enough to resolve them. At \(\sigma/\delta=0.15\), for example, the exact SER is \(8.045\times10^{-4}\) and the 200,000-symbol simulation gives \(8.05\times10^{-4}\). At \(0.10\), the exact SER is \(5.375\times10^{-7}\), so 200,000 symbols contain only about 0.11 expected errors; the observed one error is consistent with Poisson noise, not evidence for a different rate.

## 4. The two source tests

The source has two relevant cases. The short test injects \(\sigma=1\,\text{ms}\) into a \(6\,\text{ms}\) quantum and asserts that a 32-symbol message decodes exactly. The WAN test injects \(\sigma=2\,\text{ms}\) into a \(25\,\text{ms}\) quantum and asserts `ber == 0.0` for a 16-symbol message.

| case | symbols | \(\sigma/\delta\) | \(3\sigma/\delta\) | \(3\sigma\le\delta/4\)? | exact SER | exact clean \(P\) | failures / 500 seeds |
| --- | ---: | ---: | ---: | :---: | ---: | ---: | ---: |
| short jitter test | 32 | 0.1667 | 0.50 | no | \(2.531\times10^{-3}\) | 0.922105 | 52 |
| WAN benchmark | 16 | 0.0800 | 0.24 | yes | \(3.848\times10^{-10}\) | 0.9999999938 | 0 |

The WAN test is effectively deterministic under the model: a clean 16-symbol run has probability \(1-6.16\times10^{-9}\). Its zero BER comes from the large ratio \(\delta/\sigma=12.5\), not from the Gilbert-Elliott channel and not specifically from the PLL.

The short test is different. Its exact clean probability is 92.2%, so the fixed-seed assertion is a high-probability event, not a guarantee. Replaying the source's algorithm over 500 seeds produced 52 failures (10.4%), with first failures at seeds 2, 15, 22, 24, 30, 53, 54, 64, 71, and 81. A direct replay of the cloned E-CPU module at `c99af8c` produced the same 52 failures and the same first seeds in this environment. The static model predicts 7.8% failures; the observed 10.4% is 2.6 percentage points higher, about 1.9 standard errors for 500 seeds. Part of the difference is the decision-directed PLL penalty measured in Section 5.2; the rest is sampling uncertainty.

The test docstring's \(\sigma<\delta/3\) is not a zero-error guarantee. For a *bounded* jitter \(|J|\le J_{\max}\), the static decoder is error-free when \(J_{\max}<\delta/2\). The PLL's baseline moves, so its sufficient condition is tighter: \(J_{\max}\le\delta/4\) (Section 5.1). If "bounded Gaussian" means a \(3\sigma\) bound, the safe PLL condition is \(3\sigma\le\delta/4\), or \(\sigma\le\delta/12\). The short test has \(3\sigma/\delta=0.5\), twice the safe bound; the WAN test has \(0.24\), just inside it.

## 5. What the PLL changes

### 5.1 Bounded jitter: a sufficient condition

Let \(e_k=\hat\Delta_{0,k}-\Delta_0\) be the baseline tracking error. When the decoded symbol is correct,

\[
e_{k+1}=(1-\alpha)e_k+\alpha J_k .
\]

If \(|J_k|\le J_{\max}\) and \(e_0=0\), then

\[
|e_k|\le J_{\max}\left(1-(1-\alpha)^k\right)<J_{\max}.
\]

The next decision variable is \(J_k-e_{k-1}\), so its worst-case magnitude is less than \(2J_{\max}\). The decision is correct when this is below \(\delta/2\). By induction, if the loop starts with no error and the bound holds, every decision stays correct. Hence

\[
J_{\max}\le\frac{\delta}{4}
\]

is sufficient for zero symbol errors under the PLL. This is a sufficient condition, not a necessary one; a particular finite sequence may survive a larger bound. The targeted run below drives the loop with 200 symbols at \(+J_{\max}\), then applies one symbol at \(-J_{\max}\). It is 201 symbols in total.

| \(J_{\max}/\delta\) | PLL symbol errors | mean baseline error (ms) |
| ---: | ---: | ---: |
| 0.20 | 0 | 0.1810 |
| 0.24 | 0 | 0.2172 |
| 0.25 | 0 | 0.2262 |
| 0.26 | 1 | 0.2355 |
| 0.30 | 1 | 0.2717 |

The transition at \(0.25\) is the predicted boundary. The run uses \(\delta=1\,\text{ms}\), \(\alpha=0.05\), and symbol 8.

### 5.2 White noise: the PLL does not remove it

For independent zero-mean Gaussian jitter and correct decisions, the recursion above is a first-order autoregression. Its stationary variance is

\[
\operatorname{Var}(e)=\frac{\alpha}{2-\alpha}\sigma^2.
\]

The next decision variable \(J_k-e_{k-1}\) has variance

\[
\sigma^2+\frac{\alpha}{2-\alpha}\sigma^2
=
\frac{2}{2-\alpha}\sigma^2,
\]

so the effective jitter standard deviation is \(\sigma\sqrt{2/(2-\alpha)}\), slightly *larger* than \(\sigma\). For \(\alpha=0.05\), the factor is 1.0127. This is the white-noise penalty: the PLL trades some decision margin for drift tracking.

The simulation confirms the variance prediction in the error-free regime. With \(\sigma/\delta=0.05\) and 200,000 symbols, the measured ratio \(\operatorname{Var}(e)/\sigma^2\) is 0.02544, against the predicted \(0.05/1.95=0.02564\). Once errors occur, decision-directed updates add jumps of order \(\alpha\delta\), and the measured ratio rises:

| \(\sigma/\delta\) | measured \(\operatorname{Var}(e)/\sigma^2\) | linear prediction | static SER | PLL SER | genie SER |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 0.02544 | 0.02564 | 0 | 0 | 0 |
| 0.20 | 0.03039 | 0.02564 | 0.011535 | 0.013000 | 0.012620 |
| 0.30 | 0.05542 | 0.02564 | 0.089610 | 0.097915 | 0.093510 |
| 0.40 | 0.11624 | 0.02564 | 0.197010 | 0.220295 | 0.202190 |
| 0.50 | 0.13753 | 0.02564 | 0.296560 | 0.325635 | 0.301610 |

The `genie` decoder is an analysis-only baseline that uses the transmitted symbol in the phase error. It isolates the pure tracking penalty from the decision-directed penalty. At \(\sigma/\delta=0.20\), the PLL SER is 1.13 times the static SER and the genie is 1.09 times; at \(0.50\), the PLL is 1.10 times and the genie is 1.02 times. The PLL's extra penalty grows when symbol errors are common, because a wrong decoded symbol pushes the baseline in the wrong direction. The long error runs grow from a maximum of 3 at \(\sigma/\delta=0.20\) to 13 at \(0.40\) and \(0.50\); the conditional probability of an error after an error is only slightly above the unconditional rate, so the clustering is mild in this stream but the baseline variance is clearly outside the linear prediction.

All three SER columns in this table come from the same 200,000-symbol simulated stream, so the comparison is paired; the exact static SER at \(\sigma/\delta=0.20\) is \(1.164\times10^{-2}\). A table entry of `0` means no errors were observed in that stream, not that the exact error probability is zero.

### 5.3 Drift: a lock boundary at \(\alpha\delta/2\)

If the true baseline drifts by \(s\) per symbol, the error recursion becomes

\[
e_{k+1}=(1-\alpha)e_k+\alpha J_k-s.
\]

Ignoring jitter, the steady-state lag is \(e^*=-s/\alpha\), so the decision variable has mean \(s/\alpha\). A sufficient condition for keeping the margin under bounded jitter is

\[
\frac{s}{\alpha}+J_{\max}<\frac{\delta}{2}.
\]

With zero jitter, the boundary is \(s<\alpha\delta/2\). The targeted run uses \(\alpha=0.1\), \(\delta=1\,\text{ms}\), 500 symbols, symbol 8, and zero jitter. The drift column is in units of \(\alpha\delta\) per symbol.

| drift \(/\,(\alpha\delta)\) | PLL errors / 500 | static errors / 500 | PLL mean baseline error (ms) |
| ---: | ---: | ---: | ---: |
| 0.20 | 0 | 474 | -0.1764 |
| 0.40 | 0 | 487 | -0.3528 |
| 0.49 | 0 | 489 | -0.4322 |
| 0.50 | 47 | 489 | -0.5171 |
| 0.51 | 462 | 490 | -4.9438 |
| 0.80 | 490 | 493 | -6.8516 |

The transition at \(0.50\) is the predicted lock boundary. Beyond it the loop does not merely make a few isolated errors; it slips, and the mean baseline error jumps to nearly five symbols. This is a qualitatively different failure mode from white noise. It also explains why the source's drift test passes: it drifts 10 ms over 80 symbols, or 0.125 ms per symbol, with \(\alpha=0.1\) and \(\delta=8\,\text{ms}\). That is \(0.156\) in the table's units, well inside the tracking region.

## 6. What this supports and what it does not

**Supports:**

- An exact static-decoder SER and BER for the stated Gaussian model, with a seeded Monte Carlo check.
- A sufficient bounded-jitter condition for the decision-directed PLL: \(J_{\max}\le\delta/4\).
- The AR(1) baseline-variance prediction in the error-free regime, and the observed departure from it once symbol errors are common.
- A drift-tracking boundary at \(s=\alpha\delta/2\), with a sharp lock-loss transition beyond it.
- A horizon-aware reading of a zero-BER run: \((1-P_{\text{sym}})^N\), not a guarantee.
- The observation that the WAN benchmark's zero BER is expected from its large \(\delta/\sigma\), and that its Gilbert-Elliott channel is not exercised by the timing benchmark.

**Does not support:**

- A general "zero BER under Gaussian jitter" claim. Gaussian jitter is unbounded; the exact SER is positive for every \(\sigma>0\).
- A claim that the PLL improves white-noise error rates. In the error-free regime it slightly increases decision variance; with errors it adds decision-directed jumps.
- A claim that the Gilbert-Elliott burst-loss model was tested by the timing benchmark. It was not.
- A capacity claim. The Anantharam-Verdú queue timing expression
  \[
  C_{\text{timing}}=\lambda\log_2(\mu/\lambda),
  \qquad
  C_{\text{timing}}^{\max}\approx0.5307\,\mu\ \text{bits/s}
  \]
  belongs to a queue timing channel with arrival rate \(\lambda\) and service rate \(\mu\). It is not a capacity bound for this discrete cadence modulation, which uses a different input alphabet, decoder, and notion of a symbol slot. This experiment does not compute DCM capacity.
- Hardware, network, or implementation measurements. All results are model and simulation.

## 7. Reproduce

```text
python -m unittest discover -s experiments/cadence-channel -p "test_*.py" -v
python experiments/cadence-channel/cadence.py --scan --source-checks --trials 200000 --seed 20261112 --json --out experiments/cadence-channel/results/cadence-scan.json
```

The complete artifact is [results/cadence-scan.json](results/cadence-scan.json). It contains the scan rows, the two source-test reproductions, the bounded-jitter and drift probes, and the baseline-variance check. The `horizon_cap` field records the \(10^9\)-symbol reporting cap: a `null` horizon means the computed 95% horizon exceeds the cap, not that the error probability is zero.

The artifact in this repository was generated with Python 3.14.0 on Windows. CI uses Python 3.11 and runs the tests plus a smaller scan. The exact error probabilities do not depend on the random seed. The 52/500 source replay count does depend on the RNG path and Python version; the exact clean probability, 0.9221, is the stable prediction.

## 8. Source and related work

Source inspected at E-CPU commit `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`:

- `mailcpu/timing_channel.py` — `TimingChannelConfig`, `CadenceModulator`, `CadenceDemodulator`, and the PLL update.
- `mailcpu/substrate_sim.py` — `WanSubstrateSimulator`, `benchmark_timing_channel`, and the Gilbert-Elliott channel.
- `tests/test_timing_channel.py` — the short jitter test and the drift-tracking test.
- `tests/test_substrate_sim.py` — the WAN timing benchmark and its zero-BER assertion.
- The exploration note's timing-channel section and its conservation-law section.

This experiment is an independent reimplementation of the described semantics, not a copy of E-CPU code. The companion [in-transit memory](../in-transit-memory/README.md) experiment treats packet loss and retention; this one treats timing symbols and jitter. Both make the same distinction between a finite simulation result and a general law.

## 9. Open questions

- What is the capacity of this discrete cadence channel under Gaussian jitter, and how much does nearest-neighbour decoding lose relative to joint decoding?
- What happens under correlated or bursty timing jitter, rather than independent per-symbol noise? The Gilbert-Elliott channel is a packet-erasure model, not a timing-jitter model; a combined model needs both.
- How should a receiver handle erased symbols, and what timing reference survives a burst?
- What is the optimal \(\alpha\) for a joint drift-plus-jitter objective, and how does it depend on the drift rate and the symbol rate?
- Can the source tests assert a statistically meaningful bound (for example, an error count within a confidence interval of the exact prediction) instead of `ber == 0.0`?
- Does a non-Gaussian or truncated jitter distribution change the bounded-jitter guarantee in a way that is measurable?
