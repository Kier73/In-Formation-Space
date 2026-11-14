"""TCR-002: receiver-resident tensor-cut worker over E-CPU ReliableChannel/mTLS.

Warm requests carry only a typed activation and an immutable cut reference; the
receiver checks its independently provisioned shard before numerical execution.
This is an application-level tensor service on E-CPU transport, not the generic
TransitComputeWorker/VirtualLayer authority implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import time

import numpy as np

from . import tensor_cut as tcr

REQUEST = "ifs.tcr002.tensor-request.v1"
RESPONSE = "ifs.tcr002.tensor-response.v1"
ORIGIN = "tcr002-origin"
DATA = "tcr002-tensor-request"
RETURN = "tcr002-tensor-verdict"
MAX_REQUEST = 100_000
MAX_RESPONSE = 100_000
TIMEOUT = 20.0
NAME = re.compile(r"tcr002-worker-[0-9]{1,2}\Z")
RID = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class TransitTensorError(tcr.TensorCutError):
    """Bad request, policy, transport, or response evidence."""


def require(value: bool, reason: str) -> None:
    if not value:
        raise TransitTensorError(reason)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False).encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def exactly(raw: object, expected: set[str], label: str) -> dict:
    require(type(raw) is dict and set(raw) == expected, "malformed " + label)
    return raw


def worker_name(index: int) -> str:
    return f"tcr002-worker-{index}"


def check_input(request: object, manifest: dict, index: int) -> tuple[np.ndarray, str]:
    obj = exactly(request, {"schema", "request_id", "manifest_digest", "partition_id",
                            "input_digest", "input_hex"}, "request")
    require(len(canonical(obj)) <= MAX_REQUEST, "request byte budget")
    require(obj["schema"] == REQUEST and obj["manifest_digest"] == manifest["digest"],
            "receiver source/cut identity denied")
    require(type(obj["partition_id"]) is int and obj["partition_id"] == index,
            "receiver partition policy denied")
    require(type(obj["request_id"]) is str and RID.fullmatch(obj["request_id"]) is not None,
            "request identity denied")
    require(type(obj["input_digest"]) is str and DIGEST.fullmatch(obj["input_digest"]) is not None,
            "input digest malformed")
    raw_hex = obj["input_hex"]
    expected_bytes = manifest["probe_count"] * manifest["input_dim"] * 8
    require(type(raw_hex) is str and len(raw_hex) == 2 * expected_bytes and
            len(raw_hex) <= MAX_REQUEST, "input byte budget/shape mismatch")
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError as exc:
        raise TransitTensorError("invalid input hex") from exc
    require(raw.hex() == raw_hex, "noncanonical input encoding")
    array = np.frombuffer(raw, dtype="<f8").reshape(manifest["probe_count"], manifest["input_dim"])
    require(bool(np.isfinite(array).all()) and tcr._typed_digest(array) == obj["input_digest"] and
            obj["input_digest"] == manifest["input_digest"], "receiver input policy denied")
    return array, sha(canonical(obj))


def request_for(manifest: dict, index: int, inputs: np.ndarray, *, request_id: str) -> dict:
    require(inputs.dtype == np.float64 and inputs.shape ==
            (manifest["probe_count"], manifest["input_dim"]), "source activation shape")
    return {"schema": REQUEST, "request_id": request_id,
            "manifest_digest": manifest["digest"], "partition_id": index,
            "input_digest": tcr._typed_digest(inputs),
            "input_hex": np.ascontiguousarray(inputs, dtype="<f8").tobytes().hex()}


class ResidentShard:
    """One receiver-local partition; admission never trusts sender-supplied weights."""

    def __init__(self, packet: Path):
        self.manifest = tcr._validated_manifest(tcr._read_json(packet / "manifest.json"))
        assignment = tcr._read_json(packet / "assignment.json")
        index = assignment.get("partition_id")
        require(type(index) is int and 0 <= index < len(self.manifest["partitions"]) and
                assignment == {"partition_id": index, "manifest_digest": self.manifest["digest"]},
                "receiver assignment mismatch")
        part = self.manifest["partitions"][index]
        with np.load(packet / "shard.npz", allow_pickle=False) as src:
            require(set(src.files) == {"up_weight", "up_bias", "down_weight", "inputs"},
                    "unexpected local shard members")
            self.up, self.ub, self.down, x = (src[k] for k in
                ("up_weight", "up_bias", "down_weight", "inputs"))
        width = part["stop"] - part["start"]
        require(self.up.dtype == np.float32 and self.ub.dtype == np.float32 and
                self.down.dtype == np.float32 and x.dtype == np.float64,
                "receiver local tensor dtype")
        require(self.up.shape == (self.manifest["input_dim"], width) and
                self.ub.shape == (width,) and self.down.shape == (width, self.manifest["output_dim"]) and
                x.shape == (self.manifest["probe_count"], self.manifest["input_dim"]),
                "receiver local tensor shape")
        require(all(tcr._typed_digest(arr) == part["tensor_digests"][key]
                    for key, arr in (("up_weight", self.up), ("up_bias", self.ub),
                                     ("down_weight", self.down))) and
                tcr._typed_digest(x) == self.manifest["input_digest"],
                "receiver local tensor identity")
        self.index = index
        self.replies: dict[str, tuple[str, dict]] = {}
        self.executions = 0

    def handle(self, request: object) -> dict:
        rid = request.get("request_id", "") if type(request) is dict else ""
        if type(rid) is not str or len(rid) > 80:
            rid = ""
        started = time.perf_counter_ns()
        try:
            x, request_sha = check_input(request, self.manifest, self.index)
            seen = self.replies.get(rid)
            if seen is not None:
                require(seen[0] == request_sha, "conflicting request ID")
                return {**seen[1], "replayed": True, "receiver_compute_ns_local": 0}
            partial = tcr._activation(
                x @ self.up.astype(np.float64) + self.ub.astype(np.float64),
                self.manifest["activation"]) @ self.down.astype(np.float64)
            require(bool(np.isfinite(partial).all()), "nonfinite output")
            part = self.manifest["partitions"][self.index]
            receipt = {"schema": tcr.RECEIPT_SCHEMA, "manifest_digest": self.manifest["digest"],
                "source_digest": self.manifest["source_digest"],
                "input_digest": self.manifest["input_digest"],
                "partition_id": self.index, "partition_tensor_digests": part["tensor_digests"],
                "output_digest": tcr._typed_digest(partial), "output_shape": list(partial.shape),
                "arithmetic": self.manifest["arithmetic"], "status": "complete",
                "worker_trust": "unsigned artifact; no hardware or transport attestation"}
            answer = {"schema": RESPONSE, "request_id": rid, "accepted": True,
                      "worker_id": worker_name(self.index), "request_sha256": request_sha,
                      "receipt": receipt, "partial_hex":
                      np.ascontiguousarray(partial, dtype="<f8").tobytes().hex(),
                      "replayed": False,
                      "receiver_compute_ns_local": time.perf_counter_ns() - started}
            require(len(canonical(answer)) <= MAX_RESPONSE, "response budget")
            self.replies[rid] = (request_sha, answer)
            self.executions += 1
            return answer
        except (TransitTensorError, tcr.TensorCutError, ValueError, TypeError) as exc:
            return {"schema": RESPONSE, "request_id": rid, "accepted": False,
                    "worker_id": worker_name(self.index), "reason": str(exc)[:160]}


def accept_response(request: dict, response: object, manifest: dict,
                    output_dir: Path) -> dict:
    require(type(response) is dict and len(canonical(response)) <= MAX_RESPONSE,
            "response budget")
    require(response.get("schema") == RESPONSE and response.get("request_id") == request["request_id"]
            and response.get("worker_id") == worker_name(request["partition_id"]),
            "response identity mismatch")
    require(response.get("accepted") is True, "receiver denied tensor operation")
    expected = {"schema", "request_id", "accepted", "worker_id", "request_sha256",
                "receipt", "partial_hex", "replayed", "receiver_compute_ns_local"}
    exactly(response, expected, "success response")
    require(response["request_sha256"] == sha(canonical(request)) and
            type(response["receiver_compute_ns_local"]) is int and
            response["receiver_compute_ns_local"] >= 0 and
            type(response["replayed"]) is bool, "unbound receiver response")
    raw = response["partial_hex"]
    expected_length = 8 * manifest["probe_count"] * manifest["output_dim"]
    require(type(raw) is str and len(raw) == expected_length * 2, "partial byte extent")
    try:
        data = bytes.fromhex(raw)
    except ValueError as exc:
        raise TransitTensorError("invalid partial encoding") from exc
    require(data.hex() == raw, "noncanonical partial encoding")
    partial = np.frombuffer(data, dtype="<f8").reshape(manifest["probe_count"], manifest["output_dim"])
    require(bool(np.isfinite(partial).all()) and
            response["receipt"].get("output_digest") == tcr._typed_digest(partial),
            "corrupt partial receipt")
    index = request["partition_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    tcr._write_json(output_dir / f"receipt-{index}.json", response["receipt"])
    np.save(output_dir / f"partial-{index}.npy", partial, allow_pickle=False)
    # The existing TCR-001 validator applies all immutable partition/receipt checks.
    tcr._accept(manifest, output_dir, index)
    return {"worker": response["worker_id"], "replayed": response["replayed"],
            "receiver_compute_ns_local": response["receiver_compute_ns_local"],
            "application_request_bytes": len(canonical(request)),
            "application_response_bytes": len(canonical(response))}


def ssl_context(ca: Path, cert: Path, key: Path, *, server: bool) -> ssl.SSLContext:
    if server:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_verify_locations(cafile=str(ca))
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return ctx


def channels(transport, *, index: int, serving: bool):
    from mailcpu.reliability import ReliableChannel, ReliabilityPolicy
    local = worker_name(index) if serving else ORIGIN
    peer = ORIGIN if serving else worker_name(index)
    policy = ReliabilityPolicy(lease_ticks=4, max_attempts=7, window_size=2)
    tx = ReliableChannel(transport, source=local, destination=peer, peer=peer,
                         channel=RETURN if serving else DATA, policy=policy)
    rx = ReliableChannel(transport, source=local, destination=local, peer=peer,
                         channel=DATA if serving else RETURN, policy=policy)
    return tx, rx


def wait_ack(channel, sequence: int, until: float) -> None:
    last_tick = time.monotonic()
    while time.monotonic() < until:
        channel.process_ack()
        if sequence not in channel.pending_sequences():
            return
        if time.monotonic() - last_tick > .1:
            require(sequence not in channel.tick(), "reliable delivery retries exhausted")
            last_tick = time.monotonic()
        time.sleep(.005)
    raise TransitTensorError("delivery acknowledgement deadline")


def send(host: str, port: int, index: int, request: dict,
         ca: Path, cert: Path, key: Path) -> tuple[dict, dict]:
    from mailcpu.mtls_transport import connect_mutual_tls
    tls = connect_mutual_tls(host, port, ORIGIN, worker_name(index),
                             ssl_context(ca, cert, key, server=False),
                             server_hostname=worker_name(index), timeout=8.0,
                             max_frame_size=1 << 20)
    try:
        tx, rx = channels(tls, index=index, serving=False)
        start = time.perf_counter_ns()
        sequence = tx.send(request)
        deadline = time.monotonic() + TIMEOUT
        last_tick = time.monotonic()
        answer = None
        while time.monotonic() < deadline:
            tx.process_ack()
            if sequence not in tx.pending_sequences():
                received = rx.receive()
                if received is not None:
                    answer = received[1]
                    break
            if time.monotonic() - last_tick > .1:
                require(sequence not in tx.tick(), "request retransmission exhausted")
                last_tick = time.monotonic()
            time.sleep(.005)
        require(answer is not None, "missing application response")
        local_elapsed = time.perf_counter_ns() - start
        # Allow the server time to observe the return-channel RACK before closing.
        time.sleep(.2)
        return answer, {"client_roundtrip_ns_local": local_elapsed, "tls_version": tls.socket.version()}
    finally:
        tls.close()


def serve_one(listener, resident: ResidentShard, ca: Path, cert: Path, key: Path) -> dict:
    from mailcpu.mtls_transport import accept_mutual_tls
    tls = accept_mutual_tls(listener, worker_name(resident.index), ORIGIN,
                            ssl_context(ca, cert, key, server=True),
                            expected_peer_dns=ORIGIN, max_frame_size=1 << 20)
    try:
        tx, rx = channels(tls, index=resident.index, serving=True)
        deadline = time.monotonic() + TIMEOUT
        record = {}
        while time.monotonic() < deadline:
            def commit(seq, payload):
                record["response"] = resident.handle(payload)
            received = rx.receive(commit=commit)
            if received is not None:
                break
            time.sleep(.005)
        require("response" in record, "missing tensor request")
        result = record["response"]
        # This is an application verdict after the inbound RDATA is admitted.
        sequence = tx.send(result)
        wait_ack(tx, sequence, deadline)
        return {"worker": worker_name(resident.index), "accepted": result["accepted"],
                "tls_version": tls.socket.version(), "receiver_execution_count": resident.executions}
    finally:
        tls.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--packet", type=Path, required=True)
    server.add_argument("--port", type=int, default=0)
    server.add_argument("--sessions", type=int, default=2)
    server.add_argument("--bind", default="127.0.0.1")
    for cmd in (server,):
        cmd.add_argument("--ca", type=Path, required=True)
        cmd.add_argument("--cert", type=Path, required=True)
        cmd.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "serve":
        from mailcpu.socket_transport import SocketTransport
        resident = ResidentShard(args.packet)
        require(0 < args.sessions <= 8 and args.bind == "127.0.0.1", "local listen policy")
        listener = SocketTransport.listen(args.bind, args.port)
        try:
            print(json.dumps({"worker": worker_name(resident.index),
                              "port": listener.getsockname()[1], "pid": os.getpid()}), flush=True)
            for _ in range(args.sessions):
                status = serve_one(listener, resident, args.ca, args.cert, args.key)
                print(json.dumps(status, sort_keys=True), flush=True)
        finally:
            listener.close()


if __name__ == "__main__":
    main()
