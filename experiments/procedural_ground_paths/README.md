# PGT-004 — Intention-conditioned observations embedded in real HTTP and stdio paths

**Research question:** Can a trained model choose which part of a mathematical state-space to observe, adapt when its *communication paths* change, and leave the decision of what is sufficiently established to the receiver's exact Ground/authority services?

**Status:** direct local experimental demonstration of observer-process HTTP/stdio heterogeneity; native E-CPU authority and the native `IntentEmbedding` projection are mandatory hosted CI gates, **not claimed successful locally**. The live experiment is **not an IOS-003 authenticated mTLS service** or a Hypervisor admission. It relies on separately enrolled signing keys and local peer processes.

## Continuity and reuse

- **PGT-003:** uses the already-trained 4,193-parameter shared-action neural query scorer and exact 30-function hypothesis language. No new model or synthetic final-answer generator is trained. Prior cost benchmark is separate from this live demonstration.
- **COG-009:** reuses `Host`, `HostProcess`, Ed25519 signer and key identity. The test enrolls three distinct keys, rather than treating HTTP origin identity or a transport ACK as proof of source truth.
- **PGT-003 witness ABI:** reuses `SignedObserverPath`'s challenge/response format and `recover` independent signature/chain verifier, and its salted opaque source commitment.
- **PGT-001 and IFS PON-003:** extend the *actual HTTP path* beyond model artifact retrieval: `GET /v1/observe?request=...` becomes a bounded, receiver-selected observation of the hidden source. The response contains one signed observation; the full source and model weights never traverse this request.
- **E-CPU IOS-001 / IOS-003:** tests that native IOS-001 checks exact sufficiency conditional on a finite Ground, and that native E-CPU's `IntentEmbedding` treats HTTP and stdio descriptors as distinct structural contexts. CI also runs E-CPU's existing IOS-003 mutual-TLS/ReliableChannel regression on pinned fix commit `393462c6e0dafba8e0ee22946ae44227c5c6e4e6`. This experiment does **not** replace or route its live HTTP traffic through IOS-003.

## What really ran

Three separate observer-worker processes hold the same privately salted, eight-coordinate synthetic source. Two offer a local HTTP GET observer interface; one offers the pre-existing signed stdio interface. Each HTTP GET requests a specific finite source coordinate under a fresh nonce, exact source-root digest, and enrolled observer identity. The HTTP handler applies that observation to its private source, signs the exact result with Ed25519, and returns canonical JSON with a SHA-256 `ETag`, bounded `Content-Length`, `Cache-Control: no-store`, and a fixed observation content type. The receiver rejects redirects, unbounded responses, incorrect headers/ETags, substituted keys, mismatched nonces, modified signed contents, or unrecognized HTTP paths.

The **advisory neural model** receives the requested target coordinate, a distribution over candidate mathematical laws, prior signed observations, and a **path-conditioned symbolic cost estimate**. The estimate adds a declared measurement cost to the cheapest two *currently reachable* enrolled-host prices. The model selects the next coordinate; a route selector chooses the cheapest available enrolled hosts for that coordinate; two distinct matching signed responses are required to retain a reported observation. This uses no unobserved source values to choose a query.

The mathematical intention and pinned source identity are stable across changes of HTTP/stdio placement. A process kill is real: once an HTTP host dies, previously committed receipts remain and new observations use the surviving paths. A separate disagreement test terminates one HTTP peer, introduces a contradictory signed stdio answer, retains **unknown**, then restarts a HTTP observer to obtain a second agreeing signed report.

### The trust distinction

- A hash/ETag matches bytes, not origin identity; HTTP is **loopback without TLS**. Ed25519 verifies enrolled signer identity. Receiver-trusted public keys and final evidence head are **out-of-band inputs**, not self-validated by the artifact.
- Two independently enrolled signers may collude or share a false mathematical belief. This experiment **does not** independently prove the observation source's mathematical truth, even when two votes agree. Negative tests make two valid signatures agree on a false answer.
- The 30-function hypothesis family is an explicit *candidate language*, not an admitted model of any unknown internet source. The trained model's inferred target value never becomes an admitted Ground. Only a directly witnessed target-specific observation is returned, marked `WITNESSED_NOT_GROUND_ADMITTED`.
- HTTP ETag and route timings are receiver-observed metadata, not signed physical provenance or independently attested wall-clock/energy measurements. A receiver can replay and hash-check the sidecar representation metadata against signed bytes, but cannot authenticate the historical physical network path from a replay file alone.
- Routes are **actual** bounded local HTTP and local stdio. No passive transit-router execution, independent physical fault domains, real public HTTPS, native E-CPU Hypervisor grant, full IOS-003 integration, hidden-source-independent mathematical admission, or trust-free remote compute is asserted.

## Direct run

Python 3.11+, `numpy`, `torch`, and `cryptography`, with PYTHONPATH pointing to `experiments/procedural_ground_navigation`, `experiments/procedural_ground_training`, `experiments/codonic-capability-atlas` from frozen COG-009 source, and this directory:

```sh
python -m unittest discover -s experiments/procedural_ground_paths -p 'test_*.py' -v
python experiments/procedural_ground_paths/run_path_navigation.py --output /tmp/pgt004-evidence
python experiments/procedural_ground_paths/run_path_navigation.py --output /tmp/pgt004-evidence --mode verify
```

The final verification is designed for a **new process**, not the source-observer runtime. It independently checks every source signature, exact nonce/root/host request, external roster and high-water head, all predecessor hash links, HTTP response byte digest/ETag, and the count of actual HTTP versus stdio response frames. It requires no private keys and makes zero new host requests.

## Direct representative evidence

On the seed-9 case: target coordinate **6**. Initially the neural model advised observing coordinate **1**. With one HTTP host killed (same mathematical intention, same prior), its cost-conditioned next-coordinate advice changed to **2**. The model's actual online sequence requested coordinates 1, 2, 4, 3, 7, with the target eventually directly witnessed. The result matched the withheld synthetic oracle only in the **independent audit**; the online receiver never used that oracle. The three-host local run produced 14 signed receipts, consisting of 12 HTTP and 2 stdio responses, carrying 7,110 observed response bytes; a separate receiver reconstructed them with zero host calls. Timings vary across runs, and only response bytes (not entire HTTP/TCP frame overhead) are counted in this metric.

Local Python tests: **8 pass; 2 native E-CPU tests skip** where native E-CPU is unavailable. Hosted native tests are configured to fail rather than skip and do not certify a deployed HTTP observer until run. Existing PGT-003 regression should also be run.

## Next physical frontier

Bridge this signed HTTP/stdio projection into **native IOS-003** as one locally installed, receiver-policy-admitted observation capability. Its mTLS + ReliableChannel authority remains the native gate. Investigate approved HTTPS endpoints and typed HTTP link/response observations within the admitted Ground, including ETag/conditional retrieval and cache retention as actual observable relations. Then add external Ground certification, independent observer custody, real measured end-to-end path vector, and recovery-lineage storage. *A new protocol is not permission to use an unrelated public server as a compute host.*
