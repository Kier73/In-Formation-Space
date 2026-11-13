# RE-005 — Independently witnessed events are not automatically causes

**Status:** exact synthetic experiment with distinct A (actuator), C (event witness), B (plant readout), and D (verifier) roles. The repository workflow exercises the real E-CPU `TemporalContext`/`CausalStamp` implementation pinned at `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`; its independent hosted jobs and controls require separate successful CI evidence. This is *not* a physical sensor, physical source attestation, randomized clinical experiment, or universal causal-discovery algorithm.

## Question

If an external event is observed by a third actor rather than inferred by an actuator or plant observer, does its authenticated event record establish that the event **caused** a response? **No.** It can establish a scoped claim that the enrolled witness issued particular records and that those records are consistent with a declared causal handoff. It cannot, without additional justified assumptions or interventions, distinguish an event's causal role from a common cause or coincidence.

## Mathematical fixture

Three declared episodes with binary external-event `E` and unobserved background variable `U`. A command acts on the plant each episode. The hypothetical response is one of:

- `event_causal`: `Y = 1 + E`;
- `common_cause_marker`: `Y = 1 + U` (E is a correlated marker, not a causal input);
- `common_cause_alias`: same input-output law as the marker but different private realization.

The first two episodes are passive, with `(E,U)=(1,1)` and `(0,0)`, so all laws yield `(Y=2,Y=1)` despite perfect event-output correlation and independently recorded E. The third *synthetic controlled* episode declares `(E,U)=(0,1)`, so the causal hypothesis predicts `Y=1`, while both common-cause candidates predict `Y=2`.

| Episode | E | U (unobserved) | Event-causal Y | Common-cause Y |
| --- | ---: | ---: | ---: | ---: |
| Passive positive | 1 | 1 | 2 | 2 |
| Passive negative | 0 | 0 | 1 | 1 |
| Controlled negative | 0 | 1 | 1 | 2 |

**Critical assumption:** an event witness observing `E=0` does *not* establish that `U` remained fixed or that an unknown alternative disturbance was excluded. The controlled episode may narrow candidates **only** when the verifier explicitly receives `controlled_exclusion_assured=True` from a separately trusted source. That Boolean is an injected synthetic contract, not independently demonstrated by the witness MAC or E-CPU clock. Without it, the third episode is marked `not_identifiable`, and all three candidates survive. With it, the two common-cause aliases survive, but no **physical causation** is declared proved.

A signed or MAC-authenticated observation record attests to the data origin **relative to a trusted key**, not the truth of the asserted physical event, nor that E caused Y. Our HMAC key is issued in a dedicated GitHub Actions job and passed to C and D, not to A or B. **This is a deliberately bounded key-enrollment demonstration:** the one-run key is transported via Actions artifact storage (a shared workflow trust domain) and is not a hardware-backed identity, protected secret store, GitHub OIDC attestation, or independent authentication of physical equipment. The repository's deterministic local report uses an openly specified test key and therefore has **no secret-key security**; the hosted workflow generates a fresh random key.

## Separate-host temporal path

The hosted workflow uses real E-CPU `TemporalContext` on distinct jobs. A emits A0/A1/A2 and C emits C0/C1/C2 without receiving one another's stamps; they are **vector-clock concurrent**, not necessarily physically simultaneous. B receives the *last A and C causal stamps* before producing B0/B1/B2. The independent verifier checks:

- `A2 concurrent C2`;
- `A2 before B0` and `C2 before B0`;
- `B0 before B1 before B2`;
- all actor-local vectors advance exactly as the declared fixture requires;
- the B evidence refers to the exact public A/C records supplied to D;
- C's assertions validate under the enrollment key, with role/episode/session bound by HMAC.

No cross-host wall-time subtraction is attempted. The local integer tick coordinates deliberately use distinct offsets and are **synthetic fixture coordinates**, not measured physical time. The third-party witness is not an independently verified physical disturbance sensor. A digest without the enrolled HMAC is **not** origin authentication. An HMAC alone is **not** an assertion that the witnessed event caused anything.

## Reproduction

Standard-library model and regression tests:

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/independent_event_causation.py > /tmp/re005_report.json
cmp experiments/response-equivalence/re005_report.json /tmp/re005_report.json
```

Real E-CPU runtime check after checking out the pinned dependency in `external/E-CPU`:

```bash
PYTHONPATH=external/E-CPU:experiments/response-equivalence \
  python experiments/response-equivalence/ecpu_re005_cases.py
```

Hosted workflow: `.github/workflows/re005-independent-witness.yml`. Distinct enrollment, source, witness, receiver and independent verifier jobs emit public artifacts; D receives the ephemeral enrollment key only to validate witness HMACs. The workflow also checks the old RE-001–RE-004 tests. Tests reject tampering, changed event claims even after rehashing, altered role/session, replayed witness episodes, missing evidence, falsely reported causal dependencies, denied witness reads, and rewritten receiver stamps.

## Interpretation and next frontier

- **Established in the fixture:** event/output correlation and a third actor's authenticated observation do **not** establish physical causation. A controlled intervention discriminates an explicit, finite candidate set only when its exclusion/stability assumptions are admitted. Equivalent internal realizations remain indistinguishable.
- **Not established:** real source identity, environmental sensors, independent fault domains, a secured key-registration service, verified exogenous intervention, unobserved-confounder exclusion, physical causal effect, independent transport or E-CPU consensus/admission. GitHub Actions jobs are independent processes, not verified distinct physical hosts.
- **Next question:** Can the exclusion assumption itself be supported by independently checked intervention receipts and negative-control sensors, rather than a Boolean given to the verifier? A useful next path is a real host-distributed, independently attested perturbation with control and treatment arms and explicit interference checks.

## Research lineage

- [RE-001–004](README.md): response equivalence, active attention, independent state reconstruction, and intervention-vs-drift.
- [E-CPU temporal semantics](https://github.com/Kier73/E-CPU/blob/main/mailcpu/temporal.py): typed causal time, vector clock and independent local domains.
- [In-Formation-Space MOR-001](../multi-observer-causal-reconstruction/README.md): artifact-relayed independent causal reconstruction across GitHub jobs.
- [In-Formation-Space intervention-aware attention](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md): selected observations may change the world.
- [VGI Build 15](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/theory_development/build_15/BUILD_15.md): event correspondence does not imply shared clocks.
