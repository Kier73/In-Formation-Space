# Duplicated mTLS authority identity

**Experiment:** DMA-001  
**Status:** local multi-process adversarial experiment against the actual E-CPU recovery-lineage mTLS service.  
**Question:** does a mutually authenticated TLS connection make a fixed-membership authority identity unique, or does it authenticate possession of a trusted certificate/private key and its configured DNS identity?

## Why this follows DAD-001

[DAD-001](../duplicated-authority-domain/README.md) showed that two isolated copies of one fixed membership can each seal a different recovery root when the full member/journal set is cloned. It deliberately tested the quorum logic with independent local journals and did not include a network identity layer.

DMA-001 adds the actual E-CPU RecoveryLineageAuthorityService, RecoveryLineagePeerClient, DistributedRecoveryLineageCoordinator, SocketTransport, ReliableChannel, and mutual-TLS adapters. It asks whether TLS endpoint authentication changes the cloned-membership result.

## Construction

A throwaway test CA issues four short-lived certificate identities:

- owner A: owner-a.mailcpu.test;
- member B: member-b.mailcpu.test;
- member C: member-c.mailcpu.test;
- a trusted negative-control client: intruder.mailcpu.test.

All certificates include client/server authentication EKUs. The left and right authority domains deliberately reuse the exact same owner A certificate and private key, and the exact same B and C server/member certificates and private keys.

The two authority copies share one immutable membership:

- system ID: ifs-mtls-credential-clone-machine;
- incarnation 1;
- members A, B and C;
- owner A, term 1;
- one shared genesis digest;
- strict-majority quorum: two of three.

Each copy starts two independent E-CPU service processes, B and C, with its own local journals. Both owner A processes use the same client certificate/key, but connect to different B/C service processes and different journals. They run concurrently and seal generation 1 from the same genesis with different state payloads.

The services require CA-valid client certificates and check that the client certificate has the expected owner DNS SAN. They also present B/C server certificates, which the owner clients validate against the CA and the expected server hostname. No mock TLS or quorum service is used.

## Observation

A separate observer reopens all six durable journals using RecoveryLineageAuthority and reconstructs each local RecoveryLineageCoordinator proof. It requires:

- each local quorum to have three prepare votes and three durable commit decisions;
- all six journals to pass replay verification;
- each independently reconstructed proof to match the exact owner-issued proof;
- different generation-1 roots to be refused by the opposite copy, with no automatic winner.

The experiment also presents a CA-trusted intruder.mailcpu.test certificate to a service expecting owner-a.mailcpu.test. That connection must be rejected. A subsequent connection using the correct cloned owner A certificate must still read the service's committed high-water.

Two modes are tested. Divergent state labels must produce duplicated_mtls_identity_split_brain; identical state labels must produce matching_duplicate_identity_views. The observer never chooses a winner based on timing, endpoint order, process IDs, or cluster labels.

## Interpretation

The discriminating result is:

**mTLS peer authentication is not, by itself, uniqueness of authority identity.**

In the E-CPU service profile used here, TLS checks the CA trust path, negotiated protocol, server hostname, and expected client DNS SAN. Two processes that possess the same trusted owner certificate/private key can each satisfy that check at two separate service instances configured to expect that same owner DNS identity. The same is true for the copied member identities. Each copy can then exercise its own durable quorum.

That is not evidence that mTLS is broken. It is the expected distinction between authenticating a presented credential and establishing that the credential is unique, hardware-bound, non-exportable, or globally enrolled only once.

DAD-001 and DMA-001 therefore probe different assumptions:

- DAD-001: can the complete local membership/journal set be copied?
- DMA-001: can the credentials that identify that set be copied while still satisfying the configured TLS peer policy?

A successful run makes the same-membership fork reproducible over authenticated TCP/ReliableChannel sessions—but the owner and four member services are separate OS processes on **one machine**. It is not evidence of physically separate machines, independent administrative control, hardware identity, or a deployed multi-host consensus network.

## What would make identity less clonable?

A deployment needs a trust factor outside the copied files and keys. Possible directions include:

- hardware-backed, non-exportable member keys (TPM/HSM) with remote attestation and enrollment tied to the membership epoch;
- a protected external identity registry that prevents one member key from being simultaneously enrolled in two active authority domains;
- journals in independently protected fault domains with rollback-resistant storage;
- an external monotonic witness that serializes membership/owner-term transitions;
- an explicit membership reconfiguration protocol that fences the previous configuration before authorizing a successor.

A certificate fingerprint pin alone can detect a substituted certificate, but it does not stop a byte-for-byte clone of the pinned certificate and private key. The same caveat applies to an ordinary file-backed private key stored next to a copied journal.

This experiment does not implement an HSM, TPM, remote attestation, external enrollment registry, global transaction coordinator, or membership reconfiguration. It isolates the missing uniqueness assumption; it does not resolve it.

## Reproduction

The workflow checks out E-CPU at commit c82d795e6b7602cc3d6e8c41e8622820914f5cbf.

~~~bash
git clone https://github.com/Kier73/E-CPU external/E-CPU
git -C external/E-CPU checkout c82d795e6b7602cc3d6e8c41e8622820914f5cbf
python -m pip install "pytest>=8,<9" "jsonschema>=4,<5"
export PYTHONPATH="external/E-CPU"
cd experiments/duplicated-mtls-authority
python -m pytest -q test_clone_mtls.py
~~~

The suite creates ephemeral OpenSSL credentials, starts four authority-service child processes and two owner child processes, releases both owners through one start gate, reopens all six member journals, and validates the report schema. The two integration cases cover divergent and matching state roots; the divergent case includes the trusted-but-wrong-DNS client test.

## Evidence boundary

- The keys and certificates are deliberately cloned test credentials; private keys are temporary test files and are not production secrets.
- All six authority processes and the observer run on one host. Physical fault-domain separation is explicitly false.
- Each E-CPU journal is a durable hash-chain receipt, not an independently signed statement from a hardware identity.
- A valid per-copy quorum is local evidence, not global adjudication. The winner field remains null.
- No actual theorem computation, VGI kernel acceptance, or external side-effect semantics are tested.
