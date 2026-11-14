"""Independent receiver pin and Ed25519 negative tests for OE-003."""
import copy
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from costed_navigation import CostedDistinctionNavigator
from witness_realization import (
    PLAN_SCHEMA, RECEIPT_SCHEMA, AUTH_SCHEMA,
    build_plan, digest, sign_claim, verify_plan, verify_realization,
)


def pkbytes(priv):
    return priv.public_key().public_bytes(serialization.Encoding.Raw,
                                          serialization.PublicFormat.Raw)


def model():
    states = ("a", "b", "x", "y", "c", "d")
    outputs = {s: 0 for s in states} | {"c": 1, "d": 2}
    edges = {
        ("a", "expensive"): "c", ("b", "expensive"): "d",
        ("a", "cheap"): "x", ("b", "cheap"): "y",
        ("x", "cheap"): "c", ("y", "cheap"): "d",
    }
    return CostedDistinctionNavigator(
        states, ("expensive", "cheap"), ("read",),
        lambda s, t: outputs[s], lambda s, a: edges.get((s, a), s),
    )


def fixture():
    nav = model()
    plan = build_plan(nav, "a", "b", request_id="synthetic-request-1",
                      source_policy_digest="pinned-cost-profile-digest",
                      action_costs=(10, 2), test_costs=(1,))
    assert plan["selected"]["actions"] == ["cheap", "cheap"]
    receiver_privs = {lane: Ed25519PrivateKey.generate() for lane in ("left", "right")}
    authority_priv = Ed25519PrivateKey.generate()
    policy = "pinned-authority-policy-digest"
    runs = {}
    for lane in ("left", "right"):
        initial = plan["initial_states"][lane]
        current = initial
        trace = []
        for i, action in enumerate(plan["selected"]["actions"]):
            next_state = nav.states[nav._steps[(nav._index[current], nav.actions.index(action))]]
            trace.append({"sequence": i, "action": action, "before": current,
                          "after": next_state})
            current = next_state
        value = nav._outputs[nav._index[current]][0]
        body = {
            "schema": RECEIPT_SCHEMA, "request_id": plan["request_id"],
            "plan_digest": plan["plan_digest"], "lane": lane,
            "receiver_key_id": f"demo-receiver-{lane}",
            "observation_id": f"synthetic-encounter-{lane}",
            "initial_state": initial, "steps": trace,
            "test": plan["selected"]["test"], "state": current, "value": value,
        }
        receiver = sign_claim(body, receiver_privs[lane])
        auth = sign_claim({
            "schema": AUTH_SCHEMA, "request_id": plan["request_id"],
            "plan_digest": plan["plan_digest"], "lane": lane,
            "decision": "AUTHORIZED", "receiver_key_id": body["receiver_key_id"],
            "receiver_envelope_digest": digest(receiver), "policy_digest": policy,
        }, authority_priv)
        attempt = f"{plan['request_id']}:{lane}"
        intent = {
            "candidate_name": f"witness-terminal:{lane}",
            "query": "Check the selected terminal witness test",
            "hypothesis_set_digest": plan["model_digest"],
            "estimated_cost": float(plan["selected"]["estimated_total_ns"]),
            "plan_ref": f"urn:sha256:{plan['plan_digest']}",
            "authority_required": True, "application_required": False,
            "sender_ack_required": False,
        }
        def event(stage, actor, evidence_ref, details):
            return {"stage": stage, "actor": actor, "clock_value": None,
                    "clock_domain": None, "evidence_ref": evidence_ref,
                    "details": details}
        events = [
            event("planned", "planner", intent["plan_ref"], {
                "attempt_id": attempt, "candidate_name": intent["candidate_name"],
                "query": intent["query"],
                "hypothesis_set_digest": intent["hypothesis_set_digest"],
                "estimated_cost": intent["estimated_cost"],
                "plan_ref": intent["plan_ref"],
            }),
            event("dispatched", "synthetic-client", f"dispatch://{lane}",
                  {"plan_digest": plan["plan_digest"], "lane": lane}),
            event("admitted", "synthetic-receiver", f"admit://{lane}",
                  {"plan_digest": plan["plan_digest"], "lane": lane}),
            event("returned", "synthetic-receiver", f"receiver-claim://{lane}", {
                "plan_digest": plan["plan_digest"], "lane": lane,
                "encounter_id": body["observation_id"],
                "payload_digest": digest(receiver),
                "canonicalization": "canonical-json-v1",
            }),
            event("evidence_authorized", "test-only-authority", "urn:sha256:" + digest(auth), {
                "decision_status": "AUTHORIZED", "policy_digest": policy,
                "decision_digest": digest(auth["payload"]), "quorum": 1,
                "strict": True, "observed_sources": [body["receiver_key_id"]],
                "dissenting_sources": [], "missing_sources": [],
                "representative_source": body["receiver_key_id"],
            }),
            event("interpreted", "synthetic-interpreter", f"interpret://{lane}", {
                "method": "exact-witness-terminal-v1", "plan_digest": plan["plan_digest"],
                "lane": lane, "test": body["test"], "value": body["value"],
            }),
        ]
        runs[lane] = {"receiver": receiver, "authority": auth, "path": {
            "attempt_id": attempt, "intent": intent, "status": "interpreted",
            "terminal": False, "events": events,
        }}
    params = {
        "expected_model_digest": plan["model_digest"],
        "expected_source_policy_digest": plan["source_policy_digest"],
        "expected_request_id": plan["request_id"],
        "expected_authority_policy_digest": policy,
        "receiver_keys": {lane: pkbytes(receiver_privs[lane]) for lane in receiver_privs},
        "authority_key": pkbytes(authority_priv),
    }
    return plan, runs, params, receiver_privs, authority_priv


