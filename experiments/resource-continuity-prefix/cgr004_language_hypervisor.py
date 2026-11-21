"""CGR-004: qualified NCR-004 observer language as a native E-CPU pure operator.

E-CPU's ORIGINAL OperatorRegistry, VirtualLayerRuntime, VirtualLayerWorkload,
HeadlessOS Hypervisor and capability admission remain in control. The worker
is a fixed local subprocess, not a dynamic code/executable payload.
NCR-004's original independent verifier is required before any invocation.

Does not mint resource effects, authenticates no external sensor, and does not
claim arbitrary source languages, physical attestation or WAN continuity.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import sys

from navigable_compute.observed_ground import (
    SourceAdmission, admit_observed_epoch, navigate_observed,
)
from navigable_compute.preclosure_verify import verify_preclosure_language
from navigable_compute.preclosure_wire import decode_preclosure

from mailcpu.runtime_qualification import (
    SubprocessQualificationEndpoint, QualificationRefused,
    canonical, digest,
)
from mailcpu.virtual_layer import (
    OperatorRegistry, OperatorSpec, VirtualBudget, VirtualOperatorRef,
    VirtualLayerRuntime, VirtualLayerWorkload,
)
from cgr003_observed_ecpu import load_epoch

OPERATOR = "cgr004.qualified_finite_word"
WORKER = Path(__file__).with_name("cgr004_finite_worker.py")
REQUEST = "ifs.cgr004.finite-native-call.v1"
REPLY = "ifs.cgr004.finite-native-reply.v1"


class GroundLanguageRefused(ValueError):
    """Mathematical semantics, qualified host, receipt or capability failed."""


@dataclass(frozen=True)
class QualifiedFiniteHost:
    """Observed process qualification, not remote authorization or attestation."""
    host_id: str
    endpoint: SubprocessQualificationEndpoint
    source_head: str
    language_digest: str
    policy_allowed_hosts: frozenset[str]
    probes: tuple[str,...]
    qualification_digest: str


def _admission(root: Path, expected_head: str) -> SourceAdmission:
    try:
        epoch = load_epoch(root)
        admission = admit_observed_epoch(epoch, expected_head=expected_head)
        if (admission.source_head != expected_head or
                not verify_preclosure_language(admission.source,admission.language) or
                decode_preclosure(admission.wire) != (admission.source,admission.language)):
            raise GroundLanguageRefused("independent NCR-004 mathematical admission failed")
        return admission
    except (TypeError, ValueError, OSError) as exc:
        raise GroundLanguageRefused("pinned source or NCR-004 certificate refused") from exc


def _request(host: str, source_head: str, initial: int,
             word: tuple[int,...], repetitions: int, nonce: str) -> dict:
    return {"schema":REQUEST, "host":host, "source_head":source_head,
            "initial":initial, "word":list(word),
            "repetitions":str(repetitions), "nonce":nonce}


def _exchange(endpoint: SubprocessQualificationEndpoint, request: dict) -> dict:
    try:
        response = endpoint.exchange(request,max_bytes=8192)
        if (type(response) is not dict or
            set(response) != {"schema","host","source_head","request_digest",
                              "state","output","execution","effect_authorized",
                              "receipt_digest"} or
            response["schema"] != REPLY or
            response["host"] != request["host"] or
            response["source_head"] != request["source_head"] or
            response["request_digest"] != digest(request) or
            response["execution"] != "independent-witnessed-state-map-powers" or
            response["effect_authorized"] is not False or
            type(response["state"]) is not int or
            type(response["output"]) is not str or
            response["receipt_digest"] != digest({
                k:v for k,v in response.items() if k != "receipt_digest"
            })):
            raise GroundLanguageRefused("unqualified native worker receipt")
        return response
    except (QualificationRefused, OSError, ValueError, KeyError, TypeError) as exc:
        raise GroundLanguageRefused("bounded original subprocess exchange refused") from exc


def _independent_expected(admission: SourceAdmission, initial: int,
                          word: tuple[int,...], repetitions: int) -> str:
    return navigate_observed(admission,expected_head=admission.source_head,
                             initial=initial,word=word,repetitions=repetitions)


def qualify_finite_host(root: Path, host_id: str, *,
                        expected_head: str, allowed_hosts: frozenset[str]
                        ) -> QualifiedFiniteHost:
    """Qualify new finite-word behavior, not reuse SAB-003's affine-only role.

    All probes are independently checked by NCR-004. A locally chosen
    subprocess command is fixed by the supervisor and never source-supplied.
    """
    if (type(allowed_hosts) is not frozenset or host_id not in allowed_hosts or
        any(type(x) is not str for x in allowed_hosts)):
        raise GroundLanguageRefused("host is not receiver-local policy permitted")
    admission = _admission(root,expected_head)
    if not WORKER.is_file():
        raise GroundLanguageRefused("fixed source-independent worker not installed")
    endpoint = SubprocessQualificationEndpoint(
        host_id,(sys.executable,str(WORKER),str(root.resolve()),host_id),
        timeout=10,
    )
    # Probe 3 different initial/action/time contexts, including long time.
    starts = admission.source.initial
    checks = ((starts[0],(0,),1),
              (starts[-1],(len(admission.source.generators)-1,),7),
              (starts[min(1,len(starts)-1)],tuple(range(
                  len(admission.source.generators))),10**80+19))
    proofs = []
    for index,(initial,word,repetitions) in enumerate(checks):
        nonce = sha256(canonical({"kind":"cgr004-probe","index":index,
                                  "host":host_id,"source":expected_head})).hexdigest()
        reply = _exchange(endpoint,_request(host_id,expected_head,initial,
                                             word,repetitions,nonce))
        expected = _independent_expected(admission,initial,word,repetitions)
        if (reply["output"] != expected or
            reply["state"] not in admission.source.states or
            admission.source.outputs[admission.source.states.index(reply["state"])] != expected):
            raise GroundLanguageRefused("worker behavior disagrees with independent NCR-004")
        proofs.append(reply["receipt_digest"])
    profile = {
        "schema":"ifs.cgr004.qualified-finite-host.v1",
        "host":host_id,"source_head":expected_head,
        "language_sha256":admission.language.digest,
        "allowed_hosts":sorted(allowed_hosts),"probes":proofs,
        "authority":False,
    }
    return QualifiedFiniteHost(host_id,endpoint,expected_head,
                               admission.language.digest,allowed_hosts,
                               tuple(proofs),digest(profile))


def execute_qualified_language(root: Path, host: QualifiedFiniteHost, *,
                               expected_head: str,
                               operating_system, pid: int, system, ground,
                               initial: int, word: tuple[int,...],
                               repetitions: int, request_sequence: int = 1) -> dict:
    """Run a finite non-affine processor through the original E-CPU Hypervisor.

    A fixed trusted receiver handler is bound to the native declarative
    OperatorSpec. The workload carries only a qualified source identity,
    operation word and logical coordinate; it cannot supply Python source.
    """
    admission = _admission(root,expected_head)
    if (not isinstance(host,QualifiedFiniteHost) or
        host.source_head != expected_head or
        host.language_digest != admission.language.digest or
        host.host_id not in host.policy_allowed_hosts or
        len(host.probes) != 3):
        raise GroundLanguageRefused("unqualified selected host or mathematical revision")
    if (type(initial) is not int or initial not in admission.source.initial or
        type(word) is not tuple or not 1 <= len(word) <= 256 or
        any(type(i) is not int or not 0 <= i < len(admission.source.generators)
            for i in word) or
        type(repetitions) is not int or not 0 <= repetitions or
        repetitions.bit_length() > 4096 or
        type(request_sequence) is not int or not 1 <= request_sequence <= 1000000):
        raise GroundLanguageRefused("invalid admitted mathematical request")
    expected = _independent_expected(admission,initial,word,repetitions)
    input_value = {
        "source_head":expected_head, "language_digest":admission.language.digest,
        "initial":initial, "word":list(word), "repetitions":str(repetitions),
        "host":host.host_id,
    }
    workload = VirtualLayerWorkload(
        "cgr004-"+digest({"input":input_value,"sequence":request_sequence})[:24],
        system,ground,{"goal":{"source_head":expected_head,
                    "language_digest":admission.language.digest,
                    "request_sequence":request_sequence}},
        (VirtualOperatorRef(OPERATOR,1,"cpu"),),
        input_value, VirtualBudget(1000000,32768,1000),request_sequence,
        ("cgr004-native",),1,
    )
    spec = OperatorSpec(
        OPERATOR,1,"NCR-004 verified finite observer-word interpreter",
        "object","object",("cpu",),
        required_rights=frozenset({"compute"}),base_energy=1,
        energy_per_byte=1,max_input_bytes=8192,max_output_bytes=8192,
        deterministic=True,effect_mode="pure",
    )

    def handler(argument, observed_workload):
        if (observed_workload.digest != workload.digest or
            canonical(dict(argument)) != canonical(input_value)):
            raise GroundLanguageRefused("foreign operator workload")
        nonce = sha256(canonical({"kind":"cgr004-execute",
                                  "workload":workload.digest,
                                  "host":host.host_id})).hexdigest()
        reply = _exchange(host.endpoint,
                          _request(host.host_id,expected_head,initial,
                                   word,repetitions,nonce))
        if (reply["output"] != expected or
            reply["state"] not in admission.source.states or
            admission.source.outputs[
                admission.source.states.index(reply["state"])] != expected):
            raise GroundLanguageRefused("native process differs from independent Ground oracle")
        return {
            "output": reply["output"],"state":reply["state"],
            "source_head":expected_head,
            "ncr_language_sha256":admission.language.digest,
            "host":host.host_id,
            "qualification_digest":host.qualification_digest,
            "native_receipt_digest":reply["receipt_digest"],
            "effect_authorized":False,
        }

    registry = OperatorRegistry()
    registry.register(spec,handler)
    runtime = VirtualLayerRuntime(
        registry,"cgr004-native",frozenset({"cpu"}))
    outcome = runtime.execute_operator(
        operating_system,pid,"cgr004-observer",
        "cgr004.execute",request_sequence,request_sequence,workload,OPERATOR,
    )
    if (not outcome.executed or outcome.action.value != "allow" or
        outcome.effect is None):
        raise GroundLanguageRefused("original Hypervisor did not admit the finite operator")
    effect = dict(outcome.effect)
    result = effect.get("result")
    if (type(result) is not dict or
        result.get("output") != expected or
        result.get("source_head") != expected_head or
        result.get("ncr_language_sha256") != admission.language.digest or
        result.get("host") != host.host_id or
        result.get("effect_authorized") is not False):
        raise GroundLanguageRefused("native Hypervisor result differs from qualified Ground")
    return {
        "source_head":expected_head,
        "language_sha256":admission.language.digest,
        "host":host.host_id,
        "request_sequence":request_sequence,
        "value":expected,
        "receiver_effect_digest":digest(effect),
        "hypervisor_effect":effect,
        "physical_effect_authorized":False,
    }
