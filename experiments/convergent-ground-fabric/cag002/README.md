# CAG-002 — One computation identity across two real transports

**Question:** Can one finite, content-addressed operation DAG survive disconnection, retransmission, and observer-host replacement when its descriptions arrive over *different network protocols*, yet produce the same verified pure result independently of route order?

**Status:** hosted dual-protocol integration and independent GitHub verifier passed (November 14, 2026 UTC). CAG-002 extends [CAG-001](../README.md) and is deliberately not a demonstration of Tailscale, WAN traversal, provider-independent failure domains, or E-CPU runtime authorization.

## Two physical protocol implementations

**NATS JetStream route (blue):** a real NATS server runs in a local Docker container with file-backed JetStream enabled. A Python publisher sends the CAG-001 blue packets and completely disconnects. Only then does a receiving client connect using a durable explicit-ACK pull consumer. The first delivery is deliberately unacknowledged before the consumer disconnects; a replacement client uses the same durable consumer and observes redelivery. This tests real TCP protocol delivery, server-managed replay and client interruption, but does **not** test broker process restart or provider outage.

**go-libp2p route (amber):** a separate Go process opens an encrypted libp2p transport on 127.0.0.1 using an ephemeral peer key, a custom typed protocol ID, and an append-only fsynced receiver spool. It receives an amber packet but deliberately drops the first transport ACK after the spool is durable. The sender retransmits; both deliveries are retained. After receiving another packet, the listening process is stopped, a *new* libp2p peer is started against the same spool, and the sender delivers the remaining packet. The peer ID rotates while the application semantic IDs are unchanged. This is real libp2p transport encryption and peer identity at loopback, **not** a libp2p circuit relay or an application-authorized E-CPU host.

Both routes use exactly the CAG-001 source Ground, canonical packet format, and semantic identity. Each has complementary dependencies. Neither carries the entire program.

## Two independent verification tiers

1. **Same-run transport observer:** the integration script retains the actual JetStream client deliveries, libp2p receiver spool, and an explicit trace describing the ACK loss and restart controls. The CAG-001 independent arithmetic checker rejects missing dependencies, invented packets, conflicting semantics, overflow and incomplete route sets; it compares both route arrival orders and recomputes the expected value 44.
2. **Separate GitHub-hosted verifier:** on the protected main branch, a different job downloads the complete bounded capture, checks the producer report's GitHub artifact attestation against this exact workflow and main ref, then independently recomputes the source DAG, route membership, duplicate handling and final report. The verifier also attests its replayed result.

There is **no shared secret or external cloud account** needed for the local pilot. Its privacy and authorization scope are limited to ephemeral local CI processes.

GitHub checks and immutable packet digests are not a substitute for genuine publisher authorization, E-CPU local Hypervisor admission, or VGI proof-carrying Ground acceptance. The libp2p peer ID authenticates the ephemeral *connection*, not the semantic application actor across restarts. ACK means transport delivery, never exactly-once execution or side-effect commitment. The two transports run on one GitHub-hosted machine under a common infrastructure operator; independent WAN provider paths, split trust domains and node failure correlation are **not** established.

## Architectural significance

The state being moved is not a CPU process image. It is a set of typed computation descriptions, whose dependency closure may be interpreted on any authorized observer-host holding the necessary Ground and verification contract. Physical arrival time is not part of the semantic identity. A new transport frame, new libp2p peer or new JetStream consumer can therefore contribute evidence for the *same* requested Ground, while the reconstruction rules keep unknown information and conflicts visible.

E-CPU contributes the next missing layer: verified origin identity, receiver-owned execution admission, and durable single-winner result publication for effects. VGI contributes semantic Ground certificates and reconstructability beyond this finite arithmetic example. CAG-002 builds neither permission layer and makes no assertion that arbitrary operations are safe to replay.

## Run

### Source and synthetic negative controls

    python -m unittest discover -s experiments/convergent-ground-fabric/cag002 -p 'test_substrates.py' -v

### Two actual network protocols

