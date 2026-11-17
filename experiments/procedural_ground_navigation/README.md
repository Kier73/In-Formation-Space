# PGT-003 — Neural experimental design for intention-relative observation

**Status:** experimentally implemented, directly executed on the local CPU and separate signed observer-worker processes. Native E-CPU integration is a mandatory GitHub workflow gate, **not yet verified**. Stacked research continuation of PGT-002.

## Why this follows the conversation

- COG-006–008 established finite and partially known cognitive Grounds and counterexample-induced revision.
- COG-009 supplied separate signed observer processes with independent enrolled keys and retained disagreement.
- COG-010 shifted from reconstructing full state to **the smallest sufficient observation for an intention**.
- PGT-001 trained genuine neural weights on synthetic full Ground tables, but the exact planner could already use those tables.
- PGT-002 withheld entire generator families and demonstrated active observation; learned answer predictions often lost to exact planning, and out-of-family extrapolations were unsafe.
- **PGT-003 changes what is learned:** a neural *observation policy* trained on cost-aware experiment selection, not a neural claim of final answer truth.

## Actual existing components reused

| Purpose | Existing implementation | How PGT-003 uses it |
|---|---|---|
| Finite function candidates and source protocol | PGT-002 `active_version_space.py` | Reuses exactly 30 distinct functions; no replacement hypothesis library |
| Exact finite Ground labels / neural checkpointer conventions | PGT-001/002 | Reuses canonical JSON, strict finite split semantics, and independent parameter hashes |
| Signed, separate-process host and enrolled public-key identities | COG-009 `Host`, `HostProcess`, `observer_worker._sign` | Reuses the worker IPC and Ed25519 signing/key identity; adds a **new narrow signed query envelope**, not a competing E-CPU Transit |
| HTTP read-only model weights | PGT-001 `http_artifact_path.py` | Reuses bounded, content-addressed local HTTP retrieval, origin failure and corruption refusal |
| Receiver-owned intention sufficiency | E-CPU IOS-001 `plan_sufficiency` | Mandatory exact native conformance test against 90 synthetic finite models |
| E-CPU long-time coordinate navigation | `mailcpu.law_certifier.lcg_navigate` | Mandatory native logarithmic-orbit parity test |
| E-CPU actual authenticated measurement | IOS-003 mTLS / ReliableChannel | Hosted E-CPU regression tests on correction branch `393462c6e0dafba8e0ee22946ae44227c5c6e4e6` (PR #169); **not wired as the COG-009 test transport** |

Source dependencies: checkout PGT-002 PR #265 (including PGT-001) as base, and COG-009 commit `b1aaebbee533c5296cc37c348f96d2f9b5b59456` in `external/cog009/`. The source package contains no signing private keys or private source salts.

## Mathematical experiment

Let the source's unknown target function be a member (or not) of the **explicitly declared** 30-function finite hypothesis family \(H\) on eight 3-bit public feature coordinates. A requested intention is the function value at one coordinate \(q^\star\). An observation host answers one selected coordinate \(q\) at a symbolic cost \(c_q\).

For an inferred set of still-consistent candidates \(V\), a bounded Bayes decision-tree teacher chooses the query that minimizes

\[
C(V) = \min_q\left[c_q + \Pr(0\mid V,q)C(V_{q,0}) + \Pr(1\mid V,q)C(V_{q,1})\right]
\]

until all hypotheses in the remaining version-space agree on the requested *target observation*. The recursion is capped at four steps; direct measurement of \(q^\star\) is always a supported fallback. Finite prior weights are explicit experiment assumptions, **not claims of calibrated external probabilities**.

The resulting synthetic query decisions train a real **shared-action 15→64→48→1 GELU neural scorer**. Its 4,193 parameters are learned with AdamW; they are persisted as a strict SHA-256-pinned, ~17 kB `npz` tensor artifact. Inference receives only the declared prior, action costs, target, and previous observations; it cannot query the hidden source until an explicit selected-host request.

The new unit of learned capability is therefore a candidate *observation choice*, not a model-produced proof, permission grant, or result.

## Direct local results (800 paired cases per distribution)

Mean **symbolic observation cost**, lower is better. These are not measured wall-time or network-energy costs. All methods start from the same initial observations per case. A policy's terminal claim is conditional on the assumed 30-function library; it is not receiver-admitted without extra evidence.

| Policy | In-family mean cost | Prior-shift mean cost | Unresolved in-family / shift |
|---|---:|---:|---:|
| Direct target query | 21.81 | 20.87 | 0 / 0 |
| Greedy intention-specific information gain / cost | 17.52 | 18.30 | 1 / 1 |
| Greedy hypothesis-disagreement / cost | 14.13 | 14.20 | 3 / 3 |
| **Trained neural observation scorer** | **13.13** | **14.09** | 2 / 4 |
| Finite four-step Bayes teacher | 11.85 | 11.80 | 0 / 0 |

This is a positive comparison for **query selection under the declared prior/cost synthetic family**; the teacher is still more cost-efficient, and the neural student can exhaust the query budget before resolution.

### Out-of-family falsifier

On **800 target functions deliberately excluded from the 30-law language**, the trained policy reached 800 seemingly unanimous candidate predictions; **305 were false** under the independently held actual function. This is a strong negative control against declaring learned predictions to be Ground truth. The implementation admits **zero** unproven hypotheses, and separately tests a direct, individually witnessed target query: all 800 synthetic target observations were correct. In 586 cases, an additional target-specific read was necessary, with an extra declared cost of 14,410 units. Hence, the candidate cost savings cannot be reported as verified execution savings on arbitrary unknown sources.

### Real separate-process host experiment

Three child processes use independently enrolled Ed25519 keys and the reusable COG-009 worker transport. They hold a **privately salted** SHA-256-committed eight-value source map. The salt prevents enumeration of the entire low-entropy source from its public root digest.

- One query collects actual signed observations, not answers from the neural model.
- One host is genuinely killed. With its replacement absent, the two remaining hosts disagree and the result stays **unknown**.
- The replacement host boots with its enrolled key, and two matching signed reports resolve the *observation*.
- The model selects additional queries using only the accumulated signed readings.
- A distinct verifier process with no private keys and no source callbacks verifies all **14 signed receipts**, an indexed predecessor-linked log and an independently provided roster/head, reconstructing four distinct observations with **zero source calls**.
- **Negative test:** two separately signing but identically dishonest hosts can produce a majority wrong answer. An enrolled signature and agreement do not establish truth or independent administrative fault domains.

These are local processes communicating over stdio. There is **no claim** of native E-CPU mTLS, Hypervisor, M3/quorum commit, untrusted-host compromise protection, or external model intelligence in this COG-009-adapted demonstration. Independent pins are supplied out of band in the experiment's verifier interface; the local replay file alone is not a globally trusted anchor.

### HTTP model continuity

The actual trained weight bytes were retrieved from two bounded read-only **loopback HTTP processes** using PGT-001's existing adapter; 120 neural output scalars matched the original model. The first process was forcibly terminated, the second supplied the exact same artifact, and corrupted surviving bytes were rejected. This demonstrates artifact continuity, not passive-server inference or a public infrastructure deployment.

## Reproduce

The workflow checks out this branch (stacked on PGT-002) and the COG-009 frozen source branch in separate locations. Locally, with Python, PyTorch, NumPy, cryptography and the three source directories on `PYTHONPATH`:

```shell
python train_policy.py --train 6000 --valid 1200 --epochs 20 --cases 500 --output results
python run_experiment.py --cases 800 --results results
python http_model_audit.py --results results
python -m unittest discover -s . -p 'test_navigation.py' -v
```

The repository's mandatory E-CPU CI gate runs the **existing** IOS-001 and IOS-003 tests and `test_native_ecpu.py`; the two native tests skip in local environments without `mailcpu` but **must not skip in CI**. The current experiments cannot establish transfer to arbitrary real-world hidden laws, nor claim trained parameter fields make physics or observation free.

## Next frontier

1. **Receiver admission**: preserve the COG-009 signed observation and learned neural proposal as distinct inputs to an actual IOS-003 live mTLS receiver; authenticate peer/authority under the native Hypervisor and receiver lease.
2. **Intention-specific failure closure**: when a candidate law is out-of-family, retain unresolved status and seek independent counterexamples or a source-proved projection, never silently bless the model's confident answer.
3. **Amortized learning**: test whether evidence obtained for one intention improves other intentions under independently certified Ground contracts. The one-intention results here are only *candidate acquisition costs*.
4. **Real cost**: observe latency, bytes, proof checks, memory and actual network routing, retaining symbolic costs as a separate model.

These distinctions align with classical cost-sensitive Bayesian experimental design, exact finite active-learning decision trees, and recent bounded version-space learning work. The mathematics is not claimed novel; the contribution is the explicit trained, source-challenged, route-persistent, refusal-aware assembly over previously built research infrastructure.