class SignedWitnessTests(unittest.TestCase):
    def test_signed_synthetic_execution_claim_is_confirmed(self):
        plan, runs, params, _, _ = fixture()
        report = verify_realization(plan, runs, **params)
        self.assertEqual(report["status"], "signed-witness-confirmed-within-trusted-claim-model")
        self.assertEqual(report["observed"], plan["selected"]["expected"])
        self.assertEqual(report["ground_effect"], "none")
        self.assertEqual(report["authority_effect"], "none")

    def test_model_or_cost_policy_pins_cannot_be_rewritten_by_producer(self):
        plan, runs, params, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, "model not receiver-pinned"):
            verify_realization(plan, runs, **{**params, "expected_model_digest": "wrong"})
        with self.assertRaisesRegex(ValueError, "cost policy not receiver-pinned"):
            verify_realization(plan, runs, **{**params, "expected_source_policy_digest": "wrong"})
        tampered = copy.deepcopy(plan)
        tampered["selected"]["estimated_total_ns"] += 1
        with self.assertRaisesRegex(ValueError, "plan digest mismatch"):
            verify_plan(tampered, expected_model_digest=params["expected_model_digest"],
                        expected_source_policy_digest=params["expected_source_policy_digest"])

    def test_request_replay_under_a_different_pin_is_rejected(self):
        plan, runs, params, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, "request was not independently pinned"):
            verify_realization(plan, runs, **{**params, "expected_request_id": "different"})

    def test_receiver_signature_tampering_rejected(self):
        plan, runs, params, _, _ = fixture()
        damaged = copy.deepcopy(runs)
        damaged["left"]["receiver"]["payload"]["value"] = 42
        with self.assertRaisesRegex(ValueError, "Ed25519"):
            verify_realization(plan, damaged, **params)

    def test_authority_signature_cannot_be_replaced_by_receiver_signature(self):
        plan, runs, params, receiver_privs, _ = fixture()
        damaged = copy.deepcopy(runs)
        damaged["left"]["authority"] = sign_claim(
            damaged["left"]["authority"]["payload"], receiver_privs["left"]
        )
        with self.assertRaisesRegex(ValueError, "Ed25519"):
            verify_realization(plan, damaged, **params)

    def test_authority_does_not_grant_access_to_unrelated_receipt(self):
        plan, runs, params, receiver_privs, _ = fixture()
        damaged = copy.deepcopy(runs)
        damaged["left"]["receiver"] = sign_claim(
            {**damaged["left"]["receiver"]["payload"], "value": 42}, receiver_privs["left"]
        )
        with self.assertRaisesRegex(ValueError, "authority signature does not authorize exact receiver claim"):
            verify_realization(plan, damaged, **params)

    def test_authority_policy_is_a_receiver_owned_external_pin(self):
        plan, runs, params, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, "authority signature does not authorize"):
            verify_realization(plan, runs, **{**params, "expected_authority_policy_digest": "wrong"})

    def test_missing_gate_or_wrong_interpretation_is_refused(self):
        plan, runs, params, _, _ = fixture()
        for index in (1, 2, 3, 4):
            damaged = copy.deepcopy(runs)
            damaged["left"]["path"]["events"].pop(index)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "lifecycle"):
                verify_realization(plan, damaged, **params)
        damaged = copy.deepcopy(runs)
        damaged["right"]["path"]["events"][-1]["details"]["value"] = 999
        with self.assertRaisesRegex(ValueError, "interpreted output"):
            verify_realization(plan, damaged, **params)

    def test_planned_cost_cannot_drift_from_signed_witness(self):
        plan, runs, params, _, _ = fixture()
        modified = copy.deepcopy(runs)
        modified["left"]["path"]["intent"]["estimated_cost"] = 1.0
        modified["left"]["path"]["events"][0]["details"]["estimated_cost"] = 1.0
        with self.assertRaisesRegex(ValueError, "cost differs"):
            verify_realization(plan, modified, **params)

    def test_missing_action_or_discontinuous_trace_is_refused(self):
        plan, runs, params, receiver_privs, _ = fixture()
        damaged = copy.deepcopy(runs)
        payload = damaged["left"]["receiver"]["payload"]
        payload["steps"].pop(0)
        damaged["left"]["receiver"] = sign_claim(payload, receiver_privs["left"])
        with self.assertRaisesRegex(ValueError, "missing or surplus actions"):
            verify_realization(plan, damaged, **params)

    def test_valid_signatures_can_report_model_mismatch_without_false_success(self):
        plan, runs, params, receiver_privs, authority_priv = fixture()
        damaged = copy.deepcopy(runs)
        payload = damaged["left"]["receiver"]["payload"]
        payload["steps"][-1]["after"] = "x"
        payload["state"] = "x"
        payload["value"] = 0
        damaged["left"]["receiver"] = sign_claim(payload, receiver_privs["left"])
        auth_payload = damaged["left"]["authority"]["payload"]
        auth_payload["receiver_envelope_digest"] = digest(damaged["left"]["receiver"])
        damaged["left"]["authority"] = sign_claim(auth_payload, authority_priv)
        damaged["left"]["path"]["events"][3]["details"]["payload_digest"] = digest(damaged["left"]["receiver"])
        damaged["left"]["path"]["events"][4]["details"]["decision_digest"] = digest(auth_payload)
        damaged["left"]["path"]["events"][4]["evidence_ref"] = "urn:sha256:" + digest(damaged["left"]["authority"])
        damaged["left"]["path"]["events"][5]["details"]["value"] = 0
        report = verify_realization(plan, damaged, **params)
        self.assertEqual(report["status"], "signed-model-mismatch")


    def test_serialized_lifecycle_replays_through_real_observation_path(self):
        """When checked out in the real repo, reuse the existing event gate."""
        import sys
        from pathlib import Path
        sibling = Path(__file__).resolve().parents[1] / "observation-path"
        if not (sibling / "observation_path.py").is_file():
            self.skipTest("standalone source checkout lacks the observation-path sibling")
        sys.path.insert(0, str(sibling))
        from observation_path import ObservationIntent, ObservationPath
        _, runs, _, _, _ = fixture()
        for lane in ("left", "right"):
            original = runs[lane]["path"]
            path = ObservationPath(ObservationIntent(
                attempt_id=original["attempt_id"], **original["intent"]
            ))
            for item in original["events"][1:]:
                path.append(item["stage"], item["actor"],
                            clock_value=item["clock_value"],
                            clock_domain=item["clock_domain"],
                            evidence_ref=item["evidence_ref"],
                            details=item["details"])
            self.assertEqual(path.to_dict(), original)


if __name__ == "__main__":
    unittest.main()
