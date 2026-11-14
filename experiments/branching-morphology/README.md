# Same Grammar, Different Canopies (BMO-001)

**Status:** independent generative-geometry experiment, 2026-11-14.  
**Question:** How much visible shape diversity appears when a branching grammar is held fixed and only its turning angle changes?

This is a deliberately separate exploration, unrelated to distributed computation or any other repository roadmap. The generated "plants" are mathematical line drawings, not physiological or ecological plant models.

## The controlled experiment

Start with the word `F`. Apply the same rewriting rule four times:

```
F -> F[+F]F[-F]F
```

Interpret the resulting string using a unit-step turtle, initially pointing upward:

- `F`: draw a line segment one unit long.
- `+` and `-`: turn by the specified angle.
- `[` and `]`: save and restore turtle position and orientation.

Run that *identical* expanded word at angles **12°, 20°, 30°, 42°, and 60°**. No random numbers, species names, physics engine, external data, or training set enter the generation. Segment count is **5⁴ = 625** for every specimen; the uninterrupted central path has 3⁴ = 81 unit steps.

Generate an SVG atlas and JSON measurements:

```bash
python experiments/branching-morphology/canopy.py \
  --svg canopies.svg --json measurements.json

python -m unittest discover -s experiments/branching-morphology -p 'test_*.py' -v
```

Python 3.11+ standard library only. Flags `--iterations` (integer 0–6) and `--angles` (one or more finite angles strictly between 0° and 90°) permit additional probes. SVG panels **fit each specimen independently** for comparison; their displayed sizes are not a common unit scale. Use the reported raw measurements to compare shape.

## Recorded observations

From a local Linux/CPython 3.13.5 run of the default experiment:

| Turn angle | Segments | Width | Height | Width / height | Convex-hull area | Hull / bounding box |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 12° | 625 | 13.715161 | 81 | 0.169323 | 582.008341 | 0.523894 |
| 20° | 625 | 21.964491 | 81 | 0.271167 | 936.635093 | 0.526459 |
| 30° | 625 | 30.696152 | 81 | 0.378965 | 1315.150888 | 0.528940 |
| 42° | 625 | 39.061574 | 81 | 0.482242 | 1666.086061 | 0.526578 |
| 60° | 625 | 46.765372 | 81 | 0.577350 | 1999.219645 | 0.527778 |

**Observation:** With this one grammar and finite parameter set, larger angles produce broader silhouettes while segment count and measured height are unchanged.

**Inference:** Distinct silhouettes need not imply different branching programs: geometric parameterization alone suffices for this example.

**Surprise, not a law:** The convex-hull fraction stays near 0.52–0.53 over these five angles. A separate exploratory probe at **75°** gives approximately **0.501** (four expansions), so the apparent near-invariance should **not** be generalized from the selected sweep. The convex hull also includes empty interior and is not a measure of foliage density.

The six local tests checked balanced expansion/count, invalid-input rejection, turtle stack restoration, a known hull, fixed-topology geometric variation, and same-process byte reproducibility of SVG/JSON. They do not constitute a proof of properties at arbitrary depths or parameter values.

## Files and evidence

- `canopy.py`: deterministic generator, hull/extent measurements, SVG and JSON outputs.
- `test_canopy.py`: standard-library behavioral tests.
- `results/default-measurements.json`: exact output record for the default parameters.
- `.github/workflows/branching-morphology.yml`: tests on two Python versions plus generated-artifact validation and downloadable SVG/JSON outputs.

## Unknowns and possible continuations

1. What remains invariant *exactly* under changes of angle, rather than in this finite sample? Separate mathematical statements about grammar from approximate floating-point geometry.
2. At which parameter values do segment crossings and canopy envelope changes create non-smooth shifts in the measurements?
3. Does a shape metric that *excludes* large empty interior (for example, sampled coverage at an explicitly stated resolution) tell a different story?
4. Can two distinct grammars yield near-identical silhouettes, and how should that ambiguity be assessed without relying on visual intuition alone?

Do not interpret this as evidence about actual botany, vascular structures, evolution, or natural growth processes. The aesthetic resemblance is an invitation to investigate, not validation.

## Exact follow-up: BMO-002

A special case admits a stronger result than the finite measurements above. At a **60°** turning angle, an integer triangular-lattice recurrence and a finite 25-point hull-containment certificate establish, by induction, that the canopy's **convex hull scales exactly by 3 at every expansion depth n ≥ 2**. Its hull/bounding-box fraction is exactly **19/36**, and its width/height ratio is exactly **1/√3**. This does not generalize to the other sampled angles.

See [Exact 60° lattice certificate](EXACT-LATTICE-60.md), [source](lattice60.py), and [independent reconstruction tests](test_lattice60.py). Run `python experiments/branching-morphology/lattice60.py` for the machine-readable certificate.

## Exact angle transitions: BMO-003

A second exact follow-up classifies **every convex-hull vertex change** over angles 0° < θ < 90° at *expansion depth two*. The six-vertex hull loses one extreme point at exactly **60°** and another at **arccos(1/4) ≈ 75.5225°**, leaving four extremes. [The phase diagram and algebraic certificate](EXACT-ANGLE-REGIMES.md) demonstrate that no other convex-hull changes occur in that scope: **390 rational-polynomial half-plane checks** and **15 strict-corner checks** certify all three continuous angle intervals without numerical sampling.

Run `python experiments/branching-morphology/angle_transitions.py` to regenerate the certificate. This does not classify internal segment crossings or higher expansion depths.

## Depth-three geometric transitions: BMO-004

