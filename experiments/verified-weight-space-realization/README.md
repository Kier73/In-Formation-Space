# Verified Weight-Space Realization

**Experiment:** WSP-002 · Structured Algorithm Compilation and Equivalent-Weight Navigation  
**Status:** <em>verified within the declared finite domain</em> by the pinned WSP-002 workflow. See the [retained CI evidence and parameter measurements](results/ci-run-43296273607.md).

This experiment continues the existing WSP-001 baseline. It does not repeat XOR/AND as its central result. It asks whether a composed finite-state law can be compiled through three routes, revised at both a local and algorithmic level, and moved through known ReLU parameter symmetries without changing its declared observations.

## Target Ground

The four Boolean inputs are ordered (q2, q1, q0, d) and the three outputs are (next_q2, next_q1, next_q0):

\[
q'_2=q_1,\qquad q'_1=q_0,\qquad q'_0=q_2\oplus q_0\oplus d.
\]

The complete one-step domain has 16 inputs. A separate scalar reference is retained in the runner; the neural compiler is never its own oracle.

## Three construction routes

1. **Truth-table minterms:** compile all 16 rows into ReLU row detectors.
2. **Direct expression DAG:** compile the typed Boolean expression without using the enumerated table as its construction input.
3. **Liveness-compacted DAG:** prune raw inputs and intermediate features once their final use has passed.

The runner compares each realization against the scalar law, typed program, MailCPU reference interpreter, MailCPU queue interpreter, and VGI Signal8 reference on every input row. It records total dense slots separately from nonzero active parameters.

## Two distinct semantic edits

- **Local exception:** input (1,0,1,0) changes from (0,1,0) to (0,1,1). The minterm realization is changed using E-CPU's guarded table intervention; the DAG realizations are independently recompiled from the edited typed source.
- **Law-level edit:** replace the feedback expression q2 XOR q0 XOR d with q2 XOR q0 XOR NOT d. This is a compositional source change and flips the third output bit on all 16 rows.

Both edits receive complete-domain verification.

## Equivalence navigation

The runner generates 20 distinct minterm-network parameterizations through hidden-unit permutations and positive power-of-two rescalings with compensating downstream weights. It checks distinct artifact digests, identical observations on all 16 declared inputs, exact inverse restoration of the original artifact, symmetry controls on the direct and liveness-compacted compiler routes, and an uncompensated permutation negative control that must produce a counterexample.

This is observer-relative equivalence on {0,1}^4, not a claim of universal or continuous-domain equivalence.

## Stateful and recurrent checks

The runner exhausts all 256 length-eight input sequences from all eight initial states: 2,048 trajectories and 16,384 transitions. It then revises a live runtime from the baseline feedback law to the input-inverted law, requires state and logical tick to remain unchanged at the revision boundary, and checks snapshot replay plus event-tamper rejection.

## Run

With E-CPU and VGI checkouts pinned to the revisions in the workflow:

~~~bash
PYTHONPATH=external/E-CPU:external/Virtual-Ground-Interpreter/virtual_ground_interpreter \
  python experiments/verified-weight-space-realization/run_experiment.py \
  --output experiments/verified-weight-space-realization/results/local-run.json
~~~

The [pinned GitHub Actions workflow](https://github.com/Kier73/In-Formation-Space/actions/runs/43296273607) passed this experiment and the focused E-CPU/VGI regression suites. The retained run note records exact source revisions, the output-artifact digest, parameter counts, and verification totals. This establishes only the explicit finite-domain and replay claims above. It does not establish arbitrary trained-network interpretation, real-valued input behavior, continuous robustness, distributed execution, or a performance advantage.

## Research ownership

- **VGI:** independent bounded semantic/reference execution.
- **E-CPU:** typed program, ReLU compilers, intervention, MailCPU execution, and stateful runtime.
- **In-Formation-Space:** orchestration, blind spots, evidence, comparisons, and retained research history.

The full research programme is described by WSP-PLAN-002. The present experiment implements its first discriminating milestone.
