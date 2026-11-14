# PON-001 — Passive Orbit Navigation on public and expiring hosts

**Research question:** Can a requested finite computation be represented as immutable
pieces of information distributed across public and temporary hosts, and navigated by an
observer after any one holder disappears, without pretending that routers or passive caches
executed the mathematical operations?

This is a new layer on top of [CAG-001](../convergent-ground-fabric/README.md).
It deliberately does **not** recreate or replace SNC-001 through SNC-004B's
mathematical neural host, VGI's admitted Grounds, or E-CPU's authenticated execution
admission. Its subject is **where an operation description exists** and **how an observer
finds a reconstructable path to its result**, not delegated CPU cycles.

## The working model

A source commits to a bounded root manifest SHA-256. That manifest names exactly
five content-addressed CAG-001 packets. A receiver knows the root digest in advance;
no passive host can choose a new root, invent a dependency, or redirect the receiver
to a new network origin. The receiver retrieves each packet from the ordered list of
explicitly authorized passive routes, checks every exact byte string against the
pinned object hash, validates CAG-001 semantic identity and packet structure, and only
then performs local deterministic arithmetic.

The example is:

~~~text
seed  = 3
left  = seed + 4            = 7
right = seed * 5            = 15
merge = left + right        = 22
final = merge * 2           = 44

pinned root SHA-256
  |
  +-- immutable object addresses (SHA-256)
      |
      +-- public GitHub raw HTTPS host (read-only)
      +-- short-lived opt-in loopback HTTP host (read-only, lease)
      |
      +-- receiver verifies exact retrieved bytes
           +-- CAG-001 dependency reconstruction
                +-- deterministic local value 44
~~~

An object address is SHA-256 of the complete canonical packet bytes. The inner
CAG-001 packet digest separately verifies its operation fields. The manifest
is also canonical and *receiver-pinned*. Distinguish these three identities:
semantic operation ID, byte identity, and public URL/location. The first two
remain stable when the third moves or disappears.

Receiver root pin for this fixture:

1345e9576fba37322a92cdf9e48c525c806ba210b389ac9a411ec1923484f229

An HTTP cache may preserve or evict these bytes according to its own rules;
successful retrieval and a pinned digest are not guarantees of persistence or
an independent endorsement of the data.

## Actual public, passive host

The repository deliberately publishes only five benign immutable operation
descriptions and a root manifest under:

experiments/passive-orbit-cache/public/

The optional public route is an **immutable Git commit SHA** path on
raw.githubusercontent.com, not a mutable branch address. Its origin and
repository/object-subtree restrictions are hard-coded in this minimal
experiment to prevent arbitrary proxying or redirect-based requests to
other sites. It performs only bounded HTTP GET with no credentials, no
writes and no execution.

This public static hosting is a real, authorized third-party provider
serving repository-owned bytes; no claim is made that its CDN cache has
placed copies on specific intermediate routers or that GitHub executed
the described program.

## Temporary holder

The opt-in local HTTP server binds only 127.0.0.1 on an ephemeral port,
serves a prepopulated directory, rejects POST and arbitrary paths, and
returns HTTP 410 after a finite lease. It does not accept public
uploads or run untrusted code. The integration experiment launches
this server as a separate process. In the fixture it holds only
the seed and left packets; the receiver must navigate to the public
host for the other three operations.

After the lease expires, an observer reconstructs the *same* final
value by fetching all objects from public HTTPS. The observer records
which source served each object, local elapsed measurements, and any
410/missing/tampered observations, without confusing those route
events with Ground admission.

## Evidence and tests

Automatic GitHub workflow:
.github/workflows/pon001-public-passive-orbit.yml

- Two Python versions test full source-pin verification, complementary
  passive holders, expiry, fallback, missing dependencies, corrupted
  object bytes, rehashed semantic tampering, root mutation, immutable
  public URL restrictions, write rejection and request bounds.
