# IGC-001 — Intention-conditioned Ground construction

**Status:** executable finite mathematical construction with independent Python/Node verification. **Not** a universal intention compiler, natural-language understanding system, new execution authority, a physical realization, or a new algorithmic theorem.

## Question

Can a system receive a description of *what behavior must exist*, **without being handed its states or architecture**, construct the smallest state-space that realizes that description, and independently prove both feasibility and a specific obstruction when the host is too small?

This experiment complements existing [E-CPU IPS-003](https://github.com/Kier73/E-CPU/blob/main/docs/GENERATIVE_GROUND_CONSTRUCTION_IPS003.md) and [IPS-004](https://github.com/Kier73/E-CPU/blob/main/docs/QUALIFIED_GENERATED_GROUND_IPS004.md). Those already synthesize and realize bounded affine behavior through E-CPU's native machinery. IGC-001 deliberately explores a **different Ground family: regular languages of temporal input traces**. It does not introduce another Hypervisor, Virtual Layer or admission registry.

## Intent as a mathematical condition, not a machine

The external observer declares:

- a finite alphabet of input tokens (e.g., `0` and `1`);
- a finite regular-language expression with `symbol`, `empty`, `epsilon`, `alt`, `concat` and `star`;
- named positive/negative behavioral examples, which must be compatible with that language;
- a host state-capacity ceiling.

It does **not** declare an initial state, internal states, transition table, register architecture, implementation word or number of states actually necessary.

The test intention is the language of all binary words ending in `01`: `(0|1)*01`. The compiler derives a three-state deterministic automaton:

| Constructed state | Input `0` | Input `1` | Accepting? |
| --- | ---: | ---: | --- |
| 0 (empty prefix) | 1 | 0 | No |
| 1 (seen suffix `0`) | 1 | 2 | No |
| 2 (seen suffix `01`) | 1 | 0 | Yes |

This state numbering is a canonical reachability ordering; state identity is relational rather than arbitrary register naming.

## Mathematical construction, independent proof

**Python producer:** use Brzozowski derivatives to construct reachable residual languages; minimize by deterministic partition refinement; BFS-canonicalize the resulting automaton. Return a SHA-256-bound typed Ground and an auditable certificate.

**Independent Node receiver:** use Thompson's epsilon-NFA construction from the original regex AST—**not** the producer's derivative code. Check language equivalence via exhaustive reachable **product automaton** of proposed DFA state and independent NFA-state subset. This checks **all finite words**, not only a bounded test horizon. No source prediction or time-series learning is involved.

**Minimality proof:** each derived state is reached by a source-word prefix; for every pair of distinct states, a suffix is provided that makes their accepted result differ. The receiver checks every prefix and distinguishing suffix. By the Myhill–Nerode principle, an equivalent deterministic finite machine requires at least as many states. State equality is derived from future observable behavior.

For the example, the three reachable words are `[]`, `[0]`, `[0,1]`. The distinguishing suffixes are `[1]` for states 0 vs 1 and the empty suffix for 0 vs 2 and 1 vs 2.

No third-party computation, signature or physical device is implied by matching mathematical behavior.

## Three distinct verified outcomes

1. **Realized under declared capacity:** capacity = 3. The synthesized machine has exactly three states. Python and independent Node independently verify it.
2. **Insufficient declared state capacity:** capacity = 2. The same source language requires three pairwise distinguishable residual states. This is an **exact impossibility result relative to deterministic finite machines realizing the stated regular language and the declared two-state capacity**—not impossibility across all computing substrates.
3. **Incompatible language constraints:** demand the one-token word `[0]` be accepted despite the declared language `(0|1)*01`. Return the exact contradictory word and acceptance facts. The receiver independently checks the counterexample.

A compilation/verification resource budget reached without a complete witness reports `budget_exhausted`, **not** mathematical impossibility. The independent Node receiver currently refuses budget-only reports rather than inventing an exhaustive proof of exhaustion.

## Navigating a constructed Ground

After constructing the Ground, request the state following `10^30` repetitions of `0`, then `1`. Both Python and Node navigate using binary composition of the transition function, with `O(N log t)` integer operations for fixed `N` states and requested repetition `t`. They agree on state **2**, accepting **true**. No trillion-step trace or extensive past history is generated.

The huge coordinate is exact mathematical action repetition, not a prediction of wall-clock time or a claim that a physical host performed `10^30` actions.

## Reproduction

```bash
python -m unittest discover -s experiments/intention-ground-construction -p 'test_*.py' -v
python experiments/intention-ground-construction/demo.py --output build/igc001
node experiments/intention-ground-construction/verify.mjs \
     build/igc001/realized.intention.json build/igc001/realized.receipt.json
node experiments/intention-ground-construction/verify.mjs \
     build/igc001/capacity-obstruction.intention.json build/igc001/capacity-obstruction.receipt.json
node experiments/intention-ground-construction/verify.mjs \
     build/igc001/contradiction.intention.json build/igc001/contradiction.receipt.json
```

The CI workflow runs the tests on Linux and Windows with Python 3.11/3.13 and Node 22, checks the three receipt classes, and retains a portable evidence bundle.

Local first-pass evidence: **17 unittest cases passed**, including 45 seeded synthetically varied regular-language constructions, full short-word comparisons, independent NFA product checks, malformed input refusal, self-rehashed forged transitions, false minimality witnesses, substituted intentions, illicit authority claims and a `10^30` navigation equality. The seeded finite comparisons are separate from Node's unbounded-word DFA/NFA equivalence argument.

## Exact authority and limitations

- **Mathematical construction:** yes, inside the declared finite regular-language family.
- **Mathematical feasibility and minimum state count:** yes, conditional on a complete independent product check and pairwise minimality certificate.
- **New physically runnable machine:** an executable transition table exists as data; this does **not** create a remote host capability, compile arbitrary code, access physical storage or deploy through E-CPU.
- **Natural-language interpretation:** not performed; the intention is a typed language AST. A natural-language-to-AST translator would require separate semantic evidence and user approval.
- **Any arbitrary algorithm or byte domain:** not established; the current alphabet is 1–8 explicitly declared ASCII tokens. The compiler does not synthesize non-regular computations.
- **Optimization:** minimal DFA states proven, not minimal energy, CPU cycles, physical gates, network cost or general VM size.
- **Cryptography:** SHA-256 checks deterministic content identity; neither it nor a returned certificate authenticates the sender or grants execution rights.
- **Complexity:** derivative expansion may exceed allocated resources. Even a regular language with a small description can require exponentially many DFA states. Receiver equivalence verification is bounded, and budget exhaustion remains unresolved.

## Next cross-repository realization

The next step should **reuse** E-CPU's IPS-003/004 execution machinery and VLD's existing finite-transition analysis, not build a new executor:

1. Convert this mathematically verified transition Ground into an existing typed E-CPU relation and have its **receiver-owned** Hypervisor choose a qualified implementation.
2. Exercise independent host/process execution with a source-bound Ground digest and an invariant-aware VGI observation contract.
3. Carry state and exact result receipts through actual mTLS and recovery, while refusing a forged or expired machine revision.
4. Measure synthesis, proof verification, transport, interpreter initialization, and repeated navigation costs together against direct simulation and lookup.
5. Broaden the intention language to non-regular specifications only with a sound proof system or an explicit unresolved status.

**Research interpretation:** the intended observable relation defines the mathematical space; the constructed states are equivalence classes of future distinguishability. The coordinate identifies an intended state position within that space; verification decides whether a particular host may realize it.
