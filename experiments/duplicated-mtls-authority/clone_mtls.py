"""Exercise cloned owner/member TLS credentials against real recovery-lineage mTLS services.

The two authority domains have distinct local journals and OS processes but share
one test CA, one owner certificate/key, and the same member certificates/keys.
This is a credential-clone experiment on one host, not a physical distributed
deployment or a claim against TLS itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import ssl
import subprocess
import sys
import time
from typing import Any, Mapping

from mailcpu import (
    DistributedRecoveryLineageCoordinator,
    RecoveryLineageAuthority,
    RecoveryLineageCoordinator,
    RecoveryLineageError,
    RecoveryLineagePeerClient,
    RecoveryLineageTransportError,
    RecoveryStateManifest,
    SeedCommitMembership,
)


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = Path(__file__).resolve().parent
OWNER_DNS = "owner-a.mailcpu.test"
SERVER_DNS = {"B": "member-b.mailcpu.test", "C": "member-c.mailcpu.test"}
INTRUDER_DNS = "intruder.mailcpu.test"
SYSTEM_ID = "ifs-mtls-credential-clone-machine"
MEMBER_IDS = ("A", "B", "C")
OWNER_ID = "A"
OWNER_TERM = 1
GENESIS = hashlib.sha256(b"ifs-mtls-credential-clone-genesis-v1").hexdigest()
REPORT_FORMAT = "in-formation.duplicated-mtls-authority-domain-observation/0.1"


class CloneExperimentError(RuntimeError):
    """The local mTLS clone experiment could not produce or reconstruct valid evidence."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(dict(value)) + b"\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloneExperimentError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CloneExperimentError(f"JSON evidence {path} must contain an object")
    return value


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def certificate_der_sha256(path: Path) -> str:
    der = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))
    return hashlib.sha256(der).hexdigest()


