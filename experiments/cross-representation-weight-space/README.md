# Cross-representation weight-space experiment

**Status: implementation in progress.** This experiment asks whether one small computational specification can be realized and checked through three distinct representations: VGI signal-state instructions, an E-CPU reference program, and an analytically generated neural network.

The first target is deliberately finite: two-input XOR, followed by a semantic edit to AND.

## What is being built

- **VGI reference:** use the Boolean subgroup embedding \(0\mapsto0, 1\mapsto4\) in \(\mathbb Z/8\mathbb Z\). Since \(4+4=0\pmod 8\), group addition realizes XOR. A nested equality/conditional expression realizes AND without adding new VGI opcodes.
- **E-CPU reference program:** use the existing MailCPU instruction algebra (COMPARE, BRANCH, SET, MUL, HALT) as an ordinary executable specification.
- **Neural realization:** the E-CPU module constructs a dense 2–85–112–1 ReLU MLP with exactly 10,000 parameters, including biases. Only nine parameters are nonzero for XOR and eight for AND. No optimizer, dataset, or training loop is used.
- **Intervention:** XOR becomes AND by changing only the two final-layer weights from (1, -2) to (0, 1).
- **Semantic evidence:** E-CPU's existing TranslationContract and paired-observation checker bind the program, model snapshot, input case, and exact output comparison. The VGI side separately exhausts its four input combinations.

The hidden features are:

\[
h_0=\operatorname{ReLU}(a+b),\qquad
h_1=\operatorname{ReLU}(a+b-1).
\]

For binary inputs, \(h_0\in\{0,1,2\}\) and \(h_1=a\land b\). The second hidden layer copies these values. The output is linear:

\[
\operatorname{XOR}(a,b)=h_0-2h_1,\qquad
\operatorname{AND}(a,b)=h_1.
\]

The final two coefficients are the only changed parameters. This is an exact construction over the declared finite input domain, not a claim that arbitrary trained networks can be synthesized this way.

## Repository locations

- E-CPU implementation: [mailcpu/weight_space.py](https://github.com/Kier73/E-CPU/blob/experiment/weight-space-programming/mailcpu/weight_space.py)
- E-CPU tests: [tests/test_weight_space.py](https://github.com/Kier73/E-CPU/blob/experiment/weight-space-programming/tests/test_weight_space.py)
- VGI tests: [test_boolean_subgroup.py](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/experiment/boolean-gate-weight-bridge/virtual_ground_interpreter/tests/test_boolean_subgroup.py)
- VGI task examples: [XOR](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/experiment/boolean-gate-weight-bridge/virtual_ground_interpreter/examples/boolean_xor.task.json) · [AND](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/experiment/boolean-gate-weight-bridge/virtual_ground_interpreter/examples/boolean_and.task.json)

## Run the integration experiment

With both repositories checked out locally:

\`\`\`bash
python -m pip install -e /path/to/E-CPU
python -m pip install -e /path/to/Virtual-Ground-Interpreter/virtual_ground_interpreter
PYTHONPATH=/path/to/E-CPU:/path/to/Virtual-Ground-Interpreter/virtual_ground_interpreter \
  python experiments/cross-representation-weight-space/run_experiment.py \
  --output experiments/cross-representation-weight-space/results/first-run.json
\`\`\`

The integration runner compares all four Boolean input pairs across the VGI task, E-CPU reference program, E-CPU queue interpreter, and generated weight model. It also records the exact parameter intervention and per-case paired semantic checks.

The focused repository tests are:

\`\`\`bash
(cd /path/to/E-CPU && python -m pytest tests/test_weight_space.py -q)
(cd /path/to/Virtual-Ground-Interpreter/virtual_ground_interpreter && \
  python -m unittest discover -s tests -p 'test_boolean_subgroup.py' -v)
\`\`\`

## Evidence boundary

A successful run would establish equivalence only for these two functions on the complete four-element input domain, under the specific VGI, MailCPU, and MLP implementations and observation projections used by the runner. It would not establish arbitrary program-to-network compilation, universal equivalence of neural representations, robustness outside binary inputs, learned generalization, or a hardware performance advantage.

The model is dense in its declared architecture and sparse in its active values. The 10,000 count includes zero-valued weights and biases; the active count is reported separately. The two-weight edit is an exact property of this chosen parameterization, not a general lower bound for XOR-to-AND interventions.

This work should be read as an executable seed for weight-space programming. The next discriminating experiment is to compile a less hand-shaped function into a distributed representation, then test whether the compiler can still produce a compact, inspectable intervention while maintaining independent semantic checks.

## Recorded run

The first two pinned GitHub Actions runs passed and produced byte-identical result JSON. See [the retained result](results/ci-run-43154718665.json) and [the provenance/evaluation note](results/ci-run-43154718665.md), including exact dependency revisions, model digests, intervention coordinates, and the bounded verification claim.
