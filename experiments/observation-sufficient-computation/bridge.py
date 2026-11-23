"""OFC-001: intention-sufficient observation forms native computation.

Reuses, without rewriting their governing algorithms:
  IFS IWI-001: exact rank/contingent action policy.
  VGI: explicit source-declared finite partial/known transition semantics.
  Navigable-Compute NCR-004/005: observation-native quotient and algebra.
  E-CPU INTENT-001 + SAB-001: generated processor and receiver-selected path.
  VLD: proof-checked, quorum-receipted alternative realization for affine offers.

The active controller never receives the hidden initial source state. A local
source fixture retains it; only its post-action *visible* channel is disclosed.
Model/table coverage is a declared premise, not inferred from a signature.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import subprocess
from typing import Any, Mapping, Sequence

from vgi.transitions import (
    GroundTransitionSystem, TransitionObservation, TransitionOutcome,
)
from navigable_compute.observed_ground import (
    ObservedEpoch, TransitionObservation as NativeWitness,
    admit_observed_epoch,
)
from navigable_compute.observer_native import (
    construct_native_algebra, navigate_native,
)
from navigable_compute.observer_native_verify import verify_native_algebra
from mailcpu.intention_formed_fabric import FiniteObserverLaw, realize_formed_intention
from mailcpu.substrate_bootstrap import (
    BootstrapPolicy, BootstrapRefused, CarrierBinding, ChannelObservation,
    OperationOffer, ResourceObservation, SubstrateObservation, digest,
    verify_bootstrap_report,
)
from vld.compiler import (
    AuthorityPolicy, EffectSemantics, IntentExpr, IntentionSpec,
    IntentionToRealizationCompiler, ObservationContract,
)

HERE = Path(__file__).resolve().parent
FIXTURES = frozenset((
    "funnel", "branch", "erased", "safe_diagnosis", "silent_conflict",
    "single_alpha", "silent_common_funnel",
))
SCHEMA = "ifs.observation-sufficient-computation.v1"


class ConstructionRefused(ValueError):
    """Evidence, source identity, policy, or execution was not sufficient."""


def _canonical(obj: Any) -> bytes:
    """Stable, finite JSON encoding used for content identities, not signatures."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(obj: Any) -> str:
    """Return a domain-separated identity for one checked record."""
    return sha256(SCHEMA.encode("ascii") + b":" + _canonical(obj)).hexdigest()


