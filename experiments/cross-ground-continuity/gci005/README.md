# GCI-005 — Authenticated disagreement is not observational truth

**Question.** When two differently identified, correctly TLS-authenticated observers issue valid signatures on contradictory permitted measurements, can the system refuse an intention without reading the hidden phase? Can a later verifier demonstrate which observer lied using the separately retained source witness?

GCI-005 extends [GCI-004](../gci004/README.md), retaining the original signed CAG-004 intention, the GCI-002 evidence-admitted closed eight-state Ground, and GCI-003's intention-relative permissioned measurement plan.

## Protocol

Two E-CPU parity observer processes (observer-a and observer-b) communicate over real loopback TCP mutual TLS, possessing separate X.509 certificate private keys issued by one ephemeral test CA. The coordinator uses actual E-CPU SocketTransport and ComputationalFabricDirectory to admit each typed ComputationalPeerSnapshot only after live transport identity and DNS SAN checks.

The coordinator sends the same 128-bit challenge for the allowed far-y-parity measurement to both peers, and collects their separately ECDSA-signed receipts bound to exact plan, Ground, host, snapshot, phase commitment, and challenge.

The hosted experiment runs two scenarios:

| Scenario | Authenticated readings | Coordinator response |
| --- | --- | --- |
| Honest agreement | Both report the same true parity bit | ADMITTED_AGREEMENT |
| Deliberate signed false reading | observer-a reports true bit; observer-b signs its complement with a valid key | REFUSED_DISAGREEMENT, with no admitted result |

An independent **phase-blind** verifier on a different CI job receives the full signed transcript but *does not download* the private phase. It checks X.509 signatures, peer identities, E-CPU snapshot semantics, exact requests, shared challenges, signed receipts, and the refusal condition. Subsequent **private witness** verification can inspect the originally withheld phase to establish which certificate-holder reported a false result.

## Why the distinction matters

A valid signature proves which private key signed a value. It does **not** prove that the value accurately describes its source. Agreement under two credentials proves consistency, not truth if the observers are colluding, compromised, or identically faulty. An honest observer's correct reading does not justify continuing after a contradictory authorized receipt.

This is a unanimous two-observer policy, **not** majority vote, independent administrative consensus or Byzantine fault tolerance. A key holder may be both authenticated and wrong.

## Explicit scope

- The peers are **distinct OS processes**, communicating through **real mutual-TLS loopback sockets on one hosted runner**; they are not independent physical machines or independent trust administrations.
- The CA and both leaf credentials are issued in the same local CI job. There is no external PKI or independently protected signing authority.
- Both receiver processes have access to the test's held mathematical phase. The coordinator implementation does not read phase data as a protocol input, although the CI job environment shares a filesystem. The phase-blind auditor *does not receive* the private artifact.
- The false reading is a **diagnostic opt-in server flag for observer-b**, never enabled in ordinary GCI-004 operation or by a network request.
- Handshake, discovery and request nanosecond timings are measured local samples, not energy or real internet routing cost estimates.
- The experiment does not establish sensor truth, persistent anti-replay storage, protection from collusion, physical failure-domain independence, or general computational acceleration.
- The GitHub main branch is not protected; main-workflow attestations establish only declared workflow provenance.

## Reproduce

Contract-only tests:

    python -m pip install 'cryptography>=43,<47'
    python -m unittest discover -s experiments/cross-ground-continuity/gci005 -p 'test_contract.py' -v

Full live proof is in [the GCI-004/GCI-005 combined workflow](../../../.github/workflows/cag004-topology-neutral.yml). The live signed-transcript tamper tests run inside the blind verifier job with actual host outputs, not synthetic signatures.

**Status:** hosted experiment in verification. A completed main-branch run is necessary before describing the result as independently verified.

## Next question

How should a distributed observer authority handle disagreement when hosts have separate administrative roots, leases expire, requests are retried after crashes, and a hostile peer retains a previously valid signing key? This requires independent trust anchoring, receiver-fresh authority and durable anti-replay beyond the present single-run test domain.
