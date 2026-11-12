# RCN-001 execution plan

## Question

Across representative finite Boolean algorithm families, what structural costs do the current minterm, direct-DAG, and live-DAG compilers produce? Can a resource navigator preserve incomparable choices rather than conceal them behind one hand-weighted score?

## Method

1. Construct 16 typed programs: parity, multiplexers, ripple adders, comparators, a priority encoder, and a reset/load/shift/hold register.
2. Keep an independent scalar oracle separate from the typed expression builder.
3. Compile every source through all three existing E-CPU compiler routes.
4. Enumerate every Boolean input row.
5. Compile an experiment-specific binary decision tree over the complete table using E-CPU BRANCH/SET/HALT instructions, then compare the independent oracle, typed source, transition table, both MailCPU interpreters, VGI Signal8, and every neural route.
6. Bind each neural/reference comparison to an explicit E-CPU semantic translation contract.
7. Derive structural cost vectors and expose Pareto and objective-specific navigation.

## Cost semantics

The cost dimensions are dense parameter slots, dense multiply slots, hidden ReLU units, and layer depth. Active nonzero coefficients are reported separately because the current model forward implementation traverses dense matrices. The work counts do not claim physical latency.

No single aggregate score is produced. Hard budgets filter routes first; objective-specific queries can then minimize storage or dense multiply work. Ties remain sets.

## Reproducibility

The workflow pins exact E-CPU, VGI, and In-Formation-Space revisions. It retains all per-row outputs, translation-contract digests, cost profiles, route observation digests, and an aggregate result digest.

## Limitations

This is a finite benchmark corpus, not a proof over all Boolean programs. Its cost vectors are architecture-derived. Sparse execution, numerical formats, measured host latency, distributed realization, and arbitrary trained-network interpretation require separate experiments.


## First verification record

The pinned [RCN-001 CI run](https://github.com/Kier73/In-Formation-Space/actions/runs/43299824228) passed the Pareto/budget policy tests, complete cross-runtime workload matrix, E-CPU finite-transition compiler tests, and VGI finite-transition / Boolean-subgroup tests. The [retained evidence note](results/ci-run-43299824228.md) records exact source revisions, all 1,364 input rows, 4,092 semantic comparisons, cost observations, and the finite-domain verification boundary.
