# E-CPU mutual-TLS operation path over Tailscale

**Experiment:** IHP-006  
**Status:** implementation and local protocol validation in progress; live hosted tailnet run pending  
**Format:** three-host, OIDC-federated Tailscale overlay with E-CPU SocketTransport, mutual TLS, ReliableChannel, and third-host reconstruction

## Question

Can the independently hosted client and server from IHP-002 perform the same peer-authenticated E-CPU operation when the server endpoint is reachable only through an ephemeral Tailscale overlay?

IHP-002 already implements the application protocol: per-run X.509 identities, reciprocal certificate fingerprint checks, a signed operation envelope, E-CPU ReliableChannel delivery and ACK, receiver-side causal merge, a durable signed receipt, a reverse ReliableChannel, and independent third-host reconstruction. Its public-inbound TCP attempt timed out on separate Azure/AWS hosted VMs.

IHP-005 added an independently attested Tailscale route preflight. Its recorded run is important but negative with respect to network evidence: the OIDC federation values were not configured, so both producers attested `credentials_missing`, no Tailscale node joined, and no peer route was attempted. A green verifier workflow did not establish overlay connectivity.

IHP-006 joins the two operation hosts to a dedicated tailnet and changes only the server endpoint selection. The existing E-CPU mTLS/ReliableChannel protocol is reused; its signed endpoint advertises the server's validated `100.64.0.0/10` Tailscale IPv4 address instead of a public egress address. A third host independently verifies all producer attestations and reconstructs the operation report.

## Topology and transfer paths

Three separate GitHub-hosted jobs participate:

1. **client_host** joins the IHP-006 tailnet, creates its ephemeral client certificate, attests and publishes only the public certificate, then downloads the server's attested bootstrap and sends the signed operation over E-CPU SocketTransport/mTLS.
2. **server_host** independently joins the same tailnet, verifies the client's public certificate attestation, creates its own certificate and a signed endpoint advertisement containing its Tailscale IPv4 address, then listens on TCP port `41763`. Its ReliableChannel commit callback validates the signed envelope, merges the sender's E-CPU causal stamp, performs the successor operation, signs the receiver receipt, and durably writes its record before the channel ACK is emitted.
3. **verifier_host** does not join the tailnet. It downloads public certificates and attested host records, independently verifies the GitHub artifact attestations, reconstructs the signed endpoint, TLS peer fingerprints, ReliableChannel sequence, envelope, receiver receipt, operation spans and causal witness, then attests the reconstruction report.

| Material | Path |
|---|---|
| Public client certificate and predicate | GitHub Actions artifact |
| Public server certificate, predicate and signed endpoint | GitHub Actions artifact |
| Signed semantic operation envelope | Tailscale overlay, E-CPU ReliableChannel over mTLS |
| ReliableChannel ACK | Same mTLS session |
| Signed receiver receipt | Reverse ReliableChannel over the same mTLS session |
| Final host records and reconstruction report | GitHub Actions artifacts, independently checked by verifier |

The artifact store is bootstrap and evidence transport only. It is not a fallback for the semantic operation, ACK or receipt. A report can claim an established causal handoff only after the actual socket session, TLS peer checks, ReliableChannel delivery and receipt verification succeed.

## Dedicated Tailscale workload identity

IHP-006 intentionally does not reuse IHP-005's identity. Configure a separate tag and GitHub workload-identity federation entry:

- Tag: `tag:ihp006-mtls-ci`
- GitHub repository secrets: `IHP006_TS_OAUTH_CLIENT_ID` and `IHP006_TS_AUDIENCE`
- Issuer: `https://token.actions.githubusercontent.com`
- Scope: `auth_keys` only
- Allowed tag: `tag:ihp006-mtls-ci`
- Workflow restriction: `Kier73/In-Formation-Space/.github/workflows/tailscale-mtls-operation-path.yml@refs/heads/main`
- Ref restriction: `refs/heads/main`
- Repository restriction: `Kier73/In-Formation-Space` (repository ID `1454466415`)

The repository's immutable GitHub OIDC subject is:

```text
repo:Kier73@29310272/In-Formation-Space@1454466415:ref:refs/heads/main
```

Use the exact subject and claim values exposed by the GitHub OIDC token in the Tailscale federation editor. In particular, match the repository, repository ID, ref and workflow-ref claims to this workflow; do not assume the claim names from another repository or copy an identity rule without checking its token claims. The client ID and audience are federation identifiers, not reusable Tailscale auth keys or OAuth client secrets.

