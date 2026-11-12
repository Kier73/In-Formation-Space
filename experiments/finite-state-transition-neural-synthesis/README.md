# Finite-state transition neural synthesis

**Status:** experiment branch; deterministic compiler and integration runner implemented.

This experiment moves from isolated Boolean gates to a finite-state transition relation with interacting state, control, and priority conditions.

## Transition ground

The source machine is a reset-dominant two-bit counter expressed as a compositional typed Boolean program using input, constant, NOT, AND, XOR, and conditional-select nodes. The program is exhaustively evaluated into a 16-row table as a compiler intermediate. Its input tuple is ordered:

[
(state_1,state_0,advance,reset)
]

Its output tuple is:

[
(next_state_1,next_state_0)
]

The transition law is:

[
s' =
egin{cases}
0 & reset=1 \\
(s+1)\bmod 4 & reset=0\land advance=1 \\
s & reset=0\land advance=0
end{cases}
]

The complete input domain contains (2^4=16) rows. The full truth table is retained in the experiment JSON.

## Typed source and table derivation

E-CPU's `two_bit_counter_program()` describes the baseline transition rule without manually listing its 16 rows. The edited machine is built with `FiniteTransitionProgram.with_row_output(...)`, which composes one exact input-pattern selector around the existing output expressions. Both typed programs are enumerated independently, and the edited table is checked against a direct one-row table replacement before neural realization.

The resulting compilation path is:

`typed transition program → complete finite table → neural minterms + MailCPU executable reference`

## Direct neural realization

E-CPU compiles each table row (r) into a hidden ReLU minterm:

[
h_r(x)=\operatorname{ReLU}
\left(
\sum_i
\begin{cases}
x_i & r_i=1 \\
1-x_i & r_i=0
\end{cases}
-(n-1)
\right)
]

For a Boolean input (x), this hidden value equals one precisely when (x=r), and zero for all other table rows. The output layer sums the minterms whose declared output bit is one.

Two layouts are tested:

| Architecture | Total parameters | Hidden representation |
|---|---:|---|
| (4-16-2) | 114 | 16 row-minterm units |
| (4-16-16-2) | 386 | 16 row-minterm units plus one identity-copy layer |

The second architecture retains the first layer's row identity through an additional hidden layer. Neither network is trained.

## Local semantic intervention

The baseline table gives reset priority. One row is then changed:

[
(0,1,1,1): (0,0)\longrightarrow(1,0)
]

This means that when the machine is in state (01) and both `advance` and `reset` are asserted, the edited model increments to (10) instead of resetting to (00).

Because the hidden layer has one unit for each complete input row, this semantic change can be realized by changing exactly one final-layer weight. The model records both table digests, both model digests, and the precise output-weight coordinate. All other table rows must remain unchanged.

## Three executable representations

- **VGI:** the existing typed task DSL expresses the transition table as nested equality/conditional expressions. Signal8 maps Boolean bits to the subgroup ({0,4}).
- **E-CPU reference program:** the table compiler builds a MailCPU program by forming the conjunction of input literals for every row and branching to that row's output block.
- **Neural realization:** E-CPU directly constructs the ReLU weights from the same total table.

The integration runner checks both the baseline and edited transition tables through all four execution paths: VGI, MailCPU reference, MailCPU queue, and both neural architectures. Each source/target comparison is bound by a semantic `TranslationContract` that includes the digest of the typed source program as well as the derived table, executable MailCPU program, neural snapshot, and input case.

## Reproduction

The focused integration workflow pins exact E-CPU and VGI revisions, runs the cross-representation experiment, runs E-CPU's dedicated transition/weight-space tests, runs VGI's Boolean and finite-transition tests, and uploads deterministic JSON evidence.

Locally, with both packages importable:

```bash
PYTHONPATH=/path/to/E-CPU:/path/to/Virtual-Ground-Interpreter/virtual_ground_interpreter \
  python experiments/finite-state-transition-neural-synthesis/run_experiment.py \
  --output experiments/finite-state-transition-neural-synthesis/results/local-run.json
```

Focused tests:

```bash
(cd /path/to/E-CPU && python -m pytest tests/test_transition_space.py -q)
(cd /path/to/Virtual-Ground-Interpreter/virtual_ground_interpreter && \
  python -m unittest discover -s tests -p 'test_finite_state_transition.py' -v)
```

## Evidence boundary

The experiment targets a complete finite Boolean domain, not continuous state or arbitrary algorithms. The truth-table compiler scales exponentially with input width because it allocates one minterm unit per input row. The model's behavior outside the declared Boolean input domain is not part of the proof. No generalization, stochastic robustness, quantization tolerance, training, or hardware performance is claimed.

