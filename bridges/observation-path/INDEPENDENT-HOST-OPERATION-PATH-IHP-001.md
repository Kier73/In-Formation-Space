# Independent hosted-VM operation-path reconstruction

**Experiment:** IHP-001  
**Status:** implementation and CI validation in progress  
**Format:** independent host operation record / report v0.1

## Question

How much of a distributed operation path can be reconstructed by a verifier that did not participate in either operation and did not share either host's process, filesystem, monotonic clock, or in-memory state?

IHP-001 treats this as three separate evidence problems:

1. Did a source host produce a specific operation record?
2. Can a receiver host independently consume that record, merge its causal stamp, and produce a successor record?
3. Can a third host verify the records' provenance and reconstruct the causal edge from the transferred bytes alone?

## Experimental topology

The workflow runs three dependent jobs on standard ubuntu-24.04 GitHub-hosted runners. Each job receives a separate standard hosted runner VM. The jobs share no working directory or in-memory process state; the only record transfer is through named GitHub Actions artifacts.

Source job / VM A produces the operation and handoff payload. Its file is attested with GitHub artifact attestations and transferred through Actions artifact storage.

Receiver job / VM B verifies the source file's attestation before consuming it. It merges the source E-CPU causal stamp into a separate TemporalContext, records its own operation, and attests the successor evidence.

Verifier job / VM C downloads both files independently, verifies both attestations against their exact bytes and the pinned workflow identity, reconstructs the DOP-001 causal edge, and attests the resulting report with a custom predicate binding the verifier job identity and exact report bytes.

The workflow runs only for main pushes or a manual dispatch targeting main. Attestation verification pins the repository, signer workflow path, source ref, and custom predicate type. It also rejects self-hosted runners. GitHub CLI 2.103.3 or newer is required because the signer-workflow matching behavior was corrected in 2.102.0.

## What is reconstructed

The source host measures its synchronous callable using its own monotonic clock and E-CPU's TemporalContext. After the call, it emits its causal stamp and packages the predecessor span digest plus sender completion frame into the existing DOP-001 handoff payload.

The receiver first verifies the source file's signed GitHub artifact attestation. It then creates its own TemporalContext, merges the transferred E-CPU CausalStamp, captures its receiver-start frame, and measures a successor callable with its own monotonic clock. The existing DOP-001 build_causal_handoff_witness function binds the predecessor and successor span digests, the sender and receiver frames, and the relay sequence identity.

The third job downloads the two files independently. It verifies each file's attestation against the actual SHA-256 bytes, checks the exact signer workflow/source-ref policy, checks that both records belong to the same run and attempt but distinct jobs/actors, and calls the existing DOP-001 causal handoff validator. It does not use the worker's or receiver's process memory, local files, or code-generated in-memory object references.

The verifier also creates a report-specific attestation predicate binding the third job identity, exact report-file SHA-256, source and receiver artifact digests, path ID, and causal handoff digest. The final reconstruction report is attested against that predicate, so a later verifier can check not only the report bytes but also which protected workflow job produced it.

## Evidence classes

| Claim | Evidence used | What that evidence establishes |
|---|---|---|
| Record integrity | SHA-256 over canonical record fields and exact file bytes | Detects changes to the record and binds the receiver to the exact source artifact |
| Workflow provenance | GitHub OIDC/Sigstore artifact attestation | Attestation is valid for the artifact digest and accepted repository/workflow/ref policy |
| Hosted-runner policy | gh attestation verify with deny-self-hosted-runners | Rejects attestations identified as produced by self-hosted runners |
| Same experiment | Repository, workflow ref/SHA, Git ref/SHA, run ID and attempt | Both records belong to one main-branch workflow run |
| Host/job separation | Three dependent workflow jobs with separate standard hosted runner VMs and distinct temporal actors | The second operation and third verification occur in different runner VMs from the source job |
| Local operation measurement | Each span's own monotonic start/end coordinates | Duration within that host's measured synchronous call |
| Cross-host precedence | Sender completion frame, payload digest, receiver merged vector stamp, receiver start frame, and endpoint span digests | A causal edge from the source operation to the receiver operation, subject to the truthfulness of the participants |
| Global duration | Not supplied | No cross-host wall duration is claimed |

## Important relay distinction

The channel name github-actions-artifact-relay/v1 describes the experiment's transfer substrate. Its sequence value is a path-local artifact-receipt ordinal. It is not an E-CPU ReliableChannel sequence, a socket frame sequence, a TCP acknowledgement, or proof of delivery over E-CPU's physical transport.

This experiment therefore demonstrates independently produced and independently verified host evidence over a real job-to-job boundary. It does not yet demonstrate a live E-CPU SocketTransport / mutual-TLS connection between the two workers. That is a separate next experiment.

## Clock and duration interpretation

No affine clock calibration is used here. This is deliberate.

The source span is measured in VM A's monotonic domain. The receiver span is measured in VM B's monotonic domain. Vector-clock merging establishes causal order without comparing those clock values. The report retains both local durations separately and sets combined_cross_host_elapsed_ns to null.

This gives a sharp result: **the causal graph is reconstructable without a shared clock; total elapsed time is not.** A future experiment can add explicitly attested calibration evidence, but it must not replace the causal edge with timestamp-order guesses.

## Trust assumptions and limits

- GitHub's OIDC/Sigstore attestation service and the GitHub Actions artifact service are part of the trust base.
- The pinned signer workflow is allowed to make the custom predicate claim. GitHub documents that predicate fields are workflow-controlled metadata; the signature does not turn a claimed runner name or host identifier into hardware attestation.
- The verifier pins the signer workflow path and refs/heads/main, and the source workflow deliberately excludes pull-request execution. Protecting the main branch and reviewing changes to this workflow are therefore essential.
- Standard hosted jobs use separate runner VMs, but the experiment does not establish distinct physical servers, regions, availability zones, power/network infrastructure, administrators, or storage failure domains.
- A malicious or compromised participant can fabricate a locally plausible operation span or vector clock. The attestation authenticates the workflow/artifact provenance; it does not attest that a particular application instruction truly executed in silicon.
- The experiment contains one source node and one receiver node. It does not yet cover retries, duplicated deliveries, fanout, multi-hop relay, crash recovery, revocation, or quorum agreement.
- Operation spans measure synchronous callable boundaries, not CPU time.
- The final report is a reconstruction of the supplied evidence, not a claim that the computation is trustworthy against a fully compromised GitHub runner.

## Reproduction and outputs

The workflow is .github/workflows/independent-host-operation-path.yml.

The CLI is bridges/observation-path/independent_host_path.py:

- produce-source creates the source-host record.
- produce-receiver verifies the source attestation before merging the causal stamp and creating the successor record.
- write-predicate prepares the custom attestation predicate for one record.
- verify verifies both attestations and writes the third-host reconstruction report.

The report is validated against independent-host-operation-report.schema.json, and its custom verifier predicate is validated against independent-host-operation-report-predicate.schema.json. Both the report and predicate are preserved in the runner workspace; the report is preserved as the independent-host-reconstruction-report workflow artifact and receives a Sigstore attestation that signs the exact report bytes and predicate.

## Next discriminating experiment

Replace GitHub's artifact relay with a direct E-CPU SocketTransport session between two independently allocated hosts, retain the same signed operation records and vector-clock handoff, and have a separately allocated verifier validate the peer certificates, signed receipt, exact payload/sequence binding, and reconstructed DOP edge. That experiment would test transport-peer identity and receipt authenticity rather than only hosted-job separation and artifact provenance.
