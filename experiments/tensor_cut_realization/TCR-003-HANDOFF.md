# TCR-003 — Native receiver admission and conditional federation

**Status (2026-11-13): implementation prototype developed locally; GitHub native CI and separate-host proof are not yet established.** This handoff tracks the actual next experiment after TCR-001/#192 and TCR-002/#195. Do not promote local tests into verified GitHub results.

## Hypothesis

A remote observer-host can retain its own immutable parameter slice and admit a bounded tensor-cut operation through E-CPU's **native VirtualLayerRuntime / Hypervisor** instead of an application-only permission check. A request should transfer a typed activation, source/cut identity and observation goal—not the numerical weight payload. A successful mTLS delivery is neither execution permission nor numerical equivalence.

The supported standalone law is
```
Y = bias + sum_i activation(X @ W1[:, I_i] + b1[I_i]) @ W2[I_i, :]
```
for disjoint exhaustive hidden-neuron partitions and a shared elementwise ReLU/GELU-tanh. FP64 evaluation of stored FP32 coefficients can differ in reduction order from a reference runtime.

## Native operator adapter

The proposed Python `native_operator.py` prototype reuses `ResidentShard` and the original `tensor_cut.py` from TCR-002/TCR-001. Before accepting a request, the receiver independently checks the pinned manifest, exact partition, tensor hashes, input digest, F64 shape and byte limit. It then builds local E-CPU objects: `HeadlessOS`, admitted `SystemSeedEnvelope` / `VirtualGroundRef`, `OperatorSpec` and `OperatorRegistry` for a deterministic pure `tcr.tensor_cut.partial` operator, `VirtualLayerRuntime`, and a process with `/virtual-layer/operators:compute`. Only `VirtualLayerRuntime.execute_operator()` invokes the local handler. The source never chooses the capability grant.

The receiver's native application response binds the original numerical receipt, Hypervisor allow/deny status, operator-contract digest, Ground identity and journal-check status. Numerical acceptance still requires the existing TCR-001 `_accept()` and dense + scalar reference checks, not simply a self-reported journal flag.

A receiver-owned SQLite database keeps (request ID, request content digest, manifest identity, operator contract identity, response bytes and response hash). The database uses WAL and synchronous FULL; it persists an accepted response before the incoming `ReliableChannel` commit callback acknowledges delivery. Repetition of an exact request may return historical evidence after restart without recomputing. This is *not* an anti-rollback guarantee, fresh Hypervisor re-admission, a signed receipt, or general exactly-once effects.

## Verification gates

1. Local source/cut/byte and typed digest rejection; malformed IP/route and TLS bootstrap rejection.
2. Native Hypervisor ALLOW with receiver-local capability; DENY with missing capability; no handler invocation on refusal.
3. Two consecutive requests per partition, showing one computation plus exact application replay.
4. Restart and replay from a protected SQLite ledger; mutate the ledger, source identity or operator contract and verify refusal.
5. Actual E-CPU mTLS `SocketTransport` / `ReliableChannel`, not an artifact used as the warm operation message.
6. Four local receiver processes and TCR-001 E-CPU DAG reconstruction; compare every numeric output coordinate against pinned dense reference and selected independent `math.fsum` scalar checks.
7. A **manual**, dedicated, credential-gated Tailscale run on separate source, origin, receiver and auditor jobs; one real-weight partition is sufficient for the first inter-host admission test. A third auditor must independently reconstruct matching request/response identities and compare the numeric partial to the preparer's independent reference.

A portable TCR-003 prototype and its offline tests were constructed in an isolated ChatGPT execution workspace, but the repository cannot assume those files have been pushed by this handoff. The automatic CI and Tailscale overlay paths must be admitted only after their code is on this branch and the checks have actually run.

## Dedicated federation requirements

Use workload-specific `TCR003_TS_OAUTH_CLIENT_ID` and `TCR003_TS_AUDIENCE` secrets, tag `tag:tcr003-native-ci`, and TCP port `41769`. Bind receiver listeners to their own Tailscale 100.64.0.0/10 IPv4, not public or loopback. Require same-run bootstrap identities; transfer only public TLS certificates and endpoint fingerprints as artifacts. Keep each private key on its originating runner. No missing-secret fallback. A third auditor does not join the tailnet. Physical host attestation, global clock calibration, and quorum-anchored anti-rollback remain open.

## Next frontier

After native admission and the first real cross-runner mTLS observation succeed, admit all four tensor cuts over federated paths and connect to `TransitBackendRouter`, `ComputationalExecutionAdmissionCoordinator`, host catalogue/revision leases, and E-CPU's quorum-anchored recovery lineage. Measure actual cold provisioning, warm wire/serialization, receiver admission, numerical compute and independent verification costs separately, before asserting a practical speed advantage.
