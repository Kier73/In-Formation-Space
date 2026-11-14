"""GCI-002 runtime-free adversarial provenance, semantic, and witness tests."""
from __future__ import annotations

import copy
import unittest

import ground_contract as c


def fixture():
    signed, trust = c.cag.issue()
    statement = c.cag.verify_intent(signed, trust)
    source = c.seal({
        "schema": c.PROBE_SCHEMA,
        "source_digest": c.cag.digest(statement),
        "ecpu_revision": c.ECPU_REVISION,
        "method": "mailcpu.law_certifier.lcg_navigate",
        "observation_kind": c.EVIDENCE_SCOPE,
        "observations": c.source_rows(statement),
        "local_elapsed_ns": 0,
    })
    context = c.cag.digest(statement)
    rows = source["observations"]
    recs = []
    finals = []
    for row in rows:
        t = row["coordinate"]
        sr, target = f"r{row['state']}", f"r{row['next_state']}"
        evidence_id = f"gci002-evidence-{t}"
        recs.append({
            "evidence_id": evidence_id,
            "encounter_id": f"gci002-encounter-{t}",
            "message_id": f"gci002-derived-message-{t}",
            "channel_id": "gci002-calculated-orbit",
            "protocol_id": "gci002-derived-evidence.v1",
            "transport_id": "github-artifact-identifier-not-delivery-proof",
            "frame_id": f"gci002-derived-frame-{t}",
            "transport_sequence": t + 1,
            "source": c.SOURCE, "ground_id": c.GROUND_ID,
            "context_digest": context,
            "source_state": sr, "action": c.ACTION,
            "status": "known", "outcomes": [{"target": target,
                                              "output": [row["next_state"]]}],
            "payload_digest": c.cag.digest(row), "correlation_id": None,
            "source_model_fingerprint": context,
        })
        finals.append({
            "source_state": sr, "action": c.ACTION, "status": "AUTHORIZED",
            "decision_digest": "1"*64, "evidence_ids": [evidence_id],
        })
    policy = {
        "ground_id":c.GROUND_ID, "context_digest":context,
        "allowed_sources":[c.SOURCE], "quorum":1, "strict":True,
    }
    ground_fp, orbit_fp, cert_fp = ("a"*64, "b"*64, "c"*64)
    cert = {
        "format":"VGI-AffineOrbitCertificate-1",
        "claim":"the affine map generates this exact closed fixed-policy OrbitIndex",
        "orbit_fingerprint":orbit_fp, "ground_fingerprint":ground_fp,
        "policy_fingerprint":"d"*64, "clock_id":c.CLOCK,
        "start_time":{"clock_id":c.CLOCK,"tick":0,
                      "basis":"logical_transition_coordinate"},
        "start_state":"r7", "cycle_start_index":0, "cycle_period":8,
        "transform": c.expected_affine_map(), "transform_fingerprint":"e"*64,
        "state_vectors":[{"state":f"r{x}","vector":[x]} for x in range(8)],
        "verified_edges":c.expected_cert_rows(source),
    }
    rec = {
        "schema":"vgi.ground-reconstruction-certificate.v1",
        "scope":"finite_action_sequence_replay",
        "compiler_id":"vgi.transition-compiler", "compiler_version":1,
        "ground_fingerprint":ground_fp, "context_digest":context,
        "action_sequences":[[c.ACTION]*n for n in (1,2,8,16)],
        "witness_count":4, "max_horizon":16, "witness_digest":"f"*64,
    }
    vgi = c.seal({
        "schema":c.VGI_SCHEMA, "source_digest":context,
        "orbit_source_report_digest":source["report_digest"],
        "vgi_revision":c.VGI_REVISION,
        "observer_source":c.SOURCE, "observation_kind":c.EVIDENCE_SCOPE,
        "evidence_policy":policy,"evidence_records":recs,
        "finalizations":finals,
        "ground_fingerprint":ground_fp, "orbit_fingerprint":orbit_fp,
        "orbit_certificate":cert, "orbit_certificate_fingerprint":cert_fp,
        "reconstruction_certificate":rec,
        "reconstruction_digest":c.cag.digest(rec),
        "partial_ground_empty_before_finalization":True,
        "missing_edge_blocks_closure":True,
        "reconstruction_replay_verified":True,
        "observations":[{
            "job_id":job["job_id"],"coordinate":job["coordinate"],
            "state_id":f"r{c.cag.state_at(job['coordinate'])%8}",
            "state_mod8":c.cag.state_at(job["coordinate"])%8,
            "projected_mod8":c.cag.observed_at(job["coordinate"])%8,
            "closed_certificate_fingerprint":cert_fp,
        } for job in statement["jobs"]],
        "preserving_parity_map":{
            "observer":"parity","source_modulus":8,"target_modulus":2,
            "transition":{"0":1,"1":0},"congruent":True,
        },
        "noncongruent_witness":c.noncongruent_witness(),
        "boundaries":c.SCOPE,
    })
    return statement, source, vgi


