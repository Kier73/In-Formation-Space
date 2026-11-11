# Run conditions: 2026-11-11-run-02-packet-only

**Run ID:** `2026-11-11-run-02-packet-only`  
**Date recorded:** 2026-11-11 (America/Toronto, UTC-05:00)  
**Packet:** [`relay-case-01`, revision 1](../../packet.md)  
**Template:** [`report-template.md`](../../report-template.md)  
**Raw response:** [`response.md`](response.md)

## Integrity of the supplied material

Hashes are SHA-256 over UTF-8 bytes with CRLF normalized to LF, so they remain stable across Git checkouts. The packet and template working-tree files use CRLF; the generated prompt and response use LF.

| Artifact | SHA-256 (LF-normalized) |
| --- | --- |
| `packet.md` (revision 1) | `f0d61d6396763030bf67fa34fa3808923b0f5e0ed3382573e9918230a5bf2595` |
| `report-template.md` | `de50f73ce741cfd64bb4497ad328df1dcb458c98f3d7f03ae8a71b527f8904b2` |
| `prompt.md` (exact recipient prompt) | `826309c690777604d2580f320abbe797e2542aaa9c15fd98c9137b84e5ce01e2` |
| `response.md` (saved raw response) | `5e4d78ac7e2bd7ba2e42550bc26a05f04f99df71a604c67f869db2516bcb4c55` |

The packet and template were included verbatim in the prompt after newline normalization; this was checked by substring comparison against the source files. The packet and template were not modified for this run.

## Recipient

- A fresh OpenCode `general` subagent, child session `ses_e338aa539ffeDMjP49HDK7XCNb`.
- Spawned by an OpenCode parent session running DeepSeek V4.1 Flash Free. The child session's exact model identifier was not independently exposed in the returned transcript; treat the parent model as context, not as a verified child identity.
- No persistent identity, memory, or shared conversation with the authoring or reviewing instance is claimed.

## Material supplied

- The handoff packet (`relay-case-01`, revision 1) and report template, inline in the recipient prompt.
- A closed-book instruction: use only the supplied material; do not call tools, read files, browse the web, or use outside material; preserve uncertainty; add a recipient-conditions section.
- No experiment README, reviewer guide, prior run, repository map, or external artifact was supplied.
- The exact prompt is retained in [prompt.md](prompt.md).

## Isolation boundary

This run is **material-limited, not sandbox-isolated**.

- The recipient ran in the same OpenCode harness and workspace environment as the parent. Repository-level context or file access may have been latent even though no repository files were supplied in the prompt.
- Tool use was prohibited by instruction, and the recipient self-reports that it used no tools or external files. The run did not instrument tool calls, and the child was not confined to a directory containing only the packet and template. The self-report is therefore evidence about the recipient's account, not an independently verified execution trace.
- The response contains no reviewer-guide wording and handles the packet's uncertainty boundaries independently. That is consistent with packet-only reasoning, but it is not proof that no outside context was available.
- This is a cleaner material condition than [run 01](../2026-11-11-run-01/response.md), whose recipient had open repository context. It does not close the residual-exposure problem identified in that run's evaluation.

## Reproduction

1. Give [prompt.md](prompt.md) to a fresh recipient under the same closed-book instruction.
2. Do not supply the reviewer guide or experiment README.
3. Preserve the raw response separately from reviewer annotations.
4. Record whether the recipient had tool access, workspace access, or repository context, and whether that access was instrumented.

A fully isolated repeat should mount only `packet.md` and `report-template.md`, disable or record tool calls, and use the same prompt.

## Notes

- Concurrent repository work by other contributors was present while this run was recorded. It did not modify the cold-start packet, template, reviewer guide, or this run directory, and none of that work was supplied to the recipient.
- The response is preserved as returned. Reviewer commentary belongs in [evaluation.md](evaluation.md), not in the raw response.
