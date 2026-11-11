# Cold-start handoff run kit

**Status:** experimental tooling for the [cold-start continuity experiment](../README.md). Zero external dependencies; Python 3.10+.

The experiment distinguishes four isolation levels (L0–L3). A level is a claim about what material the recipient received, whether tools were controlled, and whether the workspace was isolated. This kit makes that claim recordable and inspectable.

## Files

- [handoff_kit.py](handoff_kit.py) — manifest builder and run auditor.
- [test_handoff_kit.py](test_handoff_kit.py) — standard-library tests.
- [Run 02 manifest](../runs/2026-11-11-run-02-packet-only/manifest.json) — machine-readable L1 record for the recorded packet-only run.

## Record a completed run

From the repository root:

```bash
python experiments/cold-start-continuity/handoff_kit/handoff_kit.py manifest \
  --run-dir experiments/cold-start-continuity/runs/2026-11-11-run-02-packet-only \
  --packet experiments/cold-start-continuity/packet.md \
  --template experiments/cold-start-continuity/report-template.md \
  --level L1 \
  --recipient-context "fresh general subagent; parent session DeepSeek V4.1 Flash Free" \
  --notes "Self-report only; not sandboxed or instrumented."
```

The command writes `manifest.json` in the run directory and records:

- the packet and template paths and their SHA-256 hashes (LF-normalized);
- the declared isolation level;
- the declared tool policy and whether tool use was instrumented;
- whether the workspace was isolated;
- hashes for `prompt.md` and `response.md` when present;
- paths for `conditions.md` and `evaluation.md` when present.

`created_at` records when the manifest was written, not when the handoff run occurred. Re-run with `--force` after adding or changing an artifact to refresh the hashes.

## Audit a run

```bash
python experiments/cold-start-continuity/handoff_kit/handoff_kit.py audit \
  --run-dir experiments/cold-start-continuity/runs/2026-11-11-run-02-packet-only
```

Add `--json` for machine-readable output. Exit code 0 means no structural errors; 1 means at least one error; 2 is a usage error.

Prompt and response hash mismatches are errors. Conditions and evaluation hash mismatches are warnings, so later reviewer annotations can be added without silently rewriting the run evidence; refresh the manifest with `--force` when the record is intentionally updated.

The audit checks:

- the manifest format, required fields, and artifact references;
- packet, template, prompt, and response hashes;
- that an L1 prompt actually contains the packet and template text;
- that an L2/L3 manifest declares both workspace isolation and either tool instrumentation or a disabled tool policy;
- that a reviewer guide is not present in the run directory;
- that the response is non-empty;
- that files outside the standard run record set are flagged.

## What the audit does not establish

It is a consistency check, not an attestation service. It cannot prove that:

- a recipient actually obeyed a no-tools instruction;
- a tool call did not occur;
- a workspace was actually unreachable;
- the report is correct, useful, or independent of ambient context;
- the contributor identity is authentic.

A manifest can be incomplete or deliberately false. The audit can only catch records that contradict themselves or their declared level. For an L2/L3 claim, independent instrumentation or an external sandbox record is still the stronger evidence.

## Manifest shape

```json
{
  "format": "in-formation.cold-start-run/0.1",
  "run_id": "2026-11-11-run-02-packet-only",
  "created_at": "2026-11-11T16:26:54+00:00",
  "isolation_level": "L1",
  "packet": {"path": "../../packet.md", "sha256_lf": "..."},
  "template": {"path": "../../report-template.md", "sha256_lf": "..."},
  "supplied_material": ["packet.md", "report-template.md"],
  "tool_policy": "prohibited-by-instruction",
  "tool_instrumentation": false,
  "workspace_isolation": false,
  "recipient": {"context": "...", "identity_verified": false},
  "artifacts": {
    "prompt": {"path": "prompt.md", "sha256_lf": "..."},
    "response": {"path": "response.md", "sha256_lf": "..."},
    "conditions": {"path": "conditions.md", "sha256_lf": "..."},
    "evaluation": {"path": "evaluation.md", "sha256_lf": "..."}
  },
  "notes": "..."
}
```

`tool_policy` is one of `unknown`, `available`, `prohibited-by-instruction`, `disabled`, or `instrumented`. L2/L3 require `workspace_isolation: true` and either `tool_instrumentation: true` or `tool_policy: "disabled"`.

## Boundaries

The kit is deliberately narrow. It does not replace the [reviewer guide](../reviewer-guide.md), the run conditions, or a separate evaluation. It does not import the encounter-envelope format or claim compatibility with it. It is a small aid for keeping isolation claims tied to the record that supports them.