Requires Go 1.25+, Docker, Python 3.11+, network access for go-libp2p and nats-py dependencies, and a functioning local Docker daemon.

    cd experiments/convergent-ground-fabric/cag002/p2p
    go mod tidy && go build -o /tmp/cag002-p2p .
    cd ../../../../
    python -m pip install "nats-py>=2.10,<3"
    docker run -d --name cag002-local -p 127.0.0.1:4222:4222 nats:2.11.10 -js
    python experiments/convergent-ground-fabric/cag002/substrates.py run --directory /tmp/cag002-evidence --p2p-binary /tmp/cag002-p2p
    python experiments/convergent-ground-fabric/cag002/substrates.py verify --directory /tmp/cag002-evidence
    docker rm -f cag002-local

The hosted [CAG-002 workflow](../../../.github/workflows/cag002-dual-substrate.yml) performs this sequence automatically on its single integration runner and runs a separate verifier job only on main. To prevent overstating evidence, the hosted output uses status two_real_substrates_local_reconstruction, **not** multi_provider_federation.

## Verified hosted result

**Main Actions:** [CAG-002 run 43555010037](https://github.com/Kier73/In-Formation-Space/actions/runs/43555010037)  
**Implementation:** [PR #194](https://github.com/Kier73/In-Formation-Space/pull/194), merged commit 0ef122744629449e624c3b5bd273dcae30b87f0a.  
**Jobs:** tests, network_host, verifier_host — all passed. The independent verifier checked the report's GitHub artifact attestation against the protected main CAG-002 signer workflow, replayed the captured route files, reconstructed the exact report, and independently attested it.

| Protocol observation | Retained outcome |
|---|---|
| NATS JetStream blue route | File-backed stream, publication before consumer connected, durable consumer reconnect, missing ACK and explicit redelivery |
| libp2p amber route | Encrypted Go libp2p stream, fsynced receiver spool, first ACK deliberately lost, successful retransmission, restarted listener and new ephemeral peer ID |
| JetStream deliveries | 5 packets, 3 unique descriptions |
| libp2p deliveries | 5 packets, 3 unique descriptions |
| JetStream then libp2p | Unknown dependency after route 1; result 44 after route 2 |
| libp2p then JetStream | Unknown dependency after route 1; result 44 after route 2 |
| Semantic result identity | 5 distinct operation packets, same result digest for both route orders |

Exact content evidence retained in this run:

- Independent report JSON SHA-256: d0fce20caa18e62ea23c9a8793d62b2cb564305ae928fd54862fe8c50a62df36
- Canonical report digest: b09206dedc97b333710e513b0c57984e27114fefdb1d89427d231441eb12f566
- Captured JetStream JSONL SHA-256: aaeeebbf2e7775dff01c64836610e6c1cb3595329d9dad8e5a6a9e224be51f93
- Captured libp2p JSONL SHA-256: 37ea23ccdc4b618836ab6c47b521c2a585ccbb061c2673c0f08ccb42372d1e2a

The report embeds both capture hashes. Independent replay enforces canonical JSONL, packet/source membership, both route closures, duplicate-idempotent semantic interpretation, and matching report digest. Dependency resolution is retained in the cag002-go-dependency-lock Actions artifact. The hosted run used nats-py 2.16.0, nats-server 2.11.10 and pinned go-libp2p v0.44.0.

**Important limits:** both live network transports operated over loopback on a single GitHub-hosted runner; NATS ran in Docker and the libp2p listener was a separate Go process. The verifier ran in another GitHub-hosted job but authenticated and replayed a transcript supplied by the first host; it did not independently observe packets on the wire. The experiment establishes protocol-diverse, interruptible information carriage and finite result reconstruction under this fixture, not separate network operators, a circuit relay, E-CPU Hypervisor admission, VGI proof authority or arbitrary exactly-once side effects.

## Next frontier

Move JetStream to an independently administered broker and libp2p to a separately hosted relay (or implement circuit relay v2) so both routes have distinct public reachability, then repeat: host outage, producer restart, lost ACK, stale/forked semantic identities, authority rotation, and verifier-controlled admission. Compare normalized source identities and measured transport/admission/verification costs. Avoid using a public broker or relay without an explicit threat model and appropriate authentication.

References: https://docs.nats.io/concepts/jetstream and https://docs.libp2p.io/guides/getting-started-go/ .
