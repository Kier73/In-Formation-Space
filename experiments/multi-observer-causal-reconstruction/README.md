# Multi-observer causal reconstruction

**Experiment:** MOR-001  
**Status:** implementation and local regression suite added; independent hosted-VM execution pending  
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

## Interpretation boundary

A successful hosted run would establish that the protected workflow produced separately attested records, and that a fourth job reconstructed the declared pairwise vector-clock relationships from those records. It would not establish direct peer-to-peer E-CPU transport: the A1 payload in this experiment is relayed through GitHub Actions artifacts.

The deliberately offset wall readings do not establish physical clock skew or calibration accuracy. They demonstrate that this verifier does not need to compare wall clocks to reconstruct the expected causal structure.

GitHub artifact attestations bind record bytes to the configured repository/workflow/ref policy. They do not prove that a participant's claimed callable executed honestly, nor do the GitHub-hosted job identities prove separate physical servers, administrators, regions, or failure domains.

A2 and B1 being concurrent means neither recorded vector stamp is componentwise before the other. It does not assert that their physical execution intervals overlapped. C1's relation to all other events remains unobserved because no causal stamp was recorded for C1.

## Next discriminating step

After MOR-001 succeeds, carry the same four-event graph over the IHP-006 private overlay and E-CPU mTLS/ReliableChannel path. Keep the event contract and independent verifier unchanged, and change only the A1-to-B1 transport. That would compare artifact-relayed reconstruction with authenticated live message delivery without conflating transport success with causal correctness.
