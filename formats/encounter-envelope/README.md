# Encounter envelope (experimental 0.1)

**Status: exploratory proposal.** This is an optional interchange shape for carrying an observed event or artifact between contributors. It is not a repository-wide requirement, stable standard, trust system, or replacement for the data model of any connected project.

The central distinction is simple:

> Preserve what was encountered separately from what a contributor thinks it means.

An encounter can be a tool response, a measurement, a received message, a file, a runtime trace, a failed attempt, or another bounded piece of evidence. A later contributor can reinterpret it without silently changing the original record.

## Files

- [schema.json](schema.json) — JSON Schema 2020-12 description of the experimental envelope.
- [examples/tool-observation.json](examples/tool-observation.json) — a minimal illustrative record.

## Shape

An envelope has a format identifier, a local record identifier, a source declaration, and a payload. Event time and record time are separate and may be unknown.

| Field | Purpose |
| --- | --- |
| `format` | Identifies this exact envelope version. |
| `id` | Identifier chosen by the recording contributor. It is not globally unique by itself. |
| `observed_at` | Time of the event, if known, in an ISO 8601 date-time representation. |
| `recorded_at` | Time the envelope was written, if known. |
| `source` | Declared origin and capture method. A declaration is provenance information, not authentication. |
| `context` | Optional surrounding conditions needed to interpret the encounter. |
| `payload` | The captured value or a reference to the retained artifact. |
| `relations` | Optional links to related encounters or artifacts. |
| `integrity` | Optional digest metadata. The digest algorithm and canonicalization must be stated when used. |
| `extensions` | Optional namespaced additions for domain-specific needs. |

The schema permits extra fields so experiments can evolve without waiting for this proposal to anticipate every domain. Producers should still prefer namespaced extension keys and document their meaning.

## One record, not one interpretation

Do not put an unmarked conclusion inside the captured payload. Keep interpretations in separate notes or records that refer to the encounter ID.

For example:

- Encounter: "the receiver returned status 503 at 14:02 UTC".
- Hypothesis: "the receiver may have been temporarily unavailable".
- Assessment: "a retry succeeded; this supports a transient-failure explanation, but does not identify the cause".

The hypothesis is not part of the encounter. A future contributor may disagree and should be able to inspect the same underlying record.

Likewise, a contributor should not label a source "verified" merely because the envelope says so. Authentication, evidence admission, causal attribution, and semantic interpretation belong to separate contracts.

## Boundaries

This proposal deliberately does **not** define:

- a global identity or naming authority;
- a common ontology for payload contents;
- a universal timestamp, clock, or causal-ordering model;
- cryptographic signing or source authentication;
- an evidence quorum or admission policy;
- a confidence scale or universal truth status;
- a required storage backend, serialization beyond JSON, or retention period.

An absent timestamp is not zero. A missing source identity is not proof of anonymity. A reference is not proof that its target remains available. A digest is useful only when its algorithm, input bytes, and canonicalization are known.

For large or non-JSON artifacts, store the artifact separately and use `payload.reference`; retain media type, digest, and any decoding details needed to retrieve and check it. Avoid copying private or access-controlled material into a public repository.

## Why this is a proposal

The [Virtual Ground Interpreter](https://github.com/Kier73/Virtual-Ground-Interpreter) has explored encounter records, transport receipts, and a separate association ledger for hypotheses and assessments. E-CPU also distinguishes observation, Ground construction, navigation, and verification. This envelope is a small attempt to make one narrow boundary portable across projects; it does not import either project's implementation or claim that their models are interchangeable.

The next useful test is a cold-start handoff: give a new contributor only an encounter and a separate interpretation, then ask what can be recovered, what remains unknown, and what assumptions are accidentally introduced. Change or discard this format based on that experiment.
