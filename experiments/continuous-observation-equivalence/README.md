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

The executable checker now uses structurally recursive forms of its established endpoint and adjacency tests, lastUnbounded and joinedChain. This makes the verification evidence available for a terminating list induction. The additional Lean theorems joinedChainEquivalent and lastUnboundedEquivalent prove that these structural checks are **equivalent** to the original List.zip and List.reverse implementations for every list of cells; acceptance semantics have not been silently changed. Acceptance still requires an unbounded first and last cell, nonempty/proper intervals, and exact equality of adjacent cutpoints and output values.

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


## COE-010 — Unique continuous real meaning of certified rational neural observations

COE-009 kernel-checks the **entire rational input line**, including every activation breakpoint, for arbitrary accepted typed activation-cell certificates. COE-010 uses mathlib's real topology, the density of rational numbers in the real numbers, and an explicit real neural semantics to establish the next mathematical step.

**Main result:** For any typed certificate accepted by the actual Lean verifier, and for **every output component**, there exists a continuous real-valued function whose values at all embedded rational inputs match the mathematically verified certificate observations. Furthermore, **every** continuous real-valued function that has those same values at every rational input is identical to the constructed function **at every real input**. The real function is explicitly compiled from the certificate's actual rational neural-network layers; its existence is not postulated as an axiom.

### Two-layer formalization

The Mathlib-dependent COE010Real.lean module defines a small exact-rational expression language with variable, rational constant, sum, rational scaling, and ReLU constructors; it implements both an exact rational evaluator and a mathematically real-valued evaluator. It proves:

- evalReal_at_rat: real interpretation restricted to the embedded rationals agrees exactly with the cast of the rational interpretation.
- continuous_evalReal: every finite expression in the supported affine/ReLU language is continuous over the real line.
- equal_of_all_rational_agreement: two continuous real-valued functions that coincide on **all rationals** coincide on **all reals**, using the proven density of the rational embedding.
- unique_continuous_real_extension: a finite exact rational expression has one and only one continuous extension of its rational interpretation to the entire real line.

COE010Network.lean then provides the previously missing connection to the **actual** source network:

- compileLayer and compileNetwork: construct expressions from the real source Layer structures and their declared weight matrices, biases and ReLU flags.
- compileNetworkSound: the compiled expressions evaluate identically to COE008Evaluation.evalNetwork at *every rational input*, with no sampling or fixed network depth.
- componentContinuous and componentAtRat: every output component has continuous real semantics whose rational restriction is the independent numeric network evaluator.
- certifiedAtRat: selects an observation witness from COE009's previously proved complete rational-domain certificate theorem. At a shared rational cutpoint the choice of either valid cell cannot alter its value, because COE009 has already proved equality to the same source network.
- acceptedCertificateHasUniqueRealMeaning: combines the accepted certificate, COE009 rational soundness, explicit network compilation, continuity, and rational density to prove **existence and uniqueness of the continuous real meaning** of each component for any accepted certificate.

This proof is not merely a uniqueness theorem for two unrelated example functions. It quantitatively depends on the actual executable Lean certificate verifier and the original network's exact weights. The theorem is valid for arbitrary finite certificates supported by that verifier, not only the five example models.

### Reproducibility and trust

COE-010 intentionally uses a **separate Lake project** at real-lean so existing COE-005–009 Lean checks stay lightweight and Mathlib-free. The new project pins Lean 4.24.0 and Mathlib's exact Git commit f897ebcf72cd16f89ab4577d0c826cd14afaafc7. The CI job copies the original COE-005–009 Lean modules **without changing their source**, retains SHA-256 fingerprints of those originals, compiles them again in the Mathlib project, and kernel-checks the new theorems.

The axiom report explicitly lists propext, Classical.choice and Quot.sound. The workflow rejects any sorryAx or Lean.ofReduceBool in the positive theorem reports, and requires Lean to reject the false theorem claiming ReLU is the identity on a negative real input. The original certificate producer, Go and Python independent checkers, and E-CPU candidate Ground identity checks continue under the separate original CI workflow.

Reproduce with Git, Python only if generating certificates, and Lean 4.24.0:

~~~bash
cd experiments/continuous-observation-equivalence/real-lean
cp ../lean/COE*.lean .
lake update
lake exe cache get
lake build COE010Network
lake env lean COE010Real.lean
lake env lean COE010Network.lean
# This intentionally false claim MUST fail:
lake env lean COE010Invalid.lean
~~~

### Important distinction: meaning, not physical realization

This theorem establishes a **unique continuous ideal real-number interpretation** for every accepted typed certificate's rational outputs. It does **not** yet prove that a separately serialized **real-valued piecewise atlas parser** exactly implements the same function at an irrational coordinate. Such an atlas needs a real-interval membership theorem or a continuous-atlas realization proof. It also does **not** verify the Python JSON-to-Lean translator, authenticated source authority, E-CPU Ground admission, or floating-point GPU execution. A physical implementation would need separate error bounds and realization contracts.

