# Independent Prepared-Result Verification

**Experiment:** SRH-006  
**Version:** 0.1  
**Status:** implementation and CI validation in progress

SRH-006 inserts an independent verifier process between durable preparation and E-CPU quorum completion. The Python recovery worker writes the proposed next PSC checkpoint and typed continuation receipt to disk, then invokes a separate Node.js process. That verifier uses the existing independent PRC/PSC receiver to reconstruct both the input and output checkpoints, decode every nested sparse realization, replay every typed program event, and verify that the output is the exact one-step continuation predicted by the input.

The verifier returns a deterministic validation receipt. Its digest is incorporated into the final continuation receipt submitted to the E-CPU claim store. Quorum completion therefore binds not only the proposed checkpoint and transition receipt, but also the independent verifier's exact finding.

## 1. Independent validation

The new `verify_prepared_result.mjs` process validates:

- the outer handoff-envelope digest and exact PSC input bytes;
- the portable claim bundle and claim self-identities, plus its current assigned Host, peer, implementation, and epoch fields;
- the prepared-record digest and exact assignment/input bindings;
- the prepared output checkpoint byte digest and continuation-receipt digest;
- the full PSC input checkpoint, including every nested PRC capsule and all historical state/revision events;
- the full PSC output checkpoint under the same independent checks;
- exact one-step continuity: input's independently predicted next state, tick, revision, and event digest must equal the output checkpoint's restored state, tick, revision, and chain head;
- the full continuation receipt fields, including state/time, program/model identity, assignment identity, and output checkpoint digest.

The verifier does not merely compare terminal states. It requires the output checkpoint's event-chain head to equal the independently reconstructed event digest for the specific next transition predicted from the input checkpoint.

The E-CPU worker still verifies the portable claim against the live recovery-lineage quorum before invoking the independent verifier. The Node process checks the portable ticket's embedded self-identities and assignment fields, but it does not independently recreate the live quorum or validate the authority members' proof. Those remain the E-CPU store's responsibility.

## 2. Commit ordering

The worker follows this order:

1. Validate the live claim, exact current assignment epoch, Host, peer, and implementation.
2. Replay the input PSC locally and construct the proposed output checkpoint plus base continuation receipt.
3. Fsync the prepared result record, including exact input/envelope/assignment bindings, output checkpoint bytes, and base receipt.
4. Invoke the independent Node verifier as a separate process.
5. Persist the independent-verification receipt into the prepared record and fsync the updated record and directory.
6. Add the independent-verification digest to the final continuation receipt.
7. Complete the E-CPU claim with the output checkpoint digest and final child-receipt digest.
8. Create/recover the successor claim, fsync the response outbox, and only then allow ReliableChannel to acknowledge the request.

A crash before the verifier runs leaves a prepared record with no independent-verification receipt. The replacement reruns the verifier. A crash after its receipt is persisted causes the replacement to repeat verification and require the exact same deterministic report. In either case, no quorum completion occurs before successful independent validation.

## 3. Negative control

A dedicated test creates a valid prepared record, alters the output checkpoint bytes, recomputes the wrapper's prepared-record digest and the altered byte digest, but leaves the typed continuation receipt unchanged. The independent Node process must still reject it because the checkpoint itself or its semantic relationship to the input no longer validates. The E-CPU claim is then checked to remain assigned with no result or child-receipt commitment.

This tests more than a stale outer hash: the tampering deliberately repairs the outer record digest, forcing the validator to inspect the actual checkpoint and transition.

## 4. Verification receipt

The independent result receipt binds the input/output checkpoint digests, input envelope digest, claim ID, assignment epoch, base continuation receipt digest, input and output event-chain heads, tick/state transition, revision, program/model identities, realization count, and total exhaustive finite-domain rows checked across both checkpoints.

The receipt digest is inserted into the final child receipt before E-CPU completion. That final digest is what the quorum claim commits. The prepared record also stores the full independent receipt under its own canonical digest, allowing a replacement to compare a later verifier run with the earlier one.

SHA-256 provides content identity and tamper detection, not authentication. The independent process runs on the same worker machine in this experiment; it is implementation/process diversity, not physical or administrative fault-domain separation.

## 5. Scope and next step

This experiment remains a deterministic pure transition over process-separated loopback TCP. It does not provide signed validator identities, a remote independent validator host, mutual-TLS worker transport, Byzantine validation quorum, or safety for external side effects. A future extension could put the validator on a separately admitted peer and have its signed receipt travel over the fabric, so result construction, independent validation, and authority publication become separate network roles.
