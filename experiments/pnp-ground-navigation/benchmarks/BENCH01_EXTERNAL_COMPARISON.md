# BENCH-01E — External 3-SAT and production CDCL comparison

**Research checkpoint:** 22 November 2026. **Challenge:** 01/20, direct 3-SAT. **Stage:** implemented, locally adversarially tested; independent external-corpus execution and cross-platform CI are separate evidence to be appended after actual runs. No claim that P versus NP is resolved.

## Purpose and distinction from BENCH-01

The original [BENCH-01](BENCH01_3SAT.md) measures the problem-formed SAT interpreter (SFI-001–004) and the source-proof-qualified fallback (SPN-008) on deterministic instances, with explicit SAT/UNSAT/UNKNOWN distinctions. Those fixtures are not independent real-world benchmarks. This stage adds **externally authored random 3-SAT formulas** near clause-to-variable ratio 4.3, plus a real industrial-strength **CaDiCaL 1.9.5** CDCL solver accessed through the pinned PySAT distribution. Each method consumes exactly the same source clauses, and all solver costs are reported separately rather than hidden in compilation.

**Source honesty:** these small third-party instances are *not* SAT Competition 2026 Main Track instances. The [official 2026 Main Track URI manifest](https://github.com/satcompetition/2026/blob/d2f8f186dacc48b9bab7e4374aef0a3f46b96582/downloads/track_main_2026.uri) is separately pinned for a subsequent larger benchmark. Do not attribute our external-corpus measurements to a SAT Competition ranking.

## Provenance and source admission

Chosen external corpus: [TimurIbrayev/SATsolver](https://github.com/TimurIbrayev/SATsolver), commit `b285082ead7a89f51f50c0dc3a937ddefa3328ee`, paths below `benchmarks/uniform_random_3-sat/`. Small cohort, **two SAT-labelled and two UNSAT-labelled 50-variable, 218-clause instances**, with optional extension to two 75-variable, 325-clause cases. The publisher's labels are kept as untrusted metadata, not mathematical certificates.

The corpus is fetched via `https://raw.githubusercontent.com/` only at the immutable repository commit. Each downloaded original byte stream must match its declared Git blob SHA-1. The program also stores an independent SHA-256 of exactly downloaded bytes and a semantic CNF digest. The pre-existing strict `parse_dimacs` verifier checks header and all clauses. This does not authenticate the third party as an oracle or render SHA-1 a contemporary collision-resistant signature: the pinned commit, HTTPS transport and recorded SHA-256 all matter. Downloaded corpus files remain local artifacts, not vendored into our source repository.

| ID | External source subpath | Git blob SHA-1 | Publisher label only |
|---|---|---|---|
| sat50-a | `sat_50_218/01.cnf` | `9732bcb915dbb788fc6db5f336e9481e15cb4b8d` | SAT |
| unsat50-a | `unsat_50_218/01.cnf` | `9aa88f52c8a2bd54c58b0244861633b37d3ddffe` | UNSAT |
| sat50-b | `sat_50_218/02.cnf` | `a37dfc28f0c7266cd4f6e00615ad35934b24b30e` | SAT |
| unsat50-b | `unsat_50_218/02.cnf` | `23b7c16f4bf468ba89a92c242dbcd7f5614d5a1c` | UNSAT |
| sat75-a | `sat_75_325/01.cnf` | `5c224b84323ba90291a2c73275be488c87c182d8` | SAT |
| unsat75-a | `unsat_75_325/01.cnf` | `25bda60ac44c0188b3c044f90f3708067c0fc572` | UNSAT |

The [official 2026 competition manifest](https://satcompetition.github.io/2026/downloads.html) is pinned at `satcompetition/2026` commit `d2f8f186dacc48b9bab7e4374aef0a3f46b96582`, file `downloads/track_main_2026.uri`, Git blob `2b86a4d685b492a844646f378ac3f3415fd131d5`. **No file on that list has been executed in this small-cohort study.** The official rules require a SAT model and, for the Main Track, UNSAT certificates; a raw exit status is not a verified refutation.

## Three independent strategies, identical CNF input

1. **SFI-only:** BENCH-01's `run_case(... spn_fallback=False)`: `self_selecting_sat.choose`, optional Boolean `morphic_sat` interpreter, exact affine `self_forming_sat` interpreter, and independent verification (`morphic_verifier`, `derived_verifier`). Correctness of SAT is checked against the untouched source. When a coordinate budget is exceeded, report `UNKNOWN`, not UNSAT.
2. **SFI → SPN-008:** same source and initial construction, with `direct_sat_compiler.produce_direct_sat` and `verify_direct_sat` invoked only when structural construction cannot decide. A complete UNSAT conflict tree or verified contradictory XOR dependency crosses the process boundary and is replayed by the parent; otherwise return UNKNOWN.
3. **Production CDCL:** `python-sat==1.9.dev13` and its `cadical195` engine. A fresh subprocess solves the identical source. The parent checks every SAT model against the original clauses, so a SAT result can be independently accepted. A bare CDCL **UNSAT is recorded as `UNVERIFIED_UNSAT`** unless corroborated by an independently checked native UNSAT refutation. The CDCL call does not yet emit or independently check a DRAT/LRAT proof. CDCL's raw claim and evidence-admitted status are different fields.

All three attempts run in separate subprocesses with individual wall-clock deadlines and independent timing. Source input admission and downloads are kept outside these three execution timings, and raw SHA-256 values are retained. There is no assertion that the same process can run the three methods in parallel without resource contention. This is a small, uncalibrated head-to-head test, not a production leaderboard reproduction.

## Utilities found in each repository

| Repository | Exact utility or contract | Utilized in this benchmark? |
|---|---|---|
| **In-Formation-Space** | `bench01_3sat.parse_dimacs`, `run_case`, `exhaustive_reference`, source witness checker; `self_selecting_sat.choose` / `realize`, `morphic_verifier.verify`, `derived_verifier.verify_receipt` | **Yes, native execution/parent admission** |
| **In-Formation-Space** | `spectral_phase_navigation/direct_sat_compiler.produce_direct_sat`, `verify_direct_sat` (SPN-008) | **Yes, as fallback with parent proof replay** |
| **In-Formation-Space** | `construction_memory.ConstructionMemory`, `recursive_sat_compiler.refine` | Existing machinery reviewed; **not exercised** in this fixed source comparison. A future same-family source-refinement cohort would measure reuse amortization |
| **VL-I** | `problem_formed_sat` (PFI-004), `problem_formed_revision` (PFI-005), native E-CPU partition publication | Studied as cross-repository extension, **not run** here |
| **E-CPU** | `NavigableComputationDAG`, `TransferableExecutionClaimStore`, Hypervisor, mTLS, IPS-008 receiver effect handoff | Existing runtime/authority evidence; **not invoked** by this local baseline |
| **Virtual-Ground-Interpreter** | `PROOFGROUND_NAVIGATION.md`, proof/observation status and missing evidence distinctions | Informative specification, **not invoked** as a kernel |
| **Navigable-Compute** | NCR-006/007 observer quotient machinery | Examined as future semantic compression, **not invoked** on these CNFs |
| **External CDCL** | PySAT pinned distribution `1.9.dev13`, CaDiCaL `cadical195` | Runs as a truly separate solver, not a direct-SAT wrapper. An UNSAT proof checker is still **in development** |

## Test and build log

**2026-11-22, source discovery.** Inspected SAT Competition 2026's public official manifest and the Tractables SATLIB archive (mostly compressed), then selected an independently authored plain-DIMACS 3-SAT cohort suitable for bounded comparison. The official 2026 corpus is typically not constrained to three literals per clause or the small 8 MiB/64-variable prototype profile. Any future conversion to 3-CNF must preserve satisfiability and independently verify projected witnesses, not silently change source semantics.

**2026-11-22, implementation.** Implemented exact GitHub-source commit and blob validation, bounded fetch with no arbitrary URL input, the native triple-run harness, a separate CaDiCaL worker and parent-side source verification. Declared the CDCL UNSAT verification requirement explicitly rather than counting a solver return code as mathematical proof.

**2026-11-22, negative tests.** Added 13 stdlib `unittest` controls: mutated source refused despite a plausible upstream label, invalid dimensions with a recomputed blob refused, non-pinned URL rejected, false SAT and contradictory models refused, bare UNSAT remains unverified, timeouts remain UNKNOWN, invalid worker protocol and missing optional solver become errors rather than accepted results. **All 13 local tests passed** (standard-library-only, no local PySAT installed). Exact third-party source execution and PySAT installation are deferred to the GitHub Actions native dependency matrix; no local external runtime result is invented.

**Outstanding research:** actual official 2026 Main Track runs with pinned instance bytes; independent CDCL UNSAT proof generation and checking (DRAT/LRAT/FRAT); strong PAR-2 comparison with comparable hardware, independent source families and memory limits; measured construction reuse on changed CNFs; native E-CPU authenticated execution of the same source and exact admissible result.

## Reproduce

From the In-Formation-Space repo root:

```bash
cd experiments/pnp-ground-navigation/benchmarks
python -m pip install 'python-sat==1.9.dev13'
python -m unittest -v test_bench01_external.py test_bench01_3sat.py
python bench01_external.py fetch .external-bench01 --limit 4
python bench01_external.py compare .external-bench01 --limit 4 --timeout 6 --spn-nodes 8192 --output BENCH01-external-results.json
# Optional larger follow-up; more time and memory may be needed:
python bench01_external.py fetch .external-bench01 --limit 6
python bench01_external.py compare .external-bench01 --limit 6 --timeout 12 --spn-nodes 16384
```

Results are JSON with per-source Git blob and byte SHA, every engine's source-accepted verdict, wall-clock and worker timing, native proof kind and refusal reason, and the official-2026-manifest provenance marker. No unaudited `UNSAT` is allowed to masquerade as an independently proven mathematical result. The pre-existing BENCH-01 Markdown log remains the record of the original seeded campaign, and this file is the log for **this external/CDCL extension of Challenge 01**.


## CI measurement checkpoint: externally sourced CNF execution

**Verified 22 November 2026.** [GitHub Actions run 45058493009](https://github.com/Kier73/In-Formation-Space/actions/runs/45058493009), head commit `90ad345479add77afe4eb682f924929abaffcc14`. All four jobs passed on Ubuntu/Windows with Python 3.11/3.13, including 34 local-source and predecessor tests per job, exact pinned-CNF retrieval, genuine compiled `python-sat==1.9.dev13` CaDiCaL execution, and parent source-evidence checks. The Actions artifacts contain full per-instance JSON receipts; the log below records a small reproducible measurement digest.

| Independent 3-CNF source | SHA-256 of downloaded bytes | SFI alone | SFI→SPN proof | CaDiCaL + independent confirmation | SPN DPLL nodes / proof |
|---|---|---|---|---|---|
| `sat50-a` | `b63c897e8cc7974dbb67a20834cc0554ea72ea027eb073902cd5113cb4abcd97` | UNKNOWN | SAT | SAT | 136 / original-source witness |
| `unsat50-a` | `6c98cbb0cdd56e04f16c412a4c44eb83783bb1cbfc8d2568abd535817ab6a3e9` | UNKNOWN | UNSAT | UNSAT | 175 / complete conflict split tree |
| `sat50-b` | `fff791a73b43c0e43397855888a4d03205094f300087e11c85f2d4a4f42e5f60` | UNKNOWN | SAT | SAT | 73 / original-source witness |
| `unsat50-b` | `f01198d4275679505f86bbc310db9d678dbec950e76b622548e9db069c562619` | UNKNOWN | UNSAT | UNSAT | 75 / complete conflict split tree |

Median **end-to-end per-method wall time** per CI platform, milliseconds, from four independent formula cases. These are not repeats of a fixed formula or calibrated hardware comparisons; they include Python startup and source-proof checks where applicable:

| Runner | SFI-only (4 UNKNOWN) | SFI→SPN (4 qualified) | CaDiCaL (4 qualified after SPN corroboration) |
|---|---:|---:|---:|
| Ubuntu / Python 3.11 | 174.91 | 221.69 | 81.94 |
| Ubuntu / Python 3.13 | 189.35 | 222.52 | 86.28 |
| Windows / Python 3.11 | 257.27 | 319.27 | 141.10 |
| Windows / Python 3.13 | 248.44 | 298.86 | 142.46 |

**Adverse result and interpretation.** The current non-affine/affine generated interpreter does not find a qualified complete coordinate representation for these near-phase-transition formulas under its declared budgets. The native DPLL engine *does* produce complete source-replayable evidence in relatively few nodes, and production CDCL is faster on every one of these four cases on each runner. The performance of our *fallback* is not a source of competitive advantage here. The useful engineering outcome is evidence-preserving algorithm selection: the host interpreter must refuse and yield to an effective solver instead of inferring UNSAT from a failed structural construction. A next self-use step should measure which readily observed source features predict this outcome and whether skipping expensive construction pays for itself.

**Verification scope.** GitHub CI reports four qualified results in each of four platform jobs, but there are only **four distinct external source formulas**. Their SAT answers have independently re-evaluated witnesses. Their UNSAT answers are source-admitted by SPN-008 complete DPLL conflict proofs and only *then* used as corroboration for the matching CaDiCaL claims. No independent DRAT/LRAT proof was emitted by CaDiCaL in this run, and no official SAT Competition 2026 Main Track instance was executed. Production CDCL's own claim is recorded separately from the proof evidence used to accept it.

**Implementation repair during CI.** The first GitHub Actions push revealed a YAML parsing failure in an unquoted pip install command containing a colon. The workflow was fixed before tests ran, and the subsequent four-job matrix passed. This was an orchestration defect, not a solver or SAT proof failure.


## Extended independent cohort — 75-variable phase-transition cases

**Verified CI run [45058730719](https://github.com/Kier73/In-Formation-Space/actions/runs/45058730719), 22 November 2026.** The original four fixed 50-variable sources were supplemented by two exact-Git-blob-pinned 75-variable, 325-clause formulas. Each of the four Linux/Windows/Python jobs admitted all six unchanged source SHA-256 identities, ran the compiled CaDiCaL baseline and the native SFI and SFI→SPN paths, and passed source-evidence checks. The actual six-formula per-run JSON is retained in the four Actions artifacts; this log records the observations, not a replacement for the raw evidence.

| Added source | Raw SHA-256 (pinned source) | SFI-only | SFI→SPN qualified | CDCL qualified by SPN corroboration | SPN proof / nodes |
|---|---|---|---|---|---|
| `sat75-a` | `f88b2c86584d60b6bb03609da700addb141540dd091bd72c9476bfc0f21502dc` | UNKNOWN | SAT | SAT | original-source witness / 30 |
| `unsat75-a` | `895875836423eabccaf249396713174f2f8f0a0b2866b6ab09dfabc28acbd452` | UNKNOWN | UNSAT | UNSAT | complete conflict split tree / 297 |

All four platforms agreed on the same **six distinct formulas**: **SFI-only 0 SAT, 0 UNSAT, 6 UNKNOWN; SFI→SPN 3 SAT + 3 UNSAT; CaDiCaL 3 SAT + 3 UNSAT after independent source qualification**. The publisher labels were never used as proof, and the CDCL UNSAT statuses were accepted only after checking native SPN evidence.

Six-case median **per-method end-to-end wall time in milliseconds** (each formula used once per platform; time includes Python startup and source checking):

| Platform | SFI-only (UNKNOWN) | SFI→SPN | CaDiCaL |
|---|---:|---:|---:|
| Ubuntu / Python 3.11 | 197.40 | 306.49 | 83.48 |
| Ubuntu / Python 3.13 | 232.71 | 329.45 | 97.69 |
| Windows / Python 3.11 | 222.17 | 325.55 | 126.95 |
| Windows / Python 3.13 | 199.29 | 263.68 | 116.71 |

For the added `unsat75-a` case specifically, Linux/Python 3.11 source-admitted SPN proof publication required **816.08 ms** end-to-end while the separately run CaDiCaL baseline required **84.01 ms**; the other platforms showed the same ordering, with different timings. This cost gap should motivate adaptive interpreter **construction policy**, not a claim of new SAT asymptotics. The complete SPN refutation is the independent evidence supporting the answer and is more demanding than CaDiCaL's unchecked raw UNSAT claim; comparison therefore includes different verification burdens. Production CaDiCaL itself still lacks an integrated independent DRAT/LRAT proof checker in this benchmark.

**Development action:** treat failed whole-problem compression as an observation for the existing SFI-003/SPN-010 meta-SAT policy machinery. Test a source-only, pre-execution selector on genuinely held-out random, parity and structured-circuit CNFs; charge its training and classification, refuse policies that lower proof coverage or fail a predeclared cost hurdle, and preserve old working policies as recoverable structural memory. No such new policy is claimed here. Official SAT Competition **2026** Main Track instances likewise remain a next experimental tier, not part of this measurement.
