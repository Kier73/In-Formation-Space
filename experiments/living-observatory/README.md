# The Living Observatory — LO-001

An independent experimental notebook for studying how observations become questions, how alternative ecological explanations are distinguished, and when a scientific instrument should admit that its explanations are insufficient.

## First question
Why does oxygen demand appear to increase during a bloom? Live algae respiration, detrital decomposition and a temperature-associated mechanism may all predict the same observed trend. A correlation need not select among these explanations.

This is a **synthetic counterexample and experimental-design sandbox**, not a validated pond model. Standardized integer indices for live algae, detritus and temperature are not physical units; demand is an abstract response, not dissolved oxygen in mg/L. No live organisms, field measurements, real-world intervention advice or private user data. The six candidate laws and three omitted mechanisms are deliberately constructed. No outside sources or existing Virtual Layer implementations are used.

## What runs
The simulator hides its generating law from the observer. Eight passive observations vary all three indices together, so every candidate has the same predicted response. Independent paired experiments contrast a treated microcosm with a matched control in a simplified static structural model. Each reading has integer noise -1/0/1 with probabilities 1/4, 1/2, 1/4. Paired differences therefore have noise -2..2 with weights 1,4,6,4,1 over 16. Uniform prior on six candidate laws, exact finite likelihood support, normalized floating-point posterior. Adaptive policy selects expected entropy reduction per declared intervention cost; balanced cyclic, fixed single-intervention, random and passive comparators share the same maximum exploration budget of 8. All stop when one or zero candidate laws survives. Four additional reserved audit actions, cost 8 total, are common to every policy and are not used to select exploration experiments.

Each notebook preserves the observed control and treatment, contrast, candidate predictions, information score, belief before/after and a new question. It records "unresolved", "one-model-survives" or "model-library-rejected"; no surviving model is claimed true outside the candidate set and measurement assumptions. A rejection is absorbing until a future model-library revision. Replay checks recorded contrast arithmetic and belief transitions, not external measurement authenticity.

## Reproduce
Node.js 22, no dependencies: `node experiments/living-observatory/observatory.js > /tmp/lo.json`; compare to evidence.json. Executed in a hosted JavaScript isolate; CI will reproduce on Linux and Windows. 9 simulated worlds × 40 seeds × 5 policies = 1,800 sessions. The audit uses its own random stream, yielding identical reserved measurements for the same world and seed across all policies. Seeded measurements and actions. Truth label recorded only in evaluation, not passed into observer. Known truth is never eliminated, all observational records leave six candidates, budget enforced, every retained notebook replayed; tampered contrast refused. Noise and outcomes deterministic per seed, not a random population sample. Experimental cost units are invented and equal across policies; not scientific field costs.

## Results
| Policy | Unique correct known model before audit / 240 | After audit / 240 | Outside library rejected / 120 | Mean exploration cost |
|---|---:|---:|---:|---:|
| adaptive | 186 | 235 | 80 | 4.758333 |
| balanced | 122 | 202 | 80 | 5.358333 |
| random | 97 | 209 | 80 | 6.405556 |
| fixed | 39 | 234 | 80 | 6.125 |
| passive | 0 | 122 | 80 | 8 |

The threshold counterexample agrees with a candidate for every offered intervention, including reserved audits, and cannot be identified without changing the observation regime. This is intentional: successful prediction is not sufficient evidence that the model library is complete. A deliberately expanded context (detritus-index contrast +4, outside the original menu) then rejects all surviving candidate laws in 40/40 threshold-world repetitions. The expansion was chosen by the developer with knowledge of the synthetic hidden threshold; it is a prospective coverage demonstration, not autonomous discovery of a missing law, and is excluded from policy comparison. Compare individual world results and sample notebooks in evidence.json.

## Next inquiries
- Replace the static simulator with a mass-balanced nutrient/algae/grazer/decomposer system, separate sampling error from process variation, and test against independently specified dynamics.
- Introduce uncertain and unknown sensor calibration, correlated disturbances, realistic constraints on interventions, longitudinal sampling and experimental replication.
- Preserve a proposal log of competing mechanisms; use fresh observations to discriminate additions rather than refitting and declaring old data independent confirmation.
- Consider an eventual passive real-data adapter (open environmental datasets, documented units and provenance) only after defining what observations can actually support. No live intervention is required.

This project is not tied to the existing computation research. Its success is measured by better questions and justified uncertainty, not by a universal theory.
