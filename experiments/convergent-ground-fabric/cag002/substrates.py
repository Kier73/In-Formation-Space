#!/usr/bin/env python3
"""CAG-002: real JetStream + libp2p route diversity, bounded independent replay.

Both transports run on the same CI host. JetStream is a durable network
broker, libp2p is an encrypted peer stream. The final observer is local
until a distinct GitHub verifier job replays the retained route records.
Neither transport's ACK grants application/Hypervisor authority.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import convergent_fabric as cag

SCHEMA = "in-formation.cag002-dual-substrate/0.1"
REPORT_SCHEMA = "in-formation.cag002-reconstruction/0.1"


class SubstrateError(ValueError):
    pass


def require(ok: bool, why: str) -> None:
    if not ok:
        raise SubstrateError(why)


def route_packets() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source = cag.source_bundle()
    return source, cag.route_bundle(source, "blue"), cag.route_bundle(source, "amber")


def record_bytes(path: Path, docs: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(cag.canonical(doc) + b"\n" for doc in docs))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    content = path.read_bytes()
    require(content.endswith(b"\n") and len(content) <= 80_000, "unbounded or truncated route spool")
    lines = content.splitlines()
    docs = [json.loads(item) for item in lines]
    require(1 <= len(docs) <= 30 and all(isinstance(p, dict) for p in docs),
            "malformed route spool")
    require(all(cag.canonical(doc) == line for doc, line in zip(docs, lines)),
            "route spool is not canonical JSONL")
    return docs


def validate_arrivals(docs: list[Mapping[str, Any]], expected: list[dict[str, Any]],
                      label: str) -> tuple[dict[str, Any], ...]:
    expected_digests = {p["digest"] for p in expected}
    seen: set[str] = set()
    out = []
    for raw in docs:
        packet = cag.validate(raw)
        require(packet["digest"] in expected_digests and packet in expected,
                f"{label}: delivered packet is absent from authorized source projection")
        seen.add(packet["digest"])
        out.append(packet)
    require(seen == expected_digests,
            f"{label}: route delivery incomplete; missing {sorted(expected_digests-seen)}")
    return tuple(out)


def reconstruct(source: Mapping[str, Any], blue: Mapping[str, Any],
                amber: Mapping[str, Any], trace: Mapping[str, Any],
                blue_docs: list[Mapping[str, Any]],
                amber_docs: list[Mapping[str, Any]]) -> dict[str, Any]:
    cag.check_source(source)
    expected_blue = cag.check_route(blue, source, "blue")
    expected_amber = cag.check_route(amber, source, "amber")
    blue_actual = validate_arrivals(blue_docs, expected_blue, "jetstream")
    amber_actual = validate_arrivals(amber_docs, expected_amber, "libp2p")
    require(trace.get("schema") == SCHEMA and trace.get("source_digest") == source["bundle_digest"],
            "transport trace is not bound to the source")
    require(trace.get("blue_digest") == blue["bundle_digest"]
            and trace.get("amber_digest") == amber["bundle_digest"], "wrong route digest")
    jet = trace.get("jetstream", {})
    p2p = trace.get("libp2p", {})
    require(isinstance(jet, dict) and isinstance(p2p, dict), "missing transport evidence")
    require(jet.get("server") == "nats-server JetStream" and jet.get("file_storage") is True,
            "JetStream file-backed stream was not observed")
    require(jet.get("producer_disconnected_before_consumer") is True
            and jet.get("durable_consumer_reconnected") is True
            and jet.get("redelivery_after_missing_ack") is True
            and jet.get("acknowledged_count", 0) >= len(expected_blue),
            "JetStream durability/redelivery controls failed")
    require(p2p.get("protocol") == "/cag002/ground-packet/1.0.0"
            and p2p.get("listener_restarted") is True
            and p2p.get("peer_id_rotated") is True
            and p2p.get("lost_transport_ack_retried") is True
            and p2p.get("persisted_duplicate_seen") is True,
            "libp2p reconnect/ACK-loss controls failed")
    require(len(blue_actual) > len({p["digest"] for p in blue_actual})
            and len(amber_actual) > len({p["digest"] for p in amber_actual}),
            "expected duplicate deliveries not present")

    reference = cag.Replica()
    for p in cag.check_source(source).values():
        reference.ingest(p, route="source")
    expected = reference.evaluate(source["target"])
    require(expected["status"] == "locally_reconstructed_pure_result", "source Ground incomplete")

    cases = []
    for order in (("jetstream", "libp2p"), ("libp2p", "jetstream")):
        replica = cag.Replica()
        partial = []
        for route in order:
            docs = blue_actual if route == "jetstream" else amber_actual
            for p in docs:
                replica.ingest(p, route=route)
            partial.append(replica.evaluate(source["target"])["status"])
        result = replica.evaluate(source["target"])
        require(result == expected and partial[0] == "unknown_dependency",
                f"nonconvergent or prematurely completed route order: {order}")
        cases.append({
            "route_order": list(order),
            "status_after_route": partial,
            "final": result,
            "unique_packet_count": len(replica.inventory()),
        })
    require(len({p["digest"] for p in list(blue_actual) + list(amber_actual)}) == len(cag.fixture()),
            "combined transports did not carry the complete source")
    core = {
        "schema": REPORT_SCHEMA,
        "status": "two_real_substrates_local_reconstruction",
        "source_digest": source["bundle_digest"],
        "route_digests": {"jetstream": blue["bundle_digest"], "libp2p": amber["bundle_digest"]},
        "captured_route_files_sha256": {
            "jetstream": hashlib.sha256(b"".join(cag.canonical(p) + b"\n" for p in blue_actual)).hexdigest(),
            "libp2p": hashlib.sha256(b"".join(cag.canonical(p) + b"\n" for p in amber_actual)).hexdigest(),
        },
        "transport_evidence": dict(trace),
        "reference": expected,
        "cases": cases,
        "limitations": [
            "JetStream and libp2p use distinct actual network implementations on one GitHub-hosted runner, not independent provider networks.",
            "The JetStream publisher and consumer ran at distinct times against the same broker; broker persistence survived client restart, not demonstrated broker disk/crash recovery.",
            "The libp2p listener was restarted with a changed ephemeral peer ID; peer connection encryption does not establish application role authorization.",
            "A transport ACK only confirms an endpoint write. An exact arithmetic result is not a trusted E-CPU operator receipt or VGI proof.",
            "The independent hosted verifier authenticates recorded workflow artifacts, but the observation trace itself is supplied by one CI integration host.",
            "Pure finite arithmetic has no arbitrary external side effects; no exactly-once side-effect claim is made.",
        ],
    }
    return {**core, "report_digest": cag.sha(core)}


async def run_jetstream(workdir: Path, blue: dict[str, Any],
                        server_url: str) -> dict[str, Any]:
    import nats
    from nats.js.api import ConsumerConfig, StorageType
    from nats.js.errors import FetchTimeoutError

    # Publish while no receiving client is connected; close the producer.
    producer = await nats.connect(servers=[server_url], connect_timeout=3, max_reconnect_attempts=2)
    js = producer.jetstream()
    await js.add_stream(name="CAG002", subjects=["cag002.blue"],
                        storage=StorageType.FILE, max_msgs=100)
    for p in blue["packets"]:
        await js.publish("cag002.blue", cag.canonical(p))
    await producer.drain()

    receiver = await nats.connect(servers=[server_url], connect_timeout=3, max_reconnect_attempts=2)
    js = receiver.jetstream()
    subscription = await js.pull_subscribe("cag002.blue", durable="cag002-durable",
                                            stream="CAG002",
                                            config=ConsumerConfig(ack_wait=1.0, max_deliver=8))
    first = (await subscription.fetch(1, timeout=4))[0]
    # A valid first arrival is deliberately not acknowledged. The durable
    # consumer must redeliver to the replacement client after ack_wait.
    first_digest = cag.validate(json.loads(first.data))["digest"]
    await receiver.close()
    await asyncio.sleep(1.5)

    replacement = await nats.connect(servers=[server_url], connect_timeout=3, max_reconnect_attempts=2)
    repl_sub = await replacement.jetstream().pull_subscribe(
        "cag002.blue", durable="cag002-durable", stream="CAG002",
        config=ConsumerConfig(ack_wait=1.0, max_deliver=8))
    deliveries: list[dict[str, Any]] = [json.loads(first.data)]
    redelivered = False
    acknowledgments = 0
    deadline = time.monotonic() + 22
    while time.monotonic() < deadline:
        try:
            msgs = await repl_sub.fetch(1, timeout=3)
        except FetchTimeoutError:
            if redelivered and acknowledgments >= len(blue["packets"]):
                break
            continue
        for msg in msgs:
            doc = json.loads(msg.data)
            cag.validate(doc)
            deliveries.append(doc)
            metadata = msg.metadata
            if doc["digest"] == first_digest and metadata is not None and metadata.num_delivered > 1:
                redelivered = True
            await msg.ack()
            acknowledgments += 1
        if redelivered and acknowledgments >= len(blue["packets"]):
            break
    await replacement.drain()
    require(redelivered and acknowledgments >= len(blue["packets"]),
            "no durable JetStream redelivery after missing acknowledgment")
    record_bytes(workdir / "jetstream-arrivals.jsonl", deliveries)
    return {
        "server": "nats-server JetStream",
        "file_storage": True,
        "producer_disconnected_before_consumer": True,
        "durable_consumer_reconnected": True,
        "redelivery_after_missing_ack": redelivered,
        "acknowledged_count": acknowledgments,
        "route_packets_received": len(deliveries),
        "transport": "NATS JetStream persistent stream and explicit ACK",
    }


def start_peer(binary: Path, workdir: Path, *, drop_first_ack: bool) -> tuple[subprocess.Popen[Any], Any]:
    log = open(workdir / "libp2p-listener.log", "ab")
    addr = workdir / "libp2p.addr"
    addr.unlink(missing_ok=True)
    cmd = [str(binary), "-mode=serve", "-spool="+str(workdir / "libp2p-spool.jsonl"),
           "-address-file="+str(addr)]
    if drop_first_ack:
        cmd.append("-drop-first-ack")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 18
    while time.monotonic() < deadline:
        if addr.exists() and "/ip4/127.0.0.1/tcp/" in addr.read_text() and "/p2p/" in addr.read_text():
            return proc, log
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    proc.kill()
    proc.wait(timeout=4)
    log.close()
    raise SubstrateError("libp2p listener did not become ready")


def stop_peer(proc: subprocess.Popen[Any], log: Any) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    log.close()
    require(proc.returncode == 0, "libp2p listener failed on controlled stop")


def send_peer(binary: Path, workdir: Path, item: Mapping[str, Any], *, expect_ack: bool) -> None:
    p = workdir / "packet-to-send.json"
    cag.write(p, item)
    result = subprocess.run(
        [str(binary), "-mode=send",
         "-address-file="+str(workdir / "libp2p.addr"),
         "-packet-file="+str(p)],
        capture_output=True, text=True, timeout=22, check=False)
    require((result.returncode == 0) == expect_ack,
            "libp2p sender ACK result differs from fault-injection expectation")


def run_libp2p(binary: Path, workdir: Path, amber: Mapping[str, Any]) -> dict[str, Any]:
    docs = amber["packets"]
    proc, log = start_peer(binary, workdir, drop_first_ack=True)
    try:
        first_peer = (workdir / "libp2p.addr").read_text().strip()
        send_peer(binary, workdir, docs[0], expect_ack=False)
        send_peer(binary, workdir, docs[0], expect_ack=True)
        send_peer(binary, workdir, docs[1], expect_ack=True)
    finally:
        stop_peer(proc, log)
    pre = read_jsonl(workdir / "libp2p-spool.jsonl")
    require(len(pre) == 3 and pre[0] == pre[1], "missing durable duplicate after ACK loss")
    proc, log = start_peer(binary, workdir, drop_first_ack=False)
    try:
        new_peer = (workdir / "libp2p.addr").read_text().strip()
        require(new_peer != first_peer, "fresh libp2p listener did not change ephemeral peer identity")
        send_peer(binary, workdir, docs[2], expect_ack=True)
        send_peer(binary, workdir, docs[2], expect_ack=True)
    finally:
        stop_peer(proc, log)
    after = read_jsonl(workdir / "libp2p-spool.jsonl")
    require(len(after) == 5 and after[3] == after[4], "libp2p durable spool did not survive restart")
    # Do not include peer address strings in public evidence; the local
    # identities rotate and are not stable application authorization.
    return {
        "protocol": "/cag002/ground-packet/1.0.0",
        "listener_restarted": True,
        "peer_id_rotated": first_peer != new_peer,
        "lost_transport_ack_retried": True,
        "persisted_duplicate_seen": True,
        "route_packets_received": len(after),
        "transport": "encrypted go-libp2p streams",
    }


def run_hosted(workdir: Path, p2p_binary: Path, nats_url: str) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    source, blue, amber = route_packets()
    for name, doc in (("source", source), ("blue-route", blue), ("amber-route", amber)):
        cag.write(workdir / (name + ".json"), doc)
    jet = asyncio.run(run_jetstream(workdir, blue, nats_url))
    p2p = run_libp2p(p2p_binary, workdir, amber)
    trace = {
        "schema": SCHEMA,
        "source_digest": source["bundle_digest"],
        "blue_digest": blue["bundle_digest"],
        "amber_digest": amber["bundle_digest"],
        "jetstream": jet,
        "libp2p": p2p,
    }
    cag.write(workdir / "transport-trace.json", trace)
    report = reconstruct(source, blue, amber, trace,
                         read_jsonl(workdir / "jetstream-arrivals.jsonl"),
                         read_jsonl(workdir / "libp2p-spool.jsonl"))
    cag.write(workdir / "report.json", report)
    return report


def offline_verify(workdir: Path) -> dict[str, Any]:
    trace = cag.read(workdir / "transport-trace.json")
    report = reconstruct(cag.read(workdir / "source.json"),
                         cag.read(workdir / "blue-route.json"),
                         cag.read(workdir / "amber-route.json"),
                         trace,
                         read_jsonl(workdir / "jetstream-arrivals.jsonl"),
                         read_jsonl(workdir / "libp2p-spool.jsonl"))
    original = cag.read(workdir / "report.json")
    require(report == original, "independent verifier reconstructed different report")
    return report


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("command", choices=["run", "verify"])
    cli.add_argument("--directory", type=Path, required=True)
    cli.add_argument("--p2p-binary", type=Path)
    cli.add_argument("--nats-url", default="nats://127.0.0.1:4222")
    args = cli.parse_args()
    try:
        if args.command == "run":
            require(args.p2p_binary is not None, "p2p binary path is required for live run")
            report = run_hosted(args.directory, args.p2p_binary.resolve(), args.nats_url)
        else:
            report = offline_verify(args.directory)
        print(json.dumps({"status": report["status"], "result": report["reference"]["value"],
                          "report_digest": report["report_digest"]}, sort_keys=True))
    except (cag.ConvergenceError, SubstrateError, OSError, ValueError) as err:
        cli.exit(1, f"CAG-002 failed closed: {err}\n")


if __name__ == "__main__":
    main()
