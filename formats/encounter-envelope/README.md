# Encounter envelope (experimental 0.1)

**Status: exploratory proposal.** This is an optional interchange shape for carrying an observed event or artifact between contributors. It is not a repository-wide requirement, stable standard, trust system, or replacement for the data model of any connected project.

The central distinction is simple:

> Preserve what was encountered separately from what a contributor thinks it means.

An encounter can be a tool response, a measurement, a received message, a file, a runtime trace, a failed attempt, or another bounded piece of evidence. A later contributor can reinterpret it without silently changing the original record.

## Files

- [schema.json](schema.json) — JSON Schema 2020-12 description of the experimental envelope.
- [validate_envelope.py](validate_envelope.py) — zero-dependency Python structural validator and limited inline-payload digest checker.
- [test_validate_envelope.py](test_validate_envelope.py) — standard-library tests; schema-parity checks run too when the optional jsonschema package is installed.
- [capture_encounter.py](capture_encounter.py) — command runner and observation packaging utility that emits compliant envelopes.
- [examples/tool-observation.json](examples/tool-observation.json) — a minimal illustrative record.
- [examples/captured-cmd.json](examples/captured-cmd.json) — an automatically captured subprocess execution record with SHA-256 integrity verification.

## Verification

Validate an encounter record:

```bash
python formats/encounter-envelope/validate_envelope.py formats/encounter-envelope/examples/tool-observation.json
```

Run the standard-library test suite:

```bash
python -m unittest discover -s formats/encounter-envelope -p 'test_*.py' -v
```

The validator checks the documented structural constraints without third-party dependencies. Its optional schema-agreement test uses jsonschema with a format checker when that development dependency is present; otherwise that one test is skipped. The runtime validator does not import jsonschema.

An exit code of 0 means structural validation passed and any requested inline digest check was completed successfully. An exit code of 1 means a structural check failed, a digest mismatched, or a requested digest could not be verified. Exit code 2 is command usage error.

## Shape

An envelope has a format identifier, a local record identifier, a source declaration, and a payload. Event time and record time are separate and may be unknown.

| Field | Purpose |
| --- | --- |
| format | Identifies this exact envelope version. |
| id | Identifier chosen by the recording contributor. It is not globally unique by itself. |
| observed_at | Time of the event, if known, as a timezone-qualified RFC 3339-compatible date-time or null; leap-second notation (:60) is not supported by the standard-library validator. |
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

The second mode is a small, explicitly named Python serialization contract. It uses Python's `json.dumps` with `sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`, and `allow_nan=False`, then UTF-8 encodes the resulting text. JSON numeric representations remain type-sensitive: for example, a payload number written as `4` hashes differently from `4.0`. Floating-point formatting and exponent notation are those emitted by the Python JSON encoder; another language must not assume its default JSON serializer will produce identical bytes. This is **not** a claim of RFC 8785/JCS compatibility or universal cross-language canonical JSON. For cross-language interoperability, use the same Python encoder or define a new canonicalization identifier with a formally specified algorithm such as JCS.

For an inline value, integrity must include algorithm, canonicalization, and digest for the validator to verify the claim. Unsupported or missing settings are reported as unverified, not silently accepted. A mismatch is reported explicitly.

For payload.reference, the validator does not fetch the referenced artifact. An integrity declaration for a reference is reported as **not checked**, and the command exits non-zero when verification was requested. payload.digest is informational only in this implementation; it is never verified by this tool, even when integrity metadata is also present.

## Safe use of the capture utility

The cmd mode executes the supplied command string through a shell. Only run commands you trust; never pass an untrusted string into this mode. The utility records the command text, working directory, exit code, duration, platform metadata, stdout, and stderr.

Captured output and context may contain credentials, access tokens, personal information, private file paths, environment details, proprietary data, or other material that should not be published. Review and redact the envelope before committing it to a public repository. Hashes detect changes to the captured bytes; they do not make sensitive content safe to disclose.

The capture utility refuses extra context keys that would overwrite observed fields such as command, exit code, duration, platform, and working directory. Additional context is supplemental metadata and must not rewrite what the process actually reported.

