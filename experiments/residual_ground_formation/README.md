# CLT-003 — Residual Ground formation

A previously acquired collection of computational laws can reveal a representation of how laws vary. CLT-002 enumerated transformed candidate laws and found that allowing arbitrary one-cell changes destroys its conditional query advantage. This experiment replaces enumerated possibilities with a discovered GF(2) linear space of nonlinear residual functions.

## Construction

On 256 input coordinates, let f0 be a known nonlinear baseline and let r=f XOR f0. The fixture oracle evaluates a private polynomial (distinct Boolean monomials, including products of multiple input bits). The learner is not given its monomials, coefficient masks, or a degree prior. It acquires 18 complete source laws and incrementally eliminates residual vectors over GF(2). The resulting rank-12 basis comes from actual acquired function values. The target sources are distinct coefficient combinations not used in training. Three additional individually audited target laws expand the atlas to rank 15; test on 128 fresh combinations thereafter. All are generated from the same declared fixture, not natural pretrained models.

For residual basis vectors b_j in GF(2)^256, let B[x,j]=b_j(x). A set S of coordinate probes identifies a candidate in the span iff rank(B[S,:])=r. At least r binary scalar probes are necessary in the worst case. Greedily select the cheapest independent rows, sorted by declared positive cost: linear independence is a matroid, so this minimizes additive cost among full-rank coordinate bases. Solve the observed residual values for basis coefficients by exact GF(2) elimination, then realize the candidate across the domain. Compare with first-independent (coordinate order) selection.

The family has 2^r members but the learner stores r vectors, without enumerating candidates. This is standard linear algebra and matroid optimization; the integration question is whether *prior observed computations* form a useful residual Ground and permit efficient subsequent acquisition.

## Admission, counterexample and accounting

A prediction is conditional on membership in the learned span. An independent full-domain audit queries every remaining coordinate, reuses actual probe values (not predicted values) and compares all outputs. A hidden single-point mutation is rejected. Three out-of-span laws are likewise rejected before their fully observed residuals expand the atlas. Only acquired source tables update the basis. The admitted candidate is exact on this finite source table; no origin authentication or independently established family contract is implied.

Record acquisition counts and declared weighted source costs separately from basis formation XOR operations, planning basis reads/reductions, and per-query solve/reconstruction work. Not all CPU operations, wall clock, storage, verification or communication are priced. The known baseline is supplied; its acquisition is excluded from both compared methods. Conditional break-even counts amortize initial/expanded acquisitions assuming future in-span sources and an independently qualified family contract; unrestricted complete audit eliminates the source-read savings. They are not end-to-end speedups.

## Run

```sh
node experiments/residual_ground_formation/clt003.js
```

The exact same JS function was executed in the available tool runtime before committing results.json. CI independently runs the committed script and compares its JSON to that file. No external dependencies or native E-CPU execution are asserted by this round.

## Next

Discover residual families under varying base laws, challenge rank growth under nonlinear composition, represent sparse basis vectors symbolically instead of storing full tables, and qualify source family membership independently of complete source measurement. Connect the existing E-CPU/VGI observation-authority path only after establishing what the family contract proves.

Prior: [CLT-002](https://github.com/Kier73/In-Formation-Space/pull/381).
