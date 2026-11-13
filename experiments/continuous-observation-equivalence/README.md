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


## COE-004 — Link exact semantic certificates to E-CPU computational Ground identities

**Question:** Can the exact all-real observations certified by COE-001–003 be named inside E-CPU's actual representation/observation/translation identity model without granting an unauthorized or unverified Ground admission?

This is an **integration with the existing E-CPU Python contracts** (pinned to revision 3b57adcc2baaaa7e56e4bab943946f4e87e95c65), not a competing identity class.

- E-CPU RepresentationRef.from_payload() names the authored *candidate computational Ground profile*, the exact rational source network description, the verified maximal output atlas, and the certificate-verification mapping. Its content digest uses E-CPU's canonical_value_digest.
- E-CPU ObservationContract.from_definition() identifies the fixed output-atlas observer projection and its complete-domain meaning. Its comparison remains the existing E-CPU v1 canonical-json-exact comparison for serialized atlases; the **mathematical completeness** of the atlas is provided separately by the COE-002/003 activation-cell proof, not by an E-CPU object.
- E-CPU TranslationContract constructs the typed, immutable source-to-semantic-atlas reference, with mapping and observation identities, Ground/observer context digest, revision, effect class and replay class. Its digest distinguishes different source realizations even when their semantic outputs agree.
- The candidate Ground identity is the RepresentationRef for the immutable ground_profile.json description and is shared by all five tested models. It is not a registered StructuralMemorySpec or an admitted E-CPU Ground. Its profile declares language, arithmetic, all-real scalar domain, output arity, transformations, observer, and explicit non-admission.
- An independent receiver rebuilds all references and the TranslationContract using E-CPU at the same exact source revision. It verifies the raw mathematical certificate, requires the original source digest to match its **own pinned source policy**, matches the complete link, and retains ground_admitted=false and authority_granted=false in the output.
- Two representations of f(x)=x (linear and ReLU) give different source refs but identical semantic-atlas refs. Positive hidden-neuron rescaling also preserves semantic-atlas identity. A zero function and a triangular bump remain distinct even though both agree at Boolean inputs 0 and 1.

### Retained artifact roles

1. ground_profile.json is an explicitly authored, versioned candidate Ground description, **not authority**.
2. expected_ground_sources.json lives in the verifier checkout, pinning the E-CPU commit and five expected original network digests. It is **not copied from the producer artifact**. If repository policy can be maliciously changed, this experiment cannot defend against that administrative change.
3. ground_binding_producer.py constructs link artifacts from canonical COE-002 certificates after verifying the proof and checking the exact E-CPU Git checkout revision.
4. ground_binding_verifier.py receives both certificate bytes and untrusted link bytes, independently verifies the proof and rebuilds E-CPU identities. It rejects inconsistent context, source, observer, certificate, translation, revision or Ground-admission claims.
5. The extended workflow runs link production and verification in two separately scheduled jobs, each with its own pinned E-CPU source checkout, retaining link files and a machine-readable verification report.

### Run

Using a pinned E-CPU clone at repository-root external/E-CPU:

~~~bash
export PYTHONPATH="$PWD/external/E-CPU"
cd experiments/continuous-observation-equivalence
python produce_certificates.py certificates
python ground_binding_producer.py certificates links --ecpu-dir ../../external/E-CPU
python ground_binding_verifier.py certificates links --ecpu-dir ../../external/E-CPU --output independent-ground-link-report.json
python -m unittest discover -s . -p 'test_ground_binding.py' -v
~~~

### Verification versus authority

The mathematical claim is complete **only for the exact scalar rational affine/ReLU language and observer profile**, under ideal real arithmetic and bounded certificate-processing resources. E-CPU's RepresentationRef and TranslationContract are immutable *descriptions and identities*: they do not register a Structural Memory revision, approve a new Ground, issue a host capability, run a model, verify external provenance, or grant Hypervisor access. Production integration would need an explicit admission policy and receiver capability check from E-CPU's existing Ground/Hypervisor architecture, plus independently authenticated source evidence.

A natural subsequent frontier is formalizing a small certificate soundness lemma in Lean, while keeping separate the code-verification obligation that every serialized interval and each affine ReLU root is checked correctly.


## COE-005 — Lean-kernel-checked branch and complete-cover soundness rules

**Question:** Which mathematically critical implications in COE-002/003 can we have checked by an independent proof kernel rather than just reproduced in Python/Go?