The next useful difficulty increase is to remove the explicit complete truth table from the compiler input and derive the state rows from a typed transition program or a compositional decision graph, while retaining exact independent execution and provenance.

## V3: direct compositional neural compiler

The next compiler path now starts from the typed Boolean expression DAG and generates ReLU features directly, without first creating one hidden unit for every possible input row. It supports the same source nodes (input, constant, NOT, AND, XOR, SELECT), structurally shares repeated AST nodes, and self-verifies its generated model over the complete small Boolean domain.

The integration runner now compares four neural realizations: two truth-table minterm networks, the direct compositional network for the source program, and a directly compiled network for the edited one-row override. This gives 96 cross-representation cases. See [the v3 result and parameter comparison](results/ci-run-43157537916.md), [the retained summary JSON](results/ci-run-43157537916-summary.json), and [the successful workflow](https://github.com/Kier73/In-Formation-Space/actions/runs/43157537916).

One important measured limitation: the compositional source network uses 54 active parameters in 335 dense slots, better than the table models' 84/100 active parameters, but the edited override expression expands the DAG and costs 130 active parameters in 1,678 dense slots. The current compiler preserves feature paths through dense identity layers; compositional compilation therefore is not automatically compression. This points to the next optimization: feature liveness and sparse/compact layer construction, especially for row-selector subexpressions.

## V4: liveness-compacted compositional compiler

The liveness compiler adds a third neural construction path and prunes hidden features once no later AST node or output needs them. The successful [v4 workflow](https://github.com/Kier73/In-Formation-Space/actions/runs/43158333796) checks 128 cases across three compiler families. Its [provenance note](results/ci-run-43158333796.md) and [summary JSON](results/ci-run-43158333796-summary.json) preserve exact revisions, model digests, and parameter counts.

The live-feature compiler reduces the baseline compositional model from 335 to 109 dense parameters (54 to 37 active), and the one-row override from 700 to 163 dense parameters (81 to 50 active). The full 16-row transition relation and the one-row edit remain exact in every representation. The remaining dense storage overhead is documented as a separate next optimization target.

The edge-tested repeat of v4 is [workflow 43158552396](https://github.com/Kier73/In-Formation-Space/actions/runs/43158552396). Its artifact is byte-identical to the first v4 result and includes the extra leaf/input-pruning tests from E-CPU revision `5edccfcdd9f3173746b1e0f36ca0286c4cb39dc9`. See the [edge-tested provenance note](results/ci-run-43158552396.md) and [summary](results/ci-run-43158552396-summary.json).

## V6: stateful model revision and replay

The E-CPU stateful runtime is now integrated. A live state of `01` holds for one logical tick, accepts a transition-program revision without changing state or tick, then follows the revised exceptional transition to `10`. The step/revision/step history is hash-chained and the runtime snapshot is restored by replaying every event. A modified event is rejected.

The [v6 workflow](https://github.com/Kier73/In-Formation-Space/actions/runs/43227224371) passed the 128 one-step cases, 2,048 three-step recurrent trajectories, the runtime lifecycle comparison against VGI and both MailCPU interpreters, and all focused E-CPU/VGI tests. See the [v6 result note](results/ci-run-43227224371.md) and [summary JSON](results/ci-run-43227224371-summary.json).

The runtime's local patch lifecycle proves that the current typed program and neural model can be revised while retaining state/time and recording a replay-verifiable event chain. It is not yet a concurrent, distributed, durable, signed, or physical vCPU runtime.

## Compiler algebra corpus and invariant registry

The E-CPU transition compiler tests include 24 seeded, structurally varied Boolean transition programs. Each is exhaustively evaluated on its complete 3-input domain and compared across truth-table minterms, direct expression-DAG synthesis, and liveness-compacted expression-DAG synthesis.

E-CPU also records explicit N-7…N-12 invariant entries for finite table completeness, neural equivalence, commit-on-match stepping, state/time-preserving model revisions, snapshot replay/tamper rejection, and the governing mathematics annotations required on all neural modules.

The updated IFS workflow pins E-CPU at `5a3b97cba802889976c815421e4ffffac7e4bdcc`. The [latest run](https://github.com/Kier73/In-Formation-Space/actions/runs/43229568660) passed the 128-case transition experiment, 2,048 recurrent trajectories, the stateful runtime lifecycle, 21 transition compiler tests (including the generated corpus), 8 Boolean weight-space tests, 11 stateful runtime/registry tests, and both VGI reference suites. See the [provenance summary](results/ci-run-43229568660-summary.json) and [result note](results/ci-run-43229568660.md).
