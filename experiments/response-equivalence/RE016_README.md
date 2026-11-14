# RE-016 — Publicly verifiable migration receipts without hidden historical replay

**Question.** Can future authority records be checked with public keys after RE-014's symmetric HMAC verification secrets are retired, without changing historical evidence or claiming a newer attestation is equivalent to independently verifying the old history?

**Result.** Yes, but only in a **narrow, explicitly attested** sense. A migration ceremony with access to historical RE-014 HMAC material checks the complete old authority/certificate evidence and RE-015 governance + witness checkpoints once. Its role-scoped Ed25519 signers (`R1`, `W1`, `W2`) then endorse a content-addressed *public projection* and the outcome of that prior replay. Later verifiers require the pinned genesis, signed checkpoint heads, migration manifest and the public archive—**not RE-014 HMAC verification keys**. Such a verifier authenticates the *endorsement that verification occurred*, but **does not repeat** the historical HMAC check and cannot establish that the ceremony actually was honest.

This result continues [RE-014](RE014_README.md) and [RE-015](RE015_README.md); it does **not** claim that the earlier historical HMAC verifier's dependency has been magically removed. That dependency is moved into the transition ceremony and the validity of its attestation. No signature can establish physical sensors, statistical IID assumptions, hardware-bound signer identities or exhaustive truth about the observed system.

## Protocol and custody separation

1. **Legacy ceremony C (secret-holding only).** Verify the unchanged RE-014 HMAC transcript, the actual RE-013 calibrated evidence, signed RE-015 `R0 → R1` rotation/revocation, and the `W1/W2` signed checkpoint claims. Hash the *complete historical archive* (including material retained by the secret custodian) but export only a public view with `registration.keys` removed. No signed historical artifact is rewritten. Produce a `legacy_hmac_replayed_during_ceremony` claim, not a claim of universal correctness.
2. **Independent role attestations.** `R1`, `W1`, and `W2` each sign the exact migration body with **Ed25519**. Their public keys are obtained from the externally pinned RE-015 genesis and authenticated rotation chain. The public migration is rejected if any role is absent, its signature fails, or a scope, archive digest, key epoch or checkpoint changes. A role signer who knowingly signs a false ceremony result remains a possible threat. All three private keys together can produce an internally valid but dishonest attestation.
3. **Externally presented pin.** The verifier requires an independently provided pinned trust-genesis digest, migration digest, and governance latest head. The test workflow retains this as a separate GitHub artifact *within the same CI trust domain*; that is a demonstration of a **pin interface**, not proof of fault-isolated custodianship. If the database, witnesses and pin are all rolled back together, the rollback is not detectable from those bytes alone.
4. **Public replay.** A fresh process sees only `public_history` (no HMAC keys), genesis public keys, original RE-015 signed governance and checkpoints, the attested migration body and the retained pin. It independently checks signatures, strict parent-linked governance, exact identity/scope and public projection byte commitments. Its **mandatory result type** is `historical_validation_mode=attested_prior_legacy_replay`, `historical_hmac_reexecuted=false`, `legacy_secret_required_for_public_verifier=false`. The original certificate stays `revoked`.
5. **Future receipts.** New `custody_confirmed`, `audit_warning` and `legacy_keys_retired` records use only `R1 + W1 + W2` Ed25519 signatures, fixed certificate scope and a parent-linked append-only SQLite journal. An optional separately retained latest-head pin detects rollback **only while newer pin bytes survive**. The `legacy_keys_retired` event is an authenticated *claim of retirement*, **not proof of erasure**. These future records **cannot issue a fresh certificate, undo a revocation or substitute for a new calibration**.

## Exact reproducible outcomes

| Presented evidence | Result |
| --- | --- |
| Ceremony replays valid original HMAC evidence, then three attestations and pinned head verify | Public verifier reports `revoked` with **attested prior replay** |
| Public verifier has no RE-014 HMAC key material | Public replay succeeds; old HMACs are **not** reverified |
| Historical byte, session, genesis, scope, signature or retained checkpoint changed | Rejected |
| Historic archive or original HMAC receipt changed **before** ceremony | Secret-holding ceremony refuses prior replay |
| Historical HMAC keys unavailable **before** migration | Cannot perform the ceremony; no legitimate new attestation established |
| Future unsigned, replayed, scope-swapped or counterfeit public-key receipt | Rejected |
| Future certificate reissuance or revocation reversal attempted through receipt kind | Forbidden by finite policy |
| Old SQLite future journal with **newer external pin** | Rollback detected |
| All historical data, witnesses and latest pin substituted together | **Not detectable without independently retained trusted evidence** |

**Trust dependence:** a legitimate current key and two witness signatures authenticate what signers asserted; no universal claim of correctness follows. The synthetic CI source code creates the underlying ground truth and key enrollment. Root key compromise, identical organizational control over all roles, and signed false statements are not ruled out. Even full public-key replay does not prove source truthfulness or scientific model-completeness.

## Integration with E-CPU and structural memory

`.github/workflows/re016-public-migration.yml` installs `cryptography>=43,<47`, checks the genuine pinned E-CPU revision `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`, runs the full RE suite under Python 3.11/3.13 and tests the new adapter. The hosted ceremony alone receives HMAC-key-bearing original evidence. Separately scheduled `R1`, `W1`, `W2` signer jobs receive only their respective test Ed25519 key and the **public** ceremony result. An independent pinning job assembles the attestations, then a public verifier and fresh replay job reconstruct the status without legacy keys. Each signer binds its signature and the ceremony digest to its **real E-CPU causal frame**; the verifier checks `C before each signer` and signer branches mutually `concurrent`. This is logical precedence, not simultaneous physical time or an external hardware identity proof.

The implication for VGI structural memory: keep an explicit **verification mode** with the result. A reconstructed *claim about an earlier verification* cannot be silently promoted into a fresh independent reconstruction of the older evidence. This permits a useful public interface across key retirement without rewriting the original Grounds.

## Reproduction

```bash
python -m pip install 'cryptography>=43,<47'
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/public_migration.py > /tmp/re016.json
cmp experiments/response-equivalence/re016_report.json /tmp/re016.json
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re016_cases.py
```

This is a **synthetic constrained demonstration**, not a production PKI or an assurance that the secret custodian actually erased private keys. The next investigation should consider independent witness groups with different organizations and external objective log inclusion, and quantify what evidence survives an adversary able to compromise one or more roots.