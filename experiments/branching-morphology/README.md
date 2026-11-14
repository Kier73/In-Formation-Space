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
