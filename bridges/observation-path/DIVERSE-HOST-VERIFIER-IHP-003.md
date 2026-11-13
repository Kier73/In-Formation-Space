# IHP-003: Diverse implementation reconstruction of independent host evidence

**Experiment:** IHP-003  
**Status:** implemented; first live four-job main-branch execution passed on 2026-11-13T03:45:05Z  
**Format:** diverse host reconstruction report v0.1

## Question

Can a separately scheduled verifier reconstruct the IHP-001 source-to-receiver causal edge using a second implementation, rather than importing the Python validators that produced and verify the original evidence?

IHP-001 already separates the source, receiver, and primary verifier into distinct GitHub-hosted jobs. The primary verifier checks the source and receiver artifact attestations and then reconstructs the handoff through the repository's shared independent_host_path.py, distributed_operation_path.py, operation_spans.py, and temporal_provenance.py implementation.

That is independent execution across hosts, but the reconstruction code is not implementation-diverse. A defect shared by the producer and verifier can survive a clean run if both interpret the contract in the same mistaken way.

IHP-003 adds a fourth hosted job with a separate, standard-library-only reconstruction implementation.

## Topology

The existing three jobs remain unchanged:

1. source_host records a local operation, causal frame, and handoff payload, then attests the exact source-record bytes.
2. receiver_host verifies the source attestation, merges the sender causal stamp, records a successor operation and handoff witness, then attests the exact receiver-record bytes.
3. verifier_host verifies both artifact attestations against the exact artifact digests and pinned signer workflow, then produces the primary reconstruction report.

The added diverse_verifier_host job:

1. Runs as a separate GitHub-hosted ubuntu-24.04 workflow job.
2. Downloads the same source-host-evidence and receiver-host-evidence artifacts.
3. Uses only diverse_host_verifier.py and the Python standard library to parse and reconstruct the records.
4. Validates its report and report-predicate schemas.
5. Attests its own report bytes with the fourth job's GitHub workflow identity.
6. Preserves the report as diverse-host-reconstruction-report.

The new verifier does not check out E-CPU and does not import the original IHP verifier, DOP-001, the operation-span validator, or the temporal-provenance validator.

## Independent checks

The diverse implementation recomputes and checks:

- canonical UTF-8 JSON byte representation for both downloaded records;
- source and receiver record digests;
- the receiver's binding to the exact source artifact bytes;
- both operation-span digests and local duration arithmetic;
- host, actor, and monotonic clock-segment bindings;
- the source handoff-payload digest;
- the receiver handoff-witness digest;
- path, attempt, predecessor, successor, and sender/receiver frame correspondence;
- local monotonic endpoint constraints within each host's own clock domain;
- strict vector-clock happens-before from sender completion to receiver start;
- the path-local artifact-relay sequence equality.

The vector-clock relation is computed independently by componentwise comparison over the union of actor IDs. A missing component is treated as zero. The verifier accepts only a strict before relation; equal and concurrent are not causal edges.

The report keeps source and receiver local operation durations separate. combined_cross_host_elapsed_ns remains null because the hosts do not share a calibrated monotonic epoch.

## Deliberate separation from cryptographic attestation verification

The diverse verifier does not run gh attestation verify and does not authenticate the Sigstore signatures on the source or receiver inputs. That remains the primary verifier_host job's responsibility.

This separation is intentional:

- IHP-001's primary verifier answers whether the transferred bytes have acceptable artifact attestations and whether the shared implementation reconstructs their causal relation.
- IHP-003 answers whether a distinct implementation can reconstruct the content and causal relation from the same exact bytes.

The fourth job's attestation authenticates the provenance of its own report under the GitHub workflow identity. It does not retroactively authenticate the input records. Its report says this explicitly.

## What a passing result would establish

A passing fourth-job run would show that:

- the same transferred records can be parsed and checked by an implementation that does not reuse the primary validator modules;
- the second implementation reconstructs the same single directed handoff edge from the byte-level artifacts;
- no shared monotonic clock or combined cross-host duration is needed for that causal conclusion;
- the independent report can be tied to the exact report bytes and the fourth workflow job.

This is stronger than replaying the same validator in a new process, but narrower than independent confirmation of the underlying physical operation.


## First live execution

The first main-branch run completed successfully:

