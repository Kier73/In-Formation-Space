# Authority adjudication policy-space experiment

**Status:** exhaustive finite policy comparison; CI generates the complete state table.  
**Question:** how do proposer participation, independent review, abstention, approval thresholds, and rejection vetoes affect whether a revision proposal is accepted, rejected, or left unresolved?

## Why this follows append-only authority lineage

The append-only authority lineage bridge separates evidence proposal, review, adjudication, and superseding decision. Its current minimal API records an explicit adjudicator outcome. This experiment explores a richer layer in which distinct reviewers issue APPROVE, REJECT, or ABSTAIN recommendations, and a declared rule maps the collected votes to ACCEPTED, REJECTED, or INCONCLUSIVE.

The goal is not to select a policy by counting how many proposals it accepts. It is to reveal which vote configurations each rule accepts, refuses, or leaves unresolved, and to make the assumptions visible before connecting a policy to the lineage ledger.

## Finite state model

There are three symbolic participants:

- R00: the proposer;
- R01 and R02: independent review roles.

Each participant occupies one of four states:

- ABSENT: no review receipt;
- APPROVE: recommends accepting the proposal;
- REJECT: recommends rejecting the proposal;
- ABSTAIN: participates but makes neither recommendation.

The complete product contains 4^3 = 64 review patterns. No probabilities are assigned. A count of patterns is not an estimate of how often actual reviewers vote in that way.

## Candidate policies

Seven rules are evaluated:

| Policy | Proposer | Minimum distinct reviews | Approvals | Rejections |
| --- | --- | ---: | ---: | ---: |
| single_approval_permissive | Included | 1 | 1 | 3 |
| simple_majority_three | Included | 2 | 2 | 2 |
| two_approval_veto | Included | 2 | 2 | 1 |
| unanimous_three | Included | 3 | 3 | 1 |
| independent_two_of_two | Excluded | 2 | 2 | 2 |
| independent_two_of_two_veto | Excluded | 2 | 2 | 1 |
| independent_one_of_two | Excluded | 1 | 1 | 2 |

The threshold columns are counts of recommendations among eligible reviewers. ABSTAIN counts toward distinct participation, but not toward either approval or rejection thresholds.

The output is:
- ACCEPTED when the approval threshold is met without the rejection threshold;
- REJECTED when the rejection threshold is met without the approval threshold;
- INCONCLUSIVE when too few distinct reviews exist, neither threshold is met, or both thresholds are met simultaneously.

When both thresholds are met, the result is INCONCLUSIVE rather than last-vote-wins. This leaves genuinely conflicting review authority visible for further adjudication.

## What to inspect

The full adjudication-space.json contains all 64 reviewer patterns and the outcome under all seven policies. adjudication-space-summary.json records per-policy counts for accepted, rejected, and inconclusive results, along with proposer-vote, abstention, insufficient-participation, and conflicting-threshold counts.

The runner and tests independently reconstruct the finite state table and its summary digest. The portable summary schema is summary.schema.json.

## Interpretation limits

- Reviewer identities are role labels, not authenticated people or cryptographic signers.
- Review votes are supplied observations; the experiment does not establish that a reviewer is independent, competent, honest, or correctly informed.
- The model has three participants and one proposal at one logical point. It does not model collusion, dependence, deliberation, changing votes, appeals, or time-varying reviewer authority.
- All 64 configurations are enumerated, not sampled from an assumed distribution.
- Counts do not measure the truth of evidence or expected adjudication accuracy.
- The policies are candidates for further consideration, not approved authority standards.
- A future production integration needs authenticated reviewer identities, role eligibility, conflict-of-interest checks, policy versioning, signed receipts, and explicit handling of conflicting review certificates.

## Reproduce

    python experiments/authority-adjudication-space/run_adjudication_space.py --output-dir results
    python -m unittest discover -s experiments/authority-adjudication-space -p 'test_*.py' -v

CI uploads the exhaustive state table and its summary under authority-adjudication-policy-space.
