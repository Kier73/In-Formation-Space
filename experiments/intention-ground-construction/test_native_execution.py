"""IGC-002 real E-CPU Hypervisor, separate receiver-process and recovery tests."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from construct import digest, synthesize
from native_execution import (
    NativeGroundError, initial_checkpoint, validate_source, verify_checkpoint,
)

HERE = Path(__file__).resolve().parent
INTENT = json.loads((HERE / "intention.json").read_text(encoding="utf8"))


class NativeGroundTests(unittest.TestCase):
    """Run through a pinned actual E-CPU checkout, not a native API stand-in."""

    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.intent=copy.deepcopy(INTENT)
        self.receipt=synthesize(self.intent)
        self.intent_path=self.root/"trusted-intention.json"
        self.receipt_path=self.root/"candidate-receipt.json"
        self.intention_sha=digest(self.intent)
        self._save_sources()
        self.ground=self.receipt["payload"]["ground"]
        self.zero=initial_checkpoint(self.intention_sha,self.ground["ground_sha256"])
        self._calls=0

    def _save_sources(self):
        self.intent_path.write_text(json.dumps(self.intent),encoding="utf8")
        self.receipt_path.write_text(json.dumps(self.receipt),encoding="utf8")

    def worker(self,previous,token="0",host="receiver-a",grant=True,
               pin=None,expected_intention=None):
        self._calls+=1
        output=self.root/f"result-{self._calls}.json"
        checkpoint=self.root/f"previous-{self._calls}.json"
        checkpoint.write_text(json.dumps(previous),encoding="utf8")
        args=[sys.executable,str(HERE/"native_execution.py"),
              "--intention",str(self.intent_path),
              "--receipt",str(self.receipt_path),
              "--expected-intention-sha256",
              self.intention_sha if expected_intention is None else expected_intention,
              "--checkpoint",str(checkpoint),
              "--expected-checkpoint-sha256",
              previous["sha256"] if pin is None else pin,
              "--token",token,"--host-id",host,"--output",str(output)]
        if grant:
            args.append("--grant-compute")
        run=subprocess.run(args,text=True,capture_output=True,timeout=30)
        if run.returncode:
            return run,None
        return run,json.loads(output.read_text(encoding="utf8"))

    def test_distinct_receivers_reconstruct_and_continue_after_first_exits(self):
        first,res=self.worker(self.zero,"0","receiver-a")
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(res["status"],"executed_on_receiver_native_hypervisor")
        self.assertEqual(res["diagnostics"]["hypervisor_action"],"allow")
        self.assertEqual(res["diagnostics"]["handler_invocations"],1)
        first_pid=res["diagnostics"]["os_process_id"]
        checkpoint=res["checkpoint"]
        self.assertEqual(verify_checkpoint(checkpoint,self.ground,self.intention_sha)[:2],(1,1))
        self.assertEqual(checkpoint["payload"]["events"][0]["native_effect"]["kind"],
                         "virtual_layer.operator_result")
        # A wholly new process reconstructs the source and historic evidence;
        # it does not hold the first receiver's HeadlessOS or Python objects.
        second,res=self.worker(checkpoint,"1","receiver-b")
        self.assertEqual(second.returncode,0,second.stderr)
        self.assertNotEqual(first_pid,res["diagnostics"]["os_process_id"])
        self.assertEqual(res["checkpoint"]["payload"]["state"],2)
        self.assertTrue(res["checkpoint"]["payload"]["events"][-1]["accepting"])
        self.assertEqual(verify_checkpoint(res["checkpoint"],self.ground,self.intention_sha)[0],2)
        # A third receiver uses the carried prefix and no original worker.
        third,res3=self.worker(res["checkpoint"],"0","receiver-c")
        self.assertEqual(third.returncode,0,third.stderr)
        self.assertEqual(res3["checkpoint"]["payload"]["state"],1)
        fourth,res4=self.worker(res3["checkpoint"],"1","receiver-d")
        self.assertEqual(fourth.returncode,0,fourth.stderr)
        self.assertEqual(res4["checkpoint"]["payload"]["state"],2)
        self.assertEqual([e["host_id"] for e in res4["checkpoint"]["payload"]["events"]],
                         ["receiver-a","receiver-b","receiver-c","receiver-d"])

    def test_denied_receiver_never_calls_native_handler_or_advances_head(self):
        p,res=self.worker(self.zero,grant=False)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(res["status"],"refused_receiver_authority")
        self.assertEqual(res["diagnostics"]["hypervisor_action"],"deny")
        self.assertEqual(res["diagnostics"]["handler_invocations"],0)
        self.assertEqual(res["checkpoint"],self.zero)

    def test_stale_receiver_expected_root_rejected(self):
        p,first=self.worker(self.zero)
        self.assertEqual(p.returncode,0,p.stderr)
        stale,_=self.worker(self.zero,token="1",host="receiver-b",
                            pin=first["checkpoint"]["sha256"])
        self.assertNotEqual(stale.returncode,0)
        self.assertIn("high-water",stale.stderr)

    def test_mathematical_transition_forgery_is_refused_even_when_rehashed(self):
        p,first=self.worker(self.zero)
        self.assertEqual(p.returncode,0,p.stderr)
        forged=copy.deepcopy(first["checkpoint"])
        forged["payload"]["events"][0]["after"]=0
        event=forged["payload"]["events"][0]
        event["head"]=digest({k:v for k,v in event.items() if k!="head"})
        forged["payload"]["state"]=0
        forged["payload"]["head"]=event["head"]
        forged["sha256"]=digest(forged["payload"])
        # Even a hypothetical trusting host that pinned the *forged* head must
        # independently reject the mathematically invalid stage.
        denied,_=self.worker(forged,host="receiver-b")
        self.assertNotEqual(denied.returncode,0)
        self.assertIn("mathematical transition",denied.stderr)

    def test_native_effect_contract_forgery_refused(self):
        p,first=self.worker(self.zero)
        self.assertEqual(p.returncode,0,p.stderr)
        forged=copy.deepcopy(first["checkpoint"])
        forged["payload"]["events"][0]["native_effect"]["operator_id"]="forged.operator"
        event=forged["payload"]["events"][0]
        event["head"]=digest({k:v for k,v in event.items() if k!="head"})
        forged["payload"]["head"]=event["head"]
        forged["sha256"]=digest(forged["payload"])
        refused,_=self.worker(forged,host="receiver-b")
        self.assertNotEqual(refused.returncode,0)
        self.assertIn("historical native effect",refused.stderr)

    def test_two_state_capacity_obstruction_cannot_be_native_executed(self):
        self.intent["max_states"]=2
        self.receipt=synthesize(self.intent)
        self.intention_sha=digest(self.intent)
        self._save_sources()
        self.assertEqual(self.receipt["payload"]["status"],
                         "insufficient_declared_state_capacity")
        not_admitted,_=self.worker(self.zero,expected_intention=self.intention_sha)
        self.assertNotEqual(not_admitted.returncode,0)
        self.assertIn("mathematical receipt",not_admitted.stderr)

    def test_contradiction_is_not_executable(self):
        self.intent["required"].append(["0"])
        self.receipt=synthesize(self.intent)
        self.intention_sha=digest(self.intent)
        self._save_sources()
        refused,_=self.worker(self.zero,expected_intention=self.intention_sha)
        self.assertNotEqual(refused.returncode,0)
        self.assertIn("mathematical receipt",refused.stderr)

    def test_rehashed_forged_constructed_ground_refused_by_node(self):
        self.receipt["payload"]["ground"]["transitions"][0][0]=0
        ground=self.receipt["payload"]["ground"]
        ground["ground_sha256"]=digest({k:v for k,v in ground.items()
                                       if k!="ground_sha256"})
        self.receipt["sha256"]=digest(self.receipt["payload"])
        self._save_sources()
        refused,_=self.worker(self.zero)
        self.assertNotEqual(refused.returncode,0)
        self.assertIn("mathematical verification refused",refused.stderr)

    def test_source_revision_change_rejected_by_receiver_owned_pin(self):
        self.intent["max_states"]=4
        self.receipt=synthesize(self.intent)
        self._save_sources()
        refused,_=self.worker(self.zero)
        self.assertNotEqual(refused.returncode,0)
        self.assertIn("intention revision mismatch",refused.stderr)

    def test_token_and_host_selection_refuse_unlisted_values(self):
        bad_token,_=self.worker(self.zero,token="DELETE")
        self.assertNotEqual(bad_token.returncode,0)
        self.assertIn("token not admitted",bad_token.stderr)
        bad_host,_=self.worker(self.zero,host="../untrusted-host")
        self.assertNotEqual(bad_host.returncode,0)
        self.assertIn("host identifier",bad_host.stderr)

    def test_independent_verifier_is_mandatory_before_local_authority(self):
        self.receipt["payload"]["authority"]="grant_everyone"
        self.receipt["sha256"]=digest(self.receipt["payload"])
        self._save_sources()
        refused,_=self.worker(self.zero)
        self.assertNotEqual(refused.returncode,0)
        self.assertIn("mathematical verification refused",refused.stderr)

    def test_checkpoint_identity_never_transports_native_capability(self):
        p,first=self.worker(self.zero)
        self.assertEqual(p.returncode,0,p.stderr)
        checkpoint=first["checkpoint"]
        denied,res=self.worker(checkpoint,host="receiver-b",token="1",grant=False)
        self.assertEqual(denied.returncode,0,denied.stderr)
        self.assertEqual(res["status"],"refused_receiver_authority")
        self.assertEqual(res["checkpoint"],checkpoint)
        allowed,res2=self.worker(checkpoint,host="receiver-c",token="1",grant=True)
        self.assertEqual(allowed.returncode,0,allowed.stderr)
        self.assertTrue(res2["checkpoint"]["payload"]["events"][-1]["accepting"])


if __name__=="__main__":
    unittest.main()
