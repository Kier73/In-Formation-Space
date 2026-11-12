# Portable Stateful Checkpoint v1

**Experiment:** PSC-001  
**Schema:** `in-formation-space.portable-stateful-checkpoint.v1`  
**Framing magic:** `IFSPCK01`  
**Status:** research prototype; finite Boolean stateful transition runtime.

## Purpose

PSC-001 transports a live stateful transition runtime without treating its
terminal state as sufficient evidence. It binds:

- the initial typed transition program and initial state;
- the ordered step/revision event history;
- logical tick and model revision as separate counters;
- a SHA-256 genesis record and event predecessor chain;
- one PRC realization capsule for every model revision;
- the active program/model identity at the checkpoint boundary;
- the control input to be interpreted by the receiving environment.

Compiler-specific dense weight arrays are not duplicated inside the checkpoint
history. Each exact executable sparse realization is carried by its own PRC
capsule.

## Binary framing

The binary artifact is:

1. 8-byte ASCII magic `IFSPCK01`;
2. little-endian 16-bit framing version (currently 1);
3. little-endian 32-bit canonical-header byte length;
4. canonical UTF-8 JSON header.

The JSON header binds the core with `checkpoint_sha256`. Its core fields are
`schema`, `version`, `runtime`, `realizations`, and
`resume_controls`. The v1 header uses the PRC canonical JSON profile: safe
integers only, ASCII object keys, UTF-8 scalar strings, compact separators,
and lexicographically sorted object keys.

## Runtime projection

The runtime projection contains the stateful runtime schema and compiler id,
initial state, state-register names, initial and current typed programs,
current model digest, current state, logical tick, revision counter, complete
ordered event list, genesis digest, and chain-head digest.

The projection intentionally stores `current_model_digest` rather than
copying the dense floating-point model snapshot. Exact sparse executable model
bytes are carried in revision-bound PRC capsules. A receiver rebuilding the
runtime replays the typed program and event history, then checks the current
model digest against the active realization capsule.

## Revision-bound realizations

The `realizations` array contains exactly one entry for each revision,
starting at revision zero. Each entry binds:

- contiguous revision number;
- typed-program digest;
- dense compiled-model digest;
- SHA-256 of the complete nested PRC capsule;
- canonical Base64 encoding of the nested capsule bytes.

Each nested capsule must use the supported `hybrid_binary` codec for PSC-001,
identify the corresponding typed program, declare the same ordered interface,
and bind the same dense model digest. The receiver independently verifies the
capsule, decodes the sparse model, and exhaustively compares it with the typed
Boolean program over its complete finite input domain.

## Event replay

Step events must preserve the active program/model identity and satisfy the
typed program and decoded sparse model for every recorded input. They advance
logical tick by exactly one while leaving revision unchanged.

Revision events must preserve state and logical tick, advance revision by one,
preserve the exact ordered input/output interface, and bind the target program
and model to the next realization capsule.

Every event includes a contiguous sequence number, predecessor digest, and
event digest. The receiver recomputes each event digest and replays every event
before accepting the terminal state.

## Receiving and resuming

A receiving implementation:

1. validates checkpoint framing, canonical header, and checkpoint digest;
2. verifies every nested PRC capsule and its revision binding;
3. independently interprets each typed Boolean program;
4. decodes each sparse model and checks complete-domain equivalence;
5. reconstructs genesis and replays all step/revision events;
6. compares final state, logical tick, revision, program/model identities, and
   event-chain head;
7. interprets the supplied resume controls against both the active typed
   program and decoded model, and computes the next event digest.

The Python E-CPU runtime can independently restore by rebuilding the initial
runtime and replaying the same recorded events. The Node.js receiver performs
the corresponding program interpretation and sparse-model execution without
calling the Python decoder or E-CPU interpreter.

## Security and evidence boundary

SHA-256 provides content integrity and identity only. It does not authenticate
the sender, authorize a receiving host, provide external trust anchoring, or
prove who produced a checkpoint. PSC-001 does not implement encryption,
signatures, distributed consensus, concurrent ownership transfer, atomic
multi-host handoff, or durable external side-effect recovery.

Evidence is limited to the declared finite Boolean transition Ground, the
supported hybrid-binary realization capsules, the verified event history, and
the tested resume control. It does not establish arbitrary program or model
portability.