A natural next investigation is to define a piecewise real affine observer directly from the accepted cells, prove its continuity across all exact breakpoints, and use COE-010's uniqueness theorem to identify that observer with the compiled source real network. That would connect the retained cell atlas itself—not only its unique continuous mathematical meaning—to every irrational coordinate.


## COE-011 — Direct all-real interpretation of actual certified activation cells

COE-010 established that a certificate accepted by the typed Lean verifier has a **unique continuous ideal real-valued network interpretation**, determined by agreement on all rational inputs. However, that theorem compiled the network's original rational weights, not the activation-cell atlas that the certificate actually retained.

COE-011 makes the missing bridge explicit: the **rational-affine expressions and rational interval endpoints in the certified cells themselves** are interpreted at arbitrary real inputs and proved to realize the same ideal source network.

### Local cell-to-network soundness (COE011Atlas.lean)

For every accepted typed certificate, every cell within it, every output component and every real coordinate in that cell's closed real interval, the certificate's claimed affine expression at that coordinate equals the compiled source real neural network.

The proof does not merely infer equality from global rational observations. It defines rational and real **clamps** into the cell's exact rational interval, proves their compatibility under rational-to-real casting, and proves that every clamped rational point lies in the original cell. COE-009 then forces the claimed affine expression to match direct numeric network evaluation at every clamped rational coordinate. Both *clamped real* expressions are continuous (the affine output, exact clamp and compiled neural function are all continuous). The COE-010 density theorem proves that these continuous functions agree at **all** real arguments. On the cell itself, clamping is the identity. This gives a direct, kernel-checkable theorem for the retained cell description at **all real inputs**, including irrational coordinates and rational boundary cutpoints.

### Global real coverage and deterministic piecewise interpretation (COE011Coverage.lean)

The exact Boolean verifier requires a finite ordered interval chain spanning negative to positive infinity, with exact shared rational endpoints between adjacent cells. A structural induction over that **actual accepted chain** proves that every real coordinate belongs to at least one cell's closed real interval; the proof does not enumerate or sample real numbers.

The firstRealCell selector is a mathematical ordered search over the actual retained cell list, choosing the **first** cell whose closed interval contains x. The piecewiseReal function evaluates that chosen cell's own affine output expression at x; it returns zero when no matching cell exists, with correctness guaranteed only when the original verifier accepts the certificate. This is an explicit atlas interpretation, not a restatement of the full-network evaluator.

The universal Lean theorems establish:

- verifiedRealCover: every real coordinate, rational or irrational, is covered by a declared closed cell of an accepted certificate.
- overlappingCellsAgree: any two accepted cells containing the same real coordinate have equal claimed output expressions at that coordinate, including at shared cutpoints.
- piecewiseReal_eq_network: the *actual first-matching-cell atlas interpreter* equals the independently compiled continuous real source network at **every** real coordinate and output component.
- continuous_piecewiseReal: the atlas interpreter is globally continuous, despite being specified by a conditional cell-selection procedure.
- piecewiseReal_at_rational: at every exact rational coordinate the real atlas agrees with COE-009's independently proved certificate observations.

These are theorems quantified over arbitrary certificates accepted by the typed Lean verifier, not only the fixed example models.

### Adversarial and constructive controls

The positive identitySplit certificate has the source map x ↦ x, one claimed affine cell from negative infinity through zero, and a second from zero through positive infinity. Lean kernel reduction checks the certificate is accepted; the real atlas theorem proves the resulting piecewise interpretation agrees with the ideal network at **all** real inputs and is continuous.

The negative gappedSplit certificate keeps the same correct identity source network and cell affine expressions, but makes the first cell end at zero and the second begin at one. Its claim of verifier acceptance must **fail under Lean's kernel reduction**; the negative CI gate checks for a proof-tactic rejection rather than accepting a syntax/import failure.

The existing seven-job COE Python/Go/Lean/E-CPU candidate-Ground regression and pinned Mathlib proof checks remain separate acceptance gates.

### Exact scope and remaining trust boundary

The real evaluator is **noncomputable** because exact ordering of arbitrary real numbers cannot generally be decided by a finite program. Its value is a mathematically well-defined ideal function, not an implemented floating-point predictor or network runtime. For each accepted **typed** certificate, the formalization now relates its retained cell atlas to the ideal source network for the entire real line. This does not prove an independently serialized JSON-to-Lean conversion correct, authenticate the source, certify E-CPU Ground admission or distributed execution, validate any GPU/CPU approximation, or extend beyond the supported finite scalar-input rational affine/ReLU family. The proofs rely only on the standard reported Lean foundational axioms; CI rejects admitted proof holes and native-decide axioms.

To reproduce the proof using the pinned Lean 4.24 / Mathlib revision:

