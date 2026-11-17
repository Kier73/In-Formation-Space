# Native reuse: VGI evidence + E-CPU intention sufficiency (IWI continuation)

**Research date:** 2026-11-15. **Status:** source-level reuse integration committed, with native multi-platform GitHub Actions checks separately queued.

## Discovery: the predecessor systems already contain the key capabilities

The IWI-001–005 finite planning experiments were useful for finding counterexamples, but the proposed next step must **reuse** the earlier operational systems, not construct a competing local authority.

| Existing component | Exact implementation | What it already establishes |
| --- | --- | --- |
| E-CPU SAB-002 active law discovery | [`mailcpu/active_ground_discovery.py`](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/mailcpu/active_ground_discovery.py) | permissioned finite probes, holdout/repeat checks, provenance-bound candidate with explicit `finite_witness_only`; receiver-local Ground admission is separate |
| E-CPU IOS-001 observation sufficiency | [`mailcpu/intention_sufficiency.py`](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/mailcpu/intention_sufficiency.py) | exact cost-minimum permitted observation set over a supplied finite model, independent plan/resolution reconstruction and refusal |
| VGI native evidence finalization | [`vgi/evidence.py`](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/e6e1900782aeede18a4de9046511bbba234dbc6e/virtual_ground_interpreter/vgi/evidence.py) | transport-frame/Encounter-bound claims, strict/quorum source policy, explicit event finalization, replay-validated ledger and sparse/partial Ground construction |
| VGI partial transition semantics | [`vgi/transitions.py`](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/e6e1900782aeede18a4de9046511bbba234dbc6e/virtual_ground_interpreter/vgi/transitions.py) | `known` versus `unknown` versus `ambiguous`, no execution from unresolved edges, separate complete-ground replay checks |
| IFS GCI-002/003/004/005 | [GCI-002](../cross-ground-continuity/gci002/README.md), [GCI-003](../cross-ground-continuity/gci003/README.md), [GCI-004](../cross-ground-continuity/gci004/README.md), [GCI-005](../cross-ground-continuity/gci005/README.md) | cross-Ground evidence-admitted finite Ground, observation sufficiency, real loopback mTLS receiver receipts, and signed false/disagreeing receiver controls |
| E-CPU SAB-007 | [`mailcpu/federated_ground_continuity.py`](https://github.com/Kier73/E-CPU/blob/6fd416facdb2aefd6fc7d66a06b014e3d31b5a52/mailcpu/federated_ground_continuity.py) | native forwarding evidence, durable content-addressed receipt store and quorum-sealed recovery lineage (under declared trust/failure-domain assumptions) |
| IFS RE-008 | [sealed coverage and recovery](../response-equivalence/RE008_README.md) | per-epoch signed log continuity, missing/delayed samples, complementary observers, archive-gap refusal |
| IFS Authority Lineage | [append-only authority review](../../bridges/authority-lineage/README.md) | retained proposals, review, supersession and conflict frontiers without rewriting original evidence |

**Conclusion:** The source/trust, policy, planning, recovery and evidence-reconstruction primitives exist already. IWI should contribute **the missing semantic handoff** between them, not duplicate their generic mechanisms.

## Concrete new integration, not a mock authority

`native_reuse_bridge.py` imports **actual pinned E-CPU and VGI Python packages**, rather than reimplementing their internal policies:

1. Accept an already assembled **native `TransitionEvidenceLedger`**. Round-trip its JSON through VGI's own validator. Require exact expected Ground/context and VGI's strict quorum-two **explicitly finalized** `AUTHORIZED` event for `s1, a0`.
2. Use `ledger.build_ground()` to let **VGI itself** construct the partial seven-state Ground. Check that the one edge is known and the remaining 34 state/action pairs stay unknown. Extract the observed target and retained VGI evidence/decision/ledger digests. The returned status is **`VGI_FINALIZED_SAMPLE_ONLY`**.
3. Construct a deliberately small two-hypothesis **E-CPU `FiniteGround`**: if the persistent probe law is branch 2, the intended finishing action is left; if branch 3, it is right. Call native `plan_sufficiency()` and `verify_sufficiency_plan()` rather than writing another feature subset optimizer. It selects one feature at cost 2.
4. Only if a **separate external static-law coverage premise** has explicitly been asserted for the source/context, pass the measured branch to E-CPU's native `resolve_sufficiency()` and `verify_sufficiency_resolution()`. That result is **`CONDITIONAL_INTENTION_RESULT`**, not an E-CPU operation authorization or proof of unobserved future stationarity.

This is the precise scope where the earlier IOS-001 planner can replace the IWI-004 single-query advisory plan. IOS-001 is a finite, nonintervening **feature-sufficiency** planner; it does **not** replace IWI's general multi-step action-conditioned control search over incomplete static laws. Both can coexist without making incompatible semantics appear interchangeable.

The test messages are synthetic typed VGI channel events, and their `TransportFrameReceipt` is adapter-supplied. **A VGI source label or quorum is not a cryptographic identity or proof of independent physical observers.** For real identity the path must use the existing GCI-004/005 E-CPU mTLS receipt verifier. A VGI policy-finalized *sample* is not, by itself, a stable or globally complete law. E-CPU IOS-001 explicitly states that a receipt digest alone does not authenticate the issuer, so the adapter does not claim otherwise.

## Native adversarial tests

`test_native_reuse_bridge.py` exercises:

- both possible probe-law values, via actual VGI finalization, VGI partial-Ground construction, E-CPU minimum-cost plan and independently verified resolution;
- quorum without finalization (still **not authorized**), one missing receiver, unknown reading, and opposing claims from the two source labels;
- changed Ground/context, unrecognized successor, and tampered VGI finalization digest;
- rejection of an absent explicit source-stability/coverage premise;
- actual **E-CPU SAB-002** discovery with a deceptive source that agrees at every finite probe coordinate and diverges at a later coordinate, confirming that native `finite_witness_only` is the correct evidence grade.

The [dedicated workflow](../../.github/workflows/intention-without-identification-native-reuse.yml) checks out **exact pinned upstream commits** and installs native modules, testing Linux/Windows on Python 3.11 and 3.13.

Run after installing the pinned native packages:

```sh
python -m unittest discover -s experiments/intention-without-identification -p 'test_native_reuse_bridge.py' -v
```

**Do not claim this cross-repository integration passed native CI until the jobs actually complete.** Earlier IWI JS V8 math tests and simulated signature tests are not substitutes for executing the actual external E-CPU/VGI APIs.

## Specific unresolved point after this reuse

The existing systems can **observe, authenticate selected messages, preserve evidence, authorize a Ground-relative interpretation, independently reconstruct, and recover accepted receipts**. They do **not** together automatically prove that an arbitrary external source's transition law remains unchanged after power loss, across different physical hosts, or for all unobserved time.

The next work should therefore connect a GCI-004 receiver request/receipt to VGI's native `ingest_channel_message` *through the actual transport adapter*, then use existing E-CPU Recovery Lineage and IFS RE-008 sealed observations to retain and independently recheck the context-dependent authority after a process crash. A distinct **source-side invariant, complete controlled finite fault model or externally trusted conformance witness** is still required before promoting finite samples into reusable physical-law claims.

**Avoid another broad evidence layer:** use SAB-002 and VGI evidence for observations and partial Grounds; IOS-001/GCI-003 for sufficiency; GCI-004/005 for authenticated receivers; SAB-007/RE-008 for recovery and retained coverage; IWI-003 for strong action-policy proof *under declared static-law assumptions*. That seam is the actual frontier.
