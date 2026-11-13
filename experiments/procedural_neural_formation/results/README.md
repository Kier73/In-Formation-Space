# Local verification record

Executed on 2026-11-13 in the supplied Windows workspace, Python 3.13,
NumPy 2.2.5. Related E-CPU/VGI imports used the existing neighboring workspace
copies, which have no local Git revision metadata. Pinned CI checkouts are the
authoritative revision-specific integration run.

- `python -m unittest experiments.procedural_neural_formation.test_formation -v`:
  **17 tests passed**.
- `python -m experiments.procedural_neural_formation.run --output
  experiments/procedural_neural_formation/results/local-procedural.json`:
  **four procedural cases passed**, including exact coefficient checks, scalar
  oracle comparisons, changed-coefficient rejection and E-CPU DAG restoration.
- `python -m unittest discover -s experiments/external_neural_structure_reading
  -p 'test_*.py' -q`: **63 passed, 1 environment error**. The unchanged
  `test_symlinked_shard_is_rejected` could not create a Windows symbolic link
  (`WinError 1314`, missing privilege). This is not a clean full local suite.
- The local `--live` attempt failed during initial Hub metadata lookup with
  DNS `getaddrinfo` failure. No selected tensor payload was read and no local
  live-success report was produced. The separate CI network run must establish
  any claim about real observed parameters.

The retained JSON is the actual local procedural report. It is not live model
evidence. The workflow performs a separate network observation and retains its
report as `pnf-live-observed-and-procedural` only on success.
