# USM-011 — Navigate a real failed invariant through E-CPU, VGI and IFS

**Intent:** use the research systems to resolve an actual development
obstacle, not an invented theorem or artificial scheduler fixture.

## Source failure

[Branching morphology Actions run 43629648833](https://github.com/Kier73/In-Formation-Space/actions/runs/43629648833)
ran on source SHA
`7e7f86d7074eb676e2e022cd620b4b1a814c5873`.
The Python **3.11.18** job
[132553219461](https://github.com/Kier73/In-Formation-Space/actions/runs/43629648833/job/132553219461)
failed at
`test_angular_support_cone.AngularSupportingConeTests.test_fake_path_counterexample_is_not_in_grammar_cone`
(line 94), asserting that a self-cross must equal exactly `0.0`.
The float expansion instead produced `8.881784197001252e-16`.
The Python 3.13 job passed. No failing loop depth was emitted, so we
do **not** claim that a particular n failed.

The original log details are retained in
`evidence/ifs_branching_morphology_ci_failure_20261114.json`, including
the exact test/source IDs, platform version, expected/observed values and
job URL. Its canonical digest and provenance are carried into the
experiment report. This is a **transcription of public CI evidence**,
not a signed GitHub or proof-kernel attestation.

## The actual mathematical issue

For heading multisets `a` and `b`, the cross product is computed as

```text
cross(a,b,theta)
  = sum_(ka,kb) a[ka] b[kb] sin((kb-ka)*theta)
  = sum_(d>0) [N(d;a,b)-N(-d;a,b)] sin(d*theta).
```

The second identity is algebraically exact. If `a=b`, the exchange
`(ka,kb)<->(kb,ka)` pairs every positive-frequency occurrence with its
negative-frequency partner, therefore the **integer** coefficient of
every sine term is exactly zero. The identity
`cross(a,a,theta)=0` does not depend on a floating-point tolerance.

The old code summed signed floating-point contributions directly.
Floating-point cancellation is not guaranteed to return a bit-exact
zero under every interpreter or summation order, even though the exact
mathematical identity holds.

The repaired `angular_support_cone.cross_sine_coefficients` first
counts signed heading differences in integer arithmetic and returns
only **nonzero** coefficients. The existing
`cross_from_histograms` then uses `math.fsum` to evaluate those
surviving terms. On self-cross there are none, so its result is
exactly `0.0` without evaluating `sin` at all. Nonzero
cross-products remain floating-point evaluations and are tested
against the original direct formula for asymmetric histograms.

This preserves stronger mathematical information than replacing
`assertEqual(...,0.0)` with an arbitrary near-zero tolerance.

## Three existing systems put to direct work

**VGI ProofGround** represents the real invariant as a root intention
with an elaborated AND decomposition into two unresolved proof
obligations:

1. integer equality of positive and negative frequency counts;
2. zero-term evaluation without spurious floating-point contributions.

The existing IFS `build_proof_attention_plan` navigates the two
candidate verification actions. A recorded failed CI assertion remains
an **observed claim**, not a `VerifiedKernelReceipt`. Zero
obligations are marked kernel-accepted.

**E-CPU NavigableComputationDAG** records the actual executable
research chain as content-addressed nodes: observing the failing job,
checking exact integer antisymmetry, checking numerical projection,
and constructing the proof-attention plan. All four completed
observation/action stages are committed with the original source
digest. The next ready operation is the **actual Python 3.11 and 3.13
CI regression**. That operation is not committed until the external
test runs. A separate external proof-kernel obligation remains
uncommitted without independently verified proof evidence.

The report retains a native E-CPU DAG snapshot that is reloaded through
`NavigableComputationDAG.from_snapshot`, ensuring that altering the
source, a result digest or dependency commit fails reconstruction.

## Reproduce

The branching-morphology repair is entirely Python standard library:

```bash
python -m unittest discover \
  -s experiments/branching-morphology \
  -p 'test_*.py' -v
```

For the three-system research navigation, use the **existing**
`.github/workflows/proof-attention.yml` environment, which pins
compatible E-CPU and VGI revisions. In that environment:

```bash
python -m unittest discover \
  -s bridges/proof-attention \
  -p 'test_real_ci_proofground.py' -v

python bridges/proof-attention/research_ci_proofground.py \
  --output usm011-real-ci-proof-navigation.json
```

The existing branching-morphology workflow tests Python 3.11 and 3.13.
The existing proof-attention workflow tests the VGI/IFS/E-CPU bridge
and retains its JSON evidence artifact.

The tests cover the original failure, signed-integer coefficient
symmetry, asymmetric numerical agreement, invalid histogram
multiplicities, DAG checkpoint tampering, altered source provenance,
forged proof claims and report rehashing.

## Scope and interpretation

The arithmetic repair is a concrete code change. The proof-attention
adapter is a real use of VGI/IFS/E-CPU to identify and preserve the
next verification action. **No Lean kernel was executed; no theorem
receipt is invented.** In particular, passing a bounded regression
suite is not sufficient by itself to establish a universal mathematical
theorem for all possible input states.

VGI's proof graph has three explicitly unverified obligations and
two candidate research actions; the E-CPU DAG's committed prefix is
**research process evidence**, not kernel acceptance.

Full hosted CI execution is required before declaring the repaired
branch verified. The original failure from November 14 is historical,
not a claim that the present main branch is presently failing.

## Following the evidence

The next improvement is to make this bridge accept other genuine
failure forms through registered, typed observation adapters:
independent Lean kernel trace errors, failed E-CPU recovery invariants,
and observed cross-host state equivalence discrepancies. Each
adapter should preserve source identity and return a VGI ProofGround
without granting kernel acceptance.

That makes the system useful for the researcher's actual question:
**what do we know, what requires attention, and which admissible
observation would change the answer?**