def reseal(report):
    report["report_digest"] = c.cag.digest({k:v for k,v in report.items()
                                           if k!="report_digest"})


class GCI002ContractTests(unittest.TestCase):
    def test_real_source_arithmetic_and_complete_cycle(self):
        statement, source, _ = fixture()
        c.verified_probe(source, statement)
        self.assertEqual([r["state"] for r in source["observations"]],
                         [7,4,5,2,3,0,1,6])

    def test_noncongruent_observer_has_actual_successor_split(self):
        w = c.noncongruent_witness()
        self.assertEqual(w["observed_a"], w["observed_b"])
        self.assertNotEqual(w["observed_next_a"], w["observed_next_b"])

    def test_wrong_source_transition_even_if_report_rehashed(self):
        statement, source, _ = fixture()
        source["observations"][3]["next_state"] ^= 1
        reseal(source)
        with self.assertRaisesRegex(c.ContinuityRefusal, "transition"):
            c.verified_probe(source, statement)

    def test_deleted_edge_refused(self):
        statement, source, _ = fixture()
        source["observations"].pop()
        reseal(source)
        with self.assertRaises(c.ContinuityRefusal):
            c.verified_probe(source, statement)

    def test_observer_witness_tamper(self):
        statement, source, vgi = fixture()
        vgi["noncongruent_witness"]["congruent"] = True
        reseal(vgi)
        with self.assertRaises(c.ContinuityRefusal):
            c.verify_vgi(vgi, source, statement)

    def test_forged_non_finalized_ground(self):
        statement, source, vgi = fixture()
        vgi["partial_ground_empty_before_finalization"] = False
        reseal(vgi)
        with self.assertRaises(c.ContinuityRefusal):
            c.verify_vgi(vgi, source, statement)

    def test_wrong_closed_edge(self):
        statement, source, vgi = fixture()
        vgi["orbit_certificate"]["verified_edges"][0]["target_state"] = "r0"
        reseal(vgi)
        with self.assertRaises(c.ContinuityRefusal):
            c.verify_vgi(vgi, source, statement)

    def test_wrong_ground_encoding(self):
        statement, source, vgi = fixture()
        vgi["orbit_certificate"]["state_vectors"][0]["vector"] = [7]
        reseal(vgi)
        with self.assertRaises(c.ContinuityRefusal):
            c.verify_vgi(vgi, source, statement)

    def test_wrong_context(self):
        statement, source, vgi = fixture()
        vgi["evidence_policy"]["context_digest"] = "0"*64
        reseal(vgi)
        with self.assertRaises(c.ContinuityRefusal):
            c.verify_vgi(vgi, source, statement)

    def test_missing_finalization(self):
        statement, source, vgi = fixture()
        vgi["finalizations"].pop()
        reseal(vgi)
        with self.assertRaises(c.ContinuityRefusal):
            c.verify_vgi(vgi, source, statement)

    def test_false_reconstruction_claim(self):
        statement, source, vgi = fixture()
        vgi["reconstruction_certificate"]["max_horizon"] = 4
        vgi["reconstruction_digest"] = c.cag.digest(vgi["reconstruction_certificate"])
        reseal(vgi)
        with self.assertRaises(c.ContinuityRefusal):
            c.verify_vgi(vgi, source, statement)

    def test_false_full_result_from_quotient(self):
        statement, source, vgi = fixture()
        vgi["observations"][0]["projected_mod8"] = 32
        reseal(vgi)
        with self.assertRaises(c.ContinuityRefusal):
            c.verify_vgi(vgi, source, statement)

    def test_reordered_source_report_refused(self):
        statement, source, _ = fixture()
        source["observations"].reverse()
        reseal(source)
        with self.assertRaises(c.ContinuityRefusal):
            c.verified_probe(source, statement)


if __name__ == "__main__":
    unittest.main()
