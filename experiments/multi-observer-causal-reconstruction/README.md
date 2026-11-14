# Multi-observer causal reconstruction

**Experiment:** MOR-001  
**Status:** hosted MOR-001 run #3 succeeded; all three producers and the independent fourth-host verifier completed successfully  
**Question:** can a later verifier reconstruct precedence, concurrency, and genuinely unobserved relations among separate observers without a shared wall clock or shared runtime memory?

## Discriminating event graph

This experiment creates four events across three producer jobs and one verifier job.

| Event | Producer | E-CPU temporal profile | Causal information |
|---|---|---|---|
| A1 | Source host A | Monotonic + wall + causal | First source event; its frame is sent to B |
| A2 | Source host A | Monotonic + wall + causal | Later local event; deliberately not sent to B |
| B1 | Receiver host B | Monotonic + wall + causal | Starts after merging A1's actual E-CPU CausalStamp |
| C1 | Independent observer C | Monotonic + wall, no causal domain | No causal stamp is emitted |

A and B initialize their E-CPU vector clocks with the same declared two-actor roster, both counters initially zero. The actual TemporalContext emit_causal_stamp() and receive_causal_stamp() operations update the states. C intentionally does not enable ClockDomain.CAUSAL.

The verifier checks the exact six-pair relation matrix:

| Pair | Expected result | Reason |
|---|---|---|
| A1, A2 | before | Same source actor's captured vector counters |
| A1, B1 | before | B merged the A1 stamp before B1 |
| A2, B1 | concurrent | A2 was not sent; each complete vector contains a distinct advancement |
| A1, C1 | unobserved | C1 has no causal stamp |
| A2, C1 | unobserved | C1 has no causal stamp |
| B1, C1 | unobserved | C1 has no causal stamp |

The verifier refuses to replace this matrix with a different result. A missing causal stamp is not a vector-clock concurrency result.

## What is actually exercised

The reconstruct.py program imports the pinned E-CPU temporal implementation and creates real TemporalContext objects on each producer job. It also uses the existing In-Formation-Space operation-span recorder and DOP-001 causal-handoff functions.

The A1 → B1 path binds:
- A1's exact operation-span digest and sender completion TemporalFrame;
- the payload digest and the GitHub artifact-relay channel identity;
- the receiver-start TemporalFrame captured after the receiver's E-CPU causal merge;
- B1's exact operation-span digest and the sender/receiver sequence numbers.

The receiver verifies the source artifact attestation before it merges A1's stamp. The fourth job independently verifies all three producer artifact attestations, rebuilds the event matrix from the downloaded records, and attests the exact reconstruction report.

## Clock and duration treatment

Every event retains its actual actor-scoped monotonic coordinate and a wall-clock reading. The experiment injects a declared wall-source offset of +12 hours for A, -12 hours for B, and +3 hours for C. Those offsets are test inputs, not observations of natural clock skew. The wall samples remain in the report for inspection but are never used to infer order, concurrency, or elapsed time.

Operation spans are measured only within their producing actor's monotonic segment. The report retains four separate local callable durations. It sets:

- combined_cross_host_elapsed_ns = null;
- combined_duration_status = not_computed_independent_unaligned_clock_domains;
- cpu_time_claimed = false.

Local spans must not be added together as a substitute for a distributed elapsed duration.

## Reproduction

With the repository and the pinned E-CPU checkout available:

```bash
PYTHONPATH=external/E-CPU python -m py_compile \\
  experiments/multi-observer-causal-reconstruction/reconstruct.py \\
  experiments/multi-observer-causal-reconstruction/test_reconstruct.py

PYTHONPATH=external/E-CPU python -m unittest discover \\
  -s experiments/multi-observer-causal-reconstruction \\
  -p 'test_*.py' -v
```

Validate the three schemas with a Draft 2020-12 JSON Schema implementation:

- record.schema.json
- report.schema.json
- report-predicate.schema.json

The hosted workflow is .github/workflows/multi-observer-causal-reconstruction.yml. It uses separate source, receiver, observer, and verifier jobs. The receiver receives the source record through GitHub Actions artifact storage. The observer is independent and does not receive a message from A or B. The verifier receives all three retained records as artifacts.

## Observed hosted result

