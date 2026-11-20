# TPP-003 — Tactile perception through public instrument observations

**Question:** Can a physical sensor's reported observation survive two *informational* expressions—metric and English water levels—while retaining the evidence needed to distinguish measurement, interpretation, quality status, absence, and contradiction?

This follows [TPP-001](../tactile-perception-process/README.md) and [TPP-002](../tactile-perception-discovery/README.md). Unlike those synthetic plant fixtures, this adapter can make **real read-only HTTPS requests** for a public environmental sensor service. It never actuates that sensor, verifies a sensor physically, or changes external state.

## Actual observation source

[NOAA CO-OPS Data API](https://api.tidesandcurrents.noaa.gov/api/dev/) serves public water-level station observations. This experiment uses station **9414290 (San Francisco)**, product `water_level`, reference datum `MLLW`, UTC/GMT times and a bounded recent/latest query window. The provider's [response documentation](https://api.tidesandcurrents.noaa.gov/api/dev/responseHelp.html) identifies:

- `t`: observation time;
- `v`: measured water level;
- `s`: standard deviation of one-second samples contributing to the reported value (**not** a complete measurement-uncertainty certificate);
- `f`: raw flags, whose interpretation differs between preliminary and verified records;
- `q`: provider's quality status, `p` (preliminary) or `v` (verified).

This adapter **preserves** these values. Provider-verified does not mean independently authenticated, error-free or independently reconstructed by this experiment. Preliminary data is not silently promoted to verified.

## Translation contract

The same station/datum/timestamp may be requested in meters and feet. Using the internationally defined conversion

`1 foot = 0.3048 meters`,

a matched pair is compared only when station identity, product, temporal reference, and datum agree. The comparison allows **0.001 m** difference for separate 0.001-resolution representations, and preserves the greatest observed deviation and earliest contradiction.

That tolerance tests **representation agreement**, not whether the underlying instrument was accurate. Both requests are to *the same provider*; they are not independent physical measurements. Responses may have changed between requests.

No overlap, no records, invalid data, an unapproved endpoint, or a network failure yields an explicit undetermined/unavailable/invalid result, never a fabricated measurement. Missing values remain null. Duplicate timestamps fail closed rather than being silently merged. A mismatched datum cannot be compared as though it were an equivalent physical reference.

Each report records the request URL, fetch timestamp, **base64-encoded exact source bytes**, SHA-256 of those bytes, source station, unit, datum, provider flags and observed timestamps. The separate [independent replay checker](independent_replay.py) reconstructs the parsed readings and cross-unit comparison directly from those archived bytes, without importing the producing adapter. Hashes bind bytes but do **not** sign the sensor or establish origin independently of HTTPS and provider metadata.

## Reproduce

Offline conformance tests require only Python's standard library and make **no HTTP calls**:

```bash
python -m unittest discover -s experiments/tactile-perception-observations -p 'test_*.py' -v
```

For an actual read-only external observation, run:

```bash
python experiments/tactile-perception-observations/noaa_bridge.py --live --date recent
```

The CI workflow exercises offline tests across Linux/Windows and Python 3.11/3.13. A separate live-data workflow job attempts the HTTPS requests, runs the independent replay checker on the resulting JSON, and uploads the archived original payloads and parsed observations as a GitHub Actions artifact. This can report `unavailable` when the provider is down; such a result is **not** an observed measurement.

## Discriminating offline counterexamples

The 21 offline test methods (14 adapter tests and 7 independent-replay tests) demonstrate that:

- two matching timestamped provider expressions can agree within a declared conversion tolerance;
- a large discrepancy is retained as **contradicted**, rather than rounded away;
- a different datum, units, or station cannot be silently identified as equivalent;
- provider status and flags stay associated with the exact reported reading;
- missing, empty, malformed, duplicated or denied data cannot become zero;
- changing a value changes its byte digest, but a new hash is not an independently authenticated physical observation.

These tests validate the adapter's behavior on synthetic NOAA-shaped response fixtures. The optional live run is the distinct evidence for any real external feed.

## Next questions

1. Obtain a genuinely **independent** co-located instrument with overlapping times and a common calibration datum; compare the physical observations only after calibration evidence is admitted.
2. Preserve corrections and superseded public observations as versioned events instead of treating a changed provider response as a contradiction of nature.
3. Use controlled, authorized physical perturbations and independent calibrated sensing to test whether an inferred cause–response relationship survives changes in actuation and observation medium.

The experiment deliberately does not claim any of those three as completed.