The pinned Lean 4.15 project in the lean/ subdirectory proves two intentionally small rules without mathematical libraries or admitted proof holes. The branch theorem depends on Lean's foundational propext axiom (as reported by the kernel); the cover theorem depends on no axioms:

1. **Selected branch soundness:** For any value type, any Boolean activation predicate and any function, if the activation decision at an arbitrary x is the same as the decision at the selected probe, the piecewise chosen branch produces exactly the same result as the pointwise rectifying operator at x. This is independent of a particular ReLU numeric implementation.
2. **Complete observation cover transfer:** For any coordinate type X and any output type Y, if every x lies in at least one certified cell and two realizations equal the same claimed observation in each cell, they are equivalent at **every coordinate of X**. This is a universal quantified theorem; it does not rely on enumerating coordinates.

These are the logical rules exercised in the all-real COE checker, with premises that must still be established by the concrete code. In particular, the Lean development does **not** yet prove that the Python or Go root-exclusion algorithm ensures activation decisions cannot change inside a proposed interval; does not prove that cells cover the entire real line including endpoints; and does not formalize the JSON parser, Fraction arithmetic, source SHA-256, E-CPU admission or trust. **It therefore does not constitute end-to-end formal verification of COE-004.** The existing standalone verifier and cross-language tests remain necessary.

### Check

~~~bash
cd experiments/continuous-observation-equivalence/lean
lake build
lake env lean COECellSoundness.lean
~~~

The COE-005 workflow installs the pinned Lean compiler, checks the theorem statements in the kernel, retains the exact foundational-axiom report (allowing only the explicitly documented propext dependency for the branch theorem), and requires an intentionally false theorem in COECellInvalid.lean to fail. The negative control ensures this CI route does not accidentally accept a failed proof file.

The next formalization target is to prove the arithmetic bridge from a rational affine expression's root exclusion on a claimed interval to *sign stability* (with equality correctly handled at endpoints), then to connect that lemma to the verified symbolic layer evaluator. That step would discharge a substantive premise currently supplied only by the executable verifier.


## COE-006 — Kernel-checked rational root exclusion and sign stability

**Problem:** COE-002/003's exact certificate checker assumes a ReLU preactivation of the form m*x + b cannot change activation state inside an interval that contains no exact zero of that preactivation. COE-005 verified the *logical consequence* of stable activation decisions but did not prove this arithmetic premise.

COE-006 supplies the missing **rational arithmetic** bridge using Lean 4.24.0, pinned separately from the original COE-005 Lean 4.15.0 baseline because Lean's full built-in rational arithmetic/ordered-ring lemmas were added later. The proof is in lean/COERationalRoot.lean; this builds using the Lean standard library only, with no Mathlib dependency.

### Mathematically verified statements

1. **Excluded root is outside the cell:** If it is not true that left < root < right, then root <= left or right <= root. In particular, a root *on* a finite boundary does not invalidate an open-cell certificate.
2. **Rational affine monotonicity:** A positive slope yields a strictly increasing preactivation; a negative slope yields a strictly decreasing preactivation.
3. **Sign stability:** For an exact rational affine expression, an exact root witness satisfying m*root + b = 0, and a root-excluded open interval, the Boolean activation decision at any two interior rational points is identical. The proof handles positive slope, negative slope, and the slope-zero case.
4. **Constant affine function:** A zero-slope preactivation has the same activation decision at every rational input, even when it has no root because its bias is nonzero.
5. **Selection correctness:** Combining the arithmetic sign-stability result with COE-005's selected-branch theorem proves that the ReLU branch chosen by any interior probe agrees with the pointwise rectified preactivation at **every rational point in the certified open interval**.
6. **Endpoint root behavior:** At a certified exact root, the selected branch yields zero irrespective of which activation branch was chosen from the interior. This addresses roots *on* an interval endpoint; general endpoint continuity is still a separate obligation.

This version proves the property for rational points and rational coefficients. Extending the same conclusion to **all real input points** needs a corresponding real-number/ordered-field interpretation of the lemma (or a formal bridge showing the rational affine atlas determines the continuous real extension). Thus it does **not** independently establish all-real soundness of the entire serialized certificate. The COE-001/002 algorithmic all-real claim and Python/Go verification remain separate evidence.

The premise that the proposed root actually satisfies the affine zero equation must still be validated by the concrete checker: this theorem does not independently establish correctness of the Python/Go operation that computes root = -b/m. The theorem is not about multidimensional networks, floats, external source authenticity, or admitted E-CPU Ground authority.

