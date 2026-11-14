"""RE-009 separate-job causal/evidence adapter using *real* E-CPU and RE-008.

No claimed physical source attestation or independent fault domain. Exact
source evidence and observer acknowledgements are CI-enrolled HMAC contracts.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from coverage_reconstruction import CoverageError, sha
from common_mode_counter import (
    CounterError, acknowledge, produce_source, reconstruct, verify_source,
)
from ecpu_coverage_hosts import controller, witness, verify as verify_ecpu

HOST_SCHEMA = "in-formation.response-re009-hosted/0.1"


def source_host(reg: Mapping[str, Any]) -> dict[str, Any]:
    ctrl = controller(reg["challenge"])
    signed = produce_source(reg, controller_digest=ctrl["digest"])
    return {"schema": HOST_SCHEMA, "controller": ctrl, "source": signed,
            "digest": sha({"controller": ctrl, "source": signed, "schema": HOST_SCHEMA})}


def _verify_source_host(doc: Mapping[str, Any], reg: Mapping[str, Any] | None = None) -> None:
    if not isinstance(doc, dict) or set(doc) != {"schema", "controller", "source", "digest"} or doc["schema"] != HOST_SCHEMA:
        raise CounterError("source-host envelope invalid")
    if doc["digest"] != sha({k:v for k,v in doc.items() if k != "digest"}):
        raise CounterError("source-host envelope altered")
    if not isinstance(doc["controller"], dict) or doc["controller"].get("digest") != doc["source"].get("controller_digest"):
        raise CounterError("source counter/controller frame unbound")
    if reg is not None:
        verify_source(doc["source"], reg, controller_digest=doc["controller"]["digest"])


def observer_host(actor: str, source_doc: Mapping[str, Any], reg: Mapping[str, Any]) -> dict[str, Any]:
    _verify_source_host(source_doc)  # no S private signing key required
    host = witness(actor, source_doc["controller"], reg)
    ack = acknowledge(actor, host["log"], source_doc["source"], reg)
    return {"schema": HOST_SCHEMA, "actor": actor, "witness": host, "ack": ack,
            "digest": sha({"schema": HOST_SCHEMA, "actor": actor, "witness": host, "ack": ack})}


def _observer_doc(doc: Mapping[str, Any], actor: str) -> None:
    if not isinstance(doc, dict) or set(doc) != {"schema", "actor", "witness", "ack", "digest"} or doc["schema"] != HOST_SCHEMA or doc["actor"] != actor:
        raise CounterError("observer-host envelope invalid")
    if doc["digest"] != sha({k:v for k,v in doc.items() if k != "digest"}):
        raise CounterError("observer-host envelope altered")


def verify(source_doc: Mapping[str, Any], a_doc: Mapping[str, Any],
           b_doc: Mapping[str, Any], reg: Mapping[str, Any]) -> dict[str, Any]:
    _verify_source_host(source_doc, reg)
    _observer_doc(a_doc, "A")
    _observer_doc(b_doc, "B")
    a, b = a_doc["witness"], b_doc["witness"]
    # RE-008 verifies actual typed E-CPU vector stamps, per-slot binding HMAC,
    # signed observer logs, and delayed delivery's capture-time provenance.
    native = verify_ecpu(source_doc["controller"], a, b, reg)
    result = reconstruct(source_doc["source"], {"A": a["log"], "B": b["log"]},
                         {"A": a_doc["ack"], "B": b_doc["ack"]}, reg,
                         [a["delivery"]])
    if (result["status"] != "source_observer_disagreement" or
        result["source_observer_discrepancy"] != 1 or
        result["observer_blind_declared_epochs"] or
        native["causal_relation"]["A_concurrent_B"] != "concurrent"):
        raise CounterError("hosted synthetic verification predicate not satisfied")
    return {"schema": HOST_SCHEMA, "status": "source_counter_discrepancy_verified",
            "causal_relation": native["causal_relation"],
            "counter_reconstruction": result,
            "cross_host_elapsed": None,
            "physical_event_source_authenticated": False,
            "source_counter_truthfulness_proved": False,
            "physical_common_mode_loss_proved": False,
            "scope": "separate hosted jobs, real E-CPU temporal stamps, CI role keys"}


def cli() -> None:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    args = json.load(sys.stdin)
    if mode == "--source":
        result = source_host(args["registration"])
    elif mode in ("--A", "--B"):
        result = observer_host(mode[-1], args["source"], args["registration"])
    elif mode == "--verifier":
        result = verify(args["source"], args["A"], args["B"], args["registration"])
    else:
        raise SystemExit("usage: --source | --A | --B | --verifier")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    cli()
