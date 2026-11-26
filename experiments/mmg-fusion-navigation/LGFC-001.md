# LGFC-001 v0.1 — Lazy Ground Fitting Conjecture

Status: proposed, not a theorem of general algorithm search. MMG-015–017 provide a conditional theorem, an exact matrix multiplication barrier/escape witness, and mixed preliminary comparative evidence.

## Definitions

Fix a mathematical intention I=(T,τ,V): exact target identity T, required complexity τ, and independent verification V. Let G_T be the graph of verified algebraic representations, with edges given by a specified semantics-preserving transformation set M. A ground g has a scalar cost C(g) for the experiment; in MMG-015–017 this is tensor rank (nonscalar products), not complete arithmetic circuit cost. A general intention can instead use a vector of costs or a scalarized cost, with all realization and translation work charged. Keep search/build work W separate. Incumbents are certified upper bounds; targets and lower bounds are independent of them. Invalid candidates are never admitted as solutions.

For initial ground g0 and target set H={g:C(g)≤τ}, define the minimum rank-debt barrier B(g0,H)=inf over finite paths from g0 into H of max(0,max along path C(g)-C(g0)); infinity if no path. Define a monotone policy to prohibit increases in cost along each transition. A debt-capped exploratory policy can retain any verified intermediate ground with C(g)≤C(g0)+δ, irrespective of final target. Fitting means selecting/compressing candidates toward the target; lazy fitting delays that selection, not formal identity checks or final cost admission. Define first-hit probability P_π(W,τ) over a fixed seed distribution and instance family, with W a charged search-work budget.

## Conditional theorem (not conjectural)

If B>0, no monotone path from g0 can reach H. If B≤δ<∞ and a stochastic policy gives positive probability to every transition of one finite admissible path, it reaches H with probability at least the product of those transition probabilities within the path length. For independent restarts, failure probability is at most (1-q)^k where q is the per-restart lower bound. This is conditional on support and sufficient budget; it does not establish a useful value of q, nor show that delayed selection generally improves efficiency.

## Conjecture (testable, conditional)

For benchmark families with verified positive debt barriers and a sufficiently accessible set of target-reaching paths within a finite debt cap, a policy that preserves structural diversity until a fitting phase will have higher first-hit probability per fixed charged search-work budget than rank-first selection with matched moves, memory, and restart opportunities. This is an empirical hypothesis about finite-budget search, not universal dominance. Predeclare instances, targets, debt caps, policy schedules, seeds, and accounting; report P, time-to-first-hit, achieved cost, and work, including diversity overhead. A benchmark family with no advantage at matched work is negative evidence. A graph in which the unique useful path is monotone is a counterexample to an unconditional formulation; do not claim one. For matrix multiplication, no exponent below 2 is admissible in the standard explicit scalar-output model. The actual open research target remains a verified witness beating the manuscript's 9/4 claim.

## MMG-015 — first paired experiment

Same flip/split and merge moves, six-candidate archive, fixed cap initial rank+4, five paired seeds per instance. Eager sorts by rank then diversity from initial; lazy retains latest candidate and fills the archive by max-min pair-atom Jaccard distance, ignoring rank inside cap. An independent best witness is recorded. These policies differ in selection, not moves or final verification. Distinct states use sorted coefficient triples, not equivalence up to all tensor automorphisms. The seen-state set is unbounded in this finite run for both policies, so this is matched archive width rather than a measured memory bound. 30 runs, 160,000 proposals. n=2 naive rank8 -> rank7 in 3/5 eager, 5/5 lazy. n=3 naive rank27 -> rank26 in 1/5 eager, 0/5 lazy. n=4 published rank47 -> no improvement for either. Diversity increases distinct representations but is not sufficient evidence of better rank search. Equal proposal counts are not equal CPU work.

## MMG-016 — exact positive barrier in T_2 over GF(2)

Ground in row-major coefficient masks (A,B,C output convention):
[1,2,12], [4,10,6], [5,15,14], [8,5,10], [12,9,5], [13,13,15], [14,8,3], [15,12,1].
Every coefficient of T_2 is verified. Generated from a known rank7 ground by bounded exploratory moves; found after 124,216 proposals and inspection of 80 candidates. Enumerate all 3*8*7=168 ordered axis/pair moves, using same split/flip and repeated exact pair merge. All 168 distinct resulting grounds have rank9, and all are exactly verified. Thus no first step of cost≤8 exists in this specified graph. This is not a global tensor-rank lower bound, nor a claim about every possible operation.

Initial bounded breadth-first search visited 45,011 states without a lower-rank witness. A separate stochastic run with cap9 found a rank7 ground after 4,636 proposed moves (4,537 accepted); the final restart's 151-edge path is retained in mmg016_escape_results.json. Every step is replayed and independently verified. All states on path have rank≤9. The final ground:
[1,1,5], [2,4,3], [5,15,4], [8,10,12], [12,2,10], [13,14,6], [15,12,2].
Together the complete outgoing enumeration and exact path certify B=1 for reaching rank≤7 under these moves. Rank7 is a known optimum, not a new algorithmic rank bound. The path length is not claimed shortest.

## MMG-017 — periodic fitting, precommitted held-out schedule

Source/config committed at 24ce836488869ab3098d3edaf31f65f20c5dbd9c before execution. Eager and lazy as above; hybrid alternates 128 discovery proposals and 64 fitting proposals, injecting the best verified incumbent at fitting transition. Independent seeds; 5 paired runs each for isolated n=2 rank8 (cap9) and n=3 rank26 (cap30); 3 each for n=4 rank47 (cap51) and n=5 rank95 (cap99). 48 runs, 210,000 proposals. Results:
- Isolated rank8: eager 1/5, lazy 5/5, hybrid 5/5 reach rank7. Eager can escape because its archive fills with rank9 candidates; unlike strictly monotone search, it is not prohibited from debt.
- n=3 rank26: eager and lazy 0/5; hybrid 1/5 reaches rank25, a verified improvement on our own seed, not on the known rank23 constructions.
- Published n=4 and n=5: no improvements in any policy.
These preliminary small-sample tests support conditional barrier escape but not a general efficiency claim. Larger instances do not yet show success. New rank25 witness saved in the held-out results.

Measured search overhead: total 484,980,945 feature membership tests across the 48 runs. Implement a symmetric WeakMap memoization of exact pair similarities, scoped to each trial and keyed by actual candidate object identities; no policy changes. Replay all 48, comparing every result field except similarity/membership counters. All match exactly, including witnesses and first-hit events. Membership tests fall to 74,078,574 (6.55x reduction in this specific operation count). Lazy 290,578,545→40,163,730; hybrid 188,685,459→28,197,903; eager unchanged 5,716,941. This is not a wall-time speedup claim, and equal proposals are still not matched total work. Next version must use a fixed charged work budget, larger held-out seeds and adaptive fitting schedules, and charge cache lookups, storage, verification and generation. More powerful structural moves independent of the incumbent remain necessary for the strict rank targets 22 and 37.

## Reproduction

From experiments/mmg-fusion-navigation, run node mmg015_lazy_fit.js; node mmg016_rank_barrier.js; node mmg016_escape.js; node mmg017_delayed_fit.js; node mmg017_cached_fit.js. Scripts source-pin earlier receipts through repository history, independently verify retained identities, and emit JSON. All runs executed in the local JS tool environment. Remote E-CPU execution and repository CI remain separate verification tasks. No improvement below 9/4 is claimed.
