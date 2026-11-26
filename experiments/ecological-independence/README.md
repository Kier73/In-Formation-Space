# RRE-005 — Ecological independence

2026-11-25. Continuation of [RRE-004](https://github.com/Kier73/In-Formation-Space/pull/378) (the prior PR is not required to run this experiment). The previous deterministic relative-abundance model is replaced with stochastic integer populations and absorbing regional extinction.

## Model and methods

12 habitats form an undirected ring. Every habitat has 32 recruitment opportunities each season. Begin with 16 individuals at each site (192 total). Adults are replaced by the new generation. A local individual contributes reproductive intensity R=3.2 in favourable habitat or .75 otherwise. Drought multiplies R by .18. Each slot is independently occupied with probability 1-exp(-R n/32), where n is local population before reproduction. Recruits subsequently move one edge left/right with probabilities p/2 each or remain with probability 1-p. The 32 slots limit local births, not the count after immigration. Total births conserved during movement; no spontaneous immigration. A region with zero individuals remains empty.

Weather starts wet. Each season, a wet site becomes dry with probability .15, while a dry site remains dry with probability .65. With probability rho all sites use the same uniform random draw for their transitions; otherwise each uses a site-specific independent draw. This preserves the marginal transition probabilities while inducing shared shocks, not a literal Pearson correlation rho. Separate seeded pseudorandom streams for weather and recruitment/dispersal; same weather seed across paired parameter settings and fixed numbers of random draws per active season. Uniform, alternating (even sites favourable) and clustered (first six favourable) layouts are compared. Heterogeneous layouts have identical counts of good and poor sites. One replicate is a 120-season trajectory, stopped on absorbing regional extinction; later population counts are zero. Local rescue is a site that was empty and becomes occupied in one season, not proof of long-term persistence.

Main experiment: 3 layouts x 2 weather-sharing values (0,.5) x 5 dispersal probabilities (0,.08,.2,.7,1) x 180 replicates = 5,400. Six habitat-retention controls x 180 = 1,080. Retention rejects 90% of attempted moves from good to poor habitat; movement into good habitat and other movements unchanged. The test changes realized dispersal as well as habitat selectivity; a matched realized movement control remains open. Replicate IDs 1000..1179, distinct from preliminary pilot. Report extinction times (null means alive at horizon), survival, mean abundance including extinct trajectories, local losses and rescue counts, and pointwise Wilson 95% intervals. Intervals do not adjust for grid comparisons. No claim of zero true extinction probability from zero observed events.

## Results: regional survival

Shared weather rho=.5; survivors of 180 by season 120:

| p | Uniform | Alternating | Clustered |
|---:|---:|---:|---:|
| 0 | 85 | 59 | 52 |
| .08 | 180 | 80 | 169 |
| .2 | 179 | 98 | 162 |
| .7 | 176 | 27 | 154 |
| 1 | 177 | 5 | 146 |

In the alternating arrangement with shared weather, regional extinction increases from 82/180 (95% Wilson 38.45–52.85%) at p=.2 to 153/180 (79.06–89.48%) at p=.7 and 175/180 (93.66–98.81%) at p=1. Mean local rescue events per trajectory at p=1 are 76.57, versus 34.26 at p=.2. Local recolonization alone is a poor proxy for regional survival in this case; at p=1 all offspring must move to the opposite habitat quality on an alternating ring. The extreme p=1 also creates a period-two movement structure. The deterioration already appears at p=.7 with a nonzero stay probability. With independent weather the corresponding alternating extinction counts are 5/180 at p=.2, 4/180 at .7, 113/180 at 1. Shared weather and arrangement interact with dispersal.

Habitat-selective retention at rho=.5 reduces alternating extinction from 153 to 47/180 at p=.7 and 175 to 41/180 at p=1. At p=.2 it increases extinction from 82 to 87/180, so not every setting benefits. In an alternating ring good-to-poor moves are all outgoing moves from a good site. Retention may improve persistence by retaining source populations, not by creating more connectivity.

## Two-species competition

Separate script allocates the same 32 recruitment slots to two complementary specialists. Each begins with eight individuals per habitat. Recruitment occupancy probability uses the sum of species-specific reproductive intensities; a recruit's identity is chosen proportional to these intensities. Opposite species favour opposite habitat types. No immigration, species extinctions absorbing. New demographic seed stream, replicate IDs 2000..2119. 16 grid configurations and 3 retention controls x120 = 2,280 trials. Both species share weather and local recruitment slots.

Shared weather rho=.5:

| p | Both species persist: alternating | Both persist: clustered | Both persist: alternating with retention |
|---:|---:|---:|---:|
| .08 | 29/120 | 104/120 | not tested |
| .2 | 25/120 | 107/120 | 39/120 |
| .7 | 4/120 | 102/120 | 76/120 |
| 1 | 0/120 | 87/120 | 75/120 |

At p=1, 119/120 alternating unbiased trials lose both species, versus 14/120 with retention. The selective rule is an imposed trait, not an evolved or learned adaptation. In clustered habitat under independent weather both species persist in all 120 trials at each of four sampled p values. These are finite-horizon outcomes, not infinite-time survival guarantees.

## Reproduction

    node experiment.mjs > reproduced.json
    node competition.mjs > reproduced-competition.json
    diff -u results.json reproduced.json
    diff -u competition.json reproduced-competition.json

The functions were executed in a hosted JavaScript isolate and their serialized source and recorded JSON are committed. Preliminary pilot runs guided the parameter grid; two larger planned runs exceeded the execution window and are not counted as completed evidence. The reduced independent-seed main and competition experiments finished (8,760 total recorded trials). Node CLI and repo-wide CI unverified. No dependencies. Small engine rounding variation possible. The raw extinction times allow independent survival-count reconstruction.

## Interpretation and next question

This is a simplified non-overlapping-generation model, not calibrated ecological prediction. Environmental sharing is imposed, and population synchrony was not measured; the results demonstrate sensitivity to correlated disturbance, habitat topology and movement, not that dispersal causes synchronized fluctuations. No direct soil dynamics or rainfall physics here. The strongest contrast suggests that protecting source habitat and direction-selective movement may matter. Next: compare matched realized dispersal rates and move decisions based on imperfect local signals, then allow traits to mutate and measure whether selection for individual fitness improves or undermines regional coexistence. Track actual population synchrony and finite-horizon persistence separately.