The command runner currently has no built-in timeout. Use it only for commands expected to finish under the time and resource limits of the environment in which it is run.

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

## Causal graph analysis

Encounter envelopes may carry a `relations` array linking them to other envelopes by named relation kinds. The causal graph tool interprets those links as a partial order and analyzes the resulting structure.

**Files:**

- [causal_graph.py](causal_graph.py) — builds and analyzes a causal poset from a collection of envelopes.
- [test_causal_graph.py](test_causal_graph.py) — 12 unit tests for cycle detection, transitive reduction, clock-domain-scoped timestamp diagnostics, and linear extension counting.

**Relation kinds and induced edge directions:**

| Kind | Direction | Meaning |
| --- | --- | --- |
| `precedes`, `causes`, `triggers`, `initiates` | source → target | source event causally precedes target |
| `caused_by`, `depends_on`, `derived_from`, `response_to`, `verifies` | target → source | target causally precedes source |
| `references`, `annotates`, `correlates_with`, `see_also`, `replaces` | — (non-causal) | informative links; no temporal ordering imposed |

**Analyses produced:**

- **Cycle detection:** 3-color DFS identifies causal contradictions and returns an exact witness path.
- **Hasse reduction:** transitive reduction extracts the minimal dependency diagram — the edges you would draw by hand.
- **Timestamp-domain audit:** checks a causal pair only when both envelopes declare the same non-empty `context.observed_at_clock_domain`. Missing timestamps, missing domain IDs, and different domains are reported as unassessed rather than ordered. A same-domain conflict is a diagnostic: a wall clock can step or be misconfigured, so the result does not disprove the causal edge.
- **Linear extension count:** $|\Omega|$ measures temporal underdetermination — how many total orderings are consistent with the partial causal order. Computed exactly via down-set DP for $\le 16$ internal nodes.
- **External target identification:** relations pointing outside the supplied envelope set mark an epistemic boundary — the graph is known to be incomplete at those edges.



**Timestamp comparability:** `observed_at` is a wall-clock reading, not a universal event coordinate. To opt into the diagnostic for one event, supply the clock-domain identity in its context:

```json
{
  "observed_at": "2026-11-11T12:05:00Z",
  "context": {
    "observed_at_clock_domain": "receiver-wall-clock:boot-17"
  }
}
```

Two causal events are compared only when both timestamps parse and both domain IDs are exactly equal. The ID should identify the clock instance/domain, not merely a device family or a generic label such as `UTC`. A pair with a missing timestamp, missing domain ID, or different domain IDs is unassessed; it does not become concurrent and is not assigned an order. The report exposes checked and unassessed pair counts plus grouped reasons.

A same-domain timestamp conflict means only that the recorded wall-clock readings oppose the causal relation. It may reflect clock adjustment, delayed timestamp capture, bad domain metadata, or a data error. It is not proof that the causal relation is impossible. This audit does not apply affine calibration, infer causality from timestamps, or compare `recorded_at` values.

**Reproduce:**

```bash
python -m unittest discover -s formats/encounter-envelope -p 'test_causal_graph.py' -v
```

**CLI — analyze a set of envelope files:**

```bash
python formats/encounter-envelope/causal_graph.py \
    path/to/envelope-a.json \
    path/to/envelope-b.json \
    path/to/envelope-c.json
```

Exits 0 on success, 1 on a detected causal cycle or analysis error, 2 on usage error.

## Why this is a proposal

The [Virtual Ground Interpreter](https://github.com/Kier73/Virtual-Ground-Interpreter) has explored encounter records, transport receipts, and a separate association ledger for hypotheses and assessments. E-CPU also distinguishes observation, Ground construction, navigation, and verification. This envelope is a small attempt to make one narrow boundary portable across projects; it does not import either project's implementation or claim that their models are interchangeable.

The next useful test is a cold-start handoff: give a new contributor only an encounter and a separate interpretation, then ask what can be recovered, what remains unknown, and what assumptions are accidentally introduced. Change or discard this format based on that experiment.
