"""Native reuse experiment: VGI evidence admission -> E-CPU intention sufficiency.

This module does not create a new vote, signature, trust root, transition
authority, or law verifier. Its input is native VGI policy-finalized evidence.
E-CPU IOS-001 chooses the minimum sufficient *hypothesis-identifying* feature.

The final realization is conditional on an explicit, independently established
static-source-coverage premise. Neither native VGI finite finalization nor an
E-CPU receipt digest proves physical transition stationarity.

Pinned dependency installation is in the IWI native-reuse GitHub workflow.
"""
from __future__ import annotations

import hashlib
from typing import Any

from vgi.evidence import TransitionEvidenceLedger
from mailcpu.intention_sufficiency import (
    FiniteGround, FiniteState, MeasurementCapability, plan_sufficiency,
    verify_sufficiency_plan, resolve_sufficiency, verify_sufficiency_resolution,
)

GROUND_ID = "iwi.native-vgi-evidence"
SOURCE_STATE, ACTION = "s1", "a0"
STATES = tuple(f"s{i}" for i in range(7))
ACTIONS = tuple(f"a{i}" for i in range(5))
OUTPUT_CHANNELS = ("observed",)
PUBLIC = "not-yet-identified"
FEATURE = "persistent-branch"
AUTHORITY = hashlib.sha256(b"IWI/native-source-intention-authority-1").hexdigest()


class ReuseRefused(ValueError):
    """Native evidence cannot justify this particular semantic handoff."""


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def project_finalized_native_transition(
    ledger: TransitionEvidenceLedger, *,
    expected_ground_id: str,
    expected_context_digest: str,
) -> dict[str, Any]:
    """Reconstruct with VGI itself. Return a *sample*, not a universal law."""
    if not isinstance(ledger, TransitionEvidenceLedger):
        raise ReuseRefused("expected native VGI evidence ledger")
    # Check the canonical serialized ledger using VGI's original validator.
    verified = TransitionEvidenceLedger.from_json(ledger.to_json())
    if verified.policy.ground_id != expected_ground_id or (
        verified.policy.context_digest != expected_context_digest
    ):
        raise ReuseRefused("Ground or context changed")
    # A strict two-source declaration is a model policy, not external actor auth.
    if not verified.policy.strict or verified.policy.quorum < 2:
        raise ReuseRefused("strict multi-observer finalization required")
    if verified.decision(SOURCE_STATE, ACTION).status != "AUTHORIZED":
        raise ReuseRefused("no explicitly finalized authorized transition")
    ground = verified.build_ground(
        states=STATES, actions=ACTIONS,
        initial_state=SOURCE_STATE, channels=OUTPUT_CHANNELS,
    )
    if ground.status(SOURCE_STATE, ACTION) != "known":
        raise ReuseRefused("reconstructed Ground still has unresolved transition")
    step = ground.step(SOURCE_STATE, ACTION)
    if step.target not in ("s2", "s3") or step.output != (0,):
        raise ReuseRefused("observed transition outside declared hypothesis class")
    decision = verified.decision(SOURCE_STATE, ACTION)
    if len(decision.agreeing_sources) < 2 or len(step.evidence) < 2:
        raise ReuseRefused("missing reported source support")
    return {
        "status": "VGI_FINALIZED_SAMPLE_ONLY",
        "source_state": SOURCE_STATE,
        "action": ACTION,
        "target": step.target,
        "observed_output": list(step.output),
        "candidate_branch": int(step.target[1:]),
        "context_digest": verified.policy.context_digest,
        "ground_id": verified.policy.ground_id,
        "evidence_ledger_digest": verified.fingerprint,
        "decision_digest": decision.digest,
        "evidence_ids": list(step.evidence),
        "ground_complete": ground.complete,
        "unknown_pair_count": len(ground.unknown_pairs),
        "universal_law_proven": False,
        "source_authenticated_by_this_adapter": False,
    }


def prepare_native_intention(context_digest: str) -> tuple[FiniteGround, tuple[MeasurementCapability, ...], dict]:
    """Reuse E-CPU IOS-001; no duplicate cost/observer subset optimizer."""
    if not isinstance(context_digest, str) or len(context_digest) != 64:
        raise ReuseRefused("expected caller-pinned Ground context SHA-256")
    rows = (
        FiniteState.create("law-2", PUBLIC, "finish-left", {FEATURE: 2}),
        FiniteState.create("law-3", PUBLIC, "finish-right", {FEATURE: 3}),
    )
    model = FiniteGround(
        _digest("IWI-005/synthetic-two-law-Ground"),
        _digest("IWI/public-unknown-law"),
        _digest("IWI/intention-choose-finish-action"),
        context_digest, rows,
    )
    offers = (MeasurementCapability(FEATURE, _digest("IWI/native-branch-projection"),
                                     "vgi-native-conditional-observer", 2),)
    plan = plan_sufficiency(model, PUBLIC, offers, AUTHORITY)
    verify_sufficiency_plan(plan, model, PUBLIC, offers, AUTHORITY)
    if plan["status"] != "MEASURE" or plan["selected_features"] != [FEATURE] or (
        plan["declared_cost_units"] != 2
    ):
        raise ReuseRefused("native E-CPU sufficiency plan changed")
    return model, offers, plan


def conditionally_resolve_from_vgi(
    ledger: TransitionEvidenceLedger, *,
    expected_ground_id: str,
    expected_context_digest: str,
    controlled_static_law_coverage: bool,
) -> dict[str, Any]:
    """Use native VGI and E-CPU without claiming their reports prove stationarity."""
    if controlled_static_law_coverage is not True:
        raise ReuseRefused("a finalized sample cannot assert persistent-law coverage")
    sample = project_finalized_native_transition(
        ledger, expected_ground_id=expected_ground_id,
        expected_context_digest=expected_context_digest,
    )
    model, offers, plan = prepare_native_intention(expected_context_digest)
    readings = {FEATURE: sample["candidate_branch"]}
    # IOS itself explicitly states that a digest alone does not authenticate
    # the source; we verified VGI finalization separately, and still retain
    # the independently unproved static-law-coverage assumption.
    resolution = resolve_sufficiency(
        model, PUBLIC, offers, AUTHORITY, plan, readings,
        sample["evidence_ledger_digest"],
    )
    verify_sufficiency_resolution(
        resolution, model, PUBLIC, offers, AUTHORITY,
        plan, readings, sample["evidence_ledger_digest"],
    )
    return {
        "status": "CONDITIONAL_INTENTION_RESULT",
        "model": model.digest,
        "vgi_sample": sample,
        "ecpu_plan_digest": plan["plan_digest"],
        "ecpu_resolution_digest": resolution["resolution_digest"],
        "ecpu_selected_features": plan["selected_features"],
        "ecpu_symbolic_cost": plan["declared_cost_units"],
        "selected_finishing_action": resolution["result"],
        "source_stability_assumed_not_proven": True,
        "vgi_ground_admitted_by_bridge": False,
        "ecpu_external_effect_authorized": False,
    }
