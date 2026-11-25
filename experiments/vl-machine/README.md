# VLM — Virtual Layer Machine

A ground-up interactable computational environment: native physical substrate, portable semantics, demand navigation, admitted structural Grounds and independent session state. First resident intelligence will be an application of the machine, not its purpose.

## VLM-001: foundation

- Portable word32 DAG: unsigned arithmetic modulo 2^32, bitwise operators, comparison and selection. Demand evaluation executes the backward dependency closure of the requested output.
- Ground discovery composes affine coefficients symbolically; a separate bounded-degree polynomial verifier checks the identity before admission. Unsupported live operations fall back to demand realization.
- Sessions share immutable admitted Grounds but not word state or logical time. An affine orbit can navigate to a coordinate using repeated squaring. Receipts are canonical content digests, not signatures or external authority.
- Independent GNU assembly Multiboot 1 i386 guest, COM1 command interface, add/multiply/xor and affine orbit jumps, no OS or libc. Native path is deliberately narrower than the portable semantics; 32-bit step count versus portable 64-bit. QEMU TCG parity test checks actual serial results.

## Run

From this directory:

    python3 -m unittest -v
    python3 machine.py
    make -C native
    make -C native test

Native dependencies: GNU binutils, Python 3, QEMU system x86. Portable example:

    vl> open a 11
    vl> use 3 7
    vl> step a 100
    vl> discover
    vl> step a 1000000000000

Native input has no separators: a/m/x followed by two eight-digit hex words; j followed by four words A B X N. Example j00000003000000070000000b00000002 returns 0000007f (127). q exits with QEMU debug-exit. The console is a trusted experimental interface, not a protected process runtime.

## Mathematics

For f(x)=ax+b over Z/(2^32), composition (a,b)∘(c,d)=(ac,ad+b). A Ground is admitted only if polynomial checking establishes equality to the actual program on the entire word domain. Repeated squaring computes f^n(x) using at most 2 floor(log2(n))+2 compositions for n>0. The independent reference iterates the original DAG; this reduction is a proof for the stated affine family, not a general nonlinear shortcut. Admission preparation, digest and memory costs must be counted separately from query work. Work fields count symbolic operations or affine compositions, not wall time and not directly interchangeable.

## Development sequence

VLM-002: native x86-64 transition, typed ABI and full word operator parity; bounded allocator, exception isolation and explicit session handles.
VLM-003: structured applications, checked branching/loops, scheduler and operator profiling; optional session checkpoint/recovery.
VLM-004: integrate existing IFS nonlinear-orbit certificate and observer quotients as qualified operators, using independent verifier and existing lineage format.
VLM-005: E-CPU native registered operator transport, receiver-side authority and failure recovery. No new authentication or authority ledger.
VLM-006: resident model, immutable tensor source, per-session causal state; first exact source-parity then qualified layer/path reductions.
VLM-007: model proposes plans/Grounds, separate verifier admits, kernel measures end-to-end cost and can revoke on scope change. Run development workloads through this interface.

## Provenance and boundaries

Independent implementation, not copied from llm.asm. Studied MIT-licensed upstream [SMP dispatch](https://github.com/alesha-pro/llm.asm/blob/main/02-baremetal-os/smp.asm) blob e155ac4e7eab0bd6b118514d935c10f52196c63a and [transformer](https://github.com/alesha-pro/llm.asm/blob/main/shared/transformer.asm) blob ca37711f0b43771d8df134e5d89d20dea41a2473. Upstream uses x86-64 AVX2 and Qwen3; this is a new scalar boot substrate, not a port or Qwen inference benchmark. Related in-space resources: [RCG-005 nonlinear orbit](../real_connectome_ground/continuity/nonlinear_orbit/README.md), [PGT observation policy](../procedural_ground_navigation/README.md), and [temporal coordinate format](../../formats/temporal-coordinate-v2). These are identified for integration, not yet imported. VLM-001 trusts its local Python process, has no hardware security isolation, persistent state, network, floating point or loaded neural model. Hosted CI is the evidence gate.
