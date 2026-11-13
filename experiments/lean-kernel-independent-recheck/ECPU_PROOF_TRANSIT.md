# ECPU-PROOF-TRANSIT-001 — proof artifact movement over actual E-CPU channels

## Goal

The earlier `PROOF-TRANSFER-001` receiver verified six incoming artifacts via GitHub/Sigstore and committed a one-time VGI admission in a durable local SQLite ledger, but the artifacts reached the recipient via GitHub Actions artifact delivery.

This experiment substitutes **real E-CPU transport primitives** for the communication leg:

- The sender and receiver use the pinned E-CPU implementation at commit `3b57adcc2baaaa7e56e4bab943946f4e87e95c65`.
- `mailcpu.mtls_transport.connect_mutual_tls` / `accept_mutual_tls` establish a mutually authenticated stream with CA chain validation, TLS 1.2+ and expected peer DNS subject alternative names.
- `mailcpu.socket_transport.SocketTransport` carries framed E-CPU `Message` objects on the socket.
- `mailcpu.reliability.ReliableChannel` delivers sequenced, acknowledged frames using the established reliable FIFO semantics. A transport ACK means a frame was delivered, **not** that a proof was accepted.

The six artifacts transmitted are exactly the original proof runner, signed source-checker observation, signed statement, attested Ed25519 public key, serialized-kernel report, and final unified VGI receipt from the same trusted issuer workflow. No source/proof claim can be promoted by the E-CPU carrier alone.

## Wire protocol and receiving validation

`ecpu_proof_transit.py` creates a manifest with fixed version/channel, exactly six typed subject labels, byte lengths and SHA-256 hashes, an aggregate byte bound and ordered chunk counts. A bounded sequence of chunk frames follows; finally an exact manifest digest terminates the stream.

The receiving `ProofStreamDecoder` rejects missing or extra subjects, path traversal (file names are never taken from incoming wire bytes), oversized subjects or frames, shuffled and duplicate chunk indices, malformed/case-changed hex, unknown fields, changed byte lengths, truncated transfers, mismatched digest, and invalid finish transcript. It stages only the complete exact bytes into a private temporary directory. The manifest and transport identity are delivery evidence, **not a root of proof trust**.

The receiving process then invokes the unchanged `proof_receipt_receiver.receive()` policy with its **own local intent** and SQLite ledger. It independently authenticates the complete six-artifact GitHub/Sigstore chain using a patched `gh` verifier and pinned issuer workflow, reconstructs the original proof-term/source-checker result, validates the exact VGI obligation, and atomically admits it only once.

The mTLS peer certificate identity is validated by E-CPU before any byte reaches the proof receiver; the recipient independently verifies that the proof issuer workflow is allowed by its trusted policy. These are deliberately separate identities.

## Live exercise

The modified `lean-unified-kernel-receipt.yml` adds:

1. `ecpu_transport_contract_tests`: PR-safe synthetic wire/protocol/real localhost mutual-TLS tests; **does not** claim GitHub-attested proof acceptance.
2. `ecpu_mtls_proof_transfer`: main-only hosted run after the issuer's unified VGI admission and the protocol tests. The job downloads the six issuer artifacts into the sender, independently generates recipient intent from its pinned local Lean checkout, then starts **two separate Python processes** connected over real loopback TCP, mTLS, SocketTransport and ReliableChannel.

The first transfer is accepted only after live GitHub/Sigstore checks. The same six artifacts are sent again over another mTLS session by fresh processes against the unchanged SQLite ledger. The second transfer must receive an explicit **replay rejection** at the proof-admission layer. ReliableChannel acknowledgements for the second delivery do not imply proof re-admission.

The workflow attests and retains the transport observation, recipient decision, persistent SQLite ledger, and final demonstration report. Ephemeral test-only CA/private keys are **not** retained.

## Security boundaries

The test uses two processes **on the same GitHub-hosted runner over loopback TCP**. This establishes real E-CPU mTLS and reliable framing and separate processes, **not** two physically separated hosts or external internet transport.

Certificate issuance uses an ephemeral local test CA trusted by both participants for this one CI run; production PKI, key rotation, remote-host provisioning, or separate authority governance are **not** demonstrated. The E-CPU checkout is pinned to an inspected commit to keep transport behavior reproducible, not cryptographically installed as a permanent external dependency.

The receiver independently validates the mathematical/provenance claim and the local durable replay ledger; it does not assume a successful TLS handshake, packet digest or transport ACK means mathematical validity. Replay prevention remains scoped to its own persisted SQLite database. An independent host would need a separately provisioned trusted intent, certificate authority and persistent database.

The serialized proof kernel check remains tied to the fixed Lean 4.15.0 theorem and environment; this does not establish checker implementation diversity.

## Next questions

A future physically separate host deployment should pre-provision a destination-owned trust store, TLS client/server identities and durable ledger rather than distributing ephemeral test-only CA material with the sender; it should independently prove host separation and reconnect/recovery behavior. Multi-hop computational forwarding should bind a transfer's intended destination and message lineage while leaving proof verification exclusively at the final recipient.

This is a **bounded implemented communication experiment**, not a claim that the entire E-CPU computational fabric now transports arbitrary authenticated theorem certificates.
