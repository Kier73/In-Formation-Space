# CGS-010 — Hard-killed receiver, live E-CPU mTLS quorum and checkpoint-free replacement

**Research purpose.** Test the missing integration after CGS-008/009: a receiver/owner process is forcibly terminated with open authenticated communication paths, while the trusted durable checkpoint root is independently held by the **existing E-CPU recovery authority services**. A new process is not handed the old local checkpoint or candidate generation. It must ask the quorum, retrieve the corresponding state bytes from an independent content-addressed archive, and reproduce their cryptographic and mathematical interpretation.

This is an experiment in **using prior systems** rather than inventing fresh consensus. All prepare votes, strict-majority certificates, commit decisions, read-high-water checks, durable authority journals and mutual-TLS reliable channels remain E-CPU's original implementation.

## Existing components reused

- [E-CPU recovery lineage service](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/docs/RECOVERY_LINEAGE_SERVICE.md): an independently supervised \`RecoveryLineageAuthorityService\` with durable member-specific journal and authenticated owner reconnect.
- [E-CPU recovery lineage](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/docs/RECOVERY_LINEAGE.md): \`RecoveryStateManifest\`, \`DistributedRecoveryLineageCoordinator\`, \`RecoveryLineagePeerClient\` and \`RecoveryLineageAuthority\`. The real protocol is **not reimplemented**.
- [Original upstream E-CPU tests](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/tests/test_recovery_lineage_service.py): the local experiment reuses the actual upstream authority-process launcher and test certificate fixtures, and reruns these independent tests in CI.
- [CGS-008 cryptographic authority](authority.js) and its [independent Python verifier](verify_authority.py): original Ed25519-signed Ground policies, receiver checkpoints, source identities and observer receipts.
- [CGS-009 state adapter](ecpu_quorum_bridge.py): canonical serialized receiver-state material, a state-content SHA-256, and the typed E-CPU \`RecoveryStateManifest\`.

The new [CGS-010 mTLS adapter](ecpu_mtls_recovery.py) contributes only **an archive locator and source-to-E-CPU assembly**, not another quorum algorithm.

## Exact live test arrangement

\`\`\`text
  original owner/receiver process A   -- OS SIGKILL --> gone
          |          |
       mTLS         mTLS
          |          |
  authority B     authority C
  own journal     own journal
          |          |
    persist exact E-CPU commit decisions
          \         /
    replacement owner/receiver A'
      (no checkpoint path)
       same A identity/term
       protected A authority journal
          |
          +-- authenticates B/C with E-CPU mTLS
          +-- reads quorum-supported (generation, manifest root)
          +-- fetches only that archived root's original manifest
          +-- checks exact state bytes and CGS-008 Ed25519 evidence
          +-- remains effect-ineligible until a new fresh challenge
\`\`\`

In the **controlled hosted experiment**, all processes use one GitHub runner and loopback TCP; B and C are genuinely separate child processes with separate journal paths and different test leaf certificates. Owner A has its own protected journal and an explicitly provisioned TLS key and trust bootstrap. This is not a claim of independent physical failure domains. Running the service on distinct machines is supported in upstream E-CPU's deployment model, but *not tested in CGS-010*.

### Snapshot and archive discipline

The initial owner/receiver generates a new CGS-008 signed demonstration transcript. The independent Python verifier authenticates its entire Ed25519 history. Generation 1 contains the exact signed Alice/Bob agreement and committed receiver counter 1. Generation 2 contains the independently signed Bob revocation, Charlie grant, contradictory Alice/Charlie readings and receiver counter 2.

Candidate immutable data is stored in three content-addressed namespaces:

- **sources:** the complete public-only original signed transcript, hashed by exact canonical bytes;
- **objects:** the exact canonical serialized receiver state (signed checkpoint + policy prefix + receipt binding, effect authorization always false);
- **manifests:** the original E-CPU typed manifest, keyed by its own canonical digest and bound to membership, predecessor root, receiver state SHA-256, generation and capture cut.

All archive objects are fsynced **before** calling E-CPU's \`seal\` operation. An unsealed archive object is never an authority: if it has no quorum-supported root, the replacement cannot select it. The manifest is not a replacement for the quorum.

The owner commits each generation using the **genuine** E-CPU distributed coordinator with A local and B/C reached over verified mutual TLS. The owner process retains its open mTLS streams and publishes a fsynced **readiness marker** only after generations 1 and 2 have been sealed. The test harness then sends **OS SIGKILL**, not a graceful close, and removes the transient readiness marker.

### Replacement with zero local checkpoint input

The replacement process has:

1. a separately provisioned, exact CGS-008 trust bootstrap;
2. the protected original A authority journal and owner TLS identity;
3. configured B/C endpoints and CA, with fixed DNS-SAN identities;
4. access to the independent content-addressed archive.

It does **not** receive \`--bundle\`, \`--checkpoint\`, \`--generation\` or a proposed restore manifest. Its first state-selection action is \`DistributedRecoveryLineageCoordinator.latest_proof()\`, which queries the E-CPU durable journals through authenticated channels. It then loads the archive manifest named by the quorum high-water root, independently verifies the exact payload digest, rechecks \`verify_state\` against the quorum and reconstructs the CGS-008 public signed history with the **Python independent Ed25519 verifier**. No private signers are restored from the archive.

The result explicitly sets \`current_execution_authorized=false\` and \`requires_fresh_challenge=true\`. Recovery of past context is not the issuing of a fresh execution capability.

### Failure cases

[Nine integration test groups](test_ecpu_mtls_recovery.py) exercise real sockets and independently started processes:

1. A receiver/owner hard kill with live B/C mTLS streams, followed by state discovery by its separate replacement.
2. An internally valid but older generation-1 signed manifest supplied as an untrusted hint is refused after generation 2's quorum commit.
3. Missing exact archived state bytes are refused, even when the signed E-CPU quorum root is available (authority is not data availability).
4. Tampered archived state bytes are refused by the E-CPU manifest digest, including an attempted promotion of \`current_execution_authorized\`.
5. A remotely hosted B authority is hard-killed and independently restarted against its original journal; the replacement still recovers.
6. Both remote services are unavailable; restoration fails closed.
7. B's endpoint is switched to C's port; normal mutual TLS refuses the wrong DNS-SAN signer.
8. Provisioned trust is substituted; fixed E-CPU membership/owner journal continuity rejects the new realm.
9. After recovery, version-2 signed evidence still explicitly revokes Bob; no archived observer receipt authorizes current execution.

The [dedicated GitHub workflow](../../.github/workflows/cgs010-mtls-owner-recovery.yml) pins E-CPU source commit \`6fd416facdb2aefd6fc7d66a06b014e3d31b5a52\`, installs its real package, reruns its original recovery-lineage, hard-kill and TLS-service tests, then executes CGS-010 on Linux Python 3.11 and 3.13 with Node 22. Successful jobs retain a **nonsecret, newly generated root/receipt demonstration** in the artifact \`cgs010-hardkill-quorum-mtls-evidence\`.

### Verification status

**Code and tests are committed; hosted CGS-010 execution must complete successfully before the cross-repository hard-kill integration is called verified.** The E-CPU upstream service and checkpoint-recovery implementations existed and had prior tests; those are genuine existing evidence, not a substitute for running this new adapter. Earlier CGS-008 signing checks do not independently verify the mTLS path.

## Limits and follow-on question

The experiment's recovery claim is relative to **one fixed trusted owner term and identity**, protected member journals, a live honest majority and an available archive. It cannot show that local storage or signing keys survive physical destruction, nor establish Byzantine resilience or independent administrative ownership. The current adapter requires both configured remote services to be reachable to construct its distributed coordinator, so it is **more restrictive in availability** than the underlying majority quorum protocol. It cannot detect a malicious replacement trusted bootstrap or a colluding majority. It also deliberately does not issue a new post-recovery receiver challenge or evaluate physical sensor truth.

The remaining frontier is to run the same protocol **over separate administrative machines and archives**, followed by a receiver-fresh post-recovery effect that requires an E-CPU quorum-fenced current owner term. Distinguish historical interpretation, current authorization, real data availability, and revocation-at-the-time-of-action rather than collapsing any of these into "recovery succeeded."
