# Independent review: guarded shortcut trade-off

**Status:** mathematical review; original experiment preserved.  
**Scope:** run_tradeoff.py, results/analysis.md, and the recorded tradeoff-encounter.json.

## Summary

The benchmark contains a useful result: affine matrix exponentiation produces the same recurrence result as direct iteration in the primary modulus while reducing the number of transitions from \(O(t)\) to \(O(\log t)\). The recorded measurements also show a crossover in the sampled environment.

The secondary-modulus guard in the original experiment does not verify the primary state, however. Its fault-detection conclusion is therefore unsupported.

## The mathematical issue

The original primary recurrence uses:

\[
x_{k+1}=(a x_k+b)\bmod M_p,\quad M_p=2^{61}-1.
\]

The proposed guard separately computes the same recurrence modulo \(M_c=2^{31}-1\) and compares that value with the primary state reduced modulo \(M_c\).

That comparison assumes the map from the primary residue ring to the check residue ring preserves the recurrence. It does not, because:

\[
M_p \bmod M_c=1{,}073{,}741{,}823\ne0.
\]

The reduction is not a ring homomorphism when \(M_c\) does not divide \(M_p\). Modular reduction at the primary modulus can subtract multiples of \(M_p\), which change the residue modulo \(M_c\).

For the original parameters at t=10:

| Quantity | Value |
| --- | ---: |
| Primary result reduced modulo Mc | 366,246,460 |
| Independent recurrence computed modulo Mc | 510,455,710 |

The values differ even without a fault. At t=10,000, the originally computed nominal check is 1,392,226,910 while the actual primary result reduced modulo Mc is 849,091,804. The original test compares the faulty primary result against the independent smaller-modulus orbit but does not test whether the no-fault primary state satisfies that relation. A true divergence flag is therefore not a valid detection result.

## Corrected construction in v2

The corrected check computes the affine transform modulo Mp*Mc, then projects in the correct order:

\[
\tilde U=U\bmod(M_pM_c),
\]

\[
x_p=\tilde U\bmod M_p,
\]

\[
r_c=x_p\bmod M_c.
\]

Since Mp divides Mp*Mc, the first reduction preserves the result modulo Mp. The result rc is therefore the correct check residue for the canonical primary state.

The new run_tradeoff_v2.py uses matrix operations for the primary result and a separate pair-based affine-composition implementation for the check path. The test suite requires the no-fault state to pass before the injected-fault case is evaluated.

This is still a bounded residue check. State differences that are multiples of Mc can go undetected; the v2 code includes a test demonstrating this limitation. One fault fixture does not prove general fault tolerance.

## Timing interpretation

The original data supports a measured comparison in one environment, not a universal speed law.

- The sampled measurements establish a crossover between t=10 and t=50.
- The stated t* approximately 28 is not supported by linear interpolation of the tabulated cost difference; that calculation gives approximately 30.4. The sparse sampling does not justify a precise threshold.
- The original script uses minimum timings, which favor unusually low samples. V2 uses medians and adds coordinates around the observed crossover.
- The measured navigation cost is c_sigma+c_g; the broader proposed equation also includes interpreter setup and fallback costs that are not measured in the original run.

## Files

- Corrected benchmark: run_tradeoff_v2.py
- Corrected tests: test_tradeoff_v2.py
- Original analysis, preserved with correction: results/analysis.md

## Disposition

Keep the original run as a useful historical construction and timing record. Do not rely on its H3 claim. Use v2 as the basis for future guard work, and expand the fault model before making broad reliability claims.
