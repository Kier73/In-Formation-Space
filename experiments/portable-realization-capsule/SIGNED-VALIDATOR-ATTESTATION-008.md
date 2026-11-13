# Signed Remote Validator Attestation

**Experiment:** SRH-008  
**Version:** 0.1  
**Status:** implementation and CI validation in progress

SRH-008 extends SRH-007 with a durable cryptographic identity for the independent validator. Mutual TLS remains responsible for live endpoint admission and channel confidentiality/integrity. A separate Ed25519 signing key now makes the validator's exact response independently verifiable after the TLS connection has closed.

The three roles remain separate:

1. **Recovery worker:** restores the source PSC, constructs a deterministic next checkpoint and base continuation receipt.
2. **Remote validator:** independently replays both PSC checkpoints and signs a response describing the exact verification result. It has no E-CPU claim-store or quorum-publication capability.
3. **E-CPU recovery authorities:** commit the output checkpoint digest and the digest of the signed validator receipt under the live execution claim's quorum epoch.

## 1. Two independent key identities

The validator has two distinct key pairs with different purposes.

**Transport identity:** the X.509 TLS certificate and private key authenticate the live service endpoint and its DNS SAN. The worker checks the CA path, expected DNS name, and a separately configured SHA-256 pin of the validator certificate's DER bytes.

**Attestation identity:** an Ed25519 private key signs validation responses. The corresponding public key is distributed separately to the worker as an operator-provisioned PEM file. The worker calculates its key ID as SHA-256 over the public key's DER SubjectPublicKeyInfo encoding. The public key is also carried in the signed response so an offline verifier has the material needed to check the mathematics of the signature, but that embedded key is not trusted merely because it is embedded.

The validator's Ed25519 private key is not sent to the worker and is not included in the prepared checkpoint, response, or durable receipt. The test fixture generates it in a temporary directory. A deployment must protect and provision it using its own secret-management mechanism.

## 2. What is signed

The validator constructs the exact canonical response core. It computes:

`response_sha256 = SHA256(canonical(response_core))`

and signs the 32-byte digest with Ed25519. The response carries:

- the canonical response body and its SHA-256 digest;
- attestation schema and algorithm identifier;
- Ed25519 public-key ID and PEM;
- the exact signed payload digest;
- the canonical Base64 Ed25519 signature.

The response body binds the request digest, validator peer ID and DNS identity, worker peer/Host/implementation tuple, verifier-code fingerprint, and complete independent validation report. Rejected responses are signed too; the worker validates the signature and then refuses any non-verified status.

The worker checks that:
- the response digest matches the canonical response body;
- the signing public key is Ed25519;
- its DER public-key fingerprint matches the configured public-key file;
- the attestation key ID and signed payload digest match;
- the Base64 signature is canonical and exactly 64 bytes;
- the signature verifies against the response digest;
- the response's worker and validator identities match the pinned configuration.

It then stores the entire signed response inside the remote validator receipt. The receipt digest covers the signed response and its complete validation report. That digest is inserted into the final stateful continuation receipt, which is what E-CPU commits in the completed child claim.

## 3. Independent offline verification

The Node receiver performs its own Ed25519 verification using Node's cryptographic implementation. It checks the signed response body, key ID, signature length and encoding, signature, worker assignment, validator identity, verifier implementation, and exact transition report. It does not trust the Python worker's signature-validation result.

The offline CLI accepts an optional externally pinned key identifier:

`node verify_prepared_result.mjs --envelope envelope.json --prepared prepared.json --trusted-validator-key-id <sha256-spki>`

When this argument is supplied, the Node receiver also requires the attestation key ID to match the supplied trust anchor. Without it, the tool proves that the response is signed by the public key embedded in the artifact, but cannot decide whether that key belongs to an authorized validator. A self-contained signature is not a self-establishing trust policy.

The test verifies a completed prepared record offline, with the key ID supplied separately. It then flips one bit of the signature and deliberately recomputes both the outer remote-receipt digest and the prepared-record digest. The Python worker-side stored-receipt verifier and independent Node receiver must still reject the forged receipt.

## 4. Restart and commit ordering

A replacement worker verifies any stored remote-validator receipt against its configured Ed25519 public-key pin immediately after reading a prepared record. This check also runs when the E-CPU claim has already been completed and recovery would otherwise skip the original validation callback. A restart cannot reuse an altered or untrusted attestation simply because its wrapper hashes are internally consistent.

The critical order is:

1. fsync the exact prepared checkpoint and base continuation receipt;
2. send the stable content-addressed request over mutual TLS and ReliableChannel;
3. verify the returned TLS peer pin, worker tuple, signed response digest, Ed25519 key pin, and signature;
4. fsync the independent validation report and signed remote-validator receipt;
5. add the remote receipt digest to the final continuation receipt;
6. only then complete the E-CPU claim and publish the successor;
7. fsync the response outbox before acknowledging the incoming request.

If the remote peer is unavailable, the certificate or signing key does not match, the signature is invalid, or the report differs, the worker fails closed before claim completion. The source claim remains assigned with no result or child-receipt digest.

## 5. Trust enrollment, rotation, and revocation

The public key fingerprint must be provisioned through an authenticated operator/deployment channel independently of the prepared artifact. The validator's TLS certificate pin and Ed25519 public-key pin are separate configuration entries. A change in one does not silently authorize a change in the other.

Key rotation is a trust-policy operation: provision the new public key and key ID to every worker and offline verifier that should trust it, then switch the validator's signing key. The current experiment does not implement overlapping key generations, a signed key-transition statement, revocation distribution, expiry timestamps, or a validator key registry. A worker with an old pin correctly rejects a new signing key until its trust configuration is intentionally updated.

The signing key ID is a public-key fingerprint, not a person/organization identity by itself. Authorization of that key as a particular validator still comes from the deployment's external trust configuration and the binding of that configuration to the validator's peer/DNS identity.

## 6. Scope and evidence boundary

CI runs the verifier and worker as separate processes over mutually authenticated loopback TCP. The validator's Ed25519 key is separately generated from the TLS certificate and the worker is configured with a public-key file. Offline Node verification is a second-language/second-process check.

This remains one CI machine and one local administrative/storage fault domain, not physical-host or WAN separation. The validator is one checking role, not a Byzantine validation quorum. Ed25519 provides authenticity of the signed response relative to the trusted public key; it does not make a malicious trusted validator correct. SHA-256 provides content identity and integrity binding. Deterministic replay is still restricted to pure continuations; external side effects are not made safe to repeat.

The prepared-record schema advances to v4 to mark the signed-receipt format. Older v3 records do not carry this attestation and are not silently accepted as v4.
