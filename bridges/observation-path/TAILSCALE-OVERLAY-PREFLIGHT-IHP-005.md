# Tailscale overlay route preflight

**Experiment:** IHP-005  
**Status:** preflight implementation and CI validation in progress; hosted overlay run pending  
**Format:** ephemeral OIDC-authenticated tailnet peers and independently attested route observations v0.1

## Why this experiment follows IHP-002

IHP-002 successfully verified its certificates, host records, and final third-host report, but standard hosted VMs could not establish the public inbound TCP connection required by direct mTLS. The client ran in Azure westus3 and the server in AWS us-west-2; the client connect and server accept both timed out.

IHP-005 introduces a routable overlay while preserving the distinction between:
- the public GitHub artifact service used only to exchange attested peer-address bootstrap documents;
- the Tailscale control plane and encrypted WireGuard data plane used to establish the private peer route;
- the later E-CPU application transport, which is deliberately not part of this preflight.

The objective is to learn whether two independently hosted runners can reach one another over an ephemeral tailnet, and whether that path is direct UDP, DERP-relayed, peer-relayed, or unavailable.

## Experimental topology

Three independent GitHub-hosted runner jobs participate:

1. client_host joins the tailnet as an ephemeral node tagged tag:ihp005-ci, records its Tailscale IPv4 address, and attests its address document.
2. server_host independently joins the same tailnet with the same tag, records and attests its own address document.
3. Each producer downloads the other host's address artifact, verifies the GitHub artifact attestation against the exact file digest and pinned signer workflow, then runs tailscale ping --c 8 --timeout=3s --until-direct=false <peer-overlay-ip>. It stores the complete output and classifies the observed route. The explicit until-direct=false setting is important: it preserves a successful DERP or peer-relay result instead of treating "no direct path" as total failure.
4. verifier_host downloads both address documents and both route records. It independently verifies the four producer attestations, checks that each route record pins the peer's exact attested address-file digest, reconstructs the shared run/actor identities, and signs a report describing both observations.

The semantic application-payload path is not exercised in IHP-005. This is intentional: the goal here is to establish the underlying network route before re-running E-CPU mTLS over it in IHP-004.

## Authentication and one-time Tailscale setup

The workflow is designed to use Tailscale workload-identity federation with GitHub Actions, not a long-lived auth key, OAuth client secret, or reusable machine credential.

Before enabling the overlay:
1. Create the Tailscale tag tag:ihp005-ci. Tailscale requires tags used by its GitHub Action to exist already; the tag's access permissions are applied to each ephemeral runner node.
2. Create a Tailscale federated OIDC identity for GitHub Actions. Set issuer to https://token.actions.githubusercontent.com, select the auth_keys scope (shown in the admin console as Auth Keys > Write), and assign only tag:ihp005-ci. Restrict the identity to the exact repository, main ref, and workflow claims below. Tailscale's workload-identity configuration can match the subject and custom JWT claims; use the exact claim names and values shown in the GitHub OIDC token for this repository.
3. Add the federated identity's Client ID as the GitHub repository secret TS_OAUTH_CLIENT_ID.
4. Add its Audience as the GitHub repository secret TS_AUDIENCE.
5. Review the tailnet access policy for tag:ihp005-ci. For the next E-CPU transport experiment, grant only the required client-to-server TCP port (IHP-002 used 41763) between these tagged peers.

A minimal tag owner entry is:

