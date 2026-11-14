"""SNC-004B: bounded proof-capsule delivery over real E-CPU ReliableChannel/mTLS.

Communication authenticity is independent of mathematical admission: every
receiver applies its own local source policy, replays the complete COE proof,
and durably commits an observation *before* the final RDATA delivery ACK.
A reverse ReliableChannel returns a distinct application verdict.

Mode "overlay" refuses loopback, public and wildcard addresses. No endpoint
fallback or overlay emulation is hidden in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import ssl
import time
from typing import Any
import secrets

from mailcpu.mtls_transport import accept_mutual_tls, connect_mutual_tls
from mailcpu.reliability import ReliableChannel, ReliabilityPolicy
from mailcpu.socket_transport import SocketTransport

from persistent_host import PersistentSemanticHost, HostRejected, canonical, exact_object, require, sha
from federated_capsule import import_on_host
from semantic_transit import tls_context, SENDER, RECEIVER

SCHEMA = "in-formation-space.snc004b.live-capsule-wire/0.1"
SERVER_REPORT = "in-formation-space.snc004b.receiver-transport-report/0.1"
CLIENT_REPORT = "in-formation-space.snc004b.sender-transport-report/0.1"
RESPONSE_SCHEMA = "in-formation-space.snc004b.application-response/0.1"
DATA_CHANNEL = "snc004b/untrusted-capsule/v1"
RETURN_CHANNEL = "snc004b/independent-admission/v1"
CHUNK = 8192
MAX_BODY = 128 * 1024
MAX_CHUNKS = MAX_BODY // CHUNK
TIMEOUT = 35.0
TICK = 0.05
PORT = 41768
NONCE = re.compile(r"[0-9a-f]{32}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MODEL = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
REQ = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z")


class WireRejected(HostRejected):
    pass


def check(valid: bool, reason: str) -> None:
    if not valid:
        raise WireRejected(reason)


def addressing(host: str, *, overlay: bool) -> str:
    """Never use public or loopback IPs for an overlay-labelled experiment."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise WireRejected("numeric IPv4 endpoint is required") from exc
    check(address.version == 4, "only explicit IPv4 endpoints supported")
    if overlay:
        check(address in ipaddress.ip_network("100.64.0.0/10"),
              "overlay requires a Tailscale 100.64.0.0/10 endpoint")
    else:
        check(address == ipaddress.ip_address("127.0.0.1"),
              "local test must bind/connect only on loopback")
    return str(address)


def certificate_sha256(path: Path) -> str:
    pem = path.read_text(encoding="ascii")
    return sha(ssl.PEM_cert_to_DER_cert(pem))


def channel(transport: SocketTransport, *, serving: bool,
            response: bool) -> ReliableChannel:
    local = RECEIVER if serving else SENDER
    peer = SENDER if serving else RECEIVER
    return ReliableChannel(
        transport, source=local, destination=peer if response == serving else local,
        peer=peer,
        channel=RETURN_CHANNEL if response else DATA_CHANNEL,
        policy=ReliabilityPolicy(lease_ticks=4, max_attempts=7, window_size=4),
    )


def make_frames(raw: bytes, *, model: str, coordinate: str,
                request_id: str, nonce: str) -> tuple[dict[str, object], ...]:
    check(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, "capsule byte budget")
    check(type(model) is str and MODEL.fullmatch(model) is not None, "model identity")
    check(type(coordinate) is str and 0 < len(coordinate) <= 96, "coordinate budget")
    check(type(request_id) is str and REQ.fullmatch(request_id) is not None,
          "request identity")
    check(type(nonce) is str and NONCE.fullmatch(nonce) is not None, "invalid nonce")
    number = (len(raw) + CHUNK - 1) // CHUNK
    manifest = {
        "schema": SCHEMA, "kind": "federated-capsule",
        "model": model, "coordinate": coordinate, "request_id": request_id,
        "nonce": nonce, "byte_length": len(raw),
        "sha256": sha(raw), "chunks": number,
    }
    frames = [{"phase": "begin", "manifest": manifest}]
    frames.extend({
        "phase": "chunk", "index": i, "hex": raw[i * CHUNK:(i + 1) * CHUNK].hex()
    } for i in range(number))
    frames.append({
        "phase": "finish", "manifest_sha256": sha(canonical(manifest)),
    })
    return tuple(frames)


