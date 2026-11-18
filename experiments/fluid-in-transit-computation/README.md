# Fluid In-Transit Computation: Lifting CPU, GPU & Virtual Memory Algorithms (`FIT-001`)

- **Epistemic Status:** **Verified** (on finite algebraic equivalence and counterexample suites in `test_fluid_transit_study.py`; physical WAN/NIC offload remains **Open / Unmeasured**).
- **Source Lineage:** Companion study to `vld.substrates.fluid_transit` in [`Kier73/Virtual-Layer-Dynamics`](https://github.com/Kier73/Virtual-Layer-Dynamics) (`v0.6.0`).

## Central Question

When machines act strictly as stream interpreters $I_v: \Sigma_{\text{wire}} \to \Sigma_{\text{wire}}$ along a communication path, which CPU loops, GPU tensor reductions, and Virtual Memory movements lift from hardware mimicry into associative or contravariant **in-transit stream transformations**—and where must premature collapse be refused?

## Three Mathematical Lifts & One Negative Control

1. **CPU Sequential Loops $\to$ Tropical $(\min, +)$ & Finite-Transducer Stream Monoids:**
   $$d^{(T)} = d^{(0)} \odot \left(\bigodot_{t=0}^{T-1} W^{(t)}\right), \qquad (A \odot B)_{i,j} = \min_k (A_{i,k} + B_{k,j}).$$
2. **GPU Multi-Shard Softmax Attention $\to$ Online Flash-Stream Associative Monoid:**
   $$(m_A, \ell_A, O_A) \otimes (m_B, \ell_B, O_B) = \left(m_{AB},\; e^{m_A - m_{AB}}\ell_A + e^{m_B - m_{AB}}\ell_B,\; e^{m_A - m_{AB}}O_A + e^{m_B - m_{AB}}O_B\right),$$
   with $m_{AB} = \max(m_A, m_B)$, normalizing ($O/\ell$) only at the terminal receiver.
3. **Negative Control (Premature Softmax Normalization):**
   Normalizing locally per hop ($O_h / \ell_h$) and averaging across shards discards the relative partition mass $\ell_h e^{m_h}$, yielding discrepancy $> 4.3$ on a 2-shard `[1.0, 10.0]` witness.
4. **Virtual Memory Movements $\to$ Contravariant Pullback Descriptors:**
   Composing `transpose_2d`, `rotate`, `reverse`, and sparse CoW overlays transmits $O(1 + |\Delta|)$ descriptor bytes instead of $\Theta(N)$ buffer copies, while invariant reductions (`sum`, `xor`) commute directly onto the unmoved base buffer.

## Reproduction

```bash
python -m pytest experiments/fluid-in-transit-computation/test_fluid_transit_study.py -v
```
