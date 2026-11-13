# DFR-001: Decision-time evidence frontier

**Status:** finite reference model, version 0.1.  
**Question:** Can an independent verifier reconstruct which messages a receiver had recorded as admitted at a particular decision, without treating source-send precedence as proof of receiver knowledge?

## Why this is a separate question

MOR-001 and MOR-002 reconstruct causal relationships between event stamps. MRE-005 models delayed and out-of-order sensor reports. ObservationPath separately distinguishes dispatch, receiver admission, return, authorization, interpretation, and ACK progress.

The missing composition is the receiver's *decision-time evidence frontier*.

A source may send message m1, then send m2. The send of m1 can be causally before a later receiver decision even when m1 has not yet been admitted by the receiver. A vector-clock relation establishes causal precedence; it does not establish delivery, admission, or use.

This experiment keeps four claims distinct:

1. **Sent:** the source event log contains a message and its source causal stamp.
2. **Admitted:** the receiver log contains the corresponding intake event.
3. **Available at decision:** the intake is within the complete receiver-log prefix named by the decision.
4. **Used:** the controller's decision record declares that it used the evidence. This remains a claim about the controller's computation, not something a hash chain alone can prove.

## Discriminating schedule

Two source messages are created in measurement order:

| Message | Measurement sequence | Measurement epoch | Source vector |
|---|---:|---:|---|
| m1 (older) | 1 | 0 | {host-A: 1} |
| m2 (newer) | 2 | 1 | {host-A: 2} |

The receiver admits m2 first and then records decision D1. Only afterward does it admit m1 and record D2.

The synthetic receiver-local vector sequence is:

| Receiver event | Vector | Event |
|---|---|---|
| 1 | {host-A: 2, host-B: 1} | Admit m2 |
| 2 | {host-A: 2, host-B: 2} | Decide D1 |
| 3 | {host-A: 2, host-B: 3} | Admit m1 |
| 4 | {host-A: 2, host-B: 4} | Decide D2 |

At D1, both source sends are causally before the decision. But only m2 is within the receiver's complete admitted prefix. m1 arrives later. At D2, both are available; D2 declares using m2 only, demonstrating that availability and use are not interchangeable.

## Reconstructed result

From the repository root, run:

    python -m unittest discover -s experiments/decision-time-evidence-frontier -p 'test_*.py' -v
    python experiments/decision-time-evidence-frontier/frontier.py --compact

Expected core relation:

| Decision | Message | Source send → decision | Decision → receiver intake | Reconstructed availability | Declared used |
|---|---|---|---|---|---|
| D1 | m1 | before | before | arrived after decision | no |
| D1 | m2 | before | after | available at decision | yes |
| D2 | m1 | before | after | available at decision | no |
| D2 | m2 | before | after | available at decision | yes |

In the decision → receiver intake column, **before** for D1/m1 means the decision causally precedes the later receiver intake. **After** for the other rows means the intake event causally precedes the decision.

This directly demonstrates the central distinction:

    source send ≺ decision  does not imply  receiver admission ≺ decision

## Completeness and unknown states

Each receiver event is bound to its predecessor by a SHA-256 hash-chain link. A decision explicitly records the preceding event sequence and head digest that define its evidence frontier. The verifier reconstructs the available set from that prefix and checks it against the decision's declared set.

If a required event in the prefix is missing, the report emits unknown_incomplete_log and leaves the reconstructed available set null. It does not convert a missing record into evidence that a message was absent, late, lost, or unused.

Try the explicit missing-prefix case:

    python experiments/decision-time-evidence-frontier/frontier.py --drop-receiver-event 1 --compact

That removes the first receiver intake event. D1 and D2 remain present but their claimed prefixes cannot be reconstructed from a complete chain; their availability status becomes unknown. By contrast, a present record with an invalid content digest or a broken link between two present contiguous records is rejected as an integrity error.

A complete prefix only supports the statement **“the receiver log records this message as admitted by the decision frontier.”** It does not prove that the exported log is complete in the real system, that the receiver executed honestly, or that the value influenced a computation. A digest is content integrity, not authentication or anti-rollback protection. A deployed form would need an authenticated append-only receiver journal, a protected monotonic head/checkpoint, and an explicit rule for proving that the exported prefix is complete.

## Reproduction and verification boundary

The implementation uses Python's standard library and exact integer vector clocks. It retains source events, receiver events, event digests, decision frontier coordinates, declared available/used sets, reconstructed availability, and the report digest. The report validator rebuilds every assessment from the retained event logs.

No wall clock or cross-host elapsed duration is used. No global total order is emitted. The vector clocks in this fixture are declared logical coordinates; no real transport, clock calibration, mTLS, or E-CPU runtime is exercised. This is a deterministic semantics test intended to identify the required receiver-side evidence contract before an adapter is attempted.

## Files

- frontier.py — fixture creation, event validation, prefix reconstruction, report generation and validation.
- test_frontier.py — tests for late-arriving evidence, available-versus-used distinctions, incomplete prefixes, tampering, and reconstruction.
- frontier.schema.json — Draft 2020-12 schema for the portable report.
