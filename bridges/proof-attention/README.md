# Bridge: intention-scoped proof attention

**Status:** experimental planning bridge.  
**Purpose:** turn an existing VGI ProofGround into a reproducible attention frontier without flattening its AND/OR structure or promoting tactic claims into kernel results.

## Why this bridge exists

VGI's ProofGround represents each tactic application as an OR alternative, with every subgoal on that hyper-transition jointly required (AND). It also distinguishes candidate, elaborated, timed-out and rejected tactic attempts, and keeps kernel acceptance behind a separately supplied VerifiedKernelReceipt.

A proof-search host still needs to decide what to inspect or execute next. The ordinary partial-transition navigator is not the right abstraction: one tactic may create several jointly required obligations, while a theorem may have several alternative tactics. This bridge keeps those semantics intact and adds an explicit active-intention layer.

## API

\`\`\`python
from proof_attention import build_proof_attention_plan

plan = build_proof_attention_plan(
    proof_ground,
    root_obligation_ids=(root_obligation_id,),
)
\`\`\`

root_obligation_ids is required. The planner never guesses the theorem or goal of interest from insertion order, surface text, or the shape of the graph.

The returned document contains:

- a deterministic digest of the source proof Ground and a separate digest of the plan;
- the confirmed reachable frontier for the supplied root intentions;
- candidate tactic actions, each retaining its complete proposed AND bundle;
- the set of root intentions that structurally reach each obligation;
- kernel status for each child, with only kernel_accepted counting as accepted;
- recorded timeout/rejection counts, without automatically retrying failed attempts.

## Traversal and attention rules

Only elaborated hyper-transitions expand the currently observed frontier. Each of their subgoal_ids is traversed as part of that edge's AND bundle. Multiple elaborated hyper-transitions remain alternative OR routes. Cycles are handled by per-root breadth-first traversal.

A candidate transition is returned as an action for its source obligation, but its proposed children remain conditional and do not become reachable obligations until a later proof trace records the tactic as elaborated. This prevents an unexecuted tactic proposal from silently expanding the active proof state. Distinct candidate tactics remain distinct actions; their subgoal bundles are never flattened into a list of interchangeable successors.

The default structural order is:

1. larger number of explicit root intentions reaching the source first;
2. shorter distance through recorded elaborations first;
3. stable transition identifier as a deterministic tie-break.

Root coverage is structural reachability, not a probability or confidence estimate. The planner does not infer that a frequently shared subgoal is more likely to succeed.

## Measured tactic costs (optional)

An existing EmpiricalProbeCostModel may be supplied through its provenance_for(method_id) interface:

\`\`\`python
plan = build_proof_attention_plan(
    proof_ground,
    root_obligation_ids=(root_obligation_id,),
    cost_model=empirical_probe_cost_model,
)
\`\`\`

The model's method IDs must be explicitly bound to tactic labels (for example, simp to lean.tactic.simp) using ProbeCostBinding. It must contain sufficient successful samples for every candidate tactic, all measured on the same clock actor, process/clock segment and percentile. Only when every candidate method is bound and comparable does the planner use empirical p90/p95 nanoseconds as an additional tie-break after intention coverage and elaboration distance.

If one or more tactic methods lack a binding, latency ordering is disabled for the entire candidate set. Missing costs are not treated as zero, and partially calibrated costs are not compared against unknown costs. Cost evidence changes candidate ordering only; it does not become proof evidence, a success probability, or an authorization to execute a tactic.

The optional interface reuses bridges/observation-path/operation_spans.py and empirical_probe_costs.py; it does not duplicate their measurement or validation logic.

## Trust and interpretation boundaries

- The bridge does not run Lean, execute tactics, construct proof terms, or verify a kernel receipt.
- An elaborated tactic is not a kernel-accepted theorem. Even an empty subgoal bundle still requires a receipt for the parent obligation.
- A kernel-rejected receipt describes a rejected proof term; it does not prove that the proposition is unprovable. Other candidate tactics remain visible.
- Raw kernel_claims retained by VGI are included in the source digest but never promoted to accepted status.
- A candidate's declared subgoals are conditional until the trace records elaboration. They remain visible inside that candidate action's AND bundle.
- The frontier is the union of nodes reachable through recorded elaborations across alternative OR routes. It is an inspection map, not a minimum proof, proof-completeness result, or scheduling-optimality claim.
- Measured operation spans describe the named synchronous call boundary. They do not measure theorem difficulty, proof quality, or generalize automatically across clock segments or execution environments.

## Reproduction

The focused workflow checks this bridge against the pinned public VGI implementation and tests both structural behavior and optional cost binding:

\`\`\`bash
PYTHONPATH=bridges/proof-attention:bridges/observation-path:/path/to/Virtual-Ground-Interpreter/virtual_ground_interpreter \\
  python -m unittest discover -s bridges/proof-attention -p 'test_*.py' -v
\`\`\`

The workflow records its exact VGI commit in .github/workflows/proof-attention.yml.

## Next experiments

A later increment could admit new elaboration frames from a real tactic runner, then replan from the newly observed frontier. Another could compare the structural intention policy with a separate AND/OR cost-to-go algorithm on finite proof graphs. Neither should weaken the external kernel receipt boundary or infer a proof from an empty child list.
