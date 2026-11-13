# COE-001 — Continuous Observation Equivalence

**Status:** experimental exact symbolic comparison for *one scalar real input* and rational-weight feed-forward affine/ReLU networks; not a claim about arbitrary model inference, trained neural networks, or floating-point hardware.

## Why this question

[WSP-001](../cross-representation-weight-space/README.md) and [WSP-002](../verified-weight-space-realization/README.md) demonstrated semantically equivalent, differently parameterized networks on complete **finite Boolean domains**. This experiment asks something stronger within a deliberately smaller network language: can we distinguish *the whole real-valued function*, rather than only its declared sampled inputs?

A ReLU network with one scalar input, finitely many dense layers, and rational weights/biases is a continuous piecewise-affine map from the real line to an output vector. Each preactivation on an interval where its input expressions are affine has the form m*x + b. Its only possible interior activation change occurs at the exact rational root -b/m. Splitting there and propagating the resulting affine expression gives a complete description across **all real inputs**, including both unbounded tails. Adjacent intervals with the same affine output vector are merged.

The resulting ordered atlas is a normalized semantic representation: it may be identical for networks whose layer counts, hidden units, biases, and weight matrices differ. The semantic SHA-256 digest identifies the serialized rational atlas, not an authenticated claim about the producer.

## Discriminating examples

1. The single linear neuron f(x)=x and a two-hidden-neuron realization g(x)=ReLU(x)-ReLU(-x) have different structures but identical exact one-region semantic atlases. Their equivalence holds for every real x, under ideal exact arithmetic.
2. A triangular bump h(x)=ReLU(x)-2*ReLU(x-1/2)+ReLU(x-1) and the zero network agree at both Boolean inputs {0,1}, but differ in between. COE-001 produces the exact rational counterexample x=1/6 with outputs 0 and 1/6.
3. A positive-homogeneity rescaling of the first hidden unit of the triangular bump, ReLU(2*x)/2, changes the parameters, but yields the exact same four-region atlas.
4. If intermediate cells exceed a declared resource budget, the result is **unresolved**, not a false non-equivalence claim.

## Method and correctness argument

Start from the affine expression x, valid on the open interval (-infinity,+infinity). For every layer:

- Compute each preactivation by exact Fraction linear algebra over the incoming piecewise-affine vector.
- For a ReLU layer, isolate the strictly interior zero of every nonconstant preactivation in every current interval, and split at the union of those roots. Choose an exact rational interior point to decide each activation sign; the sign is fixed across that open interval because there are no remaining interior roots.
- For a linear layer, carry the affine output directly. Merge adjacent regions carrying equal affine output vectors.

Induction on layers establishes the atlas agrees with the network on every *open* output region. Affine/ReLU composition is continuous, so each finite breakpoint value equals the limiting value of its neighbors. Thus the atlas determines the result on the **entire** real line, not only at sampled interior points. For comparison, canonical maximal affine partitions suffice: two atlases are equivalent iff their normalized expressions and breakpoints match; otherwise, on an interval with differing affine expressions, at most one of two distinct exact rational interior points can hide a nonzero affine component. An independently executed rational evaluator confirms the chosen counterexample.

This argument uses *mathematical real arithmetic* and rational network parameters. It is not a proof about IEEE-754 rounding, transcendental activations, recurrent networks, arbitrary-dimensional inputs, or cryptographic authenticity. The code and tests supply algorithmic verification, not an independently machine-checked formal proof.

## Run

From the experiment directory (Python 3.11+, standard library only):

```bash
python -m unittest discover -s . -p 'test_*.py' -v
python run_experiment.py > continuous-equivalence-report.json
```

CI runs those commands and retains the deterministic report as an artifact. The test suite compares the symbolic atlas against a separate direct rational evaluator at exact breakpoints, interiors, and a deterministic random corpus of 120 networks. Such tests check the implementation; the universal equivalence claim follows from the exact piecewise-affine algorithm and its assumptions, **not** from random testing.

## Active-development questions

- Add an independently implemented certificate checker that verifies every root partition and affine law rather than trusting the constructing interpreter.
- Add a cost-aware decision procedure that defers splits when output cancelations are provable, with explicit unresolved results if budgets are exceeded.
- Map E-CPU rational ReLU realization snapshots into this restricted language, preserving source-Ground, compiler, and observer-projection identity without asserting that floating-point runtimes are exact.
- Generalize beyond one input with rational polyhedral regions, while recording the dramatic difference in complexity.

## Background

Piecewise-linear neural verification and exact partitioning are established approaches, not inventions claimed here. See [Bunel et al. (JMLR 2020)](https://jmlr.org/papers/v21/19-468.html) and [Advances in verification of ReLU neural networks](https://link.springer.com/article/10.1007/s10898-020-00949-1). COE-001 is an executable, tightly scoped bridge to observation-relative semantic identity in the three research projects.