### Negative control and trust statement

The file lean/COERootInvalid.lean intentionally attempts to assert that a positive-slope affine function has equal activation decisions at negative and positive points **without excluding its interior root**. The Lean kernel must reject it. CI also retains the original false-theorem negative control and the printed axiom-dependency output for all new theorems.

The newer ordered-ring automated proof uses foundational Lean axioms **propext, Classical.choice and Quot.sound**. Its exact dependency set is recorded and checked by CI, with no admitted proof holes (sorryAx). This is a kernel-checked proof under those explicitly listed foundations; **not** an axiom-free derivation or proof-assistant verification of the Python/Go source code.

### Reproduce

~~~bash
cd experiments/continuous-observation-equivalence/lean
lake build
lake env lean COERationalRoot.lean
# The next command must return a nonzero exit code:
lake env lean COERootInvalid.lean
~~~

A natural next experiment is to verify the computed root equation and interval inequalities directly from the wire-format rational tokens inside a small independent formal checker, then prove endpoint completion via continuity and extend the analysis from rational to real coordinates.


## COE-007 — Kernel replay of actual canonical certificate arithmetic

COE-006 established a Lean theorem: an exact rational affine preactivation whose zero lies outside a proposed rational cell has a stable ReLU branch throughout that rational cell. COE-007 asks whether **the actual producer's five certificate files**, rather than handwritten illustrative numbers, can be independently checked in a pinned Lean kernel.

### Producer-to-Lean transport

The certificate-producer job retains the unchanged COE-002 canonical JSON bytes. The independently scheduled Lean job downloads these artifacts, checks the repository's **verifier-owned** five-source SHA-256 manifest, and translates only the exact rational parameters and the claimed activation intervals into strongly typed Lean literals.

The adapter, emit_lean_certificates.py, **does not compute roots, calculate neural outputs or assert successful verification**. Its source pin and canonical JSON checks guard the translation boundary, but it remains ordinary unverified Python that must eventually be audited or replaced with a verified parser. Every emitted literal carries its original file hash; a separate manifest requires all five pinned sources and their source activation-cell counts.

### An independently implemented exact checker

The COEWireCheck.lean module is not generated by the Python producer and is compiled using the pinned Lean 4.24 toolchain. It reconstructs each neuron's affine preactivation through every layer using exact rational operations, checks each nonconstant preactivation's exact zero equation and its absence from the *interior* of the proposed activation cell, chooses the branch at an interior rational probe, and requires the reconstructed final affine output to equal the claimed output.

It also checks matrix dimensions, requires all intervals to form an ordered gap-free cover of the rational line from negative to positive infinity, and checks continuity of the declared output at adjacent finite endpoints. The generated data module contains a **closed Lean theorem proved by kernel reduction** for each of the five exact source certificates. The theorem states that the fixed Lean Boolean verifier returns true for the concrete certificate data; this is a substantially stronger check than sampling a handful of rational values.

Three further certificate bundles retain the original five pinned source descriptions but deliberately corrupt only their activation-cell claims: replacing a ReLU network's hidden activation partition with its deceptively correct compact output atlas, forging an interior output slope, and introducing a gap in the interval cover. The adapter transports all three mutations and **Lean must reject each attempted proof**. The CI gate retains positive proof source, source-file hashes, and the negative rejection logs.

### Limits of what the kernel result says

- The Lean closed theorem establishes that the **Lean verifier's exact rational computation** returns true on the encoded five certificate profiles. COE-005/006 separately establish branch-selection soundness *provided the corresponding root equation and interval assumptions hold*. These are complementary results, not yet a machine-checked proof that every branch of COEWireCheck implements those theorems.
- The transport from original JSON tokens to Lean literal expressions is still **unverified Python**. Distinct Python and Go proof checkers continue to verify the original certificate bytes, expected source identities, full semantic atlas and SHA-256 fingerprints. The Lean checker recomputes arithmetic independently but does not authenticate GitHub or E-CPU Ground authority.
- The theorem currently operates on **rational coordinates** and exact rational coefficients, not a mechanized all-real continuity argument. It does not justify physical floating-point execution, multidimensional networks, or arbitrary model architectures.
- A failure to compile a certificate does not imply a different mathematical function. It means the supplied complete-domain certificate was not accepted under the declared verification profile.

### Reproduce

With Python 3.11+ and Lean 4.24.0 and from the experiment directory:

