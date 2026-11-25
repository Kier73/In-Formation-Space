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

## VLM-004 — resident computational applications (first self-use)

A native straight-line application can construct an affine graph from earlier word results, propose and independently admit a Ground, publish the graph, spawn processes, seek, read, combine observations and emit results. Registers are write-once and typed WORD/GRAPH/PROCESS; validation checks dependencies, unused fields, and output capacity before execution. The 128-instruction/32-register budget and 1024-node graph capacity bound work. No arbitrary native bytes, addresses or external handles enter application instructions. Temporary graphs/processes are released on success or failure, and outputs are buffered until success. BUILD and LEARN mutate the active staging authority even if a later instruction fails; published graphs remain unchanged. The interpreter is serial, not a concurrent scheduler or privilege boundary.

Native discovery proposes affine coefficients by observing the original graph at 0 and 1, then calls the existing exact coefficient checker. It recognizes the canonical nonlinear chart by its candidate literals and checks the entire graph. It returns 0 if no witness is admitted, 1 for affine, 2 for chart. Sampling proposes; verification admits. There is no guarantee of discovery for arbitrary graphs.

### Serial ABI

Commands A(count), I(index,op,d,a,b,lo,hi), E(no arguments), L(no arguments) stage and execute applications or discover the active Ground. E returns APPLICATION followed by the hex output count and word values. L returns RESULT kind 00000000.

| Opcode | Name | Fields |
|---|---|---|
| 0 | CONST | d, lo |
| 1 | BUILD | a,b word registers, lo depth (1..510) |
| 2 | LEARN | d word (Ground kind) |
| 3 | PUBLISH | d graph |
| 4 | SPAWN | d process, a graph, b seed word |
| 5 | SEEK | a process, lo/hi absolute time |
| 6 | READ | d word, a process |
| 7/8/9 | ADD/MUL/XOR | d word, a/b words |
| 10 | EMIT | a word |

Unused fields zero. BUILD constructs a repeated affine chain using the existing descriptor authority. It does not synthesize arbitrary graph families yet. Applications can operate on any preloaded graph via LEARN/PUBLISH.

### Local evidence

`make && python3 -m unittest -v test_core test_process test_capsule test_application`: 12 groups passed in 1.802 s. Boot image 17,052 bytes, text 11,129 bytes, BSS 276,800 bytes, no undefined symbols in linked ELF64. 128 deterministic randomized applications each build/learn/publish two graphs, with the first distant observation determining the second graph's coefficient. Results checked against Python full-graph and affine composition references; 256 graph publications and 80 forced runtime failures left all eight graph slots reusable. Type confusion, forward/uninitialized references, register overwrite and inadequate output capacity rejected. Nonlinear discovery admitted the canonical chart but rejected square and xor examples. The guest test now includes application bytecode; it awaits QEMU.

### E-CPU integration boundary

