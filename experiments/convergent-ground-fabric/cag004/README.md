# CAG-004: topology-neutral intention and physical resource accounting

Status: independently verified hosted topology-neutral experiment; the five-job protected-main run is preserved in [CAG-004 evidence](results/ci-run-43563184861.md). Physical one/two-port hardware and independent external-provider hosting are NOT established. CAG-004 is inspired by [E-CPU PR #120](https://github.com/Kier73/E-CPU/pull/120) (SHN-001), pinned experimental head 3a81f1c386b1fc223cc0aec354c099c8c1f717a5. CAG-004 does not modify or merge that PR.

## Main proposition

A computational host is a declared active observation/interaction locus, not necessarily a physical machine. PR #120's three logical hosts share ONE interpreter. Thus the host-count is distinct from processor-count, shared failure domains and physical network reachability. We test the same exact signed mathematical intention on (a) that internal one-interpreter network and (b) a separately scheduled, receiver-authorized E-CPU pure-operator host, with independent verification of results and resource claims.

The mathematical request is:

    x(0)=7
    x(t+1)=(5*x(t)+1) mod 65536
    y(t)=(3*x(t)+11) mod 65536

Coordinates: 0, 7, 1024 and 10^15+137. The signed request specifies the law, operator ID, jobs and SHN revision; it does not supply the expected output.

## Roles and trust

1. Source job creates an ephemeral Ed25519 signature over one exact canonical request and a separately retained trust record. The private key is discarded. Protected-main workflow attestations bind both exact bytes to the GitHub workflow, NOT an independently administered publisher CA.
2. Internal host job checks the signed source and imports the exact E-CPU SHN-001 PR-head SHA. Every coordinate is run under both declared boundary-port counts (one and two); both ports remain physically unused in the simulation. The real SHN-001 OwnedNetworkFabric carries bounded byte frames between dispatcher, navigator and projector. The experiment checks full snapshot/restore before every phase, validates FIFO/receipt/journal state, and records 3 interpreter quanta, 3 logical hosts, 6 interfaces, 3 links, exact internal byte totals and 0 external payload bytes.
3. Separate receiver job checks the identical signed source and imports pinned E-CPU main commit 3b57adcc2baaaa7e56e4bab943946f4e87e95c65. It independently constructs a SystemSeed/VirtualGroundRef, registers a local deterministic pure operator, and runs it through E-CPU VirtualLayerRuntime and Hypervisor under an authorized compute-capability process. It requires first ALLOW, exact cached replay without executing again, DENY for a process lacking compute rights, and a verified E-CPU journal. The receiver's arithmetic is an independently written logarithmic affine composition, not code supplied by the source.
4. Verifier job installs NO E-CPU runtime. It checks the Ed25519 source, full result identity per job, independently computed affine oracle, an iterative oracle for small coordinates, internal SHN receipt digests/queue byte totals, receiver authority/replay claims and exact report hashes. On protected main, it checks GitHub artifact attestations for source, public-key bootstrap and both host reports before independent recomputation.

## Falsifiable claims

- All three logical topologies produce the same signed-intent-bound result value and result digest.
- The SHN internal three-host experiment uses one interpreter, not three CPUs; the three steps each consume a finite interpreter quantum, with zero external bytes and explicit bounded internal byte totals.
- Checkpoint restoration preserves all internal queued frames/receipts. Bogus port counts, forged intermediate receipts and changed phase observations are refused.
- The receiver reports only one successful pure-handler invocation per job, followed by cached replay and denial of an unprivileged request.
- Recomputed ordinary content hashes cannot override wrong identity, authority or resource claims.
- Local elapsed nanoseconds can be observed per role but are not synchronized across GitHub-hosted machines. No real chip GPIO, energy acceleration, network throughput or independently administered cloud-provider claims.

## Verification and reproduction

Offline source and tamper checks:

    python -m pip install "cryptography>=43,<47"
    python -m unittest discover -s experiments/convergent-ground-fabric/cag004 -p 'test_contract.py' -v

Hosted path: [.github/workflows/cag004-topology-neutral.yml](../../../.github/workflows/cag004-topology-neutral.yml). The four distinct jobs are source, internal SHN, independent E-CPU receiver and off-host verifier (plus source tests). On main all exchanged artifacts are attested.

CAG-004 is about the relationship of semantic identity to logical host topology, not a replacement for CAG-003's real JetStream/libp2p protocol observations. Real WAN transfer is represented here only by GitHub artifact delivery between separately scheduled jobs, not by physical port measurements.

## Subsequent frontier

Connect this same signed intention through independently controlled network origins and a physically instrumented one/two-port adapter, with stable externally trusted publisher keys and independent fault injection. PON-002 already proves two actual public HTTPS delivery operators over a shared origin and may provide a practical route. A true external-provider proof still needs distinct infrastructure administrative and failure domains. Keep the remaining requirements of CAG-003 issue #197 open.

Sources: [SHN-001 PR #120](https://github.com/Kier73/E-CPU/pull/120), [CAG-003 signed receiver admission](../cag003/README.md), [PON-002 public delivery operators](../../passive-orbit-cache/PON-002.md).