~~~bash
cd experiments/continuous-observation-equivalence/real-lean
cp ../lean/COE*.lean .
lake update
lake exe cache get
lake build COE011Fixtures
lake env lean COE011Atlas.lean
lake env lean COE011Coverage.lean
lake env lean COE011Fixtures.lean
# A deliberately false complete-cover claim MUST fail:
lake env lean COE011Invalid.lean
~~~

A natural follow-up is to reduce the remaining serialization and realization trust boundary: validate the exact JSON rational-token parser against a formally verified decoding contract, and separately specify numerical approximation error bounds for implementations that observe or execute the proven ideal real-valued interpretation.


## COE-012 — Kernel-decoded original wire token bytes

COE-011 proved that an accepted typed activation-cell certificate's actual piecewise-affine atlas agrees with its ideal real neural-network evaluator at every real coordinate. But the initial COE-007 adapter turned source JSON rational strings into typed Lean Rat literals in ordinary Python. The mathematical result did not, by itself, prove that Python transported the correct numerical values.

COE-012 reduces that numerical translation trust by carrying the original certificate's **ASCII token bytes** as ordinary lists of natural-number byte codes into Lean. Within Lean, a separate, structurally recursive decoder decides whether the spellings are canonical, calculates the exact rational numbers, decodes the allowed endpoint sentinels and activation labels, constructs the original typed certificate, and invokes the unchanged independent certificate checker.

### Kernel-reducible decoder (lean/COE012Wire.lean)

The source-token wire language is deliberately small: a canonical ASCII integer (including zero and negative integers) or a reduced signed-numerator fraction with an ASCII decimal denominator greater than one. The decoder checks canonical digit sequences, rejects signed zero and leading zeros, rejects zero/unit/negative denominators, verifies coprime numerator and denominator and performs exact rational division **in Lean**. It accepts only -inf as the absent left bound, +inf as the absent right bound, and linear or relu for activation modes. There are no floating-point or Python Fraction values in the WireCert representation.

The token decoder works over lists of ASCII codes rather than opaque Lean string-library operations. This matters for formal evidence: Lean 4.24's string conversion and splitting operations used in an initial experimental parser did not reduce under the kernel-only decision tactic. Structurally recursive lists and arithmetic do, so a successful proof depends on actual kernel arithmetic, not native evaluation or trusted execution of a parser.

The acceptWire Boolean is true **only when** token decoding succeeds and the pre-existing COEWireCheck.verify accepts the resulting exact typed certificate. The lemma acceptWire_implies_verified recovers that typed mathematical certificate from wire admission.

### Replaying the five original certificates

The additional emit_lean_wire.py bridge is intentionally **data-only**. It reads exactly the canonical five original COE-002 source files under the independently checked source-network pin policy, transports their token strings as ASCII codes without interpreting their numeric values, and emits five kernel-checkable obligations in GeneratedWireProofs.lean.

For each of the five source artifacts, the obligations require that its Lean-decoded wire representation equals the original typed literal certificate that COE-007 previously replayed, that the newly decoded wire certificate passes the original mathematical verifier, and that the emitted manifest retains the original canonical source-file SHA-256.

The original independent Python and Go byte verifiers, complete activation-cell tests, malicious certificate mutations, and E-CPU candidate-Ground identity checks remain separate.

### Mathematical real meaning (real-lean/COE012RealLink.lean)

COE-012 also composes **actual Lean wire admission** with the all-real COE-011 atlas theorem. For any accepted wire-token object, output component and real coordinate, there exists the decoded certified object such that its own piecewise-real cell-atlas interpreter agrees with the independently compiled source neural network. The decoded atlas interpreter is globally continuous. No Python-computed rational literal or parser-soundness axiom is passed to these statements.

A nontrivial source example with exactly encoded -3/2 weight establishes positive admission and an all-real semantic bridge. Negative controls include unreduced fractions, leading zeros, signed zero, malformed syntax, reversed infinity sentinels, unsupported activation modes, and injection-like text. The false proposition claiming an unreduced fraction is admitted must be rejected by Lean.

### Distinctions and remaining work

This is **not yet a fully verified JSON parser**. The extraction of JSON objects/arrays/strings and the conversion of ASCII strings into lists of byte codes remain ordinary Python. The verifier-owned expected source-network manifest and independent byte-checking reports provide separate practical safeguards, but they are not proofs of the JSON envelope's faithful conversion. COE-012 reduces trust in numeric decoding, activation and boundary label interpretation; it does not eliminate the transport boundary.

The theorem concerns exact rational parameters and the ideal real interpretation of finite scalar affine/ReLU networks. It does not establish physical floating-point execution accuracy, source authentication, remote execution, or E-CPU Ground admission.

To reproduce with Python 3.11+ and pinned Lean 4.24.0:

~~~bash
cd experiments/continuous-observation-equivalence
python produce_certificates.py received-certificates
python -m unittest test_lean_wire -v
python emit_lean_certificates.py received-certificates lean/GeneratedCertificateProofs.lean
python emit_lean_wire.py received-certificates lean/GeneratedWireProofs.lean
cd lean
lake build
lake env lean -o .lake/build/lib/lean/GeneratedCertificateProofs.olean GeneratedCertificateProofs.lean
lake env lean GeneratedWireProofs.lean
# The deliberately false unreduced-token admission MUST fail:
lake env lean COE012WireInvalid.lean
cd ../real-lean
cp ../lean/COE*.lean .
lake update
lake exe cache get
lake build COE012RealLink
lake env lean COE012RealLink.lean
~~~

The next frontier is a self-contained Lean decoder for the canonical JSON envelope itself, or a proof-bearing external parser independently checkable against the original raw JSON bytes. Separately, physical implementations require numerical error bounds and execution-attestation contracts.


## COE-013 — Independent kernel parser of original canonical JSON bytes

The COE-012 proof starts with the original ASCII numeric/sentinel/activation tokens, but still relies on Python to identify the JSON keys, arrays, cell objects, and network layer hierarchy that carry those tokens. COE-013 moves the **entire permitted COE-002 canonical JSON envelope grammar** into a separate kernel-reducible Lean 4.24 parser.

### Complete byte-level structural interpretation

The module lean/COE013Json.lean accepts a list of original file byte codes. It does **not** consume a Python-created dictionary, a parsed model, or a reconstructed activation-cell list. Its bounded, structurally recursive parser recognizes precisely the canonical COE-002 schema layout:

- top-level atomic_cells, network, network_sha256, schema, semantic_atlas, semantic_sha256 fields in their canonical sorted order, with no duplicates or extra fields;
- the network's layers array and each layer's activation, bias and weights fields, with nested arrays for weight rows;
- each atomic or semantic cell's affines, left and right fields, with affine slope/offset pairs;
- unescaped ASCII quoted source tokens, exact punctuation and no formatting whitespace, correct exact schema string and a **single trailing LF** with no further bytes;
- exactly 64 lowercase hexadecimal symbols for each SHA-256 metadata field.

A successful parse produces the COE-012 WireCert containing the **original token bytes** extracted by Lean. The existing COE-012 decoder then validates and constructs exact rational parameters and endpoint/activation meanings, and the unchanged COEWireCheck verifier rechecks the actual cell partition and network computation. The function acceptBytes returns true only after all three checks pass. The theorem acceptBytes_implies_verified proves, without a parser-soundness axiom, that any accepted original byte stream yields an accepted typed certificate.

This parser deliberately accepts the **restricted canonical ASCII JSON subset** used by the COE-002 certificate producer; it is not a general JSON parser with Unicode escapes, whitespace, arbitrary object key orders, or unconstrained values. Rejecting other JSON encodings is intentional: they are not the producer's canonical bytes. The parser's supported nesting and list lengths are bounded.

### Exact replay of the five original produced byte streams

The separate emit_lean_json_bytes.py adapter reads the original raw bytes from each of the five pinned certificate files and writes only their natural-number byte codes as Lean literal data. Unlike the older bridges, it does **not call any JSON parser** or normalize strings/objects, interpret rationals, or selectively extract cell data. It records the original byte counts and SHA-256 digests as external receipts.

The generated Lean file then proves, for **each of the five actual source files**:

1. The entire raw JSON byte stream parses to a complete canonical COE-002 envelope.
2. The WireCert extracted **from the whole raw JSON** is structurally identical to the same certificate's independently extracted COE-012 wire-token object.
3. The exact parsed bytes produce a typed certificate accepted by the pre-existing Lean mathematical verifier.

Each statement is checked by Lean kernel reduction, not by trusting Python to assert that the original JSON was valid. The original seven-job Python, Go, Lean and E-CPU candidate-Ground regression remains independent.

The additional COE013Fixtures module checks a small complete canonical JSON document, then kernel-proves rejection of duplicate keys, extra or reordered fields, wrong schema, a malformed digest, formatting whitespace, incorrect final newline, escaped tokens, reversed infinity sentinel and unreduced rational values. An intentionally false theorem claiming duplicate-key acceptance must separately fail to compile.

### Link to the entire real line

real-lean/COE013RealLink.lean composes a successful original-byte-stream admission with the COE-011 all-real theorem. For every accepted byte stream, output component and ideal real coordinate, there exists the extracted typed certificate whose actual piecewise-affine atlas equals the independently compiled real-valued neural network. Its piecewise interpreter is globally continuous.

There is no sampled-input assumption and no trusted external numeric parser premise in those theorems.

### Precise remaining trust boundary

**Cryptographic hashes are not recomputed in Lean.** The Lean JSON parser checks the digest fields' lowercase 64-hex syntax, not their SHA-256 correctness, nor the equivalence of semantic_atlas to the computed cell atlas. Those still require independently run Python and Go checkers and the pinned trusted source manifest. An adversary can put a syntactically plausible but incorrect 64-digit digest in a byte stream that passes the mathematical network/cell checker; the separate independent provenance and fingerprint checks must reject it.

