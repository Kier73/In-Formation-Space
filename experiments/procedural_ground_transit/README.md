# PGT-005 — Learned intention navigation through native E-CPU measurement paths

**Status: implemented, directly tested signed-source and synthetic-protocol layer; actual IOS-003 mTLS and E-CPU verification require the strict hosted native gate.** This experiment adds no new Hypervisor, measurement protocol, Ground certifier, or model architecture. It composes existing research.

## Architectural question

Can an actual trained neural policy choose which observation matters in a mathematical state-space, obtain that observation through HTTP/stdio observer-hosts **inside** E-CPU's receiver-controlled IOS-003 mutually authenticated, reliable measurement service, and preserve an honest distinction between *verified observation*, *conditional model prediction* and *an admitted mathematical Ground*?

## Already existing components reused, not reimplemented

- **PGT-003** `ObserverPolicy` (4,193 trained parameters) and `decision_experiment.Context`: one typed intention, current posterior over a 30-function candidate language, and declared query costs. Proposals are advisory.
- **PGT-004** `MixedPathGround`, `HTTPPeer`, and `StdioPeer`: two real local HTTP observer child processes, one signed stdio child process, enrolled Ed25519 keys, authenticated request-nonce correlation, signed evidence chains, two-key agreement, real origin kill and replacement, and separate offline `recover_paths`.
- **E-CPU IOS-001** `FiniteGround`, `MeasurementCapability`, `plan_sufficiency`, `verify_sufficiency_plan`: exact and receiver-owned sufficiency of a declared finite Ground relative to *the requested coordinate*, never a model confidence threshold.
- **E-CPU IOS-002** native `ObserverContract`, `ObserverReceipt`, `verify_observer_resolution`: exact scheduler, operation, native interpretation and context correlation.
- **E-CPU IOS-003** `HostedMeasurement`, `MeasurementPeerServer`, `MeasurementPeerClient`, `MeasurementReceiptLedger` on its existing `SocketTransport`, mutual TLS and `ReliableChannel`; the provider logs a SQLite completion before ACK. Provider authorization uses the native **installed local policy hook**, rather than trusting the originating model. The test hook is not production Hypervisor arbitration.
- **E-CPU PR #169** exact patch commit `393462c6e0dafba8e0ee22946ae44227c5c6e4e6` fixes an existing `lsinstance` typo in `HostedMeasurement`. Native CI checks out precisely that commit rather than silently using main, where the constructor still fails.

## The actual data flow

```text
                 trained PGT-003 neural proposal (q)
                              |   no authority
                              v
receiver process:  exact IOS-001 probe Ground + one native q contract
                              |   MEASURE under local receiver policy
                              v
       IOS-002 request: model, exact q, scheduler, fresh challenge
                              |
                    native IOS-003 mTLS + ReliableChannel
                              |
                              v
       separate provider process: SAN/CA TLS, installed policy, q lookup
                              |
               signed PGT-004 HTTP/stdio observer ensemble
              /                |                   \
          HTTP alpha       stdio beta           HTTP gamma
                \             |                  /
                 signed two-distinct-key agreement
                              |
                  SQLite durable completion (before ACK)
                              |
                    native IOS-002 ObserverReceipt
                              |
                              v
receiver: independently reconstruct native IOS-001 result + update
          partial candidate fiber, retain signed-path evidence separately
                              |
          source Ground membership is NOT established by these signatures
                              |
  directly read requested target through the same authenticated native path
                              |
          publish WITNESSED_NOT_GROUND_ADMITTED or UNKNOWN

 independent *third process/job*: externally pinned source/ledger head,
 verify every original Ed25519 signature plus each native ObserverReceipt,
 correlate q/value, without any source call or signing key
```

### Why the native IOS-001 calls are well-typed

The source is an **eight-coordinate hidden function**; its exact membership in the 30-law candidate language is *not* asserted. For the request for one specific q, the declared finite probe Ground contains 30 states, each with target = feature(q). It exposes only q as an offer and makes a normal IOS-001 `MEASURE` plan; no forbidden feature or invented Hypervisor right can be demanded. The receiver verifies the plan, receives an IOS-003 native receipt, revalidates IOS-002, and records the measured bit. It narrows the candidate version space and asks IOS-001 whether the *original intention* is already determined within that conditional model. `READY` is **conditional**; it is not accepted as external source truth. The receiver still requests the requested target itself unless a separate trusted source-Ground admission exists. If the q measurement is unavailable/contradictory, IOS-003 refuses and the receiver cannot narrow the space. If the observed measurements contradict every candidate, the Ground is **OUT_OF_FAMILY** and cannot be extrapolated.

