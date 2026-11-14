# CAG-001 — Convergent Ground fabric across asynchronous routes

**Research status:** bounded proof-of-mechanics for route-independent information convergence. PR unit tests and a main-only hosted experiment are separate verification gates. CAG-001 does not claim passive links execute semantics or that hosted jobs occupy independent physical trust domains.

## Research question

Can independent observer-hosts reconstruct a deterministic requested computation by collecting compact, typed operation descriptions through multiple intermittently available routes, without a continuously reachable peer or a global arrival order?

Existing E-CPU already supports reliable channels, authenticated multi-hop forwarding, semantic replay identity, and recovery. In-Formation-Space already provides local durable mailboxes, process-separated recovery, portable realizations, and MOR-001 artifact-mediated causal reconstruction. The new question here is **route-independent confluence** when descriptions are duplicated, reordered or partially absent.

## Model

The source declares a finite directed dependency graph:

~~~text
seed = 3
left = seed + 4       = 7
right = seed * 5      = 15
merge = left + right  = 22
final = merge * 2     = 44

source
  +---- blue: final, right, seed, seed
  +---- amber: merge, left, seed
                    |
           content-addressed union
                    |
        validate all dependencies
                    |
  unknown / conflicting / cycle / reconstructed
~~~

Each packet carries a stable semantic ID, typed pure operation, explicit predecessor IDs, bounded integer argument and canonical content SHA-256. The receiving replica preserves **all** different digests observed for the same semantic ID, not first-arrival-wins. Missing dependencies stay unknown. Cycles, conflicting content identities, overflow and invalid packet shapes fail closed. Arithmetic is recomputed at the observer; a hash is not authentication or authorization.

The replica is a grow-only set of immutable packet variants. Set union is associative, commutative and idempotent, so after eventual delivery of an identical finite evidence set the inventories converge. This does not make arbitrary state-changing effects commutative. A result is only locally reconstructed when its complete dependency subgraph is known, nonconflicting, acyclic and within exact numeric bounds.

In the fixture, neither blue nor amber carries enough information to calculate final alone. Their union reconstructs the reference result 44 independently of route arrival order. Anticipated negative tests include 120 packet permutations, duplicate retransmission, conflicting semantic identity, unknown predecessor, cycle, overflow, and tamper with recomputed wrapper hashes.

## Hosted experiment

The workflow is .github/workflows/cag001-convergent-ground-fabric.yml. PRs only run the unit suite. On main, a source job generates the packet DAG and GitHub-attests its exact JSON. Two separately scheduled relay jobs carry complementary out-of-order subsets and attest their own artifacts. An independent verifier job downloads all three from GitHub Actions artifacts, verifies their GitHub artifact attestations against the pinned workflow signer and main ref, reconstructs both route orders, checks the source program independently, and attests a report.

These routes are **two separately scheduled job-level information paths through a common GitHub artifact service**, not two disjoint physical networks or separate administrative authorities. The source can be malicious; GitHub attestations authenticate workflow production and exact bytes, not honest mathematics. The receiver independently checks finite arithmetic. No Tailscale federation, mTLS, E-CPU Hypervisor permission or VGI ProofGround admission is exercised in this slice.

## Links to the three repositories

- E-CPU: semantic identity is separate from transport frame identity, and every operational host requires receiver-owned authority. Source consulted: https://github.com/Kier73/E-CPU/blob/main/docs/COMMUNICATION_STREAM_COMPUTATION.md (main observed at 3b57adcc2baaaa7e56e4bab943946f4e87e95c65).
- VGI: observed, established and reconstructable Grounds must remain distinct; this experiment has only a syntactic Ground candidate and its deterministic arithmetic result, not a VGI-admitted proof. Source consulted: https://github.com/Kier73/Virtual-Ground-Interpreter (main observed at 093f11e458aff1c223d639ede413000619767ba6).
- In-Formation-Space: MOR-001, DFR-001 and Portable Realization Capsule are existing baselines, not new claims of CAG-001.

## Alternative physical substrates for the same packet contract

- NATS JetStream durable pull consumers: at-least-once delivery with replay and explicit application deduplication. https://docs.nats.io/concepts/jetstream
- libp2p circuit relays with optional hole punching: outbound-to-relay access for otherwise unreachable peers. https://libp2p.io/docs/circuit-relay/
- Delay-tolerant Bundle Protocol (RFC 9171): carry bundles across intermittent contacts. https://www.rfc-editor.org/rfc/rfc9171
- Cloudflare Durable Objects and WebSockets: an addressable rendezvous observer for outbound-connected clients, with provider trust and quota concerns. https://developers.cloudflare.com/durable-objects/best-practices/websockets/

## Next discriminating experiment

Replace **one** GitHub artifact route with a genuinely independent provider or self-hosted relay, inject partial outage and restart, and check convergence with the same content-addressed DAG and off-route verifier. Authenticate original publishers and bind the result to E-CPU receiver-local execution admission and VGI proof certificates. Keep a transport-delivery ACK, a host-created computation receipt, a mathematical check and an independent attestation as different evidence tiers.

This experiment does not benchmark real latency, energy, neural tensor speed, or physical independent host failure domains.

## Reproduce

~~~bash
python -m unittest discover -s experiments/convergent-ground-fabric -p 'test_convergent_fabric.py' -v
python experiments/convergent-ground-fabric/convergent_fabric.py source --out /tmp/source.json
python experiments/convergent-ground-fabric/convergent_fabric.py relay --source /tmp/source.json --route blue --out /tmp/blue.json
python experiments/convergent-ground-fabric/convergent_fabric.py relay --source /tmp/source.json --route amber --out /tmp/amber.json
python experiments/convergent-ground-fabric/convergent_fabric.py verify --source /tmp/source.json --blue /tmp/blue.json --amber /tmp/amber.json --out /tmp/report.json
~~~
