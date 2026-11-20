# TPP-005 — Selecting observations before retrieving their other expression

**Question:** Can an observer use one available expression of a physical
measurement to choose which *other* expressions to acquire, without seeing
their values in advance, then independently test the resulting inferred
relationship?

This experiment continues [TPP-004](../tactile-perception-calibration/README.md).
It also relates to the repository's established active-attention work:
[Trial 04](../description-to-realization/trials/trial-04-active-distinction-selection/README.md)
and [RIV-010](../reference-calibrated-evidence/RIV-010-README.md).
Those experiments already provide general finite observation selection and
value-of-information models. TPP-005 does not replace them: it tests a
**concrete read-only external provider acquisition policy**, preserving the
difference between "choosing what to inspect" and "actually requesting it."

## Observable process

A read-only observer makes the following series of requests to
[NOAA CO-OPS Data API](https://api.tidesandcurrents.noaa.gov/api/dev/):

1. Read one **complete elapsed UTC day** of station 9414290 water-level
   observations, MLLW datum, in **feet**. This is the available *input
   expression*.
2. Check and retain the received original bytes, provider quality flags,
   UTC timestamps, station, datum and the declared unit.
3. **Before reading any metric target**, select four target times by the
   feet-side values alone: the two input extrema plus two interior input
   quantiles. The plan includes a SHA-256 digest binding these choices to
   the input-source bytes.
4. Choose four other *chronologically spread* timestamps for genuinely
   withheld challenges; none can overlap with training.
5. Make **eight separately addressed metric NOAA HTTPS requests** for
   six-minute windows around exactly those timestamps. Every returned
   response has its own source URL, timestamped original bytes and SHA-256
   digest. A matching timestamp must actually be present. The adapter never
   substitutes a neighbor or a missing reading.
6. Fit an affine relation from the four selected metric pairs, using
   TPP-004's exact rational feasible-interval solver, **without consulting
   the official conversion factor**, then test four withheld pairs.
7. Replay the entire manifest, original response bytes, input-only plan,
   request contracts, fit and outcome. Altered, absent or contradictory
   evidence must not silently become a successful observation.

The plant here is a *real provider-reported environmental instrument*, not
the synthetic actuation fixture in TPP-001/002. The process does not
physically intervene in the ocean or independently establish the station's
measurement accuracy. Both units still come from **one provider**. NOAA's
preliminary `q=p` observations remain preliminary.

## Exact reason for the selection rule

For four training samples `(x_i, y_i)`, the TPP-004 relation is

```
y = a*x + b, with |y_i - (a*x_i + b)| <= epsilon
```

Eliminating the unknown intercept from any two observations with
`x_high > x_low` bounds the possible slope with an interval no wider
than `4*epsilon/(x_high-x_low)`.

Consequently, **choosing the two furthest-apart available input values
minimizes this particular two-point worst-case slope-width bound**, given
equal representation tolerance and equal cost *per target reading*.
Two additional input quantiles probe whether an affine relation remains
feasible across its range.

This rule is **not** a universal optimal experimental-design policy. It is
not a Bayesian information-gain calculation and does not minimize every
multi-observation cost or maximize the probability of finding
misspecification. After training, four time-spaced withheld probes seek
counterexamples instead of training the same law repeatedly.

The plan records the slope-width bound, a four-point chronological
baseline's bound (computed without any target values), and the complete
selection method. The baseline bound is a mathematical comparison under
declared conditions, **not** measured HTTP performance.

## Cost and provenance warning

This is a real selective-target-acquisition experiment, but *the NOAA
service is optimized for batched requests*. Reading all target data in one
request might take fewer **HTTP requests** than our eight fine-grained
queries. TPP-005 records **nine actual request attempts** on the live path:
one input-day request and eight target-window requests, together with
observed original response-body byte counts. It must not claim network,
energy, elapsed-time or transport-byte savings merely because fewer metric
measurements were returned. HTTP/TLS overhead and the provider's internal
work are not measured.

The derived relation is valid only relative to its model family, 0.001 m
representation tolerance, matched reference frame and the actual observed
data. It is not an authenticated calibration standard.

## Reproduction

No additional packages, Python 3.11 or later. From the repo root:

```bash
python -m unittest discover -s experiments/tactile-perception-acquisition -p 'test_*.py' -v
python experiments/tactile-perception-acquisition/selective_observer.py --live > tpp005-live.json
python experiments/tactile-perception-acquisition/selective_observer.py --replay tpp005-live.json
```

The live script attempts **one fixed previous UTC day** by default. It
can accept a specified fully elapsed day via `--day YYYYMMDD`. No current
or future observations are requested. The workflow runs a four-platform
offline test matrix and one bounded public HTTPS experiment. A successful
workflow job does not itself mean the provider supplied usable data:
the retained report includes explicit `heldout-consistent`, `falsified`,
`undetermined`, `invalid-evidence` or `invalid-plan` classifications.

Offline tests use synthetic NOAA-shaped response bodies transformed into
**simulated separate window responses**; they do not count as network
measurements. They check input-only selection, a non-affine heldout
counterexample, missing/changed provider data, exact replay, quality
mismatch, wrong request URL, tampered response and bounded request policy.

## Next question

A future experiment could compare **measured** costs for an entire batched
target-day request versus selective fine-grained requests, while verifying
that the same physical reference and provider revision are compared. It
could also use independently calibrated sources or controlled actuation to
investigate transferable physical response laws, rather than merely
different numerical expressions from one data service.
