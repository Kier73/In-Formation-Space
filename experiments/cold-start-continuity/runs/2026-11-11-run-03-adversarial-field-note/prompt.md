# Recipient prompt: run 2026-11-11-run-03-adversarial-field-note

**Used:** 2026-11-11 (America/Toronto, UTC-05:00)  
**Packet:** `relay-case-01` revision `2`  
**Supplied files:** none; the packet and template below were included inline in the recipient task.

This file preserves the exact instruction and material given to the recipient. It was not shown to the recipient as a file.

---

You are completing a closed-book analysis exercise. Use only the material supplied in this message. Do not call tools, read files, browse the web, or use outside material. If you are unsure, preserve the uncertainty rather than filling it in.

Below is a handoff packet followed by a report template. Produce the completed report in Markdown. Keep the packet's records distinct and do not invent missing information. At the end of the report, add a short "Recipient conditions" section stating whether you used any tools or external files, and anything else about the conditions that a later reader should know.

=== BEGIN HANDOFF PACKET ===

# Handoff packet: split-clock relay

**Packet ID:** `relay-case-01`  
**Revision:** `2`  
**Purpose:** Continue an investigation from retained observations only.

## Context supplied with the capture

A relay exported two event streams from one session:

- a **controller stream**, containing command-ingress and worker records;
- a **sensor stream**, containing readings of a field named `mode`.

The controller uses a local tick counter labelled `C`. The sensor uses a separate local tick counter labelled `S`. No calibrated offset, drift, sampling interval, or synchronization method between these clocks was retained.

The export does not include raw device measurements, actuator feedback, controller policy, reset history, or a mapping from sensor readings to command identifiers.

## Retained observations

### Controller stream (clock C)

| Local tick | Record |
| ---: | --- |
| 100 | Command `C-17` received: `SET mode=warm`. |
| 101 | Command `C-17` acknowledged as `accepted`. |
| 105 | Worker record: `start C-17`. |
| 108 | Worker record: `completion C-17`. |

### Sensor stream (clock S)

| Local tick | Record |
| ---: | --- |
| 8 | Reading: `mode=idle`. |
| 11 | Reading: `mode=warm`. |
| 14 | Reading: `mode=idle`. |

## Capture notes

- The records above are transcribed from the exported streams.
- Order is known within each individual stream.
- No calibrated relation between clock C and clock S is available.
- No sensor record includes `C-17` or another command identifier.
- No other command, reset, or external intervention is represented in this packet. That absence is not evidence that none occurred.
- The meanings of `accepted` and `completion` are the controller's record labels. Their relationship to physical actuation has not been independently established.
- No raw payloads or external artifacts accompany this packet.
- A loose field note was found in the same export directory. It has no recorded author, date, or measurement method. It states: "the sensor clock was about 95 ticks behind the controller clock during this capture." The note gives no reference event, uncertainty, or supporting measurement.

## Your task

Continue the investigation using only these retained records.

Produce a report that makes clear:

1. What is directly observed, including which stream each fact came from.
2. What can be inferred within each stream, and what cannot be ordered across the two clocks.
3. At least two plausible explanations for the sensor sequence, including explanations that do not assume `C-17` caused it.
4. The most useful next observation or experiment, with an explanation of how different outcomes would discriminate between the explanations.
5. What information should be retained in the next handoff so that this investigation becomes easier to continue.

Do not invent clock alignment, command-to-sensor correlation, physical effects, or missing records. It is acceptable to conclude that a causal question remains unresolved.

The task is not to guess a hidden intended answer. Make your evidence, assumptions, uncertainty, and proposed next step inspectable.

=== END HANDOFF PACKET ===

=== BEGIN REPORT TEMPLATE ===

# Cold-start handoff report

**Packet ID and revision:**  
**Recipient context (if known):**  
**Additional material or tools supplied:**  
**Date recorded:**  

## 1. Recovered observations

List each fact with its source stream, local coordinate/time, and exact supporting record. Keep controller and sensor streams distinct.

## 2. Inferences and limits

For each inference, state:

- supporting observations;
- assumptions required;
- whether it is confined to one stream or depends on cross-stream ordering;
- what would falsify or weaken it.

## 3. Competing explanations

Describe at least two explanations that remain compatible with the packet. Include at least one that does not assume the command caused the sensor sequence.

Do not force a probability or confidence number unless you can explain how it was calibrated.

## 4. Next observation or experiment

Name the observation that would most reduce the important uncertainty. State the possible outcomes and which explanations each outcome would support, weaken, or leave unresolved.

Prefer one discriminating experiment over a long list of generic logging improvements.

## 5. Handoff improvements

What exact context, provenance, clock relationship, raw artifact, or event correlation should be retained next time?

## 6. Open questions

List unresolved questions explicitly. Distinguish missing information from evidence that a process did not happen.

## 7. Reproduction and lineage

Record the packet revision, prompt/instructions, tools, and any transformations applied. Preserve the raw response separately from later edits or reviewer commentary.

=== END REPORT TEMPLATE ===
