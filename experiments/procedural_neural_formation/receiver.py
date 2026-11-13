"""Separate PNF-002 receiver: bounded capsule assembly over E-CPU mutual TLS."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import ssl
import time

from mailcpu import ReliabilityPolicy, ReliableChannel, SocketTransport
from mailcpu.mtls_transport import accept_mutual_tls

from .capsule import MAX_CAPSULE, canonical, sha, verify_capsule
from .formation import FormationError

SENDER = "pnf-source"
RECEIVER = "pnf-receiver"
SOURCE_DNS = "source.pnf.test"
RECEIVER_DNS = "receiver.pnf.test"
REQUEST = "ifs.pnf.portable.request.v1"
RESPONSE = "ifs.pnf.portable.response.v1"
CHUNK = 64 * 1024
FRAME = 256 * 1024


def implementation_digest() -> str:
    root = Path(__file__).parent
    return sha(b"".join(name.encode() + b"\x00" + (root / name).read_bytes()
                       for name in ("capsule.py", "formation.py", "verification.py", "receiver.py")))


class Assembly:
    """One externally pinned request; transport ACK means volatile staging only."""
    def __init__(self, policy: dict, request_id: str):
        if type(policy.get("capsule_bytes")) is not int or not 0 < policy["capsule_bytes"] <= MAX_CAPSULE:
            raise FormationError("invalid transfer byte budget")
        self.policy = policy
        self.request_id = request_id
        self.buffer = bytearray()
        self.next_index = 0
        self.finished = False
        self.report = None

    def accept(self, sequence: int, payload: dict) -> None:
        if self.finished or not isinstance(payload, dict) or payload.get("request_id") != self.request_id:
            raise FormationError("unexpected or repeated transfer request")
        if payload.get("kind") == "chunk":
            if set(payload) != {"request_id", "kind", "index", "data"}:
                raise FormationError("invalid chunk fields")
            index, encoded = payload["index"], payload["data"]
            if type(index) is not int or index != self.next_index or sequence != index + 1:
                raise FormationError("chunk order mismatch")
            if not isinstance(encoded, str) or len(encoded) > 4 * ((CHUNK + 2) // 3):
                raise FormationError("chunk encoded size exceeded")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise FormationError("invalid chunk encoding") from exc
            expected = min(CHUNK, self.policy["capsule_bytes"] - len(self.buffer))
            if len(raw) != expected or expected <= 0:
                raise FormationError("chunk byte count mismatch")
            self.buffer.extend(raw)
            self.next_index += 1
        elif payload.get("kind") == "verify":
            if set(payload) != {"request_id", "kind"} or sequence != self.next_index + 1:
                raise FormationError("invalid completion frame")
            if len(self.buffer) != self.policy["capsule_bytes"]:
                raise FormationError("incomplete capsule")
            self.finished = True
            try:
                self.report = verify_capsule(bytes(self.buffer), self.policy)
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                self.report = {"status": "rejected", "reason": f"{type(exc).__name__}: {exc}"}
        else:
            raise FormationError("unsupported transfer frame")


def serve(config: dict, ready_path: Path) -> None:
    assembly = Assembly(config["policy"], config["request_id"])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(config["certificate"], config["private_key"])
    context.load_verify_locations(cafile=config["ca"])
    listener = SocketTransport.open_listener("127.0.0.1", 0)
    listener.settimeout(20)
    transport = None
    try:
        ready_path.write_bytes(canonical({"port": listener.getsockname()[1], "pid": os.getpid(),
                                         "implementation_digest": implementation_digest()}))
        transport = accept_mutual_tls(listener, RECEIVER, SENDER, context, expected_peer_dns=SOURCE_DNS,
                                     max_frame_size=FRAME, send_timeout=10)
        actual_pin = sha(transport.socket.getpeercert(binary_form=True))
        if actual_pin != config["source_certificate_sha256"]:
            raise FormationError("source certificate pin mismatch")
        reliability = ReliabilityPolicy(window_size=1, lease_ticks=1000, max_attempts=3)
        incoming = ReliableChannel(transport, RECEIVER, RECEIVER, REQUEST, reliability, peer=SENDER)
        outgoing = ReliableChannel(transport, RECEIVER, SENDER, RESPONSE, reliability, peer=SENDER)
        deadline = time.monotonic() + 180
        while not assembly.finished and time.monotonic() < deadline:
            if incoming.receive(commit=assembly.accept) is None:
                time.sleep(0.001)
        if not assembly.finished:
            raise TimeoutError("capsule transfer did not complete")
        response = {"request_id": config["request_id"], "capsule_sha256": config["policy"]["capsule_sha256"],
                    "receiver_pid": os.getpid(), "implementation_digest": implementation_digest(),
                    "source_certificate_sha256": actual_pin, "chunks": assembly.next_index,
                    "report": assembly.report}
        outgoing.send(response)
        deadline = time.monotonic() + 15
        while outgoing.pending_sequences() and time.monotonic() < deadline:
            outgoing.process_ack()
            time.sleep(0.001)
        if outgoing.pending_sequences():
            raise TimeoutError("verification response was not acknowledged")
    finally:
        if transport is not None:
            transport.close()
        listener.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    args = parser.parse_args()
    serve(json.loads(args.config.read_text(encoding="utf-8")), args.ready)