~~~bash
python produce_certificates.py certificate-artifacts
python -m unittest test_lean_certificate_bridge -v
python emit_lean_certificates.py certificate-artifacts lean/GeneratedCertificateProofs.lean
cd lean
lake build
lake env lean GeneratedCertificateProofs.lean
~~~

The expanded continuous-observation-equivalence workflow performs the same steps on the *unmodified producer artifact*, runs the three negative Lean controls, and retains the checked manifest and evidence.

The next frontier is a theorem relating the Lean verifier's Boolean result to a universally quantified rational-network evaluation statement, followed by a formal rational-to-real continuity extension. This would remove another remaining distinction between a checked finite proof object and the mathematical observation it denotes.


## COE-008 — Refinement from executable certificate checks to rational network meaning

**Question:** When the independent Lean certificate checker accepts a proposed source network and activation-cell atlas, does its acceptance force the atlas to agree with actual network evaluation, rather than simply asserting self-consistent symbolic data?

The answer is formally established for each **open activation cell and every rational input inside that cell**, in the pinned Lean 4.24 environment.

### Two distinct interpretations

The existing checker (COEWireCheck.lean) constructs a symbolic affine law within each cell and computes its Boolean acceptance result. COE008Evaluation.lean adds a **separate numeric source evaluator**, with an ordinary list-dot-product at each neuron, layerwise ReLU evaluation, and no reference to the certificate's proposed cells.

The refinement proof connects these meanings in stages:

1. root_guard_implies_sign_stable: the **actual Boolean root-exclusion guard** entails a stable ReLU sign for any two rational points inside a proposed cell, including unbounded ends. The executable root computation and exact-zero test are not assumed correct as a separate axiom.
2. weightedAt: evaluating a propagated symbolic affine dot product at a point is equal to an independently defined numeric row dot product at that same point.
3. advanceSound: if one propagation step is accepted, it agrees with numeric evaluation of that layer at **every rational point in the cell**.
4. foldSound: the accepted sequence of propagation steps agrees with applying all original source layers numerically at the same input. This is proved by induction over an arbitrary list of layers, not simply by enumerating five known model fixtures.
5. verifiedCertificateSound: for an arbitrary certificate, accepted by COEWireCheck.verify, any member of its proposed activation cells, and any rational interior point x, **the certified affine output equals the direct network evaluation at x**. No additional trusted mathematical-soundness premise is passed to this theorem.

The checker also now explicitly requires that its selected rational probe lies strictly inside the proposed open interval. This is a fail-closed strengthening of the executable verifier, not a relaxation of the proof obligations.

### Formal theorem (mathematical meaning)

The main result is universally quantified: for any certificate C, cell c, and rational x,

- if the Lean verifier accepts C;
- c is an element of C's certified cell list; and
- x lies in the **open** interval of c,

then evaluating c's stated affine output at x produces exactly the same vector as directly evaluating C's source network numerically at x.

The proof is checked by Lean's kernel with no admitted proof holes. Its arithmetic reasoning uses the explicitly reported Lean foundational axioms propext, Classical.choice, and Quot.sound.

### Boundaries kept explicit

This proof is **not yet a theorem for every rational x on the entire number line**, because the checker represents intervals as **open** cells: the exact rational cutpoints between adjacent cells do not belong to either interior. Although the executable verifier checks agreement of neighboring affine outputs at those cutpoints, turning that observation into a full mechanized endpoint theorem still requires an explicit formal continuity argument for the direct ReLU network. A rational-to-real extension is likewise not yet formalized.

The certificate JSON-to-Lean translator is unverified Python. The Python/Go checkers independently validate canonical bytes, network identities, complete original certificates, and semantic hashes; the Lean theorem concerns the **typed data after translation**. This experiment does not provide authenticated producer authority, E-CPU Ground admission, GPU arithmetic proofs, or general network architecture support.

### Verification and next frontier

The pinned Lean workflow compiles COE008Soundness.lean and COE008Evaluation.lean, checks the new universal theorem's axiom audit, and preserves the COE-005/006 negative controls. The existing seven-job COE workflow independently checks the original Python-produced certificates and three malicious certificate mutations using Python, Go and Lean.

Next: formally prove that accepted adjacent piecewise-affine observations agree with direct evaluation **at rational cutpoints**, using the continuity of each affine and ReLU layer; then investigate the rational-to-real completion. Only after those steps can a fully quantified *all-real-input* Lean soundness claim be made.