def _openssl(directory: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["openssl", *arguments],
        cwd=directory,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CloneExperimentError(f"OpenSSL command failed: {result.stderr.strip()}")


def create_test_certificates(directory: Path) -> dict[str, Path]:
    """Create a throwaway CA, three shared clone identities, and a trusted wrong-DNS client."""
    if shutil.which("openssl") is None:
        raise CloneExperimentError("OpenSSL CLI is required for ephemeral mTLS test certificates")
    directory.mkdir(parents=True, exist_ok=True)
    ca_key = directory / "test-ca.key"
    ca_certificate = directory / "test-ca.pem"
    _openssl(
        directory,
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(ca_key), "-out", str(ca_certificate),
        "-days", "2", "-sha256",
        "-subj", "/CN=IFS cloned identity test CA",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
    )
    result: dict[str, Path] = {"ca_key": ca_key, "ca": ca_certificate}
    identities = {
        "A": OWNER_DNS,
        "B": SERVER_DNS["B"],
        "C": SERVER_DNS["C"],
        "intruder": INTRUDER_DNS,
    }
    for identity, dns_name in identities.items():
        private_key = directory / f"{identity}.key"
        request = directory / f"{identity}.csr"
        certificate = directory / f"{identity}.pem"
        extensions = directory / f"{identity}.ext"
        _openssl(
            directory,
            "req", "-new", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(private_key), "-out", str(request),
            "-subj", f"/CN={dns_name}",
        )
        extensions.write_text(
            "\n".join(
                (
                    f"subjectAltName=DNS:{dns_name}",
                    "extendedKeyUsage=clientAuth,serverAuth",
                    "basicConstraints=critical,CA:FALSE",
                    "keyUsage=critical,digitalSignature,keyEncipherment",
                )
            ) + "\n",
            encoding="utf-8",
        )
        _openssl(
            directory,
            "x509", "-req", "-in", str(request),
            "-CA", str(ca_certificate), "-CAkey", str(ca_key),
            "-CAcreateserial", "-out", str(certificate),
            "-days", "2", "-sha256", "-extfile", str(extensions),
        )
        result[f"{identity}_key"] = private_key
        result[f"{identity}_cert"] = certificate
    return result


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    e_cpu = ROOT / "external" / "E-CPU"
    existing = environment.get("PYTHONPATH", "")
    prefix = str(e_cpu)
    environment["PYTHONPATH"] = os.pathsep.join(
        [prefix, existing] if existing else [prefix]
    )
    return environment


def _wait_for_ready(process: subprocess.Popen[str], timeout_seconds: float = 12.0) -> dict[str, Any]:
    if process.stdout is None:
        raise CloneExperimentError("authority process stdout was not captured")
    ready_set, _, _ = select.select([process.stdout], [], [], timeout_seconds)
    if not ready_set:
        process.kill()
        stdout, stderr = process.communicate(timeout=5)
        raise CloneExperimentError(
            f"authority process did not announce readiness; stdout={stdout!r}; stderr={stderr!r}"
        )
    line = process.stdout.readline()
    if not line:
        stdout, stderr = process.communicate(timeout=5)
        raise CloneExperimentError(
            f"authority process exited before readiness; stdout={stdout!r}; stderr={stderr!r}"
        )
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise CloneExperimentError(f"authority readiness line is malformed: {line!r}") from exc
    if not isinstance(value, dict):
        raise CloneExperimentError("authority readiness record must be an object")
    return value


def _start_authority(
    *,
    cluster_id: str,
    member_id: str,
    membership_path: Path,
    journal_path: Path,
    certificates: Mapping[str, Path],
) -> tuple[subprocess.Popen[str], dict[str, Any]]:
    worker = EXPERIMENT / "tls_authority_worker.py"
    process = subprocess.Popen(
        [
            sys.executable,
            str(worker),
            member_id,
            str(membership_path),
            str(journal_path),
            str(certificates[f"{member_id}_cert"]),
            str(certificates[f"{member_id}_key"]),
            str(certificates["ca"]),
            OWNER_DNS,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=_environment(),
    )
    try:
        ready = _wait_for_ready(process)
    except Exception:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        raise
    if ready.get("member_id") != member_id:
        process.kill()
        process.communicate(timeout=5)
        raise CloneExperimentError(f"{cluster_id}/{member_id} announced the wrong service identity")
    ready["certificate_der_sha256"] = certificate_der_sha256(certificates[f"{member_id}_cert"])
    ready["server_private_key_file_sha256"] = file_sha256(certificates[f"{member_id}_key"])
    ready["dns_name"] = SERVER_DNS[member_id]
    return process, ready


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)


def _start_owner(
    *,
    cluster_id: str,
    state_label: str,
    membership_path: Path,
    endpoints_path: Path,
    certificates: Mapping[str, Path],
    start_gate: Path,
    out_dir: Path,
) -> subprocess.Popen[str]:
    worker = EXPERIMENT / "clone_owner_worker.py"
    return subprocess.Popen(
        [
            sys.executable,
            str(worker),
            "--cluster-id", cluster_id,
            "--state-label", state_label,
            "--membership", str(membership_path),
            "--endpoints", str(endpoints_path),
            "--owner-certificate", str(certificates["A_cert"]),
            "--owner-private-key", str(certificates["A_key"]),
            "--client-ca", str(certificates["ca"]),
            "--owner-dns", OWNER_DNS,
            "--start-gate", str(start_gate),
            "--out-dir", str(out_dir),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_environment(),
    )


def _wait_for_owner(process: subprocess.Popen[str], cluster_id: str, timeout_seconds: float = 40.0) -> None:
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate(timeout=5)
        raise CloneExperimentError(
            f"{cluster_id} owner did not finish; stdout={stdout!r}; stderr={stderr!r}"
        )
    if process.returncode != 0:
        raise CloneExperimentError(
            f"{cluster_id} owner failed (exit={process.returncode}); "
            f"stdout={stdout!r}; stderr={stderr!r}"
        )


def _owner_tls_context(certificates: Mapping[str, Path], identity: str = "A") -> ssl.SSLContext:
    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=str(certificates["ca"]),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        certfile=str(certificates[f"{identity}_cert"]),
        keyfile=str(certificates[f"{identity}_key"]),
    )
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def _probe_wrong_dns_identity(
    membership: SeedCommitMembership,
    endpoint: Mapping[str, Any],
    certificates: Mapping[str, Path],
) -> tuple[bool, tuple[int, str] | None]:
    """The trusted but wrongly named client cert must not enter the service's expected-owner channel."""
    wrong_peer: RecoveryLineagePeerClient | None = None
    rejected = False
    try:
        wrong_peer = RecoveryLineagePeerClient.connect_mutual_tls(
            membership,
            "B",
            str(endpoint["host"]),
            int(endpoint["port"]),
            _owner_tls_context(certificates, "intruder"),
            server_hostname=str(endpoint["dns_name"]),
            timeout=1.0,
            handshake_timeout=1.0,
        )
        wrong_peer.committed_state()
    except RecoveryLineageTransportError:
        rejected = True
    finally:
        if wrong_peer is not None:
            wrong_peer.close()

    if not rejected:
        return False, None

    good_peer: RecoveryLineagePeerClient | None = None
    try:
        good_peer = RecoveryLineagePeerClient.connect_mutual_tls(
            membership,
            "B",
            str(endpoint["host"]),
            int(endpoint["port"]),
            _owner_tls_context(certificates, "A"),
            server_hostname=str(endpoint["dns_name"]),
            timeout=2.0,
            handshake_timeout=2.0,
        )
        state = good_peer.committed_state()
        return True, state
    except RecoveryLineageTransportError:
        return True, None
    finally:
        if good_peer is not None:
            good_peer.close()


def _reconstruct_cluster(
    cluster_dir: Path,
    membership: SeedCommitMembership,
    owner_result: Mapping[str, Any],
    remote_processes: Mapping[str, int],
) -> dict[str, Any]:
    manifest = RecoveryStateManifest.from_snapshot(owner_result["manifest"])
    if owner_result["membership_digest"] != membership.digest:
        raise CloneExperimentError("owner result membership digest differs from the shared membership")
    if owner_result["manifest_digest"] != manifest.digest:
        raise CloneExperimentError("owner result manifest digest is invalid")
    state_path = cluster_dir / owner_result["state_payload"]["file_name"]
    payload = state_path.read_bytes()
    manifest.verify_payload(payload)
    if (
        len(payload) != owner_result["state_payload"]["size_bytes"]
        or hashlib.sha256(payload).hexdigest() != owner_result["state_payload"]["sha256"]
    ):
        raise CloneExperimentError("owner state payload does not match its retained digest and size")

    authorities = {
        member_id: RecoveryLineageAuthority(
            membership,
            member_id,
            cluster_dir / "authorities" / f"{member_id}.jsonl",
        )
        for member_id in membership.member_ids
    }
    if not all(authority.verify() for authority in authorities.values()):
        raise CloneExperimentError(f"{cluster_dir.name} contains a journal that failed replay verification")
    observer = RecoveryLineageCoordinator(membership, authorities)
    reconstructed = observer.verify_state(manifest)
    high_water = observer.high_water()
    bundled_proof = owner_result["proof"]
    if reconstructed.snapshot() != bundled_proof:
        raise CloneExperimentError(f"{cluster_dir.name} observer could not reconstruct the exact owner proof")
    if high_water != (manifest.generation, manifest.digest):
        raise CloneExperimentError(f"{cluster_dir.name} observer recovered a different high-water")

    journal_rows = []
    for member_id in membership.member_ids:
        journal_path = cluster_dir / "authorities" / f"{member_id}.jsonl"
        authority = authorities[member_id]
        journal_rows.append(
            {
                "member_id": member_id,
                "journal_sha256": file_sha256(journal_path),
                "journal_size_bytes": journal_path.stat().st_size,
                "committed_state": list(authority.committed_state() or (0, membership.genesis_state_digest)),
                "journal_replay_verified": authority.verify(),
            }
        )
    return {
        "cluster_id": owner_result["cluster_id"],
        "owner_process_id": owner_result["owner_process_id"],
        "owner_certificate_der_sha256": owner_result["owner_identity"]["certificate_der_sha256"],
        "owner_private_key_file_sha256": owner_result["owner_identity"]["private_key_file_sha256"],
        "root_digest": manifest.digest,
        "manifest": manifest.snapshot(),
        "manifest_digest": manifest.digest,
        "proof_digest": digest(owner_result["proof"]),
        "prepare_members": owner_result["prepare_members"],
        "commit_members": owner_result["commit_members"],
        "remote_processes": dict(remote_processes),
        "remote_authorities": owner_result["remote_authorities"],
        "journal_reports": journal_rows,
        "local_quorum_reconstructed": True,
        "local_high_water": {
            "generation": high_water[0],
            "root_digest": high_water[1],
        },
    }


def run_cloned_mtls_authority_experiment(
    out_dir: Path,
    *,
    left_state: str = "left-state",
    right_state: str = "right-state",
) -> dict[str, Any]:
    """Run two isolated local quorum copies that intentionally reuse the same mTLS credentials."""
    out_dir.mkdir(parents=True, exist_ok=True)
    credential_dir = out_dir / "credentials"
    certificates = create_test_certificates(credential_dir)
    membership = SeedCommitMembership(
        SYSTEM_ID,
        1,
        MEMBER_IDS,
        OWNER_ID,
        OWNER_TERM,
        GENESIS,
    )
    membership_path = out_dir / "membership.json"
    write_json(membership_path, membership.snapshot())

    processes: dict[str, subprocess.Popen[str]] = {}
    owner_processes: dict[str, subprocess.Popen[str]] = {}
    try:
        endpoint_docs: dict[str, dict[str, Any]] = {}
        for cluster_id in ("left", "right"):
            cluster_dir = out_dir / cluster_id
            cluster_dir.mkdir(parents=True, exist_ok=True)
            endpoint_docs[cluster_id] = {}
            for member_id in ("B", "C"):
                process, ready = _start_authority(
                    cluster_id=cluster_id,
                    member_id=member_id,
                    membership_path=membership_path,
                    journal_path=cluster_dir / "authorities" / f"{member_id}.jsonl",
                    certificates=certificates,
                )
                processes[f"{cluster_id}-{member_id}"] = process
                endpoint_docs[cluster_id][member_id] = ready

            write_json(cluster_dir / "endpoints.json", endpoint_docs[cluster_id])

        start_gate = out_dir / "start-both-owners"
        owner_processes["left"] = _start_owner(
            cluster_id="left",
            state_label=left_state,
            membership_path=membership_path,
            endpoints_path=out_dir / "left" / "endpoints.json",
            certificates=certificates,
            start_gate=start_gate,
            out_dir=out_dir / "left",
        )
        owner_processes["right"] = _start_owner(
            cluster_id="right",
            state_label=right_state,
            membership_path=membership_path,
            endpoints_path=out_dir / "right" / "endpoints.json",
            certificates=certificates,
            start_gate=start_gate,
            out_dir=out_dir / "right",
        )
        # Both owner processes start from the same credential and configuration before either is released.
        start_gate.write_text("go\n", encoding="ascii")
        _wait_for_owner(owner_processes["left"], "left")
        _wait_for_owner(owner_processes["right"], "right")

        owner_results = {
            cluster_id: read_json(out_dir / cluster_id / "owner-result.json")
            for cluster_id in ("left", "right")
        }
        wrong_dns_rejected, good_identity_state = _probe_wrong_dns_identity(
            membership,
            endpoint_docs["left"]["B"],
            certificates,
        )
        if not wrong_dns_rejected:
            raise CloneExperimentError("service accepted a CA-trusted client certificate with the wrong owner DNS SAN")
        expected_left_root = owner_results["left"]["manifest_digest"]
        if good_identity_state != (1, expected_left_root):
            raise CloneExperimentError("correct owner DNS identity could not resume the left service after rejection")

        # The verifier is deliberately a different process context from both owner processes.
        clusters = {}
        for cluster_id in ("left", "right"):
            remote_pids = {
                member_id: int(endpoint_docs[cluster_id][member_id]["process_id"])
                for member_id in ("B", "C")
            }
            clusters[cluster_id] = _reconstruct_cluster(
                out_dir / cluster_id,
                membership,
                owner_results[cluster_id],
                remote_pids,
            )

        left = clusters["left"]
        right = clusters["right"]
        shared_fixed_membership = (
            owner_results["left"]["membership"] == owner_results["right"]["membership"]
            and owner_results["left"]["membership_digest"] == owner_results["right"]["membership_digest"]
            == membership.digest
        )
        same_generation_and_predecessor = (
            left["manifest"]["generation"] == right["manifest"]["generation"]
            and left["manifest"]["predecessor_digest"] == right["manifest"]["predecessor_digest"]
        )
        conflicting_roots = left["root_digest"] != right["root_digest"]

        # Cross-verification is the discriminating question: a clone can prove its own root,
        # but neither clone can validate a different root at the same generation and predecessor.
        left_authorities = {
            member_id: RecoveryLineageAuthority(
                membership,
                member_id,
                out_dir / "left" / "authorities" / f"{member_id}.jsonl",
            )
            for member_id in membership.member_ids
        }
        right_authorities = {
            member_id: RecoveryLineageAuthority(
                membership,
                member_id,
                out_dir / "right" / "authorities" / f"{member_id}.jsonl",
            )
            for member_id in membership.member_ids
        }
        left_observer = RecoveryLineageCoordinator(membership, left_authorities)
        right_observer = RecoveryLineageCoordinator(membership, right_authorities)
        left_manifest = RecoveryStateManifest.from_snapshot(left["manifest"])
        right_manifest = RecoveryStateManifest.from_snapshot(right["manifest"])
        try:
            left_observer.verify_state(right_manifest)
            left_accepts_right = True
        except RecoveryLineageError:
            left_accepts_right = False
        try:
            right_observer.verify_state(left_manifest)
            right_accepts_left = True
        except RecoveryLineageError:
            right_accepts_left = False

        if conflicting_roots:
            if left_accepts_right or right_accepts_left:
                raise CloneExperimentError("a clone admitted the competing same-slot manifest")
            classification = "duplicated_mtls_identity_split_brain"
            adjudication = "refuse_automatic_winner"
            winner: str | None = None
        else:
            if not left_accepts_right or not right_accepts_left:
                raise CloneExperimentError("matching duplicate roots were incorrectly classified as a fork")
            classification = "matching_duplicate_identity_views"
            adjudication = "no_fork_observed"
            winner = None

        process_records = []
        for cluster_id in ("left", "right"):
            process_records.append(
                {
                    "cluster_id": cluster_id,
                    "owner_process_id": clusters[cluster_id]["owner_process_id"],
                    "authority_process_ids": clusters[cluster_id]["remote_processes"],
                }
            )
        observer_pid = os.getpid()
        all_pids = [
            observer_pid,
            *[
                int(clusters[c]["owner_process_id"])
                for c in ("left", "right")
            ],
            *[
                int(clusters[c]["remote_processes"][member])
                for c in ("left", "right")
                for member in ("B", "C")
            ],
        ]
        if len(all_pids) != len(set(all_pids)):
            raise CloneExperimentError("owner, authority and observer OS process IDs are not distinct")

        certificate_fingerprints = {
            identity: certificate_der_sha256(certificates[f"{identity}_cert"])
            for identity in ("A", "B", "C", "intruder")
        }
        private_key_fingerprints = {
            identity: file_sha256(certificates[f"{identity}_key"])
            for identity in ("A", "B", "C", "intruder")
        }
        credential_clone = {
            "owner_certificate_der_sha256": certificate_fingerprints["A"],
            "owner_private_key_file_sha256": private_key_fingerprints["A"],
            "member_certificate_der_sha256": {
                member: certificate_fingerprints[member] for member in ("B", "C")
            },
            "member_private_key_file_sha256": {
                member: private_key_fingerprints[member] for member in ("B", "C")
            },
            "left_and_right_owner_certificate_identical": (
                left["owner_certificate_der_sha256"] == right["owner_certificate_der_sha256"]
                == certificate_fingerprints["A"]
            ),
            "left_and_right_owner_private_key_identical": (
                left["owner_private_key_file_sha256"] == right["owner_private_key_file_sha256"]
                == private_key_fingerprints["A"]
            ),
            "left_and_right_member_certificates_identical": all(
                endpoint_docs["left"][member]["certificate_der_sha256"]
                == endpoint_docs["right"][member]["certificate_der_sha256"]
                == certificate_fingerprints[member]
                for member in ("B", "C")
            ),
            "certificates_are_ephemeral_test_credentials": True,
        }
        report = {
            "format": REPORT_FORMAT,
            "classification": classification,
            "adjudication": adjudication,
            "winner": winner,
            "membership_digest": membership.digest,
            "shared_fixed_membership": shared_fixed_membership,
            "same_generation_and_predecessor": same_generation_and_predecessor,
            "generation": left["manifest"]["generation"],
            "predecessor_digest": left["manifest"]["predecessor_digest"],
            "conflicting_roots": conflicting_roots,
            "left_accepts_right_manifest": left_accepts_right,
            "right_accepts_left_manifest": right_accepts_left,
            "clusters": [left, right],
            "credential_clone": credential_clone,
            "peer_authentication": {
                "mechanism": "mutually-authenticated TLS 1.2+",
                "owner_expected_dns": OWNER_DNS,
                "member_expected_dns": SERVER_DNS,
                "wrong_ca_trusted_but_wrong_dns_client_rejected": wrong_dns_rejected,
                "correct_owner_identity_remained_serviceable": True,
                "correct_owner_observed_left_high_water": list(good_identity_state),
            },
            "process_layout": {
                "observer_process_id": observer_pid,
                "separate_owner_and_member_processes": True,
                "distinct_process_ids": len(all_pids) == len(set(all_pids)),
                "process_count": len(all_pids),
                "same_host_process_test": True,
                "physical_fault_domain_separation_established": False,
                "clusters": process_records,
            },
            "verified_layers": [
                "both owner processes use the exact same owner certificate and private key",
                "both cloned authority sets use the same member certificate/private-key pairs",
                "each member service requires a CA-valid client certificate and the configured owner DNS SAN",
                "two separate owner OS processes authenticated to their corresponding cloned B/C services",
                "both independent local quorums durably prepared and committed the same fixed membership slot",
                "a separate observer reopened and replayed all six authority journals",
                "each local quorum reconstructs its exact owner-issued recovery proof",
                "cross-verification rejects competing roots at the same generation and predecessor",
                "a CA-trusted client certificate with the wrong owner DNS SAN is rejected without taking down the service",
            ],
            "not_established": [
                "distinct physical hosts, hardware roots, cloud accounts, power domains, or administrative fault domains; all processes run on one host",
                "non-exportability or hardware-backed protection of the TLS private keys",
                "a globally unique certificate subject or DNS SAN; DNS identity is not hardware identity",
                "protection against cloning all authority credentials and journals before a new decision",
                "distributed consensus between the two cloned authority copies; there is no cross-cluster message path",
                "an external witness or monotonic identity registry that selects one globally authorized membership",
                "actual theorem execution or VGI kernel acceptance; this is an authority-identity experiment",
            ],
        }
        write_json(out_dir / "report.json", report)
        return report
    finally:
        for process in owner_processes.values():
            if process.poll() is None:
                process.kill()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
        for process in processes.values():
            _stop(process)


def main() -> int:
    selected = argparse.ArgumentParser(description=__doc__)
    selected.add_argument("--out-dir", type=Path, required=True)
    selected.add_argument("--left-state", default="left-state")
    selected.add_argument("--right-state", default="right-state")
    args = selected.parse_args()
    report = run_cloned_mtls_authority_experiment(
        args.out_dir,
        left_state=args.left_state,
        right_state=args.right_state,
    )
    print(
        json.dumps(
            {
                "classification": report["classification"],
                "adjudication": report["adjudication"],
                "winner": report["winner"],
                "report_digest": digest(report),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
