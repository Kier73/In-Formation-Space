# RE-015 — Credential continuity, issuer loss, and independently retained authority checkpoints

**Status:** exact synthetic authority/recovery research. This does not attest physical signer identity, prove scientific assumptions, or provide a production PKI.

## Question

Can a conditionally issued RE-014 certificate remain reconstructable after its original issuer process disappears, while revocation authority rotates to a new credential and an old authority database can be rolled back?

## Construction

RE-014's existing SQLite issuance transcript remains unmodified and supplies the prior evidence, signed methodology and provenance assertions, issuance, exact certificate digest and scope. RE-015 adds a **separate append-only governance ledger** that changes the *current* certificate status without rewriting the historical RE-014 issuer record.

1. A narrowly pinned trust genesis lists the initial `R0` Ed25519 public key and two separate external witness public keys `W1`, `W2`. The replacement public key is introduced through a signed rotation record. The trust genesis itself is externally assumed; our CI enrollment is not a real credential authority.
2. A rotation entry is signed by **R0 plus both W1 and W2**, binds the existing RE-014 certificate digest and evidence scope, and activates the new `R1` key. The original issuer process or key is not needed for subsequent *new* governance signatures.
3. A separate revocation is signed by **R1 plus both W1 and W2**, names a policy reason, and turns the effective reconstructed state to `revoked`. Stolen or replayed R0 signatures cannot revoke after rotation.
4. An append-only SQLite governance journal retains the parent-linked signed decisions. W1 and W2 each maintain a **distinct SQLite checkpoint archive** outside that authority database. Their signed, count-monotone anchors bind the base RE-014 anchor, evidence digest, certificate digest, scope, and the new journal head.
5. A new verifier reconstructs the original RE-014 admission, the new key chain and revocation, and both latest external witness heads. A stale/rolled-back authority journal fails when either retained external checkpoint is newer. Forked but internally valid governance histories are likewise detected relative to a retained anchor.

The local model supports a retained witness checkpoint at index 0 (before rotation), 1 (after rotation) and 2 (after revocation). An interrupted update affecting one external replica **fails closed** rather than silently discarding or repairing the disagreement. Only explicitly retained valid receipts permit a deliberate repair process; one is not invented by the verifier.

## Results and counterexamples

| Evidence situation | Reconstructed state or decision |
| --- | --- |
| RE-014 issuance, no governance decisions | `conditionally_admitted` |
| R0 + W1 + W2 rotate to R1 | `conditionally_admitted` with new authorized R1 |
| R1 + W1 + W2 revoke | `revoked` |
| R0 attempts a new revocation after rotation | signature verification fails |
| A single witness tries to sign on behalf of both | verification fails |
| Governance SQLite rolled back, newer W1/W2 heads retained | rollback detected |
| Two valid forks, one retained external latest head | conflicting fork detected |
| All governance and both external witness archives rolled back together | **not detectable from the replayed evidence alone** |
| Original issuer host unavailable, historical RE-014 material preserved | new verifier reconstructs conditional issuance and revocation |

**Legacy verification dependency:** RE-014 signs authority receipts with symmetric HMAC. Full reconstruction of the *historical* RE-014 issuer record still requires preserving its verification key material (`V`, `M`, `P`, etc.) in trusted custody; Ed25519 cannot retroactively replace those HMACs. RE-015's **new** key transitions and witness anchors use Ed25519 public-key verification. This experiment therefore demonstrates loss of the original *issuer process*, not independent recovery after every historical HMAC secret is destroyed.

**External anti-rollback dependency:** SQLite `UPDATE`/`DELETE` triggers protect normal transactions, not an administrator who replaces database bytes. Two independent witness files detect rollback **only when at least one newer authenticated external checkpoint is retained and presented**. Simultaneous collusion or rollback of the authority and both witnesses is outside this guarantee. Both roots sign the governance actions, so the current policy tolerates no dishonest/compromised root; it is not Byzantine consensus. Two separately scheduled GitHub Actions jobs are not attested fault-isolated hardware.

**Public trust bootstrap:** A valid Ed25519 signature authenticates a claim only to the initial pinned keys. The genesis is created by the fixture; no production device enrollment, public PKI, secure element, real-world root rotation, or external attestation is claimed. The existing RE-014 calibration remains conditional on statistical and physical assumptions that no signature proves. The CI-hosted fixture transfers keys through short-lived artifacts; those artifacts are *not* secure key escrow.

## E-CPU temporal integration

`.github/workflows/re015-credential-continuity.yml` runs all response-equivalence tests (Python 3.11/3.13), then checks out pinned E-CPU `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`. Distinct hosted jobs write rotation and revocation journals, after which W1/W2 write independent checkpoint SQLite files. A separate verifier uses actual `TemporalContext`/`CausalStamp` operations and requires the event order `Q before R before W1`, `R before W2`, and `W1 concurrent W2`. This is causal message-handoff evidence, not wall-clock synchrony or physical host identity. The verifier compares each archived witness SQLite history to the supplied signed checkpoint list, independently reconstructs all records, and reports no physical validity guarantee.

## Reproduce

Install `cryptography` (tested with 46.x) and run from the repository root:

```bash
python -m pip install 'cryptography>=43,<47'
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/credential_continuity.py > /tmp/re015-replay.json
cmp experiments/response-equivalence/re015_report.json /tmp/re015-replay.json
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re015_cases.py
```

The synthetic results are exact with respect to the supplied policy, signed records, anchored history and finite fixture. They are **not** a universal trust/reliability result.

## Next investigation

Make an externally retained trust genesis and latest checkpoint durable across *actual* organizational fault domains, and transition the RE-014 historical symmetric receipt layer to asymmetric verifier-only evidence without rewriting its original history. Examine key compromise detection and independent public-key rotation policies with honest-minority and colluding-witness counterexamples.