class CapsuleDecoder:
    def __init__(self) -> None:
        self.manifest: dict | None = None
        self.fragments: list[bytes] = []
        self.complete = False
        self.body: bytes | None = None
        self.frames = 0

    def ingest(self, frame: object) -> None:
        check(not self.complete, "frames after finish")
        check(self.frames < MAX_CHUNKS + 2, "frame budget exhausted")
        self.frames += 1
        if self.manifest is None:
            obj = exact_object(frame, {"phase", "manifest"}, "start frame")
            check(obj["phase"] == "begin", "missing begin")
            man = exact_object(obj["manifest"], {
                "schema", "kind", "model", "coordinate", "request_id",
                "nonce", "byte_length", "sha256", "chunks",
            }, "manifest")
            check(man["schema"] == SCHEMA and man["kind"] == "federated-capsule",
                  "unknown capsule route")
            check(type(man["model"]) is str and MODEL.fullmatch(man["model"]) is not None,
                  "invalid model")
            check(type(man["request_id"]) is str and REQ.fullmatch(man["request_id"]) is not None,
                  "invalid request")
            check(type(man["coordinate"]) is str and 0 < len(man["coordinate"]) <= 96,
                  "invalid coordinate")
            check(type(man["nonce"]) is str and NONCE.fullmatch(man["nonce"]) is not None,
                  "invalid nonce")
            check(type(man["byte_length"]) is int and 0 < man["byte_length"] <= MAX_BODY,
                  "unbounded document")
            check(type(man["sha256"]) is str and DIGEST.fullmatch(man["sha256"]) is not None,
                  "invalid document digest")
            check(type(man["chunks"]) is int and
                  man["chunks"] == (man["byte_length"] + CHUNK - 1) // CHUNK,
                  "inconsistent chunk count")
            self.manifest = man
            return

        if len(self.fragments) < self.manifest["chunks"]:
            obj = exact_object(frame, {"phase", "index", "hex"}, "chunk")
            check(obj["phase"] == "chunk" and
                  type(obj["index"]) is int and obj["index"] == len(self.fragments),
                  "out-of-order chunk")
            s = obj["hex"]
            check(type(s) is str and len(s) % 2 == 0 and
                  0 < len(s) <= 2 * CHUNK, "invalid chunk size")
            try:
                fragment = bytes.fromhex(s)
            except ValueError as exc:
                raise WireRejected("invalid chunk encoding") from exc
            check(fragment.hex() == s, "noncanonical hex encoding")
            expected = min(CHUNK, self.manifest["byte_length"] -
                           CHUNK * len(self.fragments))
            check(len(fragment) == expected, "incorrect fragment length")
            self.fragments.append(fragment)
            if len(self.fragments) == self.manifest["chunks"]:
                body = b"".join(self.fragments)
                check(len(body) == self.manifest["byte_length"] and
                      sha(body) == self.manifest["sha256"],
                      "document integrity failure")
                self.body = body
            return

        obj = exact_object(frame, {"phase", "manifest_sha256"}, "terminal frame")
        check(obj["phase"] == "finish" and
              obj["manifest_sha256"] == sha(canonical(self.manifest)),
              "terminal commitment mismatch")
        self.complete = True


def verdict(host: PersistentSemanticHost, *, body: bytes, manifest: dict
            ) -> dict[str, object]:
    """Receiver-owned policy, mathematical certificate, and durable receipt."""
    try:
        imported = import_on_host(host, manifest["model"], body)
        observation = host.observe(
            model=manifest["model"], coordinate=manifest["coordinate"],
            request_id=manifest["request_id"],
        )
        check(observation["construction_ns"] == 0 and
              observation["cache_state"] == "restored-verified",
              "verification did not restore the imported model")
        result = {
            "schema": "in-formation-space.snc004.receiver-report/0.1",
            "model": manifest["model"], "import": imported,
            "observation": observation,
            "origin_document_sha256": sha(body),
            "authority_scope": "receiver-local exact mathematical cache only",
        }
        return {"schema": RESPONSE_SCHEMA, "nonce": manifest["nonce"],
                "accepted": True, "document_sha256": sha(body),
                "request_id": manifest["request_id"],
                "result": result}
    except (HostRejected, WireRejected, ValueError, TypeError) as exc:
        return {"schema": RESPONSE_SCHEMA, "nonce": manifest["nonce"],
                "accepted": False, "document_sha256": sha(body),
                "request_id": manifest["request_id"],
                "reason": str(exc)[:160]}


