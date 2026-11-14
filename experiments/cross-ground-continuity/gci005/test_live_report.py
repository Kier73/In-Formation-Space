"""Revalidate real signed TLS transcripts with post-hash adversarial edits."""
from __future__ import annotations
import argparse
import copy
import unittest
from pathlib import Path
from cryptography.exceptions import InvalidSignature
import honesty_contract as h

class GCI005ActualReceiptTests(unittest.TestCase):
    directory: Path

    @classmethod
    def setUpClass(cls):
        cls.binding,cls.public,cls.plan=h.get_binding(cls.directory)
        cls.original=h.cag.read(cls.directory/"gci005-quorum.json")

    def verify(self,report):
        return h.verify_record(report,self.binding,self.public,self.plan)

    def altered(self,mutation):
        report=copy.deepcopy(self.original)
        mutation(report)
        report["report_digest"]=h.c.jdigest({k:v for k,v in report.items()
                                             if k!="report_digest"})
        return report

    def test_unchanged_real_signed_observations_admitted(self):
        summary=self.verify(self.original)
        self.assertEqual([r["verdict"] for r in summary["rounds"]],
                         ["ADMITTED_AGREEMENT","REFUSED_DISAGREEMENT"])

    def test_signed_false_value_cannot_be_rehashed_into_truth(self):
        r=self.altered(lambda report:
            report["rounds"][1]["receipts"][1]["payload"].__setitem__(
                "value",1-report["rounds"][1]["receipts"][1]["payload"]["value"]))
        with self.assertRaises((ValueError,InvalidSignature,h.gci3.SufficiencyRefused)):
            self.verify(r)

    def test_swapped_server_certificate_refused(self):
        r=self.altered(lambda report:
            report["rounds"][0]["discovery"][1].__setitem__(
                 "certificate_pem",report["rounds"][0]["discovery"][0]["certificate_pem"]))
        with self.assertRaises((ValueError,InvalidSignature,h.gci3.SufficiencyRefused)):
            self.verify(r)

    def test_conflict_claiming_admission_refused(self):
        def mutate(report):
            row=report["rounds"][1]["verdict"]
            row.update({"status":"ADMITTED_AGREEMENT","returned_result":True,
                        "admitted_value":0})
        r=self.altered(mutate)
        with self.assertRaises((ValueError,InvalidSignature,h.gci3.SufficiencyRefused)):
            self.verify(r)

    def test_missing_peer_receipt_refused(self):
        r=self.altered(lambda report:report["rounds"][0]["receipts"].pop())
        with self.assertRaises((ValueError,InvalidSignature,h.gci3.SufficiencyRefused)):
            self.verify(r)

    def test_wrong_ground_refused(self):
        r=self.altered(lambda report:report["binding"].__setitem__(
              "ground_fingerprint","a"*64))
        with self.assertRaises((ValueError,InvalidSignature,h.gci3.SufficiencyRefused)):
            self.verify(r)

    def test_receipt_rebound_to_another_observer_refused(self):
        r=self.altered(lambda report:
            report["rounds"][1]["receipts"][1].__setitem__("peer_id","observer-a"))
        with self.assertRaises((ValueError,InvalidSignature,h.gci3.SufficiencyRefused)):
            self.verify(r)

    def test_fake_permitted_feature_refused(self):
        r=self.altered(lambda report:
            report["rounds"][1]["receipts"][1]["request"].__setitem__(
                "feature","full-state"))
        with self.assertRaises((ValueError,InvalidSignature,h.gci3.SufficiencyRefused)):
            self.verify(r)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True,type=Path)
    args=p.parse_args()
    GCI005ActualReceiptTests.directory=args.directory
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(GCI005ActualReceiptTests)
    outcome=unittest.TextTestRunner(verbosity=2).run(suite)
    if not outcome.wasSuccessful():
        raise SystemExit(1)

if __name__=="__main__":
    main()
