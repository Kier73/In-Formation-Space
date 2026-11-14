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

## Verified hosted result

The first main-branch execution completed successfully: [GitHub Actions run 43553335051](https://github.com/Kier73/In-Formation-Space/actions/runs/43553335051), on squash commit 5df38e85e276d350f2adae4e4fd26608aba30a44.

- jobs: tests, source_host, relay_blue_host, relay_amber_host, verifier_host — **all succeeded**
- source, blue and amber records: published as separate workflow artifacts; all three subject artifacts passed GitHub CLI attestation verification by the off-route verifier, pinned to the exact main-branch workflow signer
- final artifact: cag001-independent-convergence-report / report.json
- exact report file SHA-256: 33065060ffea74eb9cf12ff43f0ef2219946fc972c857866ee8e0f8ff960108f
- canonical report digest: 9a9bc3a9979e06c77d2b3f5765ca28485a519bd683d6872b2e4f178acf189f94
- report status: multi_route_eventual_convergence
- reconstructed value in both routes: 44, with five distinct packet identities
- blue then amber: unknown_dependency → locally_reconstructed_pure_result
- amber then blue: unknown_dependency → locally_reconstructed_pure_result
- local permutation/conflict test suite: 13 test cases passed, including all 120 permutations of the five unique packets

The result was inspected from the retained JSON report, not inferred merely from a green Actions badge. The report and the producer route artifacts are attested by GitHub workflow infrastructure; this does **not** establish physical route diversity, sender honesty, separate cloud providers, or VGI/E-CPU execution authority. The independent verifier recomputes finite pure arithmetic and rejects inconsistent route content. It does not execute remote arbitrary operations.

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
