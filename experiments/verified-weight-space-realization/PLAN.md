# WSP-PLAN-002 execution record

This directory is the implementation workspace for **Verified Weight-Space Realization**.

The research proposition is that meaning, algorithm, representation, and realizer remain distinct. A typed law may have several representations, including a neural parameterization. Artifact identity is not functional identity; every equivalence claim is relative to a declared domain, output projection, and observation contract.

## WSP-002 target

Use the three-bit input-driven feedback law:

\[
(q_2,q_1,q_0,d)\mapsto(q_1,q_0,q_2\oplus q_0\oplus d).
\]

The complete single-step domain has 16 inputs. Compile through truth-table minterms, a direct Boolean expression DAG, and a liveness-compacted DAG. Compare to independent scalar, MailCPU reference/queue, and VGI Signal8 observations.

## Discriminating tests

1. Apply a one-row semantic exception and a global feedback-law edit.
2. Construct distinct ReLU parameterizations using hidden-unit permutation and positive scaling with compensating downstream weights.
3. Require exact finite-domain agreement, different artifact digests, inverse restoration, and a failing uncompensated-permutation control.
4. Exhaust all 2,048 length-eight trajectories from all eight initial states.
5. Revise the live transition law without changing current state or logical tick; verify replay and tamper rejection.

## Measurement discipline

Report architecture, dense parameter slots, active parameters, active fraction, source/program/model digests, changed coordinates, observation digests, exact case count, trajectory count, and limitations separately. The finite-domain observation digest is an index for a declared observation set, not a universal proof of function equality.

## Evidence status

The runner and workflow are the executable specification. CI results must be recorded with exact E-CPU, VGI, and In-Formation-Space revisions. Before a successful pinned workflow exists, the status remains **candidate / verification pending**. A source artifact, passing focused finite tests, and a cross-repository integration result are different evidence layers.

## Repository responsibilities

- VGI provides the bounded semantic reference.
- E-CPU owns typed transition semantics, neural realizations, model intervention, and stateful execution.
- In-Formation-Space preserves the experiment, provenance, result summaries, and unresolved questions.

No claim is made for arbitrary real-valued inputs, trained-network decompilation, distributed tensor execution, or hardware performance.
