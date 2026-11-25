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
| j | input, steps high, steps low | Jump 64-bit time in admitted affine map |
| q | none | Guest shutdown via QEMU debug-exit if configured |

Operator IDs: input=0, const=1, add=2, mul=3, xor=4, and=5, unsigned-less=6, select=7. Each dependency must precede its node. Unused fields are zero. SELECT uses a as condition, b as true value and c as false value. Replies are OK, REJECT or RESULT with output and work hex words. Work for j is compositions, not word operations.

Two bounded descriptor banks provide transactional replacement; malformed node invalidates staging without touching the active graph or its Ground. Successful commit invalidates the previous Ground. Admission checks all live polynomial coefficients, not a finite sample. Candidate generation may take place in a separate observer (e.g. portable machine.py). There is no concurrent access, privilege isolation, dynamic heap, persistent memory or network in this stage. The full native graph is fixed-capacity static memory, a deliberate bounded allocator precursor.

## Local execution evidence

Local gcc and binutils built the freestanding ELF, 8840 bytes, with no undefined symbols in the linked 64-bit executable. Hosted differential suite: 3 tests passed, including 300 randomized graphs with 10 inputs each, 120 independent 128-layer affine graphs with forged coefficient rejection, short iterative oracle and distant-time composition tests, and transactional failure. The native boot/serial path still requires QEMU verification. Native binary size excludes zero-initialized memory; no neural model included.

## Next

Unify typed graph protocol with the portable source identity, bounded session handles, graph storage and causal checkpoints. Then route independently qualified kernels through E-CPU, and provide resident neural applications through typed tensor operators. No new distributed authority protocol is introduced here.
