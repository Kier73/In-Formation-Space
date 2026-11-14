"""Adversarial, independent GCI-001 audit tests (no VGI/E-CPU runtime)."""
from __future__ import annotations

import copy
import unittest

import continuity as g


def fixture():
    signed, trust = g.cag.issue()
    statement = g.cag.verify_intent(signed, trust)
    full, coarse = g.expected_maps(statement)
    rows = []
    for job in statement["jobs"]:
        t = job["coordinate"]
        x, y = g.cag.state_at(t), g.cag.observed_at(t)
        rows.append({
            "job_id": job["job_id"], "coordinate": t,
            "state_value": x, "result_value": y,
            "coarse_state_value": x % 8,
            "coarse_result_value": y % 8,
            "semantic_result_digest": g.cag.semantic_result(job, y, statement),
        })
    body = {
        "schema": g.SCHEMA, "source_digest": g.cag.digest(statement),
        "vgi_revision": g.VGI_REFERENCE,
        "execution_method": "vgi.affine.ModularAffineMap.power",
        "full_map": full, "coarse_map": coarse,
        "observer_contexts": copy.deepcopy(g.OBSERVERS),
        "observations": rows,
        "quotient_counterexample": g.expected_counterexample(statement),
        "closed_orbit_certificate_claimed": False,
        "independent_physical_observers_claimed": False,
        "local_elapsed_ns": 0, "boundaries": g.SCOPE,
    }
    return signed, trust, g.seal(body)


def reseal(report):
    report["report_digest"] = g.cag.digest({k: v for k, v in report.items()
                                         if k != "report_digest"})


class ContinuityAuditTests(unittest.TestCase):
    def test_exact_full_and_quotient_views(self):
        signed, trust, report = fixture()
        results = g.verify_vgi(report, signed, trust)
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["full_state"], 7)
        self.assertEqual(results[0]["full_result"], 32)
        self.assertEqual(results[-1]["coordinate"], 10**15 + 137)

    def test_reachable_counterexample_prevents_full_quotient_claim(self):
        signed, trust, report = fixture()
        example = report["quotient_counterexample"]
        self.assertNotEqual(example["state_a"], example["state_b"])
        self.assertEqual(example["coarse_a"], example["coarse_b"])
        self.assertNotEqual(example["result_a"], example["result_b"])
        self.assertFalse(example["coordinate_observed"])
        g.verify_vgi(report, signed, trust)

    def test_forged_result_even_after_rehash(self):
        signed, trust, report = fixture()
        report["observations"][0]["result_value"] += 8
        reseal(report)
        with self.assertRaisesRegex(g.ContinuityError, "observation"):
            g.verify_vgi(report, signed, trust)

    def test_false_semantic_identity_even_if_number_matches(self):
        signed, trust, report = fixture()
        report["observations"][1]["semantic_result_digest"] = "f" * 64
        reseal(report)
        with self.assertRaises(g.ContinuityError):
            g.verify_vgi(report, signed, trust)

    def test_false_ground_and_mathematical_projection_refused(self):
        for field, mutation in [
            ("full_map", lambda r: r["full_map"]["matrix"][1].__setitem__(0, 10)),
            ("coarse_map", lambda r: r["coarse_map"]["offset"].__setitem__(0, 0)),
            ("observer_contexts", lambda r: r["observer_contexts"][2].__setitem__("modulus", 65536)),
        ]:
            with self.subTest(field=field):
                signed, trust, report = fixture()
                mutation(report)
                reseal(report)
                with self.assertRaisesRegex(g.ContinuityError, "Ground representation"):
                    g.verify_vgi(report, signed, trust)

    def test_lossy_observation_cannot_be_promoted(self):
        signed, trust, report = fixture()
        report["quotient_counterexample"]["full_result_identifiable_from_coarse_alone"] = True
        reseal(report)
        with self.assertRaisesRegex(g.ContinuityError, "quotient"):
            g.verify_vgi(report, signed, trust)

    def test_claimed_certificate_without_orbit_is_refused(self):
        signed, trust, report = fixture()
        report["closed_orbit_certificate_claimed"] = True
        reseal(report)
        with self.assertRaisesRegex(g.ContinuityError, "scope"):
            g.verify_vgi(report, signed, trust)

    def test_virtual_host_does_not_claim_physical_independence(self):
        signed, trust, report = fixture()
        report["independent_physical_observers_claimed"] = True
        reseal(report)
        with self.assertRaises(g.ContinuityError):
            g.verify_vgi(report, signed, trust)

    def test_wrong_source_trust_refused(self):
        signed, trust, report = fixture()
        trust["issuer_workflow"] = "Kier73/other/.github/workflows/other.yml@refs/heads/main"
        with self.assertRaises(g.cag.TopologyError):
            g.verify_vgi(report, signed, trust)

    def test_extra_observation_or_duplicate_refused(self):
        signed, trust, report = fixture()
        report["observations"].append(copy.deepcopy(report["observations"][0]))
        reseal(report)
        with self.assertRaises(g.ContinuityError):
            g.verify_vgi(report, signed, trust)

    def test_bool_is_not_integer_coordinate(self):
        signed, trust, report = fixture()
        report["observations"][0]["coordinate"] = False
        reseal(report)
        with self.assertRaisesRegex(g.ContinuityError, "noninteger"):
            g.verify_vgi(report, signed, trust)

    def test_digest_tamper_without_reseal_refused(self):
        signed, trust, report = fixture()
        report["observations"][0]["coarse_result_value"] ^= 1
        with self.assertRaisesRegex(g.ContinuityError, "digest"):
            g.verify_vgi(report, signed, trust)


if __name__ == "__main__":
    unittest.main()
