"""CAG-004: adversarial topology-neutral source and observation checks.

These unit fixtures are synthetic; hosted jobs test actual SHN-001 and E-CPU.
"""
from __future__ import annotations

import copy
import pathlib
import sys
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import contract as c


def fixture():
    signed, trust = c.issue(Ed25519PrivateKey.generate())
    statement = c.verify_intent(signed, trust)
    internal, external = [], []
    for job in statement["jobs"]:
        value = c.observed_at(job["coordinate"])
        receipts, total_bytes = c.internal_receipts(job)
        semantic = c.semantic_result(job, value, statement)
        for ports in (1, 2):
            internal.append({
                "schema": "mailcpu.self-hosted-port-network.v1",
                "job_id": job["job_id"],
                "requested_coordinate": job["coordinate"],
                "observed_value": value,
                "physical_boundary_ports": ports,
                "logical_observer_hosts": 3,
                "internal_virtual_interfaces": 6,
                "internal_link_count": 3,
                "interpreter_quanta": 3,
                "internal_payload_bytes": total_bytes,
                "external_payload_bytes": 0,
                "materialized_orbit_intermediate_states": 0,
                "navigation_algorithm": "mailcpu.law_certifier.lcg_navigate",
                "observer_receipts": receipts,
                "journal_verified": True,
                "independent_physical_execution_claimed": False,
                "hardware_port_emulation_verified": False,
                "semantic_result_digest": semantic,
                "restored_phases": ["navigator", "projector", "dispatcher", "done"],
                "local_elapsed_ns": 100,
            })
        external.append({
            "job_id": job["job_id"], "coordinate": job["coordinate"],
            "observed_value": value, "semantic_result_digest": semantic,
            "workload_digest": "a" * 64,
            "operator_contract_digest": "b" * 64,
            "hypervisor_allow": True, "hypervisor_replayed": True,
            "hypervisor_denied": True, "handler_invocations": 1,
            "receiver_journal_verified": True, "receiver_local_elapsed_ns": 100,
        })
    inside = c.seal_report({
        "schema": c.INTERNAL_SCHEMA,
        "source_digest": c.digest(statement), "shn_revision": c.SHN_REFERENCE,
        "execution_domain": "one E-CPU interpreter, internal OwnedNetworkFabric",
        "observations": internal,
    })
    outside = c.seal_report({
        "schema": c.EXTERNAL_SCHEMA,
        "source_digest": c.digest(statement), "ecpu_revision": c.ECPU_RECEIVER_REFERENCE,
        "execution_domain": "independent GitHub-hosted E-CPU Hypervisor receiver",
        "external_link_claim": "GitHub Actions artifact transfer, physical byte rate not measured",
        "observations": external,
    })
    return signed, trust, inside, outside


def reseal(doc):
    doc.pop("report_digest", None)
    doc["report_digest"] = c.digest(doc)
    return doc


