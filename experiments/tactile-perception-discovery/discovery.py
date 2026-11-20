"""TPP-002 — Blind identification of observer-relative cross-medium expression.

Executable synthetic plants interact with the learner through genuine OS pipes.
All laws are stipulated fixtures; no physical equipment is connected.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction as Q
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tactile-perception-process"))
from tactile_process import action_wire, decode_action

SCHEMA = "in-formation-space.tpp002.v1"
# Private to the child plant at *execution* time, not inaccessible to a code reader.
# (a, b, c, rho, sensor_gain, offset, additional_quadratic_drive_term)
PLANTS = {
    "electrical": (Q(1), Q(1), Q(1,2), Q(1,2), Q(7), Q(3), Q(0)),
    "hydraulic": (Q(2), Q(3,2), Q(2,3), Q(1,2), Q(11), Q(-5), Q(0)),
    "aliased": (Q(1), Q(2), Q(1,4), Q(1,2), Q(7), Q(3), Q(0)),
    "slow": (Q(2), Q(1), Q(1), Q(3,4), Q(13), Q(2), Q(0)),
    "memoryless": (Q(3), Q(0), Q(1), Q(1,3), Q(5), Q(1), Q(0)),
    "nonlinear": (Q(1), Q(1), Q(1,2), Q(1,2), Q(7), Q(3), Q(1)),
}

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

def ratio(n):
    return f"{n.numerator}/{n.denominator}"

def exact(s):
    if not isinstance(s, str):
        raise ValueError("not a rational observation")
    q = Q(s)
    if ratio(q) != s:
        raise ValueError("noncanonical observation")
    return q

class Unavailable(RuntimeError):
    pass

class Plant:
    """Stateful *synthetic* responder. Parameters are absent from IPC replies."""
    def __init__(self, route, denied=False):
        if route not in PLANTS:
            raise ValueError("unknown route")
        self.route, self.denied = route, denied
        self.x = self.h = Q(0)
        self.prev, self.index = "0" * 64, 0

    def exchange(self, message):
        if not isinstance(message, dict) or message.get("op") not in ("read", "step"):
            raise ValueError("invalid request")
        if set(message) != ({"op"} if message["op"] == "read" else {"op","encoding","wire_hex"}):
            raise ValueError("unexpected request fields")
        op = message["op"]
        if op == "step":
            wire = bytes.fromhex(message["wire_hex"])
            if wire.hex() != message["wire_hex"]:
                raise ValueError("noncanonical wire")
            kind, u = decode_action(wire, message["encoding"])
            if kind == "idle":
                u = Q(0)
            a,b,c,rho,g,o,nonlinear = PLANTS[self.route]
            self.x += a*u + b*self.h + nonlinear*u*u
            self.h = rho*self.h + c*u
        else:
            kind = "read"
        gain, origin = PLANTS[self.route][4:6]
        value = gain*self.x + origin
        packet = {
            "schema": SCHEMA, "scope": "synthetic-not-physical-measurement",
            "route": self.route, "index": self.index, "kind": kind,
            "request_digest": sha256(canonical(message)).hexdigest(),
            "prev": self.prev, "status": "refused" if self.denied else "observed",
            "raw": None if self.denied else ratio(value),
        }
        packet["digest"] = sha256(canonical(packet)).hexdigest()
        self.prev, self.index = packet["digest"], self.index + 1
        return packet

class Observer:
    """Uses real local subprocess pipes; validates the returned *synthetic* receipts."""
    def __init__(self, route, encoding="text", denied=False):
        self.route, self.encoding, self.denied = route, encoding, denied
        self.previous, self.count = "0" * 64, 0
        self.receipts = []
        self.process = None

    def __enter__(self):
        cmd = [sys.executable, "-u", str(Path(__file__).resolve()), "--plant", self.route]
        if self.denied:
            cmd.append("--deny")
        self.process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, bufsize=1)
        return self

    def __exit__(self, *_):
        if self.process:
            self.process.stdin.close()
            self.process.stdout.close()
            self.process.wait(timeout=10)
            self.process.stderr.close()

    def transact(self, message):
        self.process.stdin.write(canonical(message).decode("ascii") + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("plant process did not respond")
        event = json.loads(line)
        expected = {"schema","scope","route","index","kind","request_digest","prev","status","raw","digest"}
        if set(event) != expected or event["schema"] != SCHEMA:
            raise ValueError("unrecognized receipt")
        if event["scope"] != "synthetic-not-physical-measurement" or event["route"] != self.route:
            raise ValueError("wrong scope or source")
        if type(event["index"]) is not int or event["index"] != self.count:
            raise ValueError("out-of-order receipt")
        if event["request_digest"] != sha256(canonical(message)).hexdigest() or event["prev"] != self.previous:
            raise ValueError("broken input binding or ancestry")
        digest = sha256(canonical({k:v for k,v in event.items() if k != "digest"})).hexdigest()
        if event["digest"] != digest:
            raise ValueError("invalid digest")
        if event["status"] not in ("observed", "refused"):
            raise ValueError("invalid status")
        if event["status"] == "refused" and event["raw"] is not None:
            raise ValueError("refused measurement cannot contain data")
        measured = exact(event["raw"]) if event["status"] == "observed" else None
        self.previous, self.count = digest, self.count + 1
        self.receipts.append(event)
        if measured is None:
            raise Unavailable("raw sensor refused; no zero or other value inferred")
        return measured

    def read(self):
        return self.transact({"op":"read"})

    def step(self, action):
        kind, amount = action
        wire = action_wire(kind, amount, self.encoding)
        return self.transact({"op":"step","encoding":self.encoding,"wire_hex":wire.hex()})

@dataclass(frozen=True)
class Law:
    """Identifiable raw-output dynamics; rho=None means unidentified, not zero."""
    origin: Q
    A: Q
    B: Q
    rho: Q | None

    @property
    def ratio(self):
        return self.B / self.A if self.A else None

    def predict(self, actions):
        y, latent, observations = self.origin, Q(0), []
        for kind, command in actions:
            if kind not in ("drive", "idle") or not isinstance(command, Q) or not 0 <= command <= 1:
                raise ValueError("invalid action")
            if kind == "idle" and command:
                raise ValueError("idle command must be zero")
            u = command if kind == "drive" else Q(0)
            y += self.A*u + latent
            if self.B:
                if self.rho is None:
                    raise ValueError("latent dynamics unidentified")
                latent = self.rho*latent + self.B*u
            else:
                latent = Q(0)
            observations.append(y)
        return tuple(observations)

    def serialize(self):
        return {"origin":ratio(self.origin), "A":ratio(self.A), "B":ratio(self.B),
                "rho":ratio(self.rho) if self.rho is not None else None,
                "memory_ratio":ratio(self.ratio) if self.ratio is not None else None}

DRIVE = ("drive", Q(1,2))
IDLE = ("idle", Q(0))
HELDOUT = (("drive", Q(1,4)), IDLE, IDLE, ("drive",Q(3,4)),
           ("drive",Q(1,3)), IDLE)

def identify(route, encoding="text", denied=False):
    """Four observations; no access to internal plant parameters."""
    with Observer(route, encoding, denied=denied) as observer:
        y0 = observer.read()
        y1 = observer.step(DRIVE)
        y2 = observer.step(IDLE)
        y3 = observer.step(IDLE)
        A = 2*(y1-y0)
        B = 2*(y2-y1)
        rho = (y3-y2)/(y2-y1) if B else None
        return Law(y0,A,B,rho), observer.receipts

def transfer(source, target_origin, target_after, u=Q(1,2)):
    """Target has only two readings; transferred dynamics remain a hypothesis."""
    if not 0 < u <= 1:
        raise ValueError("invalid target pulse")
    if source.ratio is None:
        raise Unavailable("cannot infer source memory ratio")
    A = (target_after-target_origin)/u
    B = A*source.ratio
    if B and source.rho is None:
        raise Unavailable("unidentified source decay")
    return Law(target_origin,A,B,source.rho if B else None)

def measure(route, actions, encoding="json"):
    with Observer(route, encoding) as observer:
        y0 = observer.read()
        outputs = tuple(observer.step(action) for action in actions)
        return y0, outputs, observer.receipts

def challenge(law, route, actions=HELDOUT):
    y0, observed, receipts = measure(route, actions)
    predicted = law.predict(actions)
    failures = [i for i,(p,o) in enumerate(zip(predicted,observed)) if p!=o]
    return {"match":not failures, "first_failure":failures[0] if failures else None,
            "predicted":[ratio(x) for x in predicted],
            "observed":[ratio(x) for x in observed],
            "initial":ratio(y0), "receipts":len(receipts)}

def refine(source, route):
    """Two additional idle readings can refute and refine transferred decay."""
    with Observer(route, "json") as observer:
        y0 = observer.read()
        y1 = observer.step(DRIVE)
        preliminary = transfer(source,y0,y1)
        y2 = observer.step(IDLE)
        y3 = observer.step(IDLE)
        B = 2*(y2-y1)
        corrected = Law(y0,2*(y1-y0),B,(y3-y2)/(y2-y1) if B else None)
        diverged = preliminary.predict((DRIVE,IDLE,IDLE)) != (y1,y2,y3)
        return corrected, {"contradiction":diverged,"additional_observations":2,
                           "raw":[ratio(q) for q in (y0,y1,y2,y3)]}

def experiment():
    source, source_receipts = identify("electrical")
    with Observer("hydraulic", "json") as observer:
        y0, y1 = observer.read(), observer.step(DRIVE)
    target = transfer(source,y0,y1)
    with Observer("slow") as observer:
        z0, z1 = observer.read(), observer.step(DRIVE)
    wrong = transfer(source,z0,z1)
    corrected, discrepancy = refine(source,"slow")
    nonlinear, _ = identify("nonlinear")
    memoryless, _ = identify("memoryless")
    alias, _ = identify("aliased")
    return {
        "schema":"in-formation-space.tpp002.result.v1",
        "scope":"synthetic-exact-subprocess-only",
        "source_law":source.serialize(), "source_training_reads":len(source_receipts),
        "target_law":target.serialize(), "target_training_reads":2,
        "target_heldout":challenge(target,"hydraulic"),
        "different_decay_heldout":challenge(wrong,"slow"),
        "correction":discrepancy, "corrected_law":corrected.serialize(),
        "corrected_heldout":challenge(corrected,"slow"),
        "out_of_class_heldout":challenge(nonlinear,"nonlinear"),
        "memoryless_rho_unidentified":memoryless.rho is None,
        "hidden_alias_same_observation_law":alias == source,
    }

def plant_main(route, denied):
    plant = Plant(route, denied)
    for line in sys.stdin:
        try:
            print(json.dumps(plant.exchange(json.loads(line)), sort_keys=True, separators=(",", ":")),flush=True)
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            print(json.dumps({"status":"invalid-request","error":type(exc).__name__}),flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plant",choices=sorted(PLANTS))
    parser.add_argument("--deny",action="store_true")
    args = parser.parse_args()
    if args.plant:
        plant_main(args.plant,args.deny)
    else:
        print(json.dumps(experiment(),indent=2,sort_keys=True))