- A separate hosted job performs **actual public HTTPS GETs** to
  raw.githubusercontent.com under the tested commit SHA, plus reads
  from the temporary local server. A second run after the lease
  expires must recover from public storage alone. The report
  distinguishes a physically remote public provider from the
  same-run local temporary test service.
- The existing CAG-001 permutation and conflict suite runs alongside
  the new tests.

Do **not** claim a real Internet public-host result merely because the
local tests pass. The actual-public-GET job must succeed with an
artifact containing the routes used and source object digests.

## How this relates to time-state navigation

Let an operation state be described by a dependency graph whose
verified packet identities are known. At an observation time t,
the receiver can obtain only the subset of packets whose holders
are reachable and whose leases have not expired. The reachable
subgraph at t need not be sufficient to reconstruct the result.

A different route at t+Δ may expose the missing packet. The receiver
reconstructs **without requesting that any passive host compute a
transition**. The time-varying availability of evidence changes which
path is navigable, not the mathematical result certified by the
complete dependency graph.

This is a useful *structural memory and communication-availability*
experiment, but it is not proof that arbitrary computations execute
in the electromagnetic signals of an IP packet or that transit
latency itself supplies processor cycles.

## Physical substrates worth testing next

- **IPFS:** a verified CID can be found through provider routing.
  Persistence requires actual providers or pins; copies are not
  magically guaranteed. See https://docs.ipfs.tech/how-to/pin-files/
- **HTTP edge caching:** a conventional origin may return public
  cacheable responses and edge caches may preserve them, but cache
  allocation and eviction are controlled by the operator. See
  https://www.rfc-editor.org/rfc/rfc9111.html
- **libp2p circuit relay v2:** cooperating relays expose limited,
  leased reservations for peers behind NAT; relays carry traffic
  but do not run the described computation. See
  https://libp2p.io/docs/circuit-relay/
- **Opt-in programmable edges:** Cloudflare Workers, serverless tasks
  or other explicitly provisioned accounts can **execute** a
  verifier or small transformation. They differ from passive caches:
  permission, CPU limits, billing and externally owned governance
  apply. See https://developers.cloudflare.com/workers/platform/limits/
- **Authorized store-and-forward:** a cooperative DTN/queue provider
  can retain bounded immutable packets until a later observer
  retrieves them, with a clear lease and quota.

None of these mechanisms authorizes placing information on random
nonparticipating routers, exploiting open proxies, creating uncontrolled
resource use on public services, or treating transport ACK as execution.

## Next frontier

PON-002 could replace the fixed fixture with independently signed
root manifests, delegated/rotatable source policies and multiple
opt-in third-party holders (for example IPFS plus authorized HTTP).
The hard question is *navigable capability*: can the observer choose
among transient holders, resolve missing state, and verify any exact
pure result **without requiring an always-online authority or remote
compiler**, while still refusing stale, revoked, conflicting or
untrusted operation claims?

A further integration could treat an SNC exact neural capsule as one
large object type and use CAG-001 packets to describe its provenance
and placement. The receiver still must independently verify it
under its own mathematical policy, as SNC-004A already requires.


## Continued orbit experiments

- [PON-002 — signed public-delivery navigation](PON-002.md) verifies bounded Ed25519 root-capability mechanics and exact all-predecessor reconstruction through GitHub raw and jsDelivr public HTTPS, while identifying their shared GitHub source origin.
- [PON-003 — surviving-origin recovery](PON-003.md) separates two signed publication inventories and exact CIDv1/IPFS raw blocks from flat immutable bucket objects. Hosted tests kill a real origin process, reject substituted bytes, and preserve mathematical identity through a surviving host. An opt-in public R2 and IPFS read-only probe is installed but does not claim externally provisioned origin success until independently configured and observed.

Keep *provider delivery*, *persisted origin storage*, *source/key authority*, and *observer mathematical realization* as separate evidence layers.
