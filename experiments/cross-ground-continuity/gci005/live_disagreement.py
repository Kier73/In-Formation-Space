"""GCI-005 real E-CPU mTLS observer consensus and signed-false-reading refusal.

Real OS child processes on one loopback CI runner, no claim of separate
administrative ownership. Coordinator never reads the hidden private phase.
Two leaf certificates have independent keys under one ephemeral test CA.
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from cryptography import x509
from cryptography.hazmat.primitives import serialization

import honesty_contract as h
import live_observer_fabric as live
from mailcpu.computational_fabric import (
    ComputationalPeerSnapshot, ComputationalFabricDirectory,
)
from mailcpu.mtls_transport import connect_mutual_tls, MutualTLSTransportError
from mailcpu.socket_transport import SocketTransport


def check(ok: bool, reason: str) -> None:
    h.require(ok,reason)


def one_round(directory: Path,scenario: str,
              binding: Mapping[str,str],
              public: Mapping[str,Any],
              plan: Mapping[str,Any]) -> dict[str, Any]:
    check(scenario in h.SCENARIOS,"unknown hosted experiment scenario")
    # The diagnostic mode must be selected by the test harness, not by a
    # caller-provided observation request or an ordinary GCI-004 coordinator.
    adversarial=scenario==h.SCENARIOS[1]
    with tempfile.TemporaryDirectory(prefix="gci005-mtls-") as temp:
        keys=Path(temp)
        identity=live.write_identity_files(keys)
        processes=[]
        transports: dict[str, SocketTransport]={}
        discovered=[]
        records=[]
        wrong_dns=False
        cleaned=False
        failure=None
        try:
            for peer in h.TWO:
                ready=keys/f"{peer}-ready.json"
                args=[sys.executable,str(Path(live.__file__).resolve()),
                      "--serve",peer,"--directory",str(directory),
                      "--cert-dir",str(keys),"--ready-path",str(ready)]
                if adversarial and peer=="observer-b":
                    args.append("--gci005-diagnostic-false-reading")
                proc=subprocess.Popen(args,
                      stdout=(keys/f"{peer}.stdout").open("w"),
                      stderr=(keys/f"{peer}.stderr").open("w"))
                processes.append((peer,proc))
            endpoints={}
            for peer,proc in processes:
                path=keys/f"{peer}-ready.json"
                end=time.monotonic()+12.0
                while time.monotonic()<end and not path.exists():
                    check(proc.poll() is None,
                          "observer died before TLS ready: "+
                          (keys/f"{peer}.stderr").read_text()[-1800:])
                    time.sleep(.02)
                check(path.exists(),"observer never opened a socket: "+peer)
                endpoints[peer]=json.loads(path.read_text())["port"]
            # Prove actual TLS rejects a different expected DNS SAN.
            try:
                t=connect_mutual_tls("127.0.0.1",endpoints["observer-a"],
                    "coordinator","observer-a",live.tls_client(keys),
                    server_hostname="forged.gci005.invalid",timeout=2,
                    handshake_timeout=2)
            except MutualTLSTransportError:
                wrong_dns=True
            else:
                t.close()
            check(wrong_dns,"wrong DNS identity was accepted by real mutual TLS")
            fabric=ComputationalFabricDirectory("coordinator",
                    {peer:h.c.PEERS[peer][1] for peer in h.TWO},
                    max_peer_lease_seconds=60)
            snapshot_by_peer={}
            for peer in h.TWO:
                dns=h.c.PEERS[peer][1]
                begin=time.perf_counter_ns()
                transport=connect_mutual_tls("127.0.0.1",endpoints[peer],
                     "coordinator",peer,live.tls_client(keys),
                     server_hostname=dns,timeout=5.0,handshake_timeout=5.0)
                handshake_ns=max(1,time.perf_counter_ns()-begin)
                transports[peer]=transport
                expected_leaf=x509.load_pem_x509_certificate(
                    (keys/f"{peer}.pem").read_bytes()
                    ).public_bytes(serialization.Encoding.DER)
                check(transport.socket.getpeercert(binary_form=True)==expected_leaf,
                      "real TLS authenticated unexpected server certificate")
                start=time.perf_counter_ns()
                live.send(transport,peer,"DISCOVER",
                    {"schema":"gci004.discovery-request.v1",
                     "ground_fingerprint":binding["ground_fingerprint"]})
                result=live.receive(transport,"SNAPSHOT")
                measured_ns=max(1,time.perf_counter_ns()-start)
                check(result is not None and result[0]=="SNAPSHOT",
                      "no authenticated source advertisement")
                snapshot=ComputationalPeerSnapshot.from_dict(result[1])
                check(fabric.merge_authenticated_snapshot(snapshot,
                      authenticated_transport=transport),
                      "live E-CPU directory rejected unique source advertisement")
                h.c.check_fabric_snapshot(result[1],peer,h.FEATURE,dns,binding)
                snapshot_by_peer[peer]=snapshot
                discovered.append({
                    "peer_id":peer,"dns":dns,"feature":h.FEATURE,
                    "certificate_pem":(keys/f"{peer}.pem").read_text(),
                    "snapshot":result[1],"snapshot_digest":snapshot.digest,
                    "discovery_rtt_ns":measured_ns,
                    "handshake_ns":handshake_ns,
                    "negotiated_tls":transport.socket.version(),
                    "channel_binding_verified":True,
                })
            check(len(fabric.active_snapshots)==2 and len(fabric.hosts)==2,
                  "real E-CPU directory did not admit both authenticated observers")
            # One identical logical challenge; the signed payload separately
            # binds each exact peer identity and snapshot revision/digest.
            challenge=secrets.token_hex(16)
            for peer in h.TWO:
                request=h.c.expected_request(
                    h.TASK,h.FEATURE,public,plan,binding,challenge)
                transport=transports[peer]
                start=time.perf_counter_ns()
                sent=live.send(transport,peer,"OBSERVE",request)
                result=live.receive(transport,"RECEIPT")
                rtt=max(1,time.perf_counter_ns()-start)
                check(result is not None and result[0]=="RECEIPT" and
                      set(result[1])=={"payload","signature_b64"},
                      "peer did not return a cryptographic observation receipt")
                message,received=result[1],result[2]
                cert=x509.load_pem_x509_certificate((keys/f"{peer}.pem").read_bytes())
                h.c.verify_receipt(cert,message["payload"],message["signature_b64"])
                payload=message["payload"]
                check(payload["request_digest"]==h.c.jdigest(request) and
                      payload["snapshot_digest"]==snapshot_by_peer[peer].digest and
                      payload["peer_id"]==peer,
                      "signed receipt did not bind the live plan and peer")
                records.append({"peer_id":peer,"request":request,
                    "payload":payload,"signature_b64":message["signature_b64"],
                    "observation_rtt_ns":rtt,"request_payload_bytes":sent,
                    "response_payload_bytes":received})
            values={r["peer_id"]:r["payload"]["value"] for r in records}
            verdict=h.decisions(values)
            check(verdict["status"]==(
                 "REFUSED_DISAGREEMENT" if adversarial else "ADMITTED_AGREEMENT"),
                 "real authenticated peer values did not reproduce diagnostic distinction")
        except BaseException as exc:
            failure=exc
        finally:
            close_errors=[]
            for peer,t in transports.items():
                try:
                    live.send(t,peer,"CLOSE",{"done":True})
                    answer=live.receive(t,"CLOSED",timeout=5)
                    if answer is None or answer[0]!="CLOSED" or answer[1]!={"done":True}:
                        close_errors.append(peer+": no completed close receipt")
                    else:
                        live.send(t,peer,"BYE",{"done":True})
                except Exception as exc:
                    close_errors.append(peer+": "+str(exc))
            server_errors=[]
            for peer,proc in processes:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                if proc.returncode!=0:
                    server_errors.append(peer+": "+(keys/f"{peer}.stderr").read_text()[-2500:])
            for t in transports.values():
                try:t.close()
                except Exception:pass
            if failure is None:
                check(not close_errors and not server_errors,
                      "host shutdown failed: "+repr(close_errors+server_errors))
                cleaned=True
            else:
                if close_errors or server_errors:
                    print("Diagnostic teardown: "+repr(close_errors+server_errors),file=sys.stderr)
        if failure is not None:
            raise failure
        return {
            "scenario":scenario,"ca_certificate_pem":identity["ca_pem"],
            "client_certificate_pem":identity["client_pem"],
            "discovery":discovered,"receipts":records,"verdict":verdict,
            "server_process_count":2,"bad_server_dns_refused":wrong_dns,
            "clean_shutdown":cleaned,"phase_withheld":True,
        }


def run(directory: Path) -> dict[str,Any]:
    binding,public,plan=h.get_binding(directory)
    source=h.cag.read(directory/"gci004-network.json")
    h.gci3.check_sealed(source,{"schema","binding","public_digest","plan_digest",
        "origin","ca_certificate_pem","client_certificate_pem","discovery",
        "requests","measurements","realization","scope","transport_kind",
        "bad_hostname_refused","forbidden_feature_refused","replay_refused"},h.c.SCHEMA)
    rounds=[one_round(directory,scenario,binding,public,plan)
            for scenario in h.SCENARIOS]
    result=h.c.sealed({
        "schema":h.SCHEMA,"binding":binding,
        "public_digest":public["report_digest"],
        "plan_digest":plan["report_digest"],
        "source_gci004_report_digest":source["report_digest"],
        "origin":"gci005-real-ecpu-mtls-disagreement",
        "rounds":rounds,"scope":h.SCOPE,
        "coordinator_does_not_read_private_phase":True,
        "transport_kind":"127.0.0.1-tcp-tlsv1.2+",
    })
    h.verify_record(result,binding,public,plan)
    h.cag.persist(directory/"gci005-quorum.json",result)
    print("GCI-005 real mTLS agreement and signed disagreement",
          result["report_digest"])
    return result


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--directory",type=Path,required=True)
    args=p.parse_args()
    try:run(args.directory)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        p.exit(1,f"GCI-005 live observer: {type(exc).__name__}: {exc}\n")


if __name__=="__main__":
    main()
