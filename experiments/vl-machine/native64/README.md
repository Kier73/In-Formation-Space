# VLM-002 — native x86-64 descriptor machine

The machine now loads arbitrary bounded word32 DAGs, rather than dispatching only standalone arithmetic primitives. Assembly establishes long mode and identity paging. A freestanding C core implements the execution ABI, and the same source is compiled as a hosted library for differential testing. No libc or OS is required in the guest.

## Build and use

    make
    python3 test_core.py -v
    python3 test_guest.py

The latter requires QEMU system x86; boot manually with:

    qemu-system-x86_64 -m 32 -cpu qemu64 -kernel vlm64.elf -display none -serial stdio -monitor none

The image is a Multiboot ELF32 envelope around linked x86-64 code. Guest protocol: one command followed by exactly eight lowercase hex digits per word, then LF. No spaces. All words unsigned.

| Command | Words | Meaning |
|---|---|---|
| b | count, output index | Begin staging graph (max 1024 nodes) |
| p | index, op, a, b, c, literal | Append next validated node |
| c | none | Commit staged graph atomically |
| r | input | Observe output and report word-op count |
| g | coefficient a, coefficient b | Independently check and admit affine candidate |
| h | shear coefficient k, translation d | Verify and admit canonical nonlinear chart |
| j | input, steps high, steps low | Jump 64-bit time in admitted map |
| q | none | Guest shutdown via QEMU debug-exit if configured |

Operator IDs: input=0, const=1, add=2, mul=3, xor=4, and=5, unsigned-less=6, select=7. Each dependency must precede its node. Unused fields are zero. SELECT uses a as condition, b as true value and c as false value. Replies are OK, REJECT or RESULT with output and work hex words. Work for affine j is compositions; nonlinear chart j reports fixed word operations.

Two bounded descriptor banks provide transactional replacement; malformed node invalidates staging without touching the active graph or its Ground. Successful commit invalidates the previous Ground. Admission checks all live polynomial coefficients, not a finite sample. Candidate generation may take place in a separate observer (e.g. portable machine.py). There is no concurrent access, privilege isolation, dynamic heap, persistent memory or network in this stage. The full native graph is fixed-capacity static memory, a deliberate bounded allocator precursor.

## Local execution evidence

Local gcc and binutils built the extended freestanding ELF, 9796 bytes, with no undefined symbols in the linked 64-bit executable. Hosted differential suite: 4 tests passed, including 300 randomized graphs with 10 inputs each, 120 independent 128-layer affine graphs with forged coefficient rejection, short iterative oracle and distant-time composition tests, transactional failure, and 200 nonlinear chart trials with iteration parity, distant-time composition and tamper rejection. The native boot/serial path still requires QEMU verification. Native binary size excludes zero-initialized memory; no neural model included.

## Next

Unify typed graph protocol with the portable source identity, bounded session handles, graph storage and causal checkpoints. Then route independently qualified kernels through E-CPU, and provide resident neural applications through typed tensor operators. No new distributed authority protocol is introduced here.

## Nonlinear native path Ground

A word packs two 16-bit coordinates. Let k be divisible by 65536, l(x)=x & 65535, E(x)=x+k*l(x)^3 and D(x)=x-k*l(x)^3, with arithmetic modulo 2^32. Because adding a multiple of 65536 leaves l unchanged, D(E(x))=x and E(D(x))=x. Let M(x)=x+d. The admitted graph is exactly F=D∘M∘E, so F^n(x)=D(E(x)+n*d). This is exact for every 32-bit x and every unsigned 64-bit n. For k=65536,d=1 the second finite difference at x=0,1,2 is nonzero, so F is not affine. The verifier checks all 16 nodes against this canonical graph; no inference from sampled outputs is accepted. One ordinary transition needs 11 word operators; navigation needs 12 word operators independently of n. A 10^12-step reference would require 11*10^12 word operators (analytical, not executed). This is a restricted reversible-chart family and not automatic discovery of arbitrary nonlinear laws. It is conceptually related to IFS [RCG-005 nonlinear orbit](../../real_connectome_ground/continuity/nonlinear_orbit/README.md) through exact conjugacy; this word-ring specialization is independently implemented.

## VLM-003 — structural processes

Publish the currently committed graph and its verified Ground (if present) into one of eight immutable snapshot slots. Up to 64 processes may refer to these snapshots. Graph replacement in the staging interface cannot change a published graph. Generation-tagged handles reject stale references within one authority lifetime; slots retire rather than wrap. Graph release fails while processes refer to it.

| Command | Words | Meaning |
|---|---|---|
| P | none | Publish graph; returns HANDLE |
| D | graph | Release unreferenced graph |
| S | graph, seed | Spawn process; returns HANDLE |
| T | process, time high, time low | Seek absolute logical time; RESULT zero and work |
| O | process | Observe current state and work |
| X | process | Close process |
| K | process | Return CHECKPOINT graph, seed, time high, time low (Ground required) |
| R | graph, seed, time high, time low | Restore as new process (Ground required) |

A grounded process keeps seed and absolute time, not a materialized current result: seek (even backward) changes only the coordinate and reports zero word-operator executions. Observation reconstructs using the pinned admitted Ground. Ungrounded processes advance at most 1024 transitions per request, retain current state and reject backward or over-budget seeks. Checkpoints are 16-byte logical payloads, local recipes rather than authenticated or cross-boot identities; the graph must remain published. A restored process gets a new handle. The static process struct also contains lifecycle metadata and a fallback word; 16 bytes is not the actual in-memory size. The shared graph table retains original descriptors for audit and fallback.

Local build: 13,524-byte ELF32 boot envelope, 7,864 bytes text, 273,696 bytes BSS, no undefined symbols in linked ELF64. Run `make && python3 -m unittest -v test_core test_process`. Seven hosted groups passed, including 64 processes using two different graphs, 1,024 randomized unsigned-64-bit time observations, 64 close/restore comparisons, graph and process exhaustion, stale handles and bounded fallback. Actual guest process protocol test is added to test_guest.py; QEMU unavailable locally, hosted CI pending. These are sequentially interleaved virtual processes, not 64 simultaneous hardware threads. Next: stable source identities and portable capsules reverified at a fresh authority, task queues, scheduling and native E-CPU handoff.

### Portable reconstruction capsule (host adapter)

`capsule.py` exports the original native graph descriptor, its SHA-256 source identity, Ground witness, seed and uint64 time; no process handle or realized output travels. A fresh process accepts the bounded JSON via stdin (`python3 capsule.py < capsule.json`), checks schema and digests, loads the graph into its own native core, independently checks the witness and reconstructs the requested coordinate. Source hash here is the canonical native descriptor encoding, not yet the portable interpreter's graph identity format. Digests provide integrity only, not origin authentication; a different valid source/seed/time with newly computed digests is a different valid request. This adapter is hosted, not a guest transport. Restore may change the active staging graph even when witness admission fails; existing published snapshots are unaffected. No remote authorization or durable ledger is claimed.

Extended local build: 13,848-byte ELF32 envelope, 8,136 bytes text, 273,696 bytes BSS. `make && python3 -m unittest -v test_core test_process test_capsule`: 9 groups passed, including independent fresh-process restores for both affine and nonlinear Grounds at 10^12, same-process round-trip identity, and rejection of altered digest, rehashed invalid witness, rehashed invalid graph and out-of-range time. The C core is shared by hosted and guest builds, but the portable capsule wrapper is Python. Guest execution remains a CI gate.
