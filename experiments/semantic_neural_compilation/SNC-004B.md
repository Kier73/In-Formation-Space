# SNC-004B — Live E-CPU verified capsule over a dedicated Tailscale mTLS route

**Status:** implemented and awaiting verification. Live cross-host result is *not established* until the manual overlay workflow completes and its third-host audit passes.

## Question

Can a separate E-CPU recipient accept a neural realization from another host over a real authenticated Tailscale route while preserving a receiver-owned mathematical source policy, independent COE-002 full-real-line verification, and durable exact observation?

SNC-004A used GitHub Actions artifacts to transfer an untrusted capsule between isolated jobs. SNC-004B reserves artifact transfer for **public identity bootstrap and subsequent evidence auditing**. The sender transfers the capsule itself only through E-CPU SocketTransport, ReliableChannel and mutual TLS.

## Protocol

1. Sender and receiver independently create short-lived TLS identities. Their *private* keys remain in local job storage, not GitHub artifacts. Public certificates and a declared Tailscale IPv4 endpoint are exchanged within the same workflow run through GitHub Actions artifacts.
2. A dedicated receiver listener binds only to its own Tailscale 100.64.0.0/10 address on TCP **41768**. The sender refuses wildcard, public, loopback, arbitrary DNS or non-Tailscale endpoints when overlay mode is requested. The receiver public endpoint binds the same workflow run, attempt, port and certificate digest.
3. TLS verifies the server's DNS name, the client's expected DNS SAN, and each negotiated peer certificate fingerprint against the exchanged bootstrap.
4. The sender transmits a finite untrusted SNC-004A capsule as ordered 8,192-byte fragments, preceded by the exact document SHA-256, length, nonce, request ID and model name, then followed by a terminal manifest SHA-256. E-CPU reliable-channel ACKs observe delivery only.
5. Inside the final ReliableChannel commit callback, the receiver independently checks its own pinned semantic source policy; replays COE-002 all-real certificate verification; restores the exact rational ReLU realization; commits an exact input/output observation and durable receipt **before the final delivery ACK**.
6. A separate reverse ReliableChannel conveys an application verdict tied to the original nonce, document SHA and request ID. A negative semantic decision is distinct from successful transport. The receiver may never use a sender-defined policy to admit a model.
7. A third runner checks client/server peer certificate identity, nonce, exact document digest and frame counts, their matching receiver application result and durable receipt, and independently recomputes both full-domain mathematical equivalence and the specific rational output.

## Verification evidence tiers

- The automatic PR workflow, .github/workflows/snc004b-transport-contract.yml, checks bounded frames and source-rebinding rejection on Python 3.11 and 3.13. It also runs a real loopback mTLS session between distinct Python processes and explicitly requires a denied-policy session.
- The manual workflow, .github/workflows/snc004b-tailscale-live.yml, provides independent GitHub-hosted **client**, **server**, and **auditor** jobs. It requires a dedicated Tailscale workload identity. No actual remote-host success is claimed until those jobs complete and the auditor reports a reconstructed live operation.
- The live workflow deliberately fails if dedicated federation credentials are missing; **no public TCP or GitHub artifact payload fallback** is permitted. The third auditor never joins the tailnet.

## Dedicated workload federation prerequisites

For a manual dispatch on the main branch, configure repository secrets:

- SNC004B_TS_OAUTH_CLIENT_ID
- SNC004B_TS_AUDIENCE

Configure a separately allowlisted ephemeral Tailscale OAuth workload federation identity, restricted to repository Kier73/In-Formation-Space, GitHub issuer https://token.actions.githubusercontent.com, ref refs/heads/main, and workflow path .github/workflows/snc004b-tailscale-live.yml. Allow only tag:snc004b-semantic-ci to connect to the same tag on **tcp:41768**. Do not reuse IHP-005/IHP-006/MOR-002 credentials. The Tailscale GitHub action is pinned to immutable commit 064b10558093f38325e838ddea35486bdc6b1d5c.

The short-lived certificates are per-host self-signed test identities whose public keys are distributed through the same-run GitHub artifact channel, pinned exactly by their SHA-256 digests. This is not external issuer authentication or independent signed key provenance. Higher assurance requires source-manifest and verifier key attestations, rotation/revocation, and anti-rollback controls.

## Exact limits

This is *one-dimensional, ideal rational affine/ReLU semantics*, not arbitrary transformer architecture or guaranteed numerical GPU execution. The capsule contains full neural parameters and certificate, not the source-only semantic atlas. Receiver mathematical cache admission does not authorize external computation effects or VGI Ground admission.

GitHub-hosted jobs are distinct execution environments, but their underlying physical machines are not independently attested. Application byte counts exclude TLS/packet overhead; host-local monotonic measurements cannot be combined into a cross-machine latency estimate. A third-host report from collected artifacts independently verifies *reported* transport evidence and mathematics, not direct packet capture.

A live success requires an actual joined overlay, reciprocal TLS peer fingerprints, all E-CPU frames and application receipt, mathematically verified exact source meaning, and a successful independent third-host audit. Missing credentials, a network timeout, a failed TLS peer check or a skipped auditor means no live success.

## Natural next frontier

If a live overlay run succeeds, connect its peer identity and exact received bytes to the COE-015–018 and RE-015 source-governance and anti-rollback mechanisms. Preserve independent mathematical meaning, network path evidence, source authority and execution permission as separate decisions.
