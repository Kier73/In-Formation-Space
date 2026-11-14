# SNC-001 — Semantic-to-neural compilation

**Status:** Experimental, exact one-real-input constructive neural compilation.
An untrusted producer compiles a canonical mathematical function into a new
two-layer rational ReLU network. A separately scheduled receiver checks the
complete all-real output using the existing independent COE-002 checker.

## Research question

Can a finite, verified-format description of what a model should *do*
construct a neural realization directly, rather than beginning with existing
weights or fitting samples?

SNC-001 is deliberately limited to **continuous piecewise-affine maps
from one real input to one or more real outputs**. This language can be
represented by exact rational slopes and offsets on finitely many intervals.
It does not construct arbitrary transformer models, discover suitable
descriptions from natural language, train weights, or realize numerical GPU
inference.

## Constructive law

Suppose the canonical output atlas has breakpoints
\`t_1 < ... < t_k\`, leftmost output law \`b + m_0*x\`, and successive
output slopes \`m_1, ..., m_k\`. For each output coordinate,

\`\`\`text
f(x) = b + m_0 * (ReLU(x) - ReLU(-x))
         + sum(i=1..k, (m_i - m_(i-1)) * ReLU(x - t_i)).
\`\`\`

Two hidden neurons produce \`ReLU(x)\` and \`ReLU(-x)\`; one more
produces \`ReLU(x-t_i)\` for every breakpoint. The output affine layer
uses the leftmost intercept and slope differences as exact rational
parameters. Hence a function with \`R\` maximal regions has exactly
\`R+1\` hidden neurons. No loss function, numerical optimization or
training dataset appears in the construction.

The algebra follows from \`x = ReLU(x) - ReLU(-x)\` and continuity at
every breakpoint: the hinge contribution updates the derivative without
introducing an output jump. Thus on each interval the resulting
network has the specified slope, and it agrees at the first interval's
intercept. Continuity then forces all subsequent offsets. The checker
does not trust this argument as a producer assertion: it replays all
hidden-cell activation laws from the candidate network.

This is a **known one-dimensional ReLU hinge representation**, not
a newly discovered mathematical result. The contribution is the
cross-repository *constructive semantic-to-neural interface* and
portable whole-domain verification.

## Evidence and independence

- **Input:** a canonical COE-style semantic atlas, including exact
  rational endpoint/affine tokens and both unbounded tails. The
  producer rejects gaps, overlaps, jumps, redundant partitions,
  noncanonical tokens, arity errors and exceeded budgets.
- **Producer:** \`compiler.py\` generates an architecture and the
  existing COE-002 portable activation-cell certificate. A local
  equality check catches producer regressions but is **not proof**.
- **Receiver:** \`verifier.py\` imports only COE-002's
  \`independent_certificate_checker\`, never the compiler or the COE
  atlas builder. It checks the exact serialized certificate, rederives
  affine output laws from network weights for every proposed atomic
  interval, checks hidden activation sign changes, continuity,
  full-line coverage, maximal semantic reduction and digests. It
  requires the independently verified semantic atlas to match the
  supplied source description.
- **External semantic pin:** the receiver can require
  \`expected_source_sha256\` from its own policy. CI uses
  \`examples.json\` checked out by the receiver job, rather than
  accepting a producer-supplied source hash alone. The supplied
  policy is checked-in CI trust, not third-party source authentication.
- **Independent process:** the GitHub Actions \`construct\` job
  produces transferable JSON capsules and the
  \`receive-and-verify\` job checks their bytes on a separate runner,
  using Python 3.13 instead of the producer's 3.11. This is not a
  claim of independent organizations or trusted hardware.

Both original and generated model identity must be retained. The
capsule reports semantic and neural identities separately; a shared
semantic digest does **not** imply shared architecture or equal
numerical floating-point executions. COE-002 checks ideal rational
parameters and real arithmetic. This SNC run **does not invoke
Lean** or independently formalize the hinge compiler in a proof
assistant. Formal COE-010 to COE-014 work can be connected later.

## Examples

Five checked-in descriptions exercise the direct constructive law:

| Source description | Mathematical result | Hidden neurons |
|---|---|---:|
| \`identity\` | \`x\` | 2 |
| \`constant\` | \`7/3\` | 2 |
| \`clamp_0_1\` | \`max(0,min(x,1))\` | 4 |
| \`triangular_bump\` | \`ReLU(x) - 2ReLU(x-1/2) + ReLU(x-1)\` | 5 |
| \`vector_x_abs\` | \`(x,abs(x))\` | 3 |

The test suite checks exact rational outputs at breakpoints and across
other inputs as an additional regression guard. Only successful
independent full-domain certificate verification justifies the
all-real equivalence result.

## Reproduction

From the repository root, with Python 3.11+ and standard library only:

\`\`\`bash
python -m unittest discover -s experiments/semantic_neural_compilation -p 'test_*.py' -v
python experiments/semantic_neural_compilation/run_experiment.py --output-dir /tmp/snc-results
python experiments/semantic_neural_compilation/verify_artifacts.py --capsules /tmp/snc-results/capsules
\`\`\`

The receiver can also verify any individual capsule using
\`python experiments/semantic_neural_compilation/verifier.py <capsule.json>
--expected-source-sha256 <receiver-owned-64-character-sha256>\`.

If the producer or verifier exceeds a declared work/region budget,
it must **reject or report unresolved**, never silently accept
finite tests as universal mathematical equivalence.

## Adversarial gates

The unit suite requires rejection of a model whose coefficient was
changed and whose network hash was recomputed; a forged source atlas
with recomputed source hash; a source that violates a receiver-owned
identity pin; hidden activation transitions removed from the
certificate; noncanonical/duplicate JSON; missing or discontinuous
regions; and proof-cell budget exhaustion.

## Relationship to the three architectures

- **In-Formation-Space** already has COE exact rational networks,
  complete semantic atlases and an independent activation-cell
  certificate checker. SNC-001 uses them as the construction
  language and verification authority.
- **E-CPU** already has content-addressed computation paths,
  neural graph projection, semantic translation and authenticated
  receiver execution. The next experiment is to convey the compact
  *semantic atlas* instead of shipping the generated parameter
  arrays, then reconstruct and verify at the receiver before deciding
  where to execute. Transport bytes, runtime and numerical-error
  contracts must be measured separately.
- **VGI** has ProofGround obligations and separate observed,
  admitted and reconstructed evidence. A later adapter can turn
  this accepted semantic-to-model relation into a typed proof
  obligation and retain unresolved aspects explicitly.

SNC-001 adds **no E-CPU Ground admission**, no receiver authorization,
no numerical execution guarantee, no GPU shortcut and no
multi-dimensional neural synthesis. In particular, its source
semantic digest and certificate hash prove integrity under a
specific trusted verifier context, not origin authenticity.

## Suggested SNC-002

Transport a *source* semantic atlas over E-CPU mTLS/ReliableChannel to
a separate receiver, reconstruct and independently verify the model
there, compare atlas bytes against a parameter-transfer baseline, and
measure total transfer, construction, verification and execution costs.
This would test whether moving mathematical meaning can be preferable
to moving the already instantiated neural weights.
