# RRE-002 — The memory of a landscape

2026-11-25. Independent continuation of [RRE-001](https://github.com/Kier73/In-Formation-Space/pull/375); this is a new phenomenological model, not an extension of its water-balance equations. Empirical context: [plant–soil feedback and drought legacies](https://doi.org/10.1111/nph.14661), [soil versus plant legacy transplant experiment](https://doi.org/10.1111/nph.19291), and [persistent microbial drought memory](https://pmc.ncbi.nlm.nih.gov/articles/PMC11383273/). No field data fitted.

## Question

Can the interaction of vegetation and soil retain a drought history even when neither compartment alone is sufficient to produce a lasting change? Distinguish transient recovery from convergence to a different locally stable equilibrium under the same post-disturbance forcing.

## Model

x is relative cover of the drought-favoured strategy, h is a dimensionless soil conditioning coordinate favouring that strategy. Both lie in (0,1). One season maps

    x' = (1-m) sigmoid(logit(x) + b + d + k(2h-1)) + m/2
    h' = (1-r)h + r x'

where immigration/recruitment mixing m=0.05, soil response r=0.2, k is positive feedback, b is normal environmental preference, d is a temporary drought-induced log fitness advantage (not rainfall or measured drought intensity). Normal recovery sets d=0. Both strategies are present, and total cover is normalized, not productivity. Soil has no direct drought forcing in this toy model.

Sweep k in {0,.06,.10,.12,.25,.5,1}, b in {-.04,0,.04}, pulse magnitude d in {.25,.5,1,1.5,2}, and duration in {1,2,3,5} seasons: 420 pulse trials. Each of 21 parameter cells starts from equilibrated low and high initial states (.1,.1) and (.9,.9); the pulses start at the low-initialization endpoint. Recovery and initial equilibration run 20,000 seasons. Switching is defined operationally: initial equilibrated cover gap > .05 and final state within 1e-7 of high endpoint in max norm. Fixed point residual checked to 1e-7 for all grid endpoints. An initial 2,000-season run failed the stationarity check; increased horizon, not relaxed tolerance. Final residuals are zero in floating-point arithmetic, not exact real-number certificates.

## Results

At b=0, k=.5, the low and high equilibria are x=h=0.067883820906339 and 0.932116179093661. Separate bisection of fixed-point equation and Jacobian calculation yield eigenvalues (0.836219,0.619108) at either outer point; the center (.5,.5) has eigenvalues (1.117271,0.680229). These establish local asymptotic stability of the outer numerical roots (with margins far from 1) and instability of the central point, not global basin geometry.

For the symmetric center, let A=1-m and B=k(1-m)/2. The Jacobian is [[A,B],[rA,1-r+rB]]. Its characteristic polynomial evaluated at 1 is r(1-A-B); an eigenvalue crosses 1 at k=2m/(1-m)=0.105263..., independent of r>0. This is a local stability threshold, not a proof of the complete global bifurcation diagram. At k=.1, b=0 both initialized trajectories converge to .5; at k=.12, b=0 they converge to .3293 and .6707. A normal preference of +/- .04 removes the observed two-endpoint distinction at k=.12. Stronger feedback maintains larger gaps but makes some pulses less able to switch the initial landscape.

Most revealing pair (k=.5, b=0):

| Pulse | Post-drought cover | Post-drought soil | Cover after 150 normal seasons |
|---|---:|---:|---:|
| d=1 for 5 seasons | .684884 | .323504 | .932116 |
| d=1.5 for 3 seasons | .685526 | .263139 | .067884 |

These are near-matched cover histories (difference .000642), selected after the sweep, not preregistered. For the first pulse, virtual common-garden transplants reset either x or h to low equilibrium while preserving the other post-drought coordinate. Both reset cases return to .067884, while the intact pair approaches .932116. Thus in this particular pair of interventions neither retained coordinate alone is sufficient to switch; the joint initial state is sufficient. Other tested stronger pulses switch even with soil reset, so the result is conditional, not a universal assertion of distributed memory. The no-feedback null control eventually returns to .5 after a strong pulse.

## Reproduce

    node experiment.mjs > reproduced.json
    node stability.mjs > reproduced-stability.json
    diff -u results.json reproduced.json
    diff -u stability.json reproduced-stability.json

Both JS functions were executed in a hosted JS isolate; saved source serializes the functions and prints JSON. Node CLI and repo-wide CI were not run. Minor rounding differences may occur. [Sweep](results.json), [stability and transplants](stability.json).

## Limits and further directions

Positive plant-soil feedback is assumed, not discovered in a field. This is not calibrated, has only two relative cover strategies, no absolute abundance, explicit water, direct microbial dynamics, seed banks, spatial structure, stochastic extinction, or realistic time scale. Local numerical stability is not proof of robustness to arbitrary perturbations. The next substantive challenge is to introduce spatial dispersal and soil diffusion, then ask whether a small disturbed region can invade a recovered landscape, and whether patch geometry or corridors alter persistence. That can be tested against a no-feedback null and a homogeneous landscape. Keep these questions independent of the other repository programmes.
