# RRE-004 — The ecology of selective connectivity

2026-11-25. Independent continuation of [RRE-003](https://github.com/Kier73/In-Formation-Space/pull/377), source e6bdf97849a5e96a9a2b7dbb20fee005383a67b4. This experiment reduces geography to two equal-sized habitats and adds a third plant strategy.

## Question

Can exchange restore a locally absent species without homogenizing the two communities? Can intermittent exchange improve the trade-off, and does that conclusion survive inspection of every phase of the exchange cycle?

## Model

Each habitat has relative abundances A, B, C summing to one, and soil conditioning h in [0,1]. Let v=b+k(2h-1), b=.04, k=.5. Unnormalized growth is A exp(-v/2), B exp(v/2), C exp(a-1.5C), with a=.35 unless varied. Normalize all three; then mix 5% of the combined A/B share equally between A and B. C has no spontaneous recruitment, so exactly absent C needs seed exchange to return. Symmetric seed exchange p mixes the post-growth relative abundances between equal-sized habitats. Soil then approaches B/(A+B) at rate r=.2, followed by symmetric soil exchange q. Parameters are illustrative and no physical units or field calibration are implied.

Initial states arise by equilibrating isolated habitats from opposite plant-soil histories for 5000 seasons, then removing C entirely from the receiving habitat and renormalizing A/B there. The donor starts with C=.0905501 and the receiver before removal had C=.120557. The donor is B-dominated, the receiver A-dominated. No drought forcing is applied in this study.

Success is deliberately operational: receiving C>=.1, receiving B/(A+B)<.25, and donor B/(A+B)>.75. This is not a universal ecological success definition. Measure Shannon effective alpha diversity exp(mean local entropy), gamma diversity exp(entropy of pooled composition), multiplicative beta=gamma/alpha, and Bray-Curtis dissimilarity (half L1 distance for normalized compositions). Neither relative cover nor effective diversity estimates absolute abundance or extinction risk.

## Static exchange grid

81 combinations, p,q independently in {0,.001,.003,.01,.03,.06,.1,.2,.3}; 5000 seasons. All endpoint max one-step residuals <=1.12e-16; every step checks state validity and conservation of each species during the exchange substep, plus conservation of soil conditioning during its exchange substep. 19 combinations meet the success criterion.

| Seed p | Soil q | Receiver C | Receiver B/(A+B) | Effective gamma | Bray-Curtis |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | .073811 | 2.32958 | .86875 |
| .01 | 0 | .136075 | .108172 | 2.65889 | .72195 |
| .01 | .06 | .090550 | .936840 | 1.67875 | 0 |
| .1 | 0 | .090550 | .936840 | 1.67875 | 0 |
| 0 | .1 | 0 | .936840 | 1.50572 | .09055 |

Moderate seed exchange with low soil exchange can restore the third species and preserve distinct A/B histories. High seed exchange alone can homogenize the two habitats; strong soil exchange alone can propagate B dominance without restoring the missing C. The fastest successful static configuration in this grid reaches C=.1 at season 15 (p=.03,q=0,.001,.003); these are grid observations, not an optimization proof.

Sensitivity: four C growth advantages .30,.35,.40,.50 crossed with four representative p,q settings. At p=.01,q=.003 every tested advantage passes; p=.003,q=.003 fails at a=.30 (C=.0965). At p=.01,q=.06 every tested advantage fails distinct-history criterion. This establishes conditional robustness across this small grid only.

## Temporal connectivity: endpoint trap and complete-cycle audit

Initial schedules hold q=.003 and arithmetic mean p=.01; open seed exchange once every P seasons at p=.01P, with no seed exchange on intervening seasons. P in {1,2,5,10,20,50}. A first endpoint-only comparison at season 5000 incorrectly suggests that all six schedules meet the success criterion at all times. In fact the reported endpoint is just one phase; it cannot establish whole-cycle persistence. Equal arithmetic mean mixing fractions also do not imply equal cumulative transport of individual seeds or equal ecological effects.

The separate schedule-audit.mjs enumerates all 88 starting phases, checks the difference between phase-matched states one full period apart, and measures worst-case late-cycle abundances and dissimilarity. All phase-matched residuals zero in floating point. Times are seasons from removal; first and sustained >=.1 crossing agree within the simulated horizon for each tested phase.

| Period | First recovery range | Minimum C over late cycle | Maximum receiver B/(A+B) | Minimum donor B/(A+B) | Minimum dissimilarity | All phases/all cycle pass |
|---:|---:|---:|---:|---:|---:|:---|
| 1 | 22 | .14112 | .11184 | .91052 | .71368 | yes |
| 2 | 22–23 | .14098 | .11709 | .90551 | .70451 | yes |
| 5 | 20–24 | .13999 | .13550 | .88735 | .67220 | yes |
| 10 | 18–27 | .13672 | .17234 | .85039 | .60759 | yes |
| 20 | 15–33 | .12783 | .25513 | .76854 | .46268 | no |
| 50 | 5–54 | .11107 | .51327 | .51327 | 0 | no |

At P=50, exchange of exactly 50% between two equal habitats makes the two plant compositions identical immediately after the exchange (soil remains distinct). The communities subsequently differentiate again. Thus a snapshot shortly before opening can overstate their persistent distinctness. Pulsed schedules can achieve earlier recovery for some opening phases but have worse worst-case waiting times and transiently reduce distinction. Continuous exchange has the best worst-case first recovery time among these schedules. There is no general ranking implied outside this grid.

## Reproduction

    node experiment.mjs > reproduced.json
    node schedule-audit.mjs > reproduced-audit.json
    diff -u results.json reproduced.json
    diff -u schedule-audit.json reproduced-audit.json

Both functions were actually executed in the hosted JavaScript isolate; the committed .mjs files contain the serialized functions plus JSON-printing statements. Node CLI and repository CI not run; tolerate tiny engine-dependent rounding. No external dependencies. [Main results](results.json), [cycle audit](schedule-audit.json).

## Interpretation and further exploration

This is an illustrative deterministic relative-abundance model, not a calibrated conservation intervention. The negative frequency dependence of C, positive A/B soil feedback, immigration mixing and symmetric exchange are assumptions; a two-habitat system does not represent network topology. Success thresholds were chosen for this model. The phase audit corrects an overinterpretation of the first experiment, not a software failure. The next direction worth pursuing is to replace two habitats with a diverse network, allow dispersal traits to differ among species, and test whether time-varying connectivity can preserve rare populations under asynchronous disturbance without synchronizing their risks. Include matched total exchange controls, phase-complete evaluation, and stochastic extinction with explicit absolute populations before making ecological claims.
