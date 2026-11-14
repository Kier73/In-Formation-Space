# IHP-008 — Tailscale federation activation readiness

**Status:** static source-contract audit only. No live Tailscale authentication, direct socket exchange, credential inspection or cross-host causal success is claimed by a passing audit.

The obsolete IHP-003/IHP-004 PRs have been retired. IHP-005 preflight and IHP-006/IHP-007 authenticated operation already exist on main; MOR-002 adds independent causal reconstruction. The remaining requirement is a separately scoped federated identity and tag for each live experiment.

## What was implemented

The local Python contract audit checks both existing workflow files for:
- Manual dispatch and **main-only** live peer execution
- GitHub OIDC token write permission; the pinned Tailscale action
- The expected dedicated client ID, audience and tailnet tag for both peers
- A fail-closed missing-credential gate; no reusable authkey or OAuth-secret fallback
- Real E-CPU mTLS client, signed server endpoint, and server binding to the Tailscale IPv4
- Independent verifier and observer jobs remaining outside the tailnet

The audit emits a deterministic JSON report with workflow SHA-256 hashes and required **secret names only**. It cannot read GitHub secrets or Tailscale admin settings; it does not exercise TCP, mTLS or ReliableChannel. The existing MOR-002 tests job runs this audit and mutation tests. **Only an explicit workflow_dispatch from main can start the MOR-002 live peer, observer and verifier jobs; routine push and PR events run tests only.** Source-contract success must never be described as live overlay success.

## Required administrator setup

Create **two separate Tailscale workload federation identities**, using the GitHub Actions OIDC issuer (https://token.actions.githubusercontent.com), writable auth_keys scope (Auth Keys > Write), repository and main-ref restrictions, and the exact per-workflow identity restriction below. Check the actual JWT claim names and subject values in the Tailscale editor before creating each identity.

| Experiment | Restricted workflow_ref | Required tag | GitHub repository secrets |
|---|---|---|---|
| IHP-006/IHP-007 | Kier73/In-Formation-Space/.github/workflows/tailscale-mtls-operation-path.yml@refs/heads/main | tag:ihp006-mtls-ci | IHP006_TS_OAUTH_CLIENT_ID, IHP006_TS_AUDIENCE |
| MOR-002 | Kier73/In-Formation-Space/.github/workflows/mor002-tailscale-causal-reconstruction.yml@refs/heads/main | tag:mor002-mtls-ci | MOR002_TS_OAUTH_CLIENT_ID, MOR002_TS_AUDIENCE |

The federated client IDs and audiences are not reusable authentication secrets, but use GitHub Actions repository secrets under those exact names as the workflows expect. Do not commit credential values to the repository. Both tags must be defined in the tailnet access policy and allowed for the corresponding federation identity. An example of the two TCP-only grants, to review and merge with existing policy, is:

~~~json
{
  "grants": [
    {
      "src": ["tag:ihp006-mtls-ci"],
      "dst": ["tag:ihp006-mtls-ci"],
      "ip": ["tcp:41763"]
    },
    {
      "src": ["tag:mor002-mtls-ci"],
      "dst": ["tag:mor002-mtls-ci"],
      "ip": ["tcp:41763"]
    }
  ]
}
~~~

Do not widen to wildcard ports, public networking, or cross-experiment tag access merely to make a test pass. This example has not been deployed to the actual tailnet.

## Verification sequence

1. Run: python experiments/tailscale-federation-readiness/contract_audit.py --report /tmp/federation-contract.json. Its result means **source_contracts_verified**, not live-ready.
2. Configure the IHP-006 federated identity, exact tag and TCP-only access. Manually dispatch the **IHP-006 E-CPU mTLS operation path over Tailscale** workflow from main. Require both peers to join the tailnet, exchange attested public bootstrap records, complete mTLS, deliver via E-CPU ReliableChannel, acknowledge, sign a receiver receipt and pass third-host attestation verification. Check IHP-007's reciprocal socket/route observations.
3. If failure occurs, distinguish **missing identity**, **OIDC/tag authorization**, **overlay/TCP reachability**, **mTLS endpoint identity**, **ReliableChannel ACK/receipt**, and **third-host reconstruction**. A green negative-configuration report, successful ping, or artifact upload is not itself proof of application transport.
4. Independently configure the MOR-002 identity and manually dispatch **MOR-002 Tailscale causal reconstruction** from main. Require live A1→B1 authenticated transfer, source-local A2, separate C1 observation and off-tailnet verification. Do not impose physical simultaneity from vector-clock concurrency or compute shared cross-host elapsed time from unrelated monotonic clocks.
5. Attach the two actual Actions URLs and attested report artifacts to handoff [issue #136](https://github.com/Kier73/In-Formation-Space/issues/136) once obtained. Keep missing prerequisites separate from network-protocol failures.

The original IHP-006/IHP-007 and MOR-002 docs remain authoritative for transport behavior. This readiness audit does not replace their evidence requirements, and GitHub runner jobs alone do not prove separate physical administration.

References: https://tailscale.com/docs/integrations/github/github-action and https://cli.github.com/manual/gh_attestation_verify
