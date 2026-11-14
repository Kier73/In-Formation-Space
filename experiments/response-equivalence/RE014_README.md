# RE-014 — Durable authority reconstruction for scoped certificate admission and revocation

**Question:** Can the assumption authority required by RE-013 be recorded as a durable, independently replayable decision history rather than passed as an unexamined Boolean flag?

**Result:** Within a controlled synthetic policy, **yes** for *who asserted what, under which role/scope, and in which order*. **No** for proving that the asserted IID, physical source, stationarity, or sensor independence assumptions are actually true. Role signatures authenticate claims under the fixture's pre-enrollment; they do not authenticate reality.

## Relation to the three repositories

- [RE-011](RE011_README.md) established conditional confidence calculations and their IID/source assumptions.
- [RE-012](RE012_README.md) created a signed applicability monitor that suspends reused calibration guarantees on distribution, identity or latency changes.
- [RE-013](RE013_README.md) selected calibration actions and issued an append-only revision **only** when a caller set `assumptions_accepted=True`. RE-014 reconstructs the *authority* for making that scoped assumption declaration. It does not replace the actual statistical predicate or its required evidence.
- [IFS durable authority reconstruction](../proof-runner-independent-reconstruction/README.md) inspired SQLite-backed independent state reconstruction, distinct from believing a host's mutable status column.
- [E-CPU TemporalContext](https://github.com/Kier73/E-CPU/blob/main/mailcpu/temporal.py) supplies real typed causal handoffs on GitHub-hosted jobs. [VGI](https://github.com/Kier73/Virtual-Ground-Interpreter) motivates retaining the conditions under which a Ground or structural certificate is reconstructable and applicable.

## Authority policy (one new revision per transcript)

`authority_reconstruction.py` stores a hash-linked sequence of **role-HMAC-signed events** in a durable SQLite database. Its independent verifier accepts only these transitions:

1. `M:endorse` — a *methodology role* asserts the scoped IID/stationarity/representativeness premise.
2. `P:endorse` — a *provenance role* asserts the scoped source-reference and instrument-context premise. Its enrolled key is distinct from M's.
3. `V:issue` — the verifier role conditionally issues **RE-013 revision 2** only after both role assertions and an independent recomputation of RE-013's original suspension, signed plan, complete sensor evidence, quantitative criterion, and protocol scope.
4. `R:revoke` — a separate revocation authority suspends the issued revision under a declared reason (`population_shift`, `instrument_replaced`, `source_challenge_invalidated`, or `new_conflicting_evidence`). The same revision cannot be silently reissued or reactivated; future renewal requires new evidence and a new versioned policy transcript.

An event cannot be appended unless the **entire proposed history** independently replays under the policy. The append is one SQLite transaction, and each row is closed with a hash of the ordinal, previous head and signed receipt. SQLite UPDATE/DELETE triggers reject accidental rewrites. A malicious database owner can still replace a database or drop triggers: **the SQL file is not a tamper-proof ledger**.

The archive is exported to canonical JSON. A verifier checks the original source and observer evidence, all signer HMACs, scope, sequence, parent hashes, duplicate/late approvals, correct issuance and revocation order, and the final anchor. It requires a **separately obtained, trusted `(count, head)` checkpoint** to detect a fully rolled-back but self-consistent earlier journal. A checkpoint shipped by the same untrusted database producer is **not an external trust root**.

## Deterministic fixture results

| Signed history | Reconstructed status | What is established |
| --- | --- | --- |
| No events | `pending_authority` | No scoped authority claim accepted |
| M only, or M and P without V | `pending_authority` | Endorsements alone are not an issued certificate |
| M → P → V | `conditionally_admitted` | A conditional, scoped revision exists under **asserted** premises |
| M → P → V → R | `revoked` | That revision's applicable authority was withdrawn |
| Missing/duplicate endorsements, wrong role or scope, forged MAC, changed evidence, reordered or erased row | Rejected | Evidence/authority cannot be silently repaired |
| Earlier valid head presented after revocation | Passes only without a newer trusted anchor | An independently retained head is necessary to expose rollback |

The issued revision is bound to `fixture-passive-stratified-detection`, not the stimulated protocol. RE-013's old revision remains suspended. **No test establishes a real physical sensor, truthful source, IID experiment or production identity registry.** Even a valid, signed M/P assertion is an assertion—not proof of the underlying proposition. Consequently the output always includes `physical_source_truth_established=false`, `physical_sensor_identity_established=false`, `iid_assumption_proved=false`, `adversarial_guarantee=null`, and `external_attestation_present=false`.

## Hosted verification

`.github/workflows/re014-authority-reconstruction.yml` is designed to run Python 3.11/3.13 tests, generate scoped CI HMAC enrollment, have two separate GitHub jobs produce M/P endorsement receipts, append/issue revision 2 on a SQLite authority job, independently verify the exported journal and original SQLite bytes, revoke the revision on a subsequent job, and independently replay the revoked state. It uses **pinned E-CPU revision `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`** for causal stamps on Q → W and Q → R → W paths, rather than comparing independent host-local clocks.

This workflow demonstrates independently scheduled jobs and authenticated fixture roles; enrollment and authority keys are CI artifacts, so it **does not prove independent organizations, physical fault domains, or confidentiality against the CI operator**. The authority-bearing output is *conditional*, never a hardware or physical truth attestation.

## Reproduction

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/authority_reconstruction.py > /tmp/re014.json
cmp /tmp/re014.json experiments/response-equivalence/re014_report.json
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re014_cases.py
```

The first two commands and the deterministic report use only the Python standard library. The final command requires the pinned genuine E-CPU checkout. `ecpu_re014_hosts.py` provides a CLI for hosted role-signing, issuing, revocation and verification.

## What remains open

The next experiment should connect these scoped policy claims to externally verifiable *sources of authority*: pinned workflow provenance, signed independent instrument inventory and revocation of signer credentials, plus anti-rollback checkpoints outside the authority database. Even then, physical truthfulness and unbiased sampling would require experiments, not a certificate signature.
