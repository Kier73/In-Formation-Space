# Remote Validator Peer for Prepared PSC Results

**Experiment:** SRH-007  
**Version:** 0.1  
**Status:** implementation and CI validation in progress

SRH-007 separates result construction, independent validation, and quorum publication into three roles:

1. **Recovery worker:** restores PSC and constructs one deterministic next checkpoint plus its continuation receipt.
2. **Remote validator:** independently validates the input and proposed output in a separate Python process using the Node PRC/PSC receiver. It has no E-CPU claim store or quorum-publication capability.
3. **E-CPU recovery authorities:** validate the live execution assignment and commit the output checkpoint digest plus the remote validator receipt digest under the current quorum epoch.

The worker does not complete the claim unless the remote validator has accepted the exact prepared record.

## 1. Authenticated endpoint identity

The worker connects to the validator over E-CPU's existing mutual-TLS transport and ReliableChannel protocol. Both sides authenticate certificates and check the expected DNS SAN identity. The worker also pins the validator certificate's DER SHA-256 digest after the handshake.

The service is configured with the expected worker:
- peer ID;
- DNS identity;
- logical Host ID;
- implementation fingerprint.

The validator checks the prepared assignment against that configured tuple after the TLS identity is established. The worker performs the reciprocal local checks before sending the request. This prevents a valid certificate for one worker identity from being used to validate a checkpoint assigned to a different peer, Host, or implementation.

The service's verifier implementation fingerprint is calculated from the exact bytes of verify_prepared_result.mjs and verify_capsule.mjs. The worker compares the returned fingerprint to the verifier implementation it has pinned locally.

## 2. Validation request and receipt

The ReliableChannel request binds:
- the exact input handoff envelope and its SHA-256;
- the exact input claim ID and assignment epoch;
- the canonical prepared-record digest;
- the expected validator and worker peer identities.

Before transmission, previously stored local validation receipts are projected to null and the prepared-record digest is recomputed. This makes the validation request content-addressed and byte-stable across worker restarts; a receipt cannot recursively change the request identity it attests.

The remote service runs the independent Node verifier against temporary copies of the envelope and prepared record. The verifier checks the checkpoint framing and digests, typed finite Boolean programs, every nested PRC realization, the complete historical event chain, and the exact one-step continuity from input to output. It validates the state/time transition, model/program identities, output event-chain head, and typed continuation receipt.

The validator responds with a digest-bound report containing the validation result, validator ID and DNS identity, worker peer/Host/implementation, verifier implementation fingerprint, and request identity. The worker additionally binds the authenticated validator certificate fingerprint, response digest, full validation report, and validation digest into a ifs.psc.remote-validator-receipt.v1 object.

The receipt digest is incorporated into the final continuation receipt submitted to E-CPU. The completed claim therefore commits a digest that includes the specific validator identity, its certificate pin, the exact worker identity tuple, the verifier implementation fingerprint, and the independently checked PSC transition.

## 3. Commit ordering

1. The worker resolves and verifies the live claim at the current E-CPU quorum high-water and exact assignment epoch.
2. It restores the input PSC and constructs the proposed output checkpoint plus base continuation receipt.
3. It fsyncs the prepared record, including exact input, assignment, output checkpoint, and base receipt bindings.
4. It rereads the persisted record and checks the output bytes and base receipt still match the in-memory result.
5. It sends the prepared artifact to the mTLS validator over ReliableChannel.
6. It verifies the validator response identity, response digest, certificate pin, worker identity tuple, verifier code fingerprint, and report digest.
7. It fsyncs both the independent verification report and remote validator receipt into the prepared record.
8. It adds the remote validator receipt digest to the final continuation receipt.
9. Only then does E-CPU complete the execution claim and publish the successor claim.
10. The response outbox is fsynced before the inbound worker request is consumed and acknowledged.

A validator rejection, unavailable endpoint, certificate-pin mismatch, DNS/SAN mismatch, worker tuple mismatch, verifier-code mismatch, report digest mismatch, or prepared-record tampering prevents E-CPU claim completion. The input claim remains assigned and no result or child-receipt digest is published.

## 4. Recovery behavior

The existing four hard-crash cuts remain:
- after the prepared checkpoint is fsynced but before remote validation;
- after quorum completion but before successor publication;
- after successor publication but before outbox persistence;
- after outbox persistence but before the inbound ReliableChannel ACK.

The replacement worker reconstructs or reuses the prepared checkpoint, repeats the same content-addressed remote validation request, requires the same independent report and remote receipt, then resumes the existing idempotent claim/successor/outbox recovery path. The remote validator service is a separate process; the test keeps it available while the worker and quorum authority child processes are restarted.

The test also includes:
- a positive mTLS request/response with an exact peer/Host/implementation tuple;
- tampered output checkpoint bytes with the outer prepared-record digest recomputed, which must be rejected remotely before quorum completion;
- an incorrect validator certificate pin, which must fail closed before the request is sent.

## 5. What is and is not established

This is an independently running validator process over mutually authenticated loopback TCP, with distinct CA-issued validator and worker certificates, SAN checks, an explicit validator certificate pin, and separate verifier execution. The validator has no claim-store or consensus interface.

The CI processes still share one machine and local storage fault domain; this is not physical-host, WAN, power-loss, or administrative-domain separation. The validator receipt is authenticated during the live TLS exchange and its digest is committed by E-CPU, but the receipt is not yet a standalone digital signature that an arbitrary later party can verify offline without the validator's pinned certificate/trust configuration. SHA-256 values provide content identity and tamper detection, not authentication on their own.

The worker/validator protocol remains restricted to deterministic pure continuations. This design does not make payments, device actions, external writes, or other non-idempotent side effects safe to replay. It also does not make the validator Byzantine-fault-tolerant; the validator is one independently admitted checking role, not a validation quorum.

A next extension can issue a separately signed validator attestation and have the E-CPU claim-completion path verify that signature against an independently configured validator key, rather than relying only on the worker's authenticated exchange and receipt-digest binding.
