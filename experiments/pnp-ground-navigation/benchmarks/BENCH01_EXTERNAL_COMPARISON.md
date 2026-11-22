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
