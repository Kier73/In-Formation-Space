# Duplicated authority-domain fork detection

**Experiment:** DAD-001  
**Status:** adversarial clone experiment; live three-job workflow defined in \`.github/workflows/duplicated-authority-domain.yml\`.  
**Question:** can two isolated copies of one fixed-membership authority set each commit a different successor from the same genesis, and can a third observer detect the fork without inventing a winner?

## Why this follows the SQLite authority reconstruction

The [proof-runner SQLite reconstruction](../proof-runner-independent-reconstruction/README.md) established local process restart, owner-generation fencing, durable compare-and-swap, and independent reopening of the persisted ledger. It deliberately did not claim multi-host consensus.

E-CPU already contains a fixed-membership recovery-lineage quorum. Its [recovery-lineage design](https://github.com/Kier73/E-CPU/blob/c82d795e6b7602cc3d6e8c41e8622820914f5cbf/docs/RECOVERY_LINEAGE.md) uses one durable vote per member/slot and a strict-majority certificate. Under one actual set of journals, two quorums intersect, and the intersecting journal cannot prepare two different proposals for the same slot.

That proof assumes the configured members and their durable journals are one authority set. What happens if the entire set is copied before a decision, preserving the same system ID, membership digest, member IDs, owner term, and genesis state?

## Adversarial construction

Both producer jobs use the exact same fixed membership:

- System: \`ifs-fork-detection-machine\`
- Incarnation: 1
- Members: \`authority-a\`, \`authority-b\`, \`authority-c\`
- Owner: \`authority-a\`
- Owner term: 1
- Genesis: one shared, fixed SHA-256 digest
- Quorum: strict majority, therefore two of three

Each job creates three new local E-CPU \`RecoveryLineageAuthority\` journals. Neither cluster receives the other cluster's journals or messages. Both coordinators then seal a generation-1 \`RecoveryStateManifest\` with the same predecessor (genesis), but different state payloads.

Each isolated coordinator should therefore be able to:
1. fsync the same member IDs' prepare votes in its own journal set;
2. construct a valid strict-majority certificate;
3. persist a strict-majority of commit decisions;
4. read back its own exact local high-water and verify its own manifest.

The cluster evidence bundle retains the membership, manifest, proof, raw state payload, and all three complete journal files. The bundle commits to the SHA-256 and byte length of every journal. The two bundle files are separately attested by their GitHub-hosted producer jobs.

## Third-observer reconstruction

The observer does not trust the bundle's self-reported \`local_verification\` flag. It:

- recomputes each bundle digest and each raw journal hash;
- reopens every journal using E-CPU's \`RecoveryLineageAuthority\`;
- replays each durable hash chain;
- reconstructs a \`RecoveryLineageCoordinator\` for each isolated member set;
- obtains each cluster's quorum-supported high-water;
- reconstructs its proof from the retained journals and matches the exact bundled proof;
- asks each local coordinator to verify the other cluster's manifest.

The expected fork result is:

\`\`\`text
same membership digest       yes
same generation              yes (1)
same predecessor             yes (genesis)
left local quorum            valid
right local quorum           valid
left accepts right manifest  no
right accepts left manifest  no
winner                       unknown / not selected
\`\`\`

The distinction matters: the quorum protocol is behaving consistently inside each copy. It is the global uniqueness assumption about the identity and durability of the membership that has failed. A pair of internally valid local proofs does not tell the observer which copy is the authorized continuation.

## Interpretation

A successful live run establishes that two separately scheduled GitHub-hosted producer jobs, each running a separate local three-journal authority set, can produce conflicting quorum-supported roots while reusing the same fixed membership and genesis. A third GitHub-hosted job can independently reconstruct both histories and detect their conflict.

This is an intentional cloned-authority adversarial fixture. It is not evidence that six physical authority machines were operated. The three journals inside each cluster are local files on that cluster's producer runner. The workflow jobs exchange retained artifacts; they do not use E-CPU ReliableChannel or the distributed recovery-lineage TCP/mTLS service.

The result does **not** identify a winner. Both producer bundles are tied to their own GitHub workflow attestations, but those attestations establish the provenance of the two conflicting evidence bundles—not a unique external authority over the duplicated membership. E-CPU's member journal receipts are SHA-256 hash-chain receipts, not digital signatures from independent member keys. A hash chain gives integrity relative to a trusted head; it does not create an uncloneable participant identity.

The observer therefore emits \`cloned_membership_split_brain\`, sets \`winner: null\`, and records that automatic adjudication is refused. It must not use timestamps, artifact arrival order, runner names, or lexical cluster labels to elect a winner.

## What would be required to resolve the fork

A real deployment needs at least one trust factor outside the cloned set:

- a membership/owner-term transition authenticated by a prior, independently protected authority;
- a non-clonable or externally attested identity for each member, bound into prepare votes and commit decisions;
- journals stored in independently protected fault domains that cannot all be copied or rolled back together;
- an explicit membership-reconfiguration protocol with old-configuration and new-configuration overlap rules, rather than silently reusing the same membership digest;
- a monotonic external checkpoint or adjudication service that records which membership epoch is authoritative.

This experiment does not implement those mechanisms. It makes the missing uniqueness assumption and the failure mode inspectable.

## Reproduction

The CI workflow pins E-CPU to \`c82d795e6b7602cc3d6e8c41e8622820914f5cbf\`.

\`\`\`bash
git clone https://github.com/Kier73/E-CPU external/E-CPU
git -C external/E-CPU checkout c82d795e6b7602cc3d6e8c41e8622820914f5cbf
python -m pip install "pytest>=8,<9" "jsonschema>=4,<5"
export PYTHONPATH="external/E-CPU"
cd experiments/duplicated-authority-domain
python -m pytest -q test_fork_detection.py
\`\`\`

The test suite covers divergent roots under one membership, matching duplicate views, raw journal tampering, mixed-cluster journal substitution, proof tampering, and offline report-schema validation. Offline tests do not claim GitHub provenance.

The live workflow has two independent producer jobs and a third observer. Each producer's exact \`bundle.json\` is attested before its journal files are uploaded. The observer verifies both bundle attestations before reconstructing the six journals and attesting the final report.