## COE-009 — Complete rational-domain semantic correctness, including cutpoints

COE-008 connected the executable Lean certificate verifier to independent numeric network evaluation, but only at points **strictly inside** each open activation cell. A finite cutpoint can be an exact ReLU zero and does not belong to either adjacent open interval, even though both certified affine descriptions should evaluate correctly there.

COE-009 resolves the rational endpoint and total-coverage obligations with a kernel-checked proof under the pinned Lean 4.24 toolchain. It does **not** introduce an unproved continuity assumption.

### Endpoint correctness (COE009Endpoint.lean)

A point in a cell's **closure** may equal a finite left or right endpoint. The certificate's selected ReLU branch can have a different Boolean activation decision from the value exactly at that endpoint; at a ReLU zero, both branches still yield zero.

The theorem selectedAtClosed takes the *actual* rootExcluded Boolean guard from COEWireCheck, an interior probe, and any rational point in the corresponding closed interval. It proves that the probe-selected affine expression equals pointwise ReLU evaluation. Its key mathematical argument is that a strictly opposite-sign endpoint would force the affine preactivation root into the open interior, contradicting the verified exclusion. Equality at the zero root is handled explicitly. It covers positive, negative and zero slopes, bounded intervals, and one-sided unbounded cells.

### Entire network evaluation at endpoints (COE009Evaluation.lean)

The file retains the independent direct source interpreter COE008Evaluation.evalNetwork: list-dot-products, layerwise ReLU, no certificate cells. It extends the earlier proof by induction through every network layer:

- advanceClosedSound: one accepted symbolic layer agrees with direct rational layer evaluation throughout a **closed** activation cell.
- foldClosedSound: every accepted prefix and the complete network agree with independent direct evaluation throughout that same closed cell.
- verifiedCertificateClosedSound: if the Lean verifier accepts a certificate, then for every declared cell and every rational x in its *closed* interval, the claimed affine output equals the direct network's output at x.

These statements quantify over arbitrary typed certificates, layers and rational values, not only the five concrete fixtures.

### Complete coverage of the rational line (COE009Coverage.lean)

The executable checker now uses structurally recursive forms of its established endpoint and adjacency tests, lastUnbounded and joinedChain. This makes the verification evidence available for a terminating list induction. Acceptance still requires an unbounded first and last cell, nonempty/proper intervals, and exact equality of adjacent cutpoints and output values.

- verifiedCoverCoversRationals: for every rational coordinate x and every accepted certificate, there is at least one member of the declared activation-cell list whose **closed interval contains x**.
- verifiedCertificateAllRationals: combining that complete coverage with closed-cell network soundness proves that, at **every rational x**, at least one claimed certificate affine observation equals the independent numeric evaluation of the source network. This includes all finite rational breakpoints.

The theorem yields a **witness cell and its verified observation** for each rational input, without finite sampling or any fixed limit on network depth/number of cells in its statement.

### What the proof does not yet establish

- **All-real quantification is still open.** Rational coordinates are dense, and the represented affine/ReLU networks are mathematically continuous, but Lean has not yet formalized the rational-to-real extension of this verifier's semantics.
- The Python JSON-to-Lean literal translator is **not verified by Lean**. The source network SHA-256 pins, canonical JSON and semantic atlas remain separately verified by the Python and Go checkers, with distinct trust assumptions.
- The proof is about exact rational parameters and ideal rational pointwise evaluation, not actual floating-point/GPU execution, remote authentication, or E-CPU Ground admission.
- The printed foundational Lean axiom dependencies are propext, Classical.choice, and Quot.sound. The workflow rejects sorryAx and retains its negative controls.

### Reproduction and verification

~~~bash
cd experiments/continuous-observation-equivalence/lean
lake build
lake env lean COE009Endpoint.lean
lake env lean COE009Evaluation.lean
lake env lean COE009Coverage.lean
~~~

A separate GitHub Actions job still consumes unmodified COE-002 producer artifacts, independently checks the original certificates in Python and Go, reconstructs E-CPU candidate Ground identities under pinned policies, executes the five concrete Lean certificate proofs, and rejects adversarial certificate mutations.

The most significant next frontier is the **formal real-number semantic extension** from the established all-rational pointwise result: define the ideal real-input interpretation of exact rational affine and ReLU layers, establish their continuity, and show that agreement on the dense rational domain extends uniquely to every real coordinate. Only then can the Lean model establish the same complete continuous real-domain result claimed by the existing algorithm.
