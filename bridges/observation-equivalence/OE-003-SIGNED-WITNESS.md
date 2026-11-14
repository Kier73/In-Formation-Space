# OE-003 — Signed witness realization claims

**Status:** synthetic, exact finite-model signature-conformance experiment. The files in this directory do not dispatch E-CPU operations, attest physical execution, grant Ground authority, or authenticate unsigned transport stages of an ObservationPath.

## Question

OE-001 and OE-002 find a shortest or least-additive-cost action sequence that distinguishes two states in a finite deterministic Ground model. A plan is not an observed result. Can a separately run receiver-verifier distinguish (1) the predicted mathematical trace, (2) a keyed receiver's signed claim about a trace, (3) separately signed authorization of that exact claim, and (4) a model mismatch, without silently promoting stages?

## Scope and protocol

The new witness_realization.py accepts only a complete finite model with unique **string** states/actions/tests and exact JSON-scalar outputs. It builds a planned-not-executed object containing a model snapshot and SHA-256 identity; a caller-specified request ID, independently pinned cost-policy digest, and starting states; a least-cost action word and terminal test with *predicted* values; and a digest of all plan claims. The verifier reconstructs the least-cost path from the complete finite table instead of trusting the submitted action word.

The verifier requires independently supplied model, cost-policy, request-ID, authority-policy, and Ed25519 public-key pins. The left and right receiver verification keys must differ. A distinct authority key is required. No private key is saved in the repository. The test harness creates ephemeral **TEST-ONLY** keys at runtime. The domain-separated signature covers canonical UTF-8 sorted JSON bytes of the claim. SHA-256 alone authenticates no signer.

A receiver signs the exact request/plan/lane, encounter ID, initial state, ordered per-action transition trace, final state, terminal test and terminal result. A separate authority key signs a decision naming the **receiver's signed-envelope digest**. Approving one receipt does not approve a substituted one.

Each lane carries a six-stage serialized ObservationPath-shaped record:

    planned → dispatched → admitted → returned → evidence_authorized → interpreted

The verifier ties the planned intent to the plan/attempt, returned payload to the signed receiver envelope, authorized decision to the signed authority envelope, and interpreted result to the signed receiver result. Rejected, missing, or reordered stages cannot be treated as observations. This is a narrow required-stage profile of [ObservationPath](../observation-path/README.md), not a live E-CPU coordinator.

A consistent, signed trace can disagree with the model: the verdict is then **signed-model-mismatch**, not success. The verifier does not mutate a model, Ground, or authority.

## Reproduction

From repository root, with Python 3.11+:

~~~sh
python -m pip install 'cryptography>=43,<47'
python -m unittest discover -s bridges/observation-equivalence -p 'test_*.py' -v
~~~

Ten new tests cover a synthetic positive receipt and wrong model/cost/request pins, altered signatures, unauthorized authority keys, transplanted approvals, wrong authority policy, missing stages, wrong interpreted values, missing actions, and a validly signed counterexample to the model.

The example models a two-action cheap/cheap witness. Its source values are deterministic fixtures, and its keys/authorization are ephemeral test-only claims. This is **not** observed E-CPU host performance.

## Evidence distinctions and limitations

- **Verified:** signatures under the provided keys, equality to independent identity pins, required lifecycle bindings, mathematical witness recomputation, and exact consistency or mismatch of the signed trace.
- **Not verified:** physical execution, actual transport, actual E-CPU authority, source host honesty, independent custody of test keys, provenance of the original cost profile, VGI Ground admission, or durable prevention of repeated acceptance of the same request ID.
- A pinned request ID rejects a different request; a production receiver still needs a durable anti-replay ledger.
- Empirical p95 cost is a descriptive planning assumption, not an end-to-end p95 guarantee.
- The canonical JSON scheme is Python-compatible and has **not** been independently cross-language validated. Future untrusted JSON-byte parsing must reject duplicate keys.

## Next experiment

Run the plan on two genuinely separate E-CPU receiver-hosts, with independently managed trusted keys and a third verifier, and replace synthetic authority claims with verified real receiver-side E-CPU decisions. Only after authenticating a live observation should it become candidate VGI Ground evidence; conflicting observations should produce revision proposals, not silent state changes.