def source_fixture(name: str) -> dict[str, Any]:
    """Invoke the ORIGINAL IWI solver/auditor in an independent Node process."""
    if name not in FIXTURES:
        raise ConstructionRefused("unknown declared source model")
    p = subprocess.run(
        ["node", str(HERE / "iwi_source.js"), name],
        text=True, capture_output=True, timeout=20, check=True,
    )
    data = json.loads(p.stdout)
    if set(data) != {"schema", "fixture", "model", "certificate",
                     "source_digest", "producer"} or data["fixture"] != name:
        raise ConstructionRefused("unexpected IWI exported source schema")
    if data["schema"] != "ifs.ofc001.original-iwi-policy.v1":
        raise ConstructionRefused("unrecognized producer schema")
    node_canonical = json.dumps(
        {"model": data["model"], "certificate": data["certificate"]},
        separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf8")
    if sha256(node_canonical).hexdigest() != data["source_digest"]:
        raise ConstructionRefused("IWI source model or policy was changed in transit")
    return data


def _world(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Check the finite contract and independently reconstruct its winning ranks."""
    model, certificate = data["model"], data["certificate"]
    n, start, goal = model["n"], model["start"], model["goal"]
    if type(n) is not int or n < 1 or n > 8 or type(start) is not int or type(goal) is not int:
        raise ConstructionRefused("bounded source model refused")
    if not 0 < start < (1 << n) or not 0 < goal < (1 << n):
        raise ConstructionRefused("invalid source belief or target mask")
    outputs, transitions = model["output"], model["next"]
    if (type(outputs) is not list or len(outputs) != n or
            type(transitions) is not list or not 1 <= len(transitions) <= 8 or
            any(type(row) is not list or len(row) != n for row in transitions) or
            any(type(x) is not int or not 0 <= x < n for row in transitions for x in row) or
            any(type(x) is not int or not 0 <= x <= 7 for x in outputs)):
        raise ConstructionRefused("invalid finite transition or output contract")
    size = 1 << n
    ranks, actions = certificate["rank"], certificate["policy"]
    if (not isinstance(ranks, list) or not isinstance(actions, list)
            or len(ranks) != size or len(actions) != size):
        raise ConstructionRefused("incomplete policy certificate")

    def successor(belief: int, action: int) -> tuple[int, ...]:
        groups: dict[int, int] = {}
        for s in range(n):
            if belief & (1 << s):
                nxt = transitions[action][s]
                groups[outputs[nxt]] = groups.get(outputs[nxt], 0) | (1 << nxt)
        return tuple(groups[k] for k in sorted(groups))

    expected = [-1] * size
    for belief in range(1, size):
        if not belief & ~goal:
            expected[belief] = 0
    for depth in range(1, size):
        delta = []
        for belief in range(1, size):
            if expected[belief] >= 0:
                continue
            if any(all(expected[child] >= 0 for child in successor(belief, a))
                   for a in range(len(transitions))):
                delta.append(belief)
        if not delta:
            break
        for belief in delta:
            expected[belief] = depth
    if ranks != expected or actions[0] != -1:
        raise ConstructionRefused("IWI purported winning/losing ranks not independently reproducible")
    for belief in range(1, size):
        a = actions[belief]
        if expected[belief] <= 0:
            if a != -1:
                raise ConstructionRefused("losing or terminal belief claims an action")
        elif type(a) is not int or not 0 <= a < len(transitions) or not all(
                0 <= expected[next_b] < expected[belief] for next_b in successor(belief, a)):
            raise ConstructionRefused("a selected action is not universally rank-decreasing")
    return model, certificate


def _verified_models(model: Mapping[str, Any]) -> tuple[
        GroundTransitionSystem, FiniteObserverLaw, Any, Any]:
    """Construct independent VGI, NC and E-CPU interpretations of one pinned law."""
    n, nexts, visible, goal = (model[k] for k in ("n", "next", "output", "goal"))
    names = tuple(f"s{i}" for i in range(n))
    actions = tuple(f"a{i}" for i in range(len(nexts)))
    values = tuple((visible[i], int(bool((1 << i) & goal))) for i in range(n))
    observations = tuple(
        TransitionObservation(
            names[s], actions[a],
            (TransitionOutcome(names[nexts[a][s]], values[nexts[a][s]]),),
            evidence=("declared-complete-source-model;not-independent-authentication",),
        )
        for s in range(n) for a in range(len(actions))
    )
    vgi = GroundTransitionSystem(
        names, actions, names[0], ("visible", "goal"),
        observations, {"scope": "declared finite model; hidden initial unknown"},
    )
    if not vgi.complete or GroundTransitionSystem.from_json(vgi.to_json()).fingerprint != vgi.fingerprint:
        raise ConstructionRefused("VGI incomplete or non-reconstructable source")
    law = FiniteObserverLaw(
        names, actions, ("visible", "goal"),
        tuple(tuple(nexts[a][s] for a in range(len(actions))) for s in range(n)),
        values,
    )
    labels = tuple(f"visible{v[0]}goal{v[1]}" for v in values)
    witnesses = tuple(NativeWitness(
        i, s, actions[a], nexts[a][s], labels[s], labels[nexts[a][s]]
    ) for i, (s, a) in enumerate(
        (s, a) for s in range(n) for a in range(len(actions))
    ))
    epoch = ObservedEpoch(
        "ifs.ofc001.declared-source", "static-table-hypothesis.v1",
        tuple(range(n)), actions, tuple(range(n)), witnesses,
    )
    nc = admit_observed_epoch(epoch, expected_head=epoch.source_head)
    algebra = construct_native_algebra(nc.source, nc.language)
    if not verify_native_algebra(nc.source, nc.language, algebra):
        raise ConstructionRefused("NC generated operator algebra not independently verified")
    for s in range(n):
        for a in range(len(actions)):
            vstep = vgi.step(names[s], actions[a])
            if (vstep.target != names[nexts[a][s]]
                    or vstep.output != values[nexts[a][s]]
                    or law.replay(names[s], (actions[a],), ("visible", "goal"))
                    != dict(zip(("visible", "goal"), vstep.output))):
                raise ConstructionRefused("cross-interpreter semantics disagree")
            nr = navigate_native(nc.source, nc.language, algebra, s, (a,), 1)
            if nr.output != labels[nexts[a][s]]:
                raise ConstructionRefused("NC observer-native operation differs from source")
    return vgi, law, nc, algebra


def _host_inventory(machine_operation: str, *, alpha_available: bool) -> tuple[
        SubstrateObservation, BootstrapPolicy, tuple[CarrierBinding, ...]]:
    """Advertise two receiver-admitted hosts, with replaceable preferred route."""
    def resource(locus: str, offer: tuple[OperationOffer, ...] = ()):
        return ResourceObservation(locus, "observation-locus", 1, 30,
                                   "receiver-tested", digest({"locus": locus}), offer)
    def link(name: str, src: str, dest: str, kind: str):
        return ChannelObservation(name, src, dest, (kind,), 1, 1, 30,
                                  digest({"link": name}), 8192)
    resources = [resource("input"), resource("witness", (
        OperationOffer("form.observe.v1", "form.state.v1", "form.observed.v1", 1),
    ))]
    links = []
    for host, cost, enabled in (("worker.alpha", 1, alpha_available), ("worker.beta", 7, True)):
        if enabled:
            resources.append(resource(host, (
                OperationOffer(machine_operation, "form.request.v1", "form.state.v1", cost),
            )))
            links.extend((link(host + ".in", "input", host, "form.request.v1"),
                          link(host + ".out", host, "witness", "form.state.v1")))
    inventory = SubstrateObservation(tuple(resources), tuple(links))
    policy = BootstrapPolicy(
        frozenset({(host, machine_operation) for host in ("worker.alpha", "worker.beta")} |
                  {("witness", "form.observe.v1")}),
        frozenset(edge.channel_id for edge in links),
        "receiver-installed-pure-operators-not-source-claims",
    )
    carriers = tuple(
        CarrierBinding(edge.channel_id, lambda payload, time: payload,
                       digest({"receiver-bound-carrier": edge.channel_id}))
        for edge in links
    )
    return inventory, policy, carriers


def _affine_action(row: Sequence[int], modulus: int) -> tuple[int, int] | None:
    """Recognize an exact ring-affine law only if it matches EVERY state."""
    if modulus < 2:
        return None
    a, b = (row[1] - row[0]) % modulus, row[0] % modulus
    return (a, b) if all((a*x+b) % modulus == row[x] for x in range(modulus)) else None


class HiddenSourceHost:
    """Local receiver with an opaque current state, never returned to controller."""

    def __init__(self, model: dict[str, Any], law: FiniteObserverLaw,
                 original_state: int, *, use_vld: bool = True):
        if not 0 <= original_state < model["n"] or not (model["start"] >> original_state) & 1:
            raise ConstructionRefused("host starts outside the requested possible initial set")
        self._model, self._law, self._state = model, law, original_state
        self._use_vld = use_vld
        self._formed_head: str | None = None
        self.observed = []
        self._vld_compilations = 0

    def perform(self, action: int, *, alpha_available: bool, coordinate: int) -> dict[str, Any]:
        """Use E-CPU actual processor/path planner; VLD independently executes affine cases."""
        if type(action) is not int or not 0 <= action < len(self._model["next"]):
            raise ConstructionRefused("unadmitted IWI policy action")
        from mailcpu.intention_formed_fabric import form_observer_machine
        machine = form_observer_machine(self._law, ("visible", "goal"))
        inventory, policy, carriers = _host_inventory(
            machine.operation, alpha_available=alpha_available,
        )
        previous = self._state
        formed = realize_formed_intention(
            self._law, ("visible", "goal"), f"s{previous}", (f"a{action}",),
            inventory, policy, carriers,
            admitted_interpreters=("worker.alpha", "worker.beta"),
            admitted_observers=("witness",), ingress="input", observer="witness",
            coordinate=coordinate,
        )
        if not verify_bootstrap_report(formed.report, formed.task, formed.plan):
            raise ConstructionRefused("E-CPU independent plan verification refused")
        if self._formed_head is None:
            self._formed_head = formed.machine.fingerprint
        elif formed.machine.fingerprint != self._formed_head:
            raise ConstructionRefused("host change mutated mathematical processor identity")
        expected = self._model["next"][action][previous]
        obs = formed.report["output"]["observation"]
        if obs != {"visible": self._model["output"][expected],
                   "goal": int(bool((1 << expected) & self._model["goal"]))}:
            raise ConstructionRefused("E-CPU actual execution differs from source")
        vld_backend = None
        if self._use_vld:
            affine = _affine_action(self._model["next"][action], self._model["n"])
            if affine:
                a, b = affine
                compiler = IntentionToRealizationCompiler()
                intention = IntentionSpec(
                    f"ofc001.a{action}.coordinate{coordinate}",
                    IntentExpr.affine_mod(
                        IntentExpr.var("private_input"), a=a, b=b,
                        modulus=self._model["n"]),
                    ObservationContract("int_vector"),
                    AuthorityPolicy(f"ofc001.receiver.{coordinate}.{action}"),
                    EffectSemantics.PURE,
                )
                plan = compiler.compile(intention)
                methods = [c for c in plan.candidates
                           if c.backend_kind == "fluid_in_transit_stream"]
                chosen = methods[0] if methods else plan.get_candidate()
                rcpt = compiler.realize(
                    plan, {"private_input": previous},
                    realization_id=chosen.realization_id,
                )
                if rcpt.admitted_observation != expected:
                    raise ConstructionRefused("independent VLD numerical realization differs")
                if not rcpt.authority_audit:
                    raise ConstructionRefused("VLD native quorum continuity evidence absent")
                vld_backend = rcpt.backend_kind
                self._vld_compilations += 1
        self._state = expected
        step = {
            "action": action, "visible": obs["visible"],
            "path": [s.locus for s in formed.plan.steps],
            "machine": formed.machine.fingerprint,
            "task": formed.task.fingerprint,
            "source": self._law.fingerprint,
            "vld_alternative": vld_backend,
        }
        self.observed.append(step)
        # Do not return the hidden state or the goal channel to the controller.
        return {"visible": obs["visible"], "execution": step}

    def audit_goal(self) -> bool:
        """Receiver-held final state is compared with the declared goal only at audit."""
        return bool((1 << self._state) & self._model["goal"])

    @property
    def vld_executions(self) -> int:
        """Count genuine alternative numerical realizations, not model guesses."""
        return self._vld_compilations


def run_intention(
    packet: Mapping[str, Any], *, expected_source_digest: str,
    original_state: int, failover_after: int | None = None,
) -> dict[str, Any]:
    """Run one hidden-source intention from IWI through VGI, NC, E-CPU and VLD."""
    if (not isinstance(packet, Mapping) or
            packet.get("schema") != "ifs.ofc001.original-iwi-policy.v1" or
            packet.get("source_digest") != expected_source_digest):
        raise ConstructionRefused("source head differs from receiver-pinned intention")
    # Refuse a fake self-consistent SHA without validating the actual IWI model.
    model, cert = _world(packet)
    node_canonical = json.dumps(
        {"model": model, "certificate": cert},
        separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf8")
    if sha256(node_canonical).hexdigest() != expected_source_digest:
        raise ConstructionRefused("changed source model or plan")
    vgi, law, nc, algebra = _verified_models(model)
    initial_belief = model["start"]
    if cert["rank"][initial_belief] < 0:
        return {
            "schema": SCHEMA,
            "status": "UNREALIZABLE_FOR_ALL_DECLARED_INITIAL_STATES",
            "source": expected_source_digest,
            "vgi_ground": vgi.fingerprint,
            "nc_language": nc.language.digest,
            "observations": 0, "native_executions": 0,
        }
    # The hidden starting coordinate is passed only to this receiver, never
    # to the IWI plan, native quotient builder, or VLD intention compiler.
    host = HiddenSourceHost(model, law, original_state)
    belief = initial_belief
    steps: list[dict[str, Any]] = []
    while belief & ~model["goal"]:
        rank = cert["rank"][belief]
        if rank <= 0 or len(steps) > (1 << model["n"]):
            raise ConstructionRefused("certificate does not produce finite guaranteed termination")
        action = cert["policy"][belief]
        outcome = host.perform(
            action, alpha_available=(failover_after is None or len(steps) < failover_after),
            coordinate=5,
        )
        group = 0
        for current in range(model["n"]):
            if belief & (1 << current):
                successor = model["next"][action][current]
                if model["output"][successor] == outcome["visible"]:
                    group |= 1 << successor
        if not group or cert["rank"][group] >= rank:
            raise ConstructionRefused("observed branch did not decrease guaranteed rank")
        steps.append({
            "belief_before": belief, "action": action,
            "observed_visible": outcome["visible"],
            "belief_after": group,
            "execution": outcome["execution"],
        })
        belief = group
    if not host.audit_goal():
        raise ConstructionRefused("receiver-held hidden state failed objective")
    result = {
        "schema": SCHEMA, "status": "GOAL_REALIZED_WITHOUT_INITIAL_IDENTIFICATION",
        "source": expected_source_digest,
        "vgi_ground": vgi.fingerprint, "nc_epoch": nc.source_head,
        "nc_quotient": nc.language.digest, "nc_algebra": algebra.digest,
        "ecpu_machine": host.observed[0]["machine"] if steps else None,
        "initial_belief_count": initial_belief.bit_count(),
        "native_executions": len(steps), "vld_redundant_executions": host.vld_executions,
        "observations": len(steps),
        "final_belief_count": belief.bit_count(),
        "final_belief_mask": belief,
        "steps": steps,
        "scope": "known declared static finite model; receiver-local carriers; no physical source attestation",
    }
    result["receipt_sha256"] = _digest(result)
    return result


def demonstrate() -> dict[str, Any]:
    """Exercise blind/contingent policy, host loss, and explicit refusal fixtures."""
    a = source_fixture("funnel")
    b = source_fixture("branch")
    c = source_fixture("erased")
    safe = source_fixture("safe_diagnosis")
    silent = source_fixture("silent_conflict")
    common = source_fixture("silent_common_funnel")
    return {
        "funnel": run_intention(a, expected_source_digest=a["source_digest"],
                                 original_state=2),
        "branch": run_intention(b, expected_source_digest=b["source_digest"],
                                 original_state=2, failover_after=1),
        "erased": run_intention(c, expected_source_digest=c["source_digest"],
                                 original_state=2),
        "multi_law_safe_diagnosis": run_intention(
            safe, expected_source_digest=safe["source_digest"],
            original_state=4, failover_after=1),
        "multi_law_silent_conflict": run_intention(
            silent, expected_source_digest=silent["source_digest"],
            original_state=1),
        "multi_law_common_funnel": run_intention(
            common, expected_source_digest=common["source_digest"],
            original_state=3),
    }


if __name__ == "__main__":
    print(json.dumps(demonstrate(), indent=2, sort_keys=True))
