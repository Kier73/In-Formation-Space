# Translation Discovery Log — TDL-006

## The observer admitted by the route is the observer authenticated by the measurement

**Round:** 2026-11-22. [TDL-001](TRANSLATION_DISCOVERY_LOG.md) · [TDL-002](TRANSLATION_DISCOVERY_LOG_002.md) · [TDL-003](TRANSLATION_DISCOVERY_LOG_003.md) · [TDL-004](TRANSLATION_DISCOVERY_LOG_004.md) · [TDL-005](TRANSLATION_DISCOVERY_LOG_005.md) · [VL-I technical specification](https://github.com/Kier73/VL-I/blob/main/docs/ROUTED_AUTHENTICATED_REFINEMENT_TDL006.md).

Evidence notation: **I** = implemented source, **M** = mathematically derived property, **O** = observed test execution, **H** = next construction. Native receipts and source hash identities establish the scope explicitly described in their own implementation; do not promote record integrity to historical TLS authentication or physical independence.

## TDL-006/A — A source-relative observation must preserve its identity through both execution authorities

**I:** [TDL-004](https://github.com/Kier73/VL-I/blob/main/src/vli/fabric_refinement.py) already admits exact source-row operations and local carrier paths through E-CPU SAB-001. [TDL-005](https://github.com/Kier73/VL-I/blob/main/src/vli/authenticated_refinement.py) already admits live CA-verified IOS-003 TLS measurement sessions and distinct VGI evidence sources. Those protocols each have useful authorities, but previously neither was obligated to use the **same selected endpoint** as the other.

**I — TDL-006 composition:** [`plan_routed_authenticated_refinement`](https://github.com/Kier73/VL-I/blob/main/src/vli/routed_authenticated_refinement.py) expands an observation offer \(a_i\) into one uniquely typed SAB-001 task for every peer \(\pi\) required by the receiver:

\[
r_{i,\pi}=(\mathrm{sourceLaw},a_i,\mathrm{offerID},
           \mathrm{peerID}_\pi,\mathrm{expectedDNS}_\pi,
           \mathrm{source/intentionEpoch},\mathrm{challenge}).
\tag{TDL6-A1}
\]

The task's output representation is unique to both observation and peer; it must be realized by an operation at that peer's exact E-CPU resource ID. Immediately before making the remote measurement, [`execute_routed_authenticated_refinement`](https://github.com/Kier73/VL-I/blob/main/src/vli/routed_authenticated_refinement.py) checks the native IOS-003 client against the exact same peer ID and the actual currently negotiated TLS peer DNS SAN. It uses E-CPU's existing `_bound_transport` check, not caller-provided claims of an earlier certificate.

**M — endpoint identity equation:**

\[
\boxed{\mathrm{SABRealizerLocus}(i,\pi)
       =\mathrm{ReceiverPinnedPeerID}_{\pi}
       =\mathrm{IOS003ProviderID}_{\pi},
\qquad
\mathrm{TLSVerifiedSAN}_{\pi}
       =\mathrm{ExpectedDNS}_{\pi}.}
\tag{TDL6-A2}
\]

This is an executable *endpoint binding*: the intended mathematical question and receiver-admitted operation travel together to the selected peer's live measurement session. A cheap authorized path to a different observer cannot satisfy the result type even if it returns a bit.

**Scope:** SAB-001's currently used carriers are receiver-local byte movers for dispatch admission; the real mTLS measurement travels on IOS-003's own authenticated socket. TDL-006 **does not prove that SAB's local carrier graph is the physical IP route** used by the TLS packets. That additional path-to-wire verification is an explicit subsequent experiment.

## TDL-006/B — Information basis selection must include quorum-qualified route cost

**I — code:** the planner considers up to 12 observer rows and 2–8 distinctly pinned peers. It calls E-CPU `AdaptiveBootstrap.plan` for every offered pair \((i,\pi)\) and filters any row lacking a complete set of admitted peer-specific routes. It takes the route-specific declared quanta \(q_{i,\pi}\) and reuses TDL-003's independent GF(2) rank/cost optimizer.

\[
\boxed{\mathcal A_{\rm available}=
  \{i:\forall\pi\in P,\ \mathrm{AdmitSAB}(r_{i,\pi})\}.}
\tag{TDL6-B1}
\]

\[
\boxed{
q_i^{(P)}=\sum_{\pi\in P}q_{i,\pi},\qquad
S^*=\operatorname{argmin}_{S\subseteq\mathcal A_{\rm available}}
(\sum_{i\in S}q_i^{(P)},\ |S|,\mathrm{IDs}(S))
}
\tag{TDL6-B2}
\]

subject to

\[
\operatorname{rowspan}(B_{\rm new})
\subseteq\operatorname{rowspan}([B_{\rm old};A_S]).
\tag{TDL6-B3}
\]

**M — new connection:** an observer row might be inexpensive at one host, but absent at another whose independent evidence is required. The relevant unit of available information is a **quorum-qualified observation**, not one cheap scalar projection. Information and host availability therefore interact *before* the processor's next representation is chosen.

### Source-grounded finite test case

A four-register source has old observation \(x_0\) and new intention requiring \(x_1\). Two native TLS provider identities, `peer-left` and `peer-right`, are required for every selected bit. The E-CPU inventory advertises an intermediate receiver-owned relay to the right peer.

| Mathematical observation | Route quanta at left peer | Route quanta at right peer | Complete-peer cost |
|---|---:|---:|---:|
| \(x_1\) direct | 22 | 23 | 45 |
| \(x_1\oplus x_2\) | 3 | 4 | 7 |
| \(x_2\) | 3 | 4 | 7 |

The cost-optimal sufficient basis chooses the latter two, total **14 declared quanta**. Their values determine \(x_1=(x_1\oplus x_2)\oplus x_2\); IOS-003 and VGI require agreement from both peers on *each* selected row. Revoking one peer's route to \(x_2\) removes that entire candidate from the quorum-qualified catalogue, and the mathematical selector chooses the more expensive direct source row instead.

**Important:** these are receiver-inventory **declared quanta**, not measured TLS elapsed time, wire bytes, energy or global infrastructure costs. The source is a deterministic test Ground; observer peers are separate local TLS endpoints with distinct certificates, not independently operated physical machines.

## TDL-006/C — Independent verification must reconstruct the *missing alternatives*

**I:** [`verify_routed_authenticated_plan`](https://github.com/Kier73/VL-I/blob/main/src/vli/routed_authenticated_verify.py) independently creates *every* potential \((\mathrm{offer},\mathrm{peer})\) task and E-CPU route from the current inventory, source/interpreter Ground, receiver policy, scheduler coordinate, authority identity and challenge. It verifies that:
- each eligible source row has a complete quorum-sized set of exact peer/operation routes;
- the supplied mathematical plan's *entire* offered catalogue equals the independently admitted catalogue, rather than a hand-picked subset;
- the chosen row set is sufficient and exact-cost optimal using the independent TDL-003 rank/cost verifier;
- every selected task and route digest matches the reconstructed native E-CPU plan.

**M:** A compact certificate claiming that a selected source-row basis is cheapest is only meaningful relative to the **full admissible catalogue**. A malicious or stale producer could otherwise omit a less expensive available observation. This is the same structural distinction seen in TDL-001 between *record presence* and *qualified authority*: the complement is a proof obligation.

**I — run and record:** the authenticated execution path checks the live TLS client peer IDs/certificate SANs, executes SAB's bound dispatch handlers and local carriers with receiver oracles, and runs the existing IOS-003/VGI strict quorum pipeline. The independent [result verifier](https://github.com/Kier73/VL-I/blob/main/src/vli/routed_authenticated_verify.py) checks the SAB reports, source/epoch cost plan, TDL-005 native receipt/Ground identities, VGI source membership and mathematical state result.

A returned JSON result can be independently checked for **record consistency**. It cannot be replayed offline as proof of the historical TLS handshake because E-CPU's native `ObserverReceipt` is content-addressed rather than source-signed. Live session assurance is present only at the point of acquisition.

## TDL-006/D — Epoch and recovery semantics

The routed acquisition epoch binds:
- exact old/new source and interpreter digests;
- retained old native coordinate;
- the receiver's observed E-CPU inventory and admission policy digests;
- the route-planning coordinate;
- all required peer identities *and* expected DNS SANs;
- the current authority digest, scheduler and challenge nonce.

\[
\mathrm{Epoch} =
H(\mathrm{sourceLaw},\mathrm{intention},z_o,I,P,\tau,
  \mathrm{peers},\mathrm{authority},\mathrm{scheduler},\mathrm{nonce}).
\tag{TDL6-D1}
\]

**I:** E-CPU route admission is independently rechecked before dispatch, after dispatch and before final return, preventing an already-detected authority/lease change from silently granting a stale epoch. IOS-003's preexisting durable read-only completion ledger returns the same reading when an identical challenge/request is retried on a recovered connection; a fresh challenge initiates a new observation attempt.

**M:** an old processor coordinate is not a global clock, and a prior source-row measurement can be true of a past source state while false of the current state. Thus a future durable multi-host service must distinguish *retrying one observation attempt* from *moving to a new observation state*. A process restart after partial VGI receipt collection needs its own fenced attempt log; this round exercises complete attempt retry rather than proving crash-atomic distributed commit.

**H:** extend the experiment to kill an independently controlled measurement process after its durable IOS commit, rejoin with the same authenticated peer identity and challenge, and resume only missing per-row VGI evidence without reissuing successful semantic effects.

## TDL-006/E — Reproduction and observed execution status

**I:** [`tests/test_routed_authenticated_refinement.py`](https://github.com/Kier73/VL-I/blob/main/tests/test_routed_authenticated_refinement.py) exercises the public E-CPU native SAB route planner/execute paths and preexisting TDL-005 live CA-certified IOS mTLS fixture. The test targets include:
- exact 2×2 peer/row binding and successful strict VGI quorum and new processor state;
- swapped TLS clients and wrong pinned certificate SAN rejected before a reading;
- lease expiry, revoked receiver allowlist and alternative information basis;
- independent SAB receiver-oracle rejection of incorrect dispatch identity;
- disagreement between authenticated peer readings;
- durable identical-challenge reconnection and source-row receipt identity;
- altered/rehashed route, peer ID, cost, VGI evidence and observation epoch refused by the offline record verifier.

**Exploratory check and correction:** the initial CI run exposed a fixture arithmetic error: two source rows each cost \(3+4=7\), so the combined optimum is 14 rather than 28. That assertion was corrected without changing production code; the passing complete matrix and its exact revision are recorded below.

[Dedicated test workflow](https://github.com/Kier73/VL-I/blob/main/.github/workflows/tdl006-routed-authenticated.yml): Linux/Windows × Python 3.11/3.13, exercising the new tests plus IOS-003 live TLS and prior TDL-004 route regressions.

**O — matching CI execution (2026-11-22):** [VL-I Actions run 45072964545](https://github.com/Kier73/VL-I/actions/runs/45072964545) passed the full four-job Linux/Windows × Python 3.11/3.13 matrix at implementation head `aa1bb321cb9245034ad03cf05c85d908c59a9c98`. In every environment, **10 new TDL-006 route/TLS binding tests**, **9 TDL-005 live TLS/quorum regression tests**, and **7 TDL-004 receiver-owned route regressions** completed successfully: **26 tests per environment; 104 observed test executions**. The first exploratory run's only failure was an incorrectly doubled expected combined route cost (28 rather than the actual 14), corrected in the final tested revision without changing production logic.

**O — exact scope:** the experiment exercises real E-CPU native SAB-001 path planning and bound dispatch handlers/carriers, native IOS-003 CA-verified TLS sockets, existing VGI strict source quorum and the exact VL-I mathematical decoder. The test peers run as separate certificate identities in a single local test environment; exported record verification is not historical TLS authentication and the locally bound SAB channels are not a claimed physical IP route.

## TDL-006/F — Next research frontiers

1. **Actual wire path correspondence:** instrument the live IOS-003 peer/channel with source-observed network metadata and compare it against a typed SAB route, distinguishing an authorization graph from a physical byte path.
2. **Authenticated observation-fabric discovery:** extend E-CPU's peer directory so every offered row can be discovered and authenticated under an exact source-law / projection contract, with explicit revision/lease monotonicity.
3. **Recover partial evidence, not just complete replies:** durable VGI per-peer evidence over host process kills, no dual finalization, fresh epoch fencing, and independent old/new Host identities.
4. **Variable quorum optimization:** choose peer subsets under quorum and independently qualified source provenance, rather than requiring every selected peer for every row.
5. **Cost versus physics:** benchmark real wall time, wire bytes, TLS session reuse, retransmissions, payload sizes and energy; test whether declared quanta-optimal bases are actually faster or cheaper.
6. **Portable origin proof:** compare native live mTLS assurance with signed source Ground/measurement assertions, revocation checks, and independent offline verification without claiming content hashes alone prove historical source identity.

The throughline is becoming a testable implementation chain: *mathematical intention determines source-row questions; those questions determine a quorum-qualified route/peer set; native TLS identifies the actual respondent; VGI qualifies agreement; the new processor state is reconstructed from exact admitted information.*