class TopologyContractTests(unittest.TestCase):
    def test_independent_small_oracle_and_billion_plus_coordinate(self):
        for t in (0, 1, 2, 7, 11, 64, 1024, 2048):
            self.assertEqual(c.observed_at(t), c.iterative_at(t))
        self.assertIsInstance(c.observed_at(10**15 + 137), int)
        with self.assertRaises(c.TopologyError):
            c.observed_at(10**18 + 1)

    def test_signed_ephemeral_intent_round_trip(self):
        signed, trust, internal, external = fixture()
        self.assertEqual(c.verify_intent(signed, trust), c.intent())
        report = c.verify(internal, external, signed, trust)
        self.assertEqual(report["status"], "same_semantics_distinct_topology_accounting")
        self.assertEqual(len(report["results"]), len(c.COORDINATES))
        self.assertEqual(set(report["results"][0]["topologies"]),
                         {"internal-one-port", "internal-two-port", "separate-receiver"})

    def test_signed_statement_change_without_signature_is_denied(self):
        signed, trust, _, _ = fixture()
        signed["statement"]["jobs"][0]["coordinate"] = 19
        with self.assertRaises(c.TopologyError):
            c.verify_intent(signed, trust)

    def test_new_signer_does_not_match_workflow_trust_record(self):
        signed, trust, _, _ = fixture()
        signed["signature_b64"] = c.b64(Ed25519PrivateKey.generate().sign(
            c.canonical(signed["statement"])))
        with self.assertRaisesRegex(c.TopologyError, "signature invalid"):
            c.verify_intent(signed, trust)

    def test_issuer_and_epoch_not_granted_by_signature(self):
        signed, trust, _, _ = fixture()
        for field, invalid in (
            ("issuer_workflow", "other/workflow@refs/heads/dev"),
            ("epoch", 2), ("key_id", "1"*64),
        ):
            with self.subTest(field=field):
                fake = copy.deepcopy(trust)
                fake[field] = invalid
                with self.assertRaises(c.TopologyError):
                    c.verify_intent(signed, fake)

    def test_malformed_trust_key_rejected(self):
        signed, trust, _, _ = fixture()
        trust["public_key_b64"] = c.b64(b"x" * 32)
        with self.assertRaisesRegex(c.TopologyError, "fingerprint"):
            c.verify_intent(signed, trust)

    def test_internal_frame_or_receipt_forgery_is_not_sufficient(self):
        signed, trust, internal, external = fixture()
        internal["observations"][0]["observer_receipts"][0] = "f"*64
        reseal(internal)
        with self.assertRaisesRegex(c.TopologyError, "internal observation"):
            c.verify(internal, external, signed, trust)

    def test_fake_one_port_resource_account_is_rejected(self):
        signed, trust, internal, external = fixture()
        internal["observations"][0]["external_payload_bytes"] = 1000
        reseal(internal)
        with self.assertRaisesRegex(c.TopologyError, "internal observation"):
            c.verify(internal, external, signed, trust)

    def test_fake_more_interpreters_does_not_create_capacity(self):
        signed, trust, internal, external = fixture()
        internal["observations"][0]["interpreter_quanta"] = 2
        internal["observations"][0]["logical_observer_hosts"] = 32
        reseal(internal)
        with self.assertRaises(c.TopologyError):
            c.verify(internal, external, signed, trust)

    def test_checkpoint_phase_omission_rejected(self):
        signed, trust, internal, external = fixture()
        internal["observations"][0]["restored_phases"] = ["navigator", "done"]
        reseal(internal)
        with self.assertRaisesRegex(c.TopologyError, "internal observation"):
            c.verify(internal, external, signed, trust)

    def test_missing_or_duplicated_host_is_refused(self):
        signed, trust, internal, external = fixture()
        internal["observations"][1] = copy.deepcopy(internal["observations"][0])
        reseal(internal)
        with self.assertRaisesRegex(c.TopologyError, "missing or duplicate"):
            c.verify(internal, external, signed, trust)

    def test_remote_permission_claim_cannot_be_replaced_by_value_match(self):
        signed, trust, internal, external = fixture()
        external["observations"][0]["hypervisor_denied"] = False
        reseal(external)
        with self.assertRaisesRegex(c.TopologyError, "authorization claim failed"):
            c.verify(internal, external, signed, trust)

    def test_equal_values_but_divergent_semantic_identity_refused(self):
        signed, trust, internal, external = fixture()
        external["observations"][0]["semantic_result_digest"] = "0"*64
        reseal(external)
        with self.assertRaisesRegex(c.TopologyError, "authorization claim failed"):
            c.verify(internal, external, signed, trust)

    def test_report_digest_recomputed_by_attacker_does_not_escape_checks(self):
        signed, trust, internal, external = fixture()
        external["observations"][3]["observed_value"] += 1
        reseal(external)
        with self.assertRaisesRegex(c.TopologyError, "authorization claim failed"):
            c.verify(internal, external, signed, trust)

    def test_receiver_replay_claim_is_not_optional(self):
        signed, trust, internal, external = fixture()
        external["observations"][0]["handler_invocations"] = 2
        reseal(external)
        with self.assertRaises(c.TopologyError):
            c.verify(internal, external, signed, trust)

    def test_canonical_file_roundtrip_and_reject_indented_doc(self):
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp)/"record.json"
            doc = c.intent()
            c.persist(p, doc)
            self.assertEqual(c.read(p), doc)
            p.write_text(' { "schema": "fake" }\n', encoding="utf-8")
            with self.assertRaisesRegex(c.TopologyError, "noncanonical"):
                c.read(p)

    def test_extra_host_field_denied_even_with_same_digest(self):
        signed, trust, internal, external = fixture()
        internal["observations"][0]["independent_gpu_host"] = True
        reseal(internal)
        with self.assertRaisesRegex(c.TopologyError, "unexpected internal resource"):
            c.verify(internal, external, signed, trust)

    def test_negative_or_boolean_coordinate_does_not_enter_arithmetic(self):
        for bad in (-1, True, 2.5, 10**18+1):
            with self.subTest(bad=bad), self.assertRaises(c.TopologyError):
                c.state_at(bad)


if __name__ == "__main__":
    unittest.main()