def peer_sha(transport: SocketTransport) -> str:
    raw = transport.socket.getpeercert(binary_form=True)
    check(type(raw) is bytes and len(raw) > 0, "missing mTLS certificate")
    return sha(raw)


def _wait_ack(ch: ReliableChannel, seq: int, deadline: float) -> None:
    last_tick = time.monotonic()
    while seq in ch.pending_sequences():
        check(time.monotonic() < deadline, "reliable acknowledgement deadline")
        ch.process_ack()
        if seq not in ch.pending_sequences():
            break
        if time.monotonic() - last_tick >= TICK:
            check(seq not in ch.tick(), "reliable delivery attempts exhausted")
            last_tick = time.monotonic()
        time.sleep(.005)


def send(*, address: str, port: int, overlay: bool,
         own_cert: Path, own_key: Path, trusted_server_cert: Path,
         capsule: bytes, model: str, coordinate: str, request_id: str,
         output: Path, nonce: str | None = None) -> dict:
    address = addressing(address, overlay=overlay)
    check(type(port) is int and 1 <= port <= 65535, "invalid TCP port")
    nonce = nonce or secrets.token_hex(16)
    frames = make_frames(capsule, model=model, coordinate=coordinate,
                         request_id=request_id, nonce=nonce)
    tcp = connect_mutual_tls(
        address, port, SENDER, RECEIVER,
        tls_context(trusted_server_cert, own_cert, own_key, server=False),
        server_hostname=RECEIVER, timeout=8.0, max_frame_size=1 << 20,
    )
    try:
        actual = peer_sha(tcp)
        expected = certificate_sha256(trusted_server_cert)
        check(actual == expected, "live server certificate differs from bootstrap pin")
        outbound = channel(tcp, serving=False, response=False)
        inbound = channel(tcp, serving=False, response=True)
        began = time.perf_counter_ns()
        for frame in frames:
            seq = outbound.send(frame)
            _wait_ack(outbound, seq, time.monotonic() + TIMEOUT)
        response = None
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            observed = inbound.receive()
            if observed is not None:
                response = observed[1]
                break
            time.sleep(.005)
        check(type(response) is dict and set(response) == (
            {"schema", "nonce", "accepted", "document_sha256", "request_id", "result"}
            if response and response.get("accepted") is True else
            {"schema", "nonce", "accepted", "document_sha256", "request_id", "reason"}
        ), "missing or malformed application response")
        check(response["schema"] == RESPONSE_SCHEMA and
              response["nonce"] == nonce and
              response["request_id"] == request_id and
              response["document_sha256"] == sha(capsule) and
              type(response["accepted"]) is bool,
              "response identity/nonce does not match sent document")
        if response["accepted"] is True:
            check(response["result"]["origin_document_sha256"] == sha(capsule) and
                  response["result"]["observation"]["receipt"]["request_id"] == request_id,
                  "response not bound to this operation")
        report = {
            "schema": CLIENT_REPORT, "mode": "overlay" if overlay else "local",
            "nonce": nonce, "document_sha256": sha(capsule),
            "bytes_sent_application": len(capsule),
            "sent_frame_count": len(frames),
            "peer_certificate_sha256": actual,
            "local_certificate_sha256": certificate_sha256(own_cert),
            "tls_version": tcp.socket.version(),
            "sender_duration_ns_local": time.perf_counter_ns() - began,
            "response": response,
            "external_execution_authorized": False,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical(report))
        # Keep stream alive after reverse ReliableChannel ACK is sent,
        # allowing receiver process to consume it before TLS close.
        time.sleep(.25)
        return report
    finally:
        tcp.close()