The external step of transporting original file bytes into a Lean list of natural-number literals is also not formally verified. File byte SHA-256 receipts and cross-checking against separately consumed Python and Go original artifacts provide independent experimental evidence, but not an end-to-end cryptographic theorem inside Lean.

The result remains a proof of **ideal exact rational scalar affine/ReLU computations interpreted over the entire real line**, not numerical GPU correctness, distributed host authentication, or E-CPU Ground admission.

To reproduce with Python 3.11 and Lean 4.24:

~~~bash
cd experiments/continuous-observation-equivalence
python produce_certificates.py received-certificates
python emit_lean_certificates.py received-certificates lean/GeneratedCertificateProofs.lean
python emit_lean_wire.py received-certificates lean/GeneratedWireProofs.lean
python emit_lean_json_bytes.py received-certificates lean/GeneratedJSONProofs.lean
python -m unittest test_lean_json_bytes -v
cd lean
lake build
lake env lean -o .lake/build/lib/lean/GeneratedCertificateProofs.olean GeneratedCertificateProofs.lean
lake env lean -o .lake/build/lib/lean/GeneratedWireProofs.olean GeneratedWireProofs.lean
lake env lean GeneratedJSONProofs.lean
# This deliberately false duplicate-key theorem MUST be rejected:
lake env lean COE013Invalid.lean
cd ../real-lean
cp ../lean/COE*.lean .
lake update
lake exe cache get
lake build COE013RealLink COE011Fixtures
lake env lean COE013RealLink.lean
~~~

Next investigations: independently reconstruct or verify SHA-256 under a formal specification, bind a signed exact source manifest to the original file bytes, and construct explicit numerical realization/error contracts for deployed hardware. These are different problems from the now kernel-checked canonical JSON syntax and mathematical semantics.


## COE-014 — Source-byte SHA-256 integrity and pinned network policy

COE-013 kernel-checks canonical original JSON bytes, exact typed certificate reconstruction, mathematical admission and ideal real-valued piecewise semantics. It previously syntax-checked SHA-256 fields but did not recalculate them. COE-014 introduces a separate, pure-Lean SHA-256 function and a receiver-owned source digest allowlist, reducing this remaining provenance gap.

### Pure-Lean SHA-256

The new lean/COE014SHA256.lean implements SHA-256 padding, big-endian message lengths, the 64 round constants, bitwise compression, multiblock message scheduling, binary digests and lowercase hexadecimal digests. The implementation uses ordinary Lean UInt32 modular arithmetic, not an external hashing library, native_decide or a trusted hash axiom.

The dedicated COE014Vectors.lean runner compares this implementation against five independently known SHA-256 results: empty input, short ASCII, ordinary text, a 256-octet binary multiblock input and 1000 repeated ASCII bytes. These are **runtime tests of pure Lean code**, not a general proof of equivalence to the FIPS specification or of SHA-256 collision resistance.

### Hashing the original network bytes

COE013Json.Envelope now retains the exact original network JSON object byte span as networkRaw during canonical JSON parsing. It is **not** a reconstructed encoding supplied by Python. COE014Provenance.acceptPinnedBytes checks all three requirements:

1. The original canonical JSON envelope and COE-012 rational tokens pass the unchanged Lean certificate verifier.
2. SHA-256(networkRaw), computed independently in Lean, equals the original JSON network_sha256 field.
3. The matching digest belongs to the verifier-owned, statically reviewed list of five network SHA-256 pins already used by independent Python/Go fixtures.

The kernel-checked pinned_bytes_witness theorem derives the actual digest equality, pinned membership and a mathematically admitted typed certificate from the Boolean gate. pinned_implies_accepted shows that the stronger gate never weakens the old mathematical admission checks.

### Five original sources and adversarial checks

The emitter emit_lean_hash_replay.py supplies positions for test mutations but does not calculate the hash for Lean. The original bytes are the same COE-013 byte literals already verified in the repository. The compiled pure-Lean runner recomputes every original producer model's nested-network digest and checks it against both the claimed field and the independent static receiver policy.

For **every one of five** sources it also mutates one network numeric value without updating the hash, and separately alters the SHA-256 field without changing the network. Both corrupted byte streams must still parse as valid JSON, and both must fail the SHA-256 consistency or pinned gate. The original seven-job Python, Go, Lean and E-CPU candidate-Ground regression continues independently.

### All-real formal interpretation

COE014RealLink.pinnedSourceAllReal connects stronger hash-pinned byte admission to the complete mathematical theorem from COE-011: each accepted cell atlas denotes the same ideal neural computation at **every real coordinate**, including irrational inputs and exact ReLU cutpoints. pinnedSourceContinuous proves the resulting piecewise interpreter remains globally continuous. No external numeric parsing or externally asserted hash equality is used as an axiom for these implications.

### Explicit trust boundary

