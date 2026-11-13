# Proof-runner completion receipts

**Status:** executable signed-receipt reference experiment.  
**Question:** after the route authority grants a stable proof-runner execution ticket, how can a receiving host verify that a particular runner key signed completion of the exact request and exact result envelope?

## Connection to the existing bridge

The proof-action route ledger already appends an `execution_authorized` event before an external runner callback. The event binds the route epoch, attempt ID, request digest, deterministic execution ID, and runner ID. The portable proof-action protocol already gives the returned result a digest over its attempt ID, request digest, Encounter return evidence, and normalized VGI proof trace.

This experiment connects those existing records without changing them:

1. Validate the exact `execution_authorized` event and its self-digest.
2. Recompute and validate the portable request digest.
3. Validate the result envelope and its request correlation.
4. Create an Ed25519 receipt signed by the runner key, binding the authorization-event digest, route epoch, execution ID, attempt ID, request digest, runner identity, result digest, Encounter-evidence digest, and proof-trace digest.
5. Verify the receipt with an externally trusted runner public key and the exact event, request, and result supplied by the host.

The execution ID formula is reproduced from `bridges/proof-attention/proof_action_route_epoch.py`; the result envelope format is read from `bridges/proof-attention/proof_action_protocol.py`.

## Creating and verifying a receipt

The runner should create the receipt only after it has durably committed the result for the execution ticket. If it crashes after the result commit but before receipt publication, it can reload the exact result and deterministically recreate the receipt with the same key.

```python
from completion_receipts import (
    create_completion_receipt,
    verify_completion_receipt,
)

# These are the exact route-ledger event, request, and result documents.
receipt = create_completion_receipt(
    execution_authorization_event,
    proof_action_request,
    proof_action_result,
    private_key=runner_private_key,
)

verified = verify_completion_receipt(
    receipt,
    execution_authorization_event,
    proof_action_request,
    proof_action_result,
    trusted_runner_id="lean-worker-pool-a",
    trusted_public_key=trusted_runner_public_key,
)
```

The receipt is a detached signature over canonical JSON. Its key ID is the SHA-256 fingerprint of the raw Ed25519 public key. A verifier must obtain the public key from a trust configuration that pins the intended key to the expected runner identity; accepting a public key supplied only by the receipt would not authenticate the runner.

The JSON Schema is `completion-receipt.schema.json`. The implementation is `completion_receipts.py`, with focused adversarial tests in `test_completion_receipts.py`.

## What verification establishes

A successful verification establishes that:

- the supplied authorization event is a self-consistent `execution_authorized` record, and its ticket formula matches the request;
- the request and result envelopes are internally digest-valid and refer to the same attempt and request digest;
- the exact route-authority event digest and result digest are covered by a valid Ed25519 signature;
- the signature verifies under the externally pinned public key for the runner identity.

It allows a host to distinguish “the worker says it finished this exact request/result” from “a result-shaped message arrived.” It is a verifiable runner claim, not an independent observation of the computation.

## Deliberate trust boundaries

- The caller must validate the *complete* route-ledger chain, its compare-and-swap authority, and authority identity. This module checks the authorization event's self-digest and internal ticket binding; one valid event by itself does not prove its place in a trusted ledger.
- The caller must pin the runner public key to the expected runner identity. Key possession is not remote-host identity unless that mapping is trusted.
- The runner could sign a fabricated result. A signature does not prove that Lean ran, that a tactic executed honestly, or that the runner is uncompromised.
- The receipt binds the existing result envelope. It does not authenticate the Encounter source independently, fetch raw result bytes, or validate the normalized proof trace.
- Kernel acceptance remains a separate VGI `VerifiedKernelReceipt` and trusted checker boundary. `completion_status=result_produced` does not mean tactic success or theorem acceptance.
- The Ed25519 receipt is deterministic for fixed inputs and a fixed key, so a crash after durable result commit but before receipt persistence can be recovered by recreating it. Key rotation or changing result material creates a different receipt and must be handled as a distinct trust-policy event.
- This is a protocol reference, not a live proof-worker deployment or a multi-host receipt database.

## Reproduction

```bash
python -m pip install "cryptography>=42,<47" "jsonschema>=4,<5"
python -m unittest discover -s . -p 'test_*.py' -v
```

The tests exercise valid signing and verification, ticket derivation, wrong runner identities and keys, authority-event substitution/tampering, request/result correlation, changed result content, signature tampering, and schema validity.
