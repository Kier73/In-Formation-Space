# RCP-001 — Fork-aware common-prefix continuation of a constructed intelligence

**Research:** Can an intelligence survive cloned host authority **without falsely selecting one of two internally valid histories**, while still regaining a safe right to commit new effects?

**Status:** finite, real-E-CPU-quorum, independently verified test; no global consensus solution claimed. This experiment composes existing DAD-001 cloned authority evidence and E-CPU recovery lineage with a **single protected effect receiver**. This receiver is a separately trusted local authority, and must not be copied alongside the original authority quorum.

## Existing mechanisms — not rebuilt

The initial question of rehosting is not open in its basic form. [E-CPU IPS-005](https://github.com/Kier73/E-CPU/blob/main/docs/FENCED_GENERATED_GROUND_IPS005.md) already retains one qualified mathematical result across assigned-host changes. [IPS-008](https://github.com/Kier73/E-CPU/blob/main/docs/RECEIVER_HANDOFF_BARRIER_IPS008.md) freezes effects before an authenticated rehome. [IGC-003](../intention-ground-construction/IGC-003.md) demonstrates actual intention-derived DFA operations across mTLS receiver processes and real E-CPU quorum recovery. VL-I TIME-001 preserves one environment interpreter's causal identity across observation-host changes. NCB-006 additionally serializes two competing *pure* controllers' local resource claims under SQLite.

But **IFS DAD-001 and DMA-001 go beyond host failure**. They show that cloning an entire fixed-membership quorum (including member journals and, in the mTLS case, keys) can produce two conflicting and separately verified histories that appear to belong to the same owner and machine identity. The existing fork observer correctly refuses to elect a winner.

[Resource fencing tokens](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html) are an established technique to prevent stale owners from committing writes, but a fencing epoch produced by a fully cloned authority could itself fork. The relevant uniqueness must be owned at the **effect destination**, not inferred from duplicated source credentials.

## Proposed conceptual leap: recover what both histories can establish

A conventional strategy tries to determine which of the two cloned successors was the genuine one. But **neither** is uniquely established. Instead:

1. Independently verify both E-CPU journal sets, their actual quorum proofs and their incompatible generation-one roots.
2. Compute the **last common predecessor** from those verified roots. In DAD-001's source this is the original externally specified genesis digest; no contested generation-one output is admitted.
3. Atomically **quarantine both** disputed histories at an effect receiver that is *not* part of the cloned membership. The receiver does not promote whichever packet arrived first.
4. Require the **actual original seed bytes**, not merely the claimed common-prefix hash. Otherwise a digest may prove identity but cannot reconstruct a computation.
5. Construct a **new membership incarnation** using the same system identity but independently installed different authority IDs, owner term and membership digest, and seal a real new E-CPU recovery root anchored to those seed bytes.
6. Only after independently checking the new quorum high-water does the effect receiver atomically advance its own local authority epoch. Stale old roots remain refused even if their contents or credentials are otherwise valid.
7. Execute receiver-mediated resource effects only under the exact new root and epoch; deduplicate writes by operation identity within the same SQLite transaction as the authority check.

The mathematical insight is that *identity* can remain at the level of the shared causal Ground while *authority to affect the world* becomes a new, resource-relative relation. There is no need to decide which disputed historical branch was superior. The conflicted branch-specific work is discarded, not silently claimed as preserved.

## Actual experiment (not simulated certificates)

The existing [DAD-001 `produce_cluster`](../duplicated-authority-domain/fork_detection.py) constructs two local copies of **real E-CPU `RecoveryLineageAuthority` journals** using the same three-member identity, owner term and genesis. Each copy independently seals a different generation-one `RecoveryStateManifest` with its own quorum. The unmodified [`observe_two_clusters`](../duplicated-authority-domain/fork_detection.py) reopens all six journal files, replays each authority ledger and confirms conflicting roots from identical membership and predecessor. It emits `winner: null`.

The new [`ForkSafeEffectReceiver`](receiver.py) uses one durable local SQLite database with `BEGIN IMMEDIATE`, pinned old and new authority descriptions, an immutable policy row, receiver high-water, and an atomic effect log. Its input is **the real evidence directories**, not a self-rehashed fork classification supplied by an untrusted sender. It refuses to freeze if independent journal validation fails or the supplied fork does not share the expected original genesis.

For the reproducible tiny fixture, the original seed `b"ifs-duplicated-authority-domain-genesis-v1"` has SHA-256 equal to the fixed GENESIS and is supplied as a trusted **byte artifact** for reconstruction. The new E-CPU membership retains the same `SYSTEM_ID` but declares incarnation 2, term 2 and three **different named members**. Its fresh authority journals are created separately, its new manifest is actually sealed, and the receiver independently checks the exact current quorum high-water. These member labels and local journal locations are not hardware identity attestation; the receiver bootstrap and storage must be protected independently.

The new effect is one receiver-owned SQLite value publication, not a physical actuator, email, payment or distributed multi-resource transaction. The protected receiver makes that one local effect stream unambiguous while the global original-quorum fork remains **unresolved**.

## Discriminating controls

- Two valid clones, each with a genuine quorum proof, cannot publish any effect through a protected receiver that has not installed fresh continuation authority.
- Observing the divergent proofs quarantines the receiver durably, including after a new process reopens its database.
- A missing or incorrect common-prefix *byte artifact* refuses recovery, even with a valid but branch-specific sealed quorum.
- The new independently verified membership must be pinned to the receiver. Merely changing the owner label, presenting an old membership, or self-rehashing a checkpoint does not reconstitute it.
- An old conflicting root with epoch 1 **or with a forged epoch 2** is refused even after the new incarnation starts committing.
- Identical copied states are not misclassified as a divergent fork. Repeated observations of the same fork are idempotent; a different conflicting fork cannot replace a previously frozen one.
- Parallel receiver-local writes to the same operation identity commit once, then return the same receipt; a conflicting value under that identity is refused.
- **Critical negative control:** copy the trusted receiver SQLite database too. The two receiver copies can diverge, proving this solution is only valid when the destination authority is independently protected and not itself cloned.

## What is actually proved and what remains open

This experiment establishes conditional **resource-local linearizable effect continuation** from the last unambiguous causal predecessor, despite two incompatible and locally valid E-CPU quorum histories, within one non-cloned SQLite receiver failure domain.

It does **not** establish which cloned branch was globally legitimate, which host was alive, that a malicious actor cannot copy the receiver database, that separate member keys were stored in HSMs, or that the original machine's full semantic state was reconstructable from an arbitrary digest alone. This DAD-001 case uses an original known seed as the recoverable prefix. Older branches can continue *computing*, but must not mutate this **participating** receiver's resource after its epoch advances. Other effect destinations are not protected.

At most one resource-local successor is committed through one trusted receiver high-water; the method is not a global authority-election system or a solution to arbitrary rollback. If the shared predecessor bytes are missing, the correct answer is **cannot yet reconstruct**, not permission to guess. If the receiver cannot enforce downstream effects atomically, no guarantee of effect exclusivity is implied.

## Reproduce

CI pins E-CPU to `e380070312b7553d8bd4860a460bb7b9dce7070a` and runs Python 3.11/3.13 on Linux/Windows. From the repository root:

```sh
python -m pip install -e ./external/E-CPU
python -m pip install "pytest>=8,<9" "jsonschema>=4,<5"
export PYTHONPATH="$PWD/experiments/duplicated-authority-domain:$PWD/experiments/resource-continuity-prefix:$PWD/external/E-CPU"
python -m pytest -q experiments/duplicated-authority-domain/test_fork_detection.py experiments/resource-continuity-prefix/test_receiver.py
python experiments/resource-continuity-prefix/run_experiment.py --output rcp001-report.json
```

The report includes source quorum root digests, common predecessor identity, protected-receiver revision, new quorum root, actual refused stale writes, and separately measured time for quorum construction, independent fork verification, resource freeze, reconstitution and a new effect. A report digest supports integrity, not unique host provenance.

## Next ambitious experiment

Lift common-prefix reconstitution into VL-I's TIME-001 continuously changing environment Ground, where a copied observer epoch can fork with two different yet locally consistent interpretations. Derive the **largest independently witnessed shared observation section**, continue interpretation from its evidence, and grant the new receiver incarnation only the capabilities supported by those exact shared observations. Then replace the local SQLite receiver with E-CPU's independently authenticated IPS-008 effect receiver, preserving the same proof rules.

That would connect continuous intelligence identity, information-theoretic causal intersection, and resource-effect authority rather than repeatedly building new host-restart machinery.
