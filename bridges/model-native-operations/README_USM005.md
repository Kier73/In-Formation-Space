# USM-005 — Observe a recovered model-operated Ground from another host

This experiment reuses the IFS USM-003 independently reconstructable operation
protocol, pairing it with E-CPU USM-005's actual receiver crash, quorum-sealed
checkpoint and authenticated restart. It belongs in In-Formation-Space because
the verifier must not depend on the program it is verifying.

## Experimental arrangement

The producer GitHub Actions job checks out an **immutable E-CPU USM-005 commit**
and runs a model host connected to a separately launched E-CPU receiver
process. The receiver commits a structural-memory navigation at logical
coordinate `1_000_000_000_137`, quorum-seals a local recovery checkpoint and
hard-exits before ACK. A replacement receiver process restores the state,
reconnects via mutual TLS, and acknowledges the same model operation
without semantic re-entry. The model host process survives the interruption.

The resulting JSON artifact is transferred by GitHub Actions to a second,
independent verifier job. The second job does **not** install or import E-CPU,
VGI, neural inference frameworks or the model checkpoint implementation. It
reuses `independent_verify.py` to reconstruct the exact journal transitions,
operation identities, receiver outputs, digest chain, and independently
re-evaluated source value.

The new `verify_recovered_model.py` also checks:

- The recovered session is identical to the recorded model-issued sequence
  `observe -> propose -> read` with exactly three causal events.
- The returned value, receipt ID, Ground digest, revision, and trace digest
  agree across the producer's independent observation envelope and recovery
  result.
- The producer's declared receiver-loss cut, pending reliable sequence 3,
  unchanged model PID, authenticated reconnection, and generation 1→2
  succession are internally consistent.
- The producer explicitly records that its three recovery anchors share one
  failure domain. This is quorum protocol exercised locally, **not** a
  simulated independent quorum with three physical machines.
- A fabricated result fails the known source formula, even if the attacker
  reconstructs the record hash chain and outer artifact digest.

## Reproduce without installing E-CPU

```bash
python -m unittest discover \
  -s bridges/model-native-operations \
  -p 'test_recovery_independent.py' -v

python bridges/model-native-operations/verify_recovered_model.py \
  usm005-source.json --output usm005-independent-report.json
```

The second command requires a JSON file produced by E-CPU USM-005. The hosted
workflow provides that file automatically.

## What this proves, and what it does not

The **producer** executes the actual E-CPU implementation on a hard-killed
receiver process and a new socket. The **independent verifier** confirms that
the exported causal record is internally consistent and that its final
mathematical value agrees with a *separate source implementation*. It cannot
observe the original OS process kill or TLS handshake merely from the report.
It therefore marks `process_liveness_independently_attested=false`.

It does not implement E-CPU's quorum signature/certificate verifier, so
`native_quorum_signatures_independently_verified=false`. The reported zero
semantic reentries are supported by the native E-CPU receiver's state
comparison and original operation history, but a standalone JSON artifact
cannot independently attest every host-side effect.

The source is a deterministic mathematical fixture, not a physical sensor
stream; this tests a particular bounded state-space and does not prove all
possible future states. The two GitHub Action jobs are separate host
environments joined by artifact transfer, not an online TLS link between
independent GitHub runners.

## Related work

- E-CPU [USM-004](https://github.com/Kier73/E-CPU/pull/140): authenticated
  model process issues actual E-CPU calls over native MailCPU ReliableChannel.
- E-CPU [USM-005](https://github.com/Kier73/E-CPU/pull/141): explicit
  post-commit/pre-ACK receiver death, native registry/channel restoration,
  and quorum-anchored state high-water.
- IFS [USM-003](https://github.com/Kier73/In-Formation-Space/pull/229):
  independent host trace, hash, and known-source navigation reconstruction.
- Earlier E-CPU receiver/terminal recovery and rehoming experiments provide
  the recovery lineage and semantic retry rules reused here.

A natural subsequent experiment is to distribute the recovery ledger across
separate authenticated hosts, exercise competing owner epochs, and ask VGI to
verify mathematical equivalence between original and reconstructed Ground
interpretations, not only operation chronology.
