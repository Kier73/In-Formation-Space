#!/usr/bin/env python3
"""Two network-isolated E-CPU proof hosts: kill, recovery, acceptance, replay.

A CI *virtual-host* integration exercise, NOT two physical computers. Docker
gives separate network namespaces, PID namespaces, read-only code image and
disjoint mounts. The destination independently authenticates six upstream
GitHub/Sigstore artifacts, owns its prior Lean-intention and a durable ledger.

Test-only PKI provisioner distributes each participant's key and the common CA
before launch, never sending keys or recipient policy over the proof stream.

A killed receiving process does not get a semantic receipt for incomplete
delivery. Sender restarts and retransmits the whole immutable six-part package
on a new mutual-TLS session. The ledger survives a *second* receiving-process
restart and rejects the otherwise authentic repeated package.

This is deliberately whole-package retry, NOT a durable E-CPU frame/checkpoint
resume or proof of physically separate hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Mapping

from ecpu_proof_transit_demo import _certs
import proof_receipt_receiver as receiver
import term_receipt as term

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
IMAGE_DOCKERFILE = HERE / "Dockerfile.proof-host"
PORT = 49773
TIMEOUT = 260
POLL = 0.15


class IsolatedHostFailure(RuntimeError):
    pass


def call(argv: list[str], *, timeout: int = TIMEOUT, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    if check and result.returncode != 0:
        raise IsolatedHostFailure(
            f"command {argv[0:3]} exit={result.returncode}: {result.stderr[-1200:]}"
        )
    return result


def docker(*args: str, check: bool = True, timeout: int = TIMEOUT) -> subprocess.CompletedProcess[str]:
    return call(["docker", *args], check=check, timeout=timeout)


def _copy(source: Path, destination: Path, *, private: bool = False) -> None:
    if not source.is_file() or source.is_symlink():
        raise IsolatedHostFailure("host provisioning source must be a regular file")
    shutil.copyfile(source, destination)
    destination.chmod(0o600 if private else 0o644)


def _build_context(workspace: Path) -> Path:
    context = workspace / "image-context"
    context.mkdir(mode=0o700)
    for dest, source in (
        ("experiment", HERE),
        ("mailcpu", REPO_ROOT / "external" / "E-CPU" / "mailcpu"),
        ("vgi", REPO_ROOT / "external" / "Virtual-Ground-Interpreter" / "virtual_ground_interpreter" / "vgi"),
    ):
        if not source.is_dir():
            raise IsolatedHostFailure(f"pinned software checkout missing: {source}")
        shutil.copytree(source, context / dest,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    _copy(IMAGE_DOCKERFILE, context / "Dockerfile")
    return context


def _provision(workspace: Path, subjects: Mapping[str, Path], intent: Path) -> dict[str, Path]:
    if set(subjects) != set(receiver.SUBJECTS):
        raise IsolatedHostFailure("host provisioner requires exact six subjects")
    result = {}
    for label in ("sender-data", "sender-credentials", "recipient-state",
                  "recipient-credentials", "ca-provisioner"):
        directory = workspace / label
        directory.mkdir(mode=0o700)
        result[label] = directory

    # The admin-created CA key exists only in ca-provisioner. It is never
    # mounted in either host, and is destroyed when this experiment exits.
    certificates = _certs(result["ca-provisioner"])
    _copy(certificates["ca"], result["sender-credentials"] / "ca.pem")
    _copy(certificates["ca"], result["recipient-credentials"] / "ca.pem")
    _copy(certificates["client_cert"], result["sender-credentials"] / "identity.pem")
    _copy(certificates["server_cert"], result["recipient-credentials"] / "identity.pem")
    _copy(certificates["client_key"], result["sender-credentials"] / "identity.key", private=True)
    _copy(certificates["server_key"], result["recipient-credentials"] / "identity.key", private=True)

    for kind in receiver.SUBJECTS:
        _copy(subjects[kind], result["sender-data"] / f"{kind}.bin")
    # Intention is delivered by a locally trusted provisioner, not sent
    # inside the evidence payload or visible to the proof origin container.
    trusted_intent = receiver.ReceiverIntent.load(intent)
    _copy(intent, result["recipient-state"] / "trusted-intent.json", private=True)
    if trusted_intent.recipient_scope != "ecpu-virtual-host-B":
        raise IsolatedHostFailure("recipient policy's designated audience is not host B")
    return result


def _runtime_common(name: str, network: str, image: str, provisioned: Mapping[str, Path],
                    *, recipient: bool, host_gh: Path) -> list[str]:
    args = [
        "--name", name, "--network", network,
        "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "HOME=/tmp",
        "-e", "XDG_CACHE_HOME=/tmp/cache",
    ]
    if recipient:
        args.extend([
            "--network-alias", "proof-recipient",
            "--mount", f"type=bind,src={provisioned['recipient-credentials']},dst=/identity,readonly",
            "--mount", f"type=bind,src={provisioned['recipient-state']},dst=/recipient",
            "--mount", f"type=bind,src={host_gh},dst=/usr/local/bin/gh,readonly",
            "-e", "GH_TOKEN",
        ])
    else:
        args.extend([
            "--mount", f"type=bind,src={provisioned['sender-credentials']},dst=/identity,readonly",
            "--mount", f"type=bind,src={provisioned['sender-data']},dst=/sender,readonly",
        ])
    args.append(image)
    return args


def _server(name: str, network: str, image: str, provisioned: Mapping[str, Path], gh: Path) -> None:
    args = _runtime_common(name, network, image, provisioned, recipient=True, host_gh=gh)
    docker("run", "-d", *args,
           "serve", "--bind", "0.0.0.0", "--port", str(PORT),
           "--ca", "/identity/ca.pem", "--cert", "/identity/identity.pem",
           "--key", "/identity/identity.key",
           "--intent", "/recipient/trusted-intent.json",
           "--ledger", "/recipient/durable-proof-ledger.sqlite3",
           "--output", "/recipient/admitted-once.json",
           "--transport-report", "/recipient/transport-observation.json")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        report = docker("logs", name, check=False).stdout
        if f"LISTEN_PORT={PORT}" in report:
            return
        status = docker("inspect", "-f", "{{.State.Running}}", name).stdout.strip()
        if status != "true":
            raise IsolatedHostFailure(
                f"recipient container exited before TLS binding: {docker('logs', name, check=False).stderr[-900:]}"
            )
        time.sleep(POLL)
    raise IsolatedHostFailure("recipient virtual host did not bind its TLS address")


def _sender(name: str, network: str, image: str, provisioned: Mapping[str, Path],
            gh: Path, *, fault: bool) -> subprocess.CompletedProcess[str]:
    args = _runtime_common(name, network, image, provisioned, recipient=False, host_gh=gh)
    args.extend([
        "send", "--host", "proof-recipient", "--port", str(PORT),
        "--ca", "/identity/ca.pem", "--cert", "/identity/identity.pem",
        "--key", "/identity/identity.key",
    ])
    if fault:
        args.extend(["--test-fault-after-frames", "2"])
    for kind in receiver.SUBJECTS:
        args.extend(["--" + kind.replace("_", "-"), f"/sender/{kind}.bin"])
    return docker("run", "--rm", *args, check=False)


def _await_exit(name: str) -> tuple[int, str]:
    result = docker("wait", name, timeout=TIMEOUT)
    code = int(result.stdout.strip())
    log = docker("logs", name, check=False)
    return code, log.stdout + "\n" + log.stderr


def _accept_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with sqlite3.connect(path) as db:
        return int(db.execute("SELECT count(*) FROM accepted_proof_transfers").fetchone()[0])


def experiment(subjects: Mapping[str, Path], intent: Path, output: Path) -> dict[str, Any]:
    if not os.environ.get("GH_TOKEN"):
        raise IsolatedHostFailure("recipient must get GH_TOKEN independently from CI")
    gh_source = shutil.which("gh")
    if not gh_source:
        raise IsolatedHostFailure("patched gh verifier must be installed on provisioner")
    gh = Path(gh_source).resolve()
    if not gh.is_file():
        raise IsolatedHostFailure("installed GitHub CLI executable is missing")

    suffix = uuid.uuid4().hex[:10]
    network = "proof-host-network-" + suffix
    image = "ecpu-proof-host:" + suffix
    containers: list[str] = []
    with tempfile.TemporaryDirectory(prefix="proof-separate-hosts-") as root:
        workspace = Path(root)
        provisioned = _provision(workspace, subjects, intent)
        context = _build_context(workspace)
        docker("build", "--pull", "-t", image, str(context), timeout=TIMEOUT)
        docker("network", "create", "--driver", "bridge", network)
        try:
            # Sender has no GH_TOKEN, no proof recipient trust policy, and no
            # recipient TLS private key or SQLite state mount. Receiver has no
            # sender-subject files and no origin TLS private key.
            verifier_check = docker(
                "run", "--rm",
                "--mount", f"type=bind,src={gh},dst=/usr/local/bin/gh,readonly",
                "--entrypoint", "/usr/local/bin/gh", image, "--version",
            )
            if "gh version" not in verifier_check.stdout:
                raise IsolatedHostFailure("isolated receiver cannot run its own patched verifier")
            ledger = provisioned["recipient-state"] / "durable-proof-ledger.sqlite3"
            receipt_path = provisioned["recipient-state"] / "admitted-once.json"
            report_path = provisioned["recipient-state"] / "transport-observation.json"

            # Boundary 1: partial transfer and hard loss of the receiver.
            first = "proof-recipient-fault-" + suffix
            containers.append(first)
            _server(first, network, image, provisioned, gh)
            fail = _sender("proof-origin-partial-" + suffix, network, image,
                           provisioned, gh, fault=True)
            if fail.returncode == 0 or "intentional test-only sender process fault" not in fail.stderr:
                raise IsolatedHostFailure(f"expected incomplete sender fault, got: {fail.stderr[-900:]}")
            docker("kill", first)
            if ledger.exists() or receipt_path.exists():
                raise IsolatedHostFailure("incomplete proof transfer incorrectly committed VGI admission")
            docker("rm", "-f", first)
            containers.remove(first)

            # Boundary 2: restart host process from same recipient-owned volume;
            # retransmit the entire exact proof package from scratch.
            second = "proof-recipient-accept-" + suffix
            containers.append(second)
            _server(second, network, image, provisioned, gh)
            accepted = _sender("proof-origin-retry-" + suffix, network, image,
                               provisioned, gh, fault=False)
            if accepted.returncode or "MAILCPU_PROOF_FRAMES_ACKED:" not in accepted.stdout:
                raise IsolatedHostFailure(f"new TLS sender did not finish ACKed delivery: {accepted.stderr[-1000:]}")
            code, logs = _await_exit(second)
            if code or "MAILCPU_PROOF_RECIPIENT_ACCEPTED:" not in logs:
                raise IsolatedHostFailure(f"recipient did not verify authentic proof: {logs[-1500:]}")
            if _accept_count(ledger) != 1:
                raise IsolatedHostFailure("authenticated recipient did not commit exactly one durable admission")
            term._bind_digest(term._read(receipt_path), "isolated host receiving decision")
            term._bind_digest(term._read(report_path), "isolated host mTLS observation")
            docker("rm", "-f", second)
            containers.remove(second)

            # Boundary 3: restart recipient again, move exactly the same bytes
            # over *new TLS session*, reliable delivery ACKed; semantic replay
            # must fail against the persisted destination-owned ledger.
            third = "proof-recipient-replay-" + suffix
            containers.append(third)
            _server(third, network, image, provisioned, gh)
            redelivery = _sender("proof-origin-replay-" + suffix, network, image,
                                 provisioned, gh, fault=False)
            if redelivery.returncode or "MAILCPU_PROOF_FRAMES_ACKED:" not in redelivery.stdout:
                raise IsolatedHostFailure(f"second transport delivery was not ACKed: {redelivery.stderr[-1000:]}")
            code, logs = _await_exit(third)
            if code == 0 or "replayed receipt" not in logs:
                raise IsolatedHostFailure(f"replayed proof was not specifically rejected: {logs[-1200:]}")
            if _accept_count(ledger) != 1:
                raise IsolatedHostFailure("replay unexpectedly mutated durable receiver state")

            intent_doc = receiver.ReceiverIntent.load(
                provisioned["recipient-state"] / "trusted-intent.json"
            )
            decision = term._read(receipt_path)
            observation = term._read(report_path)
            record = {
                "format": "in-formation.ecpu-virtual-host-recovery/0.1",
                "status": "isolated_virtual_hosts_authenticated_recovery_and_replay_rejection",
                "virtual_hosts": {
                    "origin": "separate Docker network/PID namespace, sender data and origin-only mTLS key",
                    "recipient": "separate Docker network/PID namespace, independently provisioned policy, receiver-only mTLS key and mounted durable ledger",
                    "shared_trust": "ephemeral admin-issued CA public certificate; admin private key never mounted",
                    "runtime": "two containers on one GitHub-hosted machine; NOT physically separate computers",
                },
                "transport": "E-CPU SocketTransport + ReliableChannel on Docker bridge TCP with mutual TLS",
                "test_fault": "incomplete prefix ACKed then receiving container SIGKILL; no VGI ledger/admission written",
                "recovery": "fresh receiver container with same destination volume; whole immutable artifact package retransmitted",
                "authenticated_receipt": decision["receipt_ref"],
                "receiver_decision_digest": decision["document_digest"],
                "transport_observation_digest": observation["document_digest"],
                "issuer_provenance": "recipient independently reverified six GitHub/Sigstore subjects and exact VGI obligation",
                "replay": "second receiver container and new sender TLS session; reliable delivery acknowledged; recipient rejected already admitted proof",
                "destination_durable_admissions": 1,
                "recipient_scope": intent_doc.recipient_scope,
                "source_sha": intent_doc.expected_source_sha,
                "run_id": intent_doc.expected_run_id,
                "limitations": [
                    "Virtual hosts share one physical GitHub runner and a trusted CI admin provisioner",
                    "Test-only ephemeral CA, not production independently administered PKI",
                    "Whole-package retransmission, not durable per-frame checkpoint resume",
                    "SQLite replay detection is local to receiving mounted volume, not global",
                    "Fixed Lean theorem and same trusted GitHub issuer workflow",
                ],
            }
            term._write(output, {**record, "document_digest": term.digest(record)})
            return record
        finally:
            for name in reversed(containers):
                docker("rm", "-f", name, check=False, timeout=35)
            docker("network", "rm", network, check=False, timeout=35)
            docker("image", "rm", "-f", image, check=False, timeout=35)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for kind in receiver.SUBJECTS:
        parser.add_argument("--" + kind.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        subjects = {name: getattr(args, name) for name in receiver.SUBJECTS}
        report = experiment(subjects, args.intent, args.output)
        print("ECPU_ISOLATED_HOST_RECOVERED_AND_REPLAY_REJECTED", flush=True)
    except (ValueError, IsolatedHostFailure, OSError, sqlite3.Error,
            subprocess.SubprocessError) as exc:
        parser.exit(1, f"ECPU_ISOLATED_HOST_REJECTED:{exc}\n")


if __name__ == "__main__":
    main()
