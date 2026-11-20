"""IGC-003: two actual TLS computation peers and real three-process E-CPU quorum.

No fake voters, no fake Hypervisor, no network bypass. Each test isolates its
own authority journals, ephemeral CA, source pins and archive on one CI runner.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from construct import canonical,digest,synthesize
from native_execution import initial_checkpoint,verify_checkpoint
from quorum_ground import membership_for

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ECPU_TEST=ROOT/"external"/"E-CPU"/"tests"/"test_recovery_lineage_service.py"
NETWORK=HERE/"authenticated_ground.py"
QUORUM=HERE/"quorum_ground.py"

def upstream_fixture():
    """Import only upstream E-CPU fixture creation, not its internal ledger logic."""
    spec=importlib.util.spec_from_file_location("_igc003_ecpu_service_fixture",ECPU_TEST)
    if spec is None or spec.loader is None:
        raise RuntimeError("pinned upstream E-CPU authority fixture missing")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(ECPU_TEST.exists() and shutil.which("openssl") and shutil.which("node"),
                     "requires pinned native E-CPU checkout, OpenSSL and Node")
class AuthenticatedGroundTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="igc003-")
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.fixture=upstream_fixture()
        self.certs=self.fixture._make_certificates(self.base)
        self.original=json.loads((HERE/"intention.json").read_text(encoding="utf8"))
        self.intention=copy.deepcopy(self.original)
        self.receipt=synthesize(self.intention)
        self.source_sha=digest(self.intention)
        self.ground=self.receipt["payload"]["ground"]
        self.intention_path=self.base/"trusted-intention.json"
        self.receipt_path=self.base/"trusted-receipt.json"
        self.intention_path.write_bytes(canonical(self.intention))
        self.receipt_path.write_bytes(canonical(self.receipt))
        self.zero=initial_checkpoint(self.source_sha,self.ground["ground_sha256"])
        self.membership=membership_for(self.source_sha,self.ground["ground_sha256"])
        self.archive=self.base/"archive"
        self.owner=self.base/"A-journal.jsonl"
        self.endpoints_file=self.base/"authority-endpoints.json"
        self.services={}
        self.ports={}
        self.seq=0

    def start_authorities(self):
        """Launch original B/C E-CPU services with independent durable journals."""
        for member in ("B","C"):
            proc,ready=self.fixture._start_member(self.base,self.membership,
                                                  self.certs,member)
            self.services[member]=proc
            self.ports[member]={"host":"127.0.0.1","port":ready["port"],
                                "dns":"member-"+member.lower()+".mailcpu.test"}
            self.addCleanup(self.fixture._stop,proc)
        self.endpoints_file.write_bytes(canonical(self.ports))

    def _invoke_quorum(self,action,*,checkpoint=None,output=None,hint=None,ok=True):
        args=[sys.executable,str(QUORUM),action,
              "--intention",str(self.intention_path),
              "--receipt",str(self.receipt_path),
              "--expected-intention-sha256",self.source_sha,
              "--archive",str(self.archive),
              "--owner-journal",str(self.owner),
              "--tls-dir",str(self.base),
              "--endpoints",str(self.endpoints_file)]
        if checkpoint is not None:
            path=self.base/("seal-stage-"+str(self.seq)+".json")
            path.write_bytes(canonical(checkpoint))
            args+=["--checkpoint",str(path)]
        if output is not None:args+=["--output",str(output)]
        if hint is not None:args+=["--candidate-hint",hint]
        result=subprocess.run(args,capture_output=True,text=True,timeout=45)
        if ok:
            self.assertEqual(result.returncode,0,result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode,0,result.stdout)
        return result.stderr

    def seal_and_hard_kill_owner(self,checkpoint):
        """Keep an authenticated original owner alive after sealing, then kill it."""
        self.seq+=1
        input_path=self.base/("kill-owner-candidate-"+str(self.seq)+".json")
        input_path.write_bytes(canonical(checkpoint))
        ready=self.base/("owner-sealed-before-hard-kill.json")
        args=[sys.executable,str(QUORUM),"seal",
              "--intention",str(self.intention_path),
              "--receipt",str(self.receipt_path),
              "--expected-intention-sha256",self.source_sha,
              "--archive",str(self.archive),
              "--owner-journal",str(self.owner),
              "--tls-dir",str(self.base),
              "--endpoints",str(self.endpoints_file),
              "--checkpoint",str(input_path),
              "--ready-file",str(ready),"--hard-kill-ready"]
        proc=subprocess.Popen(args,text=True,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        self.addCleanup(self.fixture._stop,proc)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline and not ready.exists():
            if proc.poll() is not None:
                out,err=proc.communicate(timeout=2)
                self.fail("original owner failed before quorum seal: "+err+out)
            time.sleep(.025)
        self.assertTrue(ready.exists(),"original quorum owner did not publish readiness")
        self.assertIsNone(proc.poll(),"original coordinator unexpectedly exited")
        sealed=json.loads(ready.read_text(encoding="utf8"))
        self.assertEqual(sealed["generation"],1)
        self.assertEqual(sealed["decision_members"],["A","B","C"])
        proc.kill()
        proc.communicate(timeout=5)
        self.assertNotEqual(proc.returncode,0)
        ready.unlink()
        self.assertFalse(ready.exists())
        return sealed

    def _start_compute(self,member,checkpoint,*,grant=True):
        self.seq+=1
        cp_path=self.base/("network-previous-"+str(self.seq)+".json")
        cp_path.write_bytes(canonical(checkpoint))
        ready=self.base/("compute-ready-"+str(self.seq)+".json")
        report=self.base/("compute-report-"+str(self.seq)+".json")
        args=[sys.executable,str(NETWORK),"server",
              "--intention",str(self.intention_path),
              "--receipt",str(self.receipt_path),
              "--expected-intention-sha256",self.source_sha,
              "--checkpoint",str(cp_path),
              "--expected-checkpoint-sha256",checkpoint["sha256"],
              "--tls-dir",str(self.base),"--host-member",member,
              "--ready-file",str(ready),"--record-file",str(report)]
        if not grant:args.append("--no-compute-right")
        proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              text=True)
        self.addCleanup(self.fixture._stop,proc)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if proc.poll() is not None:
                out,err=proc.communicate(timeout=2)
                self.fail("compute host died before mTLS readiness: "+out+err)
            if ready.exists():
                try:
                    r=json.loads(ready.read_text(encoding="utf8"))
                except json.JSONDecodeError:
                    time.sleep(.02);continue
                self.assertEqual(r["host_member"],member)
                return proc,cp_path,ready,report
            time.sleep(.02)
        self.fail("compute receiver did not expose listener readiness")

    def _client(self,member,cp_path,checkpoint,ready,token,*,ok=True):
        self.seq+=1
        output=self.base/("client-"+str(self.seq)+".json")
        args=[sys.executable,str(NETWORK),"client",
              "--intention",str(self.intention_path),
              "--receipt",str(self.receipt_path),
              "--expected-intention-sha256",self.source_sha,
              "--checkpoint",str(cp_path),
              "--expected-checkpoint-sha256",checkpoint["sha256"],
              "--tls-dir",str(self.base),"--host-member",member,
              "--advertisement",str(ready),
              "--token",token,"--output",str(output)]
        result=subprocess.run(args,text=True,capture_output=True,timeout=35)
        if ok:
            self.assertEqual(result.returncode,0,result.stderr)
            return json.loads(output.read_text(encoding="utf8"))
        self.assertNotEqual(result.returncode,0,result.stdout)
        return result.stderr

    def network_step(self,member,checkpoint,token,*,grant=True):
        host,cp_path,ready,report=self._start_compute(member,checkpoint,grant=grant)
        output=self._client(member,cp_path,checkpoint,ready,token,ok=grant)
        stdout,stderr=host.communicate(timeout=12)
        self.assertEqual(host.returncode,0,stderr)
        side=json.loads(report.read_text(encoding="utf8"))
        self.assertTrue(side["result_acknowledged"])
        self.assertEqual(side["handler_invocations"],1 if grant else 0)
        self.assertEqual(side["local_hypervisor_action"],"allow" if grant else "deny")
        if grant:
            self.assertEqual(output["status"],"native_mtls_hypervisor_executed")
            new=output["checkpoint"]
            self.assertEqual(len(new["payload"]["events"]),
                             len(checkpoint["payload"]["events"])+1)
            self.assertEqual(verify_checkpoint(new,self.ground,self.source_sha)[0],
                             len(new["payload"]["events"]))
            return new,side
        self.assertTrue("refused" in output.lower() or
                        "hypervisor" in output.lower())
        return checkpoint,side

    def test_real_mtls_compute_two_peers_and_quorum_recovery_after_owner_death(self):
        self.start_authorities()
        stage1,host1=self.network_step("B",self.zero,"0")
        self.assertEqual(stage1["payload"]["state"],1)
        sealed1=self.seal_and_hard_kill_owner(stage1)
        # The old owner's authenticated streams were severed by a hard OS
        # kill; a fresh owner has no candidate checkpoint, only the
        # protected authority journal, live peers and content archive.
        restored1=self.base/"recovered-state-1.json"
        recovered1=self._invoke_quorum("recover",output=restored1)
        self.assertEqual(recovered1["generation"],1)
        self.assertTrue(recovered1["state_selected_from_quorum_not_local_candidate"])
        cp=json.loads(restored1.read_text(encoding="utf8"))
        self.assertEqual(cp,stage1)
        stage2,host2=self.network_step("C",cp,"1")
        self.assertNotEqual(host1["host_pid"],host2["host_pid"])
        self.assertEqual(stage2["payload"]["state"],2)
        self.assertTrue(stage2["payload"]["events"][-1]["accepting"])
        sealed2=self._invoke_quorum("seal",checkpoint=stage2)
        self.assertEqual(sealed2["generation"],2)
        restored2=self.base/"recovered-state-2.json"
        current=self._invoke_quorum("recover",output=restored2)
        self.assertEqual(current["generation"],2)
        self.assertEqual(current["manifest_root"],sealed2["manifest_root"])
        self.assertEqual(json.loads(restored2.read_text(encoding="utf8")),stage2)
        stale=self._invoke_quorum("recover",hint=sealed1["manifest_root"],ok=False)
        self.assertIn("superseded",stale)
        stale_seal=self._invoke_quorum("seal",checkpoint=stage1,ok=False)
        self.assertIn("generation",stale_seal)
        evidence=os.environ.get("IGC003_EVIDENCE_DIR")
        if evidence:
            location=Path(evidence)
            location.mkdir(parents=True,exist_ok=True)
            (location/"accepted-checkpoint.json").write_bytes(canonical(stage2))
            (location/"experiment-summary.json").write_bytes(canonical({
                "schema":"ifs.igc003.mtls-quorum-evidence.v1",
                "source_sha256":self.source_sha,
                "ground_sha256":self.ground["ground_sha256"],
                "physical_host_separation":False,
                "native_mtls_operation_hosts":["B","C"],
                "operation_receiver_pids":[host1["host_pid"],host2["host_pid"]],
                "native_quorum_services":["B","C"],
                "native_quorum_state_roots":[sealed1["manifest_root"],sealed2["manifest_root"]],
                "recovered_latest_root":current["manifest_root"],
                "final_mathematical_state":2,
                "final_accepting":True,
                "stale_state_refused":True,
                "network_transport":"E-CPU native reliable Hypervisor operation over mutual TLS",
                "recovery_authority":"E-CPU DistributedRecoveryLineageCoordinator",
                "quorum_rollback_protection":"majority at time of read, fixed membership",
                "source_authentication":"caller-pinned SHA only; no external signature",
            }))

    def test_client_lacks_permission_despite_valid_ground_and_peer_certificate(self):
        cp,host=self.network_step("B",self.zero,"0",grant=False)
        self.assertEqual(cp,self.zero)
        self.assertEqual(host["handler_invocations"],0)

    def test_mtls_rejects_wrong_server_dns_even_with_valid_ca_cert(self):
        proc,cp,ready,report=self._start_compute("B",self.zero)
        altered=json.loads(ready.read_text(encoding="utf8"))
        # Rebind the advertised *label* to C while the real TLS server is B.
        # The client may construct a typed workload, but only the actual
        # negotiated certificate may establish the peer identity.
        altered["host_member"]="C"
        altered["node_id"]="igc003-C"
        altered["peer_server_dns"]="member-c.mailcpu.test"
        ready.write_bytes(canonical(altered))
        failure=self._client("C",cp,self.zero,ready,"0",ok=False)
        self.assertTrue("certificate" in failure.lower()
                        or "tls" in failure.lower()
                        or "mutually authenticated" in failure.lower())
        # No forged request reaches receiver. Terminate blocked peer.
        self.fixture._stop(proc)

    def test_tampered_archived_state_fails_even_when_quorum_root_valid(self):
        self.start_authorities()
        cp,_=self.network_step("B",self.zero,"0")
        sealed=self._invoke_quorum("seal",checkpoint=cp)
        from quorum_ground import archived
        location=archived(self.archive,"objects",sealed["state_digest"])
        content=location.read_bytes()
        location.write_bytes(content.replace(b'"state":1',b'"state":2'))
        failure=self._invoke_quorum("recover",ok=False)
        self.assertTrue("digest" in failure.lower() or
                        "checkpoint" in failure.lower())

    def test_missing_quorum_services_cannot_admit_even_valid_math(self):
        self.start_authorities()
        cp,_=self.network_step("B",self.zero,"0")
        sealed=self._invoke_quorum("seal",checkpoint=cp)
        self.fixture._stop(self.services["B"])
        self.fixture._stop(self.services["C"])
        failure=self._invoke_quorum("recover",ok=False)
        self.assertTrue("connection" in failure.lower() or
                        "authority" in failure.lower() or "refused" in failure.lower())


if __name__=="__main__":
    unittest.main()
