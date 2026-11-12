# Realization Cost and Navigation

**Experiment:** RCN-001 · Compiler-cost landscape across finite Boolean workloads  
**Status:** candidate; pinned cross-repository CI is the verification gate.

This experiment follows WSP-002. Rather than adding another isolated function, it asks how three existing E-CPU compiler routes behave across a family of structurally different Boolean computations, and whether an explicit objective can navigate their trade-offs without inventing a universal score.

## Workload family

The current matrix has 16 workloads:

| Family | Workloads | Maximum input width |
|---|---:|---:|
| Parity | 4 | 8 |
| Multiplexer | 2 | 6 |
| Ripple-carry adder | 4 | 8 |
| Unsigned comparator | 4 | 8 |
| Priority encoder | 1 | 4 |
| Reset/load/shift/hold state control | 1 | 8 |

Every workload has a separately written scalar reference and a typed Boolean source program. The complete Boolean domain is enumerated.

## Realization routes

Each typed program is compiled using:

1. Complete truth-table minterms.
2. Direct compositional expression DAG.
3. Liveness-compacted expression DAG.

Each row is checked against the independent scalar reference, typed program, generated transition table, MailCPU reference interpreter, MailCPU queue interpreter, VGI Signal8, and every neural realization. Each neural/reference comparison receives a semantic translation contract.

## Cost model: keep unlike quantities separate

The report records:

- Dense parameter slots, including zero weights and biases.
- Nonzero active parameters and weight slots.
- Dense multiply slots for one forward pass.
- Bias-add slots and hidden ReLU units.
- Layer depth and maximum hidden width.
- Artifact and observation digests.

The current E-CPU forward implementation traverses dense matrices, including zero coefficients. Active-parameter count is therefore a sparsity diagnostic, not evidence of lower current execution work. Dense multiply slots and depth are structural estimates, not measured CPU/GPU latency. This experiment deliberately does not infer runtime savings from fewer nonzero values.

## Cost navigation

The navigator supports hard caps on dense parameter slots and dense multiply slots. After filtering infeasible routes, it can return:

- The Pareto frontier across dense parameters, dense multiplies, hidden ReLU units, and depth.
- The minimum-storage route set.
- The minimum-dense-compute route set.

It does not combine these quantities into a weighted score. When storage and forward work disagree, the result is an antichain of admissible choices. A caller can select a route only by stating a resource budget and/or an objective.

## Run

With the pinned E-CPU and VGI checkouts used by the workflow:

~~~bash
PYTHONPATH=external/E-CPU:external/Virtual-Ground-Interpreter/virtual_ground_interpreter \
  python experiments/realization-cost-navigation/run_experiment.py \
  --output experiments/realization-cost-navigation/results/local-run.json
~~~

The companion policy tests are run by the workflow. CI retains the full case evidence and exact source revisions.

## Evidence boundary

A successful run verifies only the selected finite Boolean workloads and their declared output projections. It does not establish the best compiler for every algorithm, continuous-domain equivalence, a sparse-runtime speedup, hardware performance, training/generalization, LLM weight interpretation, or distributed tensor execution.

## Why this sits beside WSP-002

WSP-002 demonstrated multiple exact realizations of one feedback law and constructive ReLU symmetries. RCN-001 varies the law itself and measures the structural costs of the available compiler paths. The next research question is not just whether a description can be realized, but which verified realization is admissible under a stated set of resources and intentions.
