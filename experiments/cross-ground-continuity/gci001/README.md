# GCI-001 — Cross-Ground Computational Intention Continuity

**Question:** can one signed mathematical intention remain verifiably equivalent
through different observer projections, Ground representations, logical host
topologies and realization methods?

**Status:** executable cross-repository experimental extension of CAG-004;
CI results must be checked separately. A positive finite experiment is NOT a
general proof of representation invariance or independent physical hosting.

## One signed source, no new publisher authority

GCI-001 reuses the actual signed CAG-004 intent issued and attested by
`.github/workflows/cag004-topology-neutral.yml`, rather than signing a
similar-looking second source. Its law is

```text
x(0) = 7
x(t+1) = (5*x(t)+1) mod 65536
y(t) = (3*x(t)+11) mod 65536
t = 0, 7, 1024, 10^15+137
```

CAG-004's source, internal SHN-001 one/two declared port counts, and
separately authorized E-CPU receiver remain unchanged. CAG-004's independent
auditor rechecks those three arrangements before GCI-001 can accept any result.
One interpreter's three virtual hosts are **not three processors**.

## Fourth independently executed representation (VGI)

A separate GitHub-hosted VGI job pins
`Kier73/Virtual-Ground-Interpreter@093f11e458aff1c223d639ede413000619767ba6`.
It imports and **actually calls** `vgi.affine.ModularAffineMap.power` in
two different representations:

- Full augmented Ground: `(x,y)` over `(Z/65536Z)^2`.
  Its matrix is `[[5,0],[15,0]]`, offset `[1,14]`, initial `[7,32]`.
- Quotient Ground: `q8(x)=x mod 8`, with map `x -> 5x+1 mod 8`.

The three observer contexts are full state `x`, affine result `y`, and
the coarse state quotient `x mod 8`. Their outputs are **not** presumed
interchangeable.

### Formal arithmetic relationship

For any input `x`, the augmented transform's first component is
`5x+1`, and its second is `15x+14=3(5x+1)+11` modulo 65536.
The initial second component is `3*7+11=32`. By induction, every iteration
preserves `y=3x+11`. Since 8 divides 65536, reduction modulo 8 commutes
with the recurrence and the projection: `q8(y)=(3*q8(x)+11) mod 8`.
These are elementary symbolic equalities for this specified family;
the experiment does not claim a kernel-checked universal Ground theorem.

The quotient **does not** determine the complete full-result observer.
Two reachable states, at coordinates 0 and 8, are distinct yet both have
`x mod 8 = 7`; without their time coordinates, their full projected
outputs differ. An asserted full-result equivalence from the quotient alone
is an explicit refusal condition.

## Verification and trust

The original CAG-004 job chain creates a workflow-attested signed intent,
runs the SHN internal-path experiment and the separate receiver-owned
E-CPU Hypervisor, and independently audits both. GCI-001 adds:

1. A separate VGI host importing only the signed source and pinned VGI code.
2. A VGI report with both exact maps, observations, semantic-result digests,
   explicit observer scope, lossy-quotient counterexample and local cost.
3. A second off-host verifier importing **neither VGI nor E-CPU**, checking
   source identity, CAG-004 audit, VGI model coefficients, complete observations,
   all four semantic result identities, and the lossy-quotient refusal.
4. GitHub workflow artifact attestations of the VGI report and final audit
   on protected main. Separate jobs alone do not prove separate physical,
   administrative or cryptographic trust domains.

The VGI host uses exact integer matrix powering, **not**
`AffineOrbitCertificate`: the latter requires a closed, replay-verified
`OrbitIndex`, which this 65536-state example does not construct. Therefore
the full-Ground algebraic relation is explained and independently checked,
but no VGI closed-orbit certificate or Lean kernel proof is claimed.

Source signatures and GitHub workflow attestations are different things.
The ephemeral signing key is trusted here only through the original
CAG-004 main-workflow attestation policy; no external publisher CA is
established. Independent verifier reports record scope but do not directly
witness execution inside another job's process. Local elapsed times are not
comparable as synchronized cross-host timings.

## Reproduce

```bash
python -m pip install 'cryptography>=43,<47'
python -m unittest discover -s experiments/cross-ground-continuity/gci001 -p 'test_continuity.py' -v
```

The complete real-runtime path is exercised by
`.github/workflows/cag004-topology-neutral.yml` (CAG-004 + GCI-001),
which pins E-CPU SHN-001 PR #120, E-CPU main and VGI revisions, and
retains individual role artifacts.

## Further discriminating experiments

- Make the observer context include/exclude the time coordinate explicitly,
  and compare a longer history's ability to recover information lost by q8.
- Extend beyond compatible modular quotients: attempt a non-homomorphic
  projection and require a counterexample rather than silently admitting it.
- Form a fully VGI evidence-admitted closed Ground in a smaller modulus,
  use actual `AffineOrbitCertificate`, and compare verifier independence.
- Exercise fully independent network providers and physically separate host
  authority, rather than only distinct GitHub jobs and internal virtual links.

Sources: [CAG-004](../../convergent-ground-fabric/cag004/README.md),
[E-CPU SHN-001 PR #120](https://github.com/Kier73/E-CPU/pull/120),
[VGI affine implementation](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/093f11e458aff1c223d639ede413000619767ba6/virtual_ground_interpreter/vgi/affine.py).
