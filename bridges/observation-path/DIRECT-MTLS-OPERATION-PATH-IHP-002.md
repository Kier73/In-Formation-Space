# Direct peer-authenticated operation path

**Experiment:** IHP-002  
**Status:** completed; direct hosted-runner probe and third-host negative-result attestation passed (run 4)  
**Format:** direct mTLS handoff, receiver receipt, and independent reconstruction v0.1

## Observed end-to-end result

**Successful verification run:** [IHP-002 run 4](https://github.com/Kier73/In-Formation-Space/actions/runs/43359031129)  
**Commit:** 9c0d8f63142a43bf14284131a25994e3d5462331  
**Workflow outcome:** all three jobs and the independent report attestation passed.

The successful verifier run is a successful negative-path experiment: the hosts could not establish direct TCP/mTLS, and the third host verified that result without creating a causal edge.

| Role | Worker ID | Cloud | Region | Result |
|---|---|---|---|---|
| Client host | 53e0310c-fa64-414a-ba13-91ddb9b2066a | Azure | westus3 | Published attested certificate; direct connection attempt timed out; attested unavailable record |
| Server host | 66a2a243-42ef-437c-bc3e-15f848b8b8bc | AWS | us-west-2 | Verified client certificate; published signed endpoint; accepted no inbound connection before timeout; attested unavailable record |
| Verifier host | 62becda1-8ffb-4e4f-b012-faa71aa5d882 | Azure | westus3 | Verified all four host certificate/record attestations, validated records and report, and attested the final report |

The client and server were not just separate VMs: they were scheduled on different cloud providers. The client reported:

MutualTLSTransportError: mutually authenticated TLS connection failed: timed out

The server reported:

MutualTLSTransportError: mutually authenticated TLS accept failed: timed out

The report records:
- Overall status: direct_transport_unavailable.
- Client and server record status: direct_tcp_unavailable.
- Causal reconstruction: not_established, with zero edges.
- Combined cross-host duration: null.
- Semantic operation relayed through the artifact store: false.

This distinguishes a network-reachability failure from a failure of certificate bootstrap, attestation, message signing, or report reconstruction. Both host certificates were attested, both host records were attested, and the third host successfully verified all four artifact attestations and signed the report. The direct TLS peer identity and ReliableChannel receipt could not be tested because no TCP session was established.

**Report artifact:** direct-mtls-operation-path-report in [run 4](https://github.com/Kier73/In-Formation-Space/actions/runs/43359031129).  
**Report-file SHA-256:** 7a8a06ecf179f3d0bbceed49ab89b99d4d0a2de7fa9c3789b1744acdc4714bb8  
**Canonical report digest:** 11e7f66443eaa485bc717f258ba79d22d220c4797f3eaa34bb83e13bdaf24023

The PR's focused CI passed the existing 13 operation-span tests, 13 DOP tests, 10 IHP-001 tests, 7 direct-mTLS tests, and all 10 direct/operation-path schemas. The wider In-Formation-Space integration had passed 95/95 steps before merge.

Two verifier issues were exposed and corrected during the experiment:
1. The client initially committed the digest of the endpoint payload core while the server committed the digest of the signed endpoint envelope. Both now commit the exact signed envelope digest, with a dedicated regression test.
2. The direct host-record schema initially depended on a remote operation-span schema URI. The span definition is now embedded, allowing the third verifier to validate records entirely offline.


## Question

Can the causal operation path from IHP-001 be established over an actual E-CPU SocketTransport connection between independent hosted VMs, with the receiver's identity authenticated by the sender and the sender's identity authenticated by the receiver?

IHP-001 moved records through GitHub Actions artifacts. IHP-002 uses artifacts only to bootstrap public certificates and a signed endpoint advertisement. The semantic operation payload, ReliableChannel ACK, and receiver receipt are intended to cross the direct TCP/TLS session.

## Topology and evidence flow

Three parallel/dependent GitHub-hosted VM jobs participate:

- client_host creates an ephemeral Ed25519 self-signed X.509 certificate, attests the public certificate, and publishes only the public certificate plus predicate. It never uploads the private key.
- server_host downloads and verifies that client certificate's GitHub attestation. It creates its own certificate, signs an endpoint advertisement containing its public IP/port, certificate fingerprint, DNS identity, run identity, and the expected client actor/certificate fingerprint. It attests its public certificate and publishes the public bootstrap bundle. It then listens for the direct TCP connection.
- client_host downloads and verifies the server public certificate and endpoint advertisement, connects using E-CPU connect_mutual_tls, checks the live TLS peer certificate fingerprint, sends a signed operation envelope through E-CPU ReliableChannel, waits for its ACK, then receives and verifies the server's signed receipt through a reverse ReliableChannel.
- server_host authenticates the TLS client certificate, checks the exact fingerprint against its attested bootstrap certificate and signed endpoint advertisement, and receives the envelope through E-CPU ReliableChannel.receive(commit=...). The commit callback validates the sender envelope and causal payload, merges the sender E-CPU CausalStamp, records the successor operation, constructs the DOP-001 causal witness, signs a receiver receipt, and durably writes the host record before the ReliableChannel emits its ACK. It then sends the receipt back over the same direct TLS session and waits for the receipt ACK.
- verifier_host downloads the public certificates, endpoint, and two attested host records. It independently verifies GitHub artifact attestations, record and predicate digests, endpoint signature, sender envelope signature, receiver receipt signature, both X.509 fingerprints, and the DOP-001 vector-clock handoff. It signs the report with its own workflow identity.

## What travels on which path

| Evidence or message | Transfer path | Contents |
|---|---|---|
| Client certificate bootstrap | GitHub Actions artifact | Public certificate and attestation predicate only |
| Server certificate and endpoint bootstrap | GitHub Actions artifact | Public certificate, signed endpoint advertisement, attestation predicate |
| Semantic operation handoff | Direct E-CPU SocketTransport over mTLS | Signed sender operation envelope |
| ReliableChannel ACK | Direct E-CPU SocketTransport over mTLS | Channel and received sequence |
| Receiver receipt | Direct E-CPU SocketTransport over mTLS | Ed25519-signed receipt binding exact envelope, sequence, TLS peer fingerprints, spans, temporal frames, and causal witness |
| Final host records | GitHub Actions artifact | Attested records for third-host independent reconstruction |
| Final reconstruction report | GitHub Actions artifact | Third-host report and Sigstore attestation |

The artifact store is not an alternate semantic-message relay. If the direct session cannot be established, the host records classify the outcome as direct_tcp_unavailable; the verifier emits a report with no established causal edge. It must not claim a direct edge merely because bootstrap artifacts were delivered.

## Protocol invariants

1. The client and server run as distinct workflow jobs on separate standard hosted VMs.
2. Each host generates its own private key locally. Only its public certificate is transferred.
3. The certificate subject/SAN identity is tied to the role and workflow run. The server's TLS listener requires a client certificate; the client verifies the server hostname.
4. After TLS negotiation, each side checks the actual peer certificate fingerprint against the attested bootstrap certificate. The server also checks that the live client certificate matches the client pinned in the signed endpoint advertisement.
5. The sender envelope is Ed25519-signed and binds the source host identity, certificate fingerprint, operation span, sender completion frame, DOP handoff payload, path, attempt, channel, and sequence.
6. The receiver merges the sender's E-CPU vector clock before measuring the successor operation. It validates the handoff using the existing DOP-001 endpoint and causal-frame rules.
7. The receiver receipt is Ed25519-signed and binds both certificate fingerprints, the signed-envelope digest, actual ReliableChannel sequence, source/successor span digests, both temporal frames, and the complete causal witness.
8. The receiver commit callback persists the signed receipt/record before ReliableChannel.receive() consumes the frame and emits ACK. The sender therefore cannot receive the protocol ACK before the receiver evidence has been durably written by the workflow process.
9. The third verifier reconstructs the edge from the host artifacts and public certificates, not from either participant's process memory or private keys.

## Clock and duration interpretation

No common physical clock is assumed. The source and receiver use their own E-CPU TemporalContext monotonic coordinates. Vector-clock merge establishes causal precedence. The report retains local durations separately and leaves combined_cross_host_elapsed_ns null.

## Network reachability is a measured outcome

Standard GitHub-hosted runners may not accept unsolicited inbound traffic. The workflow therefore attempts a real connection rather than presuming that a public egress IP is a reachable ingress address. In run 4, the cross-cloud client-to-server attempt timed out at both the client connection and server accept stages, despite successful public-certificate bootstrap and endpoint attestation. The verifier attested the resulting unavailable-path report.

The server binds to 0.0.0.0 on a fixed run-scoped test port and advertises the public IPv4 address observed from its own runner. The client retries the signed endpoint until its bounded connection deadline. The server accept step has a slightly longer deadline. If the TCP path is blocked, the workflow should still produce attested direct_tcp_unavailable records and a verifier report explicitly saying that causal reconstruction was not established over direct mTLS. A successful TLS socket and authenticated ReliableChannel receipt are required for direct_mtls_verified.

This negative result is useful: it separates transport capability from cryptographic and causal correctness, and provides evidence for whether a private-network overlay or another hosted-runner configuration is required.

## Trust assumptions and limits

- GitHub Actions runner isolation, OIDC/Sigstore attestation, and artifact storage remain part of the trust base.
- The X.509 certificates are self-signed per-run identity certificates. Their trust comes from exact certificate fingerprint pinning plus GitHub artifact attestation, not from a public CA.
- GitHub artifact attestations bind public certificate/record bytes to the protected workflow identity. They do not prove that the participant honestly performed its claimed operation.
- The Ed25519 receiver receipt proves possession of the pinned server private key and binds the receipt to the actual signed envelope and transport sequence. It is not a proof against a fully compromised participant process.
- Distinct runner worker IDs and regions can be recorded, but the jobs still share GitHub's control plane and cloud-provider trust.
- Operation spans measure synchronous callables, not CPU time.
- Combined cross-host elapsed time remains uncomputed without an explicitly attested clock calibration model.
- Run 4 did not establish a direct TLS session, so the signed sender envelope, ReliableChannel delivery/ACK, receiver-signed receipt, and cross-host causal edge remain implemented and locally tested, but not yet observed between independent hosted VMs.
- This is one client, one server, one operation, and one receipt. It does not yet test multi-hop routing, retries across session reconnection, process restart after receipt creation, key revocation, or multi-party quorum verification.

## Reproduction

Workflow: .github/workflows/direct-mtls-operation-path.yml

CLI: bridges/observation-path/direct_mtls_operation_path.py

- prepare-client: generate local client keys/certificate and the public certificate predicate.
- prepare-server: verify the client public certificate attestation, generate server identity, and sign the server endpoint advertisement.
- serve: accept mTLS, receive and commit the signed operation envelope, emit ReliableChannel ACK, send the signed receipt, and record the result.
- connect: verify server bootstrap, establish direct mTLS, send the signed envelope, wait for ACK, receive and verify the receipt, and record the result.
- write-record-predicate: bind a host record's exact bytes and host identity for GitHub artifact attestation.
- verify: verify all certificate and record attestations and reconstruct the direct causal edge on the third host.
- write-report-predicate: bind the report to the verifier job and exact report bytes.

Regression tests cover certificate identity, signature tampering, signed endpoint identity, a local real-TCP mTLS SocketTransport/ReliableChannel exchange, envelope validation, full receiver-receipt reconstruction, and certificate binding.