**Integrity is not authenticity.** A receiver-owned list of hashes is a trusted policy, not a digital signature of the origin. A compromised allowlist, modified checker, or substituted supposedly trusted code remains a threat. COE-014 does not verify SHA-256 collision resistance, source signatures, key distribution, network-host identity or E-CPU Ground admission. It also does not formally recompute the different semantic_atlas fingerprint; independent Python and Go checkers retain those responsibilities.

The original external file-to-Lean-byte-literal transport is still not a formal theorem. The concrete five SHA-256 comparisons are executed and independently tested in the Lean runner; the universal theorem is a kernel-checked statement about what success of the strengthened Boolean admission means. GPU/CPU floating-point realization also remains separate.

### Reproduction

~~~bash
cd experiments/continuous-observation-equivalence
python produce_certificates.py received-certificates
python emit_lean_certificates.py received-certificates lean/GeneratedCertificateProofs.lean
python emit_lean_wire.py received-certificates lean/GeneratedWireProofs.lean
python emit_lean_json_bytes.py received-certificates lean/GeneratedJSONProofs.lean
python emit_lean_hash_replay.py received-certificates lean/GeneratedHashReplay.lean
cd lean
lake build
lake env lean --run COE014Vectors.lean
lake env lean -o .lake/build/lib/lean/GeneratedCertificateProofs.olean GeneratedCertificateProofs.lean
lake env lean -o .lake/build/lib/lean/GeneratedWireProofs.olean GeneratedWireProofs.lean
lake env lean -o .lake/build/lib/lean/GeneratedJSONProofs.olean GeneratedJSONProofs.lean
lake env lean --run GeneratedHashReplay.lean
cd ../real-lean
cp ../lean/COE*.lean .
lake update
lake exe cache get
lake build COE014RealLink COE011Fixtures
lake env lean COE014RealLink.lean
~~~

The next frontier is authentic source signatures or independent authority claims, verified key distribution, a formal refinement relation between the pure-Lean SHA algorithm and an external cryptographic specification, and separately numerical execution/error contracts.


## COE-015 — Ed25519 signed source manifests, key rotation and receiver-controlled authority

COE-014 kernel-checks the exact mathematical meaning of a canonical certificate and independently recomputes its original nested network SHA-256 against a receiver-owned allowlist. This establishes **integrity under an approved digest policy**, but it does not determine whether a purported origin actually authorized those digests.

COE-015 adds a separate **Go standard-library Ed25519 signature verification gate** for an explicitly identified source manifest. The cryptographic signature checker is a separate executable, **not a Lean proof of Ed25519**. The mathematical COE-014 SHA-256 and all-real atlas proof chain remains independent and unchanged.

### Signed object and scope of authorization

The signed body is a canonical JSON manifest containing a domain-separated schema, an authority identifier, a monotonically increasing manifest version, and the complete model-ID-to-network-SHA-256 mapping. Signatures cover a fixed protocol prefix followed by the complete canonical manifest bytes. The signed-envelope verifier rejects duplicate keys, unknown fields, altered signatures and noncanonical encodings.

Most importantly, the **public keys are not taken from the signed envelope**. The receiver supplies a distinct trust policy with an authority name, authorized Ed25519 public keys, their active/revoked status, per-key valid version ranges, the required signature threshold, a minimum permitted manifest version, and independently pinned expected network SHA-256 identities.

The verifier requires all authorized signatures to be valid, from distinct allowed signers, sorted by key ID, and to satisfy the configured quorum. Unknown, revoked, not-yet-active or expired signing keys cause rejection even when the cryptographic signature verifies. A previously signed lower-version manifest cannot pass a policy whose minimum version has advanced. Altering a policy requires independent receiver review and deployment; the manifest itself cannot rotate trust anchors.

The exact original certificate bytes are checked separately. The independent Go verifier recomputes each contained network SHA-256 from the canonical original network object, checks its claimed digest, and compares it with **both** the signed manifest and the receiver policy. File-set substitutions, modified model values and incorrect digest fields are rejected.

### CI demonstrates behavior, not real-world ownership

The new signed-manifest-producer job creates a sample two-signature Ed25519 manifest from the same original certificates sent to COE's existing mathematical and independent byte checkers. It uses **public deterministic testing seeds**. The associated demo-policy.json contains only the corresponding public keys, with one earlier key explicitly revoked and two current keys required at a 2-of-2 threshold for version 3.

The separate signed-manifest-verifier CI job receives this untrusted signed artifact, checks it using the policy independently checked out of the repository, then runs adversarial Go tests. These cover wrong and duplicate signers, forged or corrupted signatures, unauthorized key replacement, revoked keys, premature/expired keys, insufficient quorum, manifest tampering, policy substitutions, network-byte tampering, certificate-file substitutions, rollback and version rotation.

A deliberate safety control requires the CLI to **reject the public demonstration policy by default**. Test-only keys work only if the receiving operator passes the explicit demonstration opt-in flag. The CLI returns an independent receipt with the signers, authority label, policy mode, checked source network hashes and explicit Ground-not-admitted status. It never claims that the demonstration proves an external human or organization controls a source key.

