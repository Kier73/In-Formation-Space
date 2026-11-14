# CAG-003 — Signed semantic origin and receiver-local computation admission

**Status:** staged experimental integration. Do not infer full CAG-003 completion from this slice or a green source test.

This experiment composes CAG-002's real NATS JetStream and go-libp2p loopback protocols with cryptographically signed immutable operation commitments, an **actual E-CPU receiver-owned Virtual Layer Runtime and Hypervisor**, and VGI's finite reconstruction-certificate implementation.

The [CAG-003 frontier issue #197](https://github.com/Kier73/In-Formation-Space/issues/197) additionally requires truly independent network/provider domains. This experimental slice does **not** configure or exercise those external domains. It isolates the semantic-authenticity and receiver-admission proof obligations so they can be reused over independently hosted transports later.

## Experimental roles and evidence order

1. **Transport publisher on host A.** Run the exact existing CAG-002 real JetStream and go-libp2p interruption fixtures. Preserve the canonical input and both distinct captured arrival histories, with transport-specific lost ACKs and restart. Their expected reconstruction is 44. Generate one fresh Ed25519 key on the publisher host; sign a canonical, versioned statement binding the *complete input file hashes*, source Ground digest, packet-route bundle digests, operator contract, expected target and exact CAG-002 result digest. The ephemeral private key is never uploaded.
2. **Receiver trust bootstrap.** Publish an explicitly scoped public-key trust record separate from the signed statement. The record binds the key fingerprint, publisher label, trust epoch, exact source digest and allowed workload contract. In the main-branch hosted workflow, the producer **GitHub-attests** this trust record, the signed statement and the network report as distinct byte-exact subjects. Receiver host B checks those three attestations with an exact signer-workflow/main-ref policy before relying on the public key.
3. **Receiver-local semantics.** Receiver B rejects any signature mismatch, key replacement, altered input byte (including apparently harmless duplicate arrivals), inconsistent source target or forged packet. It constructs its **own** E-CPU SystemSeed and admits it locally through the existing Hypervisor/Virtual Layer APIs. It registers a trusted, deterministic pure handler in the receiver's own OperatorRegistry, not in the publisher payload, and submits an exact typed VirtualLayerWorkload under a restricted compute-capability PID.
4. **Admission, denial and replay.** First E-CPU execution must return ALLOW and one result of 44 linked to the signed source digest. Exact repetition of the event must replay its cached effect with **one handler invocation**. A different process lacking compute capability must return DENY and never execute the handler. The E-CPU kernel journal must independently verify.
5. **VGI projection.** Construct a separate complete eight-state Signal8 cyclic transition Ground and run the actual VGI GroundReconstructionVerifier over a finite declared action-sequence corpus bound to the signed source digest. The VGI certificate covers only that auxiliary finite projection. **It does not establish semantic equivalence of the full CAG integer dependency DAG or authorization of remote input observations.** Recorded status: finite_projection_reconstruction_only.
6. **Verifier host C.** A separate GitHub-hosted job checks the exact main-branch producer and receiver artifact attestations, independently verifies Ed25519 with the workflow-attested trust record, reconstructs both CAG-002 transport capture histories and their arithmetic result, checks the receiver receipt and rechecks the VGI finite certificate. The independent verifier does not directly witness execution inside the E-CPU Hypervisor; the signing source and receiver's reported authority result remain GitHub-attested claims.

## Security distinctions

| Claim | What is established on a green main run | What is still absent |
|---|---|---|
| Original source integrity | Ed25519 over exact semantic+transport byte commitments checked by receiver and verifier | Independently administered, long-lived publisher registry or certificate authority |
| Transport | Actual local JetStream TCP and encrypted libp2p streams with duplicate/restart fault injection | Separate providers, WAN reachability, actual circuit relay, correlated failure isolation |
| Execution | E-CPU receiver creates its own SystemSeed Ground, computes with its local pure OperatorRegistry and Hypervisor capability gate | Arbitrary remote code execution, distributed atomic external effects |
| Replay | Exact E-CPU event replay returns same effect without second handler call | Global exactly-once across multiple external effect domains |
| VGI | Real finite reconstruction certificate tied to source context | VGI Ground proof of full integer CAG semantics |
| Verification | Three different hosted workflow jobs; independent recomputation of exact input and certificate | Independent trust or physics behind common GitHub-controlled jobs |

The trust bootstrap is deliberately **not self-authenticating**: a public key supplied by the sender is only a hash until the receiving policy accepts a separate, trustworthy binding. In this pilot that binding is GitHub's exact-main-workflow attestation. A malicious publisher with access to the same workflow could produce an attested key; the current step therefore cannot claim independent publisher authorization. A future publisher should sign under a receiver-preconfigured or independently attested stable identity.

Transport ACK, sender signature, E-CPU admission, E-CPU effect receipt, and VGI reconstruction certificate are five different kinds of evidence. None silently substitutes for another.

## Pinned runtime dependencies

- E-CPU main pinned to 3b57adcc2baaaa7e56e4bab943946f4e87e95c65 (the hosted checkout is verified by its exact GitHub Actions ref).
- VGI main pinned to 093f11e458aff1c223d639ede413000619767ba6.
- CAG-002 actual protocol bridge and canonical CAG-001 packet validation are reused unchanged.
- Ed25519 uses Python cryptography, signature over canonical sorted UTF-8 JSON, with 32-byte raw public keys and 64-byte signatures.

## Reproduction

The source and security-negative tests require Python 3.11+ and cryptography. They use synthetic CAG-002 records and do *not* require a broker.

    python -m pip install "cryptography>=43,<47"
    python -m unittest discover -s experiments/convergent-ground-fabric/cag003 -p 'test_signed_ground.py' -v

The [CAG-003 Actions workflow](../../../.github/workflows/cag003-signed-admission.yml) starts the real JetStream broker and libp2p transport, captures actual delivery records, signs source commitments, then moves them to a distinct receiver job to exercise E-CPU and VGI. A third job independently reconstructs the receipt on main.

## Next experiment

CAG-003's external network prerequisite remains open: replace the one-runner loopback NATS server with a separately administered durable JetStream broker, replace the direct loopback libp2p stream with an external circuit-relay v2 or separately hosted peer, use a stable externally anchored publisher public key, and inject independent provider outages. Only then should this be called independently hosted dual-route federation.

No external credentials or secret storage have been configured by this build.