The intended tag policy is:

```json
{
  "tagOwners": {
    "tag:ihp006-mtls-ci": []
  },
  "grants": [
    {
      "src": ["tag:ihp006-mtls-ci"],
      "dst": ["tag:ihp006-mtls-ci"],
      "ip": ["tcp:41763"]
    }
  ]
}
```

This grant is deliberately limited to the E-CPU listener port. Do not widen it to all TCP ports or all protocols to make the experiment pass. Tailscale workload identity federation accepts only provider-issued identity tokens whose issuer, audience and configured claims match the administrator's policy; GitHub Actions must grant `id-token: write` to request the token. The workflow's Tailscale action is pinned to a full commit SHA and creates ephemeral nodes that are logged out at job completion. See the official Tailscale [workload identity federation](https://tailscale.com/docs/features/workload-identity-federation) and [GitHub Action](https://tailscale.com/docs/integrations/github/github-action) documentation.

If either IHP-006 secret is absent, both operation jobs fail before producing certificates or records. There is no public-IP fallback and no result is labelled as an overlay attempt.

## Endpoint and trust checks

- `prepare-server --advertise-host` accepts only an IPv4 address within Tailscale's `100.64.0.0/10` range.
- The IHP-006 workflow identity requires that explicit address; omitting it fails closed before bootstrap.
- A third-party or public endpoint is rejected when an endpoint is signed by an IHP-006 server identity.
- The server endpoint is signed by its per-run Ed25519 key and binds the server certificate fingerprint, client actor and client certificate fingerprint.
- Mutual TLS requires the expected role-specific DNS identity and both peers compare the live TLS peer certificate fingerprint with the attested bootstrap certificate.
- The sender's signed envelope binds the exact operation span, temporal frame, causal payload, channel and sequence.
- The receiver persists the signed receipt and host record inside the ReliableChannel commit callback before ACK.
- The client verifies the returned receiver receipt and its signature.
- The third host verifies certificate and record attestations against this exact workflow, then independently reconstructs the causal handoff.

The separate Tailscale and TLS identities are complementary: WireGuard protects the overlay network path; mTLS authenticates the application peers and binds the application exchange to the per-run certificates. Neither layer substitutes for the other.

## Outcome interpretation

The existing IHP-002 record/report vocabulary is retained so the actual mTLS and causal protocol is not silently changed:

- `direct_mtls_verified` host records and a reconstructed direct transport report mean the application protocol completed over the Tailscale endpoint.
- `direct_tcp_unavailable` means the overlay TCP connection or TLS handshake could not be established; it is not a successful operation handoff.
- A report attestation proves the report bytes and workflow provenance were attested. It does not, by itself, prove that the operation succeeded; inspect the report's status and both host records.
- No combined cross-host elapsed duration is inferred. Each host retains its own monotonic operation measurements; the E-CPU causal stamp establishes order, not a calibrated shared clock.

IHP-006 is not complete until a live run has the dedicated federation identity configured and the independently verified report demonstrates a successful E-CPU operation, ACK, receiver receipt and causal reconstruction. A green run with an unavailable transport remains a useful negative result, not a successful overlay operation.

## Reproduction

Workflow: `.github/workflows/tailscale-mtls-operation-path.yml` (manual dispatch from `main`).

Protocol implementation: `bridges/observation-path/direct_mtls_operation_path.py`  
Protocol tests: `bridges/observation-path/test_direct_mtls_operation_path.py`

The E-CPU dependency is pinned to commit `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`. IHP-006 uses a separately allowlisted workflow identity in the shared mTLS implementation; the original IHP-002 workflow and its public-IP endpoint behavior remain unchanged.

The local protocol suite covers certificate generation and pinning, signed endpoint validation, real TCP mTLS and ReliableChannel delivery, receiver receipt reconstruction, the IHP-006 workflow allowlist, and refusal of public endpoint fallback. The repository integration workflow validates the new workflow YAML and runs the complete direct-mTLS and Tailscale preflight test suites.

## Known distinction

A Tailscale `ping` result identifies the overlay path used for the probe; it does not establish that the E-CPU application port is permitted. IHP-006 therefore tests the actual TCP/TLS application exchange on port `41763` instead of treating an ICMP/DISCO route observation as proof of application connectivity. When successful, it records the result at the application-protocol layer.
