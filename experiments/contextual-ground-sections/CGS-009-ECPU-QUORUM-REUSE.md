# CGS-009 — Reuse E-CPU's quorum recovery instead of inventing new checkpoint authority

**Motivation.** After CGS-008 showed that a signed, versioned receiver checkpoint is not enough to prove it is the *newest* accepted state, a cross-repository continuity check found this problem was **already addressed** by E-CPU.

The correct next step is integration, not new consensus machinery.

## Prior implementations located and their responsibility

| Existing system | Verified design | Role in CGS-009 |
|---|---|---|
| [E-CPU recovery lineage](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/docs/RECOVERY_LINEAGE.md) | `RecoveryStateManifest`, `RecoveryLineageCoordinator`, `RecoveryLineageAuthority`, durable strict-majority seed-commit journals | **Actual checkpoint freshness authority**, no rewrite |
| [E-CPU recovery-lineage service](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/docs/RECOVERY_LINEAGE_SERVICE.md) | Separate persistent member services with mTLS authentication, reconnection after process restart, protected member journals | Future deployment path for separate failure domains |
| [IFS durable route-epoch store](../proof-attention/sqlite_route_epoch_store.py) | `BEGIN IMMEDIATE` SQLite compare-and-swap and event audit after process restart | Alternative for **one local host only**, not a multi-host quorum |
| [IFS signed authority history](../continuous-observation-equivalence/coe017_attest/history/history.go) | Receiver-owned signed history, key revocations and event replay | Complements policy/observation interpretation; cannot alone detect wholesale rollback |
| [CGS-008](README.md) | Two-root Ed25519 policy revisions, receiver-signed checkpoint, fresh observer challenge and refusal after conflicting readings | **Meaning and evidence** of the candidate state; no duplicated journal consensus |

The distinction is important: a hash chain or Ed25519 signature establishes integrity *relative to a supplied root and history*. It does not prove that a recovered file is the latest committed revision. E-CPU already checks the latter through a durable, fixed-membership quorum.

## Working adapter design

[ecpu_quorum_bridge.py](ecpu_quorum_bridge.py) calls the **original** E-CPU public API installed from pinned main commit `6fd416facdb2aefd6fc7d66a06b014e3d31b5a52`, using `RecoveryStateManifest` (the existing **single-artifact** variant), rather than duplicating its prepare/vote/certificate/commit protocol.

A candidate serialized receiver state retains:
- the exact receiver-signed CGS-008 checkpoint;
- the prefix of root-signed Ground policies authorized at this generation;
- the source public transcript digest and committed observer receipt digest;
- Ground and realm identity, capture cut, and **current_execution_authorized=false**.

The existing independent [CGS-008 Python verifier](verify_authority.py) checks the two policy-root Ed25519 signatures, the receiver signature, all four observer signatures, policy ancestry/revocation, exact request/receipt bindings, and refusal status.

The adapter separately:
1. Creates a `SeedCommitMembership` whose fixed system identity and genesis root are **derived from the pinned trust bootstrap digest**, so an unrelated trust set cannot silently reuse the same authority journals.
2. Persists canonical state bytes and a typed `RecoveryStateManifest` to disk and fsyncs them **before** quorum sealing. The manifest binds exact state SHA-256, generation, predecessor root, membership, owner term, incarnation, and capture cut.
3. Calls `RecoveryLineageCoordinator.seal(manifest)`. E-CPU prepares the immutable slot, collects strict-majority votes, fsyncs commit decisions, and issues its existing proof.
4. After all owner processes have exited, reopens the original E-CPU authority journals in a **new Python process**. It obtains a quorum-supported high-water proof with `verify_state`, verifies the byte digest, then rechecks CGS-008 signatures and policy identity before reconstructing the state.
5. **Does not** mint a current receiver challenge or perform a new effect from an archived checkpoint. That requires a new fresh owner operation after recovery and its own authorized policy/clock context.

In the controlled experiment, two committed generations correspond to the original CGS-008 demo: generation 1 contains the Alice/Bob parity=1 agreement, and generation 2 includes the Bob revocation, Charlie grant, and refused signed Alice/Charlie disagreement. The exact prior valid generation-1 bytes remain on disk; they **must** be rejected after generation 2 becomes the quorum high-water.

## Real reuse and negative tests

[The CGS-009 workflow](../../.github/workflows/cgs009-ecpu-recovery.yml) installs the *pinned E-CPU package* in Linux jobs on Python 3.11 and 3.13, runs E-CPU's **existing native recovery lineage tests**, generates a fresh signed CGS-008 transcript with Node 22, and runs [eight integration test groups](test_ecpu_quorum_bridge.py), each CLI stage in a distinct process.

The cases verify:
- exact first/second E-CPU commit quorums and restart recovery of generation 2;
- refusal of a fully valid but older generation-1 checkpoint;
- refusal of reading or sealing with only one of three anchor journals;
- partial minority prepare followed by an exact retry with majority;
- byte-for-byte state and manifest tampering refusal;
- tampered policy signature refusal even with an intact committed quorum;
- refusal of occupied generations and generation skips;
- preservation of counter=2, policy_version=2 and no current authorization.

The workflow additionally retains newly generated signed public transcript, independent Ed25519 audit, E-CPU manifests, and a separate-process restoration report. It never uploads private receiver keys or the authority journals.

**Status:** implemented and committed; native GitHub-hosted integration result must be checked before merging or claiming successful real E-CPU execution of CGS-009. The earlier E-CPU module's independent recovery tests are existing work; a test pass elsewhere does not substitute for this integration gate.

## Limits and exact new distinction

The local experiment runs three **separate durable journals on a single GitHub runner**. That demonstrates reliance on the production E-CPU quorum algorithm, not independently administered, separate-machine fault tolerance. E-CPU's service module can host each authority in a separate mTLS-authenticated process/machine; CGS-009 does not claim to have deployed that topology.

- Fixed members and owner term remain trusted configuration. A different membership/reconfiguration needs an explicit continuity protocol; merely supplying a different file is insufficient.
- Recovery freshness is **relative to available honest, protected quorum journals**. Compromise of a quorum, erasure of all journals, or a new unrelated membership cannot be ruled out by hashes alone.
- A valid majority historical state can still be old with respect to an uncommitted future operation. The last **durably committed** root, not an uncommitted intention, is the recovery authority.
- The owner is assumed single-writer for durable state files. E-CPU's journal code handles conflicting quorum proposals, but CGS-009 has not built a multi-owner publication system.
- Neither quorum commitment nor signature verification proves the observed parity is true of an external physical sensor.

## Next actual research frontier

Use the existing [E-CPU recovery-lineage service](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/docs/RECOVERY_LINEAGE_SERVICE.md) across independently protected machines, connect it to CGS-008 receiver challenge issuance, and test a hard-killed receiver whose replacement has **no local prior checkpoint**, yet reconstructs the latest owner term and refuses superseded signed observations. Evaluate owner-term rotation and quorum membership changes as separate explicit authority transitions.

The useful conclusion is not a new mechanism: **the system already contained the needed proof structure; combining previously developed paths is the advance.**
