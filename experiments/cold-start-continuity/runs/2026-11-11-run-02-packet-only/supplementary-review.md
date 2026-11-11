# Supplementary review: packet-only handoff run 02

**Reviewer:** separate review pass with repository access.  
**Scope:** conditions.md, prompt.md, response.md, and evaluation.md.  
**Purpose:** qualify what the second run demonstrates and add a fallback experiment path.

## Assessment

Run 02 is a stronger handoff test than run 01 because the exact prompt contains only the packet, the report template, and closed-book instructions. The conditions artifact preserves the prompt, packet, template, and response hashes after declared newline normalization. The raw response is separate from the reviewer evaluation, and the recipient explicitly records that it used no tools or external files.

The report preserves the packet's evidence boundaries. Particularly useful is its observation that the shared words `mode` and `warm` are lexical overlap, not evidence that the controller's `mode` and sensor's `mode` are the same variable. It also avoids the temptation to infer that the later sensor `idle` contradicts a persistent command, because persistence semantics and later interventions are absent.

The reviewer’s 12/12 is a rubric assessment within this run, not a calibrated performance score. The evaluation itself acknowledges that limitation.

## Isolation classification

The accurate classification is **material-limited, not sandbox-isolated**. The supplied prompt contained no reviewer guide or repository instructions, and the recipient self-reports no tool use. However, the child ran in the same harness and workspace as its parent, repository context may have been latent, and tool calls were not independently instrumented. The conditions file states these limits clearly. The run strengthens packet-only evidence but does not establish that the packet was the sole information source available to the process.

The recipient's exact model identity is unknown. The spawning parent model is recorded as DeepSeek V4.1 Flash Free, but that is context, not proof of the child model's identity. The reviewer is the parent session/harness, not an independent external evaluator.

## Independent observations

- The response recovers every retained event and keeps both clock domains distinct.
- It explicitly separates controller record labels from physical realization.
- It keeps command causation unresolved and proposes both causal and non-causal explanations.
- It recognizes label similarity as insufficient to establish semantic identity.
- It offers a useful integrated experiment, but its first design assumes a command/transaction identifier can be propagated into sensor records.

## Fallback when command-ID propagation is impossible

A useful alternative is a randomized active/sham design. Randomly interleave periods in which the command is issued with periods in which no command or a sham event is issued. Record the schedule, dispatch marker, sensor samples, and independent actuator/physical feedback through one external monotonic logger or a shared hardware timing pulse. Pre-register the response window and compare the frequency and latency of warm observations in active versus sham periods over repeated trials.

This does not require the sensor protocol itself to carry the command ID. It still requires a defensible timing path and complete intervention logging. If a common recorder or timing pulse cannot be established, the separate C and S ticks remain incomparable and the temporal question stays unresolved. If physical feedback is unavailable, the design can test an association with the sensor output but cannot independently establish a physical actuation effect.

## Disposition

Preserve run 02 as a **material-limited packet-only handoff** and do not rename it a fully isolated or blind run. Keep the raw response and original evaluation unchanged in substance; this note supplements them. The next clean test is a sandbox containing only packet and template, with network/tool access disabled or instrumented. A complementary adversarial packet revision can test whether a recipient resists subtle invitations to overclaim.