### What is genuinely different from PGT-004

The signed HTTP/stdio observation now sits **behind** a native IOS-003 provider implementation. Receiver and provider are different OS Python processes, connected by actual localhost TCP and mutual-TLS certificates with distinct pinned DNS SANs. The receiver does not read the HTTP source bytes directly; it receives typed native observer receipts. The provider's local callback checks source signatures/quorum and admits only installed named projections. Native `ReliableChannel` handles typed, correlated frames. E-CPU still owns the receipt and plan validation.

## Experiments and falsifiers

1. **In-family**: hidden source from one 30-law table; trained model chooses q; native IOS-001 permits exactly q; separate native provider reads two signed observer responses; receiver reconstructs exact result and separately witnesses the target.
2. **Dissent and crash**: kill HTTP alpha, introduce signed stdio beta disagreement with surviving HTTP gamma; IOS-003 must send an authenticated refusal rather than treating one reply as truth; restart alpha and retry with a fresh challenge, preserving retained previous signed replies.
3. **Out-of-family adversarial source**: the hidden bits `00101000` are outside the model language. On the six-probe synthetic path, the model confidently proposes target 1 when the true target is 0. The native receiver must not promote that candidate and directly witnesses 0.
4. **Portable evidence, private keys withheld**: offline receiver gets only signed evidence, public enrolled identities, exact independent source and high-water pins, and native typed receipts. It rechecks all signatures and q/value agreement; no source hosts or native TLS private keys are present in the offline job.
5. **Negative controls**: forged signed frames, substituted externally supplied head, stale policy/lease, unauthorized feature, extra fields, and replay are refused by the existing PGT-004 and IOS-003 tests. Two colluding signed observers can still report false data; such agreement is *not* Ground certification.

## Reproduce

The local non-native test is runnable with Python 3.11+, numpy, torch and cryptography. Place PGT-003/004 and COG-009 on PYTHONPATH:

```sh
python -m unittest discover -s experiments/procedural_ground_transit -p test_protocol.py -v
```

**Native E-CPU** requires commit `393462c6e0dafba8e0ee22946ae44227c5c6e4e6` (PR #169). In the repo checkout with that source on PYTHONPATH:

```sh
PGT005_REQUIRE_NATIVE=1 python -m unittest discover -s experiments/procedural_ground_transit -p test_native_bridge.py -v
python experiments/procedural_ground_transit/run_native_transit.py --root /tmp/pgt005-native --source-index 12 --target 6
python experiments/procedural_ground_transit/run_native_transit.py --verify --root /tmp/pgt005-native \
  --expected-head <independently-carried-signer-head> --expected-root <independently-carried-source-root>
```

The CI workflow hard-requires native E-CPU's actual IOS-001, IOS-002, IOS-003 and intent-embedding suites, runs the new entire cross-process native test, and passes only public evidence to a separate GitHub job that verifies against out-of-band pinned identities.

## Evidence scope

- The signed HTTP interface is local unauthenticated **HTTP** with Ed25519 application-layer identity; the parent IOS-003 TLS link is **native real mTLS over localhost**. No claim of public HTTPS deployment, independent physical failure domains, fully remote Tailscale peers or passive network routers executing arithmetic is made.
- The 30-law model is a hypothesis language. IOS-001 certifies only the finite model's stated conditional obligations, not model-source membership; the final output is marked `WITNESSED_NOT_GROUND_ADMITTED`.
- An enrolled signing key, typed E-CPU `ObserverReceipt`, and a consistent HTTP ETag each establish *different* evidence properties. The offline replay can verify native receipt content integrity and signed source values, but cannot recreate or independently attest the historic TLS handshake from a stored receipt alone.
- The provider policy is a **receiver-installed test hook**. Native IOS-003 uses it correctly, but E-CPU's full Hypervisor/coordinator admission, mTLS peer lease management and M3 quorum lineage remain in active development for this integration.
- Symbolic query cost is not wall-clock or network transport cost; the provider additionally records actual HTTP response bytes and elapsed time. Persistent source signatures and native receipt data have nonzero storage cost.

## Frontier

The next research leap is to connect the native provider's admission callback to actual receiver-owned Hypervisor rights and peer lease, store signed/witness + IOS-003 completion in M3/RecoveryLineage with monotonic epochs, and move the same declared Ground between two physically different authorized network hosts without rekeying or reinterpreting its semantic identity.