- **Run:** [Independent hosted-VM operation path #43360810370](https://github.com/Kier73/In-Formation-Space/actions/runs/43360810370)
- **Commit:** \`ed85cc131e1c9e3bf3251766f8feafe0693a091e\`
- **Workflow conclusion:** success
- **Source host:** success; produced, attested, and uploaded its operation record.
- **Receiver host:** success; verified the source attestation, merged the sender causal stamp, produced and attested its successor record, and uploaded it.
- **Primary verifier:** success; verified both source and receiver artifact attestations, reconstructed the causal path, validated and attested its report.
- **Diverse verifier:** success; reconstructed from the same downloaded records using the independent standard-library implementation, validated and attested its report.

The two reports were downloaded from the run's preserved artifacts and compared. They agree on the exact source and receiver span digests, the exact handoff digest, sender and receiver actor identities, and the single directed causal edge:

| Evidence | Primary verifier | Diverse verifier |
|---|---|---|
| Source span digest | \`b1fbc7473a468d15af044500784e6552f98779e20c0dc32c82956191aab49d0e\` | same |
| Receiver span digest | \`63f665ec0a4a9e53ecb08b86fbddecb9b83bfad21655d812d76aa726b1c196e3\` | same |
| Handoff digest | \`1a7155a5450d7ba07a783f54db3639ec7d451b6712419ebd5403dec251697e7e\` | same |
| Causal edge count | 1 | 1 |
| Sender Lamport | 1 | 1 |
| Receiver Lamport | 2 | 2 |
| Sender vector | \`{source: 1}\` | \`{source: 1}\` |
| Receiver vector | \`{source: 1, receiver: 1}\` | \`{source: 1, receiver: 1}\` |
| Relation | before | before |

The primary verifier's source and receiver attestations both report a verified signature certificate, one verified timestamp, the exact subject digest, and the pinned main-branch workflow as signer. The diverse report separately attests its own exact report bytes; it does not claim to verify the input signatures.

The measured local synchronous-call durations in this run were:

- source host: **224,958 ns** (approximately 0.225 ms);
- receiver host: **273,071 ns** (approximately 0.273 ms).

The two values belong to different monotonic clock domains. Both reports therefore retain \`combined_cross_host_elapsed_ns: null\`. They are not transport latency, CPU time, or an end-to-end duration.

The source and receiver artifacts are preserved as \`source-host-evidence\` and \`receiver-host-evidence\`; the two reports are preserved as \`independent-host-reconstruction-report\` and \`diverse-host-reconstruction-report\`.

This live result supports one specific conclusion: two separately scheduled verifier jobs, one using the primary implementation and one using a diverse standard-library implementation, reconstructed the same causal edge from the same byte-identical host records, while the primary verifier additionally authenticated the input artifact attestations.

It does not eliminate common-mode errors in the format specification, prove physical execution, or establish independent physical infrastructure. The jobs still share GitHub's workflow control plane and artifact service, and the records remain participant-produced claims.

## What it would not establish

A passing result would not establish:

- that the source or receiver physically performed the claimed computation;
- that the source or receiver artifact signatures were valid (the primary verifier checks those);
- that the two implementations are independent of the written format specification or free of common-mode conceptual errors;
- that the runner labels imply independently attested physical servers, regions, power, networking, or administrators;
- that the artifact relay is E-CPU ReliableChannel or direct TCP/mTLS transport;
- that cross-host elapsed time or network latency is known.

The records still originate from the same workflow, and the jobs share GitHub's control plane and artifact service. A malicious participant can construct internally consistent but false evidence.

## Reproduction

Focused standard-library tests:

    python -m py_compile \
      bridges/observation-path/diverse_host_verifier.py \
      bridges/observation-path/test_diverse_host_verifier.py

    python -m unittest discover \
      -s bridges/observation-path \
      -p 'test_diverse_host_verifier.py' -v

The existing IHP workflow's diverse_verifier_tests job runs on pull requests and checks both JSON Schemas against a generated fixture report and predicate:

    .github/workflows/independent-host-operation-path.yml

The live four-job run is launched by the existing main-only IHP workflow after this change reaches main:

    .github/workflows/independent-host-operation-path.yml

The result artifact is named diverse-host-reconstruction-report.

## Next discriminating work

A useful follow-on is a differential mutation campaign: mutate one field at a time in the source record, receiver record, temporal frames, span endpoints, payload digest, handoff digest, actor vector, and run identity. The primary verifier and diverse verifier should reject the same invalid cases while accepting the same valid boundary cases. Any disagreement should be retained as a counterexample before deciding which implementation or contract needs revision.

A later experiment could ask a separately authored verifier in another language or repository to implement the format from this document and the JSON schemas alone. That would test both implementation diversity and how much of the format is actually reconstructable from its portable description.