No private production signing key is included in the repository. To use the verifier outside this demonstration, an operator must furnish independently managed private keys for signing and a receiver-owned, reviewed production trust policy containing the corresponding public keys. Trust-anchor distribution, account ownership, key custody, transparency logs and external identity authentication are out of scope here.

### Running COE-015

The demo producer and verifier use Go 1.23 standard-library dependencies only:

~~~bash
cd experiments/continuous-observation-equivalence
python produce_certificates.py certificate-artifacts

cd coe015_auth
go test -count=1 -v ./...
go run ./cmd/demo ../certificate-artifacts ../demo-manifest-artifacts

# This must FAIL: test keys are not production authority.
go run ./cmd/verify \
  -policy demo-policy.json \
  -signed ../demo-manifest-artifacts/signed-manifest.json \
  -certs ../certificate-artifacts

# Explicitly authorized test-only verification.
go run ./cmd/verify \
  -policy demo-policy.json \
  -signed ../demo-manifest-artifacts/signed-manifest.json \
  -certs ../certificate-artifacts \
  -allow-demo \
  -report demo-verifier-receipt.json
~~~

### Cryptographic and mathematical limits

This experiment verifies Ed25519 signatures using Go's maintained standard-library implementation. It does **not** formally refine Go's cryptography implementation in Lean or prove the computational hardness assumptions behind Ed25519. It does not independently attest a human's identity or grant computational Ground authority.

A valid signed digest proves that a holder of an **authorized private key** signed the versioned source manifest, provided the receiver's policy and signature implementation are trustworthy. Without an independently provisioned trust anchor, it cannot establish who that key holder is.

The COE-015 signer receipt is an additional provenance contract which can be required alongside the existing COE-014 kernel-checked byte-level SHA-256 and all-real mathematical result. Signing does not replace the mathematical checks, and the signed manifest does not authenticate the full semantic_atlas fingerprint or physical GPU/CPU execution.

The natural next frontier is a combined independently checkable admission receipt that binds the Go Ed25519 authorization result and Lean's source SHA-256/all-real proof to the **same exact received network bytes**, followed by a rigorous externally authenticated key-rotation workflow. The test-only key material must never be treated as an external signing authority.


## COE-016 — Exact-received-byte convergence of separate verifier evidence

COE-015 verifies receiver-authorized Ed25519 signatures and actual network bytes; COE-014 independently checks Lean SHA-256 pins and the exact all-real mathematical certificate. A successful status from each isolated checker is *not itself* a proof that all checkers were asked about the same file bytes. COE-016 introduces a fail-closed CI **evidence-convergence** stage to close that experimental gap without replacing any constituent verifier.

A new `same-source-evidence-convergence` job requires success from the same workflow's certificate producer, signed-manifest producer and verifier, independent Python verifier, independent Go verifier, and Lean kernel replay. It downloads their evidence artifacts through the current workflow run and, crucially, **reruns the separate Go Ed25519 verifier** on the exact received certificate directory using the local receiver-owned demonstration policy. It does not trust a producer-supplied signature receipt.

The standalone standard-library Python `coe016_binding.py` examines those reports *and rereads the original certificates itself*. For every required model, it requires:

- Identical SHA-256 of each complete original certificate file in the actual received bytes, Lean byte-literal transport receipt, independent Python report and independent Go report.
- Identical independently pinned nested-network SHA-256 in the COE-015 signed Go authority receipt, Python checker and Go checker.
- Identical exact-rational semantic-atlas SHA-256 in the Python and Go independently verified reports.
- Exactly one successful named COE-014 pinned-network/mutation-rejection status line per model in the successfully completed Lean kernel replay job; missing, duplicated, malformed or unknown lines fail closed.
- A complete, unchanged five-model file set, two distinct test signers satisfying the 2-of-2 quorum, and explicit non-admission flags.

The new artifact `coe016-test-only-cross-evidence-receipt` reports the agreed file, network and semantic digests, signer information, and scope. Adversarial unit tests mutate original files, individual evidence digests, semantic identities, source sets, Lean pass lines, and authority claims. All must be refused.

### Trust boundary

**This is an authenticated CI-run convergence observation, not a new Lean theorem or a cryptographically self-attesting independent proof bundle.** The evidence records and logs are not themselves signed; the joiner depends on the GitHub Actions runner/workflow provenance and on the separate verifier jobs executing honestly. A malicious or compromised CI environment could forge reports. The Lean transport manifest is emitted by Python before Lean runs; job dependency success and separate kernel output are necessary to interpret it as proof evidence. Files are joined by exact source bytes, not by trusting the manifest's status string alone.

Demonstration signing seeds are public. COE-016 deliberately permits **test-only** mode and reports both `origin_authenticated: false` and `ground_admitted: false`. It does not authorize remote Grounds, production signers, actual hardware numerical realization, or a real-world source identity. The next security step would be a separately checkable, signed cross-verifier receipt with authenticated verifier identities and a monotonic receiver-controlled trust-policy transition, followed by independent receiver reconstruction.

