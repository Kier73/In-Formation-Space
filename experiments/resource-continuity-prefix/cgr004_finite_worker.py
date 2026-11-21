"""CGR-004: fixed, bounded non-affine finite Ground interpreter OS worker.

This is a source-derived data interpreter, never arbitrary Python execution.
It deliberately reconstructs transition maps *without* NCR-004's quotient
algorithm, providing an independent execution implementation to compare with
NCR's native mathematical verifier at the receiver.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from cgr003_observed_ecpu import load_epoch

REQUEST = "ifs.cgr004.finite-native-call.v1"
REPLY = "ifs.cgr004.finite-native-reply.v1"


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _bounded_decimal(value):
    if (type(value) is not str or not 1 <= len(value) <= 1250
            or not value.isascii() or not value.isdecimal()
            or value != str(int(value))):
        raise ValueError("noncanonical logical coordinate")
    n = int(value)
    if n.bit_length() > 4096:
        raise ValueError("logical time budget exceeded")
    return n


def run(root: Path, host: str, request: dict) -> dict:
    if (type(request) is not dict or
        set(request) != {"schema","host","source_head","initial","word",
                         "repetitions","nonce"} or
        request["schema"] != REQUEST or request["host"] != host or
        type(request["source_head"]) is not str or
        type(request["nonce"]) is not str or len(request["nonce"]) != 64 or
        any(c not in "0123456789abcdef" for c in request["nonce"])):
        raise ValueError("worker request identity/schema mismatch")
    epoch = load_epoch(root)
    if request["source_head"] != epoch.source_head:
        raise ValueError("source changed from pinned epoch")
    initial = request["initial"]
    word = request["word"]
    if (type(initial) is not int or initial not in epoch.initial or
        type(word) is not list or not 1 <= len(word) <= 256 or
        any(type(i) is not int or i < 0 or i >= len(epoch.actions) for i in word)):
        raise ValueError("invalid admitted initial state or operation word")
    repetitions = _bounded_decimal(request["repetitions"])
    # Fail closed on incomplete source rather than silently assuming a loop.
    edges = {}
    labels = {}
    for event in epoch.witnesses:
        edge = (event.before, event.action)
        if edge in edges and edges[edge] != event.after:
            raise ValueError("contradictory transition")
        edges[edge] = event.after
        for state, output in ((event.before,event.before_output),
                              (event.after,event.after_output)):
            if state in labels and labels[state] != output:
                raise ValueError("contradictory readout")
            labels[state] = output
    if any((s,a) not in edges for s in epoch.states for a in epoch.actions):
        raise ValueError("unknown state/action transition")
    if any(s not in labels for s in epoch.states):
        raise ValueError("unknown state readout")
    # Compose explicitly witnessed maps, not NCR-004 quotient operators.
    full = {}
    for state in epoch.states:
        successor = state
        for action in word:
            successor = edges[(successor, epoch.actions[action])]
        full[state] = successor
    # Fast exponentiation of the independent full-state map.
    result = {s:s for s in epoch.states}
    power = full
    k = repetitions
    while k:
        if k & 1:
            result = {s: power[result[s]] for s in epoch.states}
        k >>= 1
        if k:
            power = {s: power[power[s]] for s in epoch.states}
    final = result[initial]
    receipt = {
        "schema": REPLY, "host": host, "source_head": epoch.source_head,
        "request_digest": digest(request),
        "state": final, "output": labels[final],
        "execution": "independent-witnessed-state-map-powers",
        "effect_authorized": False,
    }
    return {**receipt, "receipt_digest": digest(receipt)}


def main(args):
    if len(args) != 2:
        return 2
    root, host = Path(args[0]), args[1]
    try:
        data = sys.stdin.buffer.readline(8193)
        if (not data.endswith(b"\n") or len(data) > 8192 or
            sys.stdin.buffer.read(1) or not 0 < len(data) <= 8192):
            return 3
        request = json.loads(data.decode("ascii"))
        if canonical(request) + b"\n" != data:
            return 4
        response = run(root, host, request)
        sys.stdout.buffer.write(canonical(response) + b"\n")
        return 0
    except (ValueError, TypeError, KeyError, IndexError, OSError,
            json.JSONDecodeError, UnicodeError):
        return 5


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
