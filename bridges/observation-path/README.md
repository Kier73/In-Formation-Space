# Bridge: Evidence-gated observation path

**Status:** experimental protocol model.  
**Purpose:** preserve the difference between selecting an observation, sending a request, receiver admission, returned raw data, interpretation, and query resolution.

## Why this bridge exists

Trials 04–06 choose which observations would be useful. They do not execute those observations. A real communication path has additional stages, and collapsing them creates false evidence:

- A plan is not a dispatch.
- A successful dispatch is not receiver admission.
- Receiver admission is not a returned measurement.
- A timeout or rejection is not a negative sensor reading.
- A raw return is not yet an interpretation.
- A query determined over a supplied hypothesis set is not automatically a universal fact about the external world.

## Lifecycle

    planned -> dispatched -> admitted -> returned -> interpreted -> query_determined
         |          |           |           |              |
         v          v           v           v              v
    dispatch_failed  rejected  no_result  returned_unadmitted  unresolved
                           (unadmitted return and other failures are terminal)

Each attempt is append-only. Failure paths are terminal and do not silently become observations. A payload that returns without an admission receipt is preserved as `returned_unadmitted` and cannot advance to interpretation within that attempt.

## Evidence and clocks

Dispatch, admission, return, interpretation, and query-resolution events can each reference their own receipt or artifact. A returned payload must reference an Encounter Envelope and include its encounter ID, payload digest, and declared canonicalization. The path ledger records those declarations; it does not fetch or authenticate the referenced artifact. The Encounter Envelope validator remains responsible for validating the referenced envelope when it is available.

Clock values are retained only alongside their clock-domain labels. The path model does not subtract or align values from different domains. Unknown timing remains unknown.

## Query resolution boundary

The terminal `query_determined` stage requires a Boolean result, the hypothesis-set digest against which it was derived, and a basis reference. This means the query was resolved relative to that stated hypothesis set and evidence basis. It does not claim that the hypothesis set is exhaustive or that the result is a universal property of the external system.

## Files

- `observation_path.py` — append-only state machine and JSON export.
- `test_observation_path.py` — tests for legal transitions, provenance, rejection/no-result distinctions, clock domains, and immutable detail snapshots.

## Reproduce

    python -m unittest discover -s bridges/observation-path -p 'test_*.py' -v