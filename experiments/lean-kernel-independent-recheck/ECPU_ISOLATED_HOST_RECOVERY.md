# ECPU-VIRTUAL-HOST-RECOVERY-001

## Research question

Can a receiving E-CPU communication host maintain **its own identity, own authority to accept a proof, and own durable memory** while an originating host sends a fixed six-artifact VGI proof receipt over the actual mutually authenticated reliable transport, including a failed incomplete delivery and subsequent reconnection?

This experiment builds on [PROOF_TRANSFER_RECEIVER](PROOF_TRANSFER_RECEIVER.md) and [ECPU_PROOF_TRANSIT](ECPU_PROOF_TRANSIT.md). It preserves three distinct assertions:

- **Transport observation:** E-CPU `SocketTransport` + `ReliableChannel` over mTLS authenticated the origin's client certificate, delivered a bounded frame stream, and issued transport acknowledgements.
- **Issuer authority:** the receiving process independently validated *six* GitHub/Sigstore provenance attestations under its own trusted GitHub `main` workflow and exact source-commit policy, reconstructed the accepted Lean proof/term obligation, and verified the source Ed25519 signature.
- **Recipient admission:** a destination-provisioned `ReceiverIntent` and mounted durable SQLite database admitted a matching proof exactly once. A retry of a delivered proof remains a semantic replay even if E-CPU acknowledges the transport frames.

## Implemented host-isolation experiment

`ecpu_isolated_host_recovery.py` starts **two different Docker containers** on a user-defined TCP bridge network. Each has an independent PID namespace, network namespace and disjoint mounted files:

| Property | Origin host | Receiving host |
| --- | --- | --- |
| Network identity | `proof-origin` | `proof-recipient` |
| TLS private key | Sender's client identity only | Recipient's server identity only |
| Trusted CA | Admin-provisioned public CA certificate | Same CA public certificate |
| Proof evidence files | Six exact source subjects | Not mounted; obtained only via mTLS transport |
| Intended theorem/policy | None | Locally provisioned and pinned, not read from sender |
| SQLite proof replay ledger | No access | Persistent, writable destination-only bind mount |
| GitHub verifier/token | Neither mounted nor passed to container | Patched `gh` executable and `GH_TOKEN` explicitly provided |
| Root filesystem | Read-only image | Read-only image; only destination volume and temporary scratch are writable |

The private CA key remains in the administrator's ephemeral provisioning directory, never a container mount. The sender cannot read the destination policy, ledger, key or GitHub authentication environment variable through its own mounted filesystem.

The host image is built from a pinned E-CPU checkout at `3b57adcc2baaaa7e56e4bab943946f4e87e95c65`, pinned VGI at `ac13c1bbd92dfd09f17de51adef7adb2d2088bf6` and the current experiment code. `Dockerfile.proof-host` includes no secret, authorized artifact, receipt or writable replay state. On a real deployment the receiving host should separately install and approve this software rather than accepting a sender-supplied image.

## Failure/recovery sequence (CI)

1. A trusted **admin provisioner** creates test-only CA and separate leaf certificates with distinct `proof-origin` and `proof-recipient` DNS SAN identities. It creates the receiver-owned goal from the pinned Lean local source, and distributes *only* the matching credentials and intent to the appropriate container mounts.
2. Recipient container A listens on a Docker bridge address with mandatory certificate verification. A sender container authenticates and sends **exactly two ACKed frames**: the manifest and part of the first artifact. A test-only fault aborts the sender; CI hard-kills recipient A via Docker. **No VGI receipt or SQLite admission can exist** for that incomplete stream.
3. Recipient container B restarts on the same network alias and **same destination-owned persistent volume**. A new sender process authenticates and retransmits **the entire original proof package** on a fresh TLS session. The recipient stages the complete six subjects then independently validates live GitHub/Sigstore provenance and VGI obligation before committing its one SQLite admission.
4. Recipient container C restarts against the **same persistent SQLite volume**. Another authenticated sender retransmits the complete package. E-CPU reliably acknowledges the frames; the recipient verifies evidence but must explicitly raise `ReplayRejected`. Admission count must remain one.
5. CI attests a compact deterministic evidence report with the first verified VGI receipt reference, separate network-host setup, interrupted-before-admission observation and replay outcome; it does not upload the ephemeral CA private key or TLS private keys.

