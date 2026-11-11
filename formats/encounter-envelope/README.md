# Encounter envelope (experimental 0.1)

**Status: exploratory proposal.** This is an optional interchange shape for carrying an observed event or artifact between contributors. It is not a repository-wide requirement, stable standard, trust system, or replacement for the data model of any connected project.

The central distinction is simple:

> Preserve what was encountered separately from what a contributor thinks it means.

An encounter can be a tool response, a measurement, a received message, a file, a runtime trace, a failed attempt, or another bounded piece of evidence. A later contributor can reinterpret it without silently changing the original record.

## Files

- [schema.json](schema.json) — JSON Schema 2020-12 description of the experimental envelope.
- [validate_envelope.py](validate_envelope.py) — zero-dependency Python structural validator and limited inline-payload digest checker.
- [test_validate_envelope.py](test_validate_envelope.py) — standard-library tests; schema-parity checks run too when the optional jsonschema package is installed.
- [examples/tool-observation.json](examples/tool-observation.json) — a minimal illustrative record.

## Verification

Validate an encounter record:

\`\`\`bash
python formats/encounter-envelope/validate_envelope.py formats/encounter-envelope/examples/tool-observation.json
\`\`\`

Run the standard-library test suite:

\`\`\`bash
python -m unittest discover -s formats/encounter-envelope -p 'test_*.py' -v
\`\`\`

The validator checks the documented structural constraints without third-party dependencies. Its optional schema-agreement test uses jsonschema with a format checker when that development dependency is present; otherwise that one test is skipped. The runtime validator does not import jsonschema.

An exit code of 0 means structural validation passed and any requested inline digest check was completed successfully. An exit code of 1 means a structural check failed, a digest mismatched, or a requested digest could not be verified. Exit code 2 is command usage error.

## Shape

An envelope has a format identifier, a local record identifier, a source declaration, and a payload. Event time and record time are separate and may be unknown.

| Field | Purpose |
| --- | --- |
| format | Identifies this exact envelope version. |
| id | Identifier chosen by the recording contributor. It is not globally unique by itself. |
| observed_at | Time of the event, if known, as a timezone-qualified RFC 3339 date-time or null. |
| recorded_at | Time the envelope was written, if known. |
| source | Declared origin and capture method. A declaration is provenance information, not authentication. |
| context | Optional surrounding conditions needed to interpret the encounter. |
| payload | The captured value or a reference to the retained artifact. |
| relations | Optional links to related encounters or artifacts. |
| integrity | Optional digest metadata. |
| extensions | Optional namespaced additions for domain-specific needs. |

The schema permits extra fields so experiments can evolve without waiting for this proposal to anticipate every domain. Producers should still prefer namespaced extension keys and document their meaning.

## Digest contract implemented by the validator

Digest declarations are not authentication or proof of origin. They only let a reader check whether bytes match a stated digest under a stated byte-conversion rule.

The validator currently implements:

- algorithm: sha256
- canonicalization: utf8-raw-v1 — for a string payload, hash its UTF-8 bytes exactly, without JSON quotes.
- canonicalization: json-sort-keys-utf8-v1 — serialize the inline JSON value with sorted object keys, compact separators, UTF-8 characters preserved, and non-finite numbers rejected; then hash those bytes.

The second mode is a small, explicitly named local contract. It is **not** a claim of RFC 8785/JCS compatibility or universal cross-language canonical JSON. Future implementations should reproduce these exact rules or introduce a new canonicalization identifier.

For an inline value, integrity must include algorithm, canonicalization, and digest for the validator to verify the claim. Unsupported or missing settings are reported as unverified, not silently accepted. A mismatch is reported explicitly.

For payload.reference, the validator does not fetch the referenced artifact. An integrity declaration for a reference is reported as **not checked**, and the command exits non-zero when verification was requested. payload.digest by itself is only a declaration; without an algorithm, canonicalization, and accessible bytes, it is not verified by this tool.

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

For large or non-JSON artifacts, store the artifact separately and use payload.reference; retain media type, digest, and any decoding details needed to retrieve and check it. Avoid copying private or access-controlled material into a public repository.

## Why this is a proposal

The [Virtual Ground Interpreter](https://github.com/Kier73/Virtual-Ground-Interpreter) has explored encounter records, transport receipts, and a separate association ledger for hypotheses and assessments. E-CPU also distinguishes observation, Ground construction, navigation, and verification. This envelope is a small attempt to make one narrow boundary portable across projects; it does not import either project's implementation or claim that their models are interchangeable.

The next useful test is a cold-start handoff: give a new contributor only an encounter and a separate interpretation, then ask what can be recovered, what remains unknown, and what assumptions are accidentally introduced. Change or discard this format based on that experiment.
