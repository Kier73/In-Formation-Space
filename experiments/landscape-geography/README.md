# RRE-003 — The geography of ecological memory

2026-11-25. Builds conceptually on [RRE-002](https://github.com/Kier73/In-Formation-Space/pull/376) (source revision eb7f19c221513eaa86b381a7b0c3857b33dbd92c). The implementation is self-contained; the earlier PR need not be merged to run this experiment.

## Question and model

Can a locally transformed ecosystem spread through an otherwise homogeneous landscape after the disturbance ends? Does the spatial arrangement of the affected area or the width of connections determine whether the transformation persists?

Use 51 by 51 sites on a periodic square lattice. At each site, x is relative cover of a disturbance-favoured strategy and h is the associated soil conditioning coordinate. The RRE-002 local growth map is

    g_i = (1-m) sigmoid(logit(x_i) + b + d_i + k(2h_i-1)) + m/2
    x'_i = M_p(g)_i
    h'_i = M_q((1-r)h + r x')_i

where M_w(a)_i = (1-w)a_i + (w/4) sum over four nearest neighbours of a_j. A missing edge is replaced by a self-loop, so mixing is symmetric and conservative. m=.05, r=.2, k=.5, b=.04, p=.35, q=.08. Positive b mildly favours the disturbance-favoured strategy under normal conditions. Positive feedback nonetheless admits two spatially uniform equilibrium candidates: low .0738109597488908 and high .9368404925566124. Soil diffusion and seed dispersal are abstract mixing parameters, not field-estimated rates. Initial transformed sites have x=h=high, other sites x=h=low, except in the actual pulse trials which begin uniformly low. A site is called transformed if x>.5. These are relative cover fractions, not absolute biomass, species richness or calibrated ecology.

## Experiment A: patch size and shape

13 trials include four patch masks, seven barrier widths, no-feedback control and no-mixing control. Simulate 2,500 normal seasons. All mixing operations check conservation to 1e-8; graph symmetry and contrast assertions are checked. Save thresholded spatial maps at seasons 0,500,2500 and numeric trajectories.

| Initial shape | Initial transformed sites | Transformed area after 500 seasons | After 2500 |
|---|---:|---:|---:|
| Disk radius 4 | 49 | 0% | 0% |
| Disk radius 5 | 81 | 5.575% | 85.083% |
| 3 x 27 strip | 81 | 8.497% | 96.002% |
| Nine separated 3 x 3 fragments | 81 | 0% | 0% |

The equal-area masks have identical initial total plant cover and soil conditioning, but different futures. The strip outperformed the disk in this grid at this horizon. This is not a general shape ranking or a proof of critical radius. No mixing preserves the original transformed mask; removing feedback while retaining bias and mixing erases spatial heterogeneity and yields uniform cover ~.667526. The latter is NOT a transformation of the landscape through memory: the high share threshold alone cannot distinguish mechanisms.

## Experiment B: gate width and pinning

Separate the 26-column left and 25-column right regions, blocking the periodic east-west wrap and the central interface except for a centered opening. The north-south periodic connection remains. Both seed and soil transport use the same edges. Start a radius-7 disk (149 sites) in the left region. At 2500 seasons every gate case has all left sites transformed.

| Open interface edges | Right transformed area at 2500 | At 10000 (selected) |
|---:|---:|---:|
| 0 | 0% | not extended |
| 1 | 0% | 0% |
| 3 | 0% | 0% |
| 5 | .2353% | .2353% |
| 9 | 4.8627% | 100% |
| 15 | 28.3137% | not extended |
| 51 | 62.5882% | not extended |

For widths 1,3,5 the 10000-season max one-step residual is zero in floating-point arithmetic; width 5 supports three transformed sites just inside the right region but no spread across the region. Width 9 transforms the entire lattice, with zero floating-point residual by season 10000. This supports numerical pinning in narrow openings versus propagation in the wider opening for this parameter choice. It does not prove stability of the nonuniform fixed points, nor establish a universal critical width; widths 7 and other parameters are untested. Width 0 is disconnected, while width 1 is graph-connected yet does not propagate the transformed state.

## Experiment C: actual local pulse rather than initial equilibrium mask

Start every site at low equilibrium and apply d=1 only inside the circular region for 5 or 8 seasons, then remove forcing. Run to season 2500 (includes pulse). Disturbance is an abstract temporary log-fitness advantage, not a physical rainfall model.

| Radius | 5-season pulse: final transformed area | 8-season pulse |
|---:|---:|---:|
| 4 | 0% | 0% |
| 5 | 0% | 75.702% |
| 7 | 95.079% | 100% |
| 10 | 100% | 100% |

A sufficiently long pulse can create a spreading state, but a short pulse in the same area can disappear. Results at 2500 are finite-time outcomes, some still evolving (see residuals). Actual pulses do not require manually placing fully transformed equilibrium states.

## Reproduce

    node experiment.mjs > reproduced.json
    node followup.mjs > reproduced-followup.json
    diff -u results.json reproduced.json
    diff -u followup.json reproduced-followup.json

Both functions executed in a hosted JavaScript isolate, producing committed JSON. Exploratory NumPy calculations in a separate local Python container also reproduced the primary area and corridor contrasts; that preliminary script is not included, and is not independent human replication. Node CLI and repository CI were not executed. Minor cross-engine floating-point differences may occur. [Main output](results.json), [extended output](followup.json).

## Open exploration

Assumed positive feedback and deterministic mixing produce conditional results, not actual landscape management advice. Thresholded relative abundance is not biodiversity. No calibrated dispersal, soil ecology, water, succession, stochastic dynamics, climate variability, or absolute density. Width and radius are lattice units, not real distances. Future experiments: test finite perturbations around pinned interfaces, independently vary soil versus seed permeability, explore randomly spaced stepping-stone patches and habitat heterogeneity, and study the effect of dispersal range. The interesting question is whether selective connectivity can permit recolonization without allowing a persistent disturbance-driven transition to propagate. A later model could add explicit competition and species diversity before interpreting this ecologically.
