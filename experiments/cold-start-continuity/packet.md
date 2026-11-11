# Handoff packet: split-clock relay

**Packet ID:** `relay-case-01`  
**Revision:** `1`  
**Purpose:** Continue an investigation from retained observations only.

## Context supplied with the capture

A relay exported two event streams from one session:

- a **controller stream**, containing command-ingress and worker records;
- a **sensor stream**, containing readings of a field named `mode`.

The controller uses a local tick counter labelled `C`. The sensor uses a separate local tick counter labelled `S`. The offset, drift, sampling interval, and synchronization method between these clocks were not retained.

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
