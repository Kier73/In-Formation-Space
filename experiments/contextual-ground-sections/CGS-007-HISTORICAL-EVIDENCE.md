# CGS-007 — Historical signed observations as phase-blind Ground constraints

**Status:** independent integration proposed November 15, 2026. **New hosted replay not yet verified.** Builds on [CGS-001–006](README.md), without claiming to discover a new universal theorem.

## Research question

If an observer's TLS credential was valid when a physical message was transmitted but has now expired, can a later observer reconstruct the historical evidence and use its authenticated content to narrow a mathematical Ground, **without restoring that credential's current authority**?

If separately valid signed reports disagree, may a downstream planner choose the convenient one? **No.** Authentication speaks to key identity and context, not the truth of an observation or permission to ignore a conflict.

## Reusing a real E-CPU run, not manufacturing another signed fixture

CGS-007 extends [GCI-003 intention-relative sufficiency](../cross-ground-continuity/gci003/README.md), [GCI-004 live E-CPU mTLS observers](../cross-ground-continuity/gci004/README.md), and [GCI-005 signed disagreement](../cross-ground-continuity/gci005/README.md).

**Exact historical source:** successful [main run #43616685083](https://github.com/Kier73/In-Formation-Space/actions/runs/43616685083), November 14, 2026, source commit 90e719ae6efab12107ee8de2b77afe5e73dd35b2, signer workflow .github/workflows/cag004-topology-neutral.yml. That run carried **actual signed E-CPU mTLS observations**. CGS-007 is a new consumer of retained artifacts, not a new real network transmission.

The [historical replay workflow](../../.github/workflows/cgs007-historical-evidence.yml) downloads eight named source artifacts: signed intention/trust, E-CPU orbit probe, VGI closed orbit, public context, plan, GCI-004 network evidence, GCI-005 signed quorum report, and its independent blind audit.

Every input file must pass GitHub artifact-attestation verification against the exact signer workflow, ref and pinned source commit. A GitHub API run record supplies started/updated times. The verification requires GitHub CLI version >=2.102.0 to avoid the [signer-workflow prefix-match vulnerability](https://github.com/cli/cli/security/advisories/GHSA-wjmr-j3rp-mh2g). Digest equality alone is never represented as source authentication.

**No private phase artifact is downloaded or accepted.** Finding gci003-private.json in the working directory explicitly refuses the replay.

## Temporal evidence versus live authority

GCI-004's ephemeral root and leaf certificates last one day. Its normal certificate verifier correctly checks **current UTC time** and refuses expired credentials for new connections.

Historical verification has a separate obligation. The narrowly extended GCI-004 certificate check accepts an explicitly supplied **timezone-aware historical UTC instant**; its default remains current time. GCI-005's receipt auditor passes that optional historical instant through without weakening default live checks.

This experiment uses the original GitHub run's completion time: **2026-11-14 16:54:29 UTC**. Certificate issuer and leaf signatures, SANs, intended TLS roles, distinct peer keys, receipt ECDSA signatures, Ground/plan bindings and disagreement/refusal are still checked. The historical time must lie inside the certificates' validity period.

The date comes from GitHub-run metadata and **must be joined to externally verified artifact attestations**. A caller can fabricate a local timestamp JSON file: the Python module alone does not authenticate GitHub, prove physical event time or establish a universal causal clock. Completion time is a useful bounded historical replay instant for this particular within-one-day run, not a signed per-message timestamp.

Historical validity **does not authorize new effects**. Every output explicitly records current_authority=false and current_execution_authorized=false.

## Exact intention-relative projection

Unlike CGS-001's artificial affine-field graphs, this experiment uses the actual eight-state GCI-002/GCI-003 VGI Ground. It does not falsely identify that Ground with F_5, nor assume a parity bit is an invertible affine map.

The public GCI-003 threshold observation leaves a fiber of **four possible phases**. A unanimously verified signed parity result from the honest GCI-005 round narrows this to **two possible phases**, without disclosing which phase the receiver holds.

The authorized intention is far-y-parity at **10^15 + 137 transitions**. Over the finite Ground:

    x(t+1) = (5*x(t) + 1) mod 8
    y(t)   = (3*x(t) + 11) mod 8

For every odd horizon h, modulo 2:

    x(t+h) = x(t) + h = x(t)+1 (mod 2)
    y(t+h) = x(t+h)+1 = x(t) (mod 2).

Thus the requested future parity is **constant over both surviving phases** and equals their signed parity. The Python adapter reuses the existing GCI-003 intention evaluator. A separate Node.js implementation independently checks the 10^15+137 step result through logarithmic affine composition.

The deliberately contradictory signed round retains the four-phase pre-measurement fiber. Even if one validly signed value would simplify the result, choosing it would violate the declared unanimity policy.

## Independent reconstruction and tampering checks

The [Python bridge](historical_bridge.py) reconstructs the signed-intention chain, verifies the GCI-002 VGI certificate, rechecks all GCI-005 signed receipts at historical certificate time, and reproduces the original phase-blind audit. The [Node secondary verifier](verify_historical_projection.js) does not import the Python producer: it independently checks X.509 signer/public-key signatures and historical certificate windows, receipt ECDSA signatures, request/ground/challenge bindings and the long-horizon intention fiber. Both still share the original GCI-004/GCI-005 mathematical protocol assumptions.

Focused local tests, which create **synthetic expired X.509 certificates** but do not perform E-CPU network I/O:

    python -m pip install "cryptography>=43,<47"
    python -m unittest discover -s experiments/contextual-ground-sections -p 'test_historical_bridge.py' -v
    node --test experiments/contextual-ground-sections/test_historical_projection.js

The hosted replay consumes the actual GCI-005 artifacts, and its [10-mutation suite](test_historical_artifact.js) deliberately re-hashes forged receipts so that a digest-only checker would be insufficient. Changes to signed readings, signatures, source identities, auditor evidence, the phase-fiber result and current authority must be refused.

**Verification status:** the older GCI-005 main run succeeded, but CGS-007's newly authored GitHub Actions replay has not yet passed. No claim of new hosted verification is made before it runs. Successful evidence would be retained under the cgs007-historical-receipt-ground-reconstruction artifact name.

## Direct archived-source experiment — November 15, 2026

In addition to writing the new CI workflow, the GitHub connector retrieved the original eight public artifact ZIPs from historical run #43616685083 into the analysis environment. The saved [direct check record](results/cgs007-direct-archive-results.json) binds the complete SHA-256 digests of the source quorum report, public context and earlier blind audit.

Actual **Python 3.13.5 / cryptography 46.0.4** and a second **Node 22.16.0** recheck independently succeeded for the downloaded original records, checking canonical seals, four ECDSA-signed receipt payloads, the in-run CA and two distinct leaf signing keys, exact request digests, the Ground binding, public commitment and previous blind verdict. The original observer signatures reported **[1,1]** in the admitted round and **[1,0]** in the conflict/refusal round. The two original ephemeral CA certificates expired at **2026-11-15 16:52:14Z and 16:52:15Z**, after the historical replay instant **2026-11-14 16:54:29Z** and before the direct check. They were valid then and not valid now.

The public context had threshold bit **0**, leaving **[0,1,2,3]** possible phases. The honestly agreed signed parity was **1**, retaining **[1,3]**. Independent logarithmic modular composition gave the same projected output parity **1** for both phases after 10^15+137 transitions. The conflicting round remained refused.

This is **direct cryptographic and mathematical inspection of GitHub-downloaded original artifacts**. It does **not** mean the new end-to-end hosted replay passed; per-file GH artifact-attestation verification was not performed in the local analysis environment, and the new source-bound GitHub-hosted replay remains its own gate. No active peer authority or private phase was inferred.

## Trust limits and next frontier

The source used genuine loopback TLS between distinct OS processes and leaf keys **under one test CA, one GitHub runner and one administrative domain**, not separate physical/administrative roots or externally verified sensor truth. GitHub artifact attestations bind published evidence to workflow/commit, not to independently controlled sensor reality.

This experiment separates **historical mathematical evidence** from **current effect authorization**. It does not reconstruct the private phase, establish real-world measurements or implement general nonlinear contextuality.

The next frontier: receiver-fresh Ground revisions, independent trust roots, explicit revocation, bounded source leases and a signed causal timestamp witness. Old observers could then contribute authentic structural memory without acquiring new current authority.
