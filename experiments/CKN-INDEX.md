# CKN — Causal Kernel Navigation experiments

This is the entry point for the CKN research series. The experiments live under `experiments/` in **separate, numbered directories**, preserving their independent scripts, results, and original upload provenance. CKN-003c is a follow-on experiment to CKN-003, not a replacement for it.

| Experiment | Question | Source and retained outputs | Verification scope |
| --- | --- | --- | --- |
| [CKN-001 — Causal Kernel Navigation](CKN-001%20Causal%20Kernel%20Navigation/CKN-001%20Causal%20Kernel%20Navigation.md) | Can algebra, finite orbit atlases and composable stream summaries replace repeated stepping? | `run_ckn.py`, `results.json` | Reported exact and finite cross-checks; one-process numerical simulation |
| [CKN-002 — Composed Atlases](CKN-002%20Composed%20Atlases/CKN-002%20Composed%20Atlases.md) | Can products and one-way cascades be navigated without a full joint-state table? | `run_ckn2.py`, `results_ckn2.json` | **Staged** results; optimized final script was not rerun end-to-end when uploaded |
| [CKN-003 — Spectral Navigation](CKN-003%20Spectral%20Navigation/CKN-003%20Spectral%20Navigation.md) | What do zeta-zero spectral representations buy for local and aggregate prime observations? | `run_ckn3.py`, `results_ckn3.json`, `zeta_zeros_t6000.npy` | Reported single complete run; sampled numerical checks, not a proof of RH or zero completeness |
| [CKN-003c — Mixed Navigation](CKN-003c%20Mixed%20Navigation/CKN-003c%20Mixed%20Navigation.md) | Can spectral or smooth estimates guide exact prime indexing with an independently exact counter? | `run_ckn3c.py`, `results_ckn3c.json` | **Staged** run; exact answer checks reported, not one clean full-script rerun |

## Layout and dependency contract

- Each numbered folder owns its own research note, executable experiment, and retained JSON results; the existing folder names and URLs are intentionally preserved.
- **Only CKN-003 owns the generated binary zero table** `zeta_zeros_t6000.npy` (a NumPy `.npy` array). Do not duplicate it in CKN-003c.
- **CKN-003c reads CKN-003's zero table** from the sibling directory by default; optionally set `CKN_ZEROS_PATH` to an explicit file. Its output `results_ckn3c.json` remains in its own directory, or in `HERE_OVERRIDE` when the script is executed with that override.
- The existing JSON files record experiment outcomes; they are not independent proof certificates and should not be presented as fresh CI measurements.
- These scripts operate in one local process and do not claim physical-path execution or independently authenticated host receipts.

## Reproduction (from repository root)

Python with NumPy is required.

```sh
python "experiments/CKN-001 Causal Kernel Navigation/run_ckn.py"
python "experiments/CKN-002 Composed Atlases/run_ckn2.py"
python "experiments/CKN-003 Spectral Navigation/run_ckn3.py"
python "experiments/CKN-003c Mixed Navigation/run_ckn3c.py"
```

CKN-003 must run before CKN-003c **only if the retained `.npy` file is missing**. The uploaded zero table already exists at the CKN-003 path. CKN-002 and CKN-003c have longer runs; the reproducibility status above distinguishes retained staged results from a one-shot replay.

## Mathematical and evidence qualification

The 20 November 2026 Alpöge/Claude **Riemann-hypothesis proof announcement** is external to the CKN code and should not be represented as established merely because a CKN numerical experiment ran. Independent Lean verification and broader mathematical assessment must be distinguished from this experiment's observations. The analytic Schoenfeld estimates used in CKN-003 and CKN-003c are **conditional on RH** unless that external theorem is established independently. In particular, CKN-003c's exact `p_n` answers come from the exact `π(x)` anchor and sieve; the estimates affect cost, not correctness.

Future names referred to in the notes, including CKN-003b, CKN-003d and CKN-004, are proposals and are not counted as uploaded runnable experiments here.

## Lineage

CKN-001 builds on E-CPU law certification and prior finite-orbit and in-transit work; CKN-002 uses component atlases, residue-class CRT and sender-period maps; CKN-003 studies a different, spectral family of observables; CKN-003c combines estimation and exact checking. This index is intentionally navigational: it does not merge or alter experimental results.
