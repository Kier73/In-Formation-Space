# GCI-004 — Real mTLS observer discovery and receipt-bound realization

**Research question.** Can the GCI-003 intention-relative planner obtain exactly the missing observation from discoverable, authenticated host capabilities, and can an independent verifier reconstruct the result from signed host receipts and the underlying admitted Ground?

This experiment directly extends [GCI-003](../gci003/README.md) on the **same signed CAG-004 intention**, same eight-edge VGI evidence-admitted Ground and same hidden logical phase. It introduces a networked, receiver-authorized observation substrate without equating every network path with a processor.

## What is actually built

- **Three independent observer OS processes** on one Ubuntu GitHub-hosted runner, accessed through **real loopback TCP mutual TLS**, using E-CPU's real `mailcpu.mtls_transport.connect_mutual_tls`, `accept_mutual_tls`, `SocketTransport`/`Message` framing.
- A **job-local ephemeral test certificate authority** issues distinct leaf identities with DNS Subject Alternative Names. Clients reject a deliberately incorrect server DNS name; servers check the client SAN.
- Each receiver returns an **E-CPU `ComputationalPeerSnapshot`** containing its own typed `ComputationalHostAdvertisement`, version, lease, Ground fingerprint, operator specification, resource bounds and declared route metric. The coordinator admits each snapshot only through E-CPU `ComputationalFabricDirectory.merge_authenticated_snapshot` against the **actual TLS-authenticated** socket.
- Two observers provide `parity` and one provides `low2`. A coordinator measures a **real discovery round-trip time** for each and chooses the lowest observed RTT among Ground-compatible peers supporting the *already proven required feature*. This is a measured **preflight proxy**, not a forecast or guarantee that future requests will be faster.
- A separate `OBSERVE` request contains only the GCI-003 selected feature, task, fresh challenge, source/Ground binding, signed-plan digest and private-phase commitment. **It contains no private phase or complete state.**
- The server checks its *own held mathematical phase*, source binding, and the exact authorized plan before returning the requested feature. Its response is an **ECDSA-signed request-bound receipt using the very same private key as its mutually authenticated TLS leaf certificate**, proving which in-run credential signed it.
- An attempted unauthorized `full-state` observation is **refused**. Replaying a previously fulfilled challenge is **refused**. A client with the wrong TLS server hostname is **refused**.
- The coordinator recomputes the intended results from only the signed feature readings and the certified Ground. It does not use the receiver's privately held phase artifact as a protocol input.
- A separately scheduled final auditor, which does **not install E-CPU or VGI**, validates the ephemeral X.509 CA/leaf chains, SANs, typed snapshot/host metadata, receipt signatures, exact request/plan/phase commitments, independently held phase witness, the four original intention outcomes and the measured discovery/observation counters. It rejects deliberately resealed/forged receipts, contexts and results.

## Observation sufficiency before routing

The four GCI-003 cases are preserved:

| Requested result | Required extra feature | Network outcome |
| --- | --- | --- |
| Threshold after `10^15+136` transitions | none | no observer request |
| Parity of projected result after `10^15+137` transitions | parity | authenticated receipt from one of two discoverable hosts, selected by measured preflight RTT |
| Threshold after one transition | low2 | authenticated receipt from the sole authorized low2 host |
| Complete projected output modulo eight with parity-only permission | insufficient | refused, without illicit wider observation |

The exact mathematical sufficiency test precedes host discovery and measurement. Discovery claims are **metadata** and must not be confused with execution authority; only receiver-owned code, on an authenticated session and with the specific plan granted, serves an actual observation.

## Actual versus modeled measurements

Every real connection records TLS handshake time and discovery/observation request round-trip time in monotonic nanoseconds. The MailCPU framed application message sizes are measured in bytes via E-CPU's frame encoder. These are **local experimental observations**, not universal rates, physical joules or full TLS ciphertext/wire byte counts. The typed E-CPU route advertisement's `latency:1 tick` value remains a declared semantic metric, not a report of the observed nanosecond latency.

The coordinator selects the host with the least **measured discovery RTT among eligible peers**. The final auditor verifies that local selection rule from retained measurements; it cannot independently reproduce the elapsed time that an earlier process reported. Thus no global cost optimizer, network latency guarantee, cost-aware multi-hop fabric, or provider scheduler is claimed.

## Trust scope

All three observer processes, coordinator and certificate issuer run on **one CI machine, under one GitHub administrative and physical failure domain**. The CA is created by the same experiment and not an independently governed external PKI. Leaf-key signatures and real mTLS are genuine cryptographic mechanisms, but this only authenticates the ephemeral test host identities. GitHub artifact attestations bind the provenance of the resulting reports; `main` is not branch-protected. The separately withheld logical phase is not confidential from GitHub, maintainers, runner administrators, or whoever has artifact access.

Likewise, the independent auditor can verify signatures and mathematical consistency but does not witness the TLS packets itself. Its conclusion is conditioned on the correctly installed E-CPU mTLS runtime and attested host workflow, not a zero-knowledge or external-device authenticity proof. The networked observers read mathematical host state from an existing private phase artifact; they do **not** measure an external physical sensor.

## Reproduce

The CI workflow adds `gci004_real_mtls_observers` (actual E-CPU TLS/process experiment) and `gci004_independent_verifier` (no E-CPU/VGI installed). Both extend the existing CAG-004/GCI-001/GCI-002/GCI-003 chain. The runtime job pins a current verified E-CPU revision and uses an ephemeral working directory for certificate private keys; **no private TLS keys are uploaded as output artifacts**.

```bash
python -m pip install 'cryptography>=43,<47'
python -m unittest discover -s experiments/cross-ground-continuity/gci004 -p 'test_fabric_contract.py' -v
```

The focused unit tests exercise cryptographic source/receipt binding and malformed claims, while the hosted job tests real TLS handshakes, exact MailCPU framing, directory admission, unauthorized requests and replay refusal. The independent host runs additional adversarial mutations **against the actual live network report**, not solely a manufactured fixture.

## Next frontier

Extend the authenticated discovery mechanism across independently administered hosts with a durable trust bootstrap, owner-chosen operator scheduling, time-bounded and revocable capability leases, and real multi-hop transport receipts. Keep the proof of intention sufficiency separate from physical route cost and reserve the receiver's authority to refuse a request when its admitted Ground or phase has changed.
