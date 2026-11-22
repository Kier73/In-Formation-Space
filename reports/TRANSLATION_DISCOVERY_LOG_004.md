# Translation Discovery Log — TDL-004
## Intention becomes a typed observer operation and an admitted communication route

**Round:** 2026-11-22. [TDL-001](TRANSLATION_DISCOVERY_LOG.md) · [TDL-002](TRANSLATION_DISCOVERY_LOG_002.md) · [TDL-003](TRANSLATION_DISCOVERY_LOG_003.md) · [VL-I implementation](https://github.com/Kier73/VL-I/blob/main/docs/FABRIC_REFINEMENT_TDL004.md)

Evidence labels: **I — implemented**, **M — mathematical consequence**, **O — observed experiment**, **H — next construction**. A code-level test does not become an observed passing result until its matching CI run has completed successfully.

## TDL-004/A — A mathematical question must survive translation into an execution type

**I:** E-CPU SAB-001's graph planner composes observed operations by declared input and output representation kind, then chooses the cheapest receiver-admitted path satisfying leases, allowlists and bound handlers/carriers. When VL-I initially gave different requested parity rows the same generic output kind, SAB-001 could legally choose the cheapest **different** parity operation. The E-CPU graph was internally consistent, but the intended observer equation was violated.

The missing identity was **which mathematical question is answered by the bit**, not the bit's storage representation.

\[
\operatorname{Bit}(x_1)\ne\operatorname{Bit}(x_2)
\quad\text{as an admitted observer-result type, even though both live in }\mathbb F_2.
\]

**I — correction:** [`offer_output_kind(offer_id)`](https://github.com/Kier73/VL-I/blob/main/src/vli/fabric_refinement.py) includes stable observation identity in the output representation. The corresponding SAB-001 task, declared operation and channel all use this exact kind. A receiver cannot substitute one row's handler merely because it produces another one-bit result.

**M:** For observation request \(q_i=(a_i,\mathrm{source\ epoch},\mathrm{intent})\), valid realization requires both a typed runtime result and a *semantic binding* \(O_{q_i}(x)=a_ix\). A type that says only “bit” captures codomain but not the intended function. The exact output kind binds the specific declared row/offer identity within the receiver's existing typed graph; independently verifying that a sensor measures the claimed row remains a second question.

**H:** use source Ground and observer-projection digest rather than only a caller-assigned name in the representation identity, and test aliasing, equal names/different rows, and two independently verified handlers for the same mathematical observation. Extend type-verified routing into E-CPU's authenticated remote transit contracts.

## TDL-004/B — Admissible paths change the optimal information representation

**I:** [`plan_fabric_refinement`](https://github.com/Kier73/VL-I/blob/main/src/vli/fabric_refinement.py) creates a concrete `BootstrapTask` per offered observer row. For each task, E-CPU's `AdaptiveBootstrap.plan` intersects observed resources, capability offers, current leases, receiver policy, local handler/oracle bindings, and byte-moving carrier bindings. Each candidate's admitted route cost is `BootstrapPlan.estimated_quanta`, rather than the abstract flat offer cost used in TDL-003.

The mathematical optimization is

\[
S^*=\arg\min_{S\subseteq\mathcal A(I,P,\tau)}
\left(\sum_{i\in S}q_i^{\rm route},\;|S|,\;\operatorname{IDs}(S)\right)
\quad\text{subject to}\quad
\operatorname{rowspan}(B_n)\subseteq\operatorname{rowspan}[B_o;A_S].
\tag{TDL4-B1}
\]

\(\mathcal A(I,P,\tau)\) is the **current receiver-admitted** observer catalogue, not every advertised possibility. The [independent verifier](https://github.com/Kier73/VL-I/blob/main/src/vli/fabric_refinement_verify.py) reconstructs candidate tasks and re-plans the *complete* declared catalogue, refusing a certificate which omits a cheaper currently eligible source row.

**M:** the least-cost information basis is a function of mathematical intention **and** the currently realizable communication fabric:

\[
\boxed{S^*=S^*(B_o,B_n,\mathrm{inventory},\mathrm{policy},\tau).}
\]

A lease expiry can change \(S^*\) while leaving \((B_o,B_n)\) and the correct new coordinate unchanged. Thus representation selection and host/path selection are coupled; first choosing the mathematically smallest bit set and then placing it on hosts can be cost-suboptimal.

### Implemented bounded fixture

| Offered observation | Local operation quanta | Type-bound route | Total declared quanta |
|---|---:|---|---:|
| \(x_1\) | 10 | ingress → direct observer → collector | 12 |
| \(x_1\oplus x_2\) | 1 | ingress → cheap-left → collector | 3 |
| \(x_2\) | 1 | ingress → relay → cheap-right → collector | 4 |

For an old observer retaining \(x_0\) and a new intention requiring \(x_1\), the two cheap observations (cost \(3+4=7\)) are sufficient, and beat the direct result (cost 12). Removing the cheap-right lease or receiver permission changes the optimum to direct. The new result remains \(z_n=B_nx\) for a fixed declared source state whenever an admissible alternative remains.

## TDL-004/C — Path execution, evidence provenance and physical authentication are different relations

**I:** [`execute_fabric_refinement`](https://github.com/Kier73/VL-I/blob/main/src/vli/fabric_refinement.py) calls SAB-001 `plan` again before execution, then its real `execute` operation invokes bound handlers and carriers. It checks `verify_bootstrap_report`, exact request digest and observation-specific output bit, and records a local measured `perf_counter_ns` duration and canonical application-input/output byte count. It next creates VGI's actual `ChannelMessage` → `ChannelExchangeLedger` → `EncounterLedger` → `TransportFrameReceipt` → `TransitionEvidenceLedger`, then finalizes each selected observation and calls TDL-003's verified reconstruction.

**M:** three scopes must be kept distinct:

1. **Mathematical:** rank/row-span sufficiency and exact decoding for any true source-side bit values.
2. **Receiver-local authorization:** the current SAB-001 policy, handler, carrier, path lease, receiver oracle and VGI evidence finalization support the emitted bit *under the receiver's trust assumptions*.
3. **Independent physical source authority:** proof that an external, independently administered host/sensor actually generated those values, which requires authenticated external endpoint binding and source attestation.

The current VGI adapter is **one receiver-owned policy source**, and the test carriers are receiver-bound identity-byte drivers through multi-hop E-CPU route semantics. This round does not conflate them with independently authenticated mTLS remote hosts. SHA-256 report digests give record integrity, not sender authentication.

**H:** integrate E-CPU's mutual-TLS cross-process transit with exactly scoped observer operations and source-signed/mTLS-bound VGI evidence. Measure path negotiation, packet bytes and execution wall time separately, and verify safety when the host dies after producing a bit but before its evidence is finalized.

### Cross-repository discovery: mTLS observation transport already exists

**I:** [E-CPU IOS-003](https://github.com/Kier73/E-CPU/blob/main/mailcpu/intention_measurement_fabric.py) exposes `MeasurementPeerClient.connect_mutual_tls` and `MeasurementPeerServer.accept_mutual_tls`, checks authenticated peer DNS SANs and `CERT_REQUIRED`, requires preinstalled `HostedMeasurement` observer contracts, rechecks receiver-local authority at request time, and writes completed read-only measurements into a durable ledger before channel acknowledgement. These are executable primitives for the next stage, rather than novel transport mechanisms to build from scratch.

**M:** a mathematical observer offer can remain independent of a chosen network address, while a live authenticated measurement receipt can establish a source-relative trust claim for one execution. Binding their identities is an explicit **translation obligation**: offer row/epoch ↔ observer contract ↔ TLS peer identity ↔ VGI admitted source. This is stronger than merely preserving hashes across the existing receiver-local adapter.

## TDL-004/D — Verification inventory

| Test / code | Property |
|---|---|
| `tests/test_fabric_refinement.py` | Typed multi-hop routes with different observer operations, exact math and receiver-qualified VGI state |
| Same integration test | Host lease expiry, policy revocation, alternative observation basis |
| Same integration test | Receiver-oracle rejection of wrong values; unbound advertised hosts refused |
| Same integration test | Independent receipt verification rejects rehashed wrong result/cost/evidence |
| `fabric_refinement_verify.py` | Recomputes all available declared offers, independent SAB route and VGI ledger/coordinate verification |
| [Dedicated CI](https://github.com/Kier73/VL-I/blob/main/.github/workflows/tdl004-fabric-refinement.yml) | Linux/Windows Python 3.11, 3.13, plus TDL-003 and TDL-002 regressions |

At this entry's initial authorship, the above are code/test contracts. Append exact job conclusions and source commit after CI confirmation. Track unsuccessful runs and concrete corrections rather than relabeling them as successful observations.

## TDL-004/E — Research continuations

1. **Semantic type identity by law:** compile the required projection digest and source revision into the operation's type identity. Use an independent type verifier that checks the source-law interpretation without trusting a caller-assigned offer label.
2. **Authenticated receiver-independent observers:** reuse E-CPU's already implemented [IOS-003 mTLS measurement service](https://github.com/Kier73/E-CPU/blob/main/mailcpu/intention_measurement_fabric.py), especially `MeasurementPeerClient.resolve`, `MeasurementPeerServer`, `HostedMeasurement` and the durable `MeasurementReceiptLedger`. Its CA-verified peer DNS/SAN and native `ObserverReceipt` checks can supply a live authenticated origin for each typed source-row measurement. Adapt those receipts into VGI source membership and E-CPU SAB output kinds without inventing new transport, voting or signature authority. The present implementation still uses one receiver-local VGI adapter; this authenticated adapter remains a testable next construction.
3. **Quorum-aware cost:** each selected source row may require two or more independently verified observer sources. Joint optimization of rows, hosts, paths, source quorum and retry risk is a new mathematical decision problem.
4. **Measurement instead of estimate:** use actual transport/carrier instrumentation to measure latency distributions, bytes on wire and energy, and test whether minimizing estimated quanta predicts end-to-end utility.
5. **Crash-recoverable acquisition:** store unfinished observation task/lease/epoch receipts so host rehome can continue without prematurely finalizing unknown evidence. Combine E-CPU durable DAG epoch fencing with VGI immutable finalizations.
6. **Back-translation as a proof tactic:** turn observed E-CPU routes and VGI evidence into a compact sufficient-Ground certificate that can be independently checked in VGI or the mathematical interpreter before another processor is formed.

The architectural throughline is now **intention → mathematical distinctions → observation-specific typed requests → admissible host/path topology → independent receiver evidence qualification → reconstructed processor state**. Each arrow has an identifiable implementation or a precise next construction.