The next self-directed investigation increases the grammar expansion depth from two to three. It finds **exactly three convex-hull transitions** on 0° < θ < 90°: a *new algebraic angle* `arccos((2+√46)/12) ≈ 42.9574°`, followed by the same two angles `60°` and `arccos(1/4)` identified at depth two. The hull changes from 7 to 6 to 5 to 4 vertices as θ increases.

The [BMO-004 proof note](EXACT-DEPTH3-REGIMES.md), [exact-arithmetic certificate](depth3_phase.py), and [independent tests](test_depth3_phase.py) use **2,772 half-plane certificates**, **22 convexity checks** and exact arithmetic in `Q(√46)` to cover the full angle intervals. The result is about the outer convex hull, not all internal branch intersections or higher depths. Run `python experiments/branching-morphology/depth3_phase.py` to recreate the exact certificate.

## BMO-005: Recursive depth-four proof and a cubic-angle transition

At depth four, a fourth exact convex-hull change appears at **arccos(rho) ≈ 29.465468°**, where `rho` is the unique root in `(0.87,0.88)` of `144c³−48c²−80c+11=0`. The depth-four hull changes through 8, 7, 6, 5 and 4 vertices as the angle increases. The three previously certified transitions persist at their earlier exact angles.

The [recursive proof note](EXACT-DEPTH4-RECURSIVE.md), [exact-arithmetic certificate](depth4_phase.py) and [tests](test_depth4_phase.py) avoid checking all 626 endpoints against every candidate hull edge. Instead, they transform **only the previously certified depth-three hull vertices** through the grammar's five affine copies. That reduces **23,162** endpoint/edge checks to **1,007** exact interval inequalities. The certificate covers every angle between 0° and 90° and includes a counterexample to a misleading floating-point scan: one purported extra vertex is provably collinear for all angles.

Run `python experiments/branching-morphology/depth4_phase.py` to reproduce the proof record. The branch retains the same independence from other research programs.

## BMO-006: Exact depth-five transitions and a quartic root

The same fixed grammar at **five expansions** has exactly five outer-hull transitions across 0° < θ < 90°. A new transition appears at **arccos(sigma) ≈ 22.309473247°**, where sigma is the unique root in (23/25,93/100) of `864c⁴−288c³−696c²+136c+65=0`. The four earlier transition angles remain, and the strict hull vertex count moves through **9, 8, 7, 6, 5, 4** as θ increases.

The [exact depth-five proof](EXACT-DEPTH5-RECURSIVE.md), [certificate program](depth5_phase.py), and [independent tests](test_depth5_phase.py) carry the previous depth's extreme vertices through five affine copies. Rather than testing all **3,126 endpoints** in every interval, only **16–36 inherited candidates** are needed. The all-angle certificate checks **1,659** exact containment inequalities and **54** strict convexity conditions (versus **168,804** naive containment checks), including rational, quadratic, cubic and quartic boundaries. This is a reduction in proof obligations, not a benchmark of runtime speed.

Run `python experiments/branching-morphology/depth5_phase.py` to generate a machine-readable certificate. The five-stage transition sequence is evidence for, but **not a proof of**, a universal n-transition law at depth n.

## BMO-007: All-future-depth hull stabilization

The earlier finite-depth sequence admits a rigorous **all-depth consequence**. The five-copy grammar has a scale-covariant convex-hull recurrence: if `H_(k+1)=3H_k` at a turning angle, every later hull scales by 3 again. Exact polynomial comparison of **15 inherited hull regimes** (89 extreme-vertex correspondences), backed by the BMO-003–006 interval certificates, proves

```text
H_n(theta) = 3^(n-4) H_4(theta)  for every n>=5,
whenever arccos(sigma) <= theta < 90 degrees,
```

where `sigma` is the depth-five quartic transition cosine (~0.925...). Hence all five previously certified transition angles persist in *every* future depth; **no new outer-hull transition can appear above ~22.30947°**. A strict exterior-point witness proves that the newest angle is also a persistent transition, without claiming its future vertex-count increment.

The independent [proof note](ALL-DEPTH-STABILIZATION.md), [executable prerequisite certificate](all_depth_law.py), and [tests](test_all_depth_law.py) also derive an exact recurrence for the collinearity of nested branch tips at every depth. The recurrence's first positive-angle zero decreases strictly and satisfies `n*theta_n -> pi/2` in radians. **Those roots at depths six and above are candidates, not yet proven exposed-hull transitions.**

Run `python experiments/branching-morphology/all_depth_law.py` to regenerate the exact finite premises and numerical candidate illustrations.

## BMO-008: The sixth exact hull transition and an enlarged all-depth sector

The next independent test confirms the predicted depth-six candidate is a **genuine exposed convex-hull transition** at `arccos(lambda) ≈ 17.917530204°`. Here `lambda` is the unique root of `5184c⁵−1728c⁴−5472c³+1248c²+1108c−97=0` in `(0.951,0.952)`. The depth-six hull has exactly six transition angles in 0° < θ < 90°, and its vertices progress through **10, 9, 8, 7, 6, 5, 4** as θ increases.

The [proof and boundary conditions](EXACT-DEPTH6-QUINTIC.md), [exact quintic certificate](depth6_phase.py), and [independent tests](test_depth6_phase.py) check **2,483 algebraic interval containment inequalities**, **73 strict corner conditions**, and all six exact boundary hulls. A direct full-endpoint certificate would require 1,140,698 containment inequalities. The local standard-library test suite passes **49/49**.

The exact inherited-hull identities also extend BMO-007's universal stabilization theorem: for **every** later depth `n≥6` and every `θ≥17.917530204°` (with θ<90°), `H_n(θ)=3^(n−5)H_5(θ)`. A strict exterior-tip witness proves the new angle remains a geometric transition for all future depths. This still does not prove an exact n-transition count at arbitrary depth.
