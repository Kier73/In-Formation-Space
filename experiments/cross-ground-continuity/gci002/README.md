# GCI-002 — Evidence-admitted closed Ground, and the observer that fails

**Research question.** Can the same mathematical intention remain identifiable
across observer Grounds *after actual VGI evidence finalization*, and can a
deliberate non-congruent observer be refused rather than treated as equivalent?

**Status:** active hosted experiment; read its exact workflow evidence before
claiming a pass. This extends [GCI-001](../gci001/README.md) without replacing
its signed source or claiming general Ground universality.

## An eight-edge mathematical orbit that is actually closed

We reuse the exact CAG-004 signed law `x(0)=7`,
`x(t+1)=(5*x(t)+1) mod 65536`, projected to `x mod 8`.
Because `8 | 65536`, reduction to `Z/8Z` commutes with the recurrence.
The orbit visits every residue exactly once before returning:

```text
7 -> 4 -> 5 -> 2 -> 3 -> 0 -> 1 -> 6 -> 7
```

A *separate* GitHub-hosted process imports pinned E-CPU and calls the real
`mailcpu.law_certifier.lcg_navigate` for coordinates 0 through 8, producing
the eight full-precision transitions and their modulo-eight quotients.
Its output is arithmetic observation, not physical sensing. The source bytes
and host report are each GitHub-workflow attested on main.

An independent VGI host receives this report and the **same signed CAG-004
intention**. It creates one `TransitionEvidence` per observed edge under a
`TransitionEvidencePolicy` with one declared source and quorum one.
Evidence records use clearly synthetic message and frame identifiers; they do
**not** prove that independently authenticated network frames were observed.

The VGI host tests three evidence boundaries:

1. Eight ingested `QUORUM` outcomes cannot create a Ground before finalization.
2. Finalizing seven edges leaves an **unknown** edge; the orbit refuses closure.
3. Finalizing eight edges yields a complete, replay-checked Ground and an actual
   `AffineOrbitCertificate` for `x -> 5*x+1 mod 8`, with eight matched edges
   and cycle period eight.

It also uses the separate VGI `GroundReconstructionVerifier` to certify
finite direct-vs-compiled replay witnesses at horizons 1, 2, 8 and 16.
These witnesses are not an independent universal kernel proof.

## Observer congruence is conditional

The parity observer `p(x)=x mod 2` preserves transitions:
`p(F(x))=1-p(x)`. All eight states are checked. It therefore admits a
two-state deterministic observer Ground.

The threshold observer `h(x)=0` for `x<4`, else `1`, is not a
transition congruence. The two *reachable* states `0` and `1` both look
like `0` to it, but `F(0)=1` and `F(1)=6`, producing respectively
`h(F(0))=0` and `h(F(1))=1`. No deterministic transition on threshold
labels alone can represent both. GCI-002 records this explicit
counterexample and independently refuses false congruence claims.

The certified modulo-eight Ground reproduces only the original
`y(t) mod 8 = (3*x(t)+11) mod 8`. It cannot reconstruct the original
16-bit output from the coarse observation without more context.

## Trust / verification roles

- Source CAG-004 intent host: signed exact law and ephemeral workflow-bound key.
- Independent E-CPU orbit-probe host: eight actual navigator calculations.
- Independent VGI Ground host: typed evidence, explicit policy finalizations,
  closed `OrbitIndex`, true VGI affine certificate, finite replay certificate,
  and parity/threshold observer tests.
- GCI-001 internal and receiver host roles: unchanged.
- GCI-002 external auditor (with neither E-CPU nor VGI installed):
  independently rebuilds GCI-001/CAG-004 checks, eight source transitions,
  admitted evidence bindings, certificate edge claims, four requested
  coordinates and the observer counterexample. Host reports are checked for
  exact main-workflow attestations before accepting them.

GitHub workflow attestations establish a limited *workflow provenance*;
GitHub reports `main` unprotected, and job scheduling does not establish
independently administered or physical failure domains. Synthetic typed
evidence is not proof of a real authenticated channel encounter.

## Run

```bash
python -m pip install 'cryptography>=43,<47'
python -m unittest discover -s experiments/cross-ground-continuity/gci002 -p 'test_contract.py' -v
```

Hosted workflow: [CAG-004 / GCI-001 / GCI-002](../../../.github/workflows/cag004-topology-neutral.yml).
Pinned E-CPU/VGI revisions: see `ground_contract.py` and the workflow.
The real host paths are exercised only when the jobs run; these
runtime-free tests by themselves do not establish the hosted result.

## Next test

Pass one full-state distinction through multiple composable observers and
prove **whether the requested downstream intention factors through each
observer's quotient**. When it does not, request a specific contextual
measurement instead of manufacturing an answer or discarding provenance.