\`\`\`json
"tagOwners": {
  "tag:ihp005-ci": []
}
\`\`\`

An example federated identity claim restriction is:

\`\`\`json
{
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:Kier73@29310272/In-Formation-Space@1454466415:ref:refs/heads/main",
  "scopes": ["auth_keys"],
  "tags": ["tag:ihp005-ci"],
  "customClaimRules": {
    "repository": "Kier73/In-Formation-Space",
    "repository_id": "1454466415",
    "ref": "refs/heads/main",
    "workflow_ref": "Kier73/In-Formation-Space/.github/workflows/tailscale-overlay-preflight.yml@refs/heads/main"
  }
}
\`\`\`

The repository was created on November 11, 2026, after GitHub's July 15, 2026 immutable-subject change. The example therefore uses the immutable subject with owner ID 29310272 and repository ID 1454466415. GitHub repositories created before that change retain the older name-only format unless they opt in; do not copy this subject format into another repository without checking that repository's actual token claims. The exact claim-rule support and claim names should be checked in the Tailscale federated-identity editor against the GitHub OIDC token claims. The repository, immutable subject, main ref, and workflow claim are intended to narrow issuance to this one workflow. The workflow independently checks its GitHub runner identity before accepting evidence.

For IHP-004, after the overlay preflight succeeds, the narrow data-plane grant for the E-CPU listener can be:

\`\`\`json
"grants": [
  {
    "src": ["tag:ihp005-ci"],
    "dst": ["tag:ihp005-ci"],
    "ip": ["tcp:41763"]
  }
]
\`\`\`

This TCP grant is not required by the IHP-005 discovery-ping-only probe; it is the proposed minimum permission for the next E-CPU mTLS step. Do not widen the rule to all ports merely to make the preflight pass.

The Client ID and Audience are federation identifiers rather than long-lived secret credentials, but this workflow reads them from repository secrets for convenient configuration. No reusable auth key or OAuth client secret is used.

The workflow has id-token: write, required for GitHub to issue an OIDC token. Tailscale's GitHub Action is pinned to commit 064b10558093f38325e838ddea35486bdc6b1d5c and CLI version 1.104.5. It creates an ephemeral node and logs it out when the CI job completes; the coordination server then automatically removes that node from the tailnet. New workflow runs receive new ephemeral nodes.

If TS_OAUTH_CLIENT_ID or TS_AUDIENCE is absent, both jobs produce explicit credentials_missing address records and the third verifier attests a report with status overlay_credentials_missing. The workflow does not invent overlay addresses or route observations in that case.

## Route classifications

The probe uses the documented tailscale ping output to distinguish:

| Classification | Observed output | Interpretation |
|---|---|---|
| direct | via <public-ip>:<port> | A direct peer-to-peer UDP path was established |
| derp_relay | via DERP(<region>) | Traffic is routed through a Tailscale DERP relay |
| peer_relay | via peer-relay(...) | Traffic is routed through a Tailscale peer relay |
| reachable_unclassified | A successful pong without a recognized route marker | Reachability is observed, but this parser cannot classify the path |
| unreachable | No successful pong within the bounded probe | No usable peer route was observed |

tailscale ping may show an initial relay response followed by a direct response. The probe runs with --until-direct=false so all bounded replies are retained. The parser gives the direct route classification priority when it appears, because a direct path was successfully established during that probe; otherwise it prefers peer-relay and then DERP. The report retains the complete output so an independent reviewer can inspect the route progression. The command's successful DISCO ping is a tailnet peer-path observation, not proof that an arbitrary TCP application port is allowed by the tailnet policy or host firewall.

A relay result is not a plaintext fallback. Tailscale's WireGuard traffic remains end-to-end encrypted; the report separately identifies whether packets traversed a DERP or peer relay.

## What is attested

For each host, the workflow attests:
- its exact address document bytes and GitHub-hosted runner identity;
- its route record, including exact local and peer address-artifact digests;
- the route classification, ping exit code, count, and raw CLI output.

The third verifier checks:
- both producer artifact attestations against their exact downloaded SHA-256 subjects;
- pinned repository, main workflow, ref, and hosted-runner policy;
- the same run and attempt, plus three distinct workflow actors;
- each peer address commitment against the other host's attested address artifact;
- each peer-address attestation embedded in the probe record against the verifier's own independent verification of the same address artifact;
- the report and its verifier-specific predicate.

The final report itself is attested and preserved as the ihp005-overlay-route-report workflow artifact.

## Interpretation and limits

- direct_peer_to_peer means both hosts observed a direct Tailscale path in their own probe.
- overlay_reachable_with_relay_or_asymmetry means both observations were reachable, but at least one side reported a relay or an unclassified route.
- overlay_path_unavailable means one or both probes did not establish a reachable route.
- overlay_credentials_missing means the federation values were not configured, so no overlay path was attempted.
- overlay_peer_not_configured means the local node joined but the other job did not publish a ready overlay address.

The probe establishes route reachability and route type only. It does not prove that E-CPU's TCP listener is permitted by the tailnet access policy, that a specific application port is reachable, or that an mTLS session can complete. A subsequent E-CPU overlay-transport experiment will use the attested tailnet IPs with the IHP-002 E-CPU SocketTransport/mTLS implementation and retain the observed route type in its transport report.

The experiment still trusts GitHub's runner isolation and OIDC/Sigstore attestation, as well as Tailscale's control plane and tag policy. The two runner jobs may share a provider or region; the third verifier runs on a separate hosted VM. Overlay addresses are ephemeral and valid only for this workflow run.

## Reproduction

Workflow: .github/workflows/tailscale-overlay-preflight.yml

Probe implementation: bridges/observation-path/tailscale_overlay_probe.py

- create-address: records the current host identity and (when configured) its Tailscale IPv4 address.
- probe: downloads and verifies the peer address artifact and uses tailscale ping --c 8 --timeout=3s --until-direct=false to classify the overlay route, preserving relayed observations as well as any direct route discovered.
- verify: checks both address and route-record attestations and reconstructs the two-sided route report on a third host.
- write-report-predicate: binds the report to the verifier identity and exact report bytes.

Regression tests cover direct/DERP/peer-relay classification, address tampering, exact peer artifact digest binding, three-host identity, relay asymmetry, missing credentials, and rejection of route claims without peer evidence.

## Official references

- Tailscale GitHub Action: https://tailscale.com/docs/integrations/github/github-action
- Tailscale workload identity federation: https://tailscale.com/docs/features/workload-identity-federation
- Tailscale grants syntax: https://tailscale.com/docs/reference/syntax/grants
- Tailscale CLI ping: https://tailscale.com/docs/reference/tailscale-cli
- Tailscale ping path types: https://tailscale.com/docs/reference/ping-types