**Run:** [MOR-001 workflow run #3](https://github.com/Kier73/In-Formation-Space/actions/runs/43455775681)  
**Run ID:** `43455775681` · **Main revision:** `c1913ace3ccd35b6417726e57ef2a0025dcb9561`  
**Report digest:** `56a555755486d79c28df71273c8c7acdaa6f9e899bd282a8a9da9ad4fd810b18`

All five jobs passed: the fixture/test job, source host A, receiver host B, independent observer C, and independent verifier. The verifier confirmed all three producer artifact attestations, reconstructed the event matrix from the retained TemporalFrames, validated the report and predicate against the schemas, and attested the exact report bytes.

The captured causal stamps were:

| Event | Source actor counter | Receiver actor counter | Interpretation |
|---|---:|---:|---|
| A1 | 1 | 0 | First source event |
| A2 | 2 | 0 | Later source-local event; not sent |
| B1 | 1 | 1 | Receiver event after merging A1 |
| C1 | — | — | No causal stamp |

The independent report reconstructed exactly two strict-before pairs (A1 before A2; A1 before B1), one concurrent pair (A2 with B1), and three unobserved pairs (each pair involving C1). There was no global total order.

The report retained four callable-local durations: A1 248,593 ns, A2 201,822 ns, B1 193,491 ns, and C1 283,412 ns. These are per-actor synchronous-callable monotonic spans, not CPU-time measurements. No combined cross-host duration was computed.

The wall-source offsets were deliberately set to +12 hours for A, -12 hours for B, and +3 hours for C. The resulting calendar readings were retained but explicitly excluded from causal ordering. This demonstrates that the reconstruction did not need a common wall clock; it does not measure natural clock skew or calibration accuracy.

The source, receiver, observer, and verifier used four distinct GitHub-hosted jobs and temporal actor identities. The event message was relayed through GitHub Actions artifact storage. This run therefore establishes independent artifact-based causal reconstruction, not direct E-CPU peer transport, distinct physical servers, or physical simultaneity.

The report and its verifier predicate are retained as the `multi-observer-causal-reconstruction-report` artifact in the linked workflow run. The report SHA-256 is `129b18df6d022553c9aa5c0bd544dee16d8910701a8ee847dd7d23db6b2d8930`.

## Interpretation boundary

The successful hosted run establishes that the protected workflow produced separately attested records, and that a fourth job reconstructed the declared pairwise vector-clock relationships from those records. It does not establish direct peer-to-peer E-CPU transport: the A1 payload in this experiment is relayed through GitHub Actions artifacts.

The deliberately offset wall readings do not establish physical clock skew or calibration accuracy. They demonstrate that this verifier does not need to compare wall clocks to reconstruct the expected causal structure.

GitHub artifact attestations bind record bytes to the configured repository/workflow/ref policy. They do not prove that a participant's claimed callable executed honestly, nor do the GitHub-hosted job identities prove separate physical servers, administrators, regions, or failure domains.

A2 and B1 being concurrent means neither recorded vector stamp is componentwise before the other. It does not assert that their physical execution intervals overlapped. C1's relation to all other events remains unobserved because no causal stamp was recorded for C1.

## MOR-002: causal reconstruction over the Tailscale E-CPU channel

**IHP-008 activation guard:** PR and push events run the MOR-002 test job, but all four live participant jobs now require an explicit manual workflow dispatch from main. The separate OIDC/tag prerequisites and the independently verified mTLS/causal evidence gates are unchanged. See [federation readiness](../tailscale-federation-readiness/README.md).

**Status:** merged to `main` as `aa5cc63c6936ce1ac69d8c1c76ab19e007e8d257`; PR CI passed. The first main-branch run completed its tests and attested the independent C1 observer, but both peer jobs failed closed because the dedicated MOR-002 Tailscale secrets were absent. No MOR-002 tailnet join or E-CPU socket exchange has yet been observed.  
**Workflow:** [MOR-002 Tailscale causal reconstruction](../../.github/workflows/mor002-tailscale-causal-reconstruction.yml)  
**Transport implementation:** [IHP-006 direct mTLS operation path](../../bridges/observation-path/TAILSCALE-MTLS-OPERATION-PATH-IHP-006.md)  
**Pinned E-CPU revision:** `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`

MOR-002 asks whether MOR-001's causal reconstruction survives when the A1-to-B1 semantic message uses the actual E-CPU peer channel instead of GitHub Actions artifact storage. It reuses IHP-006's `SocketTransport`, mutually authenticated TLS, `ReliableChannel`, sequence-one delivery, ACK, sender-verifiable signed receiver receipt, certificate pins, signed endpoint advertisement, and reciprocal peer-route observations. It does not implement a second transport.

### Event placement is part of the experiment

| Event | Host | Capture point | Causal evidence |
|---|---|---|---|
| A1 | Client/source | Source operation completion, before the signed envelope is sent | E-CPU causal stamp included in the signed envelope |
| B1 | Server/receiver | Receiver operation start after merging A1, inside the ReliableChannel commit path | E-CPU causal stamp included in the signed receiver receipt |
| A2 | Client/source | Immediately after `ReliableChannel.send(A1)` returns, before the client processes the ACK or receipt | Later source-local stamp in a separately signed and attested sidecar; not included in A1 |
| C1 | Independent observer | Separate job with no causal-domain clock | No causal stamp |
| Verifier | Fourth job | After receiving all evidence artifacts | Independently validates and reconstructs the relation matrix; does not join the tailnet |

This timing is intentional. E-CPU's `ReliableChannel.send()` hands A1 to the transport before returning. On the receiving side, the commit callback validates and records B1 before the channel emits its ACK. The client records A2 after A1 has entered the transport, but before it processes any ACK or receiver receipt. Therefore the source has not learned B1's existence when it emits A2. A2's signed sidecar commits to the exact A1 frame, operation span, and envelope digest, while explicitly declaring `transferred_in_handoff: false`.

This avoids a subtle false-concurrency test: A2 must not be emitted before A1 is sent. If it were, a stale A1 envelope could omit later source state and make two stamps appear incomparable even though the sender's actual program order placed A2 before the handoff. The implementation and a regression test assert the ordering of send, A2 capture, and ACK processing.

MOR-002 uses E-CPU's native **sparse** vector clocks. Actors absent from a vector have counter zero; the experiment does not inject an artificial complete actor roster into the runtime. With A1 = `{A:1}`, A2 = `{A:2}`, and B1 = `{A:1,B:1}`, the expected matrix is:

| Pair | Expected result | Basis |
|---|---|---|
| A1, A2 | before | Same source actor advanced after A1 was sent |
| A1, B1 | before | B merged the actual A1 stamp before recording B1 |
| A2, B1 | concurrent | Neither actor had received the other's later event |
| A1, C1 | unobserved | C1 has no causal stamp |
| A2, C1 | unobserved | C1 has no causal stamp |
| B1, C1 | unobserved | C1 has no causal stamp |

The interpretation of A2/B1 is causal incomparability, not a claim that their physical execution intervals overlapped. There is no global total order. MOR-002 does not use wall-clock samples or derive cross-host durations; it preserves local operation spans and leaves combined elapsed time null.

### Transport and provenance

Only the semantic A1 envelope, ReliableChannel ACK, and signed receiver receipt travel over the Tailscale-protected E-CPU mTLS socket. GitHub Actions artifacts carry public certificates, the server's signed endpoint bootstrap, the source-local A2 sidecar, the independent C1 record, and attestable evidence. The independent verifier remains outside the tailnet.

The client and server take local Tailscale route observations adjacent to their authenticated socket session. The third host validates that the observations identify reciprocal socket endpoints. Each route type remains an independent point-in-time status observation; it is not a packet-level trace of every TCP segment.

### Dedicated federation setup

MOR-002 intentionally does not borrow IHP-006's federation credentials. A live hosted run requires:

1. A separate Tailscale Workload Identity Federation/OAuth configuration restricted to this repository, the MOR-002 workflow, and the protected `refs/heads/main` workflow context.
2. The Tailscale tag `tag:mor002-mtls-ci`, with a narrowly scoped policy permitting TCP port `41763` between the tagged client and server. The verifier and observer do not join this tailnet.
3. Repository Actions secrets `MOR002_TS_OAUTH_CLIENT_ID` and `MOR002_TS_AUDIENCE`, populated from that dedicated Tailscale configuration.

The workflow fails closed if either secret is absent. It does not fall back to public IP networking or to IHP-006's existing identity. The Tailscale action is pinned to commit `064b10558093f38325e838ddea35486bdc6b1d5c` and version `1.104.6`; the listener binds only to the server's validated Tailscale IPv4 address on the existing IHP-006 port.

A transport failure produces an explicit `direct_transport_unavailable` report with no causal-success matrix. It is not converted into an artifact-relayed success. A missing federation secret fails the peer job's preflight; it is a configuration prerequisite, not evidence that the transport itself failed. The first main-branch attempt ([run 43469165982](https://github.com/Kier73/In-Formation-Space/actions/runs/43469165982)) recorded this exact state: tests passed; the C1 observer record and attestation were produced; the client and server stopped at the dedicated-secret preflight; and the off-tailnet verifier was skipped. The run therefore provides no evidence about the MOR-002 tailnet route or peer socket.

### Reproduction and limits

The MOR-002 test file checks source-local A2 signing, sparse-vector relations, C1's missing causal domain, the send/A2/ACK placement, and the fail-closed workflow configuration. The hosted test job also runs the existing IHP-006 direct-mTLS regression suite and validates the MOR-002 Draft 2020-12 schemas.

Even after a successful hosted run, the evidence will establish authenticated exchange between distinct GitHub-hosted jobs, not distinct physical servers or independent cloud-provider failure domains. Artifact attestations bind exact bytes to the configured workflow identity; they do not prove honest computation. mTLS and Ed25519 prove possession of the pinned keys and peer identities, not benign execution. Local operation spans are elapsed intervals inside actor-scoped monotonic clocks, not CPU time or cross-host latency.

MOR-001 remains the independently successful artifact-relay baseline. MOR-002 is the direct-channel comparison; its live result must be read from the linked Actions run and not inferred from passing pull-request tests alone.