Inspected E-CPU revision 09a9058a43c139c476609954636e17e7fadcfd37: [M2 computational host](https://github.com/Kier73/E-CPU/blob/09a9058a43c139c476609954636e17e7fadcfd37/mailcpu/computational_host.py), [VL-I temporal host adapter](https://github.com/Kier73/E-CPU/blob/09a9058a43c139c476609954636e17e7fadcfd37/mailcpu/vli_temporal_host.py), [M2/M3 integration tests](https://github.com/Kier73/E-CPU/blob/09a9058a43c139c476609954636e17e7fadcfd37/tests/test_vli_temporal_host.py). Next qualify VLM artifact identity through M1/M2, bind a pure capsule observation operator to the pinned implementation, independently verify the receiver's result, then use existing M3 for durable process continuation. No parallel authority protocol; no E-CPU execution claimed in this increment.

## VLM-005 — first E-CPU M2 capsule adapter

`ecpu_bridge.py` admits a bounded inventory of the compiled hosted VLM library, capsule worker, adapter and relevant sources into E-CPU's existing computational artifact manifest. The compiled binary is bound by its actual bytes, not inferred reproducible from source. The existing M2 profile binds the artifact, runtime and single pure operator `vlm.capsule.observe`. Each request rechecks artifact bytes and starts an isolated Python interpreter subprocess running the admitted capsule worker and native core; no shell, request-provided code or executable path. The returned observation is bound to the capsule digest. Host-local trusted filesystem is required; hash checks do not protect against a privileged actor racing file replacement. M2 receipts are existing E-CPU receipts, not new signatures or consensus.

Local worker test: both affine and nonlinear capsules reconstructed, and rehashed invalid witnesses refused. `python3 -m unittest -v test_ecpu_bridge.Bridge.test_fresh_worker` passed. Real M2 integration requires the pinned E-CPU checkout; CI exercises two LocalComputationalHost identities, matching semantic output/digest, source and profile receipt identity, invalid operation/witness refusal and post-load artifact tamper rejection. E-CPU is unavailable locally; this gate has not run yet. This is not a network or M3 durable session test. Subsequent work should use existing M1 page backing and M3 session CAS, then authenticated Transit paths and independent host deployments.

## VLM-006 — native neural resident and verified proposal

A fixed-geometry recurrent tensor core (6 inputs, 8 hidden state coordinates, 3 logits) uses 147 signed Q4 parameters in [-127,127]. Model load is staged; replacement refuses while any of eight generation-tagged recurrent sessions is live. Input and hidden bounds keep int32 accumulators safe. Invalid inputs do not mutate a session. Hidden recurrence is clip((16*b + W*x + R*h)/16,0,127) with integer truncation toward zero; logits are unscaled integer accumulators (Q8). Independent Python parity checks 1,024 recurrent steps across eight sessions with random nonzero recurrent weights.

Parameter order: W (8x6), R (8x8), hidden bias (8), output matrix (3x8), output bias (3). Matrices row-major. Wire weights and inputs encode signed value v as v+127. Serial N begins model staging, W(index,encoded), V commits, U opens a recurrent session, F(handle,6 encoded words) returns NEURAL plus three signed logits in two's-complement hex, Y(handle) closes, Z(no args) returns RESULT proposed Ground kind and admitted kind. The application instruction 11 POLICY(d) evaluates a stateless neural proposal against the active graph and returns the admitted kind (0 = no admission). It never accepts the prediction as mathematical authority.

The retained model in policy_weights.json is a real supervised model: train_policy.py uses 2,000 synthetic graphs labelled by the actual native discovery verifier, 600 full-batch gradient updates with NumPy, then Q4 quantization. Six lossy binary graph features (bitwise, comparison, directly nonconstant multiplication, canonical chart geometry, AND, no MUL) are extracted natively. The policy has zero recurrent weights; generic recurrence is separately tested, not trained here. This is a small learned selector, not a language model. The held-out seed uses the same generator families, not out-of-family generalization.

Held-out 1,000 graphs: 817 matching route predictions, 723 Grounds available to ordinary native discovery, 622 admitted by neural selection, 101 missed, 82 invalid nonzero proposals rejected, zero observed incorrect admissions. Candidate selection is intentionally not followed by automatic fallback in this experiment, so misses remain visible. A valid chart and a tampered chart can have identical features; the representation is not sufficient to decide admissibility. The model has no demonstrated cost advantage over the ordinary verifier. Exact admission remains required; next measure feature acquisition cost, compare simple lookup and rule baselines, then use fallback when necessary.

Local evidence: 19,908-byte compiled ELF32 boot envelope, text 13,566 B, BSS 278,348 B; no undefined symbols in linked ELF64. `make && python3 -m unittest -q test_core test_process test_capsule test_application test_neural test_ecpu_bridge.Bridge.test_fresh_worker`: 16 tests passed (4.752s), including resident application policy and tamper rejection. NumPy 2.3.5 used for local training; tests consume retained weights without NumPy. Guest and real M2 integration remain pending. E-CPU bridge inventory now includes neural.c as a native build dependency.

### Representation and cost audit

Run `python3 evaluate_policy.py` after building. On the same 1,000 held-out graphs, the six binary features produce only four distinct feature vectors, two with conflicting labels. Even the best deterministic classifier chosen retrospectively on these held-out labels could predict only 825/1000 correctly from those features. The trained neural policy achieved 817/1000, near that finite-sample ceiling; this is not a generalization bound. A majority lookup learned from the training set admitted exactly as many Grounds (622) as the neural policy. Exact discovery admitted 723; adding exact fallback after neural nonadmission admitted 723, with 378 fallback calls. No incorrect admissions observed across any route.

One local timing pass, summing per-query wall time over 1,000 cases, excluding graph staging but including Python/ctypes overhead: exact discovery 0.873 ms, neural 1.683 ms, Python lookup 2.372 ms, neural plus fallback 1.698 ms. Not a controlled microbenchmark or bare-metal measurement; exact discovery is faster on this workload. Do not interpret the Python lookup time as a native table baseline. The learned model is useful as an experimental observer, not yet an accelerator. Future experiments need harder verifier costs, information-bearing features and cost-sensitive observation selection.

CI is separated into hosted native, guest, and E-CPU gates so a missing dependency in one path cannot prevent another from executing. The neural guest test exercises recurrent wire parity, weight replacement fencing, stale handles and rejection of a tampered chart. Guest execution itself has not been observed locally.

## VLM-007 — learned sensing and byte Grounds

A hosted observer constructs lossless Grounds for immutable byte strings of 1..65536 bytes using raw identity, periodic (period <=16), modular affine byte ramps, and sparse zero-default representations. Every compressed proposal is checked against the entire original source. Failed proposals return exact raw identity. A separate certification pass checks all bytes and binds SHA-256. Ground actions read arbitrary ranges and sum byte values over ranges; periodic/ramp sums avoid expanding the entire requested range and sparse sums visit entries in the range. Size is a logical descriptor size estimate (not serialized wire length or Python memory). No semantic equivalence of executable programs follows from byte compression alone.

The observer learns a bounded decision tree choosing both sensors and actions. Each sensor samples at most 16 bytes at prefix, tail, middle or stride positions, interpreted into a categorical signature. Training uses 400 synthetic sources (seed 771) and separately evaluates 400 held-out sources (seed 772), from the same generator families including corrupt repetition and deceptive zero prefixes/tails. The first objective predicts the smallest supported candidate, with a sensor penalty; the second learns per-source measured acquisition and retained representation costs. Minimize read_bytes + weight * encoded_bytes; the training model charges 16 bytes per sensor, a conservative bound. The learner sees actual measured route costs, not just codec labels. Neither sensor signature nor training result is an admission proof.

| Route | Source bytes read | Logical encoded bytes | Matches exhaustive size | Fallbacks |
|---|---:|---:|---:|---:|
| Raw identity | 455258 | 457258 | 203 | 0 |
| Exhaustive supported proposals | 962829 | 230868 | 400 | 0 |
| Fixed prefix | 588487 | 237998 | 392 | 103 |
| Label-trained adaptive | 547858 | 251832 | 383 | 24 |
| Cost-trained, weight 1 | 485514 | 309678 | 332 | 25 |
| Cost-trained, weight 4 | 582151 | 234063 | 397 | 61 |
| Cost-trained, weight 16 | 582149 | 233335 | 398 | 60 |

All 400 full reconstructions and range sums matched per route. These are logical source-access counts including candidate verification and fallback, excluding offline training and optional subsequent certification, not physical I/O measurements. Raw captures bytes directly with no redundant admission scan. Exhaustive means smallest among implemented proposals, not universal optimal compression. This implementation is hosted Python, not native kernel code. It does not yet serialize Ground descriptors into a wire format.

Real-artifact negative control: core.c, application.c, neural.c, capsule.py, policy_weights.json and the locally compiled vlm64.elf all reconstructed exactly and were SHA-256 certified; the selected representation was raw for all six. The executable triggered a failed compact proposal and fallback. The learned observer is not universally advantageous. The next experiment should extend the sensor/codec catalogue to heterogeneous block partitions, typed source structures, and compositional action queries; fit costs including training, certification, memory and action frequency.

Related prior work at IFS revision a1b3a88349b7624de140d12d29685a79305d1266: distinction refinement, adaptive attention policy and RCG-006 observer quotient. This increment independently implements a finite cost-sensitive sensor tree for byte sources rather than importing their solvers.

Reproduce: make; python3 -m unittest -v test_byte_ground; python3 byte_ground.py. Local combined hosted suite: 21 tests passed (including five new tests, 1200 randomized range checks, tamper rejection, bound tests and six actual artifacts). Guest and real E-CPU gates remain separate.

## VLM-008 — compositional Grounds and indexed actions

A byte source can contain multiple different structures. The compiler now selects verified leaves independently over a midpoint partition tree (minimum child extent 64 by default), and chooses whether a split earns its cost. Dynamic programming minimizes sum of leaf wire bytes plus optional integer weight times a full-leaf sum-work proxy. The proxy is not measured latency or the actual indexed query cost. This is exact over the specified split tree and generated candidate set, not arbitrary segmentation or universal optimal compression.

The recurrence is J(I)=min(minimum candidate leaf cost, J(left)+J(right)). Each leaf costs at least six wire bytes and one work unit, so a candidate at or below 12+2*weight cannot be improved by splitting. The compiler prunes that subtree. Training is not required for this bound; the VLM-007 learned observer remains a separate experiment. The compiler buffers the full source once, then measures internal candidate reads separately. Source certification charges another full read.

VLG1 wire: 4-byte magic, little-endian u32 source length and leaf count, then leaves: u8 kind, u32 length, payload (raw bytes; u8 period length + pattern; two u8 ramp values; u32 sparse count + repeated u32 position/u8 value). Decoding checks size bounds, complete extent, canonical sparse ordering, positive lengths, known kinds and trailing bytes. The encoding is deterministic for a given leaf sequence, not unique for a source. Restore requires an independently supplied source SHA-256 and reconstructs all bytes once for verification. This is integrity, not authentication. The receiver builds an offset and cumulative sum index; interval reads navigate to intersecting leaves, sums use two prefix queries and do not visit intermediate leaves. Construction and restore charge index preparation; index memory is not included in wire size.

Local results (26 hosted regression tests passed, 5.236s): 1,000 randomized mixed-source interval reads and sums, 60 random incompressible sources, boundary checks through 65,536 bytes, malformed wire and tamper rejection, and pruned/unpruned equivalence at weights 0,1,16.

| Source | Raw source bytes | Single Ground wire | Fixed 256-byte partition | Adaptive midpoint wire | zlib |
|---|---:|---:|---:|---:|---:|
| 100 synthetic mixed objects | 204800 | 206500 | 58200 | 55300 | 83423 |
| Actual vlm64.elf | 19908 | 19925 | 16453 | 16059 | 8165 |

The synthetic corpus shuffles four deliberately structured 512-byte regions per object. Adaptive partitions outperform fixed partitions and zlib here; this is not a general compression claim. The executable selects 22 leaves (raw, periodic, sparse) and zlib compresses it much further. All five other real artifacts (core.c, application.c, neural.c, capsule.py, policy_weights.json) select single raw leaves; zlib wins for each. Source executable SHA-256: 31496efd9960949d26376a85f569ab1d096cc65ad5308b45e5497946175b5581 (local build; CI builds may differ).

On the 100 synthetic objects, pruning reduces internal candidate reads from 3701432 to 1772776 and explored intervals from 6300 to 2100 with byte-identical output to unpruned DP. External source acquisition plus independent certification totals 409600 bytes. For the executable, internal reads fall from 399833 to 327935, intervals 511 to 423, external reads 39816. These are logical reads, not physical disk/network IO. Local compiler time for the executable was 13.1ms in one pass. Offline comparisons and receiver verification are not included in that timing.

Reproduce: make; python3 -m unittest -v test_compose_ground; python3 benchmark_compose.py. Hosted only. No guest/native codec execution or E-CPU transport is claimed. Next: typed boundary proposals (ELF sections, tensor headers), adaptive cost-labelled split decisions, and native VLG1 realization with independent admission.

### VLM-008b — interpret a typed source as another partition sensor

A bounded ELF header/section-table reader proposes byte boundaries from the source's own metadata. It supports ordinary little-endian ELF32/64 sections, checks all referenced file extents, ignores NOBITS/null payloads, and falls back on invalid or unsupported headers. This is a partition hint, not validation of executable semantics. The compiler compares section-guided composition with midpoint-only composition and selects the smaller exact wire.

Local actual ELF32 image: reading 372 metadata bytes yielded 13 boundaries (including 0 and end); section-guided wire is 15981 bytes in 15 leaves versus midpoint 16059 bytes in 22 leaves. Exact reconstruction and source digest matched. The extra search is expensive: combined internal candidate reads 572244 versus midpoint 327935, 763 intervals versus 423, buffered logical copy bytes 39816, external reads 20280 before separate full-source certification. A savings of 78 wire bytes does not justify the extra acquisition for every intention. This is a deliberately exhaustive comparison, not a cost-optimal policy. ELF64 parsing has not been exercised by the actual-image test. Malformed section offset and non-ELF fallback are tested. The full hosted suite now passes 28 tests (5.389s locally). No changes to the native executable or guest/network verification status.

Next: learn whether to engage the metadata sensor using measured action costs, rather than always paying for both routes; add source-type sensors and direct realization for the VLG1 wire.

## VLM-009 — learned operator vocabulary and parameterized application Grounds

The hosted learner now proposes two reusable representation families from examples rather than requiring each literal or template to be specified by hand.

**Literal operators.** Mine repeated 8/16/32-byte substrings of raw leaves, rank a bounded shortlist of 512 candidates, greedily cover nonoverlapping occurrences, then compare vocabulary prefixes (0/8/16/32/64 or candidate count) on disjoint validation data. Admission includes the complete vocabulary wire cost. Exact suffix dynamic programming minimizes raw-run/reference encoding within each existing raw leaf; the recurrence is D(i)=min(5+j-i+D(j), 2+D(i+|w|)) over j>i and matching words w. A maintained suffix minimum avoids enumerating every raw-run length. Compact existing leaves remain unchanged. Use VLG1 if the new program is not smaller. VLV1 binds up to 64 distinct words; VLP1 binds its SHA-256 plus typed leaves and two-byte word references. Receiver validates the entire source against an independently supplied digest. Indexed range reads and sums remain available.

**Parameterized operators.** Learn equal-length byte-column signatures over up to 256 examples. Constant columns are fixed; identical nonconstant columns form one shared input coordinate. The learned source law is B[i]=fixed[i] outside variable positions, and B[i]=value[group(i)] otherwise. Template VLT1 contains zero-placeholder fixed bytes and disjoint ordered position groups; VLA1 carries its SHA-256 and one byte per group. A candidate instance is checked byte-for-byte against the source; counterexamples fall back to VLG1. Receiver reconstructs and hashes independently. A fixed-byte prefix-sum index plus position-group counts computes arbitrary interval sums without full instance expansion. Template qualification charges its entire wire on validation; it does not prove future examples obey the observed equalities. It is a learned byte constructor, not new arbitrary executable instructions or a verified semantic optimization.

### Local results

35 hosted tests passed in 6.169 s. Seven new tests cover exact shortest-path comparison against exhaustive raw-run DP (100 cases), held-out motif reconstruction, absent-benefit rejection, malformed wire, wrong vocabulary/template identity, overlap and counterexample fallback, and 1,000 randomized template range queries.

| Held-out corpus | Composite VLG1 total | Learned vocabulary incl. shared definition | Independent zlib streams |
|---|---:|---:|---:|
| 24 synthetic mixed motif objects | 37328 | 14377 | 17982 |
| 5 actual machine artifacts | 28308 | 28308 | 12537 |
| 64 native application descriptions | 23699 | 23699 | 7899 |

The synthetic corpus deliberately shares 12 motifs across independent arrangements (12 training, 8 validation, 24 held out). All 12 proposed words qualify, 401 bytes of shared vocabulary included. Real artifact training uses core.c/application.c/capsule.py/test_core.py, validation uses neural.c/test_application.py, and test uses kernel.c/test_neural.py/test_process.py/policy_weights.json/vlm64.elf. Zero of 32 proposed words qualify. The executable is derived partly from training code, so this is a held-out file, not fully independent source content. No learned literal words proposed for the application corpus because existing composition already captures its raw-leaf structure.

**Application template breakthrough:** Train on 16 serialized native workload descriptions, validate on a distinct 16, then freeze and test 64 further randomized seed/time pairs (same workload family). The learner sees only bytes, not instruction fields. It recovers 12 variable byte groups covering 20 positions of a 504-byte application (the remaining 484 bytes fixed). The template costs 604 bytes and each instance 48 bytes (36-byte header/digest plus 12 values). Validation total is 1372 versus 5936 for VLG1. Held-out total is 3676 bytes including template, versus 23699 for VLG1, 7899 independent zlib streams, and 32256 raw bytes. Template digest: 8b84ef4b8ac9f4b510b3dfd2799a92be937793644b6065bb905ec16851f8acd4. Every held-out application was reconstructed, submitted through the actual hosted C application interpreter, and its five emitted values checked against independent Python affine calculations. All 64 pass; the literal baseline was also reconstructed and executed. This is reuse of a known workload family with novel inputs, not arbitrary program synthesis. zlib uses independent streams; no trained/shared-dictionary zlib baseline was run. Storage comparisons include definition and wire headers but not external source digest, index memory, training or computation time; no end-to-end speedup established.

Reproduce: make; python3 -m unittest -v test_vocabulary test_template_ground; python3 benchmark_vocabulary.py. CI executes the same campaign. Both learners and serialization remain hosted Python; actual application execution uses the unchanged C core. Guest/E-CPU qualification remains pending. Next: learn piecewise/equivariant templates for varying geometry, compare shared-dictionary compression and measured query costs, then lower qualified constructors to native typed operations.

## VLM-010 — native admitted application constructors

Learned VLT1 templates may now be lowered into the native C application authority without constructing a complete new instruction stream for every invocation. The existing interpreter is refactored around one instruction reader; ordinary applications still stage and type-check every instruction. A constructor stages fixed instructions and variable-position bindings once, then checks the entire invariant structure and static output count before publication. Only unrestricted CONST low immediate bytes and SEEK low/high immediate bytes may vary; all other fields, including BUILD depth, opcode, register identities and dependency structure, remain fixed. Zero placeholders, disjoint patch positions, in-range groups and complete group use are required. Therefore every assignment of admitted byte coordinates preserves the static type/operand checks. Runtime resource checks and cleanup still apply.

Native C ABI: tpl_begin(n,k), tpl_put(i,AppInsn), tpl_patch(byte_position,group), tpl_commit() -> nonzero local generation, tpl_execute(generation,values,n,outputs,capacity,written). Up to 128 instructions and 128 byte coordinates. Two static banks preserve the old template when candidate staging fails; successful publication invalidates the old generation. There is one active template, serial execution, trusted pointer ABI, no native SHA-256 or guest serial commands for this path yet. Hosted VLT1 decoding and identity validation remain separate; the local generation is not a portable identity. This is not permission to execute arbitrary machine code.

Local evidence: 38 hosted tests passed in 5.605s. Three additional tests cover 256 independently randomized application instances at uint64 times (all five outputs checked against Python references), structural patch rejection, unused coordinates, invalid dependencies, stale generations, short parameter/output buffers and extreme byte values. Freestanding image 22080 bytes, linked ELF64 text 15358 bytes, BSS 286604 bytes, no undefined symbols. Guest execution remains pending. No change to existing E-CPU authority.

One local hosted timing pass for 1000 matched applications: ordinary unpack/stage/check/execute 47.015 ms; direct parameter binding/execute 29.178 ms; one-time template learn+validation 12.085 ms, native staging/admission 0.083 ms. Inputs and reference results prepared before timing; timing includes Python/ctypes submission overhead, excludes per-source matching, source digest verification, training fixture generation and reference computation. Direct route executes one bound instruction at a time, not zero instructions. Static instruction checks and staging drop from 21000 to 21 each plus 20 patch submissions at installation. The observed advantage is specific to this workload and interface; not a bare-metal or distributed speedup. Reproduce: make; python3 -m unittest -v test_native_template; python3 test_native_template.py --benchmark.

Next use a source-pinned constructor artifact as a typed E-CPU M2 operation, with portable definition digest distinct from the local generation. Validate at a fresh receiver, keep request coordinates and semantic outputs in the existing receipts, and use existing quorum authority for durable publication. Batch or resident execution should amortize receiver preparation; independent verification and transport costs must be charged.

## VLM-011 — experience formation, behavior shapes and counterexample-driven tool refinement

The hosted experience environment uses the existing native application authority and learned template lowering, not a parallel interpreter. Task addresses (family, phase, index) deterministically generate word and uint64 coordinates. Task-level Python arithmetic/affine reference functions independently predict expected results. Encounters retain task, full application bytes, SHA-256, normalized dependency shape, declared instruction/tool sequence, actual native output, independent reference, and verification status. The tool sequence is a source descriptor, not measured per-instruction dispatch telemetry. The ledger rejects duplicate task addresses and source digests; records are chained by canonical JSON digest. Replaying regenerates tasks and reruns native execution, checking the externally supplied head. Hashes are integrity evidence, not authenticated host receipts. The summary binds selected runtime/source hashes, catalogue definitions and final route results.

### Curriculum and refinement

Initial stream: 10 compose tasks, 1 arithmetic, 1 navigate, 1 deliberate invalid dependency. The curriculum selects the family with the largest verified encounter deficit against a configured quota (12 valid encounters per family, 4 negative controls). Families and quotas are supplied by the environment, not autonomously invented. A separate validation phase qualifies templates grouped by a normalized instruction shape that masks only CONST low and SEEK low/high immediates. Template admission charges complete definition bytes, validates native static constraints, and compares each validation output with ordinary execution. Failed dependency examples never become positive training data.

After initial qualification, the challenge family varies two previously coupled temporal coordinates independently while keeping the normalized shape unchanged. All eight challenges fail the initial template match. The mismatch triggers 12 fresh training and 12 fresh validation encounters from that family. Relearning the shared shape splits eight byte-coordinate groups (12 -> 20), retains the former family and admits the broader template. The challenge cases themselves are retained but not used as training examples. The final cohort is generated after both catalogues are frozen. Each has 32 arithmetic, navigate, compose and fork tasks plus four invalid dependencies.

Local result: 244 distinct baseline encounters (232 verified, 12 expected native refusals), four structural shapes and three learned tools. On 132 final tasks, ordinary and both catalogue routes preserve all 128 valid outputs and four expected refusals. Initial constructor coverage 96/128; refined coverage 128/128. Ordinary submissions decline 36 -> 4; the refined route installs three templates in the grouped final workload. Valid application raw bytes 45,312; parameter payload 2,304 bytes; definition, identity, per-request framing, retained dataset and source matching costs are extra. This is not a total storage or speed claim. Refined compose definition 636 B and 20 parameters, validation wire total 1,980 B versus 8,894 B VLG1 baseline, including definition. Dataset replay in a fresh Python process reproduced all 244 native outcomes and the final route digest. Hosted regression suite: 42 passed in 6.212 s. Four new tests cover curriculum, challenge, replay, rehashed tamper and truncation, shape sensor and final-cohort exclusion. No guest or distributed execution claimed.

Reproduce:
    make
    python3 -m unittest -v test_experience
    python3 experience.py --ledger experience.jsonl --summary experience-summary.json

CI retains the generated dataset and summary as workflow artifacts. Local reference head 1be534aa2e623c3b0f17c6250fcf47f3fc55c7abda74935807995079850388b0; final results digest ab7793af800fdfbeb4845fcb313edf2da1208435536eb3bfd258e18156ca5ebc. Compiled binary hashes may vary by build. The system currently uses a scripted finite environment, fixed quota policy, hosted learning and one active native constructor; the catalogue is a host-side collection. Future work: dynamically choose challenges by uncertainty and cost, vary instruction topology, retain bounded multi-epoch data with durable identity, and distribute independently qualified encounters through the existing E-CPU authority.

## VLM-012 — experience generated from the acquired tools themselves

The VLM-011 catalogue is permanently retained under datasets/vlm011, with the complete 244-row ledger, catalogue summary and manifest. VLM-012 loads that exact summary by SHA-256, selects the tool with the largest number of still-fixed or coupled permissible immediate-byte coordinates, and independently intervenes on each such coordinate. No new task family is supplied. Mutation operators are restricted to already-supported CONST low and SEEK low/high byte positions; opcode, register dependencies, BUILD depth and other structural fields cannot change. The independent restricted-language evaluator checks affine application results without calling the native interpreter. Its scope is these closed application patterns; it is not an unrestricted verifier.

Eight probe interventions identified eight fixed byte positions (16..19 and 40..43, the first two CONST operands). All eight were outside the parent constructor and changed observed outputs, while native execution agreed with the independent oracle. A new curriculum then generates 16 training and 16 distinct validation applications using the detected coordinates. The initial template and candidate are compared on total definition and per-instance wire bytes, falling back to VLG1 for nonmatches. Candidate native admission and validation execution are required. Only after choosing the candidate is a 64-instance final cohort generated, half original geometry and half expanded coordinates.

Local evidence: 104 new encounters (8 probe, 16 train, 16 validation, 64 final); parent 20 parameters, candidate 28, candidate definition 684 bytes. Validation representation cost falls from 4292 B to 1708 B. Final constructor coverage 32/64 -> 64/64; every final application matched its independent oracle. All 45 hosted tests passed (5.817 s). This changes representational coverage, not the underlying instruction topology or asymptotic execution cost. Generation, admission, matching, and execution costs are not included in the wire comparison. The campaign uses deterministic bounded mutations, not unconstrained task synthesis.

Dataset retention experiment: datasets/vlm012/recipe.json stores the exact parent identity, generator blob identity, recipe phase counts, final report SHA-256, candidate identity and measured results. The complete 26849-byte outcome report (including generated coordinate recipes, source identities and outputs) can be reconstructed by running the source-pinned campaign. The CI gate checks exact regenerated report bytes against the retained SHA-256 and uploads the expanded report. This is a replayable structural dataset, not a separately stored full outcome file or an authenticated host receipt.

Reproduce: make; python3 -m unittest -v test_adaptive_experience; python3 adaptive_experience.py --output adaptive-experience.json. Next: challenge instruction topology with typed composition, choose interventions by measured marginal information and cost, and admit newly formed tools on independent environments. Guest and real E-CPU qualification remain pending.
