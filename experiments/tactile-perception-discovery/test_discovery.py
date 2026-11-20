"""TPP-002 tests: real subprocess probes, held-out predictions and refusals."""
from fractions import Fraction as Q
from hashlib import sha256
import json
import os
import unittest

from discovery import (Observer, Plant, Law, Unavailable, canonical, challenge,
                       identify, transfer, refine, experiment, measure, DRIVE, IDLE)

class CrossMediumDiscoveryTests(unittest.TestCase):
    def test_observation_discovers_composite_not_hidden_coefficients(self):
        model, receipts = identify("electrical")
        self.assertEqual((model.origin,model.A,model.B,model.rho), (Q(3),Q(7),Q(7,2),Q(1,2)))
        self.assertEqual(len(receipts),4)
        self.assertEqual(receipts[-1]["index"],3)

    def test_actual_subprocess_and_canonical_wire_encodings(self):
        for encoding in ("text","json"):
            with Observer("electrical",encoding) as sensor:
                self.assertNotEqual(sensor.process.pid,os.getpid())
                self.assertEqual(sensor.read(),Q(3))
                self.assertEqual(sensor.step(DRIVE),Q(13,2))
                self.assertEqual(sensor.receipts[1]["prev"],sensor.receipts[0]["digest"])
                for record in sensor.receipts:
                    self.assertEqual(record["digest"],
                        sha256(canonical({k:v for k,v in record.items() if k != "digest"})).hexdigest())

    def test_cross_medium_transfer_withheld_actions(self):
        source,_ = identify("electrical")
        with Observer("hydraulic","json") as sensor:
            first = sensor.read()
            second = sensor.step(DRIVE)
            self.assertEqual(len(sensor.receipts),2)
        transferred = transfer(source,first,second)
        self.assertEqual(transferred.ratio,source.ratio)
        self.assertEqual(transferred.rho,source.rho)
        self.assertNotEqual(transferred.A,source.A)
        self.assertTrue(challenge(transferred,"hydraulic")["match"])

    def test_same_initial_output_does_not_imply_same_future(self):
        source,_ = identify("electrical")
        with Observer("slow") as host:
            y0,y1=host.read(),host.step(DRIVE)
        wrong=transfer(source,y0,y1)
        result=challenge(wrong,"slow")
        self.assertFalse(result["match"])
        self.assertEqual(result["first_failure"],2)
        self.assertEqual(result["predicted"][:2],result["observed"][:2])

    def test_probing_revises_instead_of_discarding_counterexample(self):
        source,_=identify("electrical")
        revised,evidence=refine(source,"slow")
        self.assertEqual(evidence["additional_observations"],2)
        self.assertTrue(evidence["contradiction"])
        self.assertEqual(revised.rho,Q(3,4))
        self.assertTrue(challenge(revised,"slow")["match"])

    def test_non_linear_outside_class_is_falsified(self):
        fitted,_=identify("nonlinear")
        result=challenge(fitted,"nonlinear")
        self.assertFalse(result["match"])
        self.assertEqual(result["first_failure"],0)

    def test_memoryless_decay_is_unknown_not_zero(self):
        model,_=identify("memoryless")
        self.assertEqual(model.B,Q(0))
        self.assertIsNone(model.rho)
        self.assertTrue(challenge(model,"memoryless")["match"])

    def test_hidden_coordinate_alias_not_asserted_internal_identity(self):
        a,_=identify("electrical")
        b,_=identify("aliased")
        self.assertEqual(a,b)
        sequence=(DRIVE,IDLE,IDLE,("drive",Q(1,3)),DRIVE,IDLE)
        self.assertEqual(measure("electrical",sequence)[1],measure("aliased",sequence)[1])

    def test_refused_observation_not_interpreted_as_zero(self):
        with self.assertRaises(Unavailable):
            identify("electrical",denied=True)
        with Observer("electrical",denied=True) as host:
            with self.assertRaises(Unavailable):
                host.read()
            self.assertEqual(host.receipts[0]["status"],"refused")
            self.assertIsNone(host.receipts[0]["raw"])

    def test_no_transfer_without_identifiable_source(self):
        with self.assertRaises(Unavailable):
            transfer(Law(Q(0),Q(0),Q(0),None),Q(1),Q(2))
        source,_=identify("electrical")
        with self.assertRaises(ValueError):
            transfer(source,Q(1),Q(2),Q(0))

    def test_wire_accepts_only_admitted_canonical_actions(self):
        fixture=Plant("electrical")
        for bytestring in (b"drive:02/3",b"drive:2/1",b"idle:1/2"):
            with self.subTest(bytestring=bytestring),self.assertRaises(ValueError):
                fixture.exchange({"op":"step","encoding":"text","wire_hex":bytestring.hex()})

    def test_hash_chain_does_not_prove_physical_source(self):
        _,receipts=identify("electrical")
        forged=json.loads(json.dumps(receipts))
        forged[1]["raw"]="99/1"
        for i,record in enumerate(forged):
            if i:
                record["prev"]=forged[i-1]["digest"]
            record["digest"]=sha256(canonical({k:v for k,v in record.items() if k != "digest"})).hexdigest()
        # Forged values can be rehashed; cryptographic origin evidence is absent.
        self.assertNotEqual(receipts[-1]["digest"],forged[-1]["digest"])
        self.assertEqual(forged[-1]["prev"],forged[-2]["digest"])

    def test_experiment_records_expected_counterexamples(self):
        result=experiment()
        self.assertEqual(result["source_training_reads"],4)
        self.assertEqual(result["target_training_reads"],2)
        self.assertTrue(result["target_heldout"]["match"])
        self.assertFalse(result["different_decay_heldout"]["match"])
        self.assertEqual(result["different_decay_heldout"]["first_failure"],2)
        self.assertFalse(result["out_of_class_heldout"]["match"])
        self.assertEqual(result["out_of_class_heldout"]["first_failure"],0)
        self.assertTrue(result["corrected_heldout"]["match"])
        self.assertTrue(result["memoryless_rho_unidentified"])
        self.assertTrue(result["hidden_alias_same_observation_law"])

if __name__ == "__main__":
    unittest.main()
