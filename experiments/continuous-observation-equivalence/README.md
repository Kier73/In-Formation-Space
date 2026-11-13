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


## COE-002 — Portable exact activation-cell certificates and independent checking

**Question:** Can a separately executed verifier establish a claimed complete-domain ReLU function *without running or trusting the algorithm that constructed the claim?*

COE-002 adds a two-sided protocol. The original atlas constructor emits a set of **atomic activation cells** across the entire real line. Unlike its normalized final-output atlas, these cells preserve all internal ReLU zero crossings, **including hidden changes that subsequently cancel in the final output**. A standalone Python standard-library checker has no import or call into the constructor, its direct evaluator, or the certificate producer. It **verifies proposed cells** rather than using COE-001's procedure to discover missing regions.

The certificate contains:

- Exact rational, one-dimensional affine/ReLU network layers (canonical integer or reduced fraction strings).
- A SHA-256 digest of the canonical network description; the independent checker also accepts an independently known expected network digest.
- An ordered, exhaustive cover of open intervals, with finite rational or unbounded endpoints, and the claimed affine output vector on each interval.
- The reduced, maximal affine output atlas and its COE-001-compatible semantic SHA-256.

For **each proposed atomic interval**, the independent checker symbolically starts from input affine form (1,0), propagates through every layer, and establishes that *every nonconstant ReLU preactivation's exact zero lies outside the interval's interior*. Its sign cannot change inside a zero-free interval, so activation branches are fixed and the claimed affine output is checked exactly. It rejects false laws, discontinuity, holes, overlaps, truncated tails, unsorted intervals, invalid rational representations, unknown fields, inexact parameter encodings, incorrect source/semantic digests, and disclosed-cell omissions. Since affine/ReLU networks are continuous, the checked open-interval laws also determine their endpoint outputs. The checker independently reduces the verified cells to the semantic atlas and verifies its digest.

A particularly important negative control takes the valid one-region **output** atlas for ReLU(x)-ReLU(-x)=x and presents it as a single **activation** cell over all reals. Even though its final function is correct, the checker rejects the certificate: the proposed cell conceals hidden sign changes at x=0. Providing the correct two activation cells passes, and the output digest still matches the one-layer identity function.

### Reproduce

From this experiment directory, using Python 3.11 or later:

~~~bash
python -m unittest discover -s . -p 'test_*.py' -v
python produce_certificates.py certificate-artifacts
python verify_certificates.py certificate-artifacts --output independent-certificate-report.json
~~~

The conformance suite includes adversarial cases for hidden sign changes, incomplete covers, altered affine coefficients, forged source fingerprints, altered reduced atlases, noncanonical rationals, duplicate JSON keys, unsafe formats, and resource ceilings, together with 120 deterministically generated rational networks. The certificate producer and verifier use the same **declared language and data format**, but distinct implementation algorithms; the validator reads no COE-001 module.

The [COE-001 GitHub Actions workflow](../../.github/workflows/continuous-observation-equivalence.yml) now includes separate certificate-producer and certificate-checker jobs. The first retains five canonical JSON certificate artifacts; the second downloads the artifacts and runs the standalone checker in a separately scheduled job. It retains a report recording exact source identities, exact semantic fingerprints, number of checked activation cells, and artifact-byte hashes.

### Scope of verification and remaining work

- **Mathematical statement:** all-real scalar input, finite feed-forward networks with *rational* weights and affine/ReLU activations, under ideal exact arithmetic; output vectors may contain multiple components. No floating-point rounding, physical timing, arbitrary activation, or multidimensional input is inferred.
- **Verification strength:** the checker independently validates a complete *claimed* activation partition; it does not rely on tests of finitely many input points. Failure or a configured verification budget exhaustion is not equivalence evidence. Construction budget exhaustion also remains unresolved.
- **Source identity:** a digest bundled with its own network description proves only consistency of those bytes. The hosted verifier additionally matches separately embedded expected fixture digests; **these are checked-in test pins, not external provenance or authenticated signatures**. Verification of a third-party network would require obtaining its expected source digest from an appropriate trusted context.
- **Process separation:** distinct GitHub Actions jobs and separate Python implementations are useful independence of execution and method, **not proof of independent organizations, hardware attestation, or separate administrative trust**.
- **Formal strength:** this is an independently implemented, finite-certificate arithmetic checker with a mathematical justification for all-real coverage. It has not been checked in Lean, Coq, or another proof assistant.

A useful next step is a small **Go or proof-assistant-based checker** for the same exact serialized certificate, reducing common-mode Python implementation risk; another is a trust-qualified bridge from E-CPU model/Ground identities to this rational certificate profile.


## COE-003 — Cross-language independent certificate verifier (Go)

COE-002 established that a second *Python* implementation can verify a submitted activation-cell proof without importing its constructor. COE-003 tests whether the exact same Python-produced certificate bytes can also be reconstructed and validated in a **different language**.

The standalone go_checker/main.go implementation uses only Go's standard library (math/big.Rat, encoding/json, crypto/sha256). It does not call Python, reuse the Python verifier, discover breakpoints using the COE-001 atlas builder, or accept the producer's output digest as authority.

For every submitted cell, Go:

1. Checks exact rational token grammar, matrix dimensions and independently pinned model SHA-256.
2. Checks the supplied intervals form an ordered, nonoverlapping, exhaustive partition of the entire real line.
3. Recomputes every layer's affine preactivations using big.Rat, proving no hidden ReLU activation root is strictly inside a claimed cell, and checks its output law and continuity at finite breakpoints.
4. Merges adjacent equal-output cells into a canonical maximal atlas, recomputes the semantic digest and requires exact equality with the submitted atlas and digest.
5. Confirms observational equivalence for x versus ReLU(x)-ReLU(-x) and for positive rescaling of a triangular-bump hidden neuron, while rejecting identity between the zero network and that bump.

The Go parser additionally reserializes the strictly restricted ASCII-token JSON profile and requires a byte-for-byte match, including exactly one final LF. This rejects noncanonical bytes and duplicate-key encodings. The six Go tests mutate Python-produced artifacts, requiring rejection of incorrect affine laws, concealed hidden transitions, mismatched expected network identities, altered source bytes, altered semantic digests and incomplete covers. The implementation is not a generic JSON canonicalization library.

### Reproduce across Python and Go

From this experiment directory, with Python 3.11+ and Go 1.23+:

~~~bash
python produce_certificates.py certificate-artifacts
COE_CERT_DIR=certificate-artifacts go test -v go_checker/main.go go_checker/main_test.go
go run go_checker/main.go certificate-artifacts > go-independent-check-report.json
~~~

The GitHub workflow has a dedicated **Go verifier job**. It downloads the exact artifact produced by the Python job, tests its own verifier implementation, and retains a separate machine-readable verification report. The Go verifier independently recovers network, semantic and certificate SHA-256 identities for all five declared fixtures.

### What this establishes—and does not

Agreement between independently implemented Python and Go checkers reduces common-mode implementation risk. The exact semantic statement is still restricted to **scalar real inputs and rational affine/ReLU feed-forward networks under ideal real arithmetic**, with explicit computational budgets. Identical SHA-256 digests identify identical canonical descriptions under this declared profile; the tests do not establish collision resistance by themselves or authenticate an author.

Both tools and their checked-in source pins still execute within one repository's GitHub CI trust context. Separate jobs and programming languages are **not hardware attestation, separate organizations, a verified mathematical kernel or a remote deployment**. The next useful step is proof-assistant formalization of the cell-checking lemma or integration with a separately trusted model/Ground identity.