### Local reproduction of the convergence test

~~~bash
cd experiments/continuous-observation-equivalence
python -m unittest test_coe016_binding -v
# For the full positive-path join, reproduce COE-015 and the COE-002/003/014
# verifier outputs, supplying the original certificate directory and paths:
python coe016_binding.py --certs received-certificates \
  --authority joined-authority-receipt.json \
  --lean joined-lean-evidence/lean-json-replay-manifest.json \
  --python joined-python-evidence/independent-certificate-report.json \
  --go joined-go-evidence/go-independent-check-report.json \
  --lean-log joined-lean-evidence/sha256-pinned-network-replay.txt \
  --output coe016-bound-source-receipt.json
~~~


## COE-017 — Policy-scoped verifier signing keys, receiver replay state, and exact evidence bytes

COE-016 establishes that separate Python, Go, Lean and Ed25519 verification reports in one CI workflow agree on the same original certificate files. But the joined receipt was unsigned: a detached receiver of that JSON artifact alone could not attribute it to a verifier signing key or distinguish newly authorized evidence from stale replays.

COE-017 adds **a distinct verification-attestation protocol**, separate from COE-015's source-manifest signing keys. A new Go standard-library Ed25519 signer makes a canonical, domain-separated statement about the exact bytes of the COE-016 convergence receipt. That statement includes issuer, application context, monotonic sequence, whole-receipt SHA-256, a map of complete original certificate SHA-256 digests, nested source-network SHA-256 digests and the independently agreed semantic-atlas SHA-256 digests.

The separate CI `verifier-attestation-producer` job receives COE-016 evidence, regenerates the source file hashes, and produces a **PUBLIC TEST-ONLY 2-of-2 signature** using two explicitly nonsecret Ed25519 seeds. This is deliberately distinct from the source-owner keys used in COE-015. The `verifier-attestation-receiver` runs on another hosted runner, downloads those untrusted artifacts and independently supplies its own public-key trust policy, network digest allowlist, and **local replay state**.

The receiver's Go code checks canonical JSON; duplicate-key/unknown-field refusal; domain separation; actual Ed25519 signatures; distinct signers and public keys; key revocation, activation/expiry, rotation and quorum; exact COE-016 receipt SHA-256; original full certificate file hashes; actual nested network bytes and their receiver-owned network SHA-256 pins; semantic digest agreement with the signed statement; and a strictly increasing statement sequence above the receiver-owned policy floor. Only upon success does the CLI atomically replace the local receiver checkpoint. Replaying the same receipt against that checkpoint fails. Tests demonstrate a two-signer migration from the old pair to a new authorized signer, with refusal of retired and prematurely activated keys.

**Bounded security statement:** the receiver verifies control of authorized **demonstration signing keys** and checks received byte identities. It does not establish the real-world identity of any human, independent organization, physical host, or model owner. Any bearer can reproduce the public demonstration keys. This is not a Lean proof of Ed25519 or an independent derivation of the underlying mathematical result; the latter remains with the previous checkers, and the COE-016 record remains dependent on trusted CI execution. A signed verifier receipt cannot promote `ground_admitted` or `real_world_identity_authenticated` to true.

The receiver replay checkpoint is persisted **only to one local filesystem**. An isolated fresh receiver using the original seed checkpoint cannot know what another host already accepted. There is no distributed compare-and-swap, consensus, authenticated witness log or crash-consistent multi-writer journal here. An attacker who can rewrite both the receiver's independently provisioned policy and its state can bypass this experiment's replay controls. Future deployment requires external key custody, protected policy distribution, and an independently durable authority log. The new CI job never deploys a production private key.

### Reproduce

~~~bash
cd experiments/continuous-observation-equivalence
python produce_certificates.py received-certificates
# First generate a valid COE-016 convergence receipt from the separate
# verifier evidence as documented under COE-016. Then:
cd coe017_attest
go test -count=1 -v ./...
go run ./cmd/demo ../coe016-bound-source-receipt.json ../received-certificates ../demo-attestations
cp demo-state.json receiver-state.json

# Must reject public test keys by default:
go run ./cmd/verify -policy demo-policy.json \
  -signed ../demo-attestations/signed-verifier-receipt.json \
  -evidence ../coe016-bound-source-receipt.json \
  -certs ../received-certificates -state receiver-state.json \
  -report receiver-result.json

# Explicit public-key demonstration acceptance, then checkpoint advancement:
go run ./cmd/verify -policy demo-policy.json -allow-demo \
  -signed ../demo-attestations/signed-verifier-receipt.json \
  -evidence ../coe016-bound-source-receipt.json \
  -certs ../received-certificates -state receiver-state.json \
  -report receiver-result.json

# Running that last command again must fail with stale/replayed sequence.
~~~

The further frontier is independently held, non-demo verifier keys with authenticated authority transitions and replay state reconstructable across genuinely separate receivers, without trusting one local state file or a CI job's self-description.
