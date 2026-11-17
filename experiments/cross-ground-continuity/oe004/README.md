# OE-004 — A selected finite observation witness meets a real E-CPU mTLS receiver

**Status:** Experimental implementation, pending this change's GitHub CI evidence.

## Research question

Can a *single real, receiver-authorized observation* from the existing E-CPU
mutual-TLS fabric narrow an independently specified finite observer Ground,
while retaining an exact witness plan, the authenticated receipt, and separate
evidence of what actually happened?

An OE-003 two-lane plan evaluates both sides of a modeled state pair. A real
receiver does **not** perform two counterfactual observations of its hidden
state. The appropriate live semantics are instead:

1. A verified Ground yields a set of possible phase states.
2. A finite comparison selects a permitted test that distinguishes *some* of
   those states. For OE-004 this is the current phase's **parity**.
3. E-CPU's real GCI-004 observer processes receive a plan-bound request over
   loopback **mutual TLS**, evaluate their held phase, and return an ECDSA-signed
   receipt with the same leaf private key used by the TLS endpoint.
4. A separate GitHub-hosted verifier reconstructs the whole existing
   GCI-001/002/003/004 source, Ground, plan, signed request/receipt, certificate
   chain, peer discovery and independently held phase witness.
5. Only **after that verification** does OE-004 derive a candidate-state
   partition: states matching the signed parity reading remain possible; states
   with the other parity are excluded *relative to that validated Ground*.

The bridge does not create a new signer, request a second observation, mutate
the physical state, or invent an intermediate dispatch/admission lifecycle.
It uses the already recorded GCI-004 network operation, including the receiver's
authorization of the exact requested feature, policy and Ground.

## Components

- [`witness_binding.py`](witness_binding.py) uses the existing
  [OE-001/002 cost-aware finite navigator](../../../bridges/observation-equivalence/costed_navigation.py)
  to construct a zero-action, one-test `parity` distinguishing witness.
  OE-004 uses its own typed, digest-bound **symbolic-cost plan** rather than
  reusing OE-003's nanosecond-named field for a different unit. The test's
  **1 unit** is GCI-003's declared symbolic cost, *not* measured nanoseconds.
  The independent verifier reconstructs the entire OE-004 plan from the
  previously verified GCI-003 candidate Ground, then rechecks GCI-004's
  source receipt before using its result.
- [`test_witness_binding.py`](test_witness_binding.py) tests finite witness
  construction, exact model/policy pinning, incomplete or invalid candidate
  universes, false uniqueness and invalid observations.
- [`test_live_binding.py`](test_live_binding.py) runs on the separately
  scheduled GCI-004 auditor's **actual transferred network artifacts**. It
  independently rejects a changed signed reading, altered request challenge,
  wrong TLS leaf identity, rehashed substituted witness plan, and fabricated
  candidate filter. It restores every changed artifact after each test.
- The [CAG-004 main workflow](../../../.github/workflows/cag004-topology-neutral.yml)
  runs the new finite tests and extends the existing GCI-004 independent
  verifier job. That job has *no E-CPU or VGI installation*, already checks
  GitHub attestations for each input artifact on `main`, and publishes the
  reconstructed OE-004 witness receipt as an additional artifact.

## Precise observable

Let the independent verified GCI-003 source Ground constrain the current
hidden phase to the finite candidate set \(C \subseteq \mathbb Z/8\mathbb Z\).
The authorized observation is

\[
 O_{parity}(s)=s\bmod 2.
\]

A minimum-cost zero-action OE-004 plan using the OE-001/002 navigator finds a pair \(a,b\in C\) with
\(O(a)\ne O(b)\). This proves that one parity read is capable of separating
**those two possible states** under the model, not that it identifies every
element of \(C\). For the single actually signed return \(v\), OE-004
retains exactly

\[
 C_v=\{s\in C: O_{parity}(s)=v\},
 \qquad
 C_{excluded}=C\setminus C_v.
\]

The report retains \(C\), \(C_v\), \(C_{excluded}\), the OE-003 model/plan
digest, selected policy and source binding, the original GCI-004 network and
independent audit digests, authenticated leaf certificate fingerprint, peer
snapshot digest, signed request/response digest, request challenge, received
value, and separately recorded observation RTT.

## Reproduction

The contract-only test requires Python 3.11+ and `cryptography`:

```bash
python -m unittest discover -s experiments/cross-ground-continuity/oe004 -p 'test_witness_binding.py' -v
```

The **live** version needs the complete GCI-004 hosted artifact directory
(produced by the CAG-004 workflow):

```bash
python experiments/cross-ground-continuity/oe004/witness_binding.py \
  --directory evidence/cag004 --output evidence/cag004/oe004-witness.json
python experiments/cross-ground-continuity/oe004/witness_binding.py \
  --directory evidence/cag004 --verify evidence/cag004/oe004-witness.json
python experiments/cross-ground-continuity/oe004/test_live_binding.py \
  --directory evidence/cag004
```

## Trust and evidence limits

- GCI-004's E-CPU receivers use **real separate processes, TLS sockets,
  authenticated peer snapshots, and leaf-key-signed receipts**, but they
  share one CI runner and one ephemeral test CA, not independently administered
  or physically separate trust domains.
- The independent verifier executes on a **separate runner job**. The existing
  GCI-004 audit receives the privately held mathematical phase for its truth
  check; it is not phase-blind. The prior GCI-005 experiment covers signed
  disagreement using a phase-blind verifier.
- A certificate authenticates the signer, not the correctness of a physical
  sensor. The experiment observes held mathematical phase, not an external
  environment. GCI-004's report of TLS channel binding and elapsed nanoseconds
  is runtime-reported; an external auditor cannot reproduce elapsed time from
  cryptographic proof alone.
- GitHub artifact attestation on `main` binds artifacts to this workflow.
  A standalone local invocation of `verify_live_binding` does **not** itself
  verify GitHub artifact attestations or establish externally governed key
  provenance. The underlying signed receipt and independently audited source
  remain necessary.
- This bridge **does not** consume E-CPU's `GatedObservationCoordinator`
  quorum/VM-commit path. GCI-004 is a receiver-authorized single-feature host
  experiment. It does not manufacture a consensus approval or VM application.
- The selected pair is a **hypothetical comparison**, not two physical
  executions. A single returned parity value narrows the candidate fiber but
  normally does not determine a unique full state.
- The reported cost of one symbolic unit and the measured TLS observation
  round-trip nanoseconds are distinct fields; neither is an empirical OE-002
  source-span profile or a whole-path execution-cost guarantee.

## Next work

The next rigorous composition should connect a selected **action-bearing**
finite witness to E-CPU's GatedObservationCoordinator or a federated
receiver-side execution admission contract. An independent verifier would
then inspect the explicit applied/checkpoint markers and preserved source
consensus as well as signed observation receipts. The distinction between
observed symbol and actual VM state transition should remain checkable.