The test-only `--test-fault-after-frames` option intentionally stops a sender after a bounded, incomplete number of ACKed frames. It cannot be used to claim a successful proof transfer.

**Important limitation:** the experiment does *whole-package retransmission* on a **new reliable session**. It has not proved transparent recovery of E-CPU's in-flight per-frame channel snapshots, or durable application-level partial chunk state across host death. Receiver atomicity is supplied by the existing SQLite ledger after the complete independently verified package.

## Evidence layers, not a single status

No source artifact name, transfer manifest hash, successful TLS handshake, sender/receiver endpoint string, E-CPU ACK or host container status counts as a `VerifiedKernelReceipt`. These are observations about different parts of the system.

Only the receiving process can promote evidence into its own proof-admission ledger, after validating its **locally pinned** issuer workflow and run, exact VGI obligation, reconstructed proof type, actual Lean kernel result and six attested artifact bytes.

The proof target remains the fixed Lean 4.15.0 `KernelTrial.identity` experiment; distinct proof implementations, arbitrary theorem environments and global replay consensus are not established.

## Physical-host deployment path (not yet a CI claim)

The same `ecpu_proof_transit.py` CLI accepts a real remote `--host`/TCP `--port` endpoint. To run across two separately administered machines:

1. The receiving machine **independently** installs the pinned software and patched GitHub CLI; provisions a unique, persistent recipient SQLite storage path and a trusted policy derived from *its own* intended theorem, expected source SHA/run/attempt, receipt-denylist and local validity window. Do not provide these through the sender's proof-transfer channel.
2. A PKI administrator securely provisions a server certificate with DNS SAN `proof-recipient` to the receiver and a client certificate with SAN `proof-origin` to the origin, each with separate private keys, and provides only the CA public trust anchor to both. Rotate/revoke credentials according to the deployment's own CA lifecycle; do not reuse the CI test CA.
3. Provide the receiving process `GH_TOKEN` with minimum required repository-attestation read authority and network reachability to GitHub's verification services. Do **not** provide it to the origin.
4. On the **receiver**: invoke the script with mode `serve`, `--bind 0.0.0.0`, a constrained `--port`, its server `--cert`, `--key`, `--ca`, and the private `--intent`, `--ledger`, `--output`, `--transport-report` paths. Restrict inbound firewall rules to authorized origin networks.
5. On the **origin**: invoke mode `send` with `--host` pointing to the actual receiver IP/DNS, corresponding `--port`, its client TLS identity, CA, and exact paths for all six public issuer artifacts.
6. Verify the recipient decision and its persisted SQLite row independently. Restart a receiver after a deliberately interrupted incomplete transfer and then try the complete artifact again, followed by another complete retransmission. Keep originating process and receiving process logs separate.

This is an **operator runbook**, not evidence that such a physically separate deployment was completed by this PR. In particular, CI containers share one Docker daemon, one host kernel and one administrative provisioning machine; they cannot establish truly independent physical fault domains or cross-internet connectivity.

## Verification gates

PR CI: `ecpu_transport_contract_tests` runs the established 20 synthetic/mTLS tests plus provisioning, audience and incomplete-prefix adversarial tests. It never issues trusted proof admissions from PR artifacts.

Main-only CI: `ecpu_isolated_host_recovery` requires the same run's authenticated unified issuer and locally generated recipient intent, executes the actual isolated TCP/TLS Docker sequence with live recipient GitHub/Sigstore verification, and publishes a GitHub-attested recovery report only on success.

The next frontier is host-to-host testing on **two independently administered computers** (e.g., via separately provisioned Tailscale peers), with a destination-owned credential store, networking/CA failure injection, source restart, and explicit evidence that the two hosts never shared a filesystem or process manager.