def serve(*, listener: Any, overlay: bool,
          own_cert: Path, own_key: Path, trusted_client_cert: Path,
          database: Path, policy: Path, output: Path) -> dict:
    tcp = accept_mutual_tls(
        listener, RECEIVER, SENDER,
        tls_context(trusted_client_cert, own_cert, own_key, server=True),
        expected_peer_dns=SENDER, max_frame_size=1 << 20,
    )
    decoder = CapsuleDecoder()
    application = None
    try:
        actual = peer_sha(tcp)
        expected = certificate_sha256(trusted_client_cert)
        check(actual == expected, "live client certificate differs from bootstrap pin")
        inbound = channel(tcp, serving=True, response=False)
        outbound = channel(tcp, serving=True, response=True)
        host = PersistentSemanticHost(database, policy)
        began = time.perf_counter_ns()

        def commit(_sequence: int, frame: object) -> None:
            nonlocal application
            decoder.ingest(frame)
            if decoder.complete:
                check(decoder.body is not None and decoder.manifest is not None,
                      "incomplete capsule")
                # This completes inside the ReliableChannel commit callback,
                # before the final RDATA ACK is emitted.
                application = verdict(host, body=decoder.body,
                                      manifest=decoder.manifest)
                if application["accepted"]:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(canonical({
                        "schema": SERVER_REPORT,
                        "mode": "overlay" if overlay else "local",
                        "nonce": decoder.manifest["nonce"],
                        "document_sha256": sha(decoder.body),
                        "bytes_received_application": len(decoder.body),
                        "received_frame_count": decoder.frames,
                        "peer_certificate_sha256": actual,
                        "local_certificate_sha256": certificate_sha256(own_cert),
                        "tls_version": tcp.socket.version(),
                        "result": application["result"],
                        "receiver_duration_ns_local": time.perf_counter_ns() - began,
                        "report_durable_before_final_ack": True,
                        "external_execution_authorized": False,
                    }))

        deadline = time.monotonic() + TIMEOUT
        while not decoder.complete:
            check(time.monotonic() < deadline, "incomplete capsule timeout")
            frame = inbound.receive(commit=commit)
            if frame is None:
                time.sleep(.005)
        check(application is not None, "missing admission decision")
        seq = outbound.send(application)
        _wait_ack(outbound, seq, time.monotonic() + TIMEOUT)
        return application
    finally:
        tcp.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--bind", required=True)
    server.add_argument("--port", type=int, default=PORT)
    server.add_argument("--database", type=Path, required=True)
    server.add_argument("--policy", type=Path, required=True)
    server.add_argument("--output", type=Path, required=True)
    client = sub.add_parser("send")
    client.add_argument("--connect", required=True)
    client.add_argument("--port", type=int, default=PORT)
    client.add_argument("--capsule", type=Path, required=True)
    client.add_argument("--model", default="clamp")
    client.add_argument("--coordinate", default="3/4")
    client.add_argument("--request-id", default="snc004b-observation")
    client.add_argument("--output", type=Path, required=True)
    for command in (server, client):
        command.add_argument("--overlay", action="store_true")
        command.add_argument("--cert", type=Path, required=True)
        command.add_argument("--key", type=Path, required=True)
        command.add_argument("--peer-cert", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            address = addressing(args.bind, overlay=args.overlay)
            check(type(args.port) is int and 0 <= args.port <= 65535,
                  "invalid port")
            check(not args.overlay or args.port == PORT,
                  "overlay listener must use dedicated SNC-004B port")
            listener = SocketTransport.listen(address, args.port)
            listener.settimeout(TIMEOUT)
            try:
                print("LISTEN_PORT=" + str(listener.getsockname()[1]), flush=True)
                result = serve(
                    listener=listener, overlay=args.overlay,
                    own_cert=args.cert, own_key=args.key,
                    trusted_client_cert=args.peer_cert,
                    database=args.database, policy=args.policy, output=args.output)
                print(json.dumps({"accepted": result["accepted"],
                                  "nonce": result["nonce"]}), flush=True)
            finally:
                listener.close()
        else:
            result = send(
                address=args.connect, port=args.port,
                overlay=args.overlay, own_cert=args.cert, own_key=args.key,
                trusted_server_cert=args.peer_cert,
                capsule=args.capsule.read_bytes(),
                model=args.model, coordinate=args.coordinate,
                request_id=args.request_id, output=args.output,
            )
            print(json.dumps({"accepted": result["response"]["accepted"],
                              "document_sha256": result["document_sha256"],
                              "nonce": result["nonce"]}), flush=True)
            check(result["response"]["accepted"],
                  "receiver denied exact mathematical admission")
    except (OSError, ssl.SSLError, HostRejected, RuntimeError, ValueError) as exc:
        parser.exit(1, "SNC004B_REJECTED:" + str(exc)[:350] + "\n")


if __name__ == "__main__":
    main